# Copyright 2014 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from oslo.config import cfg
from neutron.common import constants as q_const
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants as plugin_const
from neutron.common.exceptions import InvalidConfigurationOption
from neutron.services.loadbalancer import constants as lb_const

from f5.bigip import bigip as f5_bigip
from f5.common import constants as f5const
from f5.bigip import exceptions as f5ex
from f5.bigip import bigip_interfaces

from eventlet import greenthread
import os
import uuid
import urllib2
import netaddr
import datetime
import hashlib
import random
from time import time
import logging as std_logging


LOG = logging.getLogger(__name__)
NS_PREFIX = 'qlbaas-'
APP_COOKIE_RULE_PREFIX = 'app_cookie_'
RPS_THROTTLE_RULE_PREFIX = 'rps_throttle_'

__VERSION__ = '0.1.1'

# configuration objects specific to iControl driver
OPTS = [
    cfg.StrOpt(
        'f5_device_type',
        default='external',
        help=_('What type of device onboarding')
    ),
    cfg.StrOpt(
        'f5_ha_type',
        default='pair',
        help=_('Are we standalone, pair(active/standby), or scalen')
    ),
    cfg.ListOpt(
        'f5_external_physical_mappings',
        default='default:1.1:True',
        help=_('Mapping between Neutron physical_network to interfaces')
    ),
    cfg.StrOpt(
        'sync_mode',
        default='replication',
        help=_('The sync mechanism: autosync or replication'),
    ),
    cfg.StrOpt(
        'f5_sync_mode',
        default='replication',
        help=_('The sync mechanism: autosync or replication'),
    ),
    cfg.StrOpt(
        'f5_vtep_folder',
        default='Common',
        help=_('Folder for the VTEP SelfIP'),
    ),
    cfg.StrOpt(
        'f5_vtep_selfip_name',
        default=None,
        help=_('Name of the VTEP SelfIP'),
    ),
    cfg.ListOpt(
        'advertised_tunnel_types',
        default=['gre', 'vxlan'],
        help=_('tunnel types which are advertised to other VTEPs'),
    ),
    cfg.BoolOpt(
        'f5_populate_static_arp',
        default=True,
        help=_('create static arp entries based on service entries'),
    ),
    cfg.BoolOpt(
        'f5_route_domain_strictness',
        default=False,
        help=_('Strict route domain isolation'),
    ),
    cfg.BoolOpt(
        'f5_common_external_networks',
        default=True,
        help=_('Treat external networks as common')
    ),
    cfg.StrOpt(
        'icontrol_hostname',
        help=_('The hostname (name or IP address) to use for iControl access'),
    ),
    cfg.StrOpt(
        'icontrol_username',
        default='admin',
        help=_('The username to use for iControl access'),
    ),
    cfg.StrOpt(
        'icontrol_password',
        default='admin',
        secret=True,
        help=_('The password to use for iControl access'),
    ),
    cfg.IntOpt(
        'icontrol_connection_timeout',
        default=30,
        help=_('How many seconds to timeout a connection to BIG-IP'),
    ),
    cfg.IntOpt(
        'icontrol_connection_retry_interval',
        default=10,
        help=_('How many seconds to wait between retry connection attempts'),
    ),
    cfg.DictOpt(
        'common_network_ids',
        default={},
        help=_('network uuid to existing Common networks mapping')
    ),
    cfg.StrOpt(
        'environment_prefix',
        default='',
        help=_('The object name prefix for this environment'),
    ),
]


def request_index(request_queue, request_id):
    for request in request_queue:
        if request[0] == request_id:
            return request_queue.index(request)


def is_connected(method):
    """Decorator to check we are connected before provisioning."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        if instance.connected:
            try:
                return method(*args, **kwargs)
            except IOError as ioe:
                instance.non_connected()
                raise ioe
        else:
            instance.non_connected()
            LOG.error(_('Cannot execute %s. Not connected.'
                        % method.__name__))
    return wrapper


def serialized(method_name):
    def real_serialized(method):
        """Decorator to serialize calls to configure via iControl"""
        def wrapper(*args, **kwargs):
            # args[0] must be an instance of iControlDriver
            service_queue = args[0].service_queue
            my_request_id = uuid.uuid4()

            service = None
            if len(args) > 0:
                last_arg = args[-1]
                if isinstance(last_arg, dict) and ('pool' in last_arg):
                    service = last_arg
            if 'service' in kwargs:
                service = kwargs['service']

            # Consolidate create_member requests for the same pool.
            #
            # NOTE: The following block of code alters the state of
            # a queue that other greenthreads are waiting behind.
            # This code assumes it will not be preempted by another
            # greenthread while running. It does not do I/O or call any
            # other monkey-patched code which might cause a context switch.
            # To avoid race conditions, DO NOT add logging to this code
            # block.

            #num_requests = len(service_queue)

            # queue optimization

            #if num_requests > 1 and method_name == 'create_member':
            #    cur_pool_id = service['pool']['id']
                #cur_index = num_requests - 1
                # do not attempt to replace the first entry (index 0)
                # because it may already be in process.
                #while cur_index > 0:
                #    (check_request, check_method, check_service) = \
                #        service_queue[cur_index]
                #    if check_service['pool']['id'] != cur_pool_id:
                #        cur_index -= 1
                #        continue
                #    if check_method != 'create_member':
                #        break
                    # move this request up in the queue and return
                    # so that existing thread can handle it
                #    service_queue[cur_index] = \
                #        (check_request, check_method, service)
                #    return

            # End of code block which assumes no preemption.

            req = (my_request_id, method_name, service)
            service_queue.append(req)
            reqs_ahead_of_us = request_index(service_queue, my_request_id)
            while reqs_ahead_of_us != 0:
                if reqs_ahead_of_us == 1:
                    # it is almost our turn. get ready
                    waitsecs = .01
                else:
                    waitsecs = reqs_ahead_of_us * .5
                if waitsecs > .01:
                    LOG.debug('%s request %s is blocking'
                          ' for %.2f secs - queue depth: %d'
                          % (str(method_name), my_request_id,
                             waitsecs, len(service_queue)))
                greenthread.sleep(waitsecs)
                reqs_ahead_of_us = request_index(service_queue, my_request_id)
            try:
                LOG.debug('%s request %s is running with queue depth: %d'
                          % (str(method_name), my_request_id,
                          len(service_queue)))
                start_time = time()
                result = method(*args, **kwargs)
                LOG.debug('%s request %s took %.5f secs'
                          % (str(method_name), my_request_id,
                             time() - start_time))
            except:
                LOG.error('%s request %s FAILED'
                          % (str(method_name), my_request_id))
                raise
            finally:
                service_queue.pop(0)
            return result
        return wrapper
    return real_serialized


def check_monitor_delete(service):
    if service['pool']['status'] == plugin_const.PENDING_DELETE:
        # Everything needs to be go with the pool, so overwrite
        # service state to appropriately remove all elements
        service['vip']['status'] = plugin_const.PENDING_DELETE
        for member in service['members']:
            member['status'] = plugin_const.PENDING_DELETE
        for monitor in service['pool']['health_monitors_status']:
            monitor['status'] = plugin_const.PENDING_DELETE


class iControlDriver(object):

    # BIG-IP containers
    __bigips = {}
    __traffic_groups = []

    # mappings
    __vips_to_traffic_group = {}
    __gw_to_traffic_group = {}

    # scheduling counts
    __vips_on_traffic_groups = {}
    __gw_on_traffic_groups = {}

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(OPTS)
        self.device_type = conf.f5_device_type
        self.plugin_rpc = None
        self.connected = False
        self.service_queue = []
        self.agent_configurations = {}

        if self.conf.f5_global_routed_mode:
            LOG.info(_('WARNING - f5_global_routed_mode enabled.'
                       ' There will be no L2 or L3 orchestration'
                       ' or tenant isolation provisioned. All vips'
                       ' and pool members must be routable through'
                       ' pre-provisioned SelfIPs.'))
            self.conf.use_namespaces = False
            self.conf.f5_snat_mode = True
            self.conf.f5_snat_addresses_per_subnet = 0
            self.agent_configurations['tunnel_types'] = []
            self.agent_configurations['bridge_mappings'] = {}
        else:
            self.interface_mapping = {}
            self.tagging_mapping = {}

            self.tunnel_types = self.conf.advertised_tunnel_types

            self.agent_configurations['tunnel_types'] = self.tunnel_types

            # map format is   phynet:interface:tagged
            for maps in self.conf.f5_external_physical_mappings:
                intmap = maps.split(':')
                net_key = str(intmap[0]).strip()
                if len(intmap) > 3:
                    net_key = net_key + ':' + str(intmap[3]).strip()
                self.interface_mapping[net_key] = str(intmap[1]).strip()
                self.tagging_mapping[net_key] = str(intmap[2]).strip()
                LOG.debug(_('physical_network %s = interface %s, tagged %s'
                            % (net_key, intmap[1], intmap[2])
                            ))
            self.agent_configurations['bridge_mappings'] = \
                                                    self.interface_mapping

            for net_id in self.conf.common_network_ids:
                LOG.debug(_('network %s will be mapped to /Common/%s'
                            % (net_id, self.conf.common_network_ids[net_id])))

            self.agent_configurations['common_networks'] = \
                                                  self.conf.common_network_ids

            if self.conf.environment_prefix:
                LOG.debug(_('BIG-IP name prefix for this environment: %s' %
                         self.conf.environment_prefix))
                bigip_interfaces.OBJ_PREFIX = \
                                          self.conf.environment_prefix + '_'
                self.agent_configurations['environment_prefix'] = \
                                          self.conf.environment_prefix

            LOG.debug(_('Setting static ARP population to %s'
                        % self.conf.f5_populate_static_arp))
            f5const.FDB_POPULATE_STATIC_ARP = self.conf.f5_populate_static_arp

        self._init_connection()

        LOG.info(_('iControlDriver initialized to %d hosts with username:%s'
                    % (len(self.__bigips), self.username)))
        LOG.info(_('iControlDriver dynamic agent configurations:%s'
                    % self.agent_configurations))

    @serialized('exists')
    @is_connected
    def exists(self, service):
        return self._service_exists(service)

    def flush_cache(self):
        bigips = self.__bigips.values()
        for set_bigip in bigips:
            set_bigip.assured_networks = []
            set_bigip.assured_snat_subnets = []
            set_bigip.assured_gateway_subnets = []

    @serialized('sync')
    @is_connected
    def sync(self, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('create_vip')
    @is_connected
    def create_vip(self, vip, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('update_vip')
    @is_connected
    def update_vip(self, old_vip, vip, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('delete_vip')
    @is_connected
    def delete_vip(self, vip, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('create_pool')
    @is_connected
    def create_pool(self, pool, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('update_pool')
    @is_connected
    def update_pool(self, old_pool, pool, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('delete_pool')
    @is_connected
    def delete_pool(self, pool, service):
        self._assure_service(service)

    @serialized('create_member')
    @is_connected
    def create_member(self, member, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('update_member')
    @is_connected
    def update_member(self, old_member, member, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('delete_member')
    @is_connected
    def delete_member(self, member, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('create_pool_health_monitor')
    @is_connected
    def create_pool_health_monitor(self, health_monitor, pool, service):
        self._assure_service(service)
        return True

    @serialized('update_health_monitor')
    @is_connected
    def update_health_monitor(self, old_health_monitor,
                              health_monitor, pool, service):
        # The altered health monitor does not mark its
        # status as PENDING_UPDATE properly.  Force it.
        for i in range(len(service['pool']['health_monitors_status'])):
            if service['pool']['health_monitors_status'][i]['monitor_id'] == \
                                                          health_monitor['id']:
                service['pool']['health_monitors_status'][i]['status'] = \
                                                   plugin_const.PENDING_UPDATE
        self._assure_service(service)
        return True

    @serialized('delete_pool_health_monitor')
    @is_connected
    def delete_pool_health_monitor(self, health_monitor, pool, service):
        # Two behaviors of the plugin dictate our behavior here.
        # 1. When a plug-in deletes a monitor that is not being
        # used by a pool, it does not notify the drivers. Therefore,
        # we need to aggresively remove monitors that are not in use.
        # 2. When a plug-in deletes a monitor which is being
        # used by one or more pools, it calls delete_pool_health_monitor
        # against the driver that owns each pool, but it does not
        # set status to PENDING_DELETE in the health_monitors_status
        # list for the pool monitor. This may be a bug or perhaps this
        # is intended to be a synchronous process.
        #
        # In contrast, when a pool monitor association is deleted, the
        # PENDING DELETE status is set properly, so this code will
        # run unnecessarily in that case.
        for status in service['pool']['health_monitors_status']:
            if status['monitor_id'] == health_monitor['id']:
                # Signal to our own code that we should delete the
                # pool health monitor. The plugin should do this.
                status['status'] = plugin_const.PENDING_DELETE

        self._assure_service(service)
        return True

    @serialized('get_stats')
    @is_connected
    def get_stats(self, service):
        # use pool stats because the pool_id is the
        # the service definition... not the vip
        #
        stats = {}
        stats[lb_const.STATS_IN_BYTES] = 0
        stats[lb_const.STATS_OUT_BYTES] = 0
        stats[lb_const.STATS_ACTIVE_CONNECTIONS] = 0
        stats[lb_const.STATS_TOTAL_CONNECTIONS] = 0
        members = {}
        bigip = self._get_bigip()
        for hostbigip in bigip.group_bigips:
            # It appears that stats are collected for pools in a pending delete
            # state which means that if those messages are queued (or delayed)
            # it can result in the process of a stats request after the pool
            # and tenant are long gone. Check if the tenant exists.
            if not service['pool'] or not hostbigip.system.folder_exists(
               bigip_interfaces.OBJ_PREFIX + service['pool']['tenant_id']):
                return None
            pool = service['pool']
            bigip_stats = hostbigip.pool.get_statistics(name=pool['id'],
                                                    folder=pool['tenant_id'])
            if 'STATISTIC_SERVER_SIDE_BYTES_IN' in bigip_stats:
                stats[lb_const.STATS_IN_BYTES] += \
                    bigip_stats['STATISTIC_SERVER_SIDE_BYTES_IN']
                stats[lb_const.STATS_OUT_BYTES] += \
                    bigip_stats['STATISTIC_SERVER_SIDE_BYTES_OUT']
                stats[lb_const.STATS_ACTIVE_CONNECTIONS] += \
                    bigip_stats['STATISTIC_SERVER_SIDE_CURRENT_CONNECTIONS']
                stats[lb_const.STATS_TOTAL_CONNECTIONS] += \
                    bigip_stats['STATISTIC_SERVER_SIDE_TOTAL_CONNECTIONS']
                if hasattr(service, 'members'):
                    # need to get members for this pool and update their status
                    states = hostbigip.pool.get_members_monitor_status(
                                                    name=pool['id'],
                                                    folder=pool['tenant_id'])
                    for member in service['members']:
                        for state in states:
                            if member['address'] == state['addr'] and\
                               member['protocol_port'] == state['port']:
                                if state['state'] == 'MONITOR_STATUS_UP':
                                    if member['id'] in members:
                                        # member has to be up on all host
                                        # in the the BIG-IP cluster
                                        if members[member['id']] != 'DOWN':
                                            members[member['id']] = 'ACTIVE'
                                else:
                                    members[member['id']] = 'DOWN'
        stats['members'] = {'members': members}
        return stats

    def remove_orphans(self, services):
        for host in self.__bigips:
            bigip = self.__bigips[host]
            existing_tenants = []
            existing_pools = []
            for service in services:
                existing_tenants.append(service.tenant_id)
                existing_pools.append(service.pool_id)
            # delete all unknown pools
            bigip.pool.purge_orhpaned_pools(existing_pools)
            # delete all unknown tenants
            bigip.system.purge_orphaned_folders(existing_tenants)

    def fdb_add(self, fdb_entries):
        for network in fdb_entries:
            net = {
                    'name': network,
                    'provider:network_type': \
                              fdb_entries[network]['network_type'],
                    'provider:segmentation_id': \
                              fdb_entries[network]['segment_id']
                  }
            tn = self._get_tunnel_name(net)
            bigip = self._get_bigip()
            add_fdb = {}
            for vtep in fdb_entries[network]['ports']:
                for host in self.__bigips:
                    bigip = self.__bigips[host]
                    if hasattr(bigip, 'local_ip') and vtep != bigip.local_ip:
                        if fdb_entries[network]['network_type'] == 'gre':
                            folder = bigip.l2gre.get_tunnel_folder(
                                                          tunnel_name=tn)
                            if folder:
                                entries = fdb_entries[network]['ports'][vtep]
                                for ent in entries:
                                    if ent[0] != '00:00:00:00:00:00':
                                        if not tn in add_fdb:
                                            add_fdb[tn] = {}
                                        add_fdb[tn]['folder'] = folder
                                        if not 'records' in add_fdb[tn]:
                                            add_fdb[tn]['records'] = {}
                                        add_fdb[tn]['records'][ent[0]] = \
                                         {'endpoint': vtep,
                                          'ip_address': ent[1]}
                        if fdb_entries[network]['network_type'] == 'vxlan':
                            folder = bigip.l2gre.get_tunnel_folder(
                                                          tunnel_name=tn)
                            if folder:
                                entries = fdb_entries[network]['ports'][vtep]
                                for ent in entries:
                                    if ent[0] != '00:00:00:00:00:00':
                                        if not tn in add_fdb:
                                            add_fdb[tn] = {}
                                        add_fdb[tn]['folder'] = folder
                                        if not 'records' in add_fdb[tn]:
                                            add_fdb[tn]['records'] = {}
                                        add_fdb[tn]['records'][ent[0]] = \
                                         {'endpoint': vtep,
                                          'ip_address': ent[1]}
            if len(add_fdb) > 0:
                if fdb_entries[network]['network_type'] == 'vxlan':
                    bigip.vxlan.add_fdb_entries(tunnel_name=tn,
                                                fdb_entries=add_fdb)
                if fdb_entries[network]['network_type'] == 'vxlan':
                    bigip.l2gre.add_fdb_entries(tunnel_name=tn,
                                                fdb_entries=add_fdb)

    def fdb_remove(self, fdb_entries):
        for network in fdb_entries:
            net = {
                    'name': network,
                    'provider:network_type': \
                              fdb_entries[network]['network_type'],
                    'provider:segmentation_id': \
                              fdb_entries[network]['segment_id']
                  }
            tn = self._get_tunnel_name(net)
            bigip = self._get_bigip()
            remove_fdb = {}
            for vtep in fdb_entries[network]['ports']:
                for host in self.__bigips:
                    bigip = self.__bigips[host]
                    if hasattr(bigip, 'local_ip') and vtep != bigip.local_ip:
                        if fdb_entries[network]['network_type'] == 'gre':
                            folder = bigip.l2gre.get_tunnel_folder(
                                                          tunnel_name=tn)
                            if folder:
                                entries = fdb_entries[network]['ports'][vtep]
                                for ent in entries:
                                    if ent[0] != '00:00:00:00:00:00':
                                        if not tn in remove_fdb:
                                            remove_fdb[tn] = {}
                                        remove_fdb[tn]['folder'] = folder
                                        if not 'records' in remove_fdb[tn]:
                                            remove_fdb[tn]['records'] = {}
                                        remove_fdb[tn]['records'][ent[0]] = \
                                         {'endpoint': vtep,
                                          'ip_address': ent[1]}
                        if fdb_entries[network]['network_type'] == 'vxlan':
                            folder = bigip.l2gre.get_tunnel_folder(
                                                          tunnel_name=tn)
                            if folder:
                                entries = fdb_entries[network]['ports'][vtep]
                                for ent in entries:
                                    if ent[0] != '00:00:00:00:00:00':
                                        if not tn in remove_fdb:
                                            remove_fdb[tn] = {}
                                        remove_fdb[tn]['folder'] = folder
                                        if not 'records' in remove_fdb[tn]:
                                            remove_fdb[tn]['records'] = {}
                                        remove_fdb[tn]['records'][ent[0]] = \
                                         {'endpoint': vtep,
                                          'ip_address': ent[1]}
            if len(remove_fdb) > 0:
                if fdb_entries[network]['network_type'] == 'vxlan':
                    bigip.vxlan.delete_fdb_entries(tunnel_name=tn,
                                                fdb_entries=remove_fdb)
                if fdb_entries[network]['network_type'] == 'vxlan':
                    bigip.l2gre.delete_fdb_entries(tunnel_name=tn,
                                                fdb_entries=remove_fdb)

    def fdb_update(self, fdb_entries):
        for network in fdb_entries:
            net = {
                    'name': network,
                    'provider:network_type': \
                              fdb_entries[network]['network_type'],
                    'provider:segmentation_id': \
                              fdb_entries[network]['segment_id']
                  }
            tn = self._get_tunnel_name(net)
            bigip = self._get_bigip()
            update_fdb = {}
            for vtep in fdb_entries[network]['ports']:
                for host in self.__bigips:
                    bigip = self.__bigips[host]
                    if hasattr(bigip, 'local_ip') and vtep != bigip.local_ip:
                        if fdb_entries[network]['network_type'] == 'gre':
                            folder = bigip.l2gre.get_tunnel_folder(
                                                          tunnel_name=tn)
                            if folder:
                                entries = fdb_entries[network]['ports'][vtep]
                                for ent in entries:
                                    if ent[0] != '00:00:00:00:00:00':
                                        if not tn in update_fdb:
                                            update_fdb[tn] = {}
                                        update_fdb[tn]['folder'] = folder
                                        if not 'records' in update_fdb[tn]:
                                            update_fdb[tn]['records'] = {}
                                        update_fdb[tn]['records'][ent[0]] = \
                                         {'endpoint': vtep,
                                          'ip_address': ent[1]}
                        if fdb_entries[network]['network_type'] == 'vxlan':
                            folder = bigip.l2gre.get_tunnel_folder(
                                                          tunnel_name=tn)
                            if folder:
                                entries = fdb_entries[network]['ports'][vtep]
                                for ent in entries:
                                    if ent[0] != '00:00:00:00:00:00':
                                        if not tn in update_fdb:
                                            update_fdb[tn] = {}
                                        update_fdb[tn]['folder'] = folder
                                        if not 'records' in update_fdb[tn]:
                                            update_fdb[tn]['records'] = {}
                                        update_fdb[tn]['records'][ent[0]] = \
                                         {'endpoint': vtep,
                                          'ip_address': ent[1]}
            if len(update_fdb) > 0:
                if fdb_entries[network]['network_type'] == 'vxlan':
                    bigip.vxlan.add_fdb_entries(tunnel_name=tn,
                                                fdb_entries=update_fdb)
                if fdb_entries[network]['network_type'] == 'vxlan':
                    bigip.l2gre.add_fdb_entries(tunnel_name=tn,
                                                fdb_entries=update_fdb)

    def tunnel_sync(self):
        resync = False
        for host in self.__bigips:
            bigip = self.__bigips[host]
            if hasattr(bigip, 'local_ip') and bigip.local_ip:
                try:
                    # send out an update to all compute agents
                    # to get the bigips associated with the br-tun
                    # interface.
                    for tunnel_type in self.tunnel_types:
                        if hasattr(self, 'tunnel_rpc'):
                            self.tunnel_rpc.tunnel_sync(self.context,
                                                        bigip.local_ip,
                                                        tunnel_type)
                except Exception as exp:
                    LOG.debug(
                        _("Unable to sync tunnel IP %(local_ip)s: %(e)s"),
                          {'local_ip': bigip.local_ip, 'e': exp})
                    resync = True
        return resync

    def non_connected(self):
        now = datetime.datetime.now()
        if (now - self.__last_connect_attempt).total_seconds() > \
                self.conf.icontrol_connection_retry_interval:
            self.connected = False
            self._init_connection()

    # A context used for storing information used to sync
    # the service request with the current configuration
    class AssureServiceContext:
        def __init__(self):
            self.device_group = None
            # keep track of which subnets we should check to delete
            # for a deleted vip or member
            self.check_for_delete_subnets = {}

            # If we add an IP to a subnet we must not delete the subnet
            self.do_not_delete_subnets = []

    class SubnetInfo:
        def __init__(self, network=None, subnet=None):
            self.network = network
            self.subnet = subnet

    def _service_exists(self, service):
        bigip = self._get_bigip()
        if not service['pool']:
            return False
        return bigip.pool.exists(name=service['pool']['id'],
                                 folder=service['pool']['tenant_id'])

    def _assure_service(self, service):
        if not service['pool']:
            return
        bigip = self._get_bigip()
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        ctxs = {}
        for prep_bigip in bigips:
            ctxs[prep_bigip.device_name] = self.AssureServiceContext()

        check_monitor_delete(service)

        start_time = time()
        self._assure_pool_create(service['pool'], bigip)
        LOG.debug("    _assure_pool_create took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_pool_monitors(service, bigip)
        LOG.debug("    _assure_pool_monitors took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_members(service, bigip, ctxs)
        LOG.debug("    _assure_members took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_vip(service, bigip, ctxs)
        LOG.debug("    _assure_vip took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_pool_delete(service, bigip)
        LOG.debug("    _assure_pool_delete took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_delete_networks(service, bigip, ctxs)
        LOG.debug("    _assure_delete_networks took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_tenant_cleanup(service, bigip, ctxs)
        LOG.debug("    _assure_tenant_cleanup took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._sync_if_clustered(bigip)
        LOG.debug("    sync took %.5f secs" % (time() - start_time))

    #
    # Provision Pool - Create/Update
    #
    def _assure_pool_create(self, pool, bigip):
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            self._assure_device_pool_create(pool, bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_pool_create(self, pool, bigip, on_last_bigip):
        if not pool['status'] == plugin_const.PENDING_DELETE:
            desc = pool['name'] + ':' + pool['description']
            bigip.pool.create(name=pool['id'],
                              lb_method=pool['lb_method'],
                              description=desc,
                              folder=pool['tenant_id'])
            if pool['status'] == plugin_const.PENDING_UPDATE:
                # make sure pool attributes are correct
                bigip.pool.set_lb_method(name=pool['id'],
                                         lb_method=pool['lb_method'],
                                         folder=pool['tenant_id'])
                bigip.pool.set_description(name=pool['id'],
                                           description=desc,
                                           folder=pool['tenant_id'])
                if on_last_bigip:
                    update_pool = self.plugin_rpc.update_pool_status
                    update_pool(pool['id'],
                                status=plugin_const.ACTIVE,
                                status_description='pool updated')
            if pool['status'] == plugin_const.PENDING_CREATE:
                if on_last_bigip:
                    update_pool = self.plugin_rpc.update_pool_status
                    update_pool(pool['id'],
                                status=plugin_const.ACTIVE,
                                status_description='pool created')

    #
    # Provision Health Monitors - Create/Update
    #
    def _assure_pool_monitors(self, service, bigip):
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            self._assure_device_pool_monitors(service, bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_pool_monitors(self, service, bigip, on_last_bigip):
        pool = service['pool']
        # Current monitors on the pool according to BigIP
        existing_monitors = bigip.pool.get_monitors(name=pool['id'],
                                                    folder=pool['tenant_id'])
        #LOG.debug(_("Pool: %s before assurance has monitors: %s"
        #            % (pool['id'], existing_monitors)))

        health_monitors_status = {}
        for monitor in pool['health_monitors_status']:
            health_monitors_status[monitor['monitor_id']] = \
                monitor['status']

        # Current monitor associations according to Neutron
        for monitor in service['health_monitors']:
            found_existing_monitor = monitor['id'] in existing_monitors
            if monitor['id'] in health_monitors_status and \
                health_monitors_status[monitor['id']] == \
                    plugin_const.PENDING_DELETE:
                bigip.pool.remove_monitor(name=pool['id'],
                                          monitor_name=monitor['id'],
                                          folder=pool['tenant_id'])
                if on_last_bigip:
                    self.plugin_rpc.health_monitor_destroyed(
                        health_monitor_id=monitor['id'],
                        pool_id=pool['id'])
                # not sure if the monitor might be in use
                try:
                    LOG.debug(_('Deleting %s monitor /%s/%s'
                                % (monitor['type'],
                                   pool['tenant_id'],
                                   monitor['id'])))
                    bigip.monitor.delete(name=monitor['id'],
                                         mon_type=monitor['type'],
                                         folder=pool['tenant_id'])
                except:
                    pass
            else:
                update_status = False
                if not found_existing_monitor:
                    timeout = int(monitor['max_retries']) * \
                              int(monitor['timeout'])
                    bigip.monitor.create(name=monitor['id'],
                                         mon_type=monitor['type'],
                                         interval=monitor['delay'],
                                         timeout=timeout,
                                         send_text=None,
                                         recv_text=None,
                                         folder=monitor['tenant_id'])
                    self._update_monitor(bigip, monitor, set_times=False)
                    update_status = True
                else:
                    if health_monitors_status[monitor['id']] == \
                            plugin_const.PENDING_UPDATE:
                        self._update_monitor(bigip, monitor)
                        update_status = True

                if not found_existing_monitor:
                    bigip.pool.add_monitor(name=pool['id'],
                                       monitor_name=monitor['id'],
                                       folder=pool['tenant_id'])
                    update_status = True

                if update_status and on_last_bigip:
                    self.plugin_rpc.update_health_monitor_status(
                                    pool_id=pool['id'],
                                    health_monitor_id=monitor['id'],
                                    status=plugin_const.ACTIVE,
                                    status_description='monitor active')

            if found_existing_monitor:
                existing_monitors.remove(monitor['id'])

        LOG.debug(_("Pool: %s removing monitors %s"
                    % (pool['id'], existing_monitors)))
        # get rid of monitors no longer in service definition
        for monitor in existing_monitors:
            bigip.monitor.delete(name=monitor,
                                 mon_type=None,
                                 folder=pool['tenant_id'])

    def _update_monitor(self, bigip, monitor, set_times=True):
        if set_times:
            timeout = int(monitor['max_retries']) * \
                      int(monitor['timeout'])
            # make sure monitor attributes are correct
            bigip.monitor.set_interval(name=monitor['id'],
                               mon_type=monitor['type'],
                               interval=monitor['delay'],
                               folder=monitor['tenant_id'])
            bigip.monitor.set_timeout(name=monitor['id'],
                              mon_type=monitor['type'],
                              timeout=timeout,
                              folder=monitor['tenant_id'])

        if monitor['type'] == 'HTTP' or monitor['type'] == 'HTTPS':
            if 'url_path' in monitor:
                send_text = "GET " + monitor['url_path'] + \
                                                " HTTP/1.0\\r\\n\\r\\n"
            else:
                send_text = "GET / HTTP/1.0\\r\\n\\r\\n"

            if 'expected_codes' in monitor:
                try:
                    if monitor['expected_codes'].find(",") > 0:
                        status_codes = \
                            monitor['expected_codes'].split(',')
                        recv_text = "HTTP/1\.(0|1) ("
                        for status in status_codes:
                            int(status)
                            recv_text += status + "|"
                        recv_text = recv_text[:-1]
                        recv_text += ")"
                    elif monitor['expected_codes'].find("-") > 0:
                        status_range = \
                            monitor['expected_codes'].split('-')
                        start_range = status_range[0]
                        int(start_range)
                        stop_range = status_range[1]
                        int(stop_range)
                        recv_text = \
                            "HTTP/1\.(0|1) [" + \
                            start_range + "-" + \
                            stop_range + "]"
                    else:
                        int(monitor['expected_codes'])
                        recv_text = "HTTP/1\.(0|1) " + \
                                    monitor['expected_codes']
                except:
                    LOG.error(_(
                        "invalid monitor expected_codes %s,"
                        " setting to 200"
                        % monitor['expected_codes']))
                    recv_text = "HTTP/1\.(0|1) 200"
            else:
                recv_text = "HTTP/1\.(0|1) 200"

            LOG.debug('setting monitor send: %s, receive: %s'
                      % (send_text, recv_text))

            bigip.monitor.set_send_string(name=monitor['id'],
                                          mon_type=monitor['type'],
                                          send_text=send_text,
                                          folder=monitor['tenant_id'])
            bigip.monitor.set_recv_string(name=monitor['id'],
                                          mon_type=monitor['type'],
                                          recv_text=recv_text,
                                          folder=monitor['tenant_id'])

    #
    # Provision Members - Create/Update
    #
    def _assure_members(self, service, bigip, ctxs):
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            ctx = ctxs[bigip.device_name]
            self._assure_device_members(service, bigip, ctx, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_members(self, service, bigip, ctx, on_last_bigip):
        start_time = time()
        # Current members on the BigIP
        pool = service['pool']
        existing_members = bigip.pool.get_members(
                                name=pool['id'],
                                folder=pool['tenant_id'])
        LOG.debug("        _assure_members get members took %.5f secs" %
                  (time() - start_time))
        #LOG.debug(_("Pool: %s before assurance has membership: %s"
        #            % (pool['id'], existing_members)))

        # Flag if we need to change the pool's LB method to
        # include weighting by the ratio attribute
        using_ratio = False
        # Members according to Neutron
        for member in service['members']:
            member_start_time = time()

            #LOG.debug(_("Pool %s assuring member %s:%d - status %s"
            #            % (pool['id'],
            #               member['address'],
            #               member['protocol_port'],
            #               member['status'])
            #            ))

            ip_address = member['address']

            network = member['network']
            subnet = member['subnet']
            if not network or self._is_common_network(network):
                net_folder = 'Common'
            else:
                net_folder = pool['tenant_id']

            if self.conf.f5_global_routed_mode:
                ip_address = ip_address + '%0'
            else:
                if not network or self._is_common_network(network):
                    ip_address = ip_address + '%0'

            found_existing_member = None

            for existing_member in existing_members:
                if ip_address.startswith(existing_member['addr']) and \
                   (member['protocol_port'] == existing_member['port']):
                    found_existing_member = existing_member
                    break

            # Delete those pending delete
            if member['status'] == plugin_const.PENDING_DELETE:
                if not network:
                    # Seems the pool member network could not
                    # be populated.  Try deleting both on a
                    # shared network and a tenant specific
                    bigip.pool.remove_member(name=pool['id'],
                                  ip_address=ip_address,
                                  port=int(member['protocol_port']),
                                  folder=pool['tenant_id'])
                    if not self.conf.f5_global_routed_mode:
                        bigip.pool.remove_member(name=pool['id'],
                                  ip_address=ip_address,
                                  port=int(member['protocol_port']),
                                  folder=pool['tenant_id'])
                else:
                    bigip.pool.remove_member(name=pool['id'],
                                      ip_address=ip_address,
                                      port=int(member['protocol_port']),
                                      folder=pool['tenant_id'])
                if network and 'provider:network_type' in network:
                    if network['provider:network_type'] == 'vxlan':
                        tunnel_name = self._get_tunnel_name(network)
                        if member['port']:
                            # In autosync mode, assure_device_members
                            # is only called for one big-ip, because it is
                            # assumed everything will sync to the other
                            # big-ips.
                            # However, we add fdb entries for tunnels here
                            # and those do not sync. So, we have to loop
                            # through the big-ips for fdb entries and add
                            # them to each big-ip.
                            if self.conf.f5_sync_mode == 'autosync':
                                bigips = bigip.group_bigips
                            else:
                                bigips = [bigip]
                            for fdb_bigip in bigips:
                                fdb_bigip.vxlan.delete_fdb_entry(
                                    tunnel_name=tunnel_name,
                                    mac_address=member['port']['mac_address'],
                                    arp_ip_address=ip_address,
                                    folder=net_folder)
                        else:
                            LOG.error(_('Member on SDN has no port. Manual '
                                        'removal on the BIG-IP will be '
                                        'required. Was the vm instance '
                                        'deleted before the pool member '
                                        'was deleted?'))
                    if network['provider:network_type'] == 'gre':
                        tunnel_name = self._get_tunnel_name(network)
                        if member['port']:
                            # See comment above about this loop.
                            if self.conf.f5_sync_mode == 'autosync':
                                bigips = bigip.group_bigips
                            else:
                                bigips = [bigip]
                            for fdb_bigip in bigips:
                                fdb_bigip.l2gre.delete_fdb_entry(
                                    tunnel_name=tunnel_name,
                                    mac_address=member['port']['mac_address'],
                                    arp_ip_address=ip_address,
                                    folder=net_folder)
                        else:
                            LOG.error(_('Member on SDN has no port. Manual '
                                        'removal on the BIG-IP will be '
                                        'required. Was the vm instance '
                                        'deleted before the pool member '
                                        'was deleted?'))
                # avoids race condition:
                # deletion of pool member objects must sync before we
                # remove the selfip from the peer bigips.
                self._sync_if_clustered(bigip)
                try:
                    if on_last_bigip:
                        self.plugin_rpc.member_destroyed(member['id'])
                except Exception as exc:
                    LOG.error(_("Plugin delete member %s error: %s"
                                % (member['id'], exc.message)
                                ))
                if subnet and \
                   subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.check_for_delete_subnets[subnet['id']] = \
                                                self.SubnetInfo(
                                                    network,
                                                    subnet)
            else:
                just_added = False
                if not found_existing_member:
                    start_time = time()
                    result = bigip.pool.add_member(
                                      name=pool['id'],
                                      ip_address=ip_address,
                                      port=int(member['protocol_port']),
                                      folder=pool['tenant_id'],
                                      no_checks=True)
                    just_added = True
                    LOG.debug("           bigip.pool.add_member %s took %.5f" %
                              (ip_address, time() - start_time))
                    if result:
                        #LOG.debug(_("Pool: %s added member: %s:%d"
                        #% (pool['id'],
                        #   member['address'],
                        #   member['protocol_port'])))
                        if on_last_bigip:
                            rpc = self.plugin_rpc
                            start_time = time()
                            rpc.update_member_status(
                                member['id'],
                                status=plugin_const.ACTIVE,
                                status_description='member created')
                            LOG.debug("            update_member_status"
                                      " took %.5f secs" %
                                      (time() - start_time))
                if just_added or \
                        member['status'] == plugin_const.PENDING_UPDATE:
                    # Is it enabled or disabled?
                    # no_checks because we add the member above if not found
                    start_time = time()
                    if member['admin_state_up']:
                        bigip.pool.enable_member(name=pool['id'],
                                    ip_address=ip_address,
                                    port=int(member['protocol_port']),
                                    folder=pool['tenant_id'],
                                    no_checks=True)
                    else:
                        bigip.pool.disable_member(name=pool['id'],
                                    ip_address=ip_address,
                                    port=int(member['protocol_port']),
                                    folder=pool['tenant_id'],
                                    no_checks=True)
                    LOG.debug("            member enable/disable"
                              " took %.5f secs" %
                              (time() - start_time))
                    # Do we have weights for ratios?
                    if member['weight'] > 1:
                        start_time = time()
                        if not just_added:
                            bigip.pool.set_member_ratio(
                                    name=pool['id'],
                                    ip_address=ip_address,
                                    port=int(member['protocol_port']),
                                    ratio=int(member['weight']),
                                    folder=pool['tenant_id'],
                                    no_checks=True)
                        if time() - start_time > .0001:
                            LOG.debug("            member set ratio"
                                      " took %.5f secs" %
                                      (time() - start_time))
                        using_ratio = True

                    if network and network['provider:network_type'] == 'vxlan':
                        tunnel_name = self._get_tunnel_name(network)
                        if 'vxlan_vteps' in member:
                            for vtep in member['vxlan_vteps']:
                                # In autosync mode, assure_device_members
                                # is only called for one big-ip, because it is
                                # assumed everything will sync to the other
                                # big-ips.
                                # However, we add fdb entries for tunnels here
                                # and those do not sync. So, we have to loop
                                # through the big-ips for fdb entries and add
                                # them to each big-ip.
                                if self.conf.f5_sync_mode == 'autosync':
                                    bigips = bigip.group_bigips
                                else:
                                    bigips = [bigip]
                                for fdb_bigip in bigips:
                                    fdb_bigip.vxlan.add_fdb_entry(
                                     tunnel_name=tunnel_name,
                                     mac_address=member['port']['mac_address'],
                                     vtep_ip_address=vtep,
                                     arp_ip_address=ip_address,
                                     folder=net_folder)
                    if network and network['provider:network_type'] == 'gre':
                        tunnel_name = self._get_tunnel_name(network)
                        if 'gre_vteps' in member:
                            for vtep in member['gre_vteps']:
                                # See comment above about this loop.
                                if self.conf.f5_sync_mode == 'autosync':
                                    bigips = bigip.group_bigips
                                else:
                                    bigips = [bigip]
                                for fdb_bigip in bigips:
                                    fdb_bigip.l2gre.add_fdb_entry(
                                     tunnel_name=tunnel_name,
                                     mac_address=member['port']['mac_address'],
                                     vtep_ip_address=vtep,
                                     arp_ip_address=ip_address,
                                     folder=net_folder)

                    if on_last_bigip:
                        if member['status'] == plugin_const.PENDING_UPDATE:
                            start_time = time()
                            self.plugin_rpc.update_member_status(
                                    member['id'],
                                    status=plugin_const.ACTIVE,
                                    status_description='member updated')
                            LOG.debug("            update_member_status"
                                      " took %.5f secs" %
                                      (time() - start_time))
                if subnet and \
                   subnet['id'] in ctx.check_for_delete_subnets:
                    del ctx.check_for_delete_subnets[subnet['id']]
                if subnet and \
                   subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.do_not_delete_subnets.append(subnet['id'])

            # Remove member from the list of members big-ip needs to remove
            if found_existing_member:
                existing_members.remove(found_existing_member)

            #LOG.debug(_("Pool: %s assured member: %s:%d"
            #        % (pool['id'],
            #           member['address'],
            #           member['protocol_port'])))
            if time() - member_start_time > .001:
                LOG.debug("        assuring member %s took %.5f secs" %
                          (member['address'], time() - member_start_time))

        LOG.debug(_("Pool: %s removing members %s"
                    % (pool['id'], existing_members)))
        # remove any members which are no longer in the service
        for need_to_delete in existing_members:
            bigip.pool.remove_member(
                                 name=pool['id'],
                                 ip_address=need_to_delete['addr'],
                                 port=int(need_to_delete['port']),
                                 folder=pool['tenant_id'])
        # if members are using weights, change the LB to RATIO
        start_time = time()
        if using_ratio:
            #LOG.debug(_("Pool: %s changing to ratio based lb"
            #        % pool['id']))
            if pool['lb_method'] == lb_const.LB_METHOD_LEAST_CONNECTIONS:
                bigip.pool.set_lb_method(
                                name=pool['id'],
                                lb_method='RATIO_LEAST_CONNECTIONS',
                                folder=pool['tenant_id'])
            else:
                bigip.pool.set_lb_method(
                                name=pool['id'],
                                lb_method='RATIO',
                                folder=pool['tenant_id'])
        else:
            # We must update the pool lb_method for the case where
            # the pool object was not updated, but the member
            # used to have a weight (setting ration) and now does
            # not.
            bigip.pool.set_lb_method(name=pool['id'],
                                     lb_method=pool['lb_method'],
                                     folder=pool['tenant_id'])
            # This is probably not required.
            #if on_last_bigip:
            #    self.plugin_rpc.update_pool_status(
            #                pool['id'],
            #                status=plugin_const.ACTIVE,
            #                status_description='pool now using ratio lb')
        if time() - start_time > .001:
            LOG.debug("        _assure_members setting pool lb method" +
                      " took %.5f secs" % (time() - start_time))

    def _assure_vip(self, service, bigip, ctxs):
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            ctx = ctxs[bigip.device_name]
            self._assure_device_vip(service, bigip, ctx, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_vip(self, service, bigip, ctx, on_last_bigip):
        vip = service['vip']
        pool = service['pool']
        bigip_vs = bigip.virtual_server
        if 'id' in vip:
            ip_address = vip['address']
            snat_pool_name = None
            network = vip['network']
            subnet = vip['subnet']

            preserve_network_name = False
            if self.conf.f5_global_routed_mode:
                network_name = None
                ip_address = ip_address + '%0'
            else:
                #
                # Provision Virtual Service - Create/Update
                #
                if network['id'] in self.conf.common_network_ids:
                    network_name = self.conf.common_network_ids[network['id']]
                    preserve_network_name = True
                elif network['provider:network_type'] == 'vlan':
                    network_name = self._get_vlan_name(network,
                                                       bigip.icontrol.hostname)
                elif network['provider:network_type'] == 'flat':
                    network_name = self._get_vlan_name(network,
                                                       bigip.icontrol.hostname)
                elif network['provider:network_type'] == 'vxlan':
                    network_name = self._get_tunnel_name(network)
                elif network['provider:network_type'] == 'gre':
                    network_name = self._get_tunnel_name(network)
                else:
                    error_message = 'Unsupported network type %s.' \
                                % network['provider:network_type'] + \
                                ' Cannot allocate VIP.'
                    LOG.error(_(error_message))
                    raise f5ex.InvalidNetworkType(error_message)
                if self._is_common_network(network):
                    network_name = '/Common/' + network_name
                    ip_address = ip_address + '%0'

                if self.conf.f5_snat_mode and \
                   self.conf.f5_snat_addresses_per_subnet > 0:
                    snat_pool_name = bigip_interfaces.decorate_name(
                                    pool['tenant_id'],
                                    pool['tenant_id'])

            if vip['status'] == plugin_const.PENDING_DELETE:
                LOG.debug(_('Vip: deleting VIP %s' % vip['id']))
                bigip_vs.remove_and_delete_persist_profile(
                                        name=vip['id'],
                                        folder=vip['tenant_id'])
                bigip_vs.delete(name=vip['id'], folder=vip['tenant_id'])

                bigip.rule.delete(name=RPS_THROTTLE_RULE_PREFIX +
                                  vip['id'],
                                  folder=vip['tenant_id'])

                bigip_vs.delete_uie_persist_profile(
                                        name=APP_COOKIE_RULE_PREFIX +
                                              vip['id'],
                                        folder=vip['tenant_id'])

                bigip.rule.delete(name=APP_COOKIE_RULE_PREFIX +
                                  vip['id'],
                                  folder=vip['tenant_id'])

                if network and \
                   'provider:network_type' in vip['network']:
                    if network['provider:network_type'] == 'vxlan':
                        if 'vxlan_vteps' in vip:
                            tunnel_name = self._get_tunnel_name(network)
                            for vtep in vip['vxlan_vteps']:
                                # In autosync mode, assure_device_vip
                                # is only called for one big-ip, because it is
                                # assumed everything will sync to the other
                                # big-ips.
                                # However, we add fdb entries for tunnels here
                                # and those do not sync. So, we have to loop
                                # through the big-ips for fdb entries and add
                                # them to each big-ip.
                                if self.conf.f5_sync_mode == 'autosync':
                                    bigips = bigip.group_bigips
                                else:
                                    bigips = [bigip]
                                for fdb_bigip in bigips:
                                    fdb_bigip.vxlan.delete_fdb_entry(
                                        tunnel_name=tunnel_name,
                                        mac_address=self._get_tunnel_fake_mac(
                                                                network, vtep),
                                        arp_ip_address=None,
                                        folder=vip['tenant_id'])
                    if network['provider:network_type'] == 'gre':
                        if 'gre_vteps' in vip:
                            tunnel_name = self._get_tunnel_name(network)
                            for vtep in vip['gre_vteps']:
                                # See comment above about this loop.
                                if self.conf.f5_sync_mode == 'autosync':
                                    bigips = bigip.group_bigips
                                else:
                                    bigips = [bigip]
                                for fdb_bigip in bigips:
                                    fdb_bigip.l2gre.delete_fdb_entry(
                                        tunnel_name=tunnel_name,
                                        mac_address=self._get_tunnel_fake_mac(
                                                                network, vtep),
                                        arp_ip_address=None,
                                        folder=vip['tenant_id'])
                # avoids race condition:
                # deletion of vip address must sync before we
                # remove the selfip from the peer bigips.
                self._sync_if_clustered(bigip)

                if subnet and \
                   subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.check_for_delete_subnets[subnet['id']] = \
                                                self.SubnetInfo(network,
                                                                subnet)
                try:
                    if on_last_bigip:
                        if vip['id'] in self.__vips_to_traffic_group:
                            vip_tg = self.__vips_to_traffic_group[vip['id']]
                            self.__vips_on_traffic_groups[vip_tg] -= 1
                            del self.__vips_to_traffic_group[vip['id']]
                        self.plugin_rpc.vip_destroyed(vip['id'])
                except Exception as exc:
                    LOG.error(_("Plugin delete vip %s error: %s"
                                % (vip['id'], exc.message)
                                ))
            else:
                vip_tg = self._service_to_traffic_group(service)

                # This is where you could decide to use a fastl4
                # or a standard virtual server.  The problem
                # is making sure that if someone updates the
                # vip protocol or a session persistence that
                # required you change virtual service types
                # would have to make sure a virtual of the
                # wrong type does not already exist or else
                # delete it first. That would cause a service
                # disruption. It would be better if the
                # specification did not allow you to update
                # L7 attributes if you already created a
                # L4 service.  You should have to delete the
                # vip and then create a new one.  That way
                # the end user expects the service outage.

                #virtual_type = 'fastl4'
                #if 'protocol' in vip:
                #    if vip['protocol'] == 'HTTP' or \
                #       vip['protocol'] == 'HTTPS':
                #        virtual_type = 'standard'
                #if 'session_persistence' in vip:
                #    if vip['session_persistence'] == \
                #       'APP_COOKIE':
                #        virtual_type = 'standard'

                # Hard code to standard until we decide if we
                # want to handle the check/delete before create
                # and document the service outage associated
                # with deleting a virtual service. We'll leave
                # the steering logic for create in place.
                # Be aware the check/delete before create
                # is not in the logic below because it means
                # another set of interactions with the device
                # we don't need unless we decided to handle
                # shifting from L4 to L7 or from L7 to L4

                virtual_type = 'standard'

                just_added_vip = False
                if virtual_type == 'standard':
                    vs_name = vip['id']
                    folder = vip['tenant_id']

                    if bigip_vs.create(name=vs_name,
                                    ip_address=ip_address,
                                    mask='255.255.255.255',
                                    port=int(vip['protocol_port']),
                                    protocol=vip['protocol'],
                                    vlan_name=network_name,
                                    traffic_group=vip_tg,
                                    use_snat=self.conf.f5_snat_mode,
                                    snat_pool=snat_pool_name,
                                    folder=folder,
                                    preserve_vlan_name=preserve_network_name):
                        # update driver traffic group mapping
                        vip_tg = bigip_vs.get_traffic_group(
                                        name=vip['id'],
                                        folder=pool['tenant_id'])
                        self.__vips_to_traffic_group[vip['id']] = vip_tg
                        self.__vips_on_traffic_groups[vip_tg] += 1
                        if on_last_bigip:
                            self.plugin_rpc.update_vip_status(
                                            vip['id'],
                                            status=plugin_const.ACTIVE,
                                            status_description='vip created')
                        just_added_vip = True
                else:
                    vs_name = vip['id']
                    folder = vip['tenant_id']

                    if bigip_vs.create_fastl4(
                                    name=vs_name,
                                    ip_address=ip_address,
                                    mask='255.255.255.255',
                                    port=int(vip['protocol_port']),
                                    protocol=vip['protocol'],
                                    vlan_name=network_name,
                                    traffic_group=vip_tg,
                                    use_snat=self.conf.f5_snat_mode,
                                    snat_pool=snat_pool_name,
                                    folder=folder,
                                    preserve_vlan_name=preserve_network_name):
                        # created update driver traffic group mapping
                        vip_tg = bigip_vs.get_traffic_group(
                                        name=vip['id'],
                                        folder=pool['tenant_id'])
                        self.__vips_to_traffic_group[vip['ip']] = vip_tg
                        self.__vips_on_traffic_groups[vip_tg] += 1
                        if on_last_bigip:
                            self.plugin_rpc.update_vip_status(
                                            vip['id'],
                                            status=plugin_const.ACTIVE,
                                            status_description='vip created')
                        just_added_vip = True

                if vip['status'] == plugin_const.PENDING_CREATE or \
                   vip['status'] == plugin_const.PENDING_UPDATE or \
                   just_added_vip:

                    desc = vip['name'] + ':' + vip['description']
                    bigip_vs.set_description(name=vip['id'],
                                             description=desc,
                                             folder=pool['tenant_id'])

                    bigip_vs.set_pool(name=vip['id'],
                                      pool_name=pool['id'],
                                      folder=pool['tenant_id'])
                    if vip['admin_state_up']:
                        bigip_vs.enable_virtual_server(
                                    name=vip['id'],
                                    folder=pool['tenant_id'])
                    else:
                        bigip_vs.disable_virtual_server(
                                    name=vip['id'],
                                    folder=pool['tenant_id'])

                    if 'session_persistence' in vip and \
                        vip['session_persistence']:
                        # branch on persistence type
                        persistence_type = \
                               vip['session_persistence']['type']

                        if persistence_type == 'SOURCE_IP':
                            # add source_addr persistence profile
                            LOG.debug('adding source_addr primary persistence')
                            bigip_vs.set_persist_profile(
                                name=vip['id'],
                                profile_name='/Common/source_addr',
                                folder=vip['tenant_id'])
                        elif persistence_type == 'HTTP_COOKIE':
                            # HTTP cookie persistence requires an HTTP profile
                            LOG.debug('adding http profile and' +
                                      ' primary cookie persistence')
                            bigip_vs.add_profile(
                                name=vip['id'],
                                profile_name='/Common/http',
                                folder=vip['tenant_id'])
                            # add standard cookie persistence profile
                            bigip_vs.set_persist_profile(
                                name=vip['id'],
                                profile_name='/Common/cookie',
                                folder=vip['tenant_id'])
                            if pool['lb_method'] == 'SOURCE_IP':
                                bigip_vs.set_fallback_persist_profile(
                                    name=vip['id'],
                                    profile_name='/Common/source_addr',
                                    folder=vip['tenant_id'])
                        elif persistence_type == 'APP_COOKIE':
                            # application cookie persistence requires
                            # an HTTP profile
                            LOG.debug('adding http profile'
                                      ' and primary universal persistence')
                            bigip_vs.add_profile(
                                name=vip['id'],
                                profile_name='/Common/http',
                                folder=vip['tenant_id'])
                            # make sure they gave us a cookie_name
                            if 'cookie_name' in vip['session_persistence']:
                                cookie_name = \
                                   vip['session_persistence']['cookie_name']
                                # create and add irule to capture cookie
                                # from the service response.
                                rule_definition = \
                          self._create_app_cookie_persist_rule(cookie_name)
                                # try to create the irule
                                if bigip.rule.create(
                                        name=APP_COOKIE_RULE_PREFIX +
                                             vip['id'],
                                        rule_definition=rule_definition,
                                        folder=vip['tenant_id']):
                                    # create universal persistence profile
                                    bigip_vs.create_uie_profile(
                                        name=APP_COOKIE_RULE_PREFIX +
                                              vip['id'],
                                        rule_name=APP_COOKIE_RULE_PREFIX +
                                                  vip['id'],
                                        folder=vip['tenant_id'])
                                # set persistence profile
                                bigip_vs.set_persist_profile(
                                        name=vip['id'],
                                        profile_name=APP_COOKIE_RULE_PREFIX +
                                                 vip['id'],
                                        folder=vip['tenant_id'])
                                if pool['lb_method'] == 'SOURCE_IP':
                                    bigip_vs.set_fallback_persist_profile(
                                        name=vip['id'],
                                        profile_name='/Common/source_addr',
                                        folder=vip['tenant_id'])
                            else:
                                # if they did not supply a cookie_name
                                # just default to regualar cookie peristence
                                bigip_vs.set_persist_profile(
                                       name=vip['id'],
                                       profile_name='/Common/cookie',
                                       folder=vip['tenant_id'])
                                if pool['lb_method'] == 'SOURCE_IP':
                                    bigip_vs.set_fallback_persist_profile(
                                        name=vip['id'],
                                        profile_name='/Common/source_addr',
                                        folder=vip['tenant_id'])
                    else:
                        bigip_vs.remove_all_persist_profiles(
                                        name=vip['id'],
                                        folder=vip['tenant_id'])

                    # rule_name = 'http_throttle_' + vip['id']

                    if vip['connection_limit'] > 0 and \
                       'protocol' in vip:
                        # spec says you need to do this for HTTP
                        # and HTTPS, but unless you can decrypt
                        # you can't measure HTTP rps for HTTPs
                        if vip['protocol'] == 'HTTP':
                            LOG.debug('adding http profile'
                                      ' and RPS throttle rule')
                            # add an http profile
                            bigip_vs.add_profile(
                                name=vip['id'],
                                profile_name='/Common/http',
                                folder=vip['tenant_id'])
                            # create the rps irule
                            rule_definition = \
                              self._create_http_rps_throttle_rule(
                                            vip['connection_limit'])
                            # try to create the irule
                            bigip.rule.create(
                                    name=RPS_THROTTLE_RULE_PREFIX +
                                     vip['id'],
                                    rule_definition=rule_definition,
                                    folder=vip['tenant_id'])
                            # for the rule text to update becuase
                            # connection limit may have changed
                            bigip.rule.update(
                                    name=RPS_THROTTLE_RULE_PREFIX +
                                     vip['id'],
                                    rule_definition=rule_definition,
                                    folder=vip['tenant_id']
                                    )
                            # add the throttle to the vip
                            bigip_vs.add_rule(
                                        name=vip['id'],
                                        rule_name=RPS_THROTTLE_RULE_PREFIX +
                                              vip['id'],
                                        priority=500,
                                        folder=vip['tenant_id'])
                        else:
                            LOG.debug('setting connection limit')
                            # if not HTTP.. use connection limits
                            bigip_vs.set_connection_limit(
                                name=vip['id'],
                                connection_limit=int(
                                        vip['connection_limit']),
                                folder=pool['tenant_id'])
                    else:
                        # clear throttle rule
                        LOG.debug('removing RPS throttle rule if present')
                        bigip_vs.remove_rule(
                                        name=vip['id'],
                                        rule_name=RPS_THROTTLE_RULE_PREFIX +
                                              vip['id'],
                                        priority=500,
                                        folder=vip['tenant_id'])
                        # clear the connection limits
                        LOG.debug('removing connection limits')
                        bigip_vs.set_connection_limit(
                                name=vip['id'],
                                connection_limit=0,
                                folder=pool['tenant_id'])

                    if vip['network'] and \
                       'provider:network_type' in vip['network']:
                        if self._is_common_network(network):
                            net_folder = 'Common'
                        else:
                            net_folder = vip['tenant_id']
                        if network['provider:network_type'] == 'vxlan':
                            if 'vxlan_vteps' in vip:
                                tunnel_name = self._get_tunnel_name(network)
                                for vtep in vip['vxlan_vteps']:
                                    mac_address = self._get_tunnel_fake_mac(
                                                                network, vtep)
                                    # In autosync mode, assure_device_vip
                                    # is only called for one big-ip,
                                    # because it is assumed everything will
                                    # sync to the other big-ips.
                                    # However, we add fdb entries for tunnels
                                    # here and those do not sync. So, we have
                                    # to loop through the big-ips for fdb
                                    # entries and add them to each big-ip.
                                    if self.conf.f5_sync_mode == 'autosync':
                                        bigips = bigip.group_bigips
                                    else:
                                        bigips = [bigip]
                                    for fdb_bigip in bigips:
                                        fdb_bigip.vxlan.add_fdb_entry(
                                                  tunnel_name=tunnel_name,
                                                  mac_address=mac_address,
                                                  vtep_ip_address=vtep,
                                                  arp_ip_address=None,
                                                  folder=net_folder)
                        if network['provider:network_type'] == 'gre':
                            if 'gre_vteps' in vip:
                                tunnel_name = self._get_tunnel_name(network)
                                for vtep in vip['gre_vteps']:
                                    mac_address = self._get_tunnel_fake_mac(
                                                                network, vtep)
                                    # See comment above about this loop.
                                    if self.conf.f5_sync_mode == 'autosync':
                                        bigips = bigip.group_bigips
                                    else:
                                        bigips = [bigip]
                                    for fdb_bigip in bigips:
                                        fdb_bigip.l2gre.add_fdb_entry(
                                              tunnel_name=tunnel_name,
                                              mac_address=mac_address,
                                              vtep_ip_address=vtep,
                                              arp_ip_address=None,
                                              folder=net_folder)

                    if on_last_bigip:
                        self.plugin_rpc.update_vip_status(
                                            vip['id'],
                                            status=plugin_const.ACTIVE,
                                            status_description='vip updated')

                if subnet and \
                   subnet['id'] in ctx.check_for_delete_subnets:
                    del ctx.check_for_delete_subnets[subnet['id']]
                if subnet and \
                   subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.do_not_delete_subnets.append(subnet['id'])

    def _assure_pool_delete(self, service, bigip):
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            self._assure_device_pool_delete(service, bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_pool_delete(self, service, bigip, on_last_bigip):
        # Remove the pool if it is pending delete
        if service['pool']['status'] == plugin_const.PENDING_DELETE:
            LOG.debug(_('Deleting Pool %s' % service['pool']['id']))
            bigip.pool.delete(name=service['pool']['id'],
                              folder=service['pool']['tenant_id'])
            try:
                if on_last_bigip:
                    self.plugin_rpc.pool_destroyed(service['pool']['id'])
            except Exception as exc:
                LOG.error(_("Plugin delete pool %s error: %s"
                            % (service['pool']['id'], exc.message)
                            ))

    def _assure_delete_networks(self, service, bigip, ctxs):
        if self.conf.f5_global_routed_mode:
            return

        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            ctx = ctxs[bigip.device_name]
            self._assure_device_delete_networks(
                                     service, bigip, ctx, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_delete_networks(self,
                                       service,
                                       bigip,
                                       ctx,
                                       on_last_bigip):
        # Clean up any Self IP, SNATs, networks, and folder for
        # services items that we deleted.
        for subnetinfo in ctx.check_for_delete_subnets.values():
            network = subnetinfo.network
            subnet = subnetinfo.subnet
            if subnet:
                delete_subnet_objects = True
                ipsubnet = netaddr.IPNetwork(subnet['cidr'])
                # Are there any virtual addresses on this subnet
                virtual_services = \
                            bigip.virtual_server.get_virtual_service_insertion(
                                        folder=service['pool']['tenant_id'])
                for virt_serv in virtual_services:
                    (vs_name, dest) = virt_serv.items()[0]
                    del vs_name
                    if netaddr.IPAddress(dest['address']) in ipsubnet:
                        delete_subnet_objects = False
                        break
                if delete_subnet_objects:
                    # If there aren't any virtual addresses, are there
                    # node addresses on this subnet
                    nodes = bigip.pool.get_node_addresses(
                                    folder=service['pool']['tenant_id'])
                    for node in nodes:
                        if netaddr.IPAddress(node) in ipsubnet:
                            delete_subnet_objects = False
                            break
                if delete_subnet_objects:
                    # Since no virtual addresses or nodes found
                    # go ahead and try to delete the Self IP
                    # and SNATs
                    if not self.conf.f5_snat_mode:
                        self._delete_gateway_on_subnet(subnetinfo,
                                                       bigip, on_last_bigip)
                    # Since no virtual addresses or nodes found
                    # go ahead and try to delete the Self IP
                    # and SNATs
                    self._delete_selfip_and_snats(service,
                                            self.SubnetInfo(network, subnet),
                                            bigip, on_last_bigip)
                    # avoids race condition:
                    # deletion of ip objects must sync before we
                    # remove the vlan from the peer bigips.
                    self._sync_if_clustered(bigip)
                    try:
                        self._delete_network(network, bigip, on_last_bigip)
                    except:
                        pass
                    # Flag this network so we won't try to go through
                    # this same process if a deleted member is on
                    # this same subnet.
                    if subnet['id'] not in ctx.do_not_delete_subnets:
                        ctx.do_not_delete_subnets.append(subnet['id'])
            else:
                LOG.error(_('Attempted to delete network and subnet when'
                            ' the subnet has no id... skipping.'))

    def _assure_tenant_cleanup(self, service, bigip, ctxs):
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            ctx = ctxs[bigip.device_name]
            self._assure_device_tenant_cleanup(service, bigip, ctx)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_tenant_cleanup(self, service, bigip, ctx):
        # if something was deleted check whether to do domain+folder teardown
        if service['pool']['status'] == plugin_const.PENDING_DELETE or \
                len(ctx.check_for_delete_subnets) > 0:
            existing_monitors = bigip.monitor.get_monitors(
                                    folder=service['pool']['tenant_id'])
            existing_pools = bigip.pool.get_pools(
                                    folder=service['pool']['tenant_id'])
            existing_vips = bigip.virtual_server.get_virtual_service_insertion(
                                    folder=service['pool']['tenant_id'])

            if not existing_monitors and \
               not existing_pools and \
               not existing_vips:
                self._remove_tenant(service, bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _remove_tenant(self, service, bigip):
        try:
            if self.conf.f5_sync_mode == 'replication':
                bigip.route.delete_domain(
                            folder=service['pool']['tenant_id'])
                bigip.system.delete_folder(
                            folder=bigip.decorate_folder(
                                           service['pool']['tenant_id']))
            else:
                # syncing the folder delete seems to cause problems,
                # so try deleting it on each device
                clustered = (len(self.__bigips.values()) > 1)
                if clustered:
                    bigip.device_group = bigip.device.get_device_group()
                # turn off sync on all devices so we can prevent
                # a sync from another device doing it
                for set_bigip in self.__bigips.values():
                    if clustered:
                        set_bigip.cluster.disable_auto_sync(bigip.device_group)
                # all domains must be gone before we attempt to delete
                # the folder or it won't delete due to not being empty
                for set_bigip in self.__bigips.values():
                    set_bigip.route.delete_domain(
                            folder=service['pool']['tenant_id'])
                    set_bigip.system.delete_folder(
                            folder=set_bigip.decorate_folder(
                                    service['pool']['tenant_id']))
                # turn off sync on all devices so we can delete the folder
                # on each device individually
                for set_bigip in self.__bigips.values():
                    if clustered:
                        set_bigip.cluster.enable_auto_sync(bigip.device_group)
                if clustered:
                    # Need to make sure this folder delete syncs before
                    # something else runs and changes the current folder to
                    # the folder being deleted which will cause big problems.
                    self._sync_if_clustered(bigip)
        except:
            LOG.error("Error cleaning up tenant " +
                               service['pool']['tenant_id'])

    def _assure_service_networks(self, service):
        if not service['pool']:
            return
        if self.conf.f5_global_routed_mode:
            return
        start_time = time()
        bigip = self._get_bigip()
        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_first_bigip = (bigip is bigips[0])
            on_last_bigip = (bigip is bigips[-1])
            self._assure_device_service_networks(service,
                        bigip, on_first_bigip, on_last_bigip)
        if time() - start_time > .001:
            LOG.debug("    assure_service_networks took %.5f secs" %
                      (time() - start_time))

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_device_service_networks(self, service,
              bigip, on_first_bigip, on_last_bigip):

        if 'id' in service['vip']:
            if not service['vip']['status'] == plugin_const.PENDING_DELETE:
                network = service['vip']['network']
                subnet = service['vip']['subnet']
                self._assure_network(network,
                    bigip, on_first_bigip, on_last_bigip)
                self._assure_selfip_and_snats(service,
                                        self.SubnetInfo(network, subnet),
                                        bigip, on_first_bigip, on_last_bigip)

        for member in service['members']:
            if not member['status'] == plugin_const.PENDING_DELETE:
                network = member['network']
                subnet = member['subnet']
                start_time = time()
                self._assure_network(network, bigip,
                                on_first_bigip, on_last_bigip)
                if time() - start_time > .001:
                    LOG.debug("        _assure_device_service_networks:"
                              "assure_network took %.5f secs" %
                              (time() - start_time))
                # each member gets a local self IP on each device
                start_time = time()
                self._assure_selfip_and_snats(service,
                                     self.SubnetInfo(network, subnet),
                                     bigip, on_first_bigip, on_last_bigip)
                if time() - start_time > .001:
                    LOG.debug("        _assure_device_service_networks:"
                              "assure_selfip_snat took %.5f secs" %
                              (time() - start_time))
                # if we are not using SNATS, attempt to become
                # the subnet's default gateway.
                if not self.conf.f5_snat_mode:
                    self._assure_gateway_on_subnet(
                            self.SubnetInfo(network,
                                            subnet),
                            bigip, on_first_bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_network(self, network, bigip, on_first_bigip, on_last_bigip):
        if not network:
            LOG.error(_('Attempted to assure a network with no id..skipping.'))
            return
        if network['id'] in self.conf.common_network_ids:
            LOG.info(_('Network is a common global network... skipping.'))
            return
        start_time = time()
        if self.conf.f5_sync_mode == 'replication' and not on_first_bigip:
            # already did this work
            return

        bigips = bigip.group_bigips
        for bigip in bigips:
            if network['id'] in bigip.assured_networks:
                continue
            self._assure_device_network(network, bigip)
            bigip.assured_networks.append(network['id'])
        if time() - start_time > .001:
            LOG.debug("        assure network took %.5f secs" %
                           (time() - start_time))

    def _is_common_network(self, network):
        return network['shared'] or \
            (network['id'] in self.conf.common_network_ids) or \
            ('router:external' in network and \
             network['router:external'] and \
             self.conf.f5_common_external_networks)

    # called for every bigip in every sync mode
    def _assure_device_network(self, network, bigip):
        if self._is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = network['tenant_id']

        # setup all needed L2 network segments
        if network['provider:network_type'] == 'vlan':
            # VLAN names are limited to 64 characters including
            # the folder name, so we name them foolish things.

            interface = self.interface_mapping['default']
            tagged = self.tagging_mapping['default']
            vlanid = 0

            # Do we have host specific mappings?
            net_key = network['provider:physical_network']
            if net_key + ':' + bigip.icontrol.hostname in \
                                        self.interface_mapping:
                interface = self.interface_mapping[
                       net_key + ':' + bigip.icontrol.hostname]
                tagged = self.tagging_mapping[
                       net_key + ':' + bigip.icontrol.hostname]
            # Do we have a mapping for this network
            elif net_key in self.interface_mapping:
                interface = self.interface_mapping[net_key]
                tagged = self.tagging_mapping[net_key]

            if tagged:
                vlanid = network['provider:segmentation_id']
            else:
                vlanid = 0

            vlan_name = self._get_vlan_name(network,
                                            bigip.icontrol.hostname)

            bigip.vlan.create(name=vlan_name,
                              vlanid=vlanid,
                              interface=interface,
                              folder=network_folder,
                              description=network['id'])

        elif network['provider:network_type'] == 'flat':
            interface = self.interface_mapping['default']
            vlanid = 0

            # Do we have host specific mappings?
            net_key = network['provider:physical_network']
            if net_key + ':' + bigip.icontrol.hostname in \
                                        self.interface_mapping:
                interface = self.interface_mapping[
                       net_key + ':' + bigip.icontrol.hostname]
            # Do we have a mapping for this network
            elif net_key in self.interface_mapping:
                interface = self.interface_mapping[net_key]

            vlan_name = self._get_vlan_name(network,
                                            bigip.icontrol.hostname)

            bigip.vlan.create(name=vlan_name,
                              vlanid=0,
                              interface=interface,
                              folder=network_folder,
                              description=network['id'])

        elif network['provider:network_type'] == 'vxlan':
            if not bigip.local_ip:
                error_message = 'Cannot create tunnel %s on %s' \
                                  % (network['id'], bigip.icontrol.hostname)
                error_message += ' no VTEP SelfIP defined.'
                LOG.error('VXLAN:' + error_message)
                raise f5ex.MissingVTEPAddress('VXLAN:' + error_message)

            tunnel_name = self._get_tunnel_name(network)
            # create the main tunnel entry for the fdb records
            bigip.vxlan.create_multipoint_tunnel(name=tunnel_name,
                                 profile_name='vxlan_ovs',
                                 self_ip_address=bigip.local_ip,
                                 vxlanid=network['provider:segmentation_id'],
                                 description=network['id'],
                                 folder=network_folder)
            # create the listerner filters for all VTEP addresses
            #local_ips = self.agent_configurations['tunneling_ips']
            #for i in range(len(local_ips)):
            #    list_name = 'ha_' + \
            #                str(network['provider:segmentation_id']) + \
            #                '_' + str(i)
            #    bigip.vxlan.create_multipoint_tunnel(name=list_name,
            #                     profile_name='vxlan_ovs',
            #                     self_ip_address=local_ips[i],
            #                     vxlanid=network['provider:segmentation_id'],
            #                     folder=network_folder)
            # notify all the compute nodes we are VTEPs
            # for this network now.
            if self.conf.l2_population:
                fdb_entries = {network['id']:
                               {
                                'ports': {
                                  bigip.local_ip:
                                    [q_const.FLOODING_ENTRY]
                                },
                                'network_type':
                                   network['provider:network_type'],
                                'segment_id':
                                   network['provider:segmentation_id']
                               }
                             }
                self.l2pop_rpc.add_fdb_entries(self.context, fdb_entries)

        elif network['provider:network_type'] == 'gre':
            if not bigip.local_ip:
                error_message = 'Cannot create tunnel %s on %s' \
                                  % (network['id'], bigip.icontrol.hostname)
                error_message += ' no VTEP SelfIP defined.'
                LOG.error('L2GRE:' + error_message)
                raise f5ex.MissingVTEPAddress('L2GRE:' + error_message)

            tunnel_name = self._get_tunnel_name(network)

            bigip.l2gre.create_multipoint_tunnel(name=tunnel_name,
                                 profile_name='gre_ovs',
                                 self_ip_address=bigip.local_ip,
                                 greid=network['provider:segmentation_id'],
                                 description=network['id'],
                                 folder=network_folder)
            # create the listerner filters for all VTEP addresses
            #local_ips = self.agent_configurations['tunneling_ips']
            #for i in range(len(local_ips)):
                #list_name = 'ha_' + \
                #            str(network['provider:segmentation_id']) + \
                #            '_' + str(i)
                #bigip.l2gre.create_multipoint_tunnel(name=list_name,
                #                 profile_name='gre_ovs',
                #                 self_ip_address=local_ips[i],
                #                 greid=network['provider:segmentation_id'],
                #                 folder=network_folder)
            # notify all the compute nodes we are VTEPs
            # for this network now.
            if self.conf.l2_population:
                fdb_entries = {network['id']:
                               {
                                'ports': {
                                  bigip.local_ip:
                                    [q_const.FLOODING_ENTRY]
                                },
                                'network_type':
                                   network['provider:network_type'],
                                'segment_id':
                                   network['provider:segmentation_id']
                               }
                             }
                self.l2pop_rpc.add_fdb_entries(self.context, fdb_entries)
        else:
            error_message = 'Unsupported network type %s.' \
                            % network['provider:network_type'] + \
                            ' Cannot setup network.'
            LOG.error(_(error_message))
            raise f5ex.InvalidNetworkType(error_message)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_selfip_and_snats(self, service, subnetinfo,
                                 bigip, on_first_bigip, on_last_bigip):

        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to create selfip and snats'
            ' for network with no id... skipping.'))
            return
        subnet = subnetinfo.subnet
        pool = service['pool']
        # Sync special case:
        # In replication mode, even though assure_selfip_and_snats
        # is called for each bigip, we allocate a floating ip later that needs
        # to be the same for every bigip. We could allocate the ips and pass
        # them back to so they can be used multiple times, but its easier to
        # just do all the work here. This function is called for every big-ip
        # but we only want to do this work once, so we'll only do this on the
        # first bigip.
        if self.conf.f5_sync_mode == 'replication' and not on_first_bigip:
            # we already did this work
            return

        preserve_network_name = False
        if self._is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = pool['tenant_id']

        if network['id'] in self.conf.common_network_ids:
            network_name = self.conf.common_network_ids[network['id']]
            preserve_network_name = True
        elif network['provider:network_type'] == 'vlan':
            network_name = self._get_vlan_name(network,
                                               bigip.icontrol.hostname)
        elif network['provider:network_type'] == 'flat':
            network_name = self._get_vlan_name(network,
                                               bigip.icontrol.hostname)
        elif network['provider:network_type'] == 'vxlan':
            network_name = self._get_tunnel_name(network)
        elif network['provider:network_type'] == 'gre':
            network_name = self._get_tunnel_name(network)
        else:
            error_message = 'Unsupported network type %s.' \
                            % network['provider:network_type'] + \
                            ' Cannot setup selfip or snat.'
            LOG.error(_(error_message))
            raise f5ex.InvalidNetworkType(error_message)

        # These selfs are unique to each big-ip
        for set_bigip in bigip.group_bigips:
            if subnet['id'] in set_bigip.assured_snat_subnets:
                continue
            self._create_local_selfip(set_bigip, subnet,
                                      network_folder, network_name,
                                      preserve_network_name)

        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        #
        if self.conf.f5_snat_addresses_per_subnet > 0:
            snat_pool_name = pool['tenant_id']

            if self.conf.f5_ha_type == 'standalone':
                self._assure_snats_standalone(bigip, subnetinfo,
                                             snat_pool_name,
                                             network_folder,
                                             pool['tenant_id'])
            elif self.conf.f5_ha_type == 'pair':
                self._assure_snats_ha(bigip, subnetinfo,
                                     snat_pool_name,
                                     network_folder,
                                     pool['tenant_id'])
            elif self.conf.f5_ha_type == 'scalen':
                self._assure_snats_scalen(bigip, service,
                                     subnetinfo,
                                     snat_pool_name,
                                     network_folder,
                                     pool['tenant_id'])

    # called for every bigip
    def _create_local_selfip(self,
                             bigip,
                             subnet,
                             network_folder,
                             network_name,
                             preserve_network_name):
        local_selfip_name = "local-" + bigip.device_name + "-" + subnet['id']

        ports = self.plugin_rpc.get_port_by_name(
                                    port_name=local_selfip_name)
        #LOG.debug("got ports: %s" % ports)
        if len(ports) > 0:
            ip_address = ports[0]['fixed_ips'][0]['ip_address']
        else:
            new_port = self.plugin_rpc.create_port_on_subnet(
                        subnet_id=subnet['id'],
                        mac_address=None,
                        name=local_selfip_name,
                        fixed_address_count=1)
            ip_address = new_port['fixed_ips'][0]['ip_address']
        netmask = netaddr.IPNetwork(
                           subnet['cidr']).netmask
        bigip.selfip.create(name=local_selfip_name,
                            ip_address=ip_address,
                            netmask=netmask,
                            vlan_name=network_name,
                            floating=False,
                            folder=network_folder,
                            preserve_vlan_name=preserve_network_name)

    def _assure_snats_standalone(self, bigip, subnetinfo,
                                snat_pool_name,
                                snat_folder,
                                snat_pool_folder):
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        # Create SNATs on traffic-group-local-only
        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)
            ports = self.plugin_rpc.get_port_by_name(
                                    port_name=index_snat_name)
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            if self._is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            tglo = '/Common/traffic-group-local-only',
            bigip.snat.create(
                       name=index_snat_name,
                       ip_address=ip_address,
                       traffic_group=tglo,
                       snat_pool_name=None,
                       folder=snat_folder)
            bigip.snat.create_pool(name=snat_pool_name,
                                   member_name=index_snat_name,
                                   folder=snat_pool_folder)

        bigip.assured_snat_subnets.append(subnet['id'])

    def _assure_snats_ha(self, bigip, subnetinfo,
                        snat_pool_name,
                        snat_folder,
                        snat_pool_folder):
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        all_assured = True
        for set_bigip in bigip.group_bigips:
            if subnet['id'] not in set_bigip.assured_snat_subnets:
                all_assured = False
                break
        if all_assured:
            return

        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)
            start_time = time()
            ports = self.plugin_rpc.get_port_by_name(
                                    port_name=index_snat_name)
            LOG.debug("        assure_snat:"
                      "get_port_by_name took %.5f secs" %
                      (time() - start_time))
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            if self._is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            if self.conf.f5_sync_mode == 'replication':
                bigips = bigip.group_bigips
            else:
                bigips = [bigip]
            for set_bigip in bigips:
                if subnet['id'] in set_bigip.assured_snat_subnets:
                    continue
                set_bigip.snat.create(
                           name=index_snat_name,
                           ip_address=ip_address,
                           traffic_group='traffic-group-1',
                           snat_pool_name=None,
                           folder=snat_folder)
                set_bigip.snat.create_pool(name=snat_pool_name,
                                       member_name=index_snat_name,
                                       folder=snat_pool_folder)

        for set_bigip in bigip.group_bigips:
            if subnet['id'] in set_bigip.assured_snat_subnets:
                continue
            set_bigip.assured_snat_subnets.append(subnet['id'])

    def _assure_snats_scalen(self, bigip, service, subnetinfo,
                            snat_pool_name,
                            snat_folder,
                            snat_pool_folder):
        network = subnetinfo.network
        subnet = subnetinfo.subnet

        all_assured = True
        for set_bigip in bigip.group_bigips:
            if subnet['id'] not in set_bigip.assured_snat_subnets:
                all_assured = False
                break
        if all_assured:
            return

        traffic_group = self._service_to_traffic_group(service)
        base_traffic_group = os.path.basename(traffic_group)
        snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)

            ports = self.plugin_rpc.get_port_by_name(
                                port_name=index_snat_name)
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.plugin_rpc.create_port_on_subnet(
                                         subnet_id=subnet['id'],
                                         mac_address=None,
                                         name=index_snat_name,
                                         fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            if self._is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name
            if self.conf.f5_sync_mode == 'replication':
                bigips = bigip.group_bigips
            else:
                # this is a synced object,
                # so only do it once in sync modes
                bigips = [bigip]
            for set_bigip in bigips:
                if subnet['id'] in set_bigip.assured_snat_subnets:
                    continue
                set_bigip.snat.create(
                           name=index_snat_name,
                           ip_address=ip_address,
                           traffic_group=traffic_group,
                           snat_pool_name=None,
                           folder=snat_folder)
                set_bigip.snat.create_pool(name=snat_pool_name,
                               member_name=index_snat_name,
                               folder=snat_pool_folder)

        for set_bigip in bigip.group_bigips:
            if subnet['id'] in set_bigip.assured_snat_subnets:
                continue
            set_bigip.assured_snat_subnets.append(subnet['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_gateway_on_subnet(self, subnetinfo,
                                  bigip, on_first_bigip, on_last_bigip):

        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to create default gateway'
                        ' for network with no id.. skipping.'))
            return
        subnet = subnetinfo.subnet

        # Sync special case:
        # In replication mode, even though _assure_floating_default_gateway is
        # called for each bigip, we allocate a floating ip later that needs to
        # be the same for every bigip. We could allocate the ips and pass them
        # back to so they can be used multiple times, but its easier to just
        # do all the work here. This function is called for every big-ip but we
        # only want to do this work once, so we'll only do this on the
        # first bigip
        if self.conf.f5_sync_mode == 'replication' and not on_first_bigip:
            # we already did this work
            return

        # Create a name for the port and for the IP Forwarding Virtual Server
        # as well as the floating Self IP which will answer ARP for the members
        gw_name = "gw-" + subnet['id']
        floating_selfip_name = "gw-" + subnet['id']
        netmask = netaddr.IPNetwork(subnet['cidr']).netmask
        ports = self.plugin_rpc.get_port_by_name(port_name=gw_name)
        if len(ports) < 1:
            need_port_for_gateway = True

        # There was no port on this agent's host, so get one from Neutron
        if need_port_for_gateway:
            try:
                new_port = \
                  self.plugin_rpc.create_port_on_subnet_with_specific_ip(
                            subnet_id=subnet['id'],
                            mac_address=None,
                            name=gw_name,
                            ip_address=subnet['gateway_ip'])
                LOG.info(_('gateway IP for subnet %s will be port %s'
                            % (subnet['id'], new_port['id'])))
            except Exception as exc:
                ermsg = 'Invalid default gateway for subnet %s:%s - %s.' \
                    % (subnet['id'],
                       subnet['gateway_ip'],
                       exc.message)
                ermsg += " SNAT will not function and load balancing"
                ermsg += " support will likely fail. Enable f5_snat_mode."
                LOG.error(_(ermsg))

        # Setup a floating SelfIP with the subnet's
        # gateway_ip address on this agent's device service group

        preserve_network_name = False
        if network['id'] in self.conf.common_network_ids:
            network_name = self.conf.common_network_ids[network['id']]
            preserve_network_name = True
        if network['provider:network_type'] == 'vlan':
            network_name = self._get_vlan_name(network,
                                               bigip.icontrol.hostname)
        elif network['provider:network_type'] == 'flat':
            network_name = self._get_vlan_name(network,
                                               bigip.icontrol.hostname)
        elif network['provider:network_type'] == 'vxlan':
            network_name = self._get_tunnel_name(network)
        elif network['provider:network_type'] == 'gre':
            network_name = self._get_tunnel_name(network)
        else:
            LOG.error(_('Unsupported network type %s. Cannot setup gateway'
                        % network['provider:network_type']))
            return

        if self._is_common_network(network):
            network_folder = 'Common'
            network_name = '/Common/' + network_name
        else:
            network_folder = subnet['tenant_id']

        # Select a traffic group for the floating SelfIP
        vip_tg = self._get_least_gw_traffic_group()

        if self.conf.f5_sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            # these are synced objects, so only create them once in sync modes
            bigips = [bigip]
        for bigip in bigips:
            if subnet['id'] in bigip.assured_gateway_subnets:
                continue

            bigip.selfip.create(
                            name=floating_selfip_name,
                            ip_address=subnet['gateway_ip'],
                            netmask=netmask,
                            vlan_name=network_name,
                            floating=True,
                            traffic_group=vip_tg,
                            folder=network_folder,
                            preserve_vlan_name=preserve_network_name)

            # Get the actual traffic group if the Self IP already existed
            vip_tg = bigip.self.get_traffic_group(name=floating_selfip_name,
                                    folder=subnet['tenant_id'])

            # Setup a wild card ip forwarding virtual service for this subnet

            bigip.virtual_server.create_ip_forwarder(
                            name=gw_name, ip_address='0.0.0.0',
                            mask='0.0.0.0',
                            vlan_name=network_name,
                            traffic_group=vip_tg,
                            folder=network_folder,
                            preserve_vlan_name=preserve_network_name)

            # Setup the IP forwarding virtual server to use the Self IPs
            # as the forwarding SNAT addresses
            bigip.virtual_server.set_snat_automap(name=gw_name,
                                folder=network_folder)
            bigip.assured_gateway_subnets.append(subnet['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _delete_network(self, network, bigip, on_last_bigip):
        if network['id'] in self.conf.common_network_ids:
            LOG.debug(_('skipping delete of common network %s'
                        % self.conf.common[network['id']]))
            return
        if self._is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = network['tenant_id']

        if self.conf.f5_sync_mode == 'replication':
            bigips = [bigip]
        else:
            bigips = bigip.group_bigips
        for set_bigip in bigips:
            if network['provider:network_type'] == 'vlan':
                vlan_name = self._get_vlan_name(network,
                                                set_bigip.icontrol.hostname)
                set_bigip.vlan.delete(name=vlan_name,
                                      folder=network_folder)

            elif network['provider:network_type'] == 'flat':
                vlan_name = self._get_vlan_name(network,
                                                set_bigip.icontrol.hostname)
                set_bigip.vlan.delete(name=vlan_name,
                                      folder=network_folder)

            elif network['provider:network_type'] == 'vxlan':
                tunnel_name = self._get_tunnel_name(network)

                set_bigip.vxlan.delete_all_fdb_entries(tunnel_name=tunnel_name,
                                                       folder=network_folder)
                set_bigip.vxlan.delete_tunnel(name=tunnel_name,
                                              folder=network_folder)
                # delete the listener filters for all VTEP addresses
                local_ips = self.agent_configurations['tunneling_ips']
                for i in range(len(local_ips)):
                    list_name = 'ha_' + \
                            str(network['provider:segmentation_id']) + \
                            '_' + str(i)
                    set_bigip.vxlan.delete_tunnel(name=list_name,
                                                  folder=network_folder)
                # notify all the compute nodes we no longer have
                # VTEPs for this network now.
                if self.conf.l2_population:
                    fdb_entries = {network['id']:
                               {
                                'ports': {
                                  set_bigip.local_ip:
                                    [q_const.FLOODING_ENTRY]
                                },
                                'network_type':
                                   network['provider:network_type'],
                                'segment_id':
                                   network['provider:segmentation_id']
                               }
                             }
                    self.l2pop_rpc.remove_fdb_entries(self.context,
                                                      fdb_entries)
            elif network['provider:network_type'] == 'gre':

                tunnel_name = self._get_tunnel_name(network)

                # for each known vtep_endpoints to this tunnel
                set_bigip.l2gre.delete_all_fdb_entries(tunnel_name=tunnel_name,
                                                       folder=network_folder)
                set_bigip.l2gre.delete_tunnel(name=tunnel_name,
                                              folder=network_folder)
                # delete the listener filters for all VTEP addresses
                local_ips = self.agent_configurations['tunneling_ips']
                for i in range(len(local_ips)):
                    list_name = 'ha_' + \
                            str(network['provider:segmentation_id']) + \
                            '_' + str(i)
                    set_bigip.l2gre.delete_tunnel(name=list_name,
                                                  folder=network_folder)
                # notify all the compute nodes we no longer
                # VTEPs for this network now.
                if self.conf.l2_population:
                    fdb_entries = {network['id']:
                               {
                                'ports': {
                                  set_bigip.local_ip:
                                    [q_const.FLOODING_ENTRY]
                                },
                                'network_type':
                                   network['provider:network_type'],
                                'segment_id':
                                   network['provider:segmentation_id']
                               }
                             }
                    self.l2pop_rpc.remove_fdb_entries(self.context,
                                                      fdb_entries)
            else:
                LOG.error(_('Unsupported network type %s. Can not delete.'
                      % network['provider:network_type']))

            if network['id'] in set_bigip.assured_networks:
                set_bigip.assured_networks.remove(network['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _delete_selfip_and_snats(self, service, subnetinfo,
                                 bigip, on_last_bigip):
        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to delete selfip and snats'
            ' for network with no id... skipping.'))
            return
        subnet = subnetinfo.subnet
        if self._is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = service['pool']['tenant_id']
        snat_pool_name = service['pool']['tenant_id']
        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        if self.conf.f5_snat_addresses_per_subnet > 0:
            # failover mode dictates SNAT placement on traffic-groups
            if self.conf.f5_ha_type == 'standalone':
                # Delete SNATs on traffic-group-local-only
                snat_name = 'snat-traffic-group-local-only-' + subnet['id']
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    index_snat_name = snat_name + "_" + str(i)
                    if self._is_common_network(network):
                        tmos_snat_name = '/Common/' + index_snat_name
                    else:
                        tmos_snat_name = index_snat_name
                    bigip.snat.remove_from_pool(name=snat_pool_name,
                                         member_name=tmos_snat_name,
                                         folder=service['pool']['tenant_id'])
                    if bigip.snat.delete(name=tmos_snat_name,
                                         folder=network_folder):
                        # Only if it still exists and can be
                        # deleted because it is not in use can
                        # we safely delete the neutron port
                        if on_last_bigip:
                            self.plugin_rpc.delete_port_by_name(
                                            port_name=index_snat_name)
            elif self.conf.f5_ha_type == 'pair':
                # Delete SNATs on traffic-group-1
                snat_name = 'snat-traffic-group-1' + subnet['id']
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    index_snat_name = snat_name + "_" + str(i)
                    if self._is_common_network(network):
                        tmos_snat_name = '/Common/' + index_snat_name
                    else:
                        tmos_snat_name = index_snat_name
                    bigip.snat.remove_from_pool(name=snat_pool_name,
                                        member_name=tmos_snat_name,
                                        folder=service['pool']['tenant_id'])
                    if bigip.snat.delete(name=tmos_snat_name,
                                         folder=network_folder):
                        # Only if it still exists and can be
                        # deleted because it is not in use can
                        # we safely delete the neutron port
                        if on_last_bigip:
                            self.plugin_rpc.delete_port_by_name(
                                            port_name=index_snat_name)
            elif self.conf.f5_ha_type == 'scalen':
                # Delete SNATs on all provider defined traffic groups
                traffic_group = self._service_to_traffic_group(service)
                base_traffic_group = os.path.basename(traffic_group)
                snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    index_snat_name = snat_name + "_" + str(i)
                    if self._is_common_network(network):
                        tmos_snat_name = "/Common/" + index_snat_name
                    else:
                        tmos_snat_name = index_snat_name
                    bigip.snat.remove_from_pool(name=snat_pool_name,
                                    member_name=tmos_snat_name,
                                    folder=service['pool']['tenant_id'])
                    if bigip.snat.delete(name=tmos_snat_name,
                                         folder=network_folder):
                        # Only if it still exists and can be
                        # deleted because it is not in use can
                        # we safely delete the neutron port
                        if on_last_bigip:
                            self.plugin_rpc.delete_port_by_name(
                                            port_name=index_snat_name)

        # delete_selfip_and_snats called for every bigip only
        # in replication mode. otherwise called once
        if self.conf.f5_sync_mode == 'replication':
            bigips = [bigip]
        else:
            bigips = bigip.group_bigips
        for bigip in bigips:
            local_selfip_name = "local-" + bigip.device_name + \
                                "-" + subnet['id']
            if self.conf.f5_populate_static_arp:
                bigip.arp.delete_by_subnet(subnet=subnet['cidr'],
                                           mask=None,
                                           folder=network_folder)
            bigip.selfip.delete(name=local_selfip_name,
                                folder=network_folder)
            self.plugin_rpc.delete_port_by_name(port_name=local_selfip_name)

        for bigip in bigip.group_bigips:
            if subnet['id'] in bigip.assured_snat_subnets:
                bigip.assured_snat_subnets.remove(subnet['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _delete_gateway_on_subnet(self, subnetinfo, bigip, on_last_bigip):
        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to delete default gateway'
            ' for network with no id... skipping.'))
            return
        subnet = subnetinfo.subnet
        if self._is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = subnet['tenant_id']

        floating_selfip_name = "gw-" + subnet['id']
        if self.conf.f5_populate_static_arp:
            bigip.arp.delete_by_subnet(subnet=subnetinfo.subnet['cidr'],
                                       mask=None,
                                       folder=network_folder)
        bigip.selfip.delete(name=floating_selfip_name,
                            folder=network_folder)

        gw_name = "gw-" + subnet['id']
        bigip.virtual_server.delete(name=gw_name,
                                    folder=network_folder)

        if on_last_bigip:
            ports = self.plugin_rpc.get_port_by_name(port_name=gw_name)
            if len(ports) < 1:
                gateway_port_id = None
            else:
                gateway_port_id = ports[0]['id']
            # There was a port on this agent's host, so remove it
            if gateway_port_id:
                try:
                    self.plugin_rpc.delete_port(port_id=gateway_port_id,
                                                mac_address=None)
                except Exception as exc:
                    ermsg = 'Error on delete gateway port' + \
                            ' for subnet %s:%s - %s.' \
                            % (subnet['id'],
                               subnet['gateway_ip'],
                               exc.message)
                    ermsg += " You will need to delete this manually"
                    LOG.error(_(ermsg))
        if subnet['id'] in bigip.assured_gateway_subnets:
            bigip.assured_gateway_subnets.remove(subnet['id'])

    def _service_to_traffic_group(self, service):
        hexhash = hashlib.md5(service['pool']['tenant_id']).hexdigest()
        tg_index = int(hexhash, 16) % len(self.__traffic_groups)
        return self.__traffic_groups[tg_index]

    # deprecated, use _service_to_traffic_group
    def _service_to_traffic_group_least_vips(self, vip_id):
        if vip_id in self.__vips_to_traffic_group:
            return self.__vips_to_traffic_group[vip_id]

        vips_on_tgs = self.__vips_on_traffic_groups

        ret_traffic_group = self.__traffic_groups[0]
        lowest_count = vips_on_tgs[ret_traffic_group]
        for traffic_group in vips_on_tgs:
            if vips_on_tgs[traffic_group] < lowest_count:
                ret_traffic_group = traffic_group
                lowest_count = vips_on_tgs[ret_traffic_group]
        return ret_traffic_group

    def _get_least_gw_traffic_group(self):
        ret_traffic_group = 'traffic-group-1'
        lowest_count = 0
        for traffic_group in self.__gw_on_traffic_groups:
            if self.__gw_on_traffic_groups[traffic_group] <= lowest_count:
                ret_traffic_group = self.__gw_on_traffic_groups[traffic_group]
        return ret_traffic_group

    def _get_bigip(self):
        hostnames = sorted(self.__bigips)
        for i in range(len(hostnames)):
            try:
                bigip = self.__bigips[hostnames[i]]
                return bigip
            except urllib2.URLError:
                pass
        raise urllib2.URLError('cannot communicate to any bigips')

    def _get_vlan_name(self, network, hostname):
        net_key = network['provider:physical_network']
        # look for host specific interface mapping
        if net_key + ':' + hostname in self.interface_mapping:
            interface = self.interface_mapping[net_key + ':' + hostname]
            tagged = self.tagging_mapping[net_key + ':' + hostname]
        # look for specific interface mapping
        elif net_key in self.interface_mapping:
            interface = self.interface_mapping[net_key]
            tagged = self.tagging_mapping[net_key]
        # use default mapping
        else:
            interface = self.interface_mapping['default']
            tagged = self.tagging_mapping['default']

        if tagged:
            vlanid = network['provider:segmentation_id']
        else:
            vlanid = 0

        vlan_name = "vlan-" + \
                    str(interface).replace(".", "-") + \
                    "-" + str(vlanid)
        if len(vlan_name) > 15:
            vlan_name = 'vlan-tr-' + str(vlanid)
        return vlan_name

    def _get_tunnel_name(self, network):
        tunnel_type = network['provider:network_type']
        tunnel_id = network['provider:segmentation_id']
        return 'tunnel-' + str(tunnel_type) + '-' + str(tunnel_id)

    def _get_tunnel_fake_mac(self, network, local_ip):
        network_id = str(network['provider:segmentation_id']).rjust(4, '0')
        mac_prefix = '02:' + network_id[:2] + ':' + network_id[2:4] + ':'
        ip_parts = local_ip.split('.')
        if len(ip_parts) > 3:
            mac = [int(ip_parts[-3]),
                   int(ip_parts[-2]),
                   int(ip_parts[-1])]
        else:
            ip_parts = local_ip.split(':')
            if len(ip_parts) > 3:
                mac = [int('0x' + ip_parts[-3], 16),
                       int('0x' + ip_parts[-2], 16),
                       int('0x' + ip_parts[-1], 16)]
            else:
                mac = [random.randint(0x00, 0x7f),
                       random.randint(0x00, 0xff),
                       random.randint(0x00, 0xff)]
        return mac_prefix + ':'.join(map(lambda x: "%02x" % x, mac))

    def _create_app_cookie_persist_rule(self, cookiename):
        rule_text = "when HTTP_REQUEST {\n"
        rule_text += " if { [HTTP::cookie " + str(cookiename)
        rule_text += "] ne \"\" }{\n"
        rule_text += "     persist uie [string tolower [HTTP::cookie \""
        rule_text += cookiename + "\"]] 3600\n"
        rule_text += " }\n"
        rule_text += "}\n\n"
        rule_text += "when HTTP_RESPONSE {\n"
        rule_text += " if { [HTTP::cookie \"" + str(cookiename)
        rule_text += "\"] ne \"\" }{\n"
        rule_text += "     persist add uie [string tolower [HTTP::cookie \""
        rule_text += cookiename + "\"]] 3600\n"
        rule_text += " }\n"
        rule_text += "}\n\n"
        return rule_text

    def _create_http_rps_throttle_rule(self, req_limit):
        rule_text = "when HTTP_REQUEST {\n"
        rule_text += " set expiration_time 300\n"
        rule_text += " set client_ip [IP::client_addr]\n"
        rule_text += " set req_limit " + str(req_limit) + "\n"
        rule_text += " set curr_time [clock seconds]\n"
        rule_text += " set timekey starttime\n"
        rule_text += " set reqkey reqcount\n"
        rule_text += " set request_count [session lookup uie $reqkey]\n"
        rule_text += " if { $request_count eq \"\" } {\n"
        rule_text += "   set request_count 1\n"
        rule_text += "   session add uie $reqkey $request_count "
        rule_text += " $expiration_time\n"
        rule_text += "   session add uie $timekey [expr {$curr_time - 2}]"
        rule_text += " [expr {$expiration_time + 2}]\n"
        rule_text += " } else {\n"
        rule_text += "   set start_time [session lookup uie $timekey]\n"
        rule_text += "   incr request_count\n"
        rule_text += "   session add uie $reqkey $request_count"
        rule_text += " $expiration_time\n"
        rule_text += "   set elapsed_time [expr {$curr_time - $start_time}]\n"
        rule_text += "   if {$elapsed_time < 60} {\n"
        rule_text += "     set elapsed_time 60\n"
        rule_text += "   }\n"
        rule_text += "   set curr_rate [expr {$request_count /"
        rule_text += "($elapsed_time/60)}]\n"
        rule_text += "   if {$curr_rate > $req_limit}{\n"
        rule_text += "     HTTP::respond 503 throttled \"Retry-After\" 60\n"
        rule_text += "   }\n"
        rule_text += " }\n"
        rule_text += "}\n"
        return rule_text

    def _init_connection(self):
        if not self.connected:
            try:
                self.__last_connect_attempt = datetime.datetime.now()

                if not self.conf.icontrol_hostname:
                    raise InvalidConfigurationOption(
                                opt_name='icontrol_hostname',
                                opt_value='valid hostname or IP address')
                if not self.conf.icontrol_username:
                    raise InvalidConfigurationOption(
                                opt_name='icontrol_username',
                                opt_value='valid username')
                if not self.conf.icontrol_password:
                    raise InvalidConfigurationOption(
                                opt_name='icontrol_password',
                                opt_value='valid password')

                self.hostnames = self.conf.icontrol_hostname.split(',')
                self.hostnames = [item.strip() for item in self.hostnames]
                self.hostnames = sorted(self.hostnames)

                if self.conf.icontrol_connection_timeout:
                    f5const.CONNECTION_TIMEOUT = \
                           self.conf.icontrol_connection_timeout

                self.agent_id = None

                self.username = self.conf.icontrol_username
                self.password = self.conf.icontrol_password

                LOG.info(_('Opening iControl connections to %s @ %s' % (
                                                            self.username,
                                                            self.hostnames[0])
                            ))
                # connect to inital device:
                first_bigip = f5_bigip.BigIP(self.hostnames[0],
                                        self.username,
                                        self.password,
                                        f5const.CONNECTION_TIMEOUT,
                                        self.conf.use_namespaces,
                                        self.conf.f5_route_domain_strictness)
                first_bigip.system.set_folder('/Common')
                major_version = first_bigip.system.get_major_version()
                if major_version < f5const.MIN_TMOS_MAJOR_VERSION:
                    raise f5ex.MajorVersionValidateFailed(
                                'device %s must be at least TMOS %s.%s'
                                % (self.hostnames[0],
                                   f5const.MIN_TMOS_MAJOR_VERSION,
                                   f5const.MIN_TMOS_MINOR_VERSION))
                minor_version = first_bigip.system.get_minor_version()
                if minor_version < f5const.MIN_TMOS_MINOR_VERSION:
                    raise f5ex.MinorVersionValidateFailed(
                            'device %s must be at least TMOS %s.%s'
                            % (self.hostnames[0],
                               f5const.MIN_TMOS_MAJOR_VERSION,
                               f5const.MIN_TMOS_MINOR_VERSION))
                extramb = first_bigip.system.get_provision_extramb()
                if int(extramb) < f5const.MIN_EXTRA_MB:
                    raise f5ex.ProvisioningExtraMBValidateFailed(
            'device %s BIG-IP not provisioned for management LARGE. extramb=%d'
                       % (self.hostnames[0], int(extramb)))

                # Turn off tunnel syncing... our VTEPs are local SelfIPs
                tunnel_sync = first_bigip.system.get_tunnel_sync()
                if tunnel_sync and tunnel_sync == 'enable':
                    first_bigip.system.set_tunnel_sync(enabled=False)

                # if there was only one address supplied and
                # this is not a standalone device, get the
                # devices trusted by this device.
                cluster_name = first_bigip.device.get_device_group()

                if not cluster_name and self.conf.f5_ha_type != 'standalone':
                    raise f5ex.BigIPClusterInvalidHA(
                     'HA mode is %s and no sync failover device group found.'
                     % self.conf.f5_ha_type)

                if len(self.hostnames) < 2:
                    if not first_bigip.cluster.get_sync_status() == \
                                                              'Standalone':
                        devices = first_bigip.cluster.devices(cluster_name)
                        mgmt_addrs = []
                        for device in devices:
                            mgmt_addrs.append(
                                first_bigip.device.get_mgmt_addr_by_device(
                                                                     device))
                        self.hostnames = mgmt_addrs
                    else:
                        if not self.conf.f5_ha_type == 'standalone':
                            raise f5ex.BigIPClusterInvalidHA(
                              'HA mode is %s and only one host found.'
                              % self.conf.f5_ha_type)

                # populate traffic groups and count vips per tg
                self.init_traffic_groups(first_bigip)

                self.__bigips[self.hostnames[0]] = first_bigip
                # connect to the rest of the devices
                for host in self.hostnames[1:]:
                    LOG.info(_('Opening iControl connections to %s @ %s' % (
                                                            self.username,
                                                            host)
                            ))
                    hostbigip = f5_bigip.BigIP(host,
                                        self.username,
                                        self.password,
                                        f5const.CONNECTION_TIMEOUT,
                                        self.conf.use_namespaces,
                                        self.conf.f5_route_domain_strictness)
                    self.__bigips[host] = hostbigip
                    hostbigip.system.set_folder('/Common')
                    major_version = hostbigip.system.get_major_version()
                    if major_version < f5const.MIN_TMOS_MAJOR_VERSION:
                        raise f5ex.MajorVersionValidateFailed(
                                    'device %s must be at least TMOS %s.%s'
                                    % (host,
                                       f5const.MIN_TMOS_MAJOR_VERSION,
                                       f5const.MIN_TMOS_MINOR_VERSION))
                    minor_version = hostbigip.system.get_minor_version()
                    if minor_version < f5const.MIN_TMOS_MINOR_VERSION:
                        raise f5ex.MinorVersionValidateFailed(
                                'device %s must be at least TMOS %s.%s'
                                % (host,
                                   f5const.MIN_TMOS_MAJOR_VERSION,
                                   f5const.MIN_TMOS_MINOR_VERSION))
                    extramb = hostbigip.system.get_provision_extramb()
                    if int(extramb) < f5const.MIN_EXTRA_MB:
                        raise f5ex.ProvisioningExtraMBValidateFailed(
                       'device %s BIG-IP not provisioned for management LARGE.'
                       % self.host)

                    # Turn off tunnel syncing... our VTEPs are local SelfIPs
                    tunnel_sync = hostbigip.system.get_tunnel_sync()
                    if tunnel_sync and tunnel_sync == 'enable':
                        hostbigip.system.set_tunnel_sync(enabled=False)

                    if hostbigip.device.get_device_group() != cluster_name:
                        raise f5ex.BigIPClusterInvalidHA(
                                       'Invalid HA. Not all devices in the' +
                                       ' same sync failover device group'
                                       )

                    for network in self.conf.common_network_ids.values():
                        if not hostbigip.vlan.exists(network,
                                                     folder='Common'):
                            raise f5ex.MissingNetwork(_(
                                  'common network %s on %s does not exist'
                                  % (network, hostbigip.icontrol.hostname)
                                  ))

                if not cluster_name and self.conf.f5_ha_type != 'standalone':
                    raise f5ex.BigIPClusterInvalidHA(
                     'HA mode is %s and no sync failover device group found.'
                     % self.conf.f5_ha_type)

                if self.conf.f5_ha_type == 'standalone' and \
                   len(self.__bigips) > 1:
                    raise f5ex.BigIPClusterInvalidHA(
                         'HA mode is %s and there are %d devices present.'
                         % (self.conf.f5_ha_type, len(self.__bigips)))

                if self.conf.f5_ha_type == 'pair' and \
                   len(self.__bigips) > 2:
                    raise f5ex.BigIPClusterInvalidHA(
                         'HA mode is %s and there are %d devices present.'
                         % (self.conf.f5_ha_type, len(self.__bigips)))

                if not self.conf.debug:
                    sudslog = std_logging.getLogger('suds.client')
                    sudslog.setLevel(std_logging.FATAL)

                # setup device object caches and sync mode
                autosync = True
                if self.conf.f5_sync_mode == 'replication':
                    autosync = False
                bigips = self.__bigips.values()

                for set_bigip in bigips:
                    set_bigip.group_bigips = bigips
                    set_bigip.sync_mode = self.conf.f5_sync_mode
                    set_bigip.assured_networks = []
                    set_bigip.assured_snat_subnets = []
                    set_bigip.assured_gateway_subnets = []
                    set_bigip.local_ip = None
                    if autosync:
                        set_bigip.cluster.enable_auto_sync(cluster_name)
                    else:
                        set_bigip.cluster.disable_auto_sync(cluster_name)

                # setup tunneling
                # setup VTEP tunnels if needed
                vtep_folder = self.conf.f5_vtep_folder
                vtep_selfip_name = self.conf.f5_vtep_selfip_name

                local_ips = []

                icontrol_endpoints = {}

                for host in self.__bigips:
                    hostbigip = self.__bigips[host]
                    icontrol_endpoints[host] = {}
                    icontrol_endpoints[host]['version'] = \
                                       hostbigip.system.get_version()
                    hostbigip.device_name = \
                                       hostbigip.device.get_device_name()
                    icontrol_endpoints[host]['device_name'] = \
                                       hostbigip.device_name
                    icontrol_endpoints[host]['platform'] = \
                                       hostbigip.system.get_platform()
                    icontrol_endpoints[host]['serial_number'] = \
                                       hostbigip.system.get_serial_number()

                    if not self.conf.f5_global_routed_mode:
                        if not vtep_folder or (vtep_folder.lower() == 'none'):
                            vtep_folder = 'Common'

                        if vtep_selfip_name and \
                           (not vtep_selfip_name.lower() == 'none'):

                            # profiles may already exist
                            hostbigip.vxlan.create_multipoint_profile(
                                                            name='vxlan_ovs',
                                                            folder='Common')
                            hostbigip.l2gre.create_multipoint_profile(
                                                            name='gre_ovs',
                                                            folder='Common')
                            # find the IP address for the selfip for each box
                            local_ip = hostbigip.selfip.get_addr(
                                                vtep_selfip_name, vtep_folder)
                            if local_ip:
                                hostbigip.local_ip = local_ip
                                local_ips.append(local_ip)
                            else:
                                raise f5ex.MissingVTEPAddress(
                                            'device %s missing vtep selfip %s'
                                            % (hostbigip.device_name,
                                               '/' + vtep_folder + '/' + \
                                               vtep_selfip_name))

                    local_ip = sorted(local_ips)

                    self.agent_configurations['tunneling_ips'] = local_ips
                    self.agent_configurations['icontrol_endpoints'] = \
                                                            icontrol_endpoints

                    LOG.debug(_('connected to iControl %s @ %s ver %s.%s'
                                % (self.username, host,
                                   major_version, minor_version)))

                self.connected = True

                if self.conf.environment_prefix:
                    self.agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                                               self.conf.environment_prefix + \
                                               '.' + self.hostnames[0]))
                else:
                    self.agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                                               self.hostnames[0]))

            except Exception as exc:
                LOG.error(_('Could not communicate with all ' +
                            'iControl devices: %s' % exc.message))

    def init_traffic_groups(self, bigip):
        self.__traffic_groups = bigip.cluster.get_traffic_groups()
        if 'traffic-group-local-only' in self.__traffic_groups:
            self.__traffic_groups.remove(
                            'traffic-group-local-only')
        self.__traffic_groups.sort()
        for traffic_group in self.__traffic_groups:
            self.__gw_on_traffic_groups[traffic_group] = 0
            self.__vips_on_traffic_groups[traffic_group] = 0

        for folder in bigip.system.get_folders():
            if not folder.startswith(bigip_interfaces.OBJ_PREFIX):
                continue
            for virtserv in bigip.virtual_server.get_virtual_servers(folder):
                vip_tg = bigip.virtual_server.get_traffic_group(
                                                    name=virtserv,
                                                    folder=folder)
                self.__vips_on_traffic_groups[vip_tg] += 1
        LOG.debug("init_traffic_groups: starting tg counts: %s"
                  % str(self.__vips_on_traffic_groups))

    # should be moved to cluster abstraction
    def _sync_if_clustered(self, bigip):
        if self.conf.f5_sync_mode == 'replication':
            return
        if len(bigip.group_bigips) > 1:
            if not hasattr(bigip, 'device_group'):
                bigip.device_group = bigip.device.get_device_group()
            self._sync_with_retries(bigip)

    def _sync_with_retries(self, bigip, force_now=False,
                           attempts=4, retry_delay=130):
        for attempt in range(1, attempts + 1):
            LOG.debug('Syncing Cluster... attempt %d of %d'
                      % (attempt, attempts))
            try:
                if attempt != 1:
                    force_now = False
                bigip.cluster.sync(bigip.device_group, force_now=force_now)
                LOG.debug('Cluster synced.')
                return
            except:
                LOG.error('ERROR: Cluster sync failed.')
                if attempt == attempts:
                    raise
                LOG.error(
             'Wait another %d seconds for devices to recover from failed sync.'
                    % retry_delay)
                greenthread.sleep(retry_delay)

    @serialized('backup_configuration')
    @is_connected
    def backup_configuration(self):
        for bigip in self.__bigips.values():
            LOG.debug(_('saving %s device configuration.'
                        % bigip.icontrol.hostname))
            bigip.cluster.save_config()

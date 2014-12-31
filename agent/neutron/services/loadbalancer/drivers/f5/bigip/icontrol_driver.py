""" F5 Networks LBaaS Driver using iControl API of BIG-IP """
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
# pylint: disable=broad-except,star-args,no-self-use

from oslo.config import cfg
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants as plugin_const
from neutron.common.exceptions import NeutronException, \
    InvalidConfigurationOption
from neutron.services.loadbalancer import constants as lb_const

from neutron.services.loadbalancer.drivers.f5.bigip.l2 import \
    BigipL2Manager

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
import itertools
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
        'icontrol_vcmp_hostname',
        help=_('The hostname (name or IP address) to use for vCMP Host '
               'iControl access'),
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


def is_connected(method):
    """Decorator to check we are connected before provisioning."""
    def wrapper(*args, **kwargs):
        """ Necessary wrapper """
        instance = args[0]
        if instance.connected:
            try:
                return method(*args, **kwargs)
            except IOError as ioe:
                LOG.error(_('IO Error detected: %s' % method.__name__))
                instance.non_connected()
                raise ioe
        else:
            LOG.error(_('Cannot execute %s. Not connected.'
                        % method.__name__))
            instance.non_connected()
    return wrapper


def serialized(method_name):
    """Outer wrapper in order to specify method name"""
    def real_serialized(method):
        """Decorator to serialize calls to configure via iControl"""
        def wrapper(*args, **kwargs):
            """ Necessary wrapper """
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


def request_index(request_queue, request_id):
    """ Get index of request in request queue """
    for request in request_queue:
        if request[0] == request_id:
            return request_queue.index(request)


class iControlDriver(object):
    """F5 LBaaS Driver for BIG-IP using iControl"""

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(OPTS)
        self.context = None
        self.agent_id = None
        self.hostnames = None
        self.device_type = conf.f5_device_type
        self.plugin_rpc = None
        self.connected = False
        self.__last_connect_attempt = None
        self.service_queue = []
        self.agent_configurations = {}
        self.tunnel_rpc = None
        self.l2pop_rpc = None

        # BIG-IP containers
        self.__bigips = {}
        self.__traffic_groups = []

        # mappings
        self.__vips_to_traffic_group = {}
        self.__gw_to_traffic_group = {}

        # scheduling counts
        self.__vips_on_traffic_groups = {}
        self.__gw_on_traffic_groups = {}

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
            self.tunnel_types = self.conf.advertised_tunnel_types
            self.agent_configurations['tunnel_types'] = self.tunnel_types

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

        self._init_bigip_hostnames()
        self._init_bigips()

        if self.conf.f5_global_routed_mode:
            self.bigip_l2_manager = None
        else:
            self.bigip_l2_manager = BigipL2Manager(self)
            self.agent_configurations['bridge_mappings'] = \
                self.bigip_l2_manager.interface_mapping

        LOG.info(_('iControlDriver initialized to %d bigips with username:%s'
                   % (len(self.__bigips), self.conf.icontrol_username)))
        LOG.info(_('iControlDriver dynamic agent configurations:%s'
                   % self.agent_configurations))

    def _init_bigip_hostnames(self):
        """ Validate and parse bigip credentials """
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

        if self.conf.environment_prefix:
            self.agent_id = str(
                uuid.uuid5(uuid.NAMESPACE_DNS,
                           self.conf.environment_prefix +
                           '.' + self.hostnames[0]))
        else:
            self.agent_id = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, self.hostnames[0]))

    def _init_bigips(self):
        """ Connect to all BIG-IPs """
        if self.connected:
            return
        try:
            if not self.conf.debug:
                sudslog = std_logging.getLogger('suds.client')
                sudslog.setLevel(std_logging.FATAL)
                requests_log = std_logging.getLogger(
                    "requests.packages.urllib3")
                requests_log.setLevel(std_logging.ERROR)
                requests_log.propagate = False

            else:
                requests_log = std_logging.getLogger(
                    "requests.packages.urllib3")
                requests_log.setLevel(std_logging.DEBUG)
                requests_log.propagate = True

            self.__last_connect_attempt = datetime.datetime.now()
            if self.conf.icontrol_connection_timeout:
                f5const.CONNECTION_TIMEOUT = \
                    self.conf.icontrol_connection_timeout

            first_bigip = self._open_bigip(self.hostnames[0])
            self._init_bigip(first_bigip, self.hostnames[0], None)
            self.__bigips[self.hostnames[0]] = first_bigip

            device_group_name = self._validate_ha(first_bigip)
            self.init_traffic_groups(first_bigip)

            # connect to the rest of the devices
            for hostname in self.hostnames[1:]:
                bigip = self._open_bigip(hostname)
                self._init_bigip(bigip, hostname, device_group_name)
                self.__bigips[hostname] = bigip

            self._initialize_tunneling()
            self.connected = True

        except NeutronException as exc:
            LOG.error(_('Could not communicate with all ' +
                        'iControl devices: %s' % exc.msg))
            greenthread.sleep(5)
            raise
        except Exception as exc:
            LOG.error(_('Could not communicate with all ' +
                        'iControl devices: %s' % exc.message))
            greenthread.sleep(5)
            raise

    def _open_bigip(self, hostname):
        """ Open bigip connection """
        LOG.info(_('Opening iControl connection to %s @ %s' %
                   (self.conf.icontrol_username, hostname)))
        return f5_bigip.BigIP(hostname, self.conf.icontrol_username,
                              self.conf.icontrol_password,
                              f5const.CONNECTION_TIMEOUT,
                              self.conf.use_namespaces,
                              self.conf.f5_route_domain_strictness)

    def _init_bigip(self, bigip, hostname, check_group_name=None):
        """ Prepare a bigip for usage """
        bigip.system.set_folder('/Common')
        major_version, minor_version = _validate_bigip_version(bigip, hostname)

        extramb = bigip.system.get_provision_extramb()
        if int(extramb) < f5const.MIN_EXTRA_MB:
            raise f5ex.ProvisioningExtraMBValidateFailed(
                'Device %s BIG-IP not provisioned for '
                'management LARGE.' % hostname)

        if self.conf.f5_ha_type == 'pair' and \
                bigip.cluster.get_sync_status() == 'Standalone':
            raise f5ex.BigIPClusterInvalidHA(
                'HA mode is pair and bigip %s in standalone mode'
                % hostname)

        if self.conf.f5_ha_type == 'scalen' and \
                bigip.cluster.get_sync_status() == 'Standalone':
            raise f5ex.BigIPClusterInvalidHA(
                'HA mode is pair and bigip %s in standalone mode'
                % hostname)

        if self.conf.f5_ha_type != 'standalone':
            device_group_name = bigip.device.get_device_group()
            if not device_group_name:
                raise f5ex.BigIPClusterInvalidHA(
                    'HA mode is %s and no sync failover '
                    'device group found for device %s.'
                    % (self.conf.f5_ha_type, hostname))
            if check_group_name and device_group_name != check_group_name:
                raise f5ex.BigIPClusterInvalidHA(
                    'Invalid HA. Device %s is in device group'
                    ' %s but should be in %s.'
                    % (hostname, device_group_name, check_group_name))
            bigip.device_group_name = device_group_name

        for network in self.conf.common_network_ids.values():
            if not bigip.vlan.exists(network, folder='Common'):
                raise f5ex.MissingNetwork(_(
                    'Common network %s on %s does not exist'
                    % (network, bigip.icontrol.hostname)))

        bigip.device_name = bigip.device.get_device_name()
        bigip.assured_networks = []
        bigip.assured_snat_subnets = []
        bigip.assured_gateway_subnets = []

        if self.conf.f5_ha_type != 'standalone':
            if self.conf.f5_sync_mode == 'autosync':
                bigip.cluster.enable_auto_sync(device_group_name)
            else:
                bigip.cluster.disable_auto_sync(device_group_name)

        # Turn off tunnel syncing... our VTEPs are local SelfIPs
        if bigip.system.get_tunnel_sync() == 'enable':
            bigip.system.set_tunnel_sync(enabled=False)

        LOG.debug(_('Connected to iControl %s @ %s ver %s.%s'
                    % (self.conf.icontrol_username, hostname,
                       major_version, minor_version)))
        return bigip

    def _validate_ha(self, first_bigip):
        """ if there was only one address supplied and
            this is not a standalone device, get the
            devices trusted by this device. """
        device_group_name = None
        if self.conf.f5_ha_type == 'standalone':
            if len(self.hostnames) != 1:
                raise f5ex.BigIPClusterInvalidHA(
                    'HA mode is standalone and %d hosts found.'
                    % len(self.hostnames))
        elif self.conf.f5_ha_type == 'pair':
            device_group_name = first_bigip.device.get_device_group()
            if len(self.hostnames) != 2:
                mgmt_addrs = []
                devices = first_bigip.cluster.devices(device_group_name)
                for device in devices:
                    mgmt_addrs.append(
                        first_bigip.device.get_mgmt_addr_by_device(device))
                self.hostnames = mgmt_addrs
            if len(self.hostnames) != 2:
                raise f5ex.BigIPClusterInvalidHA(
                    'HA mode is pair and %d hosts found.'
                    % len(self.hostnames))
        elif self.conf.f5_ha_type == 'scalen':
            device_group_name = first_bigip.device.get_device_group()
            if len(self.hostnames) < 2:
                mgmt_addrs = []
                devices = first_bigip.cluster.devices(device_group_name)
                for device in devices:
                    mgmt_addrs.append(
                        first_bigip.device.get_mgmt_addr_by_device(device))
                self.hostnames = mgmt_addrs
        return device_group_name

    def _initialize_tunneling(self):
        """ setup tunneling
            setup VTEP tunnels if needed """
        vtep_folder = self.conf.f5_vtep_folder
        vtep_selfip_name = self.conf.f5_vtep_selfip_name
        local_ips = []
        icontrol_endpoints = {}

        for host in self.__bigips:
            hostbigip = self.__bigips[host]
            ic_host = {}
            ic_host['version'] = hostbigip.system.get_version()
            ic_host['device_name'] = hostbigip.device_name
            ic_host['platform'] = hostbigip.system.get_platform()
            ic_host['serial_number'] = hostbigip.system.get_serial_number()
            icontrol_endpoints[host] = ic_host

            if self.conf.f5_global_routed_mode:
                continue

            if not vtep_folder or vtep_folder.lower() == 'none':
                vtep_folder = 'Common'

            if vtep_selfip_name and \
               not vtep_selfip_name.lower() == 'none':

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
                           '/' + vtep_folder + '/' +
                           vtep_selfip_name))

        self.agent_configurations['tunneling_ips'] = sorted(local_ips)
        self.agent_configurations['icontrol_endpoints'] = icontrol_endpoints

    def set_context(self, context):
        """ Context to keep for database access """
        self.context = context

    def set_tunnel_rpc(self, tunnel_rpc):
        """ Provide L2 manager with ML2 RPC access """
        self.tunnel_rpc = tunnel_rpc
        if self.bigip_l2_manager:
            self.bigip_l2_manager.tunnel_rpc = tunnel_rpc

    def set_l2pop_rpc(self, l2pop_rpc):
        """ Provide L2 manager with ML2 RPC access """
        if self.bigip_l2_manager:
            self.bigip_l2_manager.l2pop_rpc = l2pop_rpc

    @serialized('exists')
    @is_connected
    def exists(self, service):
        """Check that service exists"""
        return self._service_exists(service)

    def flush_cache(self):
        """Remove cached objects so they can be created if necessary"""
        for set_bigip in self.get_all_bigips():
            set_bigip.assured_networks = []
            set_bigip.assured_snat_subnets = []
            set_bigip.assured_gateway_subnets = []

    # pylint: disable=unused-argument
    @serialized('create_vip')
    @is_connected
    def create_vip(self, vip, service):
        """Create virtual server"""
        self._common_service_handler(service)

    @serialized('update_vip')
    @is_connected
    def update_vip(self, old_vip, vip, service):
        """Update virtual server"""
        self._common_service_handler(service)

    @serialized('delete_vip')
    @is_connected
    def delete_vip(self, vip, service):
        """Delete virtual server"""
        self._common_service_handler(service)

    @serialized('create_pool')
    @is_connected
    def create_pool(self, pool, service):
        """Create lb pool"""
        self._common_service_handler(service)

    @serialized('update_pool')
    @is_connected
    def update_pool(self, old_pool, pool, service):
        """Update lb pool"""
        self._common_service_handler(service)

    @serialized('delete_pool')
    @is_connected
    def delete_pool(self, pool, service):
        """Delete lb pool"""
        self._common_service_handler(service, skip_networking=True)

    @serialized('create_member')
    @is_connected
    def create_member(self, member, service):
        """Create pool member"""
        self._common_service_handler(service)

    @serialized('update_member')
    @is_connected
    def update_member(self, old_member, member, service):
        """Update pool member"""
        self._common_service_handler(service)

    @serialized('delete_member')
    @is_connected
    def delete_member(self, member, service):
        """Delete pool member"""
        self._common_service_handler(service)

    @serialized('create_pool_health_monitor')
    @is_connected
    def create_pool_health_monitor(self, health_monitor, pool, service):
        """Create pool health monitor"""
        self._common_service_handler(service, skip_networking=True)
        return True

    @serialized('update_health_monitor')
    @is_connected
    def update_health_monitor(self, old_health_monitor,
                              health_monitor, pool, service):
        """Update pool health monitor"""
        # The altered health monitor does not mark its
        # status as PENDING_UPDATE properly.  Force it.
        for i in range(len(service['pool']['health_monitors_status'])):
            if service['pool']['health_monitors_status'][i]['monitor_id'] == \
                    health_monitor['id']:
                service['pool']['health_monitors_status'][i]['status'] = \
                    plugin_const.PENDING_UPDATE
        self._common_service_handler(service, skip_networking=True)
        return True

    @serialized('delete_pool_health_monitor')
    @is_connected
    def delete_pool_health_monitor(self, health_monitor, pool, service):
        """Delete pool health monitor"""
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

        self._common_service_handler(service, skip_networking=True)
        return True
    # pylint: enable=unused-argument

    @serialized('get_stats')
    @is_connected
    def get_stats(self, service):
        """Get service stats"""
        # use pool stats because the pool_id is the
        # the service definition... not the vip
        #
        stats = {}
        stats[lb_const.STATS_IN_BYTES] = 0
        stats[lb_const.STATS_OUT_BYTES] = 0
        stats[lb_const.STATS_ACTIVE_CONNECTIONS] = 0
        stats[lb_const.STATS_TOTAL_CONNECTIONS] = 0
        members = {}
        for hostbigip in self.get_all_bigips():
            # It appears that stats are collected for pools in a pending delete
            # state which means that if those messages are queued (or delayed)
            # it can result in the process of a stats request after the pool
            # and tenant are long gone. Check if the tenant exists.
            if not service['pool'] or not hostbigip.system.folder_exists(
               bigip_interfaces.OBJ_PREFIX + service['pool']['tenant_id']):
                return None
            pool = service['pool']
            pool_get_stats = hostbigip.pool.get_statistics
            bigip_stats = pool_get_stats(name=pool['id'],
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
                    get_mon_status = hostbigip.pool.get_members_monitor_status
                    states = get_mon_status(name=pool['id'],
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

    @serialized('remove_orphans')
    def remove_orphans(self, services):
        """ Remove out-of-date configuration on big-ips """
        existing_tenants = []
        existing_pools = []
        for service in services:
            existing_tenants.append(services[service].tenant_id)
            existing_pools.append(services[service].pool_id)

        for bigip in self.get_all_bigips():
            bigip.pool.purge_orphaned_pools(existing_pools)

        for bigip in self.get_all_bigips():
            bigip.system.purge_orphaned_folders_contents(existing_tenants)

        for bigip in self.get_all_bigips():
            bigip.system.force_root_folder()

        for bigip in self.get_all_bigips():
            bigip.system.purge_orphaned_folders(existing_tenants)

    @serialized('fdb_add')
    def fdb_add(self, fdb_entries):
        """ Add (L2toL3) forwarding database entries """
        return self.bigip_l2_manager.fdb_add(fdb_entries)

    @serialized('fdb_remove')
    def fdb_remove(self, fdb_entries):
        """ Remove (L2toL3) forwarding database entries """
        return self.bigip_l2_manager.fdb_remove(fdb_entries)

    @serialized('fdb_update')
    def fdb_update(self, fdb_entries):
        """ Update (L2toL3) forwarding database entries """
        return self.bigip_l2_manager.fdb_update(fdb_entries)

    def tunnel_sync(self):
        """ Update list of tunnel endpoints """
        resync = False
        for bigip in self.get_all_bigips():
            if bigip.local_ip:
                try:
                    for tunnel_type in self.tunnel_types:
                        if self.tunnel_rpc:
                            self.tunnel_rpc.tunnel_sync(self.context,
                                                        bigip.local_ip,
                                                        tunnel_type)
                except Exception as exp:
                    LOG.debug(
                        _("Unable to sync tunnel IP %(local_ip)s: %(e)s"),
                        {'local_ip': bigip.local_ip, 'e': exp})
                    resync = True
        return resync

    @serialized('sync')
    @is_connected
    def sync(self, service):
        """Sync service defintion to device"""
        self._common_service_handler(service)

    @serialized('backup_configuration')
    @is_connected
    def backup_configuration(self):
        """ Save Configuration on Devices """
        for bigip in self.get_all_bigips():
            LOG.debug(_('saving %s device configuration.'
                        % bigip.icontrol.hostname))
            bigip.cluster.save_config()

    def _service_exists(self, service):
        """ Returns whether the bigip has a pool for the service """
        bigip = self.get_bigip()
        if not service['pool']:
            return False
        return bigip.pool.exists(name=service['pool']['id'],
                                 folder=service['pool']['tenant_id'])

    def non_connected(self):
        """ Reconnect devices """
        now = datetime.datetime.now()
        if (now - self.__last_connect_attempt).total_seconds() > \
                self.conf.icontrol_connection_retry_interval:
            self.connected = False
            self._init_bigips()

    def _common_service_handler(self, service, skip_networking=False):
        """ Assure that the service is configured on bigip(s) """
        start_time = time()
        self._assure_tenant_created(service)
        LOG.debug("    _assure_tenant_created took %.5f secs" %
                  (time() - start_time))

        if not skip_networking:
            start_time = time()
            self._assure_create_networks(service)
            if time() - start_time > .001:
                LOG.debug("        _assure_service_networks "
                          "took %.5f secs" % (time() - start_time))

        all_subnet_hints = self._assure_service(service)

        if not skip_networking:
            start_time = time()
            self._assure_delete_networks(service, all_subnet_hints)
            LOG.debug("    _assure_delete_networks took %.5f secs" %
                      (time() - start_time))

        start_time = time()
        self._assure_tenant_cleanup(service, all_subnet_hints)
        LOG.debug("    _assure_tenant_cleanup took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._sync_if_clustered()
        LOG.debug("    final sync took %.5f secs" % (time() - start_time))

    def _assure_tenant_created(self, service):
        """ Delete tenant partition.
            Called for every bigip only in replication mode,
            otherwise called once.
        """
        tenant_id = service['pool']['tenant_id']

        # create tenant folder
        for bigip in self._get_config_bigips():
            folder = bigip.decorate_folder(tenant_id)
            if not bigip.system.folder_exists(folder):
                bigip.system.create_folder(folder, change_to=True)

        # folder must sync before route domains are created.
        self._sync_if_clustered()

        # create tenant route domain
        if self.conf.use_namespaces:
            for bigip in self.get_all_bigips():
                folder = bigip.decorate_folder(tenant_id)
                if not bigip.route.domain_exists(folder):
                    bigip.route.create_domain(folder)

    def _assure_create_networks(self, service):
        """ Assure network connectivity is established on all
            bigips for the service. """
        if self.conf.f5_global_routed_mode or not service['pool']:
            return

        start_time = time()

        # Per Device Network Connectivity (VLANs or Tunnels)
        subnetsinfo = _get_subnets_to_assure(service)
        for (assure_bigip, subnetinfo) in \
                itertools.product(self.get_all_bigips(), subnetsinfo):
            self._assure_bigip_network(assure_bigip, subnetinfo.network)
            self._assure_bigip_selfip(assure_bigip, service, subnetinfo)

        # L3 Shared Config
        assure_bigips = self._get_config_bigips()
        for subnetinfo in subnetsinfo:
            if self.conf.f5_snat_addresses_per_subnet > 0:
                self._assure_subnet_snats(assure_bigips, service, subnetinfo)

            if subnetinfo.is_for_member and not self.conf.f5_snat_mode:
                self._allocate_gw_addr(subnetinfo)
                for assure_bigip in assure_bigips:
                    # if we are not using SNATS, attempt to become
                    # the subnet's default gateway.
                    self._assure_gateway_on_subnet(assure_bigip, subnetinfo)

        if time() - start_time > .001:
            LOG.debug("    assure_service_networks took %.5f secs" %
                      (time() - start_time))

    def _assure_subnet_snats(self, assure_bigips, service, subnetinfo):
        """ Ensure snat for subnet exists on bigips """
        subnet = subnetinfo.subnet
        assure_bigips = [bigip for bigip in assure_bigips
                         if subnet['id'] not in bigip.assured_snat_subnets]
        if len(assure_bigips):
            snat_addrs = self._get_snat_addrs(service, subnetinfo)
            for assure_bigip in assure_bigips:
                self._assure_bigip_snats(assure_bigip, service, subnetinfo,
                                         snat_addrs)

    def _assure_bigip_network(self, bigip, network):
        """ Ensure the bigip has connectivity to the network """
        start_time = time()
        if not network:
            LOG.error(_('Attempted to assure a network with no id..skipping.'))
            return

        if network['id'] in bigip.assured_networks:
            return

        if network['id'] in self.conf.common_network_ids:
            LOG.debug(_('Network is a common global network... skipping.'))
            return

        self.bigip_l2_manager.assure_bigip_network(bigip, network)
        bigip.assured_networks.append(network['id'])
        if time() - start_time > .001:
            LOG.debug("        assure bigip network took %.5f secs" %
                      (time() - start_time))

    def _assure_bigip_selfip(self, bigip, service, subnetinfo):
        """ Create selfip on the BIG-IP """
        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to create selfip and snats'
                        ' for network with no id... skipping.'))
            return
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        pool = service['pool']
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = pool['tenant_id']

        (network_name, preserve_network_name) = \
            self.bigip_l2_manager.get_network_name(bigip, network)

        selfip_info = {'network_folder': network_folder,
                       'network_name': network_name,
                       'preserve_network_name': preserve_network_name}

        self._create_bigip_selfip(bigip, subnet, selfip_info)

    def _create_bigip_selfip(self, bigip, subnet, selfip_info):
        """ Create selfip on BIG-IP """
        local_selfip_name = "local-" + bigip.device_name + "-" + subnet['id']

        ports = self.plugin_rpc.get_port_by_name(port_name=local_selfip_name)
        if len(ports) > 0:
            ip_address = ports[0]['fixed_ips'][0]['ip_address']
        else:
            new_port = self.plugin_rpc.create_port_on_subnet(
                subnet_id=subnet['id'],
                mac_address=None,
                name=local_selfip_name,
                fixed_address_count=1)
            ip_address = new_port['fixed_ips'][0]['ip_address']

        netmask = netaddr.IPNetwork(subnet['cidr']).netmask
        network_folder = selfip_info['network_folder']
        network_name = selfip_info['network_name']
        preserve_network_name = selfip_info['preserve_network_name']
        bigip.selfip.create(name=local_selfip_name,
                            ip_address=ip_address,
                            netmask=netmask,
                            vlan_name=network_name,
                            floating=False,
                            folder=network_folder,
                            preserve_vlan_name=preserve_network_name)

    def _get_snat_addrs(self, service, subnetinfo):
        """ Get the ip addresses for snat depending on HA mode """
        if self.conf.f5_ha_type == 'standalone':
            return self._get_snat_addrs_standalone(subnetinfo)
        elif self.conf.f5_ha_type == 'pair':
            return self._get_snat_addrs_pair(subnetinfo)
        elif self.conf.f5_ha_type == 'scalen':
            return self._get_snat_addrs_scalen(service, subnetinfo)

    def _get_snat_addrs_standalone(self, subnetinfo):
        """ Get the ip addresses for snat in standalone HA mode """
        subnet = subnetinfo.subnet
        snat_addrs = []

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
            snat_addrs.append(ip_address)
        return snat_addrs

    def _get_snat_addrs_pair(self, subnetinfo):
        """ Get the ip addresses for snat in pair HA mode """
        subnet = subnetinfo.subnet

        snat_addrs = []
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
            snat_addrs.append(ip_address)
        return snat_addrs

    def _get_snat_addrs_scalen(self, service, subnetinfo):
        """ Get the ip addresses for snat in scalen HA mode """
        subnet = subnetinfo.subnet
        snat_addrs = []

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
            snat_addrs.append(ip_address)
        return snat_addrs

    def _assure_bigip_snats(self, bigip, service, subnetinfo, snat_addrs):
        """ Ensure Snat Addresses are configured on a bigip.
            Called for every bigip only in replication mode.
            otherwise called once and synced. """
        network = subnetinfo.network
        pool = service['pool']

        snat_info = {}
        if self.bigip_l2_manager.is_common_network(network):
            snat_info['network_folder'] = 'Common'
        else:
            snat_info['network_folder'] = pool['tenant_id']
        snat_info['pool_name'] = pool['tenant_id']
        snat_info['pool_folder'] = pool['tenant_id']
        snat_info['addrs'] = snat_addrs

        if self.conf.f5_ha_type == 'standalone':
            self._assure_snats_standalone(bigip, subnetinfo, snat_info)
        elif self.conf.f5_ha_type == 'pair':
            self._assure_snats_pair(bigip, subnetinfo, snat_info)
        elif self.conf.f5_ha_type == 'scalen':
            self._assure_snats_scalen(bigip, service, subnetinfo, snat_info)

    def _assure_snats_standalone(self, bigip, subnetinfo, snat_info):
        """ Configure the ip addresses for snat in standalone HA mode """
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        # Create SNATs on traffic-group-local-only
        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = snat_info['addrs'][i]
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            tglo = '/Common/traffic-group-local-only'
            bigip.snat.create(name=index_snat_name,
                              ip_address=ip_address,
                              traffic_group=tglo,
                              snat_pool_name=snat_info['pool_name'],
                              folder=snat_info['network_folder'],
                              snat_pool_folder=snat_info['pool_folder'])

        bigip.assured_snat_subnets.append(subnet['id'])

    def _assure_snats_pair(self, bigip, subnetinfo, snat_info):
        """ Configure the ip addresses for snat in pair HA mode """
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            ip_address = snat_info['addrs'][i]
            if self.bigip_l2_manager.is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            bigip.snat.create(name=index_snat_name,
                              ip_address=ip_address,
                              traffic_group='traffic-group-1',
                              snat_pool_name=snat_info['pool_name'],
                              folder=snat_info['network_folder'],
                              snat_pool_folder=snat_info['pool_folder'])

        bigip.assured_snat_subnets.append(subnet['id'])

    def _assure_snats_scalen(self, bigip, service, subnetinfo, snat_info):
        """ Configure the ip addresses for snat in scalen HA mode """
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        traffic_group = self._service_to_traffic_group(service)
        base_traffic_group = os.path.basename(traffic_group)
        snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = snat_info['addrs'][i]
            index_snat_name = snat_name + "_" + str(i)

            if self.bigip_l2_manager.is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            bigip.snat.create(
                name=index_snat_name,
                ip_address=ip_address,
                traffic_group=traffic_group,
                snat_pool_name=snat_info['pool_name'],
                folder=snat_info['network_folder'],
                snat_pool_folder=snat_info['pool_folder'])

        bigip.assured_snat_subnets.append(subnet['id'])

    def _allocate_gw_addr(self, subnetinfo):
        """ Create a name for the port and for the IP Forwarding
            Virtual Server as well as the floating Self IP which
            will answer ARP for the members """
        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to create default gateway'
                        ' for network with no id.. skipping.'))
            return

        subnet = subnetinfo.subnet
        gw_name = "gw-" + subnet['id']
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
        return True

    def _assure_gateway_on_subnet(self, bigip, subnetinfo):
        """ called for every bigip only in replication mode.
            otherwise called once """
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_gateway_subnets:
            return

        network = subnetinfo.network
        (network_name, preserve_network_name) = \
            self.bigip_l2_manager.get_network_name(bigip, network)

        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
            network_name = '/Common/' + network_name
        else:
            network_folder = subnet['tenant_id']

        # Select a traffic group for the floating SelfIP
        floating_selfip_name = "gw-" + subnet['id']
        netmask = netaddr.IPNetwork(subnet['cidr']).netmask
        vip_tg = self._get_least_gw_traffic_group()

        bigip.selfip.create(name=floating_selfip_name,
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
        gw_name = "gw-" + subnet['id']
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

    def _assure_service(self, service):
        """ Assure that the service is configured """
        if not service['pool']:
            return

        bigips = self._get_config_bigips()
        all_subnet_hints = {}
        for prep_bigip in bigips:
            # check_for_delete_subnets:
            #     keep track of which subnets we should check to delete
            #     for a deleted vip or member
            # do_not_delete_subnets:
            #     If we add an IP to a subnet we must not delete the subnet
            all_subnet_hints[prep_bigip.device_name] = \
                {'check_for_delete_subnets': {},
                 'do_not_delete_subnets': []}

        check_monitor_delete(service)

        start_time = time()
        self._assure_pool_create(service['pool'])
        LOG.debug("    _assure_pool_create took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_pool_monitors(service)
        LOG.debug("    _assure_pool_monitors took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_members(service, all_subnet_hints)
        LOG.debug("    _assure_members took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_vip(service, all_subnet_hints)
        LOG.debug("    _assure_vip took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_pool_delete(service)
        LOG.debug("    _assure_pool_delete took %.5f secs" %
                  (time() - start_time))

        return all_subnet_hints

    def _assure_pool_create(self, pool):
        """
            Provision Pool - Create/Update
        """
        # Service Layer (Shared Config)
        for bigip in self._get_config_bigips():
            self._assure_bigip_pool_create(pool, bigip)

        # OpenStack Updates
        if pool['status'] == plugin_const.PENDING_UPDATE:
            self.plugin_rpc.update_pool_status(
                pool['id'],
                status=plugin_const.ACTIVE,
                status_description='pool updated')
        elif pool['status'] == plugin_const.PENDING_CREATE:
            self.plugin_rpc.update_pool_status(
                pool['id'],
                status=plugin_const.ACTIVE,
                status_description='pool created')

    def _assure_bigip_pool_create(self, pool, bigip):
        """ called for every bigip only in replication mode.
            otherwise called once """
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

    def _assure_pool_monitors(self, service):
        """
            Provision Health Monitors - Create/Update
        """
        # Service Layer (Shared Config)
        for bigip in self._get_config_bigips():
            monitors_destroyed, monitors_updated = \
                self._assure_bigip_pool_monitors(service, bigip)
        for monitor_destroyed in monitors_destroyed:
            self.plugin_rpc.health_monitor_destroyed(
                **monitor_destroyed)
        for monitor_updated in monitors_updated:
            self.plugin_rpc.update_health_monitor_status(
                **monitor_updated)

    def _assure_bigip_pool_monitors(self, service, bigip):
        """ called for every bigip only in replication mode.
            otherwise called once """
        monitors_destroyed = []
        monitors_updated = []
        pool = service['pool']
        # Current monitors on the pool according to BigIP
        existing_monitors = bigip.pool.get_monitors(name=pool['id'],
                                                    folder=pool['tenant_id'])

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
                monitors_destroyed.append({'health_monitor_id': monitor['id'],
                                           'pool_id': pool['id']})
                # not sure if the monitor might be in use
                try:
                    LOG.debug(_('Deleting %s monitor /%s/%s'
                                % (monitor['type'],
                                   pool['tenant_id'],
                                   monitor['id'])))
                    bigip.monitor.delete(name=monitor['id'],
                                         mon_type=monitor['type'],
                                         folder=pool['tenant_id'])
                # pylint: disable=bare-except
                except:
                    pass
                # pylint: enable=bare-except
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
                if update_status:
                    monitors_updated.append(
                        {'pool_id': pool['id'],
                         'health_monitor_id': monitor['id'],
                         'status': plugin_const.ACTIVE,
                         'status_description': 'monitor active'})

            if found_existing_monitor:
                existing_monitors.remove(monitor['id'])

        LOG.debug(_("Pool: %s removing monitors %s"
                    % (pool['id'], existing_monitors)))
        # get rid of monitors no longer in service definition
        for monitor in existing_monitors:
            bigip.monitor.delete(name=monitor,
                                 mon_type=None,
                                 folder=pool['tenant_id'])
        return monitors_destroyed, monitors_updated

    def _update_monitor(self, bigip, monitor, set_times=True):
        """ Update monitor on BIG-IP """
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
            _update_http_monitor(bigip, monitor)

    def _assure_members(self, service, all_subnet_hints):
        """
            Provision Members - Create/Update
        """
        # Service Layer (Shared Config)
        for bigip in self._get_config_bigips():
            subnet_hints = all_subnet_hints[bigip.device_name]
            self._assure_bigip_members(service, bigip, subnet_hints)

        # L2toL3 networking layer
        # Non Shared Config -  Local Per BIG-IP
        for bigip in self.get_all_bigips():
            for member in service['members']:
                if member['status'] == plugin_const.PENDING_CREATE or \
                        member['status'] == plugin_const.PENDING_UPDATE:
                    self.bigip_l2_manager.update_bigip_member_l2(
                        bigip, service['pool'], member)
                if member['status'] == plugin_const.PENDING_DELETE:
                    self.bigip_l2_manager.delete_bigip_member_l2(
                        bigip, service['pool'], member)

        # OpenStack Updates
        for member in service['members']:
            if member['status'] == plugin_const.PENDING_CREATE:
                start_time = time()
                self.plugin_rpc.update_member_status(
                    member['id'],
                    status=plugin_const.ACTIVE,
                    status_description='member created')
                LOG.debug("            update_member_status"
                          " took %.5f secs" % (time() - start_time))
            elif member['status'] == plugin_const.PENDING_UPDATE:
                start_time = time()
                self.plugin_rpc.update_member_status(
                    member['id'],
                    status=plugin_const.ACTIVE,
                    status_description='member updated')
                LOG.debug("            update_member_status"
                          " took %.5f secs" % (time() - start_time))
            elif member['status'] == plugin_const.PENDING_DELETE:
                try:
                    self.plugin_rpc.member_destroyed(member['id'])
                except Exception as exc:
                    LOG.error(_("Plugin delete member %s error: %s"
                                % (member['id'], exc.message)))

    def _assure_bigip_members(self, service, bigip, subnet_hints):
        """ Ensure pool members are on BIG-IP """
        pool = service['pool']
        start_time = time()
        # Current members on the BigIP
        pool['existing_members'] = bigip.pool.get_members(
            name=pool['id'], folder=pool['tenant_id'])
        # Flag if we need to change the pool's LB method to
        # include weighting by the ratio attribute
        any_using_ratio = False
        # Members according to Neutron
        for member in service['members']:
            member_hints = \
                self._assure_bigip_member(bigip, subnet_hints, pool, member)
            if member_hints['using_ratio']:
                any_using_ratio = True

            # Remove member from the list of members big-ip needs to remove
            if member_hints['found_existing']:
                pool['existing_members'].remove(member_hints['found_existing'])

        LOG.debug(_("Pool: %s removing members %s"
                    % (pool['id'], pool['existing_members'])))
        # remove any members which are no longer in the service
        for need_to_delete in pool['existing_members']:
            bigip.pool.remove_member(name=pool['id'],
                                     ip_address=need_to_delete['addr'],
                                     port=int(need_to_delete['port']),
                                     folder=pool['tenant_id'])

        # if members are using weights, change the LB to RATIO
        start_time = time()
        if any_using_ratio:
            #LOG.debug(_("Pool: %s changing to ratio based lb"
            #        % pool['id']))
            if pool['lb_method'] == lb_const.LB_METHOD_LEAST_CONNECTIONS:
                bigip.pool.set_lb_method(name=pool['id'],
                                         lb_method='RATIO_LEAST_CONNECTIONS',
                                         folder=pool['tenant_id'])
            else:
                bigip.pool.set_lb_method(name=pool['id'],
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
        if time() - start_time > .001:
            LOG.debug("        _assure_members setting pool lb method" +
                      " took %.5f secs" % (time() - start_time))

    def _assure_bigip_member(self, bigip, subnet_hints, pool, member):
        """ Ensure pool member is on BIG-IP """
        start_time = time()

        network = member['network']
        subnet = member['subnet']
        member_hints = {'found_existing': None,
                        'using_ratio': False}

        ip_address = member['address']
        if self.conf.f5_global_routed_mode or not network or \
                self.bigip_l2_manager.is_common_network(network):
            ip_address = ip_address + '%0'

        for existing_member in pool['existing_members']:
            if ip_address.startswith(existing_member['addr']) and \
               (member['protocol_port'] == existing_member['port']):
                member_hints['found_existing'] = existing_member
                break

        # Delete those pending delete
        if member['status'] == plugin_const.PENDING_DELETE:
            self._assure_bigip_delete_member(bigip, pool, member, ip_address)
            if subnet and \
               subnet['id'] not in subnet_hints['do_not_delete_subnets']:
                subnet_hints['check_for_delete_subnets'][subnet['id']] = \
                    SubnetInfo(network, subnet, is_for_member=True)
        else:
            just_added = False
            if not member_hints['found_existing']:
                add_start_time = time()
                port = int(member['protocol_port'])
                if bigip.pool.add_member(name=pool['id'],
                                         ip_address=ip_address,
                                         port=port,
                                         folder=pool['tenant_id'],
                                         no_checks=True):
                    just_added = True
                LOG.debug("           bigip.pool.add_member %s took %.5f" %
                          (ip_address, time() - add_start_time))
            if just_added or member['status'] == plugin_const.PENDING_UPDATE:
                member_info = {'pool': pool, 'member': member,
                               'ip_address': ip_address,
                               'just_added': just_added}
                member_hints['using_ratio'] = \
                    self._assure_update_member(bigip, member_info)
            if subnet and \
               subnet['id'] in subnet_hints['check_for_delete_subnets']:
                del subnet_hints['check_for_delete_subnets'][subnet['id']]
            if subnet and \
               subnet['id'] not in subnet_hints['do_not_delete_subnets']:
                subnet_hints['do_not_delete_subnets'].append(subnet['id'])

        if time() - start_time > .001:
            LOG.debug("        assuring member %s took %.5f secs" %
                      (member['address'], time() - start_time))
        return member_hints

    def _assure_update_member(self, bigip, member_info):
        """ Update properties of pool member on BIG-IP """
        pool = member_info['pool']
        member = member_info['member']
        ip_address = member_info['ip_address']
        just_added = member_info['just_added']

        using_ratio = False
        # Is it enabled or disabled?
        # no_checks because we add the member above if not found
        start_time = time()
        member_port = int(member['protocol_port'])
        if member['admin_state_up']:
            bigip.pool.enable_member(name=pool['id'],
                                     ip_address=ip_address,
                                     port=member_port,
                                     folder=pool['tenant_id'],
                                     no_checks=True)
        else:
            bigip.pool.disable_member(name=pool['id'],
                                      ip_address=ip_address,
                                      port=member_port,
                                      folder=pool['tenant_id'],
                                      no_checks=True)
        LOG.debug("            member enable/disable took %.5f secs" %
                  (time() - start_time))
        # Do we have weights for ratios?
        if member['weight'] > 1:
            if not just_added:
                start_time = time()
                set_ratio = bigip.pool.set_member_ratio
                set_ratio(name=pool['id'],
                          ip_address=ip_address,
                          port=member_port,
                          ratio=int(member['weight']),
                          folder=pool['tenant_id'],
                          no_checks=True)
                if time() - start_time > .0001:
                    LOG.debug("            member set ratio took %.5f secs" %
                              (time() - start_time))
            using_ratio = True

        return using_ratio

    def _assure_bigip_delete_member(self, bigip,
                                    pool, member, ip_address):
        """ Ensure pool member is deleted from BIG-IP """
        member_port = int(member['protocol_port'])
        bigip.pool.remove_member(name=pool['id'],
                                 ip_address=ip_address,
                                 port=member_port,
                                 folder=pool['tenant_id'])

        # avoids race condition:
        # deletion of pool member objects must sync before we
        # remove the selfip from the peer bigips.
        self._sync_if_clustered()

    def _assure_vip(self, service, all_subnet_hints):
        """ Ensure the vip is on all bigips. """
        vip = service['vip']
        if 'id' not in vip:
            return

        # Service Layer
        # (Shared Config)
        bigips = self._get_config_bigips()
        for bigip in bigips:
            if vip['status'] == plugin_const.PENDING_CREATE or \
               vip['status'] == plugin_const.PENDING_UPDATE:
                self._assure_bigip_create_vip(bigip, service)
            elif vip['status'] == plugin_const.PENDING_DELETE:
                self._assure_bigip_delete_vip(bigip, service)

        # L2toL3 networking layer
        # (Non Shared - Config Per BIG-IP)
        for bigip in self.get_all_bigips():
            if vip['status'] == plugin_const.PENDING_CREATE or \
               vip['status'] == plugin_const.PENDING_UPDATE:
                self.bigip_l2_manager.update_bigip_vip_l2(bigip, vip)
            if vip['status'] == plugin_const.PENDING_DELETE:
                self.bigip_l2_manager.delete_bigip_vip_l2(bigip, vip)

        # OpenStack Layer Updates
        if vip['status'] == plugin_const.PENDING_CREATE:
            self.plugin_rpc.update_vip_status(
                vip['id'],
                status=plugin_const.ACTIVE,
                status_description='vip created')
        elif vip['status'] == plugin_const.PENDING_UPDATE:
            self.plugin_rpc.update_vip_status(
                vip['id'],
                status=plugin_const.ACTIVE,
                status_description='vip updated')
        elif vip['status'] == plugin_const.PENDING_DELETE:
            try:
                self.plugin_rpc.vip_destroyed(vip['id'])
            except Exception as exc:
                LOG.error(_("Plugin delete vip %s error: %s"
                            % (vip['id'], exc.message)))

        self._update_vip_cache(bigips, vip, all_subnet_hints)

    def _update_vip_cache(self, bigips, vip, all_subnet_hints):
        """ update internal cache """
        if vip['status'] == plugin_const.PENDING_DELETE and \
                vip['id'] in self.__vips_to_traffic_group:
            vip_tg = self.__vips_to_traffic_group[vip['id']]
            self.__vips_on_traffic_groups[vip_tg] -= 1
            del self.__vips_to_traffic_group[vip['id']]
        for bigip in bigips:
            subnet_hints = all_subnet_hints[bigip.device_name]
            subnet = vip['subnet']
            if vip['status'] == plugin_const.PENDING_DELETE:
                network = vip['network']
                if subnet and subnet['id'] not in \
                        subnet_hints['do_not_delete_subnets']:
                    subnet_hints['check_for_delete_subnets'][subnet['id']] = \
                        SubnetInfo(network, subnet)
            else:
                if subnet and subnet['id'] in \
                        subnet_hints['check_for_delete_subnets']:
                    del subnet_hints['check_for_delete_subnets'][subnet['id']]
                if subnet and subnet['id'] not in \
                        subnet_hints['do_not_delete_subnets']:
                    subnet_hints['do_not_delete_subnets'].append(subnet['id'])

    def _assure_bigip_create_vip(self, bigip, service):
        """ Called for every bigip only in replication mode,
            otherwise called once for autosync mode. """
        vip = service['vip']
        pool = service['pool']
        ip_address = vip['address']
        snat_pool_name = None
        network = vip['network']
        preserve_network_name = False

        if self.conf.f5_global_routed_mode:
            network_name = None
            ip_address = ip_address + '%0'
        else:
            (network_name, preserve_network_name) = \
                self.bigip_l2_manager.get_network_name(bigip, network)

            if self.bigip_l2_manager.is_common_network(network):
                network_name = '/Common/' + network_name
                ip_address = ip_address + '%0'

            if self.conf.f5_snat_mode and \
               self.conf.f5_snat_addresses_per_subnet > 0:
                tenant_id = pool['tenant_id']
                snat_pool_name = bigip_interfaces.decorate_name(tenant_id,
                                                                tenant_id)

        vip_info = {'network_name': network_name,
                    'preserve_network_name': preserve_network_name,
                    'ip_address': ip_address,
                    'snat_pool_name': snat_pool_name}

        just_added_vip = self._create_bigip_vip(bigip, service, vip_info)

        if vip['status'] == plugin_const.PENDING_CREATE or \
           vip['status'] == plugin_const.PENDING_UPDATE or \
           just_added_vip:
            self._update_bigip_vip(bigip, service)

    def _assure_bigip_delete_vip(self, bigip, service):
        """ Remove vip from big-ip """
        vip = service['vip']
        bigip_vs = bigip.virtual_server

        LOG.debug(_('Vip: deleting VIP %s' % vip['id']))
        bigip_vs.remove_and_delete_persist_profile(
            name=vip['id'],
            folder=vip['tenant_id'])
        bigip_vs.delete(name=vip['id'], folder=vip['tenant_id'])

        bigip.rule.delete(name=RPS_THROTTLE_RULE_PREFIX +
                          vip['id'],
                          folder=vip['tenant_id'])

        bigip_vs.delete_uie_persist_profile(
            name=APP_COOKIE_RULE_PREFIX + vip['id'],
            folder=vip['tenant_id'])

        bigip.rule.delete(name=APP_COOKIE_RULE_PREFIX +
                          vip['id'],
                          folder=vip['tenant_id'])

        # avoids race condition:
        # deletion of vip address must sync before we
        # remove the selfip from the peer bigips.
        self._sync_if_clustered()

    def _create_bigip_vip(self, bigip, service, vip_info):
        """ Create vip on big-ip """
        vip = service['vip']
        pool = service['pool']

        network_name = vip_info['network_name']
        preserve_network_name = vip_info['preserve_network_name']
        ip_address = vip_info['ip_address']
        snat_pool_name = vip_info['snat_pool_name']

        bigip_vs = bigip.virtual_server
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

        folder = vip['tenant_id']
        if virtual_type == 'standard':
            if bigip_vs.create(name=vip['id'],
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
                return True
        else:
            preserve_name = preserve_network_name
            if bigip_vs.create_fastl4(name=vip['id'],
                                      ip_address=ip_address,
                                      mask='255.255.255.255',
                                      port=int(vip['protocol_port']),
                                      protocol=vip['protocol'],
                                      vlan_name=network_name,
                                      traffic_group=vip_tg,
                                      use_snat=self.conf.f5_snat_mode,
                                      snat_pool=snat_pool_name,
                                      folder=folder,
                                      preserve_vlan_name=preserve_name):
                # created update driver traffic group mapping
                vip_tg = bigip_vs.get_traffic_group(
                    name=vip['id'],
                    folder=pool['tenant_id'])
                self.__vips_to_traffic_group[vip['ip']] = vip_tg
                self.__vips_on_traffic_groups[vip_tg] += 1
                return True

    def _update_bigip_vip(self, bigip, service):
        """ Update vip on big-ip """
        vip = service['vip']
        pool = service['pool']
        bigip_vs = bigip.virtual_server

        desc = vip['name'] + ':' + vip['description']
        bigip_vs.set_description(name=vip['id'],
                                 description=desc,
                                 folder=pool['tenant_id'])

        bigip_vs.set_pool(name=vip['id'],
                          pool_name=pool['id'],
                          folder=pool['tenant_id'])
        if vip['admin_state_up']:
            bigip_vs.enable_virtual_server(name=vip['id'],
                                           folder=pool['tenant_id'])
        else:
            bigip_vs.disable_virtual_server(name=vip['id'],
                                            folder=pool['tenant_id'])

        if 'session_persistence' in vip and vip['session_persistence']:
            # branch on persistence type
            persistence_type = vip['session_persistence']['type']
            set_persist = bigip_vs.set_persist_profile
            set_fallback_persist = bigip_vs.set_fallback_persist_profile

            if persistence_type == 'SOURCE_IP':
                # add source_addr persistence profile
                LOG.debug('adding source_addr primary persistence')
                set_persist(name=vip['id'],
                            profile_name='/Common/source_addr',
                            folder=vip['tenant_id'])
            elif persistence_type == 'HTTP_COOKIE':
                # HTTP cookie persistence requires an HTTP profile
                LOG.debug('adding http profile and' +
                          ' primary cookie persistence')
                bigip_vs.add_profile(name=vip['id'],
                                     profile_name='/Common/http',
                                     folder=vip['tenant_id'])
                # add standard cookie persistence profile
                set_persist(name=vip['id'],
                            profile_name='/Common/cookie',
                            folder=vip['tenant_id'])
                if pool['lb_method'] == 'SOURCE_IP':
                    set_fallback_persist(name=vip['id'],
                                         profile_name='/Common/source_addr',
                                         folder=vip['tenant_id'])
            elif persistence_type == 'APP_COOKIE':
                self._set_bigip_vip_cookie_persist(bigip, service)
        else:
            bigip_vs.remove_all_persist_profiles(name=vip['id'],
                                                 folder=vip['tenant_id'])

        if vip['connection_limit'] > 0 and 'protocol' in vip:
            # spec says you need to do this for HTTP
            # and HTTPS, but unless you can decrypt
            # you can't measure HTTP rps for HTTPs
            conn_limit = int(vip['connection_limit'])
            if vip['protocol'] == 'HTTP':
                LOG.debug('adding http profile and RPS throttle rule')
                # add an http profile
                bigip_vs.add_profile(
                    name=vip['id'],
                    profile_name='/Common/http',
                    folder=vip['tenant_id'])
                # create the rps irule
                rule_definition = \
                    self._create_http_rps_throttle_rule(conn_limit)
                # try to create the irule
                bigip.rule.create(name=RPS_THROTTLE_RULE_PREFIX + vip['id'],
                                  rule_definition=rule_definition,
                                  folder=vip['tenant_id'])
                # for the rule text to update becuase
                # connection limit may have changed
                bigip.rule.update(name=RPS_THROTTLE_RULE_PREFIX + vip['id'],
                                  rule_definition=rule_definition,
                                  folder=vip['tenant_id'])
                # add the throttle to the vip
                rule_name = RPS_THROTTLE_RULE_PREFIX + vip['id']
                bigip_vs.add_rule(name=vip['id'], rule_name=rule_name,
                                  priority=500, folder=vip['tenant_id'])
            else:
                LOG.debug('setting connection limit')
                # if not HTTP.. use connection limits
                bigip_vs.set_connection_limit(name=vip['id'],
                                              connection_limit=conn_limit,
                                              folder=pool['tenant_id'])
        else:
            # clear throttle rule
            LOG.debug('removing RPS throttle rule if present')
            rule_name = RPS_THROTTLE_RULE_PREFIX + vip['id']
            bigip_vs.remove_rule(name=vip['id'],
                                 rule_name=rule_name,
                                 priority=500,
                                 folder=vip['tenant_id'])
            # clear the connection limits
            LOG.debug('removing connection limits')
            bigip_vs.set_connection_limit(name=vip['id'],
                                          connection_limit=0,
                                          folder=pool['tenant_id'])

    def _set_bigip_vip_cookie_persist(self, bigip, service):
        """ Setup VIP Cookie Persistence """
        vip = service['vip']
        pool = service['pool']
        bigip_vs = bigip.virtual_server

        set_persist = bigip_vs.set_persist_profile
        set_fallback_persist = bigip_vs.set_fallback_persist_profile

        # application cookie persistence requires
        # an HTTP profile
        LOG.debug('adding http profile'
                  ' and primary universal persistence')
        bigip_vs.add_profile(name=vip['id'],
                             profile_name='/Common/http',
                             folder=vip['tenant_id'])
        # make sure they gave us a cookie_name
        if 'cookie_name' in vip['session_persistence']:
            cookie_name = vip['session_persistence']['cookie_name']
            # create and add irule to capture cookie
            # from the service response.
            rule_definition = self._create_app_cookie_persist_rule(cookie_name)
            # try to create the irule
            rule_name = APP_COOKIE_RULE_PREFIX + vip['id']
            if bigip.rule.create(name=rule_name,
                                 rule_definition=rule_definition,
                                 folder=vip['tenant_id']):
                # create universal persistence profile
                bigip_vs.create_uie_profile(
                    name=APP_COOKIE_RULE_PREFIX + vip['id'],
                    rule_name=APP_COOKIE_RULE_PREFIX + vip['id'],
                    folder=vip['tenant_id'])
            # set persistence profile
            profile_name = APP_COOKIE_RULE_PREFIX + vip['id']
            set_persist(name=vip['id'],
                        profile_name=profile_name,
                        folder=vip['tenant_id'])
            if pool['lb_method'] == 'SOURCE_IP':
                profile_name = '/Common/source_addr'
                set_fallback_persist(name=vip['id'],
                                     profile_name=profile_name,
                                     folder=vip['tenant_id'])
        else:
            # if they did not supply a cookie_name
            # just default to regualar cookie peristence
            set_persist(name=vip['id'],
                        profile_name='/Common/cookie',
                        folder=vip['tenant_id'])
            if pool['lb_method'] == 'SOURCE_IP':
                profile_name = '/Common/source_addr'
                set_fallback_persist(name=vip['id'],
                                     profile_name=profile_name,
                                     folder=vip['tenant_id'])

    def _create_app_cookie_persist_rule(self, cookiename):
        """ Create rule for cookie persistence """
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
        """ Create http throttle rule """
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

    def _assure_pool_delete(self, service):
        """ Assure pool is deleted from big-ip """
        if service['pool']['status'] != plugin_const.PENDING_DELETE:
            return

        # Service Layer (Shared Config)
        for bigip in self._get_config_bigips():
            self._assure_bigip_pool_delete(bigip, service)

        # OpenStack Updates
        try:
            self.plugin_rpc.pool_destroyed(service['pool']['id'])
        except Exception as exc:
            LOG.error(_("Plugin destroy pool %s error: %s"
                        % (service['pool']['id'], exc.message)))

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_bigip_pool_delete(self, bigip, service):
        """ Assure pool is deleted from big-ip """
        # Remove the pool if it is pending delete
        LOG.debug(_('Deleting Pool %s' % service['pool']['id']))
        bigip.pool.delete(name=service['pool']['id'],
                          folder=service['pool']['tenant_id'])

    def _assure_delete_networks(self, service, all_subnet_hints):
        """ Assure networks is deleted from big-ips """
        if self.conf.f5_global_routed_mode:
            return

        deleted_names = set()

        # Delete shared config objects
        for bigip in self._get_config_bigips():
            LOG.debug('_assure_delete_networks delete nets for bigip %s %s'
                      % (bigip.device_name, all_subnet_hints))
            subnet_hints = all_subnet_hints[bigip.device_name]
            deleted_names = deleted_names.union(
                self._assure_delete_nets_shared(service,
                                                bigip,
                                                subnet_hints))

        LOG.debug('_assure_delete_networks before sync')
        # avoids race condition:
        # deletion of shared ip objects must sync before we
        # remove the selfips or vlans from the peer bigips.
        self._sync_if_clustered()

        # Delete non shared config objects
        for bigip in self.get_all_bigips():
            LOG.debug('_assure_delete_networks del nets nonshared for bigip %s'
                      % bigip.device_name)
            if self.conf.f5_sync_mode == 'replication':
                subnet_hints = all_subnet_hints[bigip.device_name]
            else:
                # If in autosync mode, then the IP operations were performed
                # on just the primary big-ip, and so that is where the subnet
                # hints are stored. So, just use those hints for every bigip.
                subnet_hints = all_subnet_hints[self.get_bigip().device_name]
            deleted_names = deleted_names.union(
                self._assure_delete_nets_nonshared(
                    service, bigip, subnet_hints))

        for port_name in deleted_names:
            LOG.debug('_assure_delete_networks del port %s'
                      % port_name)
            self.plugin_rpc.delete_port_by_name(
                port_name=port_name)

    def _assure_delete_nets_shared(self, service, bigip, subnet_hints):
        """ Assure shared configuration (which syncs) is deleted """
        deleted_names = set()
        for subnetinfo in _get_subnets_to_delete(bigip, service, subnet_hints):
            if not self.conf.f5_snat_mode:
                gw_name = self._delete_gateway_on_subnet(subnetinfo, bigip)
                deleted_names.add(gw_name)
            deleted_names = deleted_names.union(
                self._delete_bigip_snats(bigip, service, subnetinfo))
        return deleted_names

    def _delete_bigip_snats(self, bigip, service, subnetinfo):
        """ Assure shared snat configuration (which syncs) is deleted
            Called for every bigip only in replication mode,
            otherwise called once.
        """
        if not subnetinfo.network:
            LOG.error(_('Attempted to delete selfip and snats'
                        ' for missing network ... skipping.'))
            return set()

        deleted_names = set()
        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        if self.conf.f5_snat_addresses_per_subnet > 0:
            # failover mode dictates SNAT placement on traffic-groups
            if self.conf.f5_ha_type == 'standalone':
                deleted_names = self._delete_bigip_snats_standalone(
                    bigip, service, subnetinfo)
            elif self.conf.f5_ha_type == 'pair':
                deleted_names = self._delete_bigip_snats_pair(
                    bigip, service, subnetinfo)
            elif self.conf.f5_ha_type == 'scalen':
                deleted_names = self._delete_bigip_snats_scalen(
                    bigip, service, subnetinfo)

        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            bigip.assured_snat_subnets.remove(subnet['id'])

        return deleted_names

    def _delete_bigip_snats_standalone(self, bigip, service, subnetinfo):
        """ Assure snats deleted in standalone mode """
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = service['pool']['tenant_id']
        snat_pool_name = service['pool']['tenant_id']

        deleted_names = set()
        # Delete SNATs on traffic-group-local-only
        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                tmos_snat_name = '/Common/' + index_snat_name
            else:
                tmos_snat_name = index_snat_name
            bigip.snat.remove_from_pool(
                name=snat_pool_name,
                member_name=tmos_snat_name,
                folder=service['pool']['tenant_id'])
            if bigip.snat.delete(
                    name=tmos_snat_name,
                    folder=network_folder,
                    snat_pool_folder=service['pool']['tenant_id']):
                # Only if it still exists and can be
                # deleted because it is not in use can
                # we safely delete the neutron port
                deleted_names.add(index_snat_name)
        return deleted_names

    def _delete_bigip_snats_pair(self, bigip, service, subnetinfo):
        """ Assure snats deleted in HA Pair mode """
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = service['pool']['tenant_id']
        snat_pool_name = service['pool']['tenant_id']

        deleted_names = set()
        # Delete SNATs on traffic-group-1
        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                tmos_snat_name = '/Common/' + index_snat_name
            else:
                tmos_snat_name = index_snat_name
            bigip.snat.remove_from_pool(
                name=snat_pool_name,
                member_name=tmos_snat_name,
                folder=service['pool']['tenant_id'])
            if bigip.snat.delete(
                    name=tmos_snat_name,
                    folder=network_folder,
                    snat_pool_folder=service['pool']['tenant_id']):
                # Only if it still exists and can be
                # deleted because it is not in use can
                # we safely delete the neutron port
                deleted_names.add(index_snat_name)
        return deleted_names

    def _delete_bigip_snats_scalen(self, bigip, service, subnetinfo):
        """ Assure snats deleted in scalen mode """
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = service['pool']['tenant_id']
        snat_pool_name = service['pool']['tenant_id']

        deleted_names = set()

        # Delete SNATs on all provider defined traffic groups
        traffic_group = self._service_to_traffic_group(service)
        base_traffic_group = os.path.basename(traffic_group)
        snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                tmos_snat_name = "/Common/" + index_snat_name
            else:
                tmos_snat_name = index_snat_name
            bigip.snat.remove_from_pool(
                name=snat_pool_name,
                member_name=tmos_snat_name,
                folder=service['pool']['tenant_id'])
            if bigip.snat.delete(
                    name=tmos_snat_name,
                    folder=network_folder,
                    snat_pool_folder=service['pool']['tenant_id']):
                # Only if it still exists and can be
                # deleted because it is not in use can
                # we safely delete the neutron port
                deleted_names.add(index_snat_name)
        return deleted_names

    def _delete_gateway_on_subnet(self, subnetinfo, bigip):
        """ called for every bigip only in replication mode.
            otherwise called once """
        network = subnetinfo.network
        if not network:
            LOG.error(_('Attempted to delete default gateway'
                        ' for network with no id... skipping.'))
            return
        subnet = subnetinfo.subnet
        if self.bigip_l2_manager.is_common_network(network):
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

        if subnet['id'] in bigip.assured_gateway_subnets:
            bigip.assured_gateway_subnets.remove(subnet['id'])
        return gw_name

    def _assure_delete_nets_nonshared(self, service, bigip, subnet_hints):
        """ Delete non shared base objects for networks """
        deleted_names = set()
        for subnetinfo in _get_subnets_to_delete(bigip, service, subnet_hints):
            network = subnetinfo.network
            if self.bigip_l2_manager.is_common_network(network):
                network_folder = 'Common'
            else:
                network_folder = service['pool']['tenant_id']

            subnet = subnetinfo.subnet
            local_selfip_name = "local-" + bigip.device_name + \
                                "-" + subnet['id']
            if self.conf.f5_populate_static_arp:
                bigip.arp.delete_by_subnet(subnet=subnet['cidr'],
                                           mask=None,
                                           folder=network_folder)
            bigip.selfip.delete(name=local_selfip_name,
                                folder=network_folder)
            deleted_names.add(local_selfip_name)

            self.bigip_l2_manager.delete_bigip_network(bigip, network)

            if subnet['id'] not in subnet_hints['do_not_delete_subnets']:
                subnet_hints['do_not_delete_subnets'].append(subnet['id'])

        return deleted_names

    def _assure_tenant_cleanup(self, service, all_subnet_hints):
        """ Delete tenant partition.
            Called for every bigip only in replication mode,
            otherwise called once.
        """
        for bigip in self._get_config_bigips():
            subnet_hints = all_subnet_hints[bigip.device_name]
            self._assure_bigip_tenant_cleanup(bigip, service, subnet_hints)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_bigip_tenant_cleanup(self, bigip, service, subnet_hints):
        """ if something was deleted check whether to do
            domain+folder teardown """
        tenant_id = service['pool']['tenant_id']
        if service['pool']['status'] == plugin_const.PENDING_DELETE or \
                len(subnet_hints['check_for_delete_subnets']) > 0:
            existing_monitors = bigip.monitor.get_monitors(folder=tenant_id)
            existing_pools = bigip.pool.get_pools(folder=tenant_id)
            existing_vips = bigip.virtual_server.get_virtual_service_insertion(
                folder=tenant_id)

            if not (existing_monitors or existing_pools or existing_vips):
                if self.conf.f5_sync_mode == 'replication':
                    self._remove_tenant_replication_mode(service, bigip)
                else:
                    self._remove_tenant_autosync_mode(service, bigip)

    def _remove_tenant_replication_mode(self, service, bigip):
        """ Remove tenant in replication sync-mode """
        tenant_id = service['pool']['tenant_id']
        bigip.route.delete_domain(folder=tenant_id)
        bigip.system.force_root_folder()
        bigip.system.delete_folder(folder=bigip.decorate_folder(tenant_id))

    def _remove_tenant_autosync_mode(self, service, bigip):
        """ Remove tenant in autosync sync-mode """
        # all domains must be gone before we attempt to delete
        # the folder or it won't delete due to not being empty
        folder = service['pool']['tenant_id']
        for set_bigip in self.get_all_bigips():
            set_bigip.route.delete_domain(folder=folder)
            set_bigip.system.force_root_folder()

        # we need to ensure that the following folder deletion
        # is clearly the last change that needs to be synced.
        self._sync_if_clustered()
        greenthread.sleep(5)
        bigip.system.delete_folder(
            folder=bigip.decorate_folder(folder))

        # Need to make sure this folder delete syncs before
        # something else runs and changes the current folder to
        # the folder being deleted which will cause big problems.
        self._sync_if_clustered()

    def _service_to_traffic_group(self, service):
        """ Hash service tenant id to index of traffic group """
        hexhash = hashlib.md5(service['pool']['tenant_id']).hexdigest()
        tg_index = int(hexhash, 16) % len(self.__traffic_groups)
        return self.__traffic_groups[tg_index]

    # deprecated, use _service_to_traffic_group
    def _service_to_tg_least_vips(self, vip_id):
        """ Return least loaded traffic group """
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
        """ Return least loaded traffic group """
        ret_traffic_group = 'traffic-group-1'
        lowest_count = 0
        for traffic_group in self.__gw_on_traffic_groups:
            if self.__gw_on_traffic_groups[traffic_group] <= lowest_count:
                ret_traffic_group = self.__gw_on_traffic_groups[traffic_group]
        return ret_traffic_group

    def get_bigip(self):
        """ Get one consistent big-ip """
        hostnames = sorted(self.__bigips)
        for i in range(len(hostnames)):
            try:
                bigip = self.__bigips[hostnames[i]]
                return bigip
            except urllib2.URLError:
                pass
        raise urllib2.URLError('cannot communicate to any bigips')

    def get_bigip_hosts(self):
        """ Get all big-ips hostnames under management """
        return self.__bigips

    def get_all_bigips(self):
        """ Get all big-ips under management """
        return self.__bigips.values()

    def _get_config_bigips(self):
        """ Return a list of big-ips that need to be configured.
            In replication sync mode, we configure all big-ips
            individually. In autosync mode we only use one big-ip
            and then sync the configuration to the other big-ips.
        """
        if self.conf.f5_sync_mode == 'replication':
            return self.get_all_bigips()
        else:
            return [self.get_bigip()]

    def init_traffic_groups(self, bigip):
        """ Count vips and gws on traffic groups """
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

    def _sync_if_clustered(self):
        """ sync device group if not in replication mode """
        if self.conf.f5_ha_type == 'standalone' or \
                self.conf.f5_sync_mode == 'replication' or \
                len(self.get_all_bigips()) < 2:
            return
        bigip = self.get_bigip()
        self._sync_with_retries(bigip)

    def _sync_with_retries(self, bigip, force_now=False,
                           attempts=4, retry_delay=130):
        """ sync device group """
        for attempt in range(1, attempts + 1):
            LOG.debug('Syncing Cluster... attempt %d of %d'
                      % (attempt, attempts))
            try:
                if attempt != 1:
                    force_now = False
                bigip.cluster.sync(bigip.device_group_name,
                                   force_now=force_now)
                LOG.debug('Cluster synced.')
                return
            except Exception as exp:
                LOG.error('ERROR: Cluster sync failed: %s' % exp)
                if attempt == attempts:
                    raise
                LOG.error('Wait another %d seconds for devices '
                          'to recover from failed sync.' % retry_delay)
                greenthread.sleep(retry_delay)


def _get_subnets_to_assure(service):
    """ Examine service and return active networks """
    networks = dict()
    if 'id' in service['vip'] and \
            not service['vip']['status'] == plugin_const.PENDING_DELETE:
        network = service['vip']['network']
        subnet = service['vip']['subnet']
        networks[network['id']] = SubnetInfo(network, subnet)

    for member in service['members']:
        if not member['status'] == plugin_const.PENDING_DELETE:
            network = member['network']
            subnet = member['subnet']
            networks[network['id']] = \
                SubnetInfo(network, subnet, is_for_member=True)
    return networks.values()


def check_monitor_delete(service):
    """If the pool is being deleted, then delete related objects"""
    if service['pool']['status'] == plugin_const.PENDING_DELETE:
        # Everything needs to be go with the pool, so overwrite
        # service state to appropriately remove all elements
        service['vip']['status'] = plugin_const.PENDING_DELETE
        for member in service['members']:
            member['status'] = plugin_const.PENDING_DELETE
        for monitor in service['pool']['health_monitors_status']:
            monitor['status'] = plugin_const.PENDING_DELETE


def _get_subnets_to_delete(bigip, service, subnet_hints):
    """ Clean up any Self IP, SNATs, networks, and folder for
        services items that we deleted. """
    subnets_to_delete = []
    for subnetinfo in subnet_hints['check_for_delete_subnets'].values():
        subnet = subnetinfo.subnet
        if not subnet:
            continue
        if not _ips_exist_on_subnet(bigip, service, subnet):
            subnets_to_delete.append(subnetinfo)
    return subnets_to_delete


def _ips_exist_on_subnet(bigip, service, subnet):
    """ Does the big-ip have any IP addresses on this subnet? """
    ipsubnet = netaddr.IPNetwork(subnet['cidr'])
    # Are there any virtual addresses on this subnet?
    get_vs = bigip.virtual_server.get_virtual_service_insertion
    virtual_services = get_vs(folder=service['pool']['tenant_id'])
    for virt_serv in virtual_services:
        (_, dest) = virt_serv.items()[0]
        if netaddr.IPAddress(dest['address']) in ipsubnet:
            return True

    # If there aren't any virtual addresses, are there
    # node addresses on this subnet?
    get_node_addr = bigip.pool.get_node_addresses
    nodes = get_node_addr(folder=service['pool']['tenant_id'])
    for node in nodes:
        if netaddr.IPAddress(node) in ipsubnet:
            return True

    # nothing found
    return False


class SubnetInfo(object):
    """ A structure used to store a network-subnet combo """
    def __init__(self, network=None, subnet=None,
                 is_for_member=False):
        self.network = network
        self.subnet = subnet
        self.is_for_member = is_for_member


def _validate_bigip_version(bigip, hostname):
    """ Ensure the BIG-IP has sufficient version """
    major_version = bigip.system.get_major_version()
    if major_version < f5const.MIN_TMOS_MAJOR_VERSION:
        raise f5ex.MajorVersionValidateFailed(
            'Device %s must be at least TMOS %s.%s'
            % (hostname, f5const.MIN_TMOS_MAJOR_VERSION,
               f5const.MIN_TMOS_MINOR_VERSION))
    minor_version = bigip.system.get_minor_version()
    if minor_version < f5const.MIN_TMOS_MINOR_VERSION:
        raise f5ex.MinorVersionValidateFailed(
            'Device %s must be at least TMOS %s.%s'
            % (hostname, f5const.MIN_TMOS_MAJOR_VERSION,
               f5const.MIN_TMOS_MINOR_VERSION))
    return major_version, minor_version


def _update_http_monitor(bigip, monitor):
    """ Update pool monitor on bigip """
    if 'url_path' in monitor:
        send_text = "GET " + monitor['url_path'] + \
            " HTTP/1.0\\r\\n\\r\\n"
    else:
        send_text = "GET / HTTP/1.0\\r\\n\\r\\n"

    if 'expected_codes' in monitor:
        try:
            if monitor['expected_codes'].find(",") > 0:
                status_codes = monitor['expected_codes'].split(',')
                recv_text = "HTTP/1.(0|1) ("
                for status in status_codes:
                    int(status)
                    recv_text += status + "|"
                recv_text = recv_text[:-1]
                recv_text += ")"
            elif monitor['expected_codes'].find("-") > 0:
                status_range = monitor['expected_codes'].split('-')
                start_range = status_range[0]
                int(start_range)
                stop_range = status_range[1]
                int(stop_range)
                recv_text = "HTTP/1.(0|1) [" + \
                    start_range + "-" + \
                    stop_range + "]"
            else:
                int(monitor['expected_codes'])
                recv_text = "HTTP/1.(0|1) " + monitor['expected_codes']
        except Exception as exp:
            LOG.error(_(
                "invalid monitor: %s, expected_codes %s, setting to 200"
                % (exp, monitor['expected_codes'])))
            recv_text = "HTTP/1.(0|1) 200"
    else:
        recv_text = "HTTP/1.(0|1) 200"

    LOG.debug('setting monitor send: %s, receive: %s' % (send_text, recv_text))

    bigip.monitor.set_send_string(name=monitor['id'],
                                  mon_type=monitor['type'],
                                  send_text=send_text,
                                  folder=monitor['tenant_id'])
    bigip.monitor.set_recv_string(name=monitor['id'],
                                  mon_type=monitor['type'],
                                  recv_text=recv_text,
                                  folder=monitor['tenant_id'])

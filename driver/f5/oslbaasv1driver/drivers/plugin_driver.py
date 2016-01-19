""" F5 LBaaS Driver """
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

import uuid
import netaddr
import datetime

from time import time
from oslo.config import cfg  # @UnresolvedImport

from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.plugins.common import constants
from neutron.common import rpc as q_rpc
from neutron.db import agents_db
from neutron.context import get_admin_context
from neutron.extensions import portbindings
from neutron.common import log
import f5.oslbaasv1driver.drivers.constants as lbaasv1constants

PREJUNO = False
PREKILO = False
try:
    from neutron.services.loadbalancer.drivers.abstract_driver \
        import LoadBalancerAbstractDriver  # @UnresolvedImport @Reimport
    from neutron.extensions \
        import lbaas_agentscheduler  # @UnresolvedImport @Reimport
    from neutron.db.loadbalancer import loadbalancer_db as lb_db
    from neutron.openstack.common import log as logging
    from neutron.openstack.common import importutils
    from neutron.extensions.loadbalancer \
        import MemberNotFound  # @UnresolvedImport @Reimport
    from neutron.extensions.loadbalancer \
        import PoolNotFound  # @UnresolvedImport @Reimport
    from neutron.extensions.loadbalancer \
        import VipNotFound  # @UnresolvedImport @Reimport
    from neutron.extensions.loadbalancer \
        import HealthMonitorNotFound  # @UnresolvedImport @Reimport
    PREKILO = True
    try:
        from neutron.openstack.common import rpc
        from neutron.openstack.common.rpc import proxy
        PREJUNO = True
    except ImportError:
        from neutron.common import rpc as proxy
except ImportError:
    # Kilo
    from neutron_lbaas.services.loadbalancer.drivers.abstract_driver \
        import LoadBalancerAbstractDriver  # @UnresolvedImport @Reimport
    from neutron_lbaas.extensions \
        import lbaas_agentscheduler  # @UnresolvedImport @Reimport
    from neutron_lbaas.db.loadbalancer import loadbalancer_db as lb_db
    from oslo_log import log as logging
    from oslo_utils import importutils
    from neutron_lbaas.extensions.loadbalancer \
        import MemberNotFound  # @UnresolvedImport @Reimport
    from neutron_lbaas.extensions.loadbalancer \
        import PoolNotFound  # @UnresolvedImport @Reimport
    from neutron_lbaas.extensions.loadbalancer \
        import VipNotFound  # @UnresolvedImport @Reimport
    from neutron_lbaas.extensions.loadbalancer \
        import HealthMonitorNotFound  # @UnresolvedImport @Reimport
    import f5.oslbaasv1driver.drivers.rpc as proxy

LOG = logging.getLogger(__name__)

__VERSION__ = '0.1.1'

ACTIVE_PENDING = (
    constants.ACTIVE,
    constants.PENDING_CREATE,
    constants.PENDING_UPDATE,
    constants.PENDING_DELETE,
    constants.ERROR
)

OPTS = [
    cfg.StrOpt('f5_loadbalancer_pool_scheduler_driver',
               default=('f5.oslbaasv1driver'
                        '.drivers.agent_scheduler'
                        '.TenantScheduler'),
               help=_('Driver to use for scheduling '
                      'pool to a default loadbalancer agent'))
]

cfg.CONF.register_opts(OPTS)

VIF_TYPE = 'f5'
NET_CACHE_SECONDS = 1800


class LoadBalancerCallbacks(object):
    """Callbacks made by the agent to update the data model."""
    RPC_API_VERSION = '1.0'

    def __init__(self, plugin, env, scheduler):
        LOG.debug('LoadBalancerCallbacks RPC subscriber initialized')
        self.plugin = plugin
        self.env = env
        self.scheduler = scheduler
        self.net_cache = {}
        self.subnet_cache = {}

        self.last_cache_update = datetime.datetime.now()

    def _core_plugin(self):
        """ Get the core plugin """
        return self.plugin._core_plugin

    @log.log
    def get_all_pools(self, context, env=None, group=0, host=None):
        """ Get all pools for this group in this env"""
        with context.session.begin(subtransactions=True):
            if not host:
                return []
            agents = self.scheduler.get_agents_in_env(self.plugin,
                                                      context,
                                                      env,
                                                      group)
            if not agents:
                return []

            # get all pools associated with this agents in this
            # env + group a build a set of known ACTIVE pools
            # to return
            pool_ids = []
            for agent in agents:
                agent_pools = self.plugin.list_pools_on_lbaas_agent(
                    context,
                    agent.id
                )
                for pool in agent_pools['pools']:
                    pool_ids.append(
                        {
                         'agent_host': agent['host'],
                         'pool_id': pool['id'],
                         'tenant_id': pool['tenant_id']
                        }
                    )
            return pool_ids

    @log.log
    def get_active_pools(self, context, env=None, group=0, host=None):
        """ Get pools that are active for this group in this env"""
        with context.session.begin(subtransactions=True):
            if not host:
                return []
            agents = self.scheduler.get_agents_in_env(self.plugin,
                                                      context,
                                                      env,
                                                      group)
            if not agents:
                return []

            # get all pools associated with this agents in this
            # env + group a build a set of known ACTIVE pools
            # to return
            pool_ids = []
            for agent in agents:
                agent_pools = self.plugin.list_pools_on_lbaas_agent(
                    context,
                    agent.id
                )
                for pool in agent_pools['pools']:
                    if pool['status'] == constants.ACTIVE:
                        # add agent reference
                        pool_ids.append(
                            {
                             'agent_host': agent['host'],
                             'pool_id': pool['id'],
                             'tenant_id': pool['tenant_id']
                            }
                        )
            return pool_ids

    @log.log
    def get_pending_pools(self, context, env=None, group=0, host=None):
        """ Get pools that have pending task for this group in this env"""
        with context.session.begin(subtransactions=True):
            if not host:
                return []
            agents = self.scheduler.get_agents_in_env(self.plugin,
                                                      context,
                                                      env,
                                                      group)
            if not agents:
                return []

            pool_ids_by_agent_host = {}
            pools_to_update = []

            # get all pools associated with this agents in this
            # env + group, build a filter list of pool_ids and
            # a set of known non-ACTIVE pools
            for agent in agents:
                agent_pools = self.plugin.list_pools_on_lbaas_agent(
                    context,
                    agent.id
                )
                for pool in agent_pools['pools']:
                    # add this to our filter list to query
                    # VIPS and Members
                    if agent['host'] not in pool_ids_by_agent_host:
                        pool_ids_by_agent_host[agent['host']] = []
                    pool_ids_by_agent_host[agent['host']].append(pool['id'])
                    # can we tell if this pool needs updates
                    # just from the pool or health monitor
                    # status already?
                    if pool['status'] != constants.ACTIVE:
                        pools_to_update.append(
                            {
                             'agent_host': agent['host'],
                             'pool_id': pool['id'],
                             'tenant_id': pool['tenant_id']
                            }
                        )
                    for hms in pool['health_monitors_status']:
                        if hms['status'] != constants.ACTIVE:
                            pools_to_update.append(
                                {
                                 'agent_host': agent['host'],
                                 'pool_id': pool['id'],
                                 'tenant_id': pool['tenant_id']
                                }
                            )
            for agent_host in pool_ids_by_agent_host.keys():
                pool_ids = pool_ids_by_agent_host[agent_host]
                # get vips associated with pools which are not active
                vips = self.plugin.get_vips(
                    context,
                    filters={'pool_id': pool_ids, },
                    fields=['id', 'pool_id', 'status']
                )
                for vip in vips:
                    if vip['status'] != constants.ACTIVE:
                        pools_to_update.append(
                            {
                             'agent_host': agent_host,
                             'pool_id': pool['id']
                            }
                        )
                members = self.plugin.get_members(
                    context,
                    filters={'pool_id': pool_ids, },
                    fields=['id', 'pool_id', 'status']
                )
                for member in members:
                    if member['status'] != constants.ACTIVE:
                        pools_to_update.append(
                            {
                             'agent_host': agent_host,
                             'pool_id': pool['id']
                            }
                        )

            return pools_to_update

    @log.log
    def get_service_by_pool_id(
            self, context, pool_id=None, global_routed_mode=False, host=None):
        """ Get full service definition from pool id """
        # invalidate cache if it is too old
        if (datetime.datetime.now() - self.last_cache_update).seconds \
                > NET_CACHE_SECONDS:
            self.net_cache = {}
            self.subnet_cache = {}

        service = {}
        with context.session.begin(subtransactions=True):
            LOG.debug(_('Building service definition entry for %s' % pool_id))

            # populate pool
            pool = self._get_extended_pool(
                context, pool_id, global_routed_mode)
            service['pool'] = pool
            if not pool:
                LOG.debug(_('Built pool %s service: %s' % (pool_id, service)))
                return service
            # populate pool members
            adminctx = get_admin_context()
            if 'members' not in pool or len(pool['members']) == 0:
                pool['members'] = []
            service['members'] = []
            for member_id in pool['members']:
                try:
                    member = self.plugin.get_member(context, member_id)
                    member['network'] = None
                    member['subnet'] = None
                    member['port'] = None
                    if not global_routed_mode:
                        self._extend_member(
                            adminctx, context, pool, member)
                    service['members'].append(member)
                except MemberNotFound:
                    LOG.error("get_service_by_pool_id: Member not found %s" %
                              member_id)

            # populate health monitors
            service['health_monitors'] = []
            for health_mon in service['pool']['health_monitors']:
                service['health_monitors'].append(
                    self.plugin.get_health_monitor(context, health_mon)
                )

            # populate vip
            service['vip'] = self._get_extended_vip(
                context, pool, global_routed_mode)

        LOG.debug(_('Built pool %s service: %s' % (pool_id, service)))
        return service

    def _get_extended_pool(self, context, pool_id, global_routed_mode):
        """ Get Pool from Neutron and add extended data """
        # Start with neutron pool definition
        try:
            pool = self.plugin.get_pool(context, pool_id)
        except:
            LOG.error("get_service_by_pool_id: Pool not found %s" %
                      pool_id)
            return None

        # Populate extended pool attributes
        if not global_routed_mode:
            pool['subnet'] = self._get_subnet_cached(
                context, pool['subnet_id'])
            pool['network'] = self._get_network_cached(
                context, pool['subnet']['network_id'])
        else:
            pool['subnet_id'] = None
            pool['network'] = None

        return pool

    def _get_subnet_cached(self, context, subnet_id):
        """ subnet from cache or get from neutron """
        if subnet_id not in self.subnet_cache:
            subnet_dict = self._core_plugin().get_subnet(context, subnet_id)
            self.subnet_cache[subnet_id] = subnet_dict
        return self.subnet_cache[subnet_id]

    def _get_network_cached(self, context, network_id):
        """ network from cache or get from neutron """
        if network_id not in self.net_cache:
            net_dict = self._core_plugin().get_network(context, network_id)
            if 'provider:network_type' not in net_dict:
                net_dict['provider:network_type'] = 'undefined'
            if 'provider:segmentation_id' not in net_dict:
                net_dict['provider:segmentation_id'] = 0
            self.net_cache[network_id] = net_dict
        return self.net_cache[network_id]

    def _get_extended_vip(self, context, pool, global_routed_mode):
        """ add network data to vip """
        if 'vip_id' not in pool or not pool['vip_id']:
            return {'port': {'network': None, 'subnet': None}}

        vip = self.plugin.get_vip(context, pool['vip_id'])
        if global_routed_mode:
            vip['network'] = None
            vip['subnet'] = None
            vip['port'] = {}
            vip['port']['network'] = None
            vip['port']['subnet'] = None
            return vip

        vip['port'] = self._core_plugin().get_port(context, vip['port_id'])
        vip['network'] = self._get_network_cached(
            context, vip['port']['network_id'])
        self._populate_vip_network_vteps(context, vip)

        # there should only be one fixed_ip
        for fixed_ip in vip['port']['fixed_ips']:
            vip['subnet'] = self._core_plugin().get_subnet(
                context, fixed_ip['subnet_id'])
            vip['address'] = fixed_ip['ip_address']

        return vip

    def _populate_vip_network_vteps(self, context, vip):
        """ put related tunnel endpoints in vip definiton """
        vip['vxlan_vteps'] = []
        vip['gre_vteps'] = []
        if 'provider:network_type' not in vip['network']:
            return

        nettype = vip['network']['provider:network_type']
        if nettype not in ['vxlan', 'gre']:
            return

        ports = self.get_ports_on_network(context,
                                          network_id=vip['network']['id'])
        vtep_hosts = []
        for port in ports:
            if 'binding:host_id' in port and \
               port['binding:host_id'] not in vtep_hosts:
                vtep_hosts.append(port['binding:host_id'])
        for vtep_host in vtep_hosts:
            if nettype == 'vxlan':
                endpoints = self._get_vxlan_endpoints(context, vtep_host)
                for ep in endpoints:
                    if ep not in vip['vxlan_vteps']:
                        vip['vxlan_vteps'].append(ep)
            elif nettype == 'gre':
                endpoints = self._get_gre_endpoints(context, vtep_host)
                for ep in endpoints:
                    if ep not in vip['gre_vteps']:
                        vip['gre_vteps'].append(ep)

    def _extend_member(
            self, adminctx, context, pool, member):
        """ Add networking info to member """

        from neutron.db import models_v2 as core_db
        alloc_qry = adminctx.session.query(core_db.IPAllocation)
        allocated = alloc_qry.filter_by(ip_address=member['address']).all()

        # try populating member from pool subnet
        matching_keys = {'tenant_id': pool['tenant_id'],
                         'subnet_id': pool['subnet_id'],
                         'shared': None}

        if self._found_and_used_matching_addr(
                adminctx, context, member, allocated, matching_keys):
            return

        # try populating member from any tenant subnet
        matching_keys['subnet_id'] = None
        if self._found_and_used_matching_addr(
                adminctx, context, member, allocated, matching_keys):
            return

        # try populating member net from any shared subnet
        matching_keys['tenant_id'] = None
        matching_keys['shared'] = True
        if self._found_and_used_matching_addr(
                adminctx, context, member, allocated, matching_keys):
            return

    def _found_and_used_matching_addr(
            self, adminctx, context, member, allocated, matching_keys):
        """ Find a matching address that matches keys """

        # first check list of allocated addresses in neutron
        # that match the pool member and check those subnets
        # first because we prefer to use a subnet that actually has
        # a matching ip address on it.
        if self._found_and_used_neutron_addr(
                adminctx, context, member, allocated, matching_keys):
            return True

        # Perhaps the neutron network was deleted but the pool member
        # was not. If we find a cached subnet definition that matches the
        # deleted network it might help us tear down our configuration.
        if self._found_and_used_cached_subnet(
                adminctx, member, matching_keys):
            return True

        # Perhaps the neutron subnet was deleted but the pool member
        # was not. Maybe the subnet was deleted and then added back
        # with a different id. If we can find a matching subnet, it
        # might help us tear down our configuration.
        if self._found_and_used_neutron_subnet(
                adminctx, member, matching_keys):
            return True

        return False

    def _found_and_used_neutron_addr(
            self, adminctx, context, member, allocated, matching_keys):
        """ Find a matching address that matches keys """

        for alloc in allocated:
            if matching_keys['subnet_id'] and \
                    alloc['subnet_id'] != matching_keys['subnet_id']:
                continue

            try:
                net = self._get_network_cached(adminctx, alloc['network_id'])
            except:
                continue
            if matching_keys['tenant_id'] and \
                    net['tenant_id'] != matching_keys['tenant_id']:
                continue
            if matching_keys['shared'] and not net['shared']:
                continue

            member['network'] = net
            member['subnet'] = self._get_subnet_cached(
                context, alloc['subnet_id'])

            member['port'] = self._core_plugin().get_port(
                adminctx, alloc['port_id'])
            self._populate_member_network(context, member)
            return True

    def _found_and_used_cached_subnet(
            self, adminctx, member, matching_keys):
        """ check our cache for missing network """
        subnets_matched = []
        na_add = netaddr.IPAddress(member['address'])
        for subnet in self.subnet_cache:
            c_subnet = self.subnet_cache[subnet]
            na_net = netaddr.IPNetwork(c_subnet['cidr'])
            if na_add in na_net:
                if matching_keys['subnet_id'] and \
                        c_subnet['id'] != matching_keys['subnet_id']:
                    continue
                if matching_keys['tenant_id'] and \
                        c_subnet['tenant_id'] != matching_keys['tenant_id']:
                    continue
                if matching_keys['shared'] and not c_subnet['shared']:
                    continue
                subnets_matched.append(subnet)
        if len(subnets_matched) == 1:
            member['subnet'] = self._get_subnet_cached(
                adminctx, subnets_matched[0])
            member['network'] = self._get_network_cached(
                adminctx, member['subnet']['network_id'])
            return True
        return False

    def _found_and_used_neutron_subnet(
            self, adminctx, member, matching_keys):
        """ check neutron for matching network """

        na_add = netaddr.IPAddress(member['address'])

        subnets_matched = []
        for subnet in self._core_plugin()._get_all_subnets(adminctx):
            subnet_dict = self._core_plugin()._make_subnet_dict(subnet)
            self.subnet_cache[subnet_dict['id']] = subnet_dict
            na_net = netaddr.IPNetwork(subnet_dict['cidr'])
            if na_add in na_net:
                if matching_keys['subnet_id'] and \
                        subnet_dict['id'] != \
                        matching_keys['subnet_id']:
                    continue
                if matching_keys['tenant_id'] and \
                        subnet_dict['tenant_id'] != \
                        matching_keys['tenant_id']:
                    continue
                if matching_keys['shared'] and not subnet_dict['shared']:
                    continue
                subnets_matched.append(subnet_dict)
        if len(subnets_matched) == 1:
            LOG.debug(_('%s in subnet %s in cache'
                        % (member['address'],
                           subnets_matched[0]['id'])))
            member['subnet'] = subnets_matched[0]
            member['network'] = self._get_network_cached(
                adminctx, member['subnet']['network_id'])

    def _populate_member_network(self, context, member):
        """ Add networking info to pool member """
        member['vxlan_vteps'] = []
        member['gre_vteps'] = []
        if 'provider:network_type' in member['network']:
            nettype = member['network']['provider:network_type']
            if nettype == 'vxlan':
                if 'binding:host_id' in member['port']:
                    host = member['port']['binding:host_id']
                    member['vxlan_vteps'] = self._get_vxlan_endpoints(
                        context, host)
            if nettype == 'gre':
                if 'binding:host_id' in member['port']:
                    host = member['port']['binding:host_id']
                    member['gre_vteps'] = self._get_gre_endpoints(
                        context, host)
        if 'provider:network_type' not in member['network']:
            member['network']['provider:network_type'] = 'undefined'
        if 'provider:segmentation_id' not in member['network']:
            member['network']['provider:segmentation_id'] = 0

    @log.log
    def create_network(self, context, tenant_id=None, name=None, shared=False,
                       admin_state_up=True, network_type=None,
                       physical_network=None, segmentation_id=None):
        """ Create neutron network """
        network_data = {
            'tenant_id': tenant_id,
            'name': name,
            'admin_state_up': admin_state_up,
            'shared': shared
        }
        if network_type:
            network_data['provider:network_type'] = network_type
        if physical_network:
            network_data['provider:physical_network'] = physical_network
        if segmentation_id:
            network_data['provider:segmentation_id'] = segmentation_id
        return self._core_plugin().create_network(
            context, {'network': network_data})

    @log.log
    def delete_network(self, context, network_id):
        """ Delete neutron network """
        self._core_plugin().delete_network(context, network_id)

    @log.log
    def create_subnet(self, context, tenant_id=None, network_id=None,
                      name=None, shared=False, cidr=None, enable_dhcp=False,
                      gateway_ip=None, allocation_pools=None,
                      dns_nameservers=None, host_routes=None):
        """ Create neutron subnet """
        subnet_data = {'tenant_id': tenant_id,
                       'network_id': network_id,
                       'name': name,
                       'shared': shared,
                       'enable_dhcp': enable_dhcp}
        subnet_data['cidr'] = cidr
        if gateway_ip:
            subnet_data['gateway_ip'] = gateway_ip
        if allocation_pools:
            subnet_data['allocation_pools'] = allocation_pools
        if dns_nameservers:
            subnet_data['dns_nameservers'] = dns_nameservers
        if host_routes:
            subnet_data['host_routes'] = host_routes
        return self._core_plugin().create_subnet(
            context,
            {'subenet': subnet_data}
        )

    @log.log
    def delete_subnet(self, context, subnet_id):
        """ Delete neutron subnet """
        self._core_plugin().delete_subnet(context, subnet_id)

    @log.log
    def get_ports_for_mac_addresses(self, context, mac_addresses=None):
        """ Get ports for mac addresses """
        if not isinstance(mac_addresses, list):
            mac_addresses = [mac_addresses]
        filters = {'mac_address': mac_addresses}
        return self._core_plugin().get_ports(
            context,
            filters=filters
        )

    @log.log
    def get_ports_on_network(self, context, network_id=None):
        """ Get ports for mac addresses """
        if not isinstance(network_id, list):
            network_ids = [network_id]
        filters = {'network_id': network_ids}
        return self._core_plugin().get_ports(
            context,
            filters=filters
        )

    @log.log
    def create_port_on_subnet(self, context, subnet_id=None,
                              mac_address=None, name=None,
                              fixed_address_count=1, host=None):
        """ Create port on subnet """
        if subnet_id:
            subnet = self._core_plugin().get_subnet(context, subnet_id)
            if not mac_address:
                mac_address = attributes.ATTR_NOT_SPECIFIED
            fixed_ip = {'subnet_id': subnet['id']}
            if fixed_address_count > 1:
                fixed_ips = []
                for _ in range(0, fixed_address_count):
                    fixed_ips.append(fixed_ip)
            else:
                fixed_ips = [fixed_ip]
            if not host:
                host = ''
            if not name:
                name = ''
            port_data = {
                'tenant_id': subnet['tenant_id'],
                'name': name,
                'network_id': subnet['network_id'],
                'mac_address': mac_address,
                'admin_state_up': True,
                'device_id': str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host))),
                'device_owner': 'network:f5lbaas',
                'status': q_const.PORT_STATUS_ACTIVE,
                'fixed_ips': fixed_ips
            }
            port_data[portbindings.HOST_ID] = host
            port_data[portbindings.VIF_TYPE] = VIF_TYPE
            if 'binding:capabilities' in \
                    portbindings.EXTENDED_ATTRIBUTES_2_0['ports']:
                port_data['binding:capabilities'] = {'port_filter': False}
            port = self._core_plugin().create_port(
                context, {'port': port_data})
            # Because ML2 marks ports DOWN by default on creation
            update_data = {
                'status': q_const.PORT_STATUS_ACTIVE
            }
            self._core_plugin().update_port(
                context, port['id'], {'port': update_data})
            return port

    @log.log
    def create_port_on_subnet_with_specific_ip(self, context, subnet_id=None,
                                               mac_address=None, name=None,
                                               ip_address=None, host=None):
        """ Create port on subnet with specific ip address """
        if subnet_id and ip_address:
            subnet = self._core_plugin().get_subnet(context, subnet_id)
            if not mac_address:
                mac_address = attributes.ATTR_NOT_SPECIFIED
            fixed_ip = {'subnet_id': subnet['id'], 'ip_address': ip_address}
            if not host:
                host = ''
            if not name:
                name = ''
            port_data = {
                'tenant_id': subnet['tenant_id'],
                'name': name,
                'network_id': subnet['network_id'],
                'mac_address': mac_address,
                'admin_state_up': True,
                'device_id': str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host))),
                'device_owner': 'network:f5lbaas',
                'status': q_const.PORT_STATUS_ACTIVE,
                'fixed_ips': [fixed_ip]
            }
            port_data[portbindings.HOST_ID] = host
            port_data[portbindings.VIF_TYPE] = 'f5'
            if 'binding:capabilities' in \
                    portbindings.EXTENDED_ATTRIBUTES_2_0['ports']:
                port_data['binding:capabilities'] = {'port_filter': False}
            port = self._core_plugin().create_port(
                context, {'port': port_data})
            # Because ML2 marks ports DOWN by default on creation
            update_data = {
                'status': q_const.PORT_STATUS_ACTIVE
            }
            self._core_plugin().update_port(
                context, port['id'], {'port': update_data})
            return port

    @log.log
    def get_port_by_name(self, context, port_name=None):
        """ Get port by name """
        if port_name:
            filters = {'name': [port_name]}
            return self._core_plugin().get_ports(
                context,
                filters=filters
            )

    @log.log
    def delete_port(self, context, port_id=None, mac_address=None):
        """ Delete port """
        if port_id:
            self._core_plugin().delete_port(context, port_id)
        elif mac_address:
            filters = {'mac_address': [mac_address]}
            ports = self._core_plugin().get_ports(context, filters=filters)
            for port in ports:
                self._core_plugin().delete_port(context, port['id'])

    @log.log
    def delete_port_by_name(self, context, port_name=None):
        """ Delete port by name """
        if port_name:
            filters = {'name': [port_name]}
            ports = self._core_plugin().get_ports(context, filters=filters)
            for port in ports:
                self._core_plugin().delete_port(context, port['id'])

    @log.log
    def allocate_fixed_address_on_subnet(self, context, subnet_id=None,
                                         port_id=None, name=None,
                                         fixed_address_count=1, host=None):
        """ Allocate a fixed ip address on subnet """
        if subnet_id:
            subnet = self._core_plugin().get_subnet(context, subnet_id)
            if not port_id:
                port = self.create_port_on_subnet(
                    context,
                    subnet_id=subnet_id,
                    mac_address=None,
                    name=name,
                    fixed_address_count=fixed_address_count,
                    host=host
                )
            else:
                port = self._core_plugin().get_port(context, port_id)
                existing_fixed_ips = port['fixed_ips']
                fixed_ip = {'subnet_id': subnet['id']}
                if fixed_address_count > 1:
                    fixed_ips = []
                    for _ in range(0, fixed_address_count):
                        fixed_ips.append(fixed_ip)
                else:
                    fixed_ips = [fixed_ip]
            port['fixed_ips'] = existing_fixed_ips + fixed_ips
            port = self._core_plugin().update_port(context, {'port': port})
            new_fixed_ips = port['fixed_ips']
            port['new_fixed_ips'] = []
            for new_fixed_ip in new_fixed_ips:
                ip_address = new_fixed_ip['ip_address']
                is_new = True
                for existing_fixed_ip in existing_fixed_ips:
                    if ip_address == existing_fixed_ip['ip_address']:
                        is_new = False
                if is_new:
                    port['new_fixed_ips'].append(new_fixed_ip)
            return port

    @log.log
    def allocate_specific_fixed_address_on_subnet(self, context,
                                                  subnet_id=None,
                                                  port_id=None, name=None,
                                                  ip_address=None,
                                                  host=None):
        """ Allocate specific fixed ip address on subnet """
        if subnet_id and ip_address:
            subnet = self._core_plugin().get_subnet(context, subnet_id)
            if not port_id:
                port = self.create_port_on_subnet_with_specific_ip(
                    context,
                    subnet_id=subnet_id,
                    mac_address=None,
                    name=name,
                    ip_address=ip_address,
                    host=host
                )
            else:
                port = self._core_plugin().get_port(context, port_id)
                existing_fixed_ips = port['fixed_ips']
                fixed_ip = {'subnet_id': subnet['id'],
                            'ip_address': ip_address}
            port['fixed_ips'] = existing_fixed_ips + [fixed_ip]
            port = self._core_plugin().update_port(context, {'port': port})
            return port

    @log.log
    def deallocate_fixed_address_on_subnet(self, context, fixed_addresses=None,
                                           subnet_id=None, host=None,
                                           auto_delete_port=False):
        """ Allocate fixed ip address on subnet """
        if fixed_addresses:
            if not isinstance(fixed_addresses, list):
                fixed_addresses = [fixed_addresses]
            # strip all route domain decorations if they exist
            for i in range(len(fixed_addresses)):
                try:
                    decorator_index = str(fixed_addresses[i]).index('%')
                    fixed_addresses[i] = fixed_addresses[i][:decorator_index]
                except:
                    pass
            subnet = self._core_plugin().get_subnet(context, subnet_id)
            # get all ports for this host on the subnet
            filters = {
                'network_id': [subnet['network_id']],
                'tenant_id': [subnet['tenant_id']],
                'device_id': [str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host)))]
            }
            ports = self._core_plugin().get_ports(context, filters=filters)
            fixed_ips = {}
            ok_to_delete_port = {}
            for port in ports:
                ok_to_delete_port[port['id']] = False
                for fixed_ip in port['fixed_ips']:
                    fixed_ips[fixed_ip['ip_address']] = port['id']
            # only get rid of associated fixed_ips
            for fixed_ip in fixed_ips:
                if fixed_ip in fixed_addresses:
                    self._core_plugin()._delete_ip_allocation(
                        context,
                        subnet['network_id'],
                        subnet_id,
                        fixed_ip
                    )
                    ok_to_delete_port[fixed_ips[fixed_ip]] = True
                else:
                    ok_to_delete_port[fixed_ips[fixed_ip]] = False
            if auto_delete_port:
                for port in ok_to_delete_port:
                    if ok_to_delete_port[port]:
                        self.delete_port(context, port)

    @log.log
    def add_allowed_address(self, context, port_id=None, ip_address=None):
        """ Add allowed addresss """
        if port_id and ip_address:
            try:
                port = self._core_plugin().get_port(
                    context=context, id=port_id)
                address_pairs = []
                if 'allowed_address_pairs' in port:
                    for aap in port['allowed_address_pairs']:
                        if aap['ip_address'] == ip_address and \
                                aap['mac_address'] == port['mac_address']:
                            return True
                        address_pairs.append(aap)
                address_pairs.append(
                    {
                        'ip_address': ip_address,
                        'mac_address': port['mac_address']
                    }
                )
                port = {'port': {'allowed_address_pairs': address_pairs}}
                self._core_plugin().update_port(context, port_id, port)
            except Exception as exc:
                LOG.error('could not add allowed address pair: %s'
                          % exc.message)

    @log.log
    def remove_allowed_address(self, context, port_id=None, ip_address=None):
        """ Remove allowed addresss """
        if port_id and ip_address:
            try:
                port = self._core_plugin().get_port(
                    context=context, id=port_id)
                address_pairs = []
                if 'allowed_address_pairs' in port:
                    for aap in port['allowed_address_pairs']:
                        if aap['ip_address'] == ip_address and \
                                aap['mac_address'] == port['mac_address']:
                            continue
                        address_pairs.append(aap)
                port = {'port': {'allowed_address_pairs': address_pairs}}
                self._core_plugin().update_port(context, port_id, port)
            except Exception as exc:
                LOG.error('could not add allowed address pair: %s'
                          % exc.message)

    @log.log
    def update_vip_status(self, context, vip_id=None,
                          status=constants.ERROR,
                          status_description=None,
                          host=None):
        """Agent confirmation hook to update VIP status."""
        try:
            vip = self.plugin.get_vip(context, vip_id)
            if vip['status'] == constants.PENDING_DELETE:
                status = constants.PENDING_DELETE
            self.plugin.update_status(
                context,
                lb_db.Vip,
                vip_id,
                status,
                status_description
            )
        except VipNotFound:
            pass

    @log.log
    def vip_destroyed(self, context, vip_id=None, host=None):
        """Agent confirmation hook that a pool has been destroyed."""
        # delete the vip from the data model
        self.plugin._delete_db_vip(context, vip_id)

    @log.log
    def update_pool_status(self, context, pool_id=None,
                           status=constants.ERROR, status_description=None,
                           host=None):
        """Agent confirmation hook to update pool status."""
        try:
            pool = self.plugin.get_pool(context, pool_id)
            if pool['status'] == constants.PENDING_DELETE:
                LOG.debug('Pool status is PENDING_DELETE. '
                          'Pool status was not updated. %s' % pool)
                return
            self.plugin.update_status(
                context,
                lb_db.Pool,
                pool_id,
                status,
                status_description
            )
        except PoolNotFound:
            pass

    @log.log
    def pool_destroyed(self, context, pool_id=None, host=None):
        """Agent confirmation hook that a pool has been destroyed."""
        # delete the pool from the data model
        self.plugin._delete_db_pool(context, pool_id)

    @log.log
    def update_member_status(self, context, member_id=None,
                             status=constants.ERROR, status_description=None,
                             host=None):
        """Agent confirmation hook to update member status."""
        try:
            member = self.plugin.get_member(context, member_id)
            if member['status'] == constants.PENDING_DELETE:
                status = constants.PENDING_DELETE
            self.plugin.update_status(
                context,
                lb_db.Member,
                member_id,
                status,
                status_description
            )
        except MemberNotFound:
            pass

    @log.log
    def member_destroyed(self, context, member_id=None, host=None):
        """Agent confirmation hook that a member has been destroyed."""
        # delete the pool member from the data model
        try:
            self.plugin._delete_db_member(context, member_id)
        except MemberNotFound:
            pass

    @log.log
    def update_health_monitor_status(self, context, pool_id=None,
                                     health_monitor_id=None,
                                     status=constants.ERROR,
                                     status_description=None,
                                     host=None):
        """Agent confirmation hook to update healthmonitor status."""
        try:
            assoc = self.plugin._get_pool_health_monitor(
                context, health_monitor_id, pool_id)
            status = getattr(assoc, 'status', None)
            if status == constants.PENDING_DELETE:
                LOG.error("Attempt to update deleted health monitor %s" %
                          health_monitor_id)
                return
            self.plugin.update_pool_health_monitor(
                context,
                health_monitor_id,
                pool_id,
                status,
                status_description
            )
        except HealthMonitorNotFound:
            pass

    @log.log
    def health_monitor_destroyed(self, context, health_monitor_id=None,
                                 pool_id=None, host=None):
        """Agent confirmation hook that a health has been destroyed."""
        # delete the health monitor from the data model
        # the plug-in does this sometimes so allow for an error.
        try:
            self.plugin._delete_db_pool_health_monitor(
                context,
                health_monitor_id,
                pool_id
            )
        except:
            pass

    @log.log
    def update_pool_stats(self, context, pool_id=None, stats=None, host=None):
        """ Update pool stats """
        try:
            # Check if pool is in a PENDING_DELETE state. Do not update stats.
            pool = self.plugin.get_pool(context, pool_id)
            if pool['status'] == 'PENDING_DELETE':
                LOG.debug('Pool status is PENDING_DELETE. '
                          'Pool stats were not updated. %s' % pool)
                return

            # Remove any pool members that are in a PENDING_DELETE state
            # from the stats pool member list.
            members = self.plugin.get_members(
                context,
                filters={'pool_id': [pool_id], },
                fields=['id', 'pool_id', 'status']
            )
            for member in members:
                if member['status'] == 'PENDING_DELETE':
                    LOG.debug('Member status is PENDING_DELETE. Remove from '
                              'stats member list (when present):%s' % member)
                    if member['id'] in stats['members']:
                        del stats['members'][member['id']]
                        LOG.debug(
                            'Member removed from stats members:%s' % stats)
                    else:
                        LOG.debug(
                            'Member not found in stats.  Stats not modified.')
            self.plugin.update_pool_stats(context, pool_id, stats)
        except PoolNotFound:
            pass
        except Exception as ex:
            LOG.error(_('error updating pool stats: %s' % ex.message))

    def create_rpc_dispatcher(self):
        """ Create rpc dispatcher """
        return q_rpc.PluginRpcDispatcher(  # @UndefinedVariable
            [self, agents_db.AgentExtRpcCallback(self.plugin)])

    @log.log
    def _get_vxlan_endpoints(self, context, host=None):
        """ Get vxlan endpoints """
        endpoints = []
        for agent in self._core_plugin().get_agents(context):
            if 'configurations' in agent:
                if 'tunnel_types' in agent['configurations']:
                    if 'vxlan' in agent['configurations']['tunnel_types']:
                        if 'tunneling_ip' in agent['configurations']:
                            if not host:
                                endpoints.append(
                                    agent['configurations']['tunneling_ip']
                                )
                            else:
                                if str(agent['host']) == str(host):
                                    endpoints.append(
                                        agent['configurations']['tunneling_ip']
                                    )
                        if 'tunneling_ips' in agent['configurations']:
                            for ip_addr in \
                                    agent['configurations']['tunneling_ips']:
                                if not host:
                                    endpoints.append(ip_addr)
                                else:
                                    if agent['host'] == host:
                                        endpoints.append(ip_addr)
        return endpoints

    def _get_gre_endpoints(self, context, host=None):
        """ Get gre endpoints """
        endpoints = []
        for agent in self._core_plugin().get_agents(context):
            if 'configurations' in agent:
                if 'tunnel_types' in agent['configurations']:
                    if 'gre' in agent['configurations']['tunnel_types']:
                        if 'tunneling_ip' in agent['configurations']:
                            if not host:
                                endpoints.append(
                                    agent['configurations']['tunneling_ip']
                                )
                            else:
                                if str(agent['host']) == str(host):
                                    endpoints.append(
                                        agent['configurations']['tunneling_ip']
                                    )
                        if 'tunneling_ips' in agent['configurations']:
                            for ip_addr in \
                                    agent['configurations']['tunneling_ips']:
                                if not host:
                                    endpoints.append(ip_addr)
                                else:
                                    if agent['host'] == host:
                                        endpoints.append(ip_addr)
        return endpoints


class LoadBalancerAgentApi(proxy.RpcProxy):  # @UndefinedVariable
    """Plugin side of plugin to agent RPC API.

       This class publishes RPC messages for agents to consume.
    """

    BASE_RPC_API_VERSION = '1.0'
    # history
    #   1.0 Initial version
    #   1.1 Support agent_updated call

    def __init__(self, topic, env=None):
        if env:
            LOG.debug('Created LoadBalancerAgentApi RPC publisher for env %s'
                      % env)
            super(LoadBalancerAgentApi, self).__init__(
                topic, default_version=self.BASE_RPC_API_VERSION)
        else:
            LOG.debug('Created LoadBalancerAgentApi RPC publisher')
            super(LoadBalancerAgentApi, self).__init__(
                topic, default_version=self.BASE_RPC_API_VERSION)

    @log.log
    def create_vip(self, context, vip, service, host):
        """ Send message to agent to create vip """
        return self.cast(
            context,
            self.make_msg('create_vip', vip=vip, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_vip(self, context, old_vip, vip, service, host):
        """ Send message to agent to update vip """
        return self.cast(
            context,
            self.make_msg('update_vip', old_vip=old_vip, vip=vip,
                          service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_vip(self, context, vip, service, host):
        """ Send message to agent to create vip """
        return self.cast(
            context,
            self.make_msg('delete_vip', vip=vip, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_pool(self, context, pool, service, host):
        """ Send message to agent to create pool """
        return self.cast(
            context,
            self.make_msg('create_pool', pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_pool(self, context, old_pool, pool, service, host):
        """ Send message to agent to update pool """
        return self.cast(
            context,
            self.make_msg('update_pool', old_pool=old_pool, pool=pool,
                          service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_pool(self, context, pool, service, host):
        """ Send message to agent to delete pool """
        return self.cast(
            context,
            self.make_msg('delete_pool', pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_member(self, context, member, service, host):
        """ Send message to agent to create member """
        return self.cast(
            context,
            self.make_msg('create_member', member=member, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_member(self, context, old_member, member, service, host):
        """ Send message to agent to update member """
        return self.cast(
            context,
            self.make_msg('update_member', old_member=old_member,
                          member=member, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_member(self, context, member, service, host):
        """ Send message to agent to delete member """
        return self.cast(
            context,
            self.make_msg('delete_member', member=member, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool,
                                   service, host):
        """ Send message to agent to create pool health monitor """
        return self.cast(
            context,
            self.make_msg('create_pool_health_monitor',
                          health_monitor=health_monitor, pool=pool,
                          service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool, service, host):
        """ Send message to agent to update pool health monitor """
        return self.cast(
            context,
            self.make_msg('update_health_monitor',
                          old_health_monitor=old_health_monitor,
                          health_monitor=health_monitor,
                          pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor, pool,
                                   service, host):
        """ Send message to agent to delete pool health monitor """
        return self.cast(
            context,
            self.make_msg('delete_pool_health_monitor',
                          health_monitor=health_monitor,
                          pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def agent_updated(self, context, admin_state_up, host):
        """ Send message to update agent """
        return self.cast(
            context,
            self.make_msg('agent_updated',
                          payload={'admin_state_up': admin_state_up}),
            topic='%s.%s' % (self.topic, host),
            version='1.1'
        )

    @log.log
    def get_pool_stats(self, context, pool, service, host):
        """ Send message to agent to get pool stats """
        LOG.debug('Calling agent for get_pool_stats')
        stats = self.cast(
            context,
            self.make_msg('get_pool_stats', pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )
        LOG.debug('Got agent for get_pool_stats: %s' % stats)
        return stats


class F5PluginDriver(LoadBalancerAbstractDriver):
    """ Plugin Driver for LBaaS.

        This class implements the methods found in the abstract
        parent class.

        This class interacts with the data model through the
        core plugin, creates messages to send to agents and then
        invokes the LoadBalancerAgentApi class methods to
        send the RPC messages.
    """
    def __init__(self, plugin, env=None):
        if env:
            self.env = str(env).lower()
            LOG.debug('Initializing F5PluginDriver for Environment %s' % env)
        else:
            self.env = None
            LOG.debug('Initializing F5PluginDriver')

        # what scheduler to use for pool selection
        self.pool_scheduler = importutils.import_object(
            cfg.CONF.f5_loadbalancer_pool_scheduler_driver)

        # Create RPM Message caster to agents
        self.agent_rpc = LoadBalancerAgentApi(
            lbaasv1constants.TOPIC_LOADBALANCER_AGENT,
            env
        )

        # keep reference to LBaaS plugin
        self.plugin = plugin
        # create RPC listener for callback functions from agents
        # to perform service queries and object updates
        self._set_callbacks()
        # add this agent RPC to the neutron agent scheduler
        # mixins agent_notifiers dictionary for it's env
        self.plugin.agent_notifiers.update(
            {q_const.AGENT_TYPE_LOADBALANCER: self.agent_rpc})

    def _core_plugin(self):
        """ Get the core plugin """
        return self.plugin._core_plugin

    def _set_callbacks(self):
        """ Setup callbacks to receive calls from agent """
        self.callbacks = LoadBalancerCallbacks(self.plugin,
                                               self.env,
                                               self.pool_scheduler)
        topic = lbaasv1constants.TOPIC_PROCESS_ON_HOST
        if self.env:
            topic = topic + "_" + self.env

        if PREJUNO:
            self.conn = rpc.create_connection(new=True)
            # register the callback consumer
            self.conn.create_consumer(
                topic,
                self.callbacks.create_rpc_dispatcher(),
                fanout=False)
            self.conn.consume_in_thread()
        else:
            self.conn = q_rpc.create_connection(new=True)  # @UndefinedVariable
            self.conn.create_consumer(
                topic,
                [self.callbacks, agents_db.AgentExtRpcCallback(self.plugin)],
                fanout=False)
            self.conn.consume_in_threads()

    def get_pool_agent(self, context, pool_id):
        """ Get agent for a pool """
        # define which agent to communicate with to handle provision
        # for this pool.  This is in the plugin extension for loadbalancer.
        # It references the agent_scheduler and the scheduler class
        # will pick from the registered agents.

        # If the env is set, get active agent in this env. If the agent
        # which is associated with this pool is active, it will
        # be used. Otherwise another agent in the env will be used.

        # Note: without the env set, the orginal agent associated
        # with the pool will be returned regardless if it is up
        # or it is not. The RPC message will be set to his host
        # name specific queue.
        agent = self.pool_scheduler.get_lbaas_agent_hosting_pool(
            self.plugin,
            context,
            pool_id,
            env=self.env
        )
        if not agent:
            raise lbaas_agentscheduler.NoActiveLbaasAgent(pool_id=pool_id)
        return agent['agent']

    @log.log
    def create_vip(self, context, vip):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])
        vip['pool'] = self._get_pool(context, vip['pool_id'])
        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=vip['pool_id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # Update the port for the VIP to show ownership by this driver
        port_data = {
            'admin_state_up': True,
            'device_id': str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS, str(agent['host'])
                )
            ),
            'device_owner': 'network:f5lbaas',
            'status': q_const.PORT_STATUS_ACTIVE
        }
        port_data[portbindings.HOST_ID] = agent['host']
        self._core_plugin().update_port(
            context,
            vip['port_id'],
            {'port': port_data}
        )
        # call the RPC proxy with the constructed message
        self.agent_rpc.create_vip(context, vip, service, agent['host'])

    @log.log
    def update_vip(self, context, old_vip, vip):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        old_vip['pool'] = self._get_pool(context, old_vip['pool_id'])

        vip['pool'] = self._get_pool(context, vip['pool_id'])

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=vip['pool_id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_vip(context, old_vip, vip,
                                  service, agent['host'])

    @log.log
    def delete_vip(self, context, vip):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        vip['pool'] = self._get_pool(context, vip['pool_id'])

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=vip['pool_id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_vip(context, vip, service, agent['host'])

    @log.log
    def create_pool(self, context, pool):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.pool_scheduler.schedule(self.plugin, context,
                                             pool, self.env)
        if not agent:
            raise lbaas_agentscheduler.NoEligibleLbaasAgent(pool_id=pool['id'])
        if not PREJUNO:
            agent = self.plugin._make_agent_dict(agent)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool['id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )
        # call the RPC proxy with the constructed message
        self.agent_rpc.create_pool(context, pool, service, agent['host'])

    @log.log
    def update_pool(self, context, old_pool, pool):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool['id'])

        if 'vip_id' in old_pool and old_pool['vip_id']:
            old_pool['vip'] = self._get_vip(context, old_pool['vip_id'])
        else:
            old_pool['vip'] = None

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool['id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_pool(context, old_pool, pool,
                                   service, agent['host'])

    @log.log
    def delete_pool(self, context, pool):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        try:
            agent = self.get_pool_agent(context, pool['id'])
        except lbaas_agentscheduler.NoActiveLbaasAgent:
            # if there is agent for this pool.. allow the data
            # model to delete it.
            self.callbacks.pool_destroyed(context, pool['id'], None)
            return

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool['id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_pool(context, pool, service, agent['host'])

    @log.log
    def create_member(self, context, member):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        member['pool'] = pool

        start_time = time()
        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=member['pool_id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )
        LOG.debug("get_service took %.5f secs" % (time() - start_time))

        this_member_count = 0
        for service_member in service['members']:
            if service_member['address'] == member['address'] and \
               service_member['protocol_port'] == member['protocol_port']:
                this_member_count += 1
        if this_member_count > 1:
            status_description = 'duplicate member %s:%s found in pool %s' \
                % (
                    member['address'],
                    member['protocol_port'],
                    member['pool_id']
                )
            self.callbacks.update_member_status(
                context,
                member_id=member['id'],
                status=constants.ERROR,
                status_description=status_description,
                host=agent['host']
            )

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_member(context, member, service, agent['host'])

    @log.log
    def update_member(self, context, old_member, member):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a 'was' pool structure for the rpc message
        old_pool = self._get_pool(context, old_member['pool_id'])

        old_member['pool'] = old_pool

        # populate a 'to be' pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        member['pool'] = pool

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=member['pool_id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_member(context, old_member, member,
                                     service, agent['host'])

        # if they moved members between pools, we need to send
        # a service call to update the old pool to remove
        # the pool member
        if not old_member['pool_id'] == member['pool_id']:
            # the member should not be in this pool in the db anymore
            old_pool_service = self.callbacks.get_service_by_pool_id(
                context,
                pool_id=old_member['pool_id'],
                global_routed_mode=self._is_global_routed(agent),
                host=agent['host']
            )
            for service_member in old_pool_service['members']:
                if service_member['id'] == old_member['id']:
                    service_member['status'] = 'MOVING'
            self.agent_rpc.update_member(
                context, old_member, member,
                old_pool_service, agent['host']
            )

    @log.log
    def delete_member(self, context, member):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        member['pool'] = pool

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=member['pool_id'],
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_member(context, member,
                                     service, agent['host'])

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool strucutre for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool_id,
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_pool_health_monitor(context, health_monitor,
                                                  pool, service,
                                                  agent['host'])

    @log.log
    def update_pool_health_monitor(self, context, old_health_monitor,
                                   health_monitor, pool_id):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool_id,
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_health_monitor(context, old_health_monitor,
                                             health_monitor, pool,
                                             service, agent['host'])

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool_id):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool_id,
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_health_monitor(context, old_health_monitor,
                                             health_monitor, pool,
                                             service, agent['host'])

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool_id,
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_pool_health_monitor(context, health_monitor,
                                                  pool, service,
                                                  agent['host'])

    @log.log
    def stats(self, context, pool_id):
        """ Handle LBaaS method by passing to agent """
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(
            context,
            pool_id=pool_id,
            global_routed_mode=self._is_global_routed(agent),
            host=agent['host']
        )

        # call the RPC proxy with the constructed message
        self.agent_rpc.get_pool_stats(context, pool, service, agent['host'])

    @staticmethod
    def _is_global_routed(agent):
        """ Is the agent in global routed mode? """
        if 'configurations' in agent:
            if 'global_routed_mode' in agent['configurations']:
                return agent['configurations']['global_routed_mode']
        return False

    def _get_pool(self, context, pool_id):
        pool = self.plugin.get_pool(context, pool_id)
        if 'subnet_id' in pool:
            pool['subnet'] = self._core_plugin().get_subnet(
                context,
                pool['subnet_id']
            )
        pool['subnet']['network'] = \
            self._core_plugin().get_network(
                context,
                pool['subnet']['network_id']
            )

        return pool

    def _get_vip(self, context, vip_id):
        """ Get vip from neutron """
        return self.plugin.get_vip(context, vip_id)

    def _get_vxlan_endpoints(self, context):
        """ Get vxlan tunneling endpoints from all agents """
        endpoints = []
        if hasattr(self._core_plugin(), 'get_agents'):
            agents = self._core_plugin().get_agents(context)
            for agent in agents:
                if 'configurations' in agent:
                    if 'tunnel_types' in agent['configurations']:
                        if 'vxlan' in agent['configurations']['tunnel_types']:
                            if 'tunneling_ip' in agent['configurations']:
                                endpoints.append(
                                    agent['configurations']['tunneling_ip']
                                )
        return endpoints

    def _get_gre_endpoints(self, context):
        """ Get gre tunneling endpoints from all agents """
        endpoints = []
        if hasattr(self._core_plugin(), 'get_agents'):
            agents = self._core_plugin().get_agents(context)
            for agent in agents:
                if 'configurations' in agent:
                    if 'tunnel_types' in agent['configurations']:
                        if 'gre' in agent['configurations']['tunnel_types']:
                            if 'tunneling_ip' in agent['configurations']:
                                endpoints.append(
                                    agent['configurations']['tunneling_ip']
                                )
        return endpoints


class F5PluginDriverTest(F5PluginDriver):
    """ Plugin Driver for Test environment """

    def __init__(self, plugin, env='Test'):
        super(F5PluginDriverTest, self).__init__(plugin, env)


class F5PluginDriverProd(F5PluginDriver):
    """ Plugin Driver for Test environment """

    def __init__(self, plugin, env='Prod'):
        super(F5PluginDriverProd, self).__init__(plugin, env)


class F5PluginDriverDev(F5PluginDriver):
    """ Plugin Driver for Test environment """

    def __init__(self, plugin, env='Dev'):
        super(F5PluginDriverDev, self).__init__(plugin, env)

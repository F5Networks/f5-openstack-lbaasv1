import uuid

from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import rpc as q_rpc
from neutron.db import models_v2
from neutron.plugins.ml2 import models as models_ml2
from neutron.db import agents_db
from neutron.db.loadbalancer import loadbalancer_db as ldb
from neutron.extensions import lbaas_agentscheduler
from neutron.openstack.common import importutils
from neutron.common import log
from neutron.openstack.common import log as logging
from neutron.openstack.common import rpc
from neutron.openstack.common.rpc import proxy
from neutron.plugins.common import constants
from neutron.extensions import portbindings
from neutron.services.loadbalancer.drivers import abstract_driver
from neutron.context import get_admin_context
from time import time

LOG = logging.getLogger(__name__)

__VERSION__ = '0.1.1'

ACTIVE_PENDING = (
    constants.ACTIVE,
    constants.PENDING_CREATE,
    constants.PENDING_UPDATE,
    constants.ERROR
)

OPTS = [
    cfg.StrOpt('f5_loadbalancer_pool_scheduler_driver',
               default=('neutron.services.loadbalancer'
                        '.drivers.f5.agent_scheduler'
                        '.TenantScheduler'),
               help=_('Driver to use for scheduling '
                      'pool to a default loadbalancer agent'))
]

cfg.CONF.register_opts(OPTS)

# topic name for this particular agent implementation
TOPIC_PROCESS_ON_HOST = 'q-f5-lbaas-process-on-host'
TOPIC_LOADBALANCER_AGENT = 'f5_lbaas_process_on_agent'
VIF_TYPE = 'f5'

class LoadBalancerCallbacks(object):
    """Callbacks made by the agent to update the data model."""
    RPC_API_VERSION = '1.0'

    def __init__(self, plugin):
        LOG.debug('LoadBalancerCallbacks RPC subscriber initialized')
        self.plugin = plugin
        self.net_cache = {}
        self.subnet_cache = {}
        self.agent_cache = {}

    def create_rpc_dispatcher(self):
        return q_rpc.PluginRpcDispatcher(
            [self, agents_db.AgentExtRpcCallback(self.plugin)])

    @log.log
    def get_active_pending_pool_ids(self, context, host=None):
        with context.session.begin(subtransactions=True):
            qry = (context.session.query(ldb.Pool.id))
            qry = qry.filter(ldb.Pool.status.in_(ACTIVE_PENDING))
            up = True

            qry = qry.filter(ldb.Pool.admin_state_up == up)

            agents = self.plugin.get_lbaas_agents(context)
            if not agents:
                return []
            agents = self.plugin.get_lbaas_agents(context,
                                                  filters={'host': [host]})
            LOG.debug(_('Looking for pools assigned to agent.host: %s' % host))
            if not agents:
                return []
            elif len(agents) > 1:
                LOG.warning(_('Multiple lbaas agents found on host %s'), host)

            pools = self.plugin.list_pools_on_lbaas_agent(context,
                                                          agents[0].id)
            pool_ids = [pool['id'] for pool in pools['pools']]
            qry = qry.filter(ldb.Pool.id.in_(pool_ids))
            return [id for id, in qry]

    @log.log
    def get_service_by_pool_id(self, context, pool_id=None,
                            activate=False, host=None,
                           **kwargs):
        with context.session.begin(subtransactions=True):
            qry = context.session.query(ldb.Pool)
            qry = qry.filter_by(id=pool_id)
            pool = qry.one()
            LOG.debug(_('getting service definition entry for %s' % pool))
            if activate:
                # set all resources to active
                if pool.status in ACTIVE_PENDING:
                    pool.status = constants.ACTIVE
                if pool.vip:
                    if pool.vip.status in ACTIVE_PENDING:
                        pool.vip.status = constants.ACTIVE
                for m in pool.members:
                    if m.status in ACTIVE_PENDING:
                        m.status = constants.ACTIVE
                for hm in pool.monitors:
                    if hm.status in ACTIVE_PENDING:
                        hm.status = constants.ACTIVE
            retval = {}
            ports_cache = {}
            retpool = self.plugin._make_pool_dict(pool)
            retval['pool'] = retpool

            # get pool subnet
            pool_subnet_id = retpool['subnet_id']
            if pool_subnet_id in self.subnet_cache:
                retpool['subnet'] = self.subnet_cache[pool_subnet_id]
            else:
                subnet_dict = self.plugin._core_plugin.get_subnet(context,
                                            pool_subnet_id)
                retpool['subnet'] = subnet_dict
                self.subnet_cache[pool_subnet_id] = retpool['subnet']

            # get pool network
            pool_network_id = retpool['subnet']['network_id']
            if pool_network_id in self.net_cache:
                retpool['network'] = self.net_cache[pool_network_id]
            else:
                retpool['network'] = self.plugin._core_plugin.get_network(
                            context, pool_network_id)
                if not 'provider:network_type' in retpool['network']:
                    retpool['network']['provider:network_type'] = 'undefined'
                if not 'provider:segmentation_id' in retpool['network']:
                    retpool['network']['provider:segmentation_id'] = 0
                self.net_cache[pool_network_id] = retpool['network']

            # get pool subnet ports
            if pool_subnet_id in ports_cache:
                retpool['subnet_ports'] = ports_cache[pool_subnet_id]
            else:
                pool_subnet_fixed_ip_filters = {'network_id':
                                                [pool_network_id],
                'device_id': [str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host)))]}
                retpool['subnet_ports'] = \
                               self.plugin._core_plugin.get_ports(context,
                                      filters=pool_subnet_fixed_ip_filters)
                ports_cache[pool_subnet_id] = retpool['subnet_ports']

            if pool.vip:
                retval['vip'] = self.plugin._make_vip_dict(pool.vip)
                retval['vip']['port'] = (
                    self.plugin._core_plugin._make_port_dict(pool.vip.port)
                )
                retval['vip']['network'] = \
                 self.plugin._core_plugin.get_network(context,
                                        retval['vip']['port']['network_id'])
                retval['vip']['vxlan_vteps'] = []
                retval['vip']['gre_vteps'] = []
                if 'provider:network_type' in retval['vip']['network']:
                    nettype = retval['vip']['network']['provider:network_type']
                    if nettype == 'vxlan':
                        segment_qry = context.session.query(
                                                     models_ml2.NetworkSegment)
                        segment = segment_qry.filter_by(
                             network_id=retval['vip']['network']['id']).first()
                        segment_id = segment['id']
                        host_qry = context.session.query(
                                                        models_ml2.PortBinding)
                        hosts = host_qry.filter_by(segment=segment_id).all()
                        host_ids = set()
                        for host in hosts:
                            host_ids.add(host['host'])
                        for host_id in host_ids:
                            endpoints = \
                                self._get_vxlan_endpoints(context, host_id)
                            if len(endpoints) > 0:
                                retval['vip']['vxlan_vteps'] = \
                                    retval['vip']['vxlan_vteps'] + endpoints
                    if nettype == 'gre':
                        segment_qry = context.session.query(
                                                    models_ml2.NetworkSegment)
                        segment = segment_qry.filter_by(
                             network_id=retval['vip']['network']['id']).first()
                        segment_id = segment['id']
                        host_qry = context.session.query(
                                                        models_ml2.PortBinding)
                        hosts = host_qry.filter_by(segment=segment_id).all()
                        host_ids = set()
                        for host in hosts:
                            host_ids.add(host['host'])
                        for host_id in host_ids:
                            endpoints = \
                                self._get_gre_endpoints(context, host_id)
                            if len(endpoints) > 0:
                                retval['vip']['gre_vteps'] = \
                                    retval['vip']['gre_vteps'] + endpoints
                else:
                    retval['vip']['network']['provider:network_type'] = \
                                                                   'undefined'
                if not 'provider:segmentation_id' in retval['vip']['network']:
                    retval['vip']['network']['provider:segmentation_id'] = 0
                # there should only be one fixed_ip
                for fixed_ip in retval['vip']['port']['fixed_ips']:
                    retval['vip']['subnet'] = (
                         self.plugin._core_plugin.get_subnet(context,
                                                      fixed_ip['subnet_id'])
                                               )
                    retval['vip']['address'] = fixed_ip['ip_address']
                vip_subnet_fixed_ip_filters = {'network_id':
                        [retval['vip']['subnet']['network_id']],
                        'device_id': [
                            str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host)))]}
                retval['vip']['subnet_ports'] = \
                             self.plugin._core_plugin.get_ports(context,
                                      filters=vip_subnet_fixed_ip_filters)
            else:
                retval['vip'] = {}
                retval['vip']['port'] = {}
                retval['vip']['port']['network'] = None
                retval['vip']['port']['subnet'] = None
                retval['vip']['subnet_ports'] = []
            retval['members'] = []

            adminctx = get_admin_context()
            for m in pool.members:
                member = self.plugin._make_member_dict(m)
                alloc_qry = adminctx.session.query(models_v2.IPAllocation)
                allocated = alloc_qry.filter_by(
                                        ip_address=member['address']).all()
                for alloc in allocated:
                    # It is normal to find a duplicate IP for another tenant,
                    # so first see if we find its network under this
                    # tenant context. A NotFound exception is normal if
                    # the IP belongs to another tenant.
                    try:
                        #start_time = time()
                        if alloc['network_id'] in self.net_cache:
                            net = self.net_cache[alloc['network_id']]
                        else:
                            net = self.plugin._core_plugin.get_network(
                                             adminctx, alloc['network_id'])
                            self.net_cache[alloc['network_id']] = net
                        #LOG.debug("get network took %.5f secs " %
                        #          (time() - start_time))
                    except:
                        continue
                    if net['tenant_id'] != pool['tenant_id']:
                        continue

                    member['network'] = net
                    self.set_member_subnet_info(context, host,
                                                member,
                                                alloc['subnet_id'],
                                                ports_cache)
                    member['port'] = self.plugin._core_plugin.get_port(
                                             adminctx, alloc['port_id'])
                    member['vxlan_vteps'] = []
                    member['gre_vteps'] = []
                    if 'provider:network_type' in member['network']:
                        nettype = member['network']['provider:network_type']
                        if nettype == 'vxlan':
                            if 'binding:host_id' in member['port']:
                                host = member['port']['binding:host_id']
                                member['vxlan_vteps'] = \
                                    self._get_vxlan_endpoints(context, host)
                        if nettype == 'gre':
                            if 'binding:host_id' in member['port']:
                                host = member['port']['binding:host_id']
                                member['vxlan_vteps'] = \
                                    self._get_gre_endpoints(context, host)
                    else:
                        member['network']['provider:network_type'] = \
                                                                   'undefined'
                    if not 'provider:segmentation_id' in member['network']:
                        member['network']['provider:segmentation_id'] = 0
                    retval['members'].append(member)
                    break
                else:
                    # tenant member not found. accept any
                    # allocated ip on a shared network
                    for alloc in allocated:
                        try:
                            net = self.plugin._core_plugin.get_network(
                                                 adminctx, alloc['network_id'])
                        except:
                            continue
                        if not net['shared']:
                            continue
                        member['network'] = net
                        self.set_member_subnet_info(context, host,
                                                    member,
                                                    alloc['subnet_id'],
                                                    ports_cache)
                        member['port'] = self.plugin._core_plugin.get_port(
                                             adminctx, alloc['port_id'])
                        member['vxlan_vteps'] = []
                        member['gre_vteps'] = []
                        if 'provider:network_type' in member['network']:
                            nettype = \
                               member['network']['provider:network_type']
                            if nettype == 'vxlan':
                                vteps = self._get_vxlan_endpoints(context,
                                                        alloc['port_id'])
                                member['vxlan_vteps'] = vteps
                            if nettype == 'gre':
                                vteps = self._get_gre_endpoints(context,
                                                        alloc['port_id'])
                                member['gre_vteps'] = vteps
                        else:
                            member['network']['provider:network_type'] = \
                                                                   'undefined'
                        if not 'provider:segmentation_id' in member['network']:
                            member['network']['provider:segmentation_id'] = 0
                        retval['members'].append(member)
                        break
                    else:
                        member['network'] = None
                        member['subnet'] = None
                        member['port'] = None
                        retval['members'].append(member)

            retval['health_monitors'] = []
            for hm in retval['pool']['health_monitors']:
                retval['health_monitors'].append(
                      self.plugin.get_health_monitor(context, hm))

            retval['vxlan_endpoints'] = self._get_vxlan_endpoints(context)
            retval['gre_endpoints'] = self._get_gre_endpoints(context)

            return retval

    def set_member_subnet_info(self, context, host, member,
                                subnet_id, ports_cache):
        if subnet_id in self.subnet_cache:
            member['subnet'] = self.subnet_cache[subnet_id]
        else:
            core_plugin = self.plugin._core_plugin
            member['subnet'] = core_plugin.get_subnet(context, subnet_id)
            self.subnet_cache[subnet_id] = member['subnet']

        if subnet_id in ports_cache:
            member['subnet_ports'] = ports_cache[subnet_id]
        else:
            member_subnet_fixed_ip_filters = {'network_id':
                                            [member['subnet']['network_id']],
                'device_id': [str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host)))]}
            core_plugin = self.plugin._core_plugin
            member['subnet_ports'] = core_plugin.get_ports(context,
                                        filters=member_subnet_fixed_ip_filters)
            ports_cache[subnet_id] = member['subnet_ports']

    @log.log
    def create_network(self, context, tenant_id=None, name=None, shared=False,
                       admin_state_up=True, network_type=None,
                       physical_network=None, segmentation_id=None):
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
        return self.plugin._core_plugin.create_network(context, {'network':
                                                          network_data})

    @log.log
    def delete_network(self, context, network_id):
        self.plugin._core_plugin.delete_network(context, network_id)

    @log.log
    def create_subnet(self, context, tenant_id=None, network_id=None,
                      name=None, shared=False, cidr=None, enable_dhcp=False,
                      gateway_ip=None, allocation_pools=None,
                      dns_nameservers=None, host_routes=None):
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
        return self.plugin._core_plugin.create_subnet(context, {'subenet':
                                                         subnet_data})

    @log.log
    def delete_subnet(self, context, subnet_id):
        self.plugin._core_plugin.delete_subnet(context, subnet_id)

    @log.log
    def create_port_on_subnet(self, context, subnet_id=None,
                    mac_address=None, name=None,
                    fixed_address_count=1, host=None):
        if subnet_id:
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
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
            port_data[portbindings.CAPABILITIES] = {'port_filter': False}
            port = self.plugin._core_plugin.create_port(context,
                                                        {'port': port_data})
            # Because ML2 marks ports DOWN by default on creation
            update_data = {
                'status': q_const.PORT_STATUS_ACTIVE
            }
            self.plugin._core_plugin.update_port(context,
                                      port['id'],
                                      {'port': update_data})
            return port

    @log.log
    def create_port_on_subnet_with_specific_ip(self, context, subnet_id=None,
                    mac_address=None, name=None,
                    ip_address=None, host=None):
        if subnet_id and ip_address:
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
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
            port_data[portbindings.CAPABILITIES] = {'port_filer': False}
            port = self.plugin._core_plugin.create_port(context,
                                                        {'port': port_data})
            # Because ML2 marks ports DOWN by default on creation
            update_data = {
                'status': q_const.PORT_STATUS_ACTIVE
            }
            self.plugin._core_plugin.update_port(context,
                                      port['id'],
                                      {'port': update_data})
            return port

    @log.log
    def get_port_by_name(self, context, port_name=None):
        if port_name:
            filters = {'name': [port_name]}
            return self.plugin._core_plugin.get_ports(context,
                                                        filters=filters)

    @log.log
    def delete_port(self, context, port_id=None, mac_address=None):
        if port_id:
            self.plugin._core_plugin.delete_port(context, port_id)
        elif mac_address:
            filters = {'mac_address': [mac_address]}
            ports = self.plugin._core_plugin.get_ports(context,
                                                        filters=filters)
            for port in ports:
                self.plugin._core_plugin.delete_port(context, port['id'])

    @log.log
    def delete_port_by_name(self, context, port_name=None):
        if port_name:
            filters = {'name': [port_name]}
            ports = self.plugin._core_plugin.get_ports(context,
                                                        filters=filters)
            for port in ports:
                self.plugin._core_plugin.delete_port(context, port['id'])

    @log.log
    def allocate_fixed_address_on_subnet(self, context, subnet_id=None,
                               port_id=None, name=None,
                               fixed_address_count=1, host=None):
        if subnet_id:
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
            if not port_id:
                port = self.create_port_on_subnet(context,
                                 subnet_id=subnet_id,
                                 mac_address=None,
                                 name=name,
                                 fixed_address_count=fixed_address_count,
                                 host=host)
            else:
                port = self.plugin._core_plugin.get_port(context,
                                                         port_id)
                existing_fixed_ips = port['fixed_ips']
                fixed_ip = {'subnet_id': subnet['id']}
                if fixed_address_count > 1:
                    fixed_ips = []
                    for _ in range(0, fixed_address_count):
                        fixed_ips.append(fixed_ip)
                else:
                    fixed_ips = [fixed_ip]
            port['fixed_ips'] = existing_fixed_ips + fixed_ips
            port = self.plugin._core_plugin.update_port(context,
                                                        {'port': port})
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
                               ip_address=None, host=None):
        if subnet_id and ip_address:
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
            if not port_id:
                port = self.create_port_on_subnet_with_specific_ip(
                                 context,
                                 subnet_id=subnet_id,
                                 mac_address=None,
                                 name=name,
                                 ip_address=ip_address,
                                 host=host)
            else:
                port = self.plugin._core_plugin.get_port(context,
                                                         port_id)
                existing_fixed_ips = port['fixed_ips']
                fixed_ip = {'subnet_id': subnet['id'],
                            'ip_address': ip_address}
            port['fixed_ips'] = existing_fixed_ips + [fixed_ip]
            port = self.plugin._core_plugin.update_port(context,
                                                        {'port': port})
            return port

    @log.log
    def deallocate_fixed_address_on_subnet(self, context, fixed_addresses=None,
                             subnet_id=None, host=None,
                             auto_delete_port=False):
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
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
            # get all ports for this host on the subnet
            filters = {'network_id': [subnet['network_id']],
                       'tenant_id': [subnet['tenant_id']],
                       'device_id': [
                            str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host)))]}
            ports = self.plugin._core_plugin.get_ports(context,
                                                        filters=filters)
            fixed_ips = {}
            ok_to_delete_port = {}
            for port in ports:
                ok_to_delete_port[port['id']] = False
                for fixed_ip in port['fixed_ips']:
                    fixed_ips[fixed_ip['ip_address']] = port['id']
            # only get rid of associated fixed_ips
            for fixed_ip in fixed_ips:
                if fixed_ip in fixed_addresses:
                    self.plugin._core_plugin._delete_ip_allocation(context,
                                                        subnet['network_id'],
                                                        subnet_id,
                                                        fixed_ip)
                    ok_to_delete_port[fixed_ips[fixed_ip]] = True
                else:
                    ok_to_delete_port[fixed_ips[fixed_ip]] = False
            if auto_delete_port:
                for port in ok_to_delete_port:
                    if ok_to_delete_port[port]:
                        self.delete_port(context, port)

    @log.log
    def update_vip_status(self, context, vip_id=None,
                           status=constants.ERROR, status_description=None,
                           host=None):
        """Agent confirmation hook to update VIP status."""
        vip = self.plugin.get_vip(context, vip_id)
        if vip['status'] == constants.PENDING_DELETE:
            status = constants.PENDING_DELETE
        self.plugin.update_status(context,
                                  ldb.Vip,
                                  vip_id,
                                  status,
                                  status_description)

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
        self.plugin.update_status(context,
                                  ldb.Pool,
                                  pool_id,
                                  status,
                                  status_description)

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
        member = self.plugin.get_member(context, member_id)
        if member['status'] == constants.PENDING_DELETE:
            status = constants.PENDING_DELETE
        self.plugin.update_status(context,
                                  ldb.Member,
                                  member_id,
                                  status,
                                  status_description)

    @log.log
    def member_destroyed(self, context, member_id=None, host=None):
        """Agent confirmation hook that a member has been destroyed."""
        # delete the pool member from the data model
        self.plugin._delete_db_member(context, member_id)

    @log.log
    def update_health_monitor_status(self, context, pool_id=None,
                                     health_monitor_id=None,
                                     status=constants.ERROR,
                                     status_description=None,
                                     host=None):
        """Agent confirmation hook to update healthmonitor status."""
        self.plugin.update_pool_health_monitor(context,
                                               health_monitor_id, pool_id,
                                               status, status_description)

    @log.log
    def health_monitor_destroyed(self, context, health_monitor_id=None,
                                 pool_id=None, host=None):
        """Agent confirmation hook that a health has been destroyed."""
        # delete the health monitor from the data model
        # the plug-in does this sometimes so allow for an error.
        try:
            self.plugin._delete_db_pool_health_monitor(context,
                                                   health_monitor_id,
                                                   pool_id)
        except:
            pass

    @log.log
    def update_pool_stats(self, context, pool_id=None, stats=None, host=None):
        self.plugin.update_pool_stats(context, pool_id, stats)

    def _get_vxlan_endpoints(self, context, host=None):
        endpoints = []
        # populate if we are supposed to get all endpoints
        # or the host we are looking for is not cached already
        if not host or (host not in self.agent_cache):
            if hasattr(self.plugin._core_plugin, 'get_agents'):
                agents = self.plugin._core_plugin.get_agents(context)
                for agent in agents:
                    self.agent_cache[agent['host']] = agent
        for agent in self.agent_cache.values():
            if 'configurations' in agent:
                if 'tunnel_types' in agent['configurations']:
                    if 'vxlan' in agent['configurations']['tunnel_types']:
                        if 'tunneling_ip' in agent['configurations']:
                            if not host:
                                endpoints.append(
                                      agent['configurations']['tunneling_ip'])
                            else:
                                if agent['host'] == host:
                                    endpoints.append(
                                 agent['configurations']['tunneling_ip'])
                        if 'tunneling_ips' in agent['configurations']:
                            for ip in \
                                agent['configurations']['tunneling_ips']:
                                if not host:
                                    endpoints.append(ip)
                                else:
                                    if agent['host'] == host:
                                        endpoints.append(ip)
        return endpoints

    def _get_gre_endpoints(self, context, host=None):
        endpoints = []
        # populate if we are supposed to get all endpoints
        # or the host we are looking for is not cached already
        if not host or (host not in self.agent_cache):
            if hasattr(self.plugin._core_plugin, 'get_agents'):
                agents = self.plugin._core_plugin.get_agents(context)
                for agent in agents:
                    self.agent_cache[agent['host']] = agent
        for agent in self.agent_cache.values():
            if 'configurations' in agent:
                if 'tunnel_types' in agent['configurations']:
                    if 'gre' in agent['configurations']['tunnel_types']:
                        if 'tunneling_ip' in agent['configurations']:
                            if not host:
                                endpoints.append(
                                      agent['configurations']['tunneling_ip'])
                            else:
                                if agent['host'] == host:
                                    endpoints.append(
                                 agent['configurations']['tunneling_ip'])
                        if 'tunneling_ips' in agent['configurations']:
                            for ip in \
                                agent['configurations']['tunneling_ips']:
                                if not host:
                                    endpoints.append(ip)
                                else:
                                    if agent['host'] == host:
                                        endpoints.append(ip)
        return endpoints


class LoadBalancerAgentApi(proxy.RpcProxy):
    """Plugin side of plugin to agent RPC API.

       This class publishes RPC messages for
       agents to consume.
    """

    BASE_RPC_API_VERSION = '1.0'
    # history
    #   1.0 Initial version
    #   1.1 Support agent_updated call

    def __init__(self, topic):
        LOG.debug('LoadBalancerAgentApi RPC publisher constructor called')
        super(LoadBalancerAgentApi, self).__init__(
            topic, default_version=self.BASE_RPC_API_VERSION)

    @log.log
    def create_vip(self, context, vip, service, host):
        return self.cast(
            context,
            self.make_msg('create_vip', vip=vip, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_vip(self, context, old_vip, vip, service, host):
        return self.cast(
            context,
            self.make_msg('update_vip', old_vip=old_vip, vip=vip,
                          service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_vip(self, context, vip, service, host):
        return self.cast(
            context,
            self.make_msg('delete_vip', vip=vip, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_pool(self, context, pool, service, host):
        return self.cast(
            context,
            self.make_msg('create_pool', pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_pool(self, context, old_pool, pool, service, host):
        return self.cast(
            context,
            self.make_msg('update_pool', old_pool=old_pool, pool=pool,
                          service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_pool(self, context, pool, service, host):
        return self.cast(
            context,
            self.make_msg('delete_pool', pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_member(self, context, member, service, host):
        return self.cast(
            context,
            self.make_msg('create_member', member=member, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_member(self, context, old_member, member, service, host):
        return self.cast(
            context,
            self.make_msg('update_member', old_member=old_member,
                          member=member, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_member(self, context, member, service, host):
        return self.cast(
            context,
            self.make_msg('delete_member', member=member, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool,
                                   service, host):
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
        return self.cast(
            context,
            self.make_msg('delete_pool_health_monitor',
                          health_monitor=health_monitor,
                          pool=pool, service=service),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def agent_updated(self, context, admin_state_up, host):
        return self.cast(
            context,
            self.make_msg('agent_updated',
                          payload={'admin_state_up': admin_state_up}),
            topic='%s.%s' % (self.topic, host),
            version='1.1'
        )

    @log.log
    def get_pool_stats(self, context, pool, service, host):
        return self.cast(
                         context,
                         self.make_msg('get_pool_stats',
                                       pool=pool, service=service),
                         topic='%s.%s' % (self.topic, host)
                         )


class F5PluginDriver(abstract_driver.LoadBalancerAbstractDriver):
    """ Plugin Driver for LBaaS.

        This class implements the methods found in the abstract
        parent class.

        This class interacts with the data model through the
        core plugin, creates messages to send to agents and then
        invokes the LoadBalancerAgentApi class methods to
        send the RPC messages.
    """
    def __init__(self, plugin):
        LOG.debug('Initializing F5PluginDriver')

        # create the RPC message casting class - publisher
        self.agent_rpc = LoadBalancerAgentApi(TOPIC_LOADBALANCER_AGENT)
        # register the RPC call back receiving class - subscriber
        self.callbacks = LoadBalancerCallbacks(plugin)
        # connect to the RPC message bus
        self.conn = rpc.create_connection(new=True)
        # register the callback consumer
        self.conn.create_consumer(
            TOPIC_PROCESS_ON_HOST,
            self.callbacks.create_rpc_dispatcher(),
            fanout=False)
        self.conn.consume_in_thread()
        # create an instance reference to the core plugin
        # this is a regular part of the extensions model
        self.plugin = plugin
        # register as a load loadbalancer agent
        self.plugin.agent_notifiers.update(
            {q_const.AGENT_TYPE_LOADBALANCER: self.agent_rpc})
        # create an instance reference to the agent scheduler
        self.pool_scheduler = importutils.import_object(
            cfg.CONF.f5_loadbalancer_pool_scheduler_driver)

    def get_pool_agent(self, context, pool_id):
        # define which agent to communicate with to handle provision
        # for this pool.  This is in the plugin extension for loadbalancer.
        # It references the agent_scheduler and the scheduler class
        # will pick from the registered agents.
        agent = self.plugin.get_lbaas_agent_hosting_pool(context, pool_id)
        if not agent:
            raise lbaas_agentscheduler.NoActiveLbaasAgent(pool_id=pool_id)
        return agent['agent']

    @log.log
    def create_vip(self, context, vip):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        vip['pool'] = self._get_pool(context, vip['pool_id'])

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=vip['pool_id'],
                                                        activate=False,
                                                        host=agent['host'])

        # Update the port for the VIP to show ownership by this driver
        port_data = {
                'admin_state_up': True,
                'device_id':
                  str(uuid.uuid5(uuid.NAMESPACE_DNS, str(agent['host']))),
                'device_owner': 'network:f5lbaas',
                'status': q_const.PORT_STATUS_ACTIVE
        }
        port_data[portbindings.HOST_ID] = agent['host']
        self.plugin._core_plugin.update_port(context,
                                      vip['port_id'],
                                      {'port': port_data})
        # call the RPC proxy with the constructed message
        self.agent_rpc.create_vip(context, vip, service, agent['host'])

    @log.log
    def update_vip(self, context, old_vip, vip):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        old_vip['pool'] = self._get_pool(context, old_vip['pool_id'])

        vip['pool'] = self._get_pool(context, vip['pool_id'])

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=vip['pool_id'],
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_vip(context, old_vip, vip,
                                  service, agent['host'])

    @log.log
    def delete_vip(self, context, vip):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        vip['pool'] = self._get_pool(context, vip['pool_id'])

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=vip['pool_id'],
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_vip(context, vip, service, agent['host'])

    @log.log
    def create_pool(self, context, pool):
        # which agent should handle provisioning
        agent = self.pool_scheduler.schedule(self.plugin, context, pool)
        if not agent:
            raise lbaas_agentscheduler.NoEligibleLbaasAgent(pool_id=pool['id'])

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool['id'],
                                                        activate=False,
                                                        host=agent['host'])
        # call the RPC proxy with the constructed message
        self.agent_rpc.create_pool(context, pool, service, agent['host'])

    @log.log
    def update_pool(self, context, old_pool, pool):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool['id'])

        if 'vip_id' in old_pool and old_pool['vip_id']:
            old_pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            old_pool['vip'] = None

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool['id'],
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_pool(context, old_pool, pool,
                                   service, agent['host'])

    @log.log
    def delete_pool(self, context, pool):
        # which agent should handle provisioning
        try:
            agent = self.get_pool_agent(context, pool['id'])
        except lbaas_agentscheduler.NoActiveLbaasAgent:
            # if there is agent for this pool.. allow the data
            # model to delete it.
            self.callbacks.pool_destroyed(context, pool['id'], None)
            return

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool['id'],
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_pool(context, pool, service, agent['host'])

    @log.log
    def create_member(self, context, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        member['pool'] = pool

        start_time = time()
        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                pool_id=member['pool_id'],
                                                activate=False,
                                                host=agent['host'])
        LOG.debug("get_service took %.5f secs" % (time() - start_time))

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_member(context, member, service, agent['host'])

    @log.log
    def update_member(self, context, old_member, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a 'was' pool structure for the rpc message
        old_pool = self._get_pool(context, old_member['pool_id'])

        old_member['pool'] = old_pool

        # populate a 'to be' pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        member['pool'] = pool

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                pool_id=member['pool_id'],
                                                activate=False,
                                                host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_member(context, old_member, member,
                                     service, agent['host'])

    @log.log
    def delete_member(self, context, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        member['pool'] = pool

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                pool_id=member['pool_id'],
                                                activate=False,
                                                host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_member(context, member,
                                     service, agent['host'])

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool strucutre for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool_id,
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_pool_health_monitor(context, health_monitor,
                                                  pool, service,
                                                  agent['host'])

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool_id,
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_health_monitor(context, old_health_monitor,
                                             health_monitor, pool,
                                             service, agent['host'])

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool_id,
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_pool_health_monitor(context, health_monitor,
                                                  pool, service,
                                                  agent['host'])

    @log.log
    def stats(self, context, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self._get_pool(context, pool_id)

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool_id,
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.get_pool_stats(context, pool, service, agent['host'])

    def _get_pool(self, context, pool_id):
        pool = self.plugin.get_pool(context, pool_id)
        if 'subnet_id' in pool:
            pool['subnet'] = self.plugin._core_plugin.get_subnet(context,
                                                            pool['subnet_id'])
        pool['subnet']['network'] = \
           self.plugin._core_plugin.get_network(context,
                                                pool['subnet']['network_id'])

        return pool

    def _get_vxlan_endpoints(self, context):
        endpoints = []
        if hasattr(self.plugin._core_plugin, 'get_agents'):
            agents = self.plugin._core_plugin.get_agents(context)
            for agent in agents:
                if 'configurations' in agent:
                    if 'tunnel_types' in agent['configurations']:
                        if 'vxlan' in agent['configurations']['tunnel_types']:
                            if 'tunneling_ip' in agent['configurations']:
                                endpoints.append(
                                     agent['configurations']['tunneling_ip'])
        return endpoints

    def _get_gre_endpoints(self, context):
        endpoints = []
        if hasattr(self.plugin._core_plugin, 'get_agents'):
            agents = self.plugin._core_plugin.get_agents(context)
            for agent in agents:
                if 'configurations' in agent:
                    if 'tunnel_types' in agent['configurations']:
                        if 'gre' in agent['configurations']['tunnel_types']:
                            if 'tunneling_ip' in agent['configurations']:
                                endpoints.append(
                                     agent['configurations']['tunneling_ip'])
        return endpoints

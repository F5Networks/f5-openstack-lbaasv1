# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 New Dream Network, LLC (DreamHost)
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Mark McClain, DreamHost

from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import exceptions as q_exc
from neutron.common import rpc as q_rpc
from neutron.db import models_v2
from neutron.db import agents_db
from neutron.db.loadbalancer import loadbalancer_db as ldb
from neutron.extensions import lbaas_agentscheduler
from neutron.openstack.common import importutils
from neutron.common import log
from neutron.openstack.common import log as logging
from neutron.openstack.common import rpc
from neutron.openstack.common.rpc import proxy
from neutron.plugins.common import constants
from neutron.services.loadbalancer.drivers import abstract_driver

LOG = logging.getLogger(__name__)

__VERSION__ = '0.1.1'

ACTIVE_PENDING = (
    constants.ACTIVE,
    constants.PENDING_CREATE,
    constants.PENDING_UPDATE
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


class LoadBalancerCallbacks(object):
    """Callbacks made by the agent to update the data model."""
    RPC_API_VERSION = '1.0'

    def __init__(self, plugin):
        LOG.debug('LoadBalancerCallbacks RPC subscriber initialized')
        self.plugin = plugin

    def create_rpc_dispatcher(self):
        return q_rpc.PluginRpcDispatcher(
            [self, agents_db.AgentExtRpcCallback(self.plugin)])

    @log.log
    def get_active_pending_pool_ids(self, context, tenant_ids=None):
        with context.session.begin(subtransactions=True):
            qry = (context.session.query(ldb.Pool.id).
                   join(ldb.Vip))
            qry = qry.filter(ldb.Vip.status.in_(ACTIVE_PENDING))
            qry = qry.filter(ldb.Pool.status.in_(ACTIVE_PENDING))
            up = True  # makes pep8 and sqlalchemy happy
            qry = qry.filter(ldb.Vip.admin_state_up == up)
            qry = qry.filter(ldb.Pool.admin_state_up == up)
            agents = self.plugin.get_lbaas_agents(context)
            if not agents:
                return []
            pool_ids = []
            for agent in agents:
                pools = self.plugin.list_pools_on_lbaas_agent(context,
                                                          agent.id)
                LOG.debug('looking through %s for tenant_ids %s'
                          % (pools, tenant_ids))

                for pool in pools['pools']:
                    if tenant_ids:
                        if not isinstance(tenant_ids, list):
                            tenant_ids = [tenant_ids]
                        if pool['tenant_id'] in tenant_ids:
                            pool_ids.append(pool['id'])
                    else:
                        if pool['id']:
                            pool_ids.append(pool['id'])
                        return pool_ids

            if len(pool_ids) > 0:
                qry = qry.filter(ldb.Pool.id.in_(pool_ids))
                return [pool_id for pool_id, in qry]
            else:
                return []

    @log.log
    def get_service_by_pool_id(self, context, pool_id=None,
                            activate=False, host=None,
                           **kwargs):
        with context.session.begin(subtransactions=True):
            qry = context.session.query(ldb.Pool)
            qry = qry.filter_by(id=pool_id)
            pool = qry.one()
            LOG.debug(_('setting service definition entry for %s' % pool))
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
            if pool.status != constants.ACTIVE:
                raise q_exc.Invalid(_('Expected active pool'))
            if pool.vip and (pool.vip.status != constants.ACTIVE):
                raise q_exc.Invalid(_('Expected active vip'))
            retval = {}
            retval['pool'] = self.plugin._make_pool_dict(pool)
            subnet_dict = self.plugin._core_plugin.get_subnet(context,
                                            retval['pool']['subnet_id'])
            retval['pool']['subnet'] = subnet_dict
            pool_subnet_fixed_ip_filters = {'network_id':
                                            [subnet_dict['network_id']],
                             'tenant_id': [subnet_dict['tenant_id']],
                             'device_id': [host]}
            retval['pool']['ports'] = self.plugin._core_plugin.get_ports(
                                                                   context,
                                      filters=pool_subnet_fixed_ip_filters)
            retval['pool']['network'] = self.plugin._core_plugin.get_network(
                            context, retval['pool']['subnet']['network_id'])
            if pool.vip:
                retval['vip'] = self.plugin._make_vip_dict(pool.vip)
                retval['vip']['port'] = (
                    self.plugin._core_plugin._make_port_dict(pool.vip.port)
                )
                retval['vip']['network'] = \
                 self.plugin._core_plugin.get_subnet(context,
                                        retval['vip']['port']['network_id'])
                retval['vip']['subnets'] = []
                for fixed_ip in retval['vip']['port']['fixed_ips']:
                    retval['vip']['subnets'].append(fixed_ip['subnet_id'])
                retval['vip']['subnets'] = \
                 self.plugin._core_plugin.get_subnets(context,
                                                 retval['vip']['subnets'])
            else:
                retval['vip'] = {}
                retval['vip']['port'] = {}
                retval['vip']['port']['network'] = {}
                retval['vip']['port']['subnets'] = []
            retval['members'] = []
            for m in pool.members:
                if m.status in (constants.ACTIVE,
                                constants.INACTIVE):
                    member = self.plugin._make_member_dict(m)
                    alloc_qry = context.session.query(models_v2.IPAllocation)
                    allocated = alloc_qry.filter_by(
                                        ip_address=member['address']).first()
                    member['subnet'] = \
                        self.plugin._core_plugin.get_subnet(
                                             context, allocated['subnet_id'])
                    member['network'] = \
                        self.plugin._core_plugin.get_subnet(
                                             context, allocated['network_id'])
                    retval['members'].append(member)
            retval['healthmonitors'] = [
                self.plugin._make_health_monitor_dict(hm.healthmonitor)
                for hm in pool.monitors
                if hm.status == constants.ACTIVE
            ]
            retval['vxlan_endpoints'] = self._get_vxlan_endpoints(context)
            retval['gre_endpoints'] = self._get_gre_endpoints(context)
            return retval

    @log.log
    def create_port(self, context, subnet_id=None,
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
                'device_id': host,
                'device_owner': 'network:f5lbaas',
                'fixed_ips': fixed_ips
            }
            port = self.plugin._core_plugin.create_port(context,
                                                        {'port': port_data})
            return port

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
    def allocate_fixed_address(self, context, subnet_id=None,
                               port_id=None, name=None,
                               fixed_address_count=1, host=None):
        if subnet_id:
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
            if not port_id:
                port = self.create_port(context,
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
    def deallocate_fixed_address(self, context, fixed_addresses=None,
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
                       'device_id': [host]}
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
        self.plugin._delete_db_pool_health_monitor(context,
                                                   health_monitor_id,
                                                   pool_id)

    @log.log
    def update_pool_stats(self, context, pool_id=None, stats=None, host=None):
        self.plugin.update_pool_stats(context, pool_id, stats)

    def _get_vxlan_endpoints(self, context):
        endpoints = []
        if hasattr(self.plugin._core_plugin, 'get_agents'):
            agents = self.plugin._core_plugin.get_agents(context)
            for agent in agents:
                if 'configurations' in agent:
                    if 'tunnel_types' in agent['configurations']:
                        if 'vxlan' in agent['configurations']['tunnel_types']:
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
                            endpoints.append(
                                     agent['configurations']['tunneling_ip'])
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

        # populate members and monitors
        for i in range(len(pool['members'])):
            member_id = pool['members'][i]
            pool['members'][i] = self.plugin.get_member(context, member_id)
        for i in range(len(pool['health_monitors'])):
            monitor_id = pool['health_monitors'][i]
            pool['health_monitors'][i] = self.plugin.get_health_monitor(
                                                     context, monitor_id)
        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        # populate members and monitors
        for i in range(len(pool['members'])):
            member_id = pool['members'][i]
            pool['members'][i] = self.plugin.get_member(context, member_id)
        for i in range(len(pool['health_monitors'])):
            monitor_id = pool['health_monitors'][i]
            pool['health_monitors'][i] = self.plugin.get_health_monitor(
                                                     context, monitor_id)

        # populate members and monitors for old_pool
        for i in range(len(old_pool['members'])):
            member_id = old_pool['members'][i]
            old_pool['members'][i] = self.plugin.get_member(context, member_id)
        for i in range(len(old_pool['health_monitors'])):
            monitor_id = old_pool['health_monitors'][i]
            old_pool['health_monitors'][i] = self.plugin.get_health_monitor(
                                                     context, monitor_id)

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
        agent = self.get_pool_agent(context, pool['id'])

        # populate members and monitors
        for i in range(len(pool['members'])):
            member_id = pool['members'][i]
            pool['members'][i] = self.plugin.get_member(context, member_id)
        for i in range(len(pool['health_monitors'])):
            monitor_id = pool['health_monitors'][i]
            pool['health_monitors'][i] = self.plugin.get_health_monitor(
                                                     context, monitor_id)

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

        member['pool'] = pool

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                pool_id=member['pool_id'],
                                                activate=False,
                                                host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_member(context, member, service, agent['host'])

    @log.log
    def update_member(self, context, old_member, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a 'was' pool structure for the rpc message
        old_pool = self._get_pool(context, old_member['pool_id'])

        if 'vip_id' in old_pool and old_pool['vip_id']:
            old_pool['vip'] = self._get_vip(context, old_pool['vip_id'])
        else:
            old_pool['vip'] = None
        old_member['pool'] = old_pool

        # populate a 'to be' pool structure for the rpc message
        pool = self._get_pool(context, member['pool_id'])

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

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

        if 'vip_id' in pool and pool['vip_id']:
            pool['vip'] = self._get_vip(context, pool['vip_id'])
        else:
            pool['vip'] = None

        # get the complete service definition from the data model
        service = self.callbacks.get_service_by_pool_id(context,
                                                        pool_id=pool_id,
                                                        activate=False,
                                                        host=agent['host'])

        # call the RPC proxy with the constructed message
        self.agent_rpc.get_pool_stats(context, pool, service, agent['host'])

    ################################
    # utility methods for this class
    ################################

    def _get_vip_network(self, context, vip, agent):
        subnet_dict = self.plugin._core_plugin.get_subnet(
                                                    context, vip['subnet_id'])
        port_dict = self.plugin._core_plugin.get_port(context, vip['port_id'])
        network_id = subnet_dict['network_id']
        network_dict = self.plugin._core_plugin.get_network(context,
                                                            network_id)
        if 'provider:physical_network' in network_dict:
            network_dict['physical_network'] = \
                network_dict['provider:physical_network']
        if 'provider:network_type' in network_dict:
            network_dict['network_type'] = \
                network_dict['provider:network_type']
        if 'provider:segmentation_id' in network_dict:
            network_dict['segmentation_id'] = \
                network_dict['provider:segmentation_id']
        network_dict['subnet'] = subnet_dict
        fixed_ip_dict = self._get_fixed_ips(context,
                                subnet_dict['tenant_id'],
                                subnet_dict['id'],
                                agent)
        network_dict['fixed_ips'] = fixed_ip_dict
        network_dict['port'] = port_dict
        network_dict['vxlan_endpoints'] = self._get_vxlan_endpoints(context)
        network_dict['gre_endpoints'] = self._get_gre_endpoints(context)
        return network_dict

    def _get_pool_network(self, context, pool, agent):
        subnet_dict = self.plugin._core_plugin.get_subnet(
                                        context, pool['subnet_id'])
        network_id = subnet_dict['network_id']
        network_dict = self.plugin._core_plugin.get_network(
                                                context, network_id)
        network_dict['subnet'] = subnet_dict
        if 'provider:physical_network' in network_dict:
            network_dict['physical_network'] = \
                network_dict['provider:physical_network']
        if 'provider:network_type' in network_dict:
            network_dict['network_type'] = \
                network_dict['provider:network_type']
        if 'provider:segmentation_id' in network_dict:
            network_dict['segmentation_id'] = \
                network_dict['provider:segmentation_id']
        fixed_ip_dict = self._get_fixed_ips(context,
                                subnet_dict['tenant_id'],
                                subnet_dict['id'],
                                agent)
        network_dict['fixed_ips'] = fixed_ip_dict
        network_dict['vxlan_endpoints'] = self._get_vxlan_endpoints(context)
        network_dict['gre_endpoints'] = self._get_gre_endpoints(context)
        return network_dict

    def _get_vip(self, context, vip_id):
        vip = self.plugin.get_vip(context, vip_id)
        if 'port_id' in vip:
            vip['port'] = self.plugin._core_plugin.get_port(context,
                                                            vip['port_id'])
        if 'subnet_id' in vip:
            vip['subnet'] = self.plugin._core_plugin.get_subnet(context,
                                                            vip['subnet_id'])
        vip['subnet']['network'] = \
           self.plugin._core_plugin.get_network(context,
                                                vip['subnet']['network_id'])
        return vip

    def _get_pool(self, context, pool_id):
        pool = self.plugin.get_pool(context, pool_id)
        for i in range(len(pool['members'])):
            member_id = pool['members'][i]
            pool['members'][i] = self.plugin.get_member(context, member_id)
        for i in range(len(pool['health_monitors'])):
            monitor_id = pool['health_monitors'][i]
            pool['health_monitors'][i] = self.plugin.get_health_monitor(
                                                     context, monitor_id)
        if 'subnet_id' in pool:
            pool['subnet'] = self.plugin._core_plugin.get_subnet(context,
                                                            pool['subnet_id'])
        pool['subnet']['network'] = \
           self.plugin._core_plugin.get_network(context,
                                                pool['subnet']['network_id'])

        return pool

    def _get_pools(self, context, tenant_id, subnet_id):
        filters = {'subnet_id': [subnet_id], 'tenant_id': [tenant_id]}
        pools = self.plugin.get_pools(context, filters=filters)
        return pools

    def _get_members(self, context, pool_id):
        filters = {'pool_id': [pool_id]}
        members = self.plugin.get_members(context, filters=filters)
        return members

    def _get_pool_dict(self, pool):
        return self.plugin._make_pool_dict(pool)

    def _get_port_dict_by_port_id(self, context, port_id):
        port = self.plugin._core_plugin.get_port(
                                        context, port_id)
        return self.plugin._core_plugin._make_port_dict(port)

    def _get_fixed_ips(self, context, tenant_id, subnet_id, agent):
        subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
        filters = {'network_id': [subnet['network_id']],
                  'tenant_id': [tenant_id],
                  'device_id': [agent['host']]}
        fixed_ips = self.plugin._core_plugin.get_ports(context,
                                                        filters=filters)
        if fixed_ips:
            return fixed_ips
        return None

    def _get_vxlan_endpoints(self, context):
        endpoints = []
        if hasattr(self.plugin._core_plugin, 'get_agents'):
            agents = self.plugin._core_plugin.get_agents(context)
            for agent in agents:
                if 'configurations' in agent:
                    if 'tunnel_types' in agent['configurations']:
                        if 'vxlan' in agent['configurations']['tunnel_types']:
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
                            endpoints.append(
                                     agent['configurations']['tunneling_ip'])
        return endpoints

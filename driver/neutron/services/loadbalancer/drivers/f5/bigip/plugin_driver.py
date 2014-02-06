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

import uuid

from oslo.config import cfg

from neutron.api.v2 import attributes
from neutron.common import constants as q_const
from neutron.common import exceptions as q_exc
from neutron.common import rpc as q_rpc
from neutron.db import agents_db
from neutron.db.loadbalancer import loadbalancer_db
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
                       '.drivers.f5.bigip.agent_scheduler'
                       '.TenantScheduler'),
               help=_('Driver to use for scheduling '
                      'pool to a default loadbalancer agent')),
    cfg.StrOpt('f5_loadbalancer_min_snat_addresses',
               default=1,
               help=_('How many SNAT addresses should'
                      'the loadbalancer allocate per'
                      'pool subnet.'))
]

cfg.CONF.register_opts(OPTS)

# topic name for this particular agent implementation
TOPIC_PROCESS_ON_HOST = 'q-lbaas-bigip'
TOPIC_LOADBALANCER_AGENT = 'lbaas_bigip_agent'

SNAT_PORT_NAME = 'lb-snat-'


class LoadBalancerCallbacks(object):
    """Callback made by the agent to update the data model."""
    RPC_API_VERSION = '1.0'

    def __init__(self, plugin):
        LOG.debug('LoadBalancerCallbacks RPC subscriber called')
        self.plugin = plugin

    def create_rpc_dispatcher(self):
        return q_rpc.PluginRpcDispatcher(
            [self, agents_db.AgentExtRpcCallback(self.plugin)])

    @log.log
    def get_ready_services(self, context, tenant_ids=None):
        with context.session.begin(subtransactions=True):
            qry = (context.session.query(loadbalancer_db.Pool.id).
                   join(loadbalancer_db.Vip))
            qry = qry.filter(loadbalancer_db.Vip.status.in_(ACTIVE_PENDING))
            qry = qry.filter(loadbalancer_db.Pool.status.in_(ACTIVE_PENDING))
            up = True  # makes pep8 and sqlalchemy happy
            qry = qry.filter(loadbalancer_db.Vip.admin_state_up == up)
            qry = qry.filter(loadbalancer_db.Pool.admin_state_up == up)
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
                qry = qry.filter(loadbalancer_db.Pool.id.in_(pool_ids))
                return [pool_id for pool_id, in qry]
            else:
                return []

    @log.log
    def get_logical_service(self, context, pool_id=None, activate=True,
                           **kwargs):
        with context.session.begin(subtransactions=True):
            qry = context.session.query(loadbalancer_db.Pool)
            qry = qry.filter_by(id=pool_id)
            pool = qry.one()
            LOG.debug(_('setting logical_service entry for %s' % pool))
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
            snat_subnet_id = retval['pool']['subnet_id']
            snat_filters = {'network_id': [subnet_dict['network_id']],
                             'tenant_id': [subnet_dict['tenant_id']],
                             'name': [SNAT_PORT_NAME + snat_subnet_id]}
            snats_dict = self.plugin._core_plugin.get_ports(context,
                                                    filters=snat_filters)
            retval['snats'] = snats_dict
            if pool.vip:
                retval['vip'] = self.plugin._make_vip_dict(pool.vip)
                retval['vip']['port'] = (
                    self.plugin._core_plugin._make_port_dict(pool.vip.port)
                )
                for fixed_ip in retval['vip']['port']['fixed_ips']:
                    vip_subnet_dict = self.plugin._core_plugin.get_subnet(
                        context,
                        fixed_ip['subnet_id']
                    )
                    fixed_ip['subnet'] = vip_subnet_dict
            else:
                retval['vip'] = {}
                retval['vip']['port'] = {}
                retval['vip']['port']['subnet'] = {}
            retval['members'] = [
                self.plugin._make_member_dict(m)
                for m in pool.members if m.status in (constants.ACTIVE,
                                                      constants.INACTIVE)
            ]
            retval['healthmonitors'] = [
                self.plugin._make_health_monitor_dict(hm.healthmonitor)
                for hm in pool.monitors
                if hm.status == constants.ACTIVE
            ]
            vxlan_endpoints = self._get_gre_endpoints(context)
            retval['vxlan_endpoints'] = vxlan_endpoints
            LOG.debug(_('vxlan_endpoints: %s' % vxlan_endpoints))
            retval['gre_endpoints'] = self._get_gre_endpoints(context)
            return retval

    @log.log
    def pool_destroyed(self, context, pool_id=None, host=None):
        """Agent confirmation hook that a pool has been destroyed.

        This method exists for subclasses to change the deletion
        behavior.
        """
        # TODO: jgruber - 01-29-2014 data model validation.
        pass

    @log.log
    def plug_vip_port(self, context, port_id=None, host=None):
        """Agent confirmation hook that vip has been provisioned."""
        if not port_id:
            return

        try:
            port = self.plugin._core_plugin.get_port(
                context,
                port_id
            )
        except q_exc.PortNotFound:
            msg = _('Unable to find port %s to plug.')
            LOG.debug(msg, port_id)
            return

        port['admin_state_up'] = True
        port['device_owner'] = 'neutron:' + constants.LOADBALANCER
        port['device_id'] = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(host)))

        self.plugin._core_plugin.update_port(
            context,
            port_id,
            {'port': port}
        )

    @log.log
    def unplug_vip_port(self, context, port_id=None, host=None):
        """"Agent confirmation that a vip has been deprovisioned"""
        if not port_id:
            return

        try:
            port = self.plugin._core_plugin.get_port(
                context,
                port_id
            )
        except q_exc.PortNotFound:
            msg = _('Unable to find port %s to unplug.  This can occur when '
                    'the Vip has been deleted first.')
            LOG.debug(msg, port_id)
            return

        port['admin_state_up'] = False
        port['device_owner'] = ''
        port['device_id'] = ''

        try:
            self.plugin._core_plugin.update_port(
                context,
                port_id,
                {'port': port}
            )

        except q_exc.PortNotFound:
            msg = _('Unable to find port %s to unplug.  This can occur when '
                    'the Vip has been deleted first.')
            LOG.debug(msg, port_id)

    @log.log
    def update_pool_stats(self, context, pool_id=None, stats=None, host=None):
        """Agent update of pool stats.

           The stats structure should look like this example
           stats = {"bytes_in": 0,
                 "bytes_out": 0,
                 "active_connections": 0,
                 "total_connections": 0}

        """
        pass

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
    def create_vip(self, context, vip, network, host):
        return self.cast(
            context,
            self.make_msg('create_vip', vip=vip, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_vip(self, context, old_vip, vip, old_network, network, host):
        return self.cast(
            context,
            self.make_msg('update_vip', old_vip=old_vip, vip=vip,
                          old_network=old_network, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_vip(self, context, vip, network, host):
        return self.cast(
            context,
            self.make_msg('delete_vip', vip=vip, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_pool(self, context, pool, network, host):
        return self.cast(
            context,
            self.make_msg('create_pool', pool=pool, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_pool(self, context, old_pool, pool, old_network, network, host):
        return self.cast(
            context,
            self.make_msg('update_pool', old_pool=old_pool, pool=pool,
                          old_network=old_network, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_pool(self, context, pool, network, host):
        return self.cast(
            context,
            self.make_msg('delete_pool', pool=pool, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_member(self, context, member, network, host):
        return self.cast(
            context,
            self.make_msg('create_member', member=member, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_member(self, context, old_member, member, old_network,
                      network, host):
        return self.cast(
            context,
            self.make_msg('update_member', old_member=old_member,
                          member=member, old_network=old_network,
                          network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_member(self, context, member, network, host):
        return self.cast(
            context,
            self.make_msg('delete_member', member=member, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool,
                                   network, host):
        return self.cast(
            context,
            self.make_msg('create_pool_health_monitor',
                          health_monitor=health_monitor, pool=pool,
                          network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool, network, host):
        return self.cast(
            context,
            self.make_msg('update_health_monitor',
                          old_health_monitor=old_health_monitor,
                          health_monitor=health_monitor,
                          pool=pool, network=network),
            topic='%s.%s' % (self.topic, host)
        )

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor, pool,
                                   network, host):
        return self.cast(
            context,
            self.make_msg('delete_pool_health_monitor',
                          health_monitor=health_monitor,
                          pool=pool, network=network),
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
    def get_pool_stats(self, context, pool, host):
        return self.cast(
                         context,
                         self.make_msg('get_pool_stats',
                                       pool=pool),
                         topic='%s.%s' % (self.topic, host)
                         )


class BigIPPluginDriver(abstract_driver.LoadBalancerAbstractDriver):
    """ Plugin Driver for LBaaS.

        This class implements the methods found in the abstract
        parent class.

        This class interacts with the data model through the
        core plugin, creates messages to send to agents and then
        invokes the LoadBalancerAgentApi class methods to
        send the RPC messages.
    """
    def __init__(self, plugin):
        LOG.debug('Initializing BigIPPluginDriver')

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
        LOG.debug('agent for call is %s' % agent)

        if not agent:
            raise lbaas_agentscheduler.NoActiveLbaasAgent(pool_id=pool_id)
        return agent['agent']

    @log.log
    def create_vip(self, context, vip):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        # populate a network structure for the rpc message
        network = self._get_vip_network(context, vip)

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_vip(context, vip, network, agent['host'])

    @log.log
    def update_vip(self, context, old_vip, vip):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        # populate a 'was' network structure for the rpc message
        old_network = self._get_vip_network(context, old_vip)

        # populate a 'to be' network structure for the rpc message
        network = self._get_vip_network(context, vip)

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_vip(context, old_vip, vip, old_network,
                                  network, agent['host'])

    @log.log
    def delete_vip(self, context, vip):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, vip['pool_id'])

        # populate a network structure for the rpc message
        network = self._get_vip_network(context, vip)

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_vip(context, vip, network, agent['host'])

        # delete the vip from the data model
        self.plugin._delete_db_vip(context, vip['id'])

    @log.log
    def create_pool(self, context, pool):
        # which agent should handle provisioning
        agent = self.pool_scheduler.schedule(self.plugin, context, pool)
        if not agent:
            raise lbaas_agentscheduler.NoEligibleLbaasAgent(pool_id=pool['id'])

        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_pool(context, pool, network, agent['host'])

    @log.log
    def update_pool(self, context, old_pool, pool):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool['id'])

        # populate a 'was' network structure for the rpc message
        old_network = self._get_pool_network(context, old_pool)

        # populate a 'to be' network structure for the rpc message
        network = self._get_pool_network(context, pool)

        if pool['subnet_id'] != old_pool['subnet_id']:
            # see if there are pools on this subnet
            existing_pools = self._get_pools(context, pool['tenant_id'],
                                             pool['subnet_id'])
            if not existing_pools:
                # signal the agent to remove a snat pool
                # if no pools exist anymore in the data model
                self._remove_snat(context, pool['tenant_id'],
                                  pool['subnet_id'])
                old_network['remove_snat_pool'] = pool['subnet_id']

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_pool(context, old_pool, pool, old_network,
                                   network, agent['host'])

    @log.log
    def delete_pool(self, context, pool):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool['id'])

        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # delete the pool from the data model
        self.plugin._delete_db_pool(context, pool['id'])

        # see if there are any other pools on this subnet
        existing_pools = self._get_pools(context, pool['tenant_id'],
                                             pool['subnet_id'])
        if not existing_pools:
            # signal the agent to remove a snat pool
            # if no pools exist anymore in the data model
            self._remove_snat(context, pool['tenant_id'],
                              pool['subnet_id'])
            network['remove_snat_pool'] = pool['subnet_id']

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_pool(context, pool, network, agent['host'])

    @log.log
    def create_member(self, context, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a pool structure for the rpc message
        pool = self.plugin.get_pool(context, member['pool_id'])
        member['pool'] = pool
        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_member(context, member, network, agent['host'])

    @log.log
    def update_member(self, context, old_member, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a 'was' pool structure for the rpc message
        old_pool = self.plugin.get_pool(context, old_member['pool_id'])
        old_member['pool'] = old_pool

        # populate a 'to be' pool structure for the rpc message
        pool = self.plugin.get_pool(context, member['pool_id'])
        member['pool'] = pool

        # populate a 'was' network structure for the rpc message
        old_network = self._get_pool_network(context, old_pool)
        # populate a 'to be' network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_member(context, old_member, member,
                                     old_network, network, agent['host'])

    @log.log
    def delete_member(self, context, member):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, member['pool_id'])

        # populate a pool structure for the rpc message
        pool = self.plugin.get_pool(context, member['pool_id'])
        member['pool'] = pool

        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_member(context, member,
                                     network, agent['host'])

        # delete the pool member from the data model
        self.plugin._delete_db_member(context, member['id'])

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool strucutre for the rpc message
        pool = self.plugin.get_pool(context, pool_id)
        pool_dict = pool

        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.create_pool_health_monitor(context, health_monitor,
                                                  pool_dict, network,
                                                  agent['host'])

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self.plugin.get_pool(context, pool_id)
        pool_dict = pool

        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.update_health_monitor(context, old_health_monitor,
                                             health_monitor, pool_dict,
                                             network, agent['host'])

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool = self.plugin.get_pool(context, pool_id)
        pool_dict = pool

        # populate a network structure for the rpc message
        network = self._get_pool_network(context, pool)

        # call the RPC proxy with the constructed message
        self.agent_rpc.delete_pool_health_monitor(context, health_monitor,
                                                  pool_dict, network,
                                                  agent['host'])

        # delete the health monitor from the data model
        self.plugin._delete_db_pool_health_monitor(context,
                                                   health_monitor['id'],
                                                   pool_id)

    @log.log
    def stats(self, context, pool_id):
        # which agent should handle provisioning
        agent = self.get_pool_agent(context, pool_id)

        # populate a pool structure for the rpc message
        pool_dict = self.plugin.get_pool(context, pool_id)

        # call the RPC proxy with the constructed message
        self.agent_rpc.get_pool_stats(context, pool_dict, agent['host'])

    ################################
    # utility methods for this class
    ################################

    def _get_vip_network(self, context, vip):
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
        network_dict['port'] = port_dict
        network_dict['vxlan_endpoints'] = self._get_vxlan_endpoints(context)
        network_dict['gre_endpoints'] = self._get_gre_endpoints(context)
        return network_dict

    def _get_pool_network(self, context, pool):
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
        snats_dict = self._get_snats(context,
                                subnet_dict['tenant_id'],
                                subnet_dict['id'])
        network_dict['snats'] = snats_dict
        network_dict['vxlan_endpoints'] = self._get_vxlan_endpoints(context)
        network_dict['gre_endpoints'] = self._get_gre_endpoints(context)
        return network_dict

    def _get_pools(self, context, tenant_id, subnet_id):
        filters = {'subnet_id': [subnet_id], 'tenant_id': [tenant_id]}
        pools = self.plugin.get_pools(context, filters=filters)
        return pools

    def _get_pool_dict(self, pool):
        return self.plugin._make_pool_dict(pool)

    def _get_port_dict_by_port_id(self, context, port_id):
        port = self.plugin._core_plugin.get_port(
                                        context, port_id)
        return self.plugin._core_plugin._make_port_dict(port)

    def _get_snats(self, context, tenant_id, subnet_id):
        subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
        filters = {'network_id': [subnet['network_id']],
                  'tenant_id': [tenant_id],
                  'name': [SNAT_PORT_NAME + subnet_id]}
        snats = self.plugin._core_plugin.get_ports(context,
                                                        filters=filters)
        if snats:
            return snats
        return None

    def _create_snat(self, context, tenant_id,
                     subnet_id, ip_address=None):
            subnet = self.plugin._core_plugin.get_subnet(context, subnet_id)
            fixed_ip = {'subnet_id': subnet['id']}
            if ip_address and ip_address != attributes.ATTR_NOT_SPECIFIED:
                fixed_ip['ip_address'] = ip_address
            else:
                count = cfg.CONF.f5_loadbalancer_min_snat_addresses
                if count > 1:
                    fixed_ips = []
                    for _ in range(0, count):
                        fixed_ips.append(fixed_ip)
                else:
                    fixed_ips = [fixed_ip]
            port_data = {
                'tenant_id': tenant_id,
                'name': SNAT_PORT_NAME + subnet_id,
                'network_id': subnet['network_id'],
                'mac_address': attributes.ATTR_NOT_SPECIFIED,
                'admin_state_up': False,
                'device_id': '',
                'device_owner': '',
                'fixed_ips': fixed_ips
            }
            port = self.plugin._core_plugin.create_port(context,
                                                        {'port': port_data})
            return port

    def _remove_snat(self, context, tenant_id,
                     subnet_id, ip_address=None):
        snats = self._get_snats(context, tenant_id, subnet_id)
        if snats:
            for snat in snats:
                if ip_address:
                    if 'fixed_ips' in snat:
                        for fixed_ip in snat['fixed_ips']:
                            if fixed_ip == ip_address:
                                self.plugin._core_plugin.delete_port(
                                                                     context,
                                                                     snat['id']
                                                                     )
                else:
                    self.plugin._core_plugin.delete_port(context,
                                                             snat['id'])

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

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

import weakref

from oslo.config import cfg
from neutron.agent import rpc as agent_rpc
from neutron.common import constants as neutron_constants
from neutron.plugins.common import constants as plugin_const
from neutron import context
from neutron.openstack.common import importutils
from neutron.common import log
from neutron.common import topics
from neutron.openstack.common import log as logging
from neutron.openstack.common import loopingcall
from neutron.openstack.common import periodic_task
from neutron.openstack.common.rpc import dispatcher

from neutron.services.loadbalancer.drivers.f5.bigip import agent_api
from neutron.services.loadbalancer.drivers.f5.bigip import constants
from neutron.services.loadbalancer.drivers.f5 import plugin_driver

LOG = logging.getLogger(__name__)

__VERSION__ = "0.1.1"

# configuration options useful to all drivers
OPTS = [
    cfg.StrOpt(
        'f5_bigip_lbaas_device_driver',
        default=('neutron.services.loadbalancer.drivers'
                 '.f5.bigip.icontrol_driver.iControlDriver'),
        help=_('The driver used to provision BigIPs'),
    ),
    cfg.BoolOpt(
        'l2_population',
        default=False,
        help=_('Use L2 Populate service for fdb entries on the BIG-IP')
    ),
    cfg.BoolOpt(
        'f5_global_routed_mode',
        default=False,
        help=_('Disable all L2 and L3 integration in favor or global routing')
    ),
    cfg.BoolOpt(
        'use_namespaces',
        default=True,
        help=_('Allow overlapping IP addresses for tenants')
    ),
    cfg.BoolOpt(
        'f5_snat_mode',
        default=True,
        help=_('use SNATs, not direct routed mode')
    ),
    cfg.IntOpt(
        'f5_snat_addresses_per_subnet',
        default='1',
        help=_('Interface and VLAN for the VTEP overlay network')
    )
]


class LogicalServiceCache(object):
    """Manage a cache of known services."""

    class Service(object):
        """Inner classes used to hold values for weakref lookups."""
        def __init__(self, port_id, pool_id, tenant_id):
            self.port_id = port_id
            self.pool_id = pool_id
            self.tenant_id = tenant_id

        def __eq__(self, other):
            return self.__dict__ == other.__dict__

        def __hash__(self):
            return hash((self.port_id, self.pool_id, self.tenant_id))

    def __init__(self):
        LOG.debug(_("Initializing LogicalServiceCache version %s"
                    % __VERSION__))
        self.services = set()
        self.port_lookup = weakref.WeakValueDictionary()
        self.pool_lookup = weakref.WeakValueDictionary()

    def put(self, service):
        if 'port_id' in service['vip']:
            port_id = service['vip']['port_id']
        else:
            port_id = None
        pool_id = service['pool']['id']
        tenant_id = service['pool']['tenant_id']
        s = self.Service(port_id, pool_id, tenant_id)
        if s not in self.services:
            self.services.add(s)
            if port_id:
                self.port_lookup[port_id] = s
            self.pool_lookup[pool_id] = s

    def remove(self, service):
        if not isinstance(service, self.Service):
            if 'port_id' in service['vip']:
                port_id = service['vip']['port_id']
            else:
                port_id = None
            service = self.Service(
                port_id, service['pool']['id'],
                service['pool']['tenant_id']
            )
        if service in self.services:
            self.services.remove(service)

    def remove_by_pool_id(self, pool_id):
        s = self.pool_lookup.get(pool_id)
        if s:
            self.services.remove(s)

    def get_by_pool_id(self, pool_id):
        return self.pool_lookup.get(pool_id)

    def get_by_port_id(self, port_id):
        return self.port_lookup.get(port_id)

    def get_pool_ids(self):
        return self.pool_lookup.keys()

    def get_tenant_ids(self):
        tenant_ids = {}
        for service in self.services:
            tenant_ids[service.tenant_id] = 1
        return tenant_ids.keys()


class LbaasAgentManager(periodic_task.PeriodicTasks):

    # history
    #   1.0 Initial version
    #   1.1 Support agent_updated call
    RPC_API_VERSION = '1.1'

    def __init__(self, conf):
        LOG.debug(_('Initializing LbaasAgentManager with conf %s' % conf))
        self.conf = conf
        try:
            self.driver = importutils.import_object(
                conf.f5_bigip_lbaas_device_driver, self.conf)
            self.agent_host = conf.host + ":" + self.driver.agent_id
        except ImportError:
            msg = _('Error importing loadbalancer device driver: %s')
            raise SystemExit(msg % conf.f5_bigip_lbaas_device_driver)

        self.agent_state = {
            'binary': 'f5-bigip-lbaas-agent',
            'host': self.agent_host,
            'topic': plugin_driver.TOPIC_LOADBALANCER_AGENT,
            'agent_type': neutron_constants.AGENT_TYPE_LOADBALANCER,
            'start_flag': True}

        self.admin_state_up = True
        self.driver.l2pop = conf.l2_population

        if self.driver.l2pop:
            self.agent_state['l2_population'] = True
        else:
            self.agent_state['l2_population'] = False

        self.context = context.get_admin_context_without_session()
        # pass context to driver
        self.driver.context = self.context
        # create the cache of provisioned services
        self.cache = LogicalServiceCache()
        # setup all rpc and callback objects
        self._setup_rpc()
        # cause a sync of what Neutron believes
        # needs to be handled by this agent
        self.needs_resync = True

    @log.log
    def _setup_rpc(self):

        # LBaaS Callbacks API
        self.plugin_rpc = agent_api.LbaasAgentApi(
            plugin_driver.TOPIC_PROCESS_ON_HOST,
            self.context,
            self.agent_host
        )
        self.driver.plugin_rpc = self.plugin_rpc

        # Core plugin Callbacks API
        self.driver.tunnel_rpc = agent_api.CoreAgentApi(topics.PLUGIN)

        # L2 Populate plugin Callbacks API
        if self.driver.l2pop:
            self.driver.l2pop_rpc = agent_api.L2PopulationApi()

        # Agent state Callbacks API
        self.state_rpc = agent_rpc.PluginReportStateAPI(
            plugin_driver.TOPIC_PROCESS_ON_HOST)
        report_interval = self.conf.AGENT.report_interval
        if report_interval:
            heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            heartbeat.start(interval=report_interval)

        # Besides LBaaS Plugin calls... what else to consume

        # tunnel updates to support vxlan and gre endpoint
        # NOTE:  the driver can decide to handle endpoint
        # membership based on the rpc notification or through
        # other means (i.e. as part of a service definition)
        consumers = [[constants.TUNNEL, topics.UPDATE]]

        # L2 populate fdb calls
        # NOTE:  the driver can decide to handle fdb updates
        # or use some other mechanism (i.e. flooding) to
        # learn about port updates.
        if self.driver.l2pop:
            consumers.append([topics.L2POPULATION,
                              topics.UPDATE, cfg.CONF.host])

        agent_rpc.create_consumers(dispatcher.RpcDispatcher([self]),
                                   plugin_driver.TOPIC_LOADBALANCER_AGENT,
                                   consumers)

    def _report_state(self):
        try:
            # assure agent is connected:
            if not self.driver.connected:
                self.driver._init_connection()

            service_count = len(self.cache.services)
            self.agent_state['configurations'] = {
                            'device_driver': self.driver.__class__.__name__,
                            'device_type': self.driver.device_type}
            self.agent_state['configurations']['services'] = service_count
            if self.driver.l2pop:
                self.agent_state['configurations']['l2_population'] = True
            else:
                self.agent_state['configurations']['l2_population'] = False
            if self.driver.agent_configurations:
                self.agent_state['configurations'].update(
                                             self.driver.agent_configurations)
            LOG.debug(_('reporting state of agent as: %s' % self.agent_state))
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.exception(_("Failed reporting state!"))

    def initialize_service_hook(self, started_by):
        self.sync_state()

    @periodic_task.periodic_task
    def periodic_resync(self, context):
        if self.needs_resync:
            self.needs_resync = False
            if self.tunnel_sync():
                self.needs_resync = True
            if self.sync_state():
                self.needs_resync = True

    @periodic_task.periodic_task(spacing=6)
    def collect_stats(self, context):
        pool_ids = self.cache.get_pool_ids()
        LOG.debug('collecting stats on pools: %s' % pool_ids)
        for pool_id in pool_ids:
            try:
                stats = self.driver.get_stats(
                        self.plugin_rpc.get_service_by_pool_id(pool_id))
                if stats:
                    self.plugin_rpc.update_pool_stats(pool_id, stats)
            except Exception:
                LOG.exception(_('Error upating stats'))
                self.needs_resync = True

    @periodic_task.periodic_task(spacing=600)
    def backup_configuration(self, context):
        self.driver.backup_configuration()

    def tunnel_sync(self):
        return self.driver.tunnel_sync()

    def sync_state(self):
        resync = False
        known_services = set(self.cache.get_pool_ids())
        try:
            ready_pool_ids = set(
                    self.plugin_rpc.get_active_pending_pool_ids())
            LOG.debug(_('plugin produced the list of active pool ids: %s'
                        % ready_pool_ids))
            LOG.debug(_('currently known pool ids are: %s' % known_services))
            for deleted_id in known_services - ready_pool_ids:
                self.destroy_service(deleted_id)
            for pool_id in ready_pool_ids:
                self.refresh_service(pool_id)
        except Exception:
            LOG.exception(_('Unable to retrieve ready services'))
            resync = True
        return resync
        self.remove_orphans()

    @log.log
    def refresh_service(self, pool_id):
        try:
            service = self.plugin_rpc.get_service_by_pool_id(pool_id)
            # update is create or update
            self.driver.sync(service)
            self.cache.put(service)
        except Exception:
            LOG.exception(_('Unable to refresh service for pool: %s'), pool_id)
            self.needs_resync = True

    @log.log
    def destroy_service(self, pool_id):
        service = self.plugin_rpc.get_service_by_pool_id(pool_id)
        if not service:
            return
        try:
            self.driver.delete_pool(pool_id,
                                    service)
            self.plugin_rpc.pool_destroyed(pool_id)
        except Exception:
            LOG.exception(_('Unable to destroy service for pool: %s'), pool_id)
            self.needs_resync = True
        self.cache.remove(service)

    @log.log
    def remove_orphans(self):
        try:
            self.driver.remove_orphans(self.cache.get_pool_ids())
        except NotImplementedError:
            pass  # Not all drivers will support this

    @log.log
    def reload_pool(self, context, pool_id=None, host=None):
        """Handle RPC cast from plugin to reload a pool."""
        if host and host == self.agent_host:
            if pool_id:
                self.refresh_service(pool_id)

    @log.log
    def get_pool_stats(self, pool, service):
        try:
            stats = self.driver.get_stats(pool, service)
            if stats:
                    self.plugin_rpc.update_pool_stats(pool['id'], stats)
        except Exception as e:
            message = 'could not get pool stats:' + e.message
            self.plugin_rpc.update_pool_status(pool['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def create_vip(self, context, vip, service):
        """Handle RPC cast from plugin to create_vip"""
        try:
            self.driver.create_vip(vip, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not create VIP:' + e.message
            self.plugin_rpc.update_vip_status(vip['id'],
                                              plugin_const.ERROR,
                                              message)

    @log.log
    def update_vip(self, context, old_vip, vip, service):
        """Handle RPC cast from plugin to update_vip"""
        try:
            self.driver.update_vip(old_vip, vip, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not update VIP: ' + e.message
            self.plugin_rpc.update_vip_status(vip['id'],
                                              plugin_const.ERROR,
                                              message)

    @log.log
    def delete_vip(self, context, vip, service):
        """Handle RPC cast from plugin to delete_vip"""
        try:
            self.driver.delete_vip(vip, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not delete VIP:' + e.message
            self.plugin_rpc.update_vip_status(vip['id'],
                                              plugin_const.ERROR,
                                              message)

    @log.log
    def create_pool(self, context, pool, service):
        """Handle RPC cast from plugin to create_pool"""
        try:
            self.driver.create_pool(pool, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not create pool:' + e.message
            self.plugin_rpc.update_pool_status(pool['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def update_pool(self, context, old_pool, pool, service):
        """Handle RPC cast from plugin to update_pool"""
        try:
            self.driver.update_pool(old_pool, pool, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not update pool:' + e.message
            self.plugin_rpc.update_pool_status(old_pool['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def delete_pool(self, context, pool, service):
        """Handle RPC cast from plugin to delete_pool"""
        try:
            self.driver.delete_pool(pool, service)
            self.cache.remove_by_pool_id(pool['id'])
        except Exception as e:
            message = 'could not delete pool:' + e.message
            self.plugin_rpc.update_pool_status(pool['id'],
                                              plugin_const.ERROR,
                                              message)

    @log.log
    def create_member(self, context, member, service):
        """Handle RPC cast from plugin to create_member"""
        try:
            self.driver.create_member(member, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not create member:' + e.message
            self.plugin_rpc.update_member_status(member['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def update_member(self, context, old_member, member, service):
        """Handle RPC cast from plugin to update_member"""
        try:
            self.driver.update_member(old_member, member, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not update member:' + e.message
            self.plugin_rpc.update_member_status(old_member['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def delete_member(self, context, member, service):
        """Handle RPC cast from plugin to delete_member"""
        try:
            self.driver.delete_member(member, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not delete member:' + e.message
            self.plugin_rpc.update_member_status(member['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def create_pool_health_monitor(self, context, health_monitor,
                                   pool, service):
        """Handle RPC cast from plugin to create_pool_health_monitor"""
        try:
            self.driver.create_pool_health_monitor(health_monitor,
                                                   pool, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not create health monitor:' + e.message
            self.plugin_rpc.update_health_monitor_status(
                                               pool['id'],
                                               health_monitor['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool, service):
        """Handle RPC cast from plugin to update_health_monitor"""
        try:
            self.driver.update_health_monitor(old_health_monitor,
                                                 health_monitor,
                                                 pool, service)
            self.cache.put(service)
        except Exception as e:
            message = 'could not update health monitor:' + e.message
            self.plugin_rpc.update_health_monitor_status(
                                                    pool['id'],
                                                    old_health_monitor['id'],
                                                    plugin_const.ERROR,
                                                    message)

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor,
                                   pool, service):
        """Handle RPC cast from plugin to delete_pool_health_monitor"""
        try:
            self.driver.delete_pool_health_monitor(health_monitor,
                                                      pool, service)
        except Exception as e:
            message = 'could not delete health monitor:' + e.message
            self.plugin_rpc.update_health_monitor_status(pool['id'],
                                                         health_monitor['id'],
                                                         plugin_const.ERROR,
                                                         message)

    @log.log
    def agent_updated(self, context, payload):
        """Handle the agent_updated notification event."""
        if payload['admin_state_up'] != self.admin_state_up:
            self.admin_state_up = payload['admin_state_up']
            if self.admin_state_up:
                self.needs_resync = True
            else:
                for pool_id in self.cache.get_pool_ids():
                    self.destroy_service(pool_id)
            LOG.info(_("agent_updated by server side %s!"), payload)

    @log.log
    def tunnel_update(self, context, tunnel_ip, tunnel_id, tunnel_type):
        pass

    @log.log
    def fdb_add(self, context, fdb_entries):
        pass

    @log.log
    def fdb_remove(self, context, fdb_entries):
        pass

    @log.log
    def fdb_update(self, context, fdb_entries):
        pass

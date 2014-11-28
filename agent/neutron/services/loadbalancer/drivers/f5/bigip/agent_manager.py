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

import datetime

preJuno = False
try:
    from neutron.openstack.common.rpc import dispatcher
    preJuno = True
except:
    from neutron.common import rpc as n_rpc
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
    ),
    cfg.StrOpt(
        'static_agent_configuration_data',
        default=None,
        help=_(
    'static name:value entries to add to the agent configurations dictionary')
    ),
    cfg.IntOpt(
        'service_resync_interval',
        default=300,
        help=_('Number of seconds between service refresh check')
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
        self.services = {}

    @property
    def size(self):
        return len(self.services)

    def put(self, service):
        if 'port_id' in service['vip']:
            port_id = service['vip']['port_id']
        else:
            port_id = None
        pool_id = service['pool']['id']
        tenant_id = service['pool']['tenant_id']
        if not pool_id in self.services:
            s = self.Service(port_id, pool_id, tenant_id)
            self.services[pool_id] = s
        else:
            s = self.services[pool_id]
            s.tenant_id = tenant_id
            s.port_id = port_id

    def remove(self, service):
        if not isinstance(service, self.Service):
            pool_id = service['pool']['id']
        else:
            pool_id = service.pool_id
        if pool_id in self.services:
            del(self.services[pool_id])

    def remove_by_pool_id(self, pool_id):
        if pool_id in self.services:
            del(self.services[pool_id])

    def get_by_pool_id(self, pool_id):
        if pool_id in self.services:
            return self.services[pool_id]
        else:
            return None

    #def get_by_port_id(self, port_id):
    #    return self.port_lookup.get(port_id)

    def get_pool_ids(self):
        return self.services.keys()

    def get_tenant_ids(self):
        tenant_ids = {}
        for service in self.services:
            tenant_ids[service.tenant_id] = 1
        return tenant_ids.keys()


class LbaasAgentManagerBase(periodic_task.PeriodicTasks):

    # history
    #   1.0 Initial version
    #   1.1 Support agent_updated call
    RPC_API_VERSION = '1.1'

    # Not using __init__ in order to avoid complexities with super().
    # See derived classes after this class
    def do_init(self, conf):
        LOG.info(_('Initializing LbaasAgentManager with conf %s' % conf))
        self.conf = conf

        # create the cache of provisioned services
        self.cache = LogicalServiceCache()
        self.last_resync = datetime.datetime.now()
        self.needs_resync = False
        self.plugin_rpc = None

        if conf.service_resync_interval:
            self.service_resync_interval = conf.service_resync_interval
        else:
            self.service_resync_interval = constants.RESYNC_INTERVAL
        LOG.debug('setting service resync interval to %d seconds'
                                      % self.service_resync_interval)

        try:
            self.lbdriver = importutils.import_object(
                conf.f5_bigip_lbaas_device_driver, self.conf)
            if self.lbdriver.agent_id:
                self.agent_host = conf.host + ":" + self.lbdriver.agent_id
                LOG.debug('setting agent host to %s' % self.agent_host)
            else:
                self.agent_host = None
                LOG.error(_('Driver did not initialize. Fix the driver config '
                            'and restart the agent.'))
                return
        except ImportError:
            msg = _('Error importing loadbalancer device driver: %s')
            raise SystemExit(msg % conf.f5_bigip_lbaas_device_driver)

        agent_configurations = \
               {'global_routed_mode': self.conf.f5_global_routed_mode}

        if self.conf.static_agent_configuration_data:
            entries = \
              str(self.conf.static_agent_configuration_data).split(',')
            for entry in entries:
                nv = entry.strip().split(':')
                if len(nv) > 1:
                    agent_configurations[nv[0]] = nv[1]

        self.agent_state = {
            'binary': 'f5-bigip-lbaas-agent',
            'host': self.agent_host,
            'topic': plugin_driver.TOPIC_LOADBALANCER_AGENT,
            'agent_type': neutron_constants.AGENT_TYPE_LOADBALANCER,
            'l2_population': self.conf.l2_population,
            'configurations': agent_configurations,
            'start_flag': True}

        self.admin_state_up = True

        self.context = context.get_admin_context_without_session()
        # pass context to driver
        self.lbdriver.context = self.context

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
        self.lbdriver.plugin_rpc = self.plugin_rpc

        # Agent state Callbacks API
        self.state_rpc = agent_rpc.PluginReportStateAPI(
            plugin_driver.TOPIC_PROCESS_ON_HOST)
        report_interval = self.conf.AGENT.report_interval
        if report_interval:
            heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            heartbeat.start(interval=report_interval)

        if not self.conf.f5_global_routed_mode:
            # Core plugin Callbacks API
            self.lbdriver.tunnel_rpc = agent_api.CoreAgentApi(topics.PLUGIN)

            # L2 Populate plugin Callbacks API
            if self.conf.l2_population:
                self.lbdriver.l2pop_rpc = agent_api.L2PopulationApi()

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
            if self.conf.l2_population:
                consumers.append([topics.L2POPULATION,
                                  topics.UPDATE,
                                  self.agent_host])

            if preJuno:
                self.dispatcher = dispatcher.RpcDispatcher([self])
            else:
                self.endpoints = [self]

            LOG.debug(_('registering to %s consumer on RPC topic: %s'
                        % (consumers, topics.AGENT)))
            if preJuno:
                self.connection = agent_rpc.create_consumers(self.dispatcher,
                                                         topics.AGENT,
                                                         consumers)
            else:
                self.connection = agent_rpc.create_consumers(self.endpoints,
                                                         topics.AGENT,
                                                         consumers)

    def _report_state(self):
        try:
            # assure agent is connected:
            if not self.lbdriver.connected:
                self.lbdriver._init_connection()

            service_count = self.cache.size
            self.agent_state['configurations']['services'] = service_count
            if hasattr(self.lbdriver, 'service_queue'):
                self.agent_state['configurations']['request_queue_depth'] = \
                      len(self.lbdriver.service_queue)
            if self.lbdriver.agent_configurations:
                self.agent_state['configurations'].update(
                                    self.lbdriver.agent_configurations)
            LOG.debug(_('reporting state of agent as: %s' % self.agent_state))
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception:
            LOG.exception(_("Failed reporting state!"))

    def initialize_service_hook(self, started_by):
        self.sync_state()

    @periodic_task.periodic_task
    def periodic_resync(self, context):
        now = datetime.datetime.now()
        # Only force resync if the agent thinks it is
        # synchronized and the resync timer has exired
        if (now - self.last_resync).seconds > \
                            self.service_resync_interval:
            if not self.needs_resync:
                self.needs_resync = True
                LOG.debug(
                    'Forcing resync of services on resync timer (%d seconds).'
                    % self.service_resync_interval)
                self.cache.services = {}
                self.last_resync = now
                self.lbdriver.flush_cache()
        # resync if we need to
        if self.needs_resync:
            self.needs_resync = False
            if self.tunnel_sync():
                self.needs_resync = True
            if self.sync_state():
                self.needs_resync = True

    @periodic_task.periodic_task(spacing=30)
    def collect_stats(self, context):
        if not self.plugin_rpc:
            return
        pool_ids = self.cache.get_pool_ids()
        LOG.debug('collecting stats on pools: %s' % pool_ids)
        for pool_id in pool_ids:
            try:
                stats = self.lbdriver.get_stats(
                        self.plugin_rpc.get_service_by_pool_id(pool_id,
                                        self.conf.f5_global_routed_mode))
                if stats:
                    self.plugin_rpc.update_pool_stats(pool_id, stats)
            except Exception:
                LOG.exception(_('Error upating stats'))
                self.needs_resync = True

    @periodic_task.periodic_task(spacing=600)
    def backup_configuration(self, context):
        self.lbdriver.backup_configuration()

    def tunnel_sync(self):
        return self.lbdriver.tunnel_sync()

    def sync_state(self):
        if not self.plugin_rpc:
            return
        resync = False
        known_services = set(self.cache.get_pool_ids())
        try:
            active_pool_ids = set(self.plugin_rpc.get_active_pool_ids())
            LOG.debug(_('plugin produced the list of active pool ids: %s'
                        % list(active_pool_ids)))
            LOG.debug(_('currently known pool ids before sync are: %s'
                        % list(known_services)))
            for deleted_id in known_services - active_pool_ids:
                self.destroy_service(deleted_id)
            for pool_id in active_pool_ids:
                if not self.cache.get_by_pool_id(pool_id):
                    self.validate_service(pool_id)
            pending_pool_ids = self.plugin_rpc.get_pending_pool_ids()
            LOG.debug(_('plugin produced the list of pending pool ids: %s'
                        % pending_pool_ids))
            for pool_id in pending_pool_ids:
                self.refresh_service(pool_id)
            known_services = set(self.cache.get_pool_ids())
            LOG.debug(_('currently known pool ids after sync are: %s'
                        % list(known_services)))
            self.remove_orphans()
        except Exception:
            LOG.exception(_('Unable to retrieve ready services'))
            resync = True
        return resync

    @log.log
    def validate_service(self, pool_id):
        if not self.plugin_rpc:
            return
        try:
            service = self.plugin_rpc.get_service_by_pool_id(pool_id,
                                        self.conf.f5_global_routed_mode)
            self.cache.put(service)
            if not self.lbdriver.exists(service):
                LOG.error(_('active pool %s is not on BIG-IP.. syncing'
                            % pool_id))
                # update is create or update
                self.lbdriver.sync(service)
        except Exception:
            LOG.exception(_('Unable to validate service for pool: %s'),
                          pool_id)

    @log.log
    def refresh_service(self, pool_id):
        if not self.plugin_rpc:
            return
        try:
            service = self.plugin_rpc.get_service_by_pool_id(pool_id,
                                         self.conf.f5_global_routed_mode)
            self.cache.put(service)
            # update is create or update
            self.lbdriver.sync(service)
        except Exception:
            LOG.exception(_('Unable to refresh service for pool: %s'),
                          pool_id)
            self.needs_resync = True

    @log.log
    def destroy_service(self, pool_id):
        if not self.plugin_rpc:
            return
        service = self.plugin_rpc.get_service_by_pool_id(pool_id,
                                          self.conf.f5_global_routed_mode)
        if not service:
            return
        try:
            self.lbdriver.delete_pool(pool_id, service)
            self.plugin_rpc.pool_destroyed(pool_id)
        except Exception:
            LOG.exception(_('Unable to destroy service for pool: %s'),
                          pool_id)
            self.needs_resync = True
        self.cache.remove_by_pool_id(pool_id)

    @log.log
    def remove_orphans(self):
        try:
            self.lbdriver.remove_orphans(self.cache.services)
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
        if not self.plugin_rpc:
            return
        try:
            stats = self.lbdriver.get_stats(pool, service)
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
            self.lbdriver.create_vip(vip, service)
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
            self.lbdriver.update_vip(old_vip, vip, service)
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
            self.lbdriver.delete_vip(vip, service)
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
            self.lbdriver.create_pool(pool, service)
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
            self.lbdriver.update_pool(old_pool, pool, service)
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
            self.lbdriver.delete_pool(pool, service)
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
            self.lbdriver.create_member(member, service)
            self.cache.put(service)
        except IOError as e:
            message = 'could not create member:' + e.message
            self.plugin_rpc.update_member_status(member['id'],
                                               plugin_const.ERROR,
                                               message)

    @log.log
    def update_member(self, context, old_member, member, service):
        """Handle RPC cast from plugin to update_member"""
        try:
            self.lbdriver.update_member(old_member, member, service)
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
            self.lbdriver.delete_member(member, service)
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
            self.lbdriver.create_pool_health_monitor(health_monitor,
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
            self.lbdriver.update_health_monitor(old_health_monitor,
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
            self.lbdriver.delete_pool_health_monitor(health_monitor,
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
    def tunnel_update(self, context, **kwargs):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received tunnel_update: %s' % kwargs))
        except Exception as e:
            LOG.error(_('could not update tunnel:' + e.message))

    @log.log
    def add_fdb_entries(self, context, fdb_entries, host=None):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received add_fdb_entries: %s host: %s'
                        % (fdb_entries, host)))
            self.lbdriver.fdb_add(fdb_entries)
        except Exception as e:
            LOG.error(_('could not add fdb entries:' + e.message))

    @log.log
    def remove_fdb_entries(self, context, fdb_entries, host=None):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received remove_fdb_entries: %s host: %s'
                        % (fdb_entries, host)))
            self.lbdriver.fdb_remove(fdb_entries)
        except Exception as e:
            LOG.error(_('could not remove fdb entries:' + e.message))

    @log.log
    def update_fdb_entries(self, context, fdb_entries, host=None):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received update_fdb_entries: %s host: %s'
                        % (fdb_entries, host)))
            self.lbdriver.fdb_update(fdb_entries)
        except Exception as e:
            LOG.error(_('could not update tunnel:' + e.message))

if preJuno:
    class LbaasAgentManager(LbaasAgentManagerBase):
        def __init__(self, conf):
            LbaasAgentManagerBase.do_init(self, conf)
else:
    class LbaasAgentManager(n_rpc.RpcCallback, LbaasAgentManagerBase):
        def __init__(self, conf):
            super(LbaasAgentManager, self).__init__()
            LbaasAgentManagerBase.do_init(self, conf)


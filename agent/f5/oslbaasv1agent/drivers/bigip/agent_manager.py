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
import copy
from oslo.config import cfg  # @UnresolvedImport
from neutron.agent import rpc as agent_rpc
from neutron.common import constants as neutron_constants
from neutron import context
from neutron.common import log
from neutron.common import topics
from neutron.common.exceptions import NeutronException
from neutron.openstack.common import loopingcall
from neutron.openstack.common import periodic_task

from f5.oslbaasv1agent.drivers.bigip import agent_api
from f5.oslbaasv1agent.drivers.bigip import constants
import f5.oslbaasv1agent.drivers.bigip.constants as lbaasv1constants

preJuno = False
preKilo = False

try:
    from neutron.openstack.common import importutils
    from neutron.openstack.common import log as logging
    preKilo = True
    try:
        from neutron.openstack.common.rpc import dispatcher
        preJuno = True
    except ImportError:
        from neutron.common import rpc
except ImportError:
    from oslo_log import log as logging
    from oslo_utils import importutils
    from f5.oslbaasv1agent.drivers.bigip import rpc

LOG = logging.getLogger(__name__)

__VERSION__ = "0.1.1"

# configuration options useful to all drivers
OPTS = [
    cfg.StrOpt(
        'f5_bigip_lbaas_device_driver',
        default=('f5.oslbaasv1agent.drivers.bigip'
                 '.icontrol_driver.iControlDriver'),
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
            'static name:value entries to add to the agent configurations')
    ),
    cfg.IntOpt(
        'service_resync_interval',
        default=300,
        help=_('Number of seconds between service refresh check')
    ),
    cfg.StrOpt(
        'environment_prefix', default='',
        help=_('The object name prefix for this environment'),
    ),
    cfg.BoolOpt(
        'environment_specific_plugin', default=False,
        help=_('Use environment specific plugin topic')
    ),
    cfg.IntOpt(
        'environment_group_number',
        default=1,
        help=_('Agent group number for it environment')
    ),
    cfg.DictOpt(
        'capacity_policy', default={},
        help=_('Metrics to measure capacity and their limits.')
    )
]


class LogicalServiceCache(object):
    """Manage a cache of known services."""

    class Service(object):
        """Inner classes used to hold values for weakref lookups."""
        def __init__(self, port_id, pool_id, tenant_id, agent_host):
            self.port_id = port_id
            self.pool_id = pool_id
            self.tenant_id = tenant_id
            self.agent_host = agent_host

        def __eq__(self, other):
            return self.__dict__ == other.__dict__

        def __hash__(self):
            return hash(
                (self.port_id,
                 self.pool_id,
                 self.tenant_id,
                 self.agent_host)
            )

    def __init__(self):
        LOG.debug(_("Initializing LogicalServiceCache version %s"
                    % __VERSION__))
        self.services = {}

    @property
    def size(self):
        return len(self.services)

    def put(self, service, agent_host):
        if 'port_id' in service['vip']:
            port_id = service['vip']['port_id']
        else:
            port_id = None
        pool_id = service['pool']['id']
        tenant_id = service['pool']['tenant_id']
        if pool_id not in self.services:
            s = self.Service(port_id, pool_id, tenant_id, agent_host)
            self.services[pool_id] = s
        else:
            s = self.services[pool_id]
            s.tenant_id = tenant_id
            s.port_id = port_id
            s.agent_host = agent_host

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

    def get_pool_ids(self):
        return self.services.keys()

    def get_tenant_ids(self):
        tenant_ids = {}
        for service in self.services:
            tenant_ids[service.tenant_id] = 1
        return tenant_ids.keys()

    def get_agent_hosts(self):
        agent_hosts = {}
        for service in self.services:
            agent_hosts[service.agent_host] = 1
        return agent_hosts.keys()


class LbaasAgentManagerBase(periodic_task.PeriodicTasks):

    # history
    #   1.0 Initial version
    #   1.1 Support agent_updated call
    RPC_API_VERSION = '1.1'

    # Not using __init__ in order to avoid complexities with super().
    # See derived classes after this class
    def do_init(self, conf):
        LOG.info(_('Initializing LbaasAgentManager'))
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
        LOG.debug(_('setting service resync interval to %d seconds'
                    % self.service_resync_interval))

        try:
            LOG.debug(_('loading LBaaS driver %s'
                        % conf.f5_bigip_lbaas_device_driver))
            self.lbdriver = importutils.import_object(
                conf.f5_bigip_lbaas_device_driver, self.conf)
            if self.lbdriver.agent_id:
                self.agent_host = conf.host + ":" + self.lbdriver.agent_id
                self.lbdriver.agent_host = self.agent_host
                LOG.debug('setting agent host to %s' % self.agent_host)
            else:
                self.agent_host = None
                LOG.error(_('Driver did not initialize. Fix the driver config '
                            'and restart the agent.'))
                return
        except ImportError as ie:
            msg = _('Error importing loadbalancer device driver: %s error %s'
                    % (conf.f5_bigip_lbaas_device_driver,  repr(ie)))
            LOG.error(msg)
            raise SystemExit(msg)

        agent_configurations = \
            {'environment_prefix': self.conf.environment_prefix,
             'environment_group_number': self.conf.environment_group_number,
             'global_routed_mode': self.conf.f5_global_routed_mode}

        if self.conf.static_agent_configuration_data:
            entries = \
                str(self.conf.static_agent_configuration_data).split(',')
            for entry in entries:
                nv = entry.strip().split(':')
                if len(nv) > 1:
                    agent_configurations[nv[0]] = nv[1]

        self.agent_state = {
            'binary': lbaasv1constants.AGENT_BINARY_NAME,
            'host': self.agent_host,
            'topic': lbaasv1constants.TOPIC_LOADBALANCER_AGENT,
            'agent_type': neutron_constants.AGENT_TYPE_LOADBALANCER,
            'l2_population': self.conf.l2_population,
            'configurations': agent_configurations,
            'start_flag': True}

        self.admin_state_up = True

        self.context = context.get_admin_context_without_session()
        # pass context to driver
        self.lbdriver.set_context(self.context)

        # setup all rpc and callback objects
        self._setup_rpc()

        # allow driver to run post init process now that
        # rpc is all setup
        self.lbdriver.post_init()

        # cause a sync of what Neutron believes
        # needs to be handled by this agent
        self.needs_resync = True

    @log.log
    def _setup_rpc(self):

        # LBaaS Callbacks API
        topic = lbaasv1constants.TOPIC_PROCESS_ON_HOST
        if self.conf.environment_specific_plugin:
            topic = topic + '_' + self.conf.environment_prefix
            LOG.debug('agent in %s environment will send callbacks to %s'
                      % (self.conf.environment_prefix, topic))
        self.plugin_rpc = agent_api.LbaasAgentApi(
            topic,
            self.context,
            self.conf.environment_prefix,
            self.conf.environment_group_number,
            self.agent_host
        )
        # Allow driver to make callbacks using the
        # same RPC proxy as the manager
        self.lbdriver.set_plugin_rpc(self.plugin_rpc)

        # Agent state Callbacks API
        self.state_rpc = agent_rpc.PluginReportStateAPI(topic)
        report_interval = self.conf.AGENT.report_interval
        if report_interval:
            heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            heartbeat.start(interval=report_interval)

        # The LBaaS agent listener with it's host are registered
        # as part of the rpc.Service. Here we are setting up
        # other message queues to listen for updates from
        # Neutron.
        if not self.conf.f5_global_routed_mode:
            # Core plugin Callbacks API for tunnel updates
            self.lbdriver.set_tunnel_rpc(agent_api.CoreAgentApi(topics.PLUGIN))

            # L2 Populate plugin Callbacks API
            if self.conf.l2_population:
                self.lbdriver.set_l2pop_rpc(agent_api.L2PopulationApi())

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
                consumers.append(
                    [topics.L2POPULATION, topics.UPDATE, self.agent_host]
                )

            if preJuno:
                self.dispatcher = dispatcher.RpcDispatcher([self])
            else:
                self.endpoints = [self]

            LOG.debug(_('registering to %s consumer on RPC topic: %s'
                        % (consumers, topics.AGENT)))
            if preJuno:
                self.connection = agent_rpc.create_consumers(
                    self.dispatcher,
                    topics.AGENT,
                    consumers
                )
            else:
                self.connection = agent_rpc.create_consumers(
                    self.endpoints,
                    topics.AGENT,
                    consumers
                )

    def _report_state(self):
        try:
            # assure agent is connected:
            if not self.lbdriver.connected:
                self.lbdriver.connect()

            service_count = self.cache.size
            self.agent_state['configurations']['services'] = service_count
            if hasattr(self.lbdriver, 'service_queue'):
                self.agent_state['configurations']['request_queue_depth'] = \
                    len(self.lbdriver.service_queue)
            if self.lbdriver.agent_configurations:
                self.agent_state['configurations'].update(
                    self.lbdriver.agent_configurations
                )
            if self.conf.capacity_policy:
                env_score = \
                    self.lbdriver.generate_capacity_score(
                        self.conf.capacity_policy
                    )
                self.agent_state['configurations'][
                    'environment_capacity_score'] = env_score
            else:
                self.agent_state['configurations'][
                    'environment_capacity_score'] = 0
            LOG.debug(_('reporting state of agent as: %s' % self.agent_state))
            self.state_rpc.report_state(self.context, self.agent_state)
            self.agent_state.pop('start_flag', None)
        except Exception as e:
            LOG.exception(_("Failed reporting state!: " + str(e.message)))

    def initialize_service_hook(self, started_by):
        # Prior to Juno.2, multiple listeners were created, including
        # topic.host, but that was removed. We manually restore that
        # listener here if we see only one topic listener on this connection.
        if hasattr(started_by.conn, 'servers') and \
                len(started_by.conn.servers) == 1:
            node_topic = '%s.%s' % (started_by.topic, started_by.host)
            LOG.debug("Listening on rpc topic %s" % node_topic)
            endpoints = [started_by.manager]
            started_by.conn.create_consumer(
                node_topic, endpoints, fanout=False)
        self.sync_state()

    @periodic_task.periodic_task
    def periodic_resync(self, context):
        LOG.debug("tunnel_sync: periodic_resync called")
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
        LOG.debug("tunnel_sync: periodic_resync need_resync: %s"
                  % str(self.needs_resync))
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
        pool_services = copy.deepcopy(self.cache.services)
        for pool_id in pool_services:
            service = pool_services[pool_id]
            if self.agent_host == service.agent_host:
                try:
                    LOG.debug("collecting stats for pool %s" % service.pool_id)
                    stats = self.lbdriver.get_stats(
                        self.plugin_rpc.get_service_by_pool_id(
                            service.pool_id,
                            self.conf.f5_global_routed_mode
                        )
                    )
                    if stats:
                        self.plugin_rpc.update_pool_stats(service.pool_id,
                                                          stats)
                except Exception as e:
                    LOG.exception(_('Error upating stats' + str(e.message)))
                    self.needs_resync = True

    @periodic_task.periodic_task(spacing=600)
    def backup_configuration(self, context):
        self.lbdriver.backup_configuration()

    def tunnel_sync(self):
        LOG.debug("manager:tunnel_sync: calling driver tunnel_sync")
        return self.lbdriver.tunnel_sync()

    def sync_state(self):
        if not self.plugin_rpc:
            return
        resync = False
        known_services = set()
        for service in self.cache.services:
            if self.agent_host == self.cache.services[service].agent_host:
                known_services.add(service)
        try:
            # this produces a list of active pools for this agent
            # or for this agents env + group if using specific env
            active_pools = self.plugin_rpc.get_active_pools()
            active_pool_ids = set()
            for pool in active_pools:
                if self.agent_host == pool['agent_host']:
                    active_pool_ids.add(pool['pool_id'])
            LOG.debug(_('plugin produced the list of active pool ids: %s'
                        % list(active_pool_ids)))
            LOG.debug(_('currently known pool ids before sync are: %s'
                        % list(known_services)))
            # remove any pools in cache which Neutron plugin does
            # not know about.
            for deleted_id in known_services - active_pool_ids:
                self.destroy_service(deleted_id)
            # validate each service we are supposed to know about
            for pool_id in active_pool_ids:
                if not self.cache.get_by_pool_id(pool_id):
                    self.validate_service(pool_id)
            # this produces a list of pools with pending tasks
            # to be performed
            pending_pools = self.plugin_rpc.get_pending_pools()
            pending_pool_ids = set()
            for pool in pending_pools:
                if self.agent_host == pool['agent_host']:
                    pending_pool_ids.add(pool['pool_id'])
            LOG.debug(_('plugin produced the list of pending pool ids: %s'
                        % pending_pool_ids))
            # complete each pending task
            for pool_id in pending_pool_ids:
                self.refresh_service(pool_id)
            # get a list of any cached service we know now after
            # refreshing services
            known_services = set()
            for service in self.cache.services:
                if self.agent_host == self.cache.services[service].agent_host:
                    known_services.add(service)
            LOG.debug(_('currently known pool ids after sync are: %s'
                        % list(known_services)))
            # remove any orphaned services we find on the bigips
            all_pools = self.plugin_rpc.get_all_pools()
            self.remove_orphans(all_pools)
        except Exception:
            LOG.exception(_('Unable to retrieve ready services'))
            resync = True
        return resync

    @log.log
    def validate_service(self, pool_id):
        if not self.plugin_rpc:
            return
        try:
            service = self.plugin_rpc.get_service_by_pool_id(
                pool_id,
                self.conf.f5_global_routed_mode
            )
            self.cache.put(service, self.agent_host)
            if not self.lbdriver.exists(service):
                LOG.error(_('active pool %s is not on BIG-IP.. syncing'
                            % pool_id))
                self.lbdriver.sync(service)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as e:
            # the pool may have been deleted in the moment
            # between getting the list of pools and validation
            active_pool_ids = set()
            for active_pool in self.plugin_rpc.get_active_pools():
                if self.agent_host == active_pool['agent_host']:
                    active_pool_ids.add(active_pool['pool_id'])
            if pool_id in active_pool_ids:
                LOG.exception(_('Unable to validate service for pool: %s' +
                                str(e.message)), pool_id)

    @log.log
    def refresh_service(self, pool_id):
        if not self.plugin_rpc:
            return
        try:
            service = self.plugin_rpc.get_service_by_pool_id(
                pool_id,
                self.conf.f5_global_routed_mode
            )
            self.cache.put(service, self.agent_host)
            self.lbdriver.sync(service)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)
            self.needs_resync = True

    @log.log
    def destroy_service(self, pool_id):
        if not self.plugin_rpc:
            return
        service = self.plugin_rpc.get_service_by_pool_id(
            pool_id,
            self.conf.f5_global_routed_mode
        )
        if not service:
            return
        try:
            self.lbdriver.delete_pool(pool_id, service)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)
            self.needs_resync = True
        self.cache.remove_by_pool_id(pool_id)

    @log.log
    def remove_orphans(self, all_pools):
        try:
            self.lbdriver.remove_orphans(all_pools)
        except NotImplementedError:
            pass  # Not all drivers will support this

    @log.log
    def reload_pool(self, context, pool_id=None, host=None):
        """Handle RPC cast from plugin to reload a pool."""
        if host and host == self.agent_host:
            if pool_id:
                self.refresh_service(pool_id)

    @log.log
    def get_pool_stats(self, context, pool, service):
        LOG.debug("agent_manager got get_pool_stats call")
        if not self.plugin_rpc:
            return
        try:
            LOG.debug("agent_manager calling driver get_stats")
            stats = self.lbdriver.get_stats(service)
            LOG.debug("agent_manager called driver get_stats")
            if stats:
                    LOG.debug("agent_manager calling update_pool_stats")
                    self.plugin_rpc.update_pool_stats(pool['id'], stats)
                    LOG.debug("agent_manager called update_pool_stats")
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)

    @log.log
    def create_vip(self, context, vip, service):
        """Handle RPC cast from plugin to create_vip"""
        try:
            self.lbdriver.create_vip(vip, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)

    @log.log
    def update_vip(self, context, old_vip, vip, service):
        """Handle RPC cast from plugin to update_vip"""
        try:
            self.lbdriver.update_vip(old_vip, vip, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)

    @log.log
    def delete_vip(self, context, vip, service):
        """Handle RPC cast from plugin to delete_vip"""
        try:
            self.lbdriver.delete_vip(vip, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)

    @log.log
    def create_pool(self, context, pool, service):
        """Handle RPC cast from plugin to create_pool"""
        try:
            self.lbdriver.create_pool(pool, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)

    @log.log
    def update_pool(self, context, old_pool, pool, service):
        """Handle RPC cast from plugin to update_pool"""
        try:
            self.lbdriver.update_pool(old_pool, pool, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("Exception: %s" % exc.message)

    @log.log
    def delete_pool(self, context, pool, service):
        """Handle RPC cast from plugin to delete_pool"""
        try:
            self.lbdriver.delete_pool(pool, service)
            self.cache.remove_by_pool_id(pool['id'])
        except NeutronException as exc:
            LOG.error("delete_pool: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("delete_pool: Exception: %s" % exc.message)

    @log.log
    def create_member(self, context, member, service):
        """Handle RPC cast from plugin to create_member"""
        try:
            self.lbdriver.create_member(member, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("create_member: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("create_member: Exception: %s" % exc.message)

    @log.log
    def update_member(self, context, old_member, member, service):
        """Handle RPC cast from plugin to update_member"""
        try:
            self.lbdriver.update_member(old_member, member, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("update_member: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("update_member: Exception: %s" % exc.message)

    @log.log
    def delete_member(self, context, member, service):
        """Handle RPC cast from plugin to delete_member"""
        try:
            self.lbdriver.delete_member(member, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("delete_member: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("delete_member: Exception: %s" % exc.message)

    @log.log
    def create_pool_health_monitor(self, context, health_monitor,
                                   pool, service):
        """Handle RPC cast from plugin to create_pool_health_monitor"""
        try:
            self.lbdriver.create_pool_health_monitor(health_monitor,
                                                     pool, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error(_("create_pool_health_monitor: NeutronException: %s"
                        % exc.msg))
        except Exception as exc:
            LOG.error(_("create_pool_health_monitor: Exception: %s"
                        % exc.message))

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool, service):
        """Handle RPC cast from plugin to update_health_monitor"""
        try:
            self.lbdriver.update_health_monitor(old_health_monitor,
                                                health_monitor,
                                                pool, service)
            self.cache.put(service, self.agent_host)
        except NeutronException as exc:
            LOG.error("update_health_monitor: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("update_health_monitor: Exception: %s" % exc.message)

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor,
                                   pool, service):
        """Handle RPC cast from plugin to delete_pool_health_monitor"""
        try:
            self.lbdriver.delete_pool_health_monitor(health_monitor,
                                                     pool, service)
        except NeutronException as exc:
            LOG.error(_("delete_pool_health_monitor: NeutronException: %s"
                        % exc.msg))
        except Exception as exc:
            LOG.error(_("delete_pool_health_monitor: Exception: %s"
                      % exc.message))

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
            self.lbdriver.tunnel_update(**kwargs)
        except NeutronException as exc:
            LOG.error("tunnel_update: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("tunnel_update: Exception: %s" % exc.message)

    @log.log
    def add_fdb_entries(self, context, fdb_entries, host=None):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received add_fdb_entries: %s host: %s'
                        % (fdb_entries, host)))
            self.lbdriver.fdb_add(fdb_entries)
        except NeutronException as exc:
            LOG.error("fdb_add: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("fdb_add: Exception: %s" % exc.message)

    @log.log
    def remove_fdb_entries(self, context, fdb_entries, host=None):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received remove_fdb_entries: %s host: %s'
                        % (fdb_entries, host)))
            self.lbdriver.fdb_remove(fdb_entries)
        except NeutronException as exc:
            LOG.error("remove_fdb_entries: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("remove_fdb_entries: Exception: %s" % exc.message)

    @log.log
    def update_fdb_entries(self, context, fdb_entries, host=None):
        """Handle RPC cast from core to update tunnel definitions"""
        try:
            LOG.debug(_('received update_fdb_entries: %s host: %s'
                        % (fdb_entries, host)))
            self.lbdriver.fdb_update(fdb_entries)
        except NeutronException as exc:
            LOG.error("update_fdb_entrie: NeutronException: %s" % exc.msg)
        except Exception as exc:
            LOG.error("update_fdb_entrie: Exception: %s" % exc.message)

if preJuno:
    class LbaasAgentManager(LbaasAgentManagerBase):
        RPC_API_VERSION = '1.1'

        def __init__(self, conf):
            LbaasAgentManagerBase.do_init(self, conf)
else:
    class LbaasAgentManager(rpc.RpcCallback,
                            LbaasAgentManagerBase):  # @UndefinedVariable
        RPC_API_VERSION = '1.1'

        def __init__(self, conf):
            super(LbaasAgentManager, self).__init__()
            LbaasAgentManagerBase.do_init(self, conf)

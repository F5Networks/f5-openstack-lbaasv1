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
from random import randint

from neutron.common import log
from neutron.common import exceptions as q_exc
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants
from neutron.services.loadbalancer.drivers import abstract_driver
from neutron.services.loadbalancer import constants as lb_const
from neutron.db.loadbalancer import loadbalancer_db as ldb

LOG = logging.getLogger(__name__)

__VERSION__ = '0.1.1'

ACTIVE_PENDING = (
    constants.ACTIVE,
    constants.PENDING_CREATE,
    constants.PENDING_UPDATE
)


class F5LogDriver(abstract_driver.LoadBalancerAbstractDriver):
    """ Log Driver for LBaaS.

        This class implements the methods found in the abstract
        parent class.

        This class interacts with the data model through the
        core plugin, creates messages to send to agents and then
        invokes the LoadBalancerAgentApi class methods to
        send the RPC messages.
    """
    def __init__(self, plugin):
        LOG.debug('Initializing F5LogDriver')
        self.plugin = plugin
        self.members = []

    @log.log
    def create_vip(self, context, vip):
        self.plug_vip_port(context, vip['port_id'])
        self.plugin.update_status(context,
                                  ldb.Vip,
                                  vip['id'],
                                  constants.ACTIVE,
                                  'Vip Created Successfully')

    @log.log
    def update_vip(self, context, old_vip, vip):
        self.plugin.update_status(context,
                                  ldb.Vip,
                                  vip['id'],
                                  constants.ACTIVE,
                                  'Vip Updated Successfully')

    @log.log
    def delete_vip(self, context, vip):
        self.unplug_vip_port(context, vip['port_id'])
        self.plugin._delete_db_vip(context, vip['id'])

    @log.log
    def create_pool(self, context, pool):
        self.plugin.update_status(context,
                                  ldb.Pool,
                                  pool['id'],
                                  constants.ACTIVE,
                                  'Pool Created Successfully')

    @log.log
    def update_pool(self, context, old_pool, pool):
        self.plugin.update_status(context,
                                  ldb.Pool,
                                  pool['id'],
                                  constants.ACTIVE,
                                  'Pool Updated Successfully')

    @log.log
    def delete_pool(self, context, pool):
        self.plugin._delete_db_pool(context, pool['id'])

    @log.log
    def create_member(self, context, member):
        self.members.append(member)
        self.plugin.update_status(context,
                                  ldb.Member,
                                  member['id'],
                                  constants.ACTIVE,
                                  'Pool Member Created Successfully')

    @log.log
    def update_member(self, context, old_member, member):
        self.plugin.update_status(context,
                                  ldb.Member,
                                  member['id'],
                                  constants.ACTIVE,
                                  'Pool Member Updated Successfully')

    @log.log
    def delete_member(self, context, member):
        if member in self.members:
            self.members.remove(member)
        self.plugin._delete_db_member(context, member['id'])

    @log.log
    def create_pool_health_monitor(self, context, health_monitor, pool_id):
        self.plugin.update_status(context,
                                  ldb.HealthMonitor,
                                  health_monitor['id'],
                                  constants.ACTIVE,
                                  'Health Monitor Created Successfully')

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool_id):
        self.plugin.update_status(context,
                                  ldb.HealthMonitor,
                                  health_monitor['id'],
                                  constants.ACTIVE,
                                  'Health Monitor Updated Successfully')

    @log.log
    def delete_pool_health_monitor(self, context, health_monitor, pool_id):
        self.plugin._delete_db_pool_health_monitor(context,
                                                   health_monitor['id'],
                                                   pool_id)

    @log.log
    def stats(self, context, pool_id):
        """update of pool stats."""
        bytecount = randint(1000, 10000000000)
        connections = randint(1000, 10000000000)
        stats = {}
        stats[lb_const.STATS_IN_BYTES] = bytecount,
        stats[lb_const.STATS_OUT_BYTES] = bytecount * 5
        stats[lb_const.STATS_ACTIVE_CONNECTIONS] = connections
        stats[lb_const.STATS_TOTAL_CONNECTIONS] = connections * 10
        if len(self.members):
            for member in self.members:
                member[lb_const.STATS_STATUS] = lb_const.STATS_FAILED_CHECKS
        stats['members'] = self.members
        self.update_pool_stats(context, pool_id, stats)

    @log.log
    def plug_vip_port(self, context, port_id=None):
        """vip has been provisioned."""
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
        port['device_id'] = 'log_loadbalancer'

        self.plugin._core_plugin.update_port(
            context,
            port_id,
            {'port': port}
        )

    @log.log
    def unplug_vip_port(self, context, port_id=None):
        """"vip has been deprovisioned"""
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
    def update_pool_stats(self, context, pool_id=None, stats=None):
        self.plugin.update_pool_stats(self, context, pool_id, data=stats)

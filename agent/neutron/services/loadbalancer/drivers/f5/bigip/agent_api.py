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

from neutron.openstack.common.rpc import proxy
from neutron.agent import rpc as agent_rpc
from neutron.plugins.ml2.drivers.l2pop import rpc as l2pop_rpc
from neutron.common import log


class CoreAgentApi(agent_rpc.PluginApi):
    pass


class L2PopulationApi(l2pop_rpc.L2populationAgentNotifyAPI):
    pass


class LbaasAgentApi(proxy.RpcProxy):
    """Agent side of the Agent to Plugin RPC API."""

    API_VERSION = '1.0'

    def __init__(self, topic, context, host):
        super(LbaasAgentApi, self).__init__(topic, self.API_VERSION)
        self.context = context
        self.host = host

    @log.log
    def get_active_pending_pool_ids(self):
        return self.call(
               self.context,
               self.make_msg('get_active_pending_pool_ids',
                             host=self.host),
               topic=self.topic
        )

    @log.log
    def get_service_by_pool_id(self, pool_id):
        return self.call(
            self.context,
            self.make_msg(
                'get_service_by_pool_id',
                pool_id=pool_id,
                host=self.host
            ),
            topic=self.topic
        )

    @log.log
    def create_port_on_subnet(self, subnet_id=None,
                    mac_address=None, name=None,
                    fixed_address_count=1):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'create_port_on_subnet',
                                       subnet_id=subnet_id,
                                       mac_address=mac_address,
                                       name=name,
                                       fixed_address_count=fixed_address_count,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def create_port_on_subnet_with_specific_ip(self, subnet_id=None,
                                               mac_address=None, name=None,
                                               ip_address=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                'create_port_on_subnet_with_specific_ip',
                                       subnet_id=subnet_id,
                                       mac_address=mac_address,
                                       name=name,
                                       ip_address=ip_address,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def get_port_by_name(self, port_name=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'get_port_by_name',
                                       port_name=port_name
                                      ),
                         topic=self.topic
                )

    @log.log
    def delete_port(self, port_id=None, mac_address=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'delete_port',
                                       port_id=port_id,
                                       mac_address=mac_address
                                      ),
                         topic=self.topic
                )

    @log.log
    def delete_port_by_name(self, port_name=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                        'delete_port_by_name',
                                        port_name=port_name
                                       ),
                         topic=self.topic
                        )

    @log.log
    def allocate_fixed_address_on_subnet(self, subnet_id=None,
                               port_id=None, name=None,
                               fixed_address_count=1):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'allocate_fixed_address_on_subnet',
                                       subnet_id=subnet_id,
                                       port_id=port_id,
                                       name=name,
                                       fixed_address_count=fixed_address_count,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def allocate_specific_fixed_address_on_subnet(self, subnet_id=None,
                               port_id=None, name=None,
                               ip_address=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                'allocate_specific_fixed_address_on_subnet',
                                       subnet_id=subnet_id,
                                       port_id=port_id,
                                       name=name,
                                       ip_address=ip_address,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def deallocate_fixed_address_on_subnet(self, fixed_addresses=None,
                             subnet_id=None, auto_delete_port=False):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'deallocate_fixed_address_on_subnet',
                                       fixed_addresses=fixed_addresses,
                                       subnet_id=subnet_id,
                                       host=self.host,
                                       auto_delete_port=auto_delete_port
                                      ),
                         topic=self.topic
                )

    @log.log
    def update_vip_status(self, vip_id=None,
                           status=None, status_description=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'update_vip_status',
                                       vip_id=vip_id,
                                       status=status,
                                       status_description=status_description,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def vip_destroyed(self, vip_id=None):
        return self.call(
            self.context,
            self.make_msg('vip_destroyed', vip_id=vip_id, host=self.host),
            topic=self.topic
        )

    @log.log
    def update_pool_status(self, pool_id=None,
                           status=None, status_description=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'update_pool_status',
                                       pool_id=pool_id,
                                       status=status,
                                       status_description=status_description,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def pool_destroyed(self, pool_id):
        return self.call(
            self.context,
            self.make_msg('pool_destroyed', pool_id=pool_id, host=self.host),
            topic=self.topic
        )

    @log.log
    def update_member_status(self, member_id=None,
                           status=None, status_description=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'update_member_status',
                                       member_id=member_id,
                                       status=status,
                                       status_description=status_description,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def member_destroyed(self, member_id):
        return self.call(
            self.context,
            self.make_msg('member_destroyed', member_id=member_id,
                          host=self.host),
            topic=self.topic
        )

    @log.log
    def update_health_monitor_status(self, pool_id=None,
                                     health_monitor_id=None,
                                     status=None,
                                     status_description=None):
        return self.call(
                         self.context,
                         self.make_msg(
                                       'update_health_monitor_status',
                                       pool_id=pool_id,
                                       health_monitor_id=health_monitor_id,
                                       status=status,
                                       status_description=status_description,
                                       host=self.host
                                      ),
                         topic=self.topic
                )

    @log.log
    def health_monitor_destroyed(self, health_monitor_id=None,
                                 pool_id=None):
        return self.call(
            self.context,
            self.make_msg('health_monitor_destroyed',
                          health_monitor_id=health_monitor_id,
                          pool_id=pool_id,
                          host=self.host),
            topic=self.topic
        )

    @log.log
    def update_pool_stats(self, pool_id, stats):
        return self.call(
            self.context,
            self.make_msg(
                'update_pool_stats',
                pool_id=pool_id,
                stats=stats,
                host=self.host
            ),
            topic=self.topic
        )

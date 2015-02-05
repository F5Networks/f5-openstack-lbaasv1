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

from neutron.services.loadbalancer import agent_scheduler
from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)

import random


class TenantScheduler(agent_scheduler.ChanceScheduler):
    """Allocate a loadbalancer agent for a pool based on tenant_id.
       or else make a random choice.
    """

    def schedule(self, plugin, context, pool):
        """Schedule the pool to an active loadbalancer agent if there
        is no enabled agent hosting it.
        """
        with context.session.begin(subtransactions=True):
            lbaas_agent = plugin.get_lbaas_agent_hosting_pool(
                context, pool['id'])
            if lbaas_agent:
                LOG.debug(_('Pool %(pool_id)s has already been hosted'
                            ' by lbaas agent %(agent_id)s'),
                          {'pool_id': pool['id'],
                           'agent_id': lbaas_agent['id']})
                return

            candidates = plugin.get_lbaas_agents(context, active=True)
            if not candidates:
                LOG.warn(_('No active lbaas agents for pool %s'), pool['id'])
                return
            candidates = [a for a in candidates if 'f5' in a['binary']]
            if not candidates:
                LOG.warn(_('No f5 lbaas agents for pool %s'), pool['id'])
                return

            chosen_agent = None
            for candidate in candidates:
                assigned_pools = plugin.list_pools_on_lbaas_agent(
                    context, candidate['id'])
                for assigned_pool in assigned_pools['pools']:
                    if pool['tenant_id'] == assigned_pool['tenant_id']:
                        chosen_agent = candidate
                        break
                if chosen_agent:
                    break

            if not chosen_agent:
                chosen_agent = random.choice(candidates)

            binding = agent_scheduler.PoolLoadbalancerAgentBinding()
            binding.agent = chosen_agent
            binding.pool_id = pool['id']
            context.session.add(binding)
            LOG.debug(_('Pool %(pool_id)s is scheduled to '
                        'lbaas agent %(agent_id)s'),
                      {'pool_id': pool['id'],
                       'agent_id': chosen_agent['id']})
            return chosen_agent

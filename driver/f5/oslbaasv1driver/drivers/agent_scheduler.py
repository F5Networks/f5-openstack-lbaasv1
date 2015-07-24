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
import random
import json

try:
    from neutron.services.loadbalancer import agent_scheduler
    from neutron.openstack.common import log as logging
except ImportError:
    # Kilo
    from neutron_lbaas.services.loadbalancer import agent_scheduler
    from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class TenantScheduler(agent_scheduler.ChanceScheduler):
    """Allocate a loadbalancer agent for a pool based on tenant_id.
       or else make a random choice.
    """
    def __init__(self):
        self.agent_env_cache = {}
        super(TenantScheduler, self).__init__()

    def get_lbaas_agent_hosting_pool(self, plugin, context, pool_id,
                                     active=None, env=None):
        LOG.debug(_('Getting agent for pool %s with env %s' % (pool_id, env)))
        with context.session.begin(subtransactions=True):
            # returns {'agent': agent_dict}
            if env:
                lbaas_agent = plugin.get_lbaas_agent_hosting_pool(context,
                                                                  pool_id,
                                                                  active=True)
                if lbaas_agent:
                    return lbaas_agent
                else:
                    agents = self.get_active_agent_in_env(plugin, context, env)
                    if agents:
                        agent = plugin._make_agent_dict(agents[0])
                        LOG.debug('returning agent : %s' % agent)
                        return {'agent': agent}
                    else:
                        LOG.warn(_('No active lbaas agents for pool %s in %s'
                                 % (pool_id, env)))
            lbaas_agent = plugin.get_lbaas_agent_hosting_pool(context,
                                                              pool_id)
            return lbaas_agent

    def get_active_agent_in_env(self, plugin, context, env):
        with context.session.begin(subtransactions=True):
            candidates = plugin.get_lbaas_agents(context, active=True)
            return_agents = []
            if candidates:
                for candidate in candidates:
                    if candidate['id'] in self.agent_env_cache:
                        candidate_env = \
                            self.agent_env_cache[candidate['id']]
                    else:
                        agent_conf = candidate['configurations']
                        if not isinstance(agent_conf, dict):
                            agent_conf = candidate['configurations']
                            try:
                                agent_config = \
                                    json.loads(candidate['configurations'])
                            except ValueError as ve:
                                LOG.error('can not JSON decode %s : %s'
                                          % (candidate['configurations'],
                                             ve.message))
                                candidate['configurations'] = {}
                            if 'environment_prefix' in agent_conf:
                                candidate_env = \
                                    agent_config['environment_prefix']
                            else:
                                candidate_env = ""
                            if candidate_env == env:
                                return_agents.append(candidate)
            return return_agents

    def schedule(self, plugin, context, pool, env=None):
        """Schedule the pool to an active loadbalancer agent if there
        is no enabled agent hosting it.
        """
        with context.session.begin(subtransactions=True):
            if env:
                # find if the pool is hosted on an active agent
                # already. If not, find one in env.
                lbaas_agent = plugin.get_lbaas_agent_hosting_pool(
                    context, pool['id'], active=True
                )
                if lbaas_agent:
                    lbaas_agent = lbaas_agent['agent']
                    LOG.debug(_('Pool %(pool_id)s has already been hosted'
                                ' by lbaas agent %(agent_id)s'),
                              {'pool_id': pool['id'],
                               'agent_id': lbaas_agent['id']})
                    return lbaas_agent
                candidates = self.get_active_agent_in_env(plugin,
                                                          context,
                                                          env)
                if not candidates:
                    LOG.warn(_('No f5 lbaas agents are active env %s' % env))
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
            else:
                # preserve complete old behavior if env is not defined
                lbaas_agent = plugin.get_lbaas_agent_hosting_pool(
                    context, pool['id'])
                if lbaas_agent:
                    lbaas_agent = lbaas_agent['agent']
                    LOG.debug(_('Pool %(pool_id)s has already been hosted'
                                ' by lbaas agent %(agent_id)s'),
                              {'pool_id': pool['id'],
                               'agent_id': lbaas_agent['id']})
                    return lbaas_agent
                candidates = plugin.get_lbaas_agents(context, active=True)
                if not candidates:
                    LOG.warn(_('No active lbaas agents for pool %s'
                               % pool['id']))
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

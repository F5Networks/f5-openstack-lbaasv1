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
        super(TenantScheduler, self).__init__()

    def get_lbaas_agent_hosting_pool(self, plugin, context, pool_id, env=None):
        LOG.debug(_('Getting agent for pool %s with env %s' % (pool_id, env)))
        with context.session.begin(subtransactions=True):
            # returns {'agent': agent_dict}
            lbaas_agent = plugin.get_lbaas_agent_hosting_pool(context,
                                                              pool_id)
            if env:
                # find if there is a agent already bound to this pool
                # active or not active
                if lbaas_agent:
                    rt_agent = lbaas_agent['agent']
                    # which environment group is the agent in
                    agent_conf = self.deserialize_agent_configurations(
                        rt_agent['configurations']
                    )
                    if 'environment_group_number' in agent_conf:
                        rt_agent_gn = agent_conf[
                                   'environment_group_number']
                    else:
                        rt_agent_gn = 1

                    # is the agent alive return the agent for this pool
                    if rt_agent['alive']:
                        return lbaas_agent
                    else:
                        # Agent is dead. Is there another in this
                        # environment and group? If so return that agent
                        # for this task.
                        env_agents = self.get_active_agent_in_env(plugin,
                                                                  context,
                                                                  env,
                                                                  rt_agent_gn)
                        if env_agents:
                            return {'agent': env_agents[0]}
            # There is no environment for this lbaas_agent, return
            # previously scheduled agent regardless if it is alive
            # or not. This is the pre environment aware behaviour.
            return lbaas_agent

    def get_active_agent_in_env(self, plugin, context, env, group=None):
        with context.session.begin(subtransactions=True):
            candidates = plugin.get_lbaas_agents(context, active=True)
            return_agents = []
            if candidates:
                for candidate in candidates:
                    agent_conf = self.deserialize_agent_configurations(
                        candidate['configurations']
                    )
                    if 'environment_prefix' in agent_conf:
                        candidate_env = agent_conf['environment_prefix']
                    else:
                        candidate_env = ""
                if candidate_env == env:
                    if group:
                        if 'environment_group_number' in agent_conf and \
                          agent_conf['environment_group_number'] == group:
                            return_agents.append(candidate)
                    else:
                        return_agents.append(candidate)
            return return_agents

    def get_capacity(self, configurations):
        if 'environment_capacity_score' in configurations:
            return configurations['environment_capacity_score']
        else:
            return 0.0

    def deserialize_agent_configurations(self, configurations):
        agent_conf = configurations
        if not isinstance(agent_conf, dict):
            try:
                agent_conf = json.loads(configurations)
            except ValueError as ve:
                LOG.error('can not JSON decode %s : %s'
                          % (agent_conf, ve.message))
                agent_conf = {}
        return agent_conf

    def schedule(self, plugin, context, pool, env=None):
        """Schedule the pool to an active loadbalancer agent if there
        is no enabled agent hosting it.
        """
        with context.session.begin(subtransactions=True):
            if env:
                # If the pool is hosted on an active agent
                # already, return that agent or one in its env
                lbaas_agent = plugin.get_lbaas_agent_hosting_pool(
                    context, pool['id']
                )
                if lbaas_agent:
                    lbaas_agent = lbaas_agent['agent']
                    message = 'Pool %s already scheduled in env %s.' \
                        % (pool['id'], env)
                    message += ' Assigning task to agent %s.' \
                        % (lbaas_agent['id'])
                    LOG.debug(message)
                    return lbaas_agent

                # There is no existing pool agent binding.
                # Find all active agent candidate in this env.
                candidates = self.get_active_agent_in_env(plugin,
                                                          context,
                                                          env)
                if not candidates:
                    LOG.warn(_('No f5 lbaas agents are active env %s' % env))
                    return None

                # We have active candidates to choose from.
                # Qualify them bv tenant affinity and then capacity.
                chosen_agent = None
                agents_by_group = {}
                capacity_by_group = {}

                for candidate in candidates:
                    # Organize agents by their evn group
                    # and collect each group's max capacity.
                    agent_conf = self.deserialize_agent_configurations(
                        candidate['configurations']
                    )
                    gn = 1
                    if 'environment_group_number' in agent_conf:
                        gn = agent_conf['environment_group_number']
                    if gn not in agents_by_group.keys():
                        agents_by_group[gn] = []
                    agents_by_group[gn].append(candidate)
                    # populate each group's capacity
                    group_capacity = self.get_capacity(agent_conf)
                    if gn not in capacity_by_group.keys():
                        capacity_by_group[gn] = group_capacity
                    else:
                        # take the highest capacity score for
                        # all candidates in this environment group
                        if group_capacity > capacity_by_group[gn]:
                            capacity_by_group[gn] = group_capacity

                    # Do we already have tenants assigned to this
                    # agent candidate. If we do and it has capacity
                    # then assign this pool to this agent.
                    assigned_pools = plugin.list_pools_on_lbaas_agent(
                        context, candidate['id'])
                    for assigned_pool in assigned_pools['pools']:
                        if pool['tenant_id'] == assigned_pool['tenant_id']:
                            chosen_agent = candidate
                            break
                    if chosen_agent:
                        # Does the agent which had tenants assigned
                        # to it still have capacity?
                        if group_capacity >= 1.0:
                            chosen_agent = None
                        else:
                            break

                # If we don't have an agent with capacity associated
                # with our tenant_id, let's pick an agent based on
                # the group with the lowest capacity score.
                if not chosen_agent:
                    # lets get an agent from the group with the
                    # lowest capacity score
                    lowest_capacity = 1.0
                    selected_group = 1
                    for group in capacity_by_group:
                        if capacity_by_group[group] < lowest_capacity:
                            lowest_capacity = capacity_by_group[group]
                            selected_group = group
                    LOG.debug('%s group %s scheduled with capacity %s'
                              % (env, selected_group, lowest_capacity))
                    if lowest_capacity < 1.0:
                        # Choose a agent in the env froup for this
                        # tenant at random.
                        chosen_agent = random.choice(
                            agents_by_group[selected_group]
                        )

                # If there are no agents with available capacity, return None
                if not chosen_agent:
                    LOG.warn('No capacity left on any agents in env: %s' % env)
                    LOG.warn('Group capacity in %s were %s.'
                             % (env, capacity_by_group))
                    return None

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

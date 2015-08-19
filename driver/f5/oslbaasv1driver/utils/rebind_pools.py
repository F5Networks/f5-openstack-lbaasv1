#!/usr/bin/env python

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
import sys
import json

from neutron.common import config
from oslo.config import cfg
from neutron.context import get_admin_context
from neutron.db.agents_db import Agent

preJuno = False
try:
    from neutron.common import legacy
    from neutron.services.loadbalancer.agent_scheduler import \
        PoolLoadbalancerAgentBinding
    from neutron.db.loadbalancer import loadbalancer_db as ldb
    preJuno = True
except ImportError:
    from neutron.common import config as common_config
    from neutron_lbaas.services.loadbalancer.agent_scheduler import \
        PoolLoadbalancerAgentBinding
    from neutron_lbaas.db.loadbalancer import loadbalancer_db as ldb


def print_usage():
    message = '\nUsage:\n'
    message += '  python -m rebind_pools'
    message += ' --agent_id=[agent_id]\n\n'
    message += '    agent_id - uuid of the agent to rebind all bound pools\n'
    print(message)


def rebind_pools(agent_id):
    context = get_admin_context()
    agent = context.session.query(Agent).filter_by(id=agent_id).one()
    if agent:

        bindings = context.session.query(
                    PoolLoadbalancerAgentBinding
                ).filter_by(agent_id=agent.id).all()
        if not bindings:
            print('No pool bindings found for agent %s' % agent_id)
            return

        agent_config = json.loads(agent.configurations)
        env_prefix = agent_config['environment_prefix']
        env_group = agent_config['environment_group_number']

        remapped_pools = []
        need_target = True

        for target_agent in context.session.query(Agent).all():
            if need_target:
                agent_config = json.loads(target_agent.configurations)
                if 'environment_prefix' in agent_config and \
                   agent_config['environment_prefix'] == env_prefix and \
                   agent_config['environment_group_number'] == env_group:
                    # find pools
                    need_target = False
                    for binding in bindings:
                        pool = context.session.query(
                                ldb.Pool
                        ).filter_by(id=binding.pool_id).one()
                        if pool and pool.id not in remapped_pools:
                            binding.agent_id = target_agent.id
                            binding.pool_id = pool.id
                            context.session.add(binding)
                            print('Pool %s is now bound to agent %s'
                                  % (pool.id, target_agent.id))
                            remapped_pools.append(pool.id)
                    context.session.flush()
        if need_target:
            print('Did not find another agent in env %s group %s'
                  % (env_prefix, env_group))
    else:
        print('No agent with id %s found.' % agent_id)


if __name__ == "__main__":

    OPTS = [
        cfg.StrOpt(
            'agent_id',
            default=None
        )
    ]

    cfg.CONF.register_cli_opts(opts=OPTS)

    if preJuno:
        config.setup_logging(cfg.CONF)
        legacy.modernize_quantum_config(cfg.CONF)
    else:
        common_config.init(sys.argv[1:])
        config.setup_logging()

    if cfg.CONF.agent_id is None:
        print_usage()
        sys.exit(1)

    rebind_pools(cfg.CONF.agent_id)

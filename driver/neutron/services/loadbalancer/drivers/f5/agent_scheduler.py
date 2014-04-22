##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

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

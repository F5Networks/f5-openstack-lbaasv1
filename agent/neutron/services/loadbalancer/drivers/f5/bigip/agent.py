##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

import eventlet
from oslo.config import cfg

from neutron.agent.common import config
from neutron.common import legacy
from neutron.openstack.common.rpc import service as rpc_service
from neutron.openstack.common import service
from neutron.services.loadbalancer.drivers.f5.bigip import \
     agent_manager as manager
from neutron.services.loadbalancer.drivers.f5 import plugin_driver

OPTS = [
    cfg.IntOpt(
        'periodic_interval',
        default=10,
        help=_('Seconds between periodic task runs')
    )
]


class LbaasAgentService(rpc_service.Service):
    def start(self):
        super(LbaasAgentService, self).start()
        self.tg.add_timer(
            cfg.CONF.periodic_interval,
            self.manager.run_periodic_tasks,
            None,
            None
        )


def main():
    eventlet.monkey_patch()
    cfg.CONF.register_opts(OPTS)
    cfg.CONF.register_opts(manager.OPTS)
    config.register_agent_state_opts_helper(cfg.CONF)
    config.register_root_helper(cfg.CONF)

    cfg.CONF(project='neutron')
    config.setup_logging(cfg.CONF)
    legacy.modernize_quantum_config(cfg.CONF)

    mgr = manager.LbaasAgentManager(cfg.CONF)
    svc = LbaasAgentService(
        host=mgr.agent_host,
        topic=plugin_driver.TOPIC_LOADBALANCER_AGENT,
        manager=mgr
    )
    service.launch(svc).wait()

if __name__ == '__main__':
    main()

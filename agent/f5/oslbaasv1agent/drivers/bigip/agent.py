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
import eventlet
from oslo.config import cfg
from neutron.agent.common import config
from neutron.openstack.common import service
from f5.oslbaasv1agent.drivers.bigip import agent_manager as manager
import f5.oslbaasv1agent.drivers.bigip.constants as lbaasconstants

eventlet.monkey_patch()

preJuno = False
try:
    from neutron.common import legacy
    from neutron.openstack.common.rpc.service import Service
    preJuno = True
except ImportError:
    from neutron.common.rpc import Service
    from neutron.common import config as common_config

OPTS = [
    cfg.IntOpt(
        'periodic_interval',
        default=10,
        help=_('Seconds between periodic task runs')
    )
]


class LbaasAgentService(Service):
    def start(self):
        super(LbaasAgentService, self).start()
        self.tg.add_timer(
            cfg.CONF.periodic_interval,
            self.manager.run_periodic_tasks,
            None,
            None
        )


def main():
    cfg.CONF.register_opts(OPTS)
    cfg.CONF.register_opts(manager.OPTS)
    config.register_agent_state_opts_helper(cfg.CONF)
    config.register_root_helper(cfg.CONF)

    if preJuno:
        cfg.CONF(project='neutron')
        config.setup_logging(cfg.CONF)
        legacy.modernize_quantum_config(cfg.CONF)
    else:
        common_config.init(sys.argv[1:])
        config.setup_logging()

    mgr = manager.LbaasAgentManager(cfg.CONF)
    svc = LbaasAgentService(
        host=mgr.agent_host,
        topic=lbaasconstants.TOPIC_LOADBALANCER_AGENT,
        manager=mgr
    )
    service.launch(svc).wait()

if __name__ == '__main__':
    main()

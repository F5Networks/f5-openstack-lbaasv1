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

# Service resync interval
RESYNC_INTERVAL = 300

# Topic for tunnel notifications between the plugin and agent
TUNNEL = 'tunnel'

# Values for network_type
TYPE_FLAT = 'flat'
TYPE_VLAN = 'vlan'
TYPE_GRE = 'gre'
TYPE_LOCAL = 'local'
TYPE_VXLAN = 'vxlan'
VXLAN_UDP_PORT = 4789
VTEP_SELFIP_NAME = 'vtep'

# Inter-Agent Channel
AGENT_STATUS = 'f5-agents'

# RPC channel names
TOPIC_PROCESS_ON_HOST = 'q-f5-lbaas-process-on-host'
TOPIC_LOADBALANCER_AGENT = 'f5_lbaas_process_on_agent'

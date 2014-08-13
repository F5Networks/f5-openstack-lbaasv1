##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

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

# Requirements
GRE_TUNNEL_HOTFIX_REQUIRED = True
VXLAN_TUNNEL_HOTFIX_REQUIRED = True

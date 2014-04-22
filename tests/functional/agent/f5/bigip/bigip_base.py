##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# 
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
################################################################################

import unittest
import ConfigParser
from f5.bigip.bigip import BigIP


class BigIPTestBase(unittest.TestCase):
    def setUp(self):
        self.config = ConfigParser.ConfigParser()
        self.config.read('../../../../test_config.cfg')

        env = self.config.get('test_env', 'active')

        self.bigip = self._get_bigip(env)

    def _get_bigip(self, env):
        hostname = self.config.get(env, 'bigip_hostname')
        username = self.config.get(env, 'bigip_username')
        password = self.config.get(env, 'bigip_password')

        return BigIP(hostname, username, password)


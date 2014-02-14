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


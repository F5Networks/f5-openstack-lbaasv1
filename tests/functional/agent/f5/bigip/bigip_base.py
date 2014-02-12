import unittest
import ConfigParser
from f5.bigip.bigip import BigIP


class BigIPTestBase(unittest.TestCase):
    def setUp(self):
        self.config = ConfigParser.ConfigParser()
        self.config.read('../../../../test_config.cfg')

        self.bigip = self._get_bigip()

    def _get_bigip(self):
        section = 'agent.f5.bigip:global'

        hostname = self.config.get(section, 'bigip_hostname')
        username = self.config.get(section, 'bigip_username')
        password = self.config.get(section, 'bigip_password')

        return BigIP(hostname, username, password)


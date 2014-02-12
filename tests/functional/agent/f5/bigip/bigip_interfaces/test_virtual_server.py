from tests.functional.agent.f5.bigip.bigip_base import BigIPTestBase


class TestBigIPInterfaceVirtualServer(BigIPTestBase):
    def setUp(self):
        super(TestBigIPInterfaceVirtualServer, self).setUp()

        # declare global test vars section
        global_section = \
            'agent.f5.bigip.bigip_interfaces.virtual_server:global'

        # set up test VLAN
        self.vlan_name = self.config.get(global_section, 'vlan_name')
        vlan_id = self.config.get(global_section, 'vlan_id')
        vlan_interface = self.config.get(global_section, 'vlan_interface')

        self.bigip.vlan.create(self.vlan_name, vlan_id, vlan_interface)

    def test_create_virtual_server_http(self):
        section = 'agent.f5.bigip.bigip_interfaces.virtual_server:http'
        self._create_virtual_server_and_assert(section)

    def test_create_virtual_server_tcp(self):
        section = 'agent.f5.bigip.bigip_interfaces.virtual_server:tcp'
        self._create_virtual_server_and_assert(section)

    def _create_virtual_server_and_assert(self, section):
        folder = self.config.get(section, 'virtual_server_folder')
        name = self.config.get(section, 'virtual_server_name')
        protocol = self.config.get(section, 'virtual_server_protocol')
        address = self.config.get(section, 'virtual_server_address')
        mask = self.config.get(section, 'virtual_server_mask')
        port = int(self.config.get(section, 'virtual_server_port'))

        self.bigip.virtual_server.create(name,
                                         address,
                                         mask,
                                         port,
                                         protocol,
                                         self.vlan_name)

        # assertions
        self.assertTrue(self.bigip.virtual_server.exists(name, folder=folder))
        self.assertEqual(protocol,
                         self.bigip.virtual_server.get_protocol(name,
                                                                folder=folder))
        self.assertEqual(address,
                         self.bigip.virtual_server.get_addr(name,
                                                            folder=folder))
        self.assertEqual(mask,
                         self.bigip.virtual_server.get_mask(name,
                                                            folder=folder))
        self.assertEqual(port,
                         self.bigip.virtual_server.get_port(name,
                                                            folder=folder))

    def _remove_all_test_artifacts(self):
        for test_name in ['http', 'tcp']:
            section = 'agent.f5.bigip.bigip_interfaces.virtual_server:' + \
                      test_name
            self.bigip.virtual_server.delete(
                self.config.get(section, 'virtual_server_name'))

    def tearDown(self):
        # remove all test artifacts
        self._remove_all_test_artifacts()

        # remove test VLAN
        self.bigip.vlan.delete(self.vlan_name)
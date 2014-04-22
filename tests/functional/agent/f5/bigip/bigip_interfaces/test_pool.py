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

from tests.functional.agent.f5.bigip.bigip_base import BigIPTestBase

pool_http = {'folder': '/tenant1',
             'name': 'test-pool-http',
             'lb_method': 'LEAST_CONNECTIONS',
             'service_down_action': 'SERVICE_DOWN_ACTION_DROP',
             'members': [
                 {'name': 'test-member-http-1',
                  'addr': '10.0.0.1',
                  'port': 80},
                 {'name': 'test-member-http-2',
                  'addr': '10.0.0.2',
                  'port': 80},
                 {'name': 'test-member-http-3',
                  'addr': '10.0.0.3',
                  'port': 80}
             ]}

pool_ssh = {'folder': '/tenant2',
            'name': 'test-pool-ssh',
            'lb_method': 'PREDICTIVE_MEMBER',
            'service_down_action': 'SERVICE_DOWN_ACTION_RESET',
            'members': [
                {'name': 'test-member-ssh-1',
                 'addr': '10.0.0.1',
                 'port': 22},
                {'name': 'test-member-ssh-2',
                 'addr': '10.0.0.2',
                 'port': 22},
                {'name': 'test-member-ssh-3',
                 'addr': '10.0.0.3',
                 'port': 22}
            ]}

pool_dns = {'folder': '/tenant3',
            'name': 'test-pool-dns',
            'lb_method': 'ROUND_ROBIN',
            'service_down_action': 'SERVICE_DOWN_ACTION_RESELECT',
            'members': [
                {'name': 'test-member-dns-1',
                 'addr': '10.0.0.11',
                 'port': 53},
                {'name': 'test-member-dns-2',
                 'addr': '10.0.0.12',
                 'port': 53},
                {'name': 'test-member-dns-3',
                 'addr': '10.0.0.13',
                 'port': 53}
            ]}

monitor_http = {'folder': '/tenant1',
                'name': 'test-monitor-http',
                'type': 'HTTP',
                'interval': 3,
                'timeout': 10,
                'send_text': 'GET /',
                'recv_text': 'UP'}

monitor_icmp = {'folder': '/tenant1',
                'name': 'test-monitor-icmp',
                'type': 'ICMP',
                'interval': 5,
                'timeout': 16,
                'send_text': None,
                'recv_text': None}

pools = [pool_http, pool_ssh, pool_dns]
monitors = [monitor_http, monitor_icmp]
service_down_actions = ['DROP', 'RESET', 'RESELECT', 'NONE']
lb_methods = ['LEAST_CONNECTIONS', 'OBSERVED_MEMBER', 'PREDICTIVE_MEMBER',
              'ROUND_ROBIN']


class TestBigIPInterfacePool(BigIPTestBase):
    def setUp(self):
        super(TestBigIPInterfacePool, self).setUp()

    def test_create_pool_http(self):
        self._create_pool_and_assert(pool_http)

    def test_create_pool_ssh(self):
        self._create_pool_and_assert(pool_ssh)

    def test_create_pool_dns(self):
        self._create_pool_and_assert(pool_dns)

    def test_get_pool_members_http(self):
        self._create_pool_and_assert(pool_http)
        self._add_members_and_assert(pool_http)

        members = self.bigip.pool.get_members(name=pool_http['name'],
                                              folder=pool_http['folder'])
        addrs = ([member['addr'] for member in members])

        self.assertEqual(len(pool_http['members']), len(members))

        for member in members:
            self.assertTrue(member['addr'] in addrs)

    def test_get_pool_members_ssh(self):
        self._create_pool_and_assert(pool_ssh)
        self._add_members_and_assert(pool_ssh)

        members = self.bigip.pool.get_members(name=pool_ssh['name'],
                                              folder=pool_ssh['folder'])
        addrs = ([member['addr'] for member in members])

        self.assertEqual(len(pool_ssh['members']), len(members))

        for member in members:
            self.assertTrue(member['addr'] in addrs)
    
    def test_get_pool_members_dns(self):
        self._create_pool_and_assert(pool_dns)
        self._add_members_and_assert(pool_dns)

        members = self.bigip.pool.get_members(name=pool_dns['name'],
                                              folder=pool_dns['folder'])
        addrs = ([member['addr'] for member in members])

        self.assertEqual(len(pool_dns['members']), len(members))

        for member in members:
            self.assertTrue(member['addr'] in addrs)

    def test_add_pool_members_http(self):
        self._create_pool_and_assert(pool_http)
        self._add_members_and_assert(pool_http)

    def test_add_pool_members_ssh(self):
        self._create_pool_and_assert(pool_ssh)
        self._add_members_and_assert(pool_ssh)

    def test_add_pool_members_dns(self):
        self._create_pool_and_assert(pool_dns)
        self._add_members_and_assert(pool_dns)

    def test_remove_pool_members_http(self):
        self._create_pool_and_assert(pool_http)
        self._add_members_and_assert(pool_http)
        self._remove_members_and_assert(pool_http)

    def test_remove_pool_members_ssh(self):
        self._create_pool_and_assert(pool_ssh)
        self._add_members_and_assert(pool_ssh)
        self._remove_members_and_assert(pool_ssh)

    def test_remove_pool_members_dns(self):
        self._create_pool_and_assert(pool_dns)
        self._add_members_and_assert(pool_dns)
        self._remove_members_and_assert(pool_dns)

    def test_add_pool_monitors(self):
        self._create_pool_and_assert(pool_http)
        self._create_monitor_and_assert(monitor_http)
        self._create_monitor_and_assert(monitor_icmp)
        self._add_monitor_and_assert(pool_http, monitor_http)
        self._add_monitor_and_assert(pool_http, monitor_icmp)

    def test_remove_pool_monitors(self):
        self._create_pool_and_assert(pool_http)
        self._create_monitor_and_assert(monitor_http)
        self._create_monitor_and_assert(monitor_icmp)
        self._add_monitor_and_assert(pool_http, monitor_http)
        self._add_monitor_and_assert(pool_http, monitor_icmp)
        self._remove_monitor_and_assert(pool_http, monitor_http)
        self._remove_monitor_and_assert(pool_http, monitor_icmp)

    def test_get_pool_monitors(self):
        self._create_pool_and_assert(pool_http)
        self._create_monitor_and_assert(monitor_http)
        self._create_monitor_and_assert(monitor_icmp)
        self._add_monitor_and_assert(pool_http, monitor_http)
        self._add_monitor_and_assert(pool_http, monitor_icmp)

        actual_monitors = self.bigip.pool.get_monitors(name=pool_http['name'],
                                                       folder=pool_http['folder'])

        self.assertEqual(2, len(actual_monitors))
        self.assertTrue(monitor_http['name'] in actual_monitors)
        self.assertTrue(monitor_icmp['name'] in actual_monitors)

    def test_set_lb_methods(self):
        self._create_pool_and_assert(pool_http)

        for lb_method in lb_methods:
            self.bigip.pool.set_lb_method(name=pool_http['name'],
                                          lb_method=lb_method,
                                          folder=pool_http['folder'])
            self.assertEquals(lb_method, self.bigip.pool.get_lb_method(
                name=pool_http['name'], folder=pool_http['folder']))

    def test_set_service_down_actions(self):
        self._create_pool_and_assert(pool_http)

        for action in service_down_actions:
            self.bigip.pool.set_service_down_action(name=pool_http['name'],
                                                    service_down_action=action,
                                                    folder=pool_http['folder'])
            self.assertEquals(action,
                              self.bigip.pool.get_service_down_action(
                                  name=pool_http['name'],
                                  folder=pool_http['folder']))

    def test_delete_pool_http(self):
        self._create_pool_and_assert(pool_http)
        self._delete_pool_and_assert(pool_http)

    def test_delete_pool_ssh(self):
        self._create_pool_and_assert(pool_ssh)
        self._delete_pool_and_assert(pool_ssh)

    def test_delete_pool_dns(self):
        self._create_pool_and_assert(pool_dns)
        self._delete_pool_and_assert(pool_dns)

    def _create_pool_and_assert(self, pool):
        self.bigip.pool.create(name=pool['name'],
                               lb_method=pool['lb_method'],
                               folder=pool['folder'])

        self.assertTrue(self.bigip.pool.exists(name=pool['name'],
                                               folder=pool['folder']))
        self.assertEqual(pool['lb_method'],
                         self.bigip.pool.get_lb_method(name=pool['name'],
                                                       folder=pool['folder']))

    def _create_monitor_and_assert(self, monitor):
        self.bigip.monitor.create(name=monitor['name'],
                                  mon_type=monitor['type'],
                                  interval=monitor['interval'],
                                  timeout=monitor['timeout'],
                                  send_text=monitor['send_text'],
                                  recv_text=monitor['recv_text'],
                                  folder=monitor['folder'])

        self.assertTrue(self.bigip.monitor.exists(name=monitor['name'],
                                                  folder=monitor['folder']))

    def _add_monitor_and_assert(self, pool, monitor):
        expected_count = len(
            self.bigip.pool.get_monitors(name=pool['name'],
                                         folder=pool['folder'])) + 1

        self.bigip.pool.add_monitor(name=pool['name'],
                                    monitor_name=monitor['name'],
                                    folder=pool['folder'])

        actual_monitors = self.bigip.pool.get_monitors(name=pool['name'],
                                                       folder=pool['folder'])

        self.assertEqual(expected_count, len(actual_monitors))
        self.assertTrue(monitor['name'] in actual_monitors)
        
    def _remove_monitor_and_assert(self, pool, monitor):
        expected_count = len(
            self.bigip.pool.get_monitors(name=pool['name'],
                                         folder=pool['folder'])) - 1

        self.bigip.pool.remove_monitor(name=pool['name'],
                                       monitor_name=monitor['name'],
                                       folder=pool['folder'])

        actual_monitors = self.bigip.pool.get_monitors(name=pool['name'],
                                                       folder=pool['folder'])

        self.assertEqual(expected_count, len(actual_monitors))
        self.assertFalse(monitor['name'] in actual_monitors)

    def _add_members_and_assert(self, pool):
        for member in pool['members']:
            self.bigip.pool.add_member(name=pool['name'],
                                       ip_address=member['addr'],
                                       port=member['port'],
                                       folder=pool['folder'])

            exists = self.bigip.pool.member_exists(name=pool['name'],
                                                   ip_address=member['addr'],
                                                   port=member['port'],
                                                   folder=pool['folder'])
            self.assertTrue(exists)

        members = self.bigip.pool.get_members(name=pool['name'],
                                              folder=pool['folder'])

        self.assertEqual(len(pool['members']), len(members))

    def _remove_members_and_assert(self, pool):
        for member in pool['members']:
            self.bigip.pool.remove_member(name=pool['name'],
                                          ip_address=member['addr'],
                                          port=member['port'],
                                          folder=pool['folder'])

            exists = self.bigip.pool.member_exists(name=pool['name'],
                                                   ip_address=member['addr'],
                                                   port=member['port'],
                                                   folder=pool['folder'])
            self.assertFalse(exists)

        members = self.bigip.pool.get_members(name=pool['name'],
                                              folder=pool['folder'])

        self.assertEqual(0, len(members))

    def _delete_pool_and_assert(self, pool):
        self.bigip.pool.delete(name=pool['name'],
                               folder=pool['folder'])

        self.assertFalse(self.bigip.pool.exists(name=pool['name'],
                                                folder=pool['folder']))

    def _remove_all_test_artifacts(self):
        for pool in pools:
            self.bigip.pool.delete(name=pool['name'], folder=pool['folder'])

        for monitor in monitors:
            self.bigip.monitor.delete(name=monitor['name'],
                                      folder=monitor['folder'])

    def tearDown(self):
        # remove all test artifacts
        self._remove_all_test_artifacts()

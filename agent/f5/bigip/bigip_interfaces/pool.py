##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common.logger import Log
from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import icontrol_rest_folder
from f5.bigip.bigip_interfaces import strip_folder_and_prefix

from suds import WebFault
import os
import urllib
import json


class Pool(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(
                                           ['LocalLB.Pool',
                                            'LocalLB.NodeAddressV2']
                                           )
        # iControl helper objects
        self.lb_pool = self.bigip.icontrol.LocalLB.Pool
        self.lb_node = self.bigip.icontrol.LocalLB.NodeAddressV2

    @icontrol_folder
    def create(self, name=None, lb_method=None,
               description=None, folder='Common'):
        if not self.exists(name=name, folder=folder):
            # pool definition
            pool_names = [name]
            lb_methods = [self._get_lb_method_type(lb_method)]
            # create an empty pool
            addr_port_seq = self.lb_pool.typefactory.create(
                'Common.AddressPortSequence')
            pool_members_seq = [addr_port_seq]
            try:
                self.lb_pool.create_v2(pool_names,
                                       lb_methods,
                                       pool_members_seq)
                if description:
                    self.lb_pool.set_description([pool_names], [description])
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('Pool',
                              'tried to create a Pool when exists')
                    return False
                else:
                    raise wf
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            nodes = self._get_nodes_for_members(
                                                name=name,
                                                folder=folder)
            self.lb_pool.delete_pool([name])
            if len(nodes) > 0:
                # allow for nodes which are still in other pools
                try:
                    self.lb_node.delete_node_address(nodes)
                except:
                    pass
            return True
        else:
            return False

    @icontrol_folder
    def get_members(self, name=None, folder='Common'):
        members = []
        for member in self.lb_pool.get_member_v2([name])[0]:
            addr = os.path.basename(member.address)
            members.append({'addr': addr, 'port': member.port})

        return members

    @icontrol_folder
    def get_pools(self, folder='Common'):
        return self.lb_pool.get_list()

    @icontrol_folder
    def get_members_monitor_status(self, name=None, folder='Common'):
        return_members = []
        members = self.lb_pool.get_member_v2([name])[0]
        if len(members) > 0:
            member_types = [None] * len(members)
            members_seq = self.lb_pool.typefactory.create(
                                                'Common.StringSequence')
            members_seq_seq = self.lb_pool.typefactory.create(
                                        'Common.StringSequenceSequence')
            for i in range(len(members)):
                member_types[i] = self._get_addr_port_seq(members[i].address,
                                                          members[i].port)
                member_types[i] = member_types[i]['item']
            members_seq.values = member_types
            members_seq_seq.values = [members_seq]
            states = self.lb_pool.get_member_monitor_status([name],
                                                           members_seq_seq)[0]
            for i in range(len(members)):
                addr = os.path.basename(members[i].address).split('%')[0]
                port = int(members[i].port)
                return_members.append({'addr': addr,
                                       'port': port,
                                       'state': states[0]})
        return return_members

    @icontrol_folder
    def get_statistics(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            stats = self.lb_pool.get_statistics([name])[0][0].statistics
            return_stats = {}
            for stat in stats:
                return_stats[stat.type] = self.bigip.ulong_to_int(stat.value)
            return return_stats
        else:
            return {}

    @icontrol_folder
    def _get_nodes_for_members(self, name=None, folder='Common'):
        nodes = self.lb_node.get_list()
        if not len(nodes) > 0:
            return nodes
        node_addresses = self.lb_node.get_address(nodes)
        return_nodes = []
        for member in self.lb_pool.get_member_v2([name])[0]:
            for i in range(len(node_addresses)):
                if node_addresses[i] == \
                   os.path.basename(member.address).split('%')[0]:
                    return_nodes.append(nodes[i])
        return return_nodes

    @icontrol_folder
    @domain_address
    def add_member(self, name=None, ip_address=None, port=None,
                   folder='Common', no_checks=False):
        if no_checks or \
           (self.exists(name=name, folder=folder) and
              not self.member_exists(name=name,
                                  ip_address=ip_address,
                                  port=port,
                                  folder=folder)):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            try:
                self.lb_pool.add_member_v2([name], [addr_port_seq])
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('Pool',
                              'tried to create a Pool member when exists')
                    return False
                else:
                    raise wf
            return True
        else:
            return False

    @icontrol_folder
    @domain_address
    def enable_member(self, name=None, ip_address=None, port=None,
                       folder='Common', no_checks=False):
        if no_checks or \
           (self.exists(name=name, folder=folder) and \
           self.member_exists(name=name,
                                  ip_address=ip_address,
                                  port=port,
                                  folder=folder)):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            state_seq = self.lb_pool.typefactory.create(
                                                    'Common.StringSequence')
            state_seq.values = ['STATE_ENABLED']
            state_seq_seq = self.lb_pool.typefactory.create(
                                            'Common.StringSequenceSequence')
            state_seq_seq.values = [state_seq]
            self.lb_pool.set_member_session_enabled_state(
                                                         [name],
                                                         [addr_port_seq],
                                                         state_seq_seq
                                                         )
            return True
        else:
            return False

    @icontrol_folder
    @domain_address
    def disable_member(self, name=None, ip_address=None, port=None,
                       folder='Common', no_checks=False):
        if no_checks or \
           (self.exists(name=name, folder=folder) and \
           self.member_exists(name=name,
                                  ip_address=ip_address,
                                  port=port,
                                  folder=folder)):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            state_seq = self.lb_pool.typefactory.create(
                                                    'Common.StringSequence')
            state_seq.values = ['STATE_DISABLED']
            state_seq_seq = self.lb_pool.typefactory.create(
                                            'Common.StringSequenceSequence')
            state_seq_seq.values = [state_seq]
            self.lb_pool.set_member_session_enabled_state(
                                                         [name],
                                                         [addr_port_seq],
                                                         state_seq_seq
                                                         )
            return True
        else:
            return False

    @icontrol_folder
    @domain_address
    def set_member_ratio(self, name=None, ip_address=None, port=None,
                         ratio=1, folder='Common', no_checks=False):
        if no_checks or \
           (self.exists(name=name, folder=folder) and
               self.member_exists(name=name,
                                  ip_address=ip_address,
                                  port=port,
                                  folder=folder)):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            self.lb_pool.set_member_ratio([name],
                                          [addr_port_seq],
                                          [{'long': [ratio]}])
            return True
        else:
            return False

    @icontrol_folder
    @domain_address
    def remove_member(self, name=None, ip_address=None,
                      port=None, folder='Common'):
        if self.exists(name=name, folder=folder) and \
           self.member_exists(name=name, ip_address=ip_address,
                              port=port, folder=folder):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            self.lb_pool.remove_member_v2([name], [addr_port_seq])

            # node address might have multiple pool members
            # associated with it, so it might not delete
            try:
                if ip_address[-2:] == '%0':
                    ip_address = ip_address.split('%')[0]
                self.remove_node_by_address(node_ip_address=ip_address,
                                                folder=folder)
            except:
                pass
            return True
        else:
            try:
                if ip_address[-2:] == '%0':
                    ip_address = ip_address.split('%')[0]
                self.remove_node_by_address(node_ip_address=ip_address,
                                                folder=folder)
            except:
                pass
        return False

    @icontrol_folder
    def remove_node(self, name=None, folder='Common'):
        try:
            self.lb_node.delete_node_address([name])
        except:
            return False
        return True

    @icontrol_folder
    def remove_nodes(self, node_names=None, folder='Common'):
        try:
            self.lb_node.delete_node_address([node_names])
        except:
            return False
        return True

    @icontrol_folder
    def remove_node_by_address(self,
                               node_ip_address=None,
                               folder='Common'):
        nodes = self.lb_node.get_list()
        if len(nodes) > 0:
            node_addresses = self.lb_node.get_address(nodes)
            for i in range(len(node_addresses)):
                if node_addresses[i] == node_ip_address:
                    try:
                        self.lb_node.delete_node_address([nodes[i]])
                    except:
                        return False
                    return True
        return False

    @icontrol_folder
    def get_nodes(self, folder='Common'):
        nodes = self.lb_node.get_list()
        for i in range(len(nodes)):
            nodes[i] = os.path.basename(nodes[i])
        return nodes

    @icontrol_folder
    def get_node_addresses(self, folder='Common'):
        nodes = self.lb_node.get_list()
        node_addresses = []
        if len(nodes) > 0:
            node_addresses = self.lb_node.get_address(nodes)
            for i in range(len(node_addresses)):
                node_addresses[i] = node_addresses[i].split('%')[0]
        return node_addresses

    @icontrol_folder
    def get_service_down_action(self, name=None, folder='Common'):
        service_down_action_type = self.lb_pool.typefactory.create(
            'LocalLB.ServiceDownAction')
        service_down_action = self.lb_pool.get_action_on_service_down(
            [name])[0]

        if service_down_action == \
                service_down_action_type.SERVICE_DOWN_ACTION_RESET:
            return 'RESET'
        elif service_down_action == \
                service_down_action_type.SERVICE_DOWN_ACTION_DROP:
            return 'DROP'
        elif service_down_action == \
                service_down_action_type.SERVICE_DOWN_ACTION_RESELECT:
            return 'RESELECT'
        else:
            return 'NONE'

    @icontrol_folder
    def set_service_down_action(self, name=None,
                                service_down_action=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            service_down_action_type = self._get_service_down_action_type(
                service_down_action)
            self.lb_pool.set_action_on_service_down([name],
                                                    [service_down_action_type])
            return True
        else:
            return False

    @icontrol_folder
    def set_lb_method(self, name=None, lb_method=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            lb_method_type = self._get_lb_method_type(lb_method)
            self.lb_pool.set_lb_method([name], [lb_method_type])
            return True
        else:
            return False

    @icontrol_folder
    def get_lb_method(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            lb_method_type = self.lb_pool.typefactory.create(
                'LocalLB.LBMethod')
            lb_method = self.lb_pool.get_lb_method([name])[0]

            if lb_method == lb_method_type.LB_METHOD_LEAST_CONNECTION_MEMBER:
                return 'LEAST_CONNECTIONS'
            elif lb_method == lb_method_type.LB_METHOD_OBSERVED_MEMBER:
                return 'OBSERVED_MEMBER'
            elif lb_method == lb_method_type.LB_METHOD_PREDICTIVE_MEMBER:
                return 'PREDICTIVE_MEMBER'
            elif lb_method == lb_method_type.LB_METHOD_RATIO_MEMBER:
                return 'RATIO'
            elif lb_method == \
                 lb_method_type.LB_METHOD_RATIO_LEAST_CONNECTION_MEMBER:
                return 'RATIO'
            else:
                return 'ROUND_ROBIN'

    @icontrol_folder
    def set_description(self, name=None, description=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_pool.set_description([name], [description])
            return True
        else:
            return False

    @icontrol_folder
    def get_description(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_pool.get_description([name])[0]

    @icontrol_folder
    def get_monitors(self, name=None, folder='Common'):
        monitors = self._get_monitors(name=name, folder=folder)
        if len(monitors) > 0:
            monitors = strip_folder_and_prefix(monitors)
        return monitors

    @icontrol_folder
    def add_monitor(self, name=None, monitor_name=None, folder='Common'):
        monitors = self._get_monitors(name=name, folder=folder)

        if not monitor_name in monitors:
            monitors.append(monitor_name)
            self._set_monitor_assoc(name=name, monitors=monitors,
                                    folder=folder)
            return True
        else:
            return False

    @icontrol_folder
    def remove_monitor(self, name=None, monitor_name=None, folder='Common'):
        monitors = self._get_monitors(name=name, folder=folder)

        if monitor_name in monitors:
            monitors.remove(monitor_name)
            self._set_monitor_assoc(name=name, monitors=monitors,
                                    folder=folder)
            return True
        else:
            return False

    @icontrol_folder
    def _set_monitor_assoc(self, name=None, monitors=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            monitor_rule_type = self._get_monitor_rule_type(len(monitors))

            monitor_assoc = self.lb_pool.typefactory.create(
                'LocalLB.Pool.MonitorAssociation')
            monitor_rule = self.lb_pool.typefactory.create(
                'LocalLB.MonitorRule')
            monitor_rule.monitor_templates = monitors
            monitor_rule.type = monitor_rule_type
            monitor_rule.quorum = 0
            monitor_assoc.pool_name = name
            monitor_assoc.monitor_rule = monitor_rule
            self.lb_pool.set_monitor_association([monitor_assoc])

    @icontrol_folder
    def _get_monitors(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            monitors = self.lb_pool.get_monitor_association([name])[
                0].monitor_rule.monitor_templates

            if '/Common/none' in monitors:
                monitors.remove('/Common/none')

            return monitors
        else:
            return []

    def _get_addr_port_seq(self, addr, port):
        addr_port_seq = self.lb_pool.typefactory.create(
            'Common.AddressPortSequence')
        addr_port = self.lb_pool.typefactory.create('Common.AddressPort')
        addr_port.address = addr
        addr_port.port = port
        addr_port_seq.item = addr_port

        return addr_port_seq

    def _get_monitor_rule_type(self, num_monitors):
        monitor_rule_type = self.lb_pool.typefactory.create(
            'LocalLB.MonitorRuleType')

        if num_monitors == 0:
            return monitor_rule_type.MONITOR_RULE_TYPE_NONE
        elif num_monitors == 1:
            return monitor_rule_type.MONITOR_RULE_TYPE_SINGLE
        else:
            return monitor_rule_type.MONITOR_RULE_TYPE_AND_LIST

    def _get_lb_method_type(self, lb_method):
        lb_method_type = self.lb_pool.typefactory.create('LocalLB.LBMethod')
        lb_method = str(lb_method).upper()

        if lb_method == 'LEAST_CONNECTIONS':
            return lb_method_type.LB_METHOD_LEAST_CONNECTION_MEMBER
        elif lb_method == 'RATIO_LEAST_CONNECTIONS':
            return lb_method_type.LB_METHOD_RATIO_LEAST_CONNECTION_MEMBER
        elif lb_method == 'SOURCE_IP':
            return lb_method_type.LB_METHOD_LEAST_CONNECTION_NODE_ADDRESS
        elif lb_method == 'OBSERVED_MEMBER':
            return lb_method_type.LB_METHOD_OBSERVED_MEMBER
        elif lb_method == 'PREDICTIVE_MEMBER':
            return lb_method_type.LB_METHOD_PREDICTIVE_MEMBER
        elif lb_method == 'RATIO':
            return lb_method_type.LB_METHOD_RATIO_MEMBER
        else:
            return lb_method_type.LB_METHOD_ROUND_ROBIN

    def _get_service_down_action_type(self, service_down_action):
        service_down_action_type = self.lb_pool.typefactory.create(
            'LocalLB.ServiceDownAction')
        service_down_action = str(service_down_action).upper()

        if service_down_action == 'RESET':
            return service_down_action_type.SERVICE_DOWN_ACTION_RESET
        elif service_down_action == 'DROP':
            return service_down_action_type.SERVICE_DOWN_ACTION_DROP
        elif service_down_action == 'RESELECT':
            return service_down_action_type.SERVICE_DOWN_ACTION_RESELECT
        else:
            return service_down_action_type.SERVICE_DOWN_ACTION_NONE

    @icontrol_rest_folder
    def exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/pool/'
        request_url += '~' + folder + '~' + name
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False

    @icontrol_rest_folder
    @domain_address
    def member_exists(self, name=None, ip_address=None,
                      port=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/pool/'
        request_url += '~' + folder + '~' + name
        request_url += '/members/~' + folder + '~'
        request_url += urllib.quote(ip_address) + ':' + str(port)
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'address' in response_obj:
                return True
            else:
                return False
        else:
            return False

        #members = self.lb_pool.get_member_v2([name])
        #for member in members[0]:
        #    if os.path.basename(member.address) == ip_address and \
        #       int(member.port) == port:
        #        return True

import os

from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder

# Local Traffic - Pool

from neutron.common import log

class Pool(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.Pool')
        # iControl helper objects
        self.lb_pool = self.bigip.icontrol.LocalLB.Pool

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
            self.lb_pool.create_v2(pool_names, lb_methods, pool_members_seq)
            if description:
                self.lb_pool.set_description([pool_names], [description])

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_pool.delete_pool([name])

    @icontrol_folder
    def get_members(self, name=None, folder='Common'):
        return self.lb_pool.get_list([name])

    @icontrol_folder
    @domain_address
    @log.log
    def add_member(self, name=None, ip_address=None, port=None,
                   folder='Common'):
        if self.exists(name=name, folder=folder) and \
           not self.member_exists(name=name,
                                  ip_address=ip_address,
                                  port=port,
                                  folder=folder):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            self.lb_pool.add_member_v2([name], [addr_port_seq])

    @icontrol_folder
    @domain_address
    def remove_member(self, name=None, ip_address=None,
                      port=None, folder='Common'):
        if not self.exists(name=name, folder=folder) and \
           self.member_exists(name=name, ip_address=ip_address,
                              port=port, folder=folder):
            addr_port_seq = self._get_addr_port_seq(ip_address, port)
            self.lb_pool.remove_member_v2([name], [addr_port_seq])

    @icontrol_folder
    def get_service_down_action(self, name=None, folder='Common'):
        service_down_action_type = self.lb_pool.typefactory.create(
            'LocalLB.ServiceDownAction')
        service_down_action = self.lb_pool.get_action_on_service_down(
            [name])[0]

        if service_down_action == \
                service_down_action_type.SERVICE_DOWN_ACTION_RESET:
            return 'SERVICE_DOWN_ACTION_RESET'
        elif service_down_action == \
                service_down_action_type.SERVICE_DOWN_ACTION_DROP:
            return 'SERVICE_DOWN_ACTION_DROP'
        elif service_down_action == \
                service_down_action_type.SERVICE_DOWN_ACTION_RESELECT:
            return 'SERVICE_DOWN_ACTION_RESELECT'
        else:
            return 'SERVICE_DOWN_ACTION_NONE'

    @icontrol_folder
    def set_service_down_action(self, name=None,
                                service_down_action=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            service_down_action_type = self._get_service_down_action_type(
                service_down_action)
            self.lb_pool.set_action_on_service_down([name],
                                                    [service_down_action_type])

    @icontrol_folder
    def set_lb_method(self, name=None, lb_method=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            lb_method_type = self._get_lb_method_type(lb_method)
            self.lb_pool.set_lb_method([name], [lb_method_type])

    @icontrol_folder
    def get_lb_method(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            lb_method_type = self.lb_pool.typefactory.create(
                'LocalLB.LBMethod')
            lb_method = self.lb_pool.get_lb_method([name])[0]

            if lb_method == lb_method_type.LB_METHOD_LEAST_CONNECTION_MEMBER:
                return 'LB_METHOD_LEAST_CONNECTION_MEMBER'
            elif lb_method == lb_method_type.LB_METHOD_OBSERVED_MEMBER:
                return 'LB_METHOD_OBSERVED_MEMBER'
            elif lb_method == lb_method_type.LB_METHOD_PREDICTIVE_MEMBER:
                return 'LB_METHOD_PREDICTIVE_MEMBER'
            elif lb_method == lb_method_type.LB_METHOD_ROUND_ROBIN:
                return 'LB_METHOD_ROUND_ROBIN'
            else:
                # TODO: raise unsupported LB method
                pass

    @icontrol_folder
    def get_monitors(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            monitor_assoc = self.lb_pool.get_monitor_association([name])[0]
            return monitor_assoc.monitor_rule.monitor_templates

    @icontrol_folder
    def add_monitor(self, name=None, monitor_name=None, folder='Common'):
        monitors = self.get_monitors(name=name, folder=folder)

        if not monitor_name in monitors:
            monitors.append(monitor_name)
            self._set_monitor_assoc(name=name, monitors=monitors,
                                    folder=folder)

    @icontrol_folder
    def remove_monitor(self, name=None, monitor_name=None, folder='Common'):
        monitors = self.get_monitors(name=name, folder=folder)

        if monitor_name in monitors:
            monitors.remove(monitor_name)
            self._set_monitor_assoc(name=name, monitors=monitors,
                                    folder=folder)

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
        if lb_method == 'LEAST_CONNECTIONS':
            return lb_method_type.LB_METHOD_LEAST_CONNECTION_MEMBER
        elif lb_method == 'ROUND_ROBIN':
            return lb_method_type.LB_METHOD_ROUND_ROBIN
        elif lb_method == 'SOURCE_IP':
            return lb_method_type.LB_METHOD_LEAST_CONNECTION_NODE
        elif lb_method == 'LB_METHOD_LEAST_CONNECTION_MEMBER':
            return lb_method_type.LB_METHOD_LEAST_CONNECTION_MEMBER
        elif lb_method == 'LB_METHOD_OBSERVED_MEMBER':
            return lb_method_type.LB_METHOD_OBSERVED_MEMBER
        elif lb_method == 'LB_METHOD_PREDICTIVE_MEMBER':
            return lb_method_type.LB_METHOD_PREDICTIVE_MEMBER
        else:
            return lb_method_type.LB_METHOD_ROUND_ROBIN

    def _get_service_down_action_type(self, service_down_action):
        service_down_action_type = self.lb_pool.typefactory.create(
                                                'LocalLB.ServiceDownAction')

        if service_down_action == 'SERVICE_DOWN_ACTION_RESET':
            return service_down_action_type.SERVICE_DOWN_ACTION_RESET
        elif service_down_action == 'SERVICE_DOWN_ACTION_DROP':
            return service_down_action_type.SERVICE_DOWN_ACTION_DROP
        elif service_down_action == 'SERVICE_DOWN_ACTION_RESELECT':
            return service_down_action_type.SERVICE_DOWN_ACTION_RESELECT
        else:
            return service_down_action_type.SERVICE_DOWN_ACTION_NONE

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        if name in self.lb_pool.get_list():
            return True

    @icontrol_folder
    @domain_address
    @log.log
    def member_exists(self, name=None, ip_address=None,
                      port=None, folder='Common'):
        members = self.lb_pool.get_member_v2([name])
        for member in members[0]:
            if os.path.basename(member.address) == ip_address and \
               int(member.port) == port:
                return True

import os


# Local Traffic - Pool
class Pool(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.Pool')
        # iControl helper objects
        self.lb_pool = self.bigip.icontrol.LocalLB.Pool

    def create(self, name, lb_method):
        # pool definition
        pool_names = [name]
        lb_methods = [self._get_lb_method_type(lb_method)]

        # create an empty pool
        addr_port_seq = self.lb_pool.typefactory.create('Common.AddressPortSequence')
        pool_members_seq = [addr_port_seq]
        self.lb_pool.create_v2(pool_names, lb_methods, pool_members_seq)

    def delete(self, name):
        if self.exists(name):
            self.lb_pool.delete_pool([name])

    def add_member(self, name, addr, port):
        if self.exists(name) and not self.member_exists(name, addr, port):
            addr_port_seq = self._get_addr_port_seq()
            self.lb_pool.add_member_v2([name], [addr_port_seq])

    def remove_member(self, name, addr, port):
        if not self.exists(name) and self.member_exists(name, addr, port):
            addr_port_seq = self._get_addr_port_seq()
            self.lb_pool.remove_member_v2([name], [addr_port_seq])

    def get_service_down_action(self, name):
        service_down_action_type = self.lb_pool.typefactory.create('LocalLB.ServiceDownAction')
        service_down_action = self.lb_pool.get_action_on_service_down([name])[0]

        if service_down_action == service_down_action_type.SERVICE_DOWN_ACTION_RESET:
            return 'SERVICE_DOWN_ACTION_RESET'
        elif service_down_action == service_down_action_type.SERVICE_DOWN_ACTION_DROP:
            return 'SERVICE_DOWN_ACTION_DROP'
        elif service_down_action == service_down_action_type.SERVICE_DOWN_ACTION_RESELECT:
            return 'SERVICE_DOWN_ACTION_RESELECT'
        else:
            return 'SERVICE_DOWN_ACTION_NONE'

    def set_service_down_action(self, name, service_down_action):
        if self.exists(name):
            service_down_action_type = self._get_service_down_action_type(service_down_action)
            self.lb_pool.set_action_on_service_down([name], [service_down_action_type])

    def set_lb_method(self, name, lb_method):
        if self.exists(name):
            lb_method_type = self._get_lb_method_type(lb_method)
            self.lb_pool.set_lb_method([name], [lb_method_type])

    def get_lb_method(self, name):
        if self.exists(name):
            lb_method_type = self.lb_pool.typefactory.create('LocalLB.LBMethod')
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

    def get_monitors(self, name):
        if self.exists(name):
            monitor_assoc = self.lb_pool.get_monitor_association([name])[0]
            return monitor_assoc.monitor_rule.monitor_templates

    def add_monitor(self, name, monitor_name):
        monitors = self.get_monitors(name)

        if not monitor_name in monitors:
            monitors.append(monitor_name)
            self._set_monitor_assoc(name, monitors)

    def remove_monitor(self, name, monitor_name):
        monitors = self.get_monitors(name)

        if monitor_name in monitors:
            monitors.remove(monitor_name)
            self._set_monitor_assoc(name, monitors)

    def _set_monitor_assoc(self, name, monitors):
        if self.exists(name):
            monitor_rule_type = self.lb_pool.typefactory.create('LocalLB.MonitorRuleType')
            if len(monitors) == 0:
                monitor_rule_type = monitor_rule_type.MONITOR_RULE_TYPE_NONE
            elif len(monitors) == 1:
                monitor_rule_type = monitor_rule_type.MONITOR_RULE_TYPE_SINGLE
            else:
                monitor_rule_type = monitor_rule_type.MONITOR_RULE_TYPE_AND_LIST

            monitor_assoc = self.lb_pool.typefactory.create('LocalLB.Pool.MonitorAssociation')
            monitor_rule = self.lb_pool.typefactory.create('LocalLB.MonitorRule')
            monitor_rule.monitor_templates = monitors
            monitor_rule.type = monitor_rule_type
            monitor_rule.quorum = 0
            monitor_assoc.pool_name = name
            monitor_assoc.monitor_rule = monitor_rule
            self.lb_pool.set_monitor_association([monitor_assoc])

    def _get_addr_port_seq(self, addr, port):
        addr_port_seq = self.lb_pool.typefactory.create('Common.AddressPortSequence')
        addr_port = self.lb_pool.typefactory.create('Common.AddressPort')
        addr_port.address = addr
        addr_port.port = port
        addr_port_seq.item = addr_port

        return addr_port_seq

    def _get_lb_method_type(self, lb_method):
        lb_method_type = self.lb_pool.typefactory.create('LocalLB.LBMethod')
        if lb_method == 'LB_METHOD_LEAST_CONNECTION_MEMBER':
            return lb_method_type.LB_METHOD_LEAST_CONNECTION_MEMBER
        elif lb_method == 'LB_METHOD_OBSERVED_MEMBER':
            return lb_method_type.LB_METHOD_OBSERVED_MEMBER
        elif lb_method == 'LB_METHOD_PREDICTIVE_MEMBER':
            return lb_method_type.LB_METHOD_PREDICTIVE_MEMBER
        else:
            return lb_method_type.LB_METHOD_ROUND_ROBIN

    def _get_service_down_action_type(self, service_down_action):
        service_down_action_type = self.lb_pool.typefactory.create('LocalLB.ServiceDownAction')

        if service_down_action == 'SERVICE_DOWN_ACTION_RESET':
            return service_down_action_type.SERVICE_DOWN_ACTION_RESET
        elif service_down_action == 'SERVICE_DOWN_ACTION_DROP':
            return service_down_action_type.SERVICE_DOWN_ACTION_DROP
        elif service_down_action == 'SERVICE_DOWN_ACTION_RESELECT':
            return service_down_action_type.SERVICE_DOWN_ACTION_RESELECT
        else:
            return service_down_action_type.SERVICE_DOWN_ACTION_NONE

    def exists(self, name):
        if name in self.lb_pool.get_list():
            return True

    def member_exists(self, name, addr, port):
        members = self.lb_pool.get_member_v2([name])

        for member in members[0]:
            if os.path.basename(member.address) == addr and int(member.port) == port:
                return True

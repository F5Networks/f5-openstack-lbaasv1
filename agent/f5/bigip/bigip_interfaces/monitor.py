# Local Traffic - Monitor


class Monitor(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.Monitor')

        # iControl helper objects
        self.lb_monitor = self.bigip.icontrol.LocalLB.Monitor

    def create(self, name, mon_type, interval,
               timeout, send_text=None, recv_text=None):
        if not self.exists(name):
            monitor_type = self._get_monitor_type(mon_type)
            template = self.lb_monitor.typefactory.create(
                                    'LocalLB.Monitor.MonitorTemplate')
            template.template_name = name
            template.template_type = monitor_type

            monitor_ipport = self.lb_monitor.typefactory.create(
                                            'LocalLB.MonitorIPPort')
            ipport_def = self.lb_monitor.typefactory.create(
                                            'Common.IPPortDefinition')
            ipport_def.address = '0.0.0.0'
            ipport_def.port = 0
            monitor_ipport.address_type = \
                self.lb_monitor.typefactory.create(
                'LocalLB.AddressType').ATYPE_STAR_ADDRESS_STAR_PORT
            monitor_ipport.ipport = ipport_def

            template_attributes = self.lb_monitor.typefactory.create(
                                    'LocalLB.Monitor.CommonAttributes')
            template_attributes.parent_template = str.lower(mon_type)
            template_attributes.interval = interval
            template_attributes.timeout = timeout
            template_attributes.dest_ipport = monitor_ipport
            template_attributes.is_read_only = False
            template_attributes.is_directly_usable = True

            self.lb_monitor.create_template([template],
                                            [template_attributes])

            if str.lower(mon_type) in ['tcp', 'http']:
                self.set_send_string(name, send_text)
                self.set_recv_string(name, recv_text)

    def delete(self, name):
        if self.exists(name):
            self.lb_monitor.delete_template([name])

    def get_type(self, name):
        if self.exists(name):
            monitor_temp_type_type = self.lb_monitor.typefactory.create(
                                        'LocalLB.Monitor.TemplateType')
            monitor_temp_type = self.lb_monitor.get_template_type(
                                                            [name])[0]

            if monitor_temp_type == monitor_temp_type_type.TTYPE_HTTP:
                return 'HTTP'
            elif monitor_temp_type == monitor_temp_type_type.TTYPE_TCP:
                return 'TCP'
            elif monitor_temp_type == monitor_temp_type_type.TTYPE_ICMP:
                return 'ICMP'
            else:
                # TODO: add exception for unsupported monitor type
                pass

    def get_interval(self, name):
        if self.exists(name):
            prop_type = self.lb_monitor.typefactory.create(
                    'LocalLB.Monitor.IntPropertyType').ITYPE_INTERVAL
            return self.lb_monitor.get_template_integer_property(
                                        [name], [prop_type])[0].value

    def set_interval(self, name, interval):
        if self.exists(name):
            value = self.lb_monitor.typefactory.create(
                                'LocalLB.Monitor.IntegerValue')
            value.type = self.lb_monitor.typefactory.create(
                                'Monitor.IntPropertyType').ITYPE_INTERVAL
            value.value = int(interval)
            self.lb_monitor.set_template_integer_property([name], [value])

    def get_timeout(self, name):
            prop_type = self.lb_monitor.typefactory.create(
                        'LocalLB.Monitor.IntPropertyType').ITYPE_TIMEOUT
            return self.lb_monitor.get_template_integer_property(
                                            [name], [prop_type])[0].value

    def set_timeout(self, name, timeout):
        if self.exists(name):
            value = self.lb_monitor.typefactory.create(
                                'LocalLB.Monitor.IntegerValue')
            value.type = self.lb_monitor.typefactory.create(
                                'Monitor.IntPropertyType').ITYPE_TIMEOUT
            value.value = int(timeout)
            self.lb_monitor.set_template_integer_property([name], [value])

    def get_send_string(self, name):
        if self.exists(name) and self.get_type(name) in ['TCP', 'HTTP']:
            prop_type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_SEND
            return self.lb_monitor.get_template_string_property(
                                        [name], [prop_type])[0].value

    def set_send_string(self, name, send_text):
        if self.exists(name) and send_text and self.get_type(name) in \
            ['TCP', 'HTTP']:
            value = self.lb_monitor.typefactory.create(
                            'LocalLB.Monitor.StringValue')
            value.type = self.lb_monitor.typefactory.create(
                            'LocalLB.Monitor.StrPropertyType').STYPE_SEND
            value.value = send_text
            self.lb_monitor.set_template_string_property([name], [value])

    def get_recv_string(self, name):
        if self.exists(name) and self.get_type(name) in \
            ['TCP', 'HTTP']:
            prop_type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_RECEIVE
            return self.lb_monitor.get_template_string_property(
                                            [name], [prop_type])[0].value

    def set_recv_string(self, name, recv_text):
        if self.exists(name) and recv_text and self.get_type(name) in \
            ['TCP', 'HTTP']:
            value = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StringValue')
            value.type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_RECEIVE
            value.value = recv_text
            self.lb_monitor.set_template_string_property([name], [value])

    def _get_monitor_type(self, type_str):
        type_str = str.upper(type_str)
        monitor_temp_type = self.lb_monitor.typefactory.create(
                                        'LocalLB.Monitor.TemplateType')
        if type_str == 'TCP':
            return monitor_temp_type.TTYPE_TCP
        elif type_str == 'HTTP':
            return monitor_temp_type.TTYPE_HTTP
        elif type_str == 'ICMP':
            return monitor_temp_type.TTYPE_ICMP
        else:
            # TODO: raise exception for unsupported monitor type
            pass

    def exists(self, name):
        for template in self.lb_monitor.get_template_list():
            if template.template_name == name:
                return True

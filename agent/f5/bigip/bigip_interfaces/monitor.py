from f5.common import constants as const
from f5.bigip import exceptions
from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import strip_folder_and_prefix

from suds import WebFault
import os
import netaddr

import logging

LOG = logging.getLogger(__name__)


class Monitor(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.Monitor')

        # iControl helper objects
        self.lb_monitor = self.bigip.icontrol.LocalLB.Monitor

    @icontrol_folder
    def create(self, name=None, mon_type=None, interval=5,
               timeout=16, send_text=None, recv_text=None,
               folder='Common'):
        if not self.exists(name=name, folder=folder):
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

            monitor_ipport.address_type = self.lb_monitor.typefactory.create(
                'LocalLB.AddressType').ATYPE_STAR_ADDRESS_STAR_PORT

            monitor_ipport.ipport = ipport_def

            template_attributes = self.lb_monitor.typefactory.create(
                                    'LocalLB.Monitor.CommonAttributes')

            if str(mon_type) == 'ICMP':
                template_attributes.parent_template = 'gateway_icmp'
            else:
                template_attributes.parent_template = mon_type.lower()

            template_attributes.interval = interval
            template_attributes.timeout = timeout
            template_attributes.dest_ipport = monitor_ipport
            template_attributes.is_read_only = False
            template_attributes.is_directly_usable = True

            try:
                self.lb_monitor.create_template([template],
                                                [template_attributes])
                if mon_type.lower() in ['tcp', 'http']:
                    self.set_send_string(name, send_text)
                    self.set_recv_string(name, recv_text)
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    LOG.error(_(
                        'tried to create a Monitor when exists'))
                    return False
                else:
                    raise wf
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            try:
                self.lb_monitor.delete_template([name])
            except WebFault as wf:
                if "is in use" in str(wf.message):
                    return False
            return True
        else:
            return False

    @icontrol_folder
    def get_type(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            monitor_temp_type_type = self.lb_monitor.typefactory.create(
                                        'LocalLB.Monitor.TemplateType')
            monitor_temp_type = self.lb_monitor.get_template_type(
                                                            [name])[0]

            if monitor_temp_type == monitor_temp_type_type.TTYPE_HTTP:
                return 'HTTP'
            elif monitor_temp_type == monitor_temp_type_type.TTYPE_TCP:
                return 'TCP'
            elif monitor_temp_type == \
                    monitor_temp_type_type.TTYPE_GATEWAY_ICMP:
                return 'ICMP'
            else:
                # TODO: add exception for unsupported monitor type
                pass

    @icontrol_folder
    def get_interval(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                    'LocalLB.Monitor.IntPropertyType').ITYPE_INTERVAL
            return self.lb_monitor.get_template_integer_property(
                                        [name], [prop_type])[0].value

    @icontrol_folder
    def set_interval(self, name=None, interval=5, folder='Common'):
        if self.exists(name=name, folder=folder):
            value = self.lb_monitor.typefactory.create(
                                'LocalLB.Monitor.IntegerValue')
            value.type = self.lb_monitor.typefactory.create(
                                'LocalLB.Monitor.IntPropertyType').ITYPE_INTERVAL
            value.value = int(interval)
            self.lb_monitor.set_template_integer_property([name], [value])
            return True
        else:
            return False

    @icontrol_folder
    def get_timeout(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                        'LocalLB.Monitor.IntPropertyType').ITYPE_TIMEOUT
            return self.lb_monitor.get_template_integer_property(
                                            [name], [prop_type])[0].value

    @icontrol_folder
    def set_timeout(self, name=None, timeout=16, folder='Common'):
        if self.exists(name=name, folder=folder):
            value = self.lb_monitor.typefactory.create(
                                'LocalLB.Monitor.IntegerValue')
            value.type = self.lb_monitor.typefactory.create(
                                'LocalLB.Monitor.IntPropertyType').ITYPE_TIMEOUT
            value.value = int(timeout)
            self.lb_monitor.set_template_integer_property([name], [value])
            return True
        else:
            return False

    @icontrol_folder
    def get_send_string(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_SEND
            return self.lb_monitor.get_template_string_property(
                                        [name], [prop_type])[0].value

    @icontrol_folder
    def set_send_string(self, name=None, send_text=None, folder='Common'):
        if self.exists(name=name, folder=folder) and send_text:
            value = self.lb_monitor.typefactory.create(
                            'LocalLB.Monitor.StringValue')
            value.type = self.lb_monitor.typefactory.create(
                            'LocalLB.Monitor.StrPropertyType').STYPE_SEND
            value.value = send_text
            self.lb_monitor.set_template_string_property([name], [value])
            return True
        else:
            return False

    @icontrol_folder
    def get_recv_string(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_RECEIVE
            return self.lb_monitor.get_template_string_property(
                                            [name], [prop_type])[0].value

    @icontrol_folder
    def set_recv_string(self, name=None, recv_text=None, folder='Common'):
        if self.exists(name=name, folder=folder) and recv_text:
            value = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StringValue')
            value.type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_RECEIVE
            value.value = recv_text
            self.lb_monitor.set_template_string_property([name], [value])
            return True
        else:
            return False

    def _get_monitor_type(self, type_str):
        type_str = type_str.upper()
        monitor_temp_type = self.lb_monitor.typefactory.create(
                                        'LocalLB.Monitor.TemplateType')
        if type_str == 'TCP':
            return monitor_temp_type.TTYPE_TCP
        elif type_str == 'HTTP':
            return monitor_temp_type.TTYPE_HTTP
        elif type_str == 'HTTPS':
            return monitor_temp_type.TTYPE_HTTPS
        elif type_str == 'ICMP':
            return monitor_temp_type.TTYPE_GATEWAY_ICMP
        elif type_str == 'UDP':
            return monitor_temp_type.TTYPE_UDP
        elif type_str == 'INBAND':
            return monitor_temp_type.TTYPE_INBAND
        else:
            raise exceptions.UnknownMonitorType(
                                        'Unknown monitor %s' % type_str)

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        for template in self.lb_monitor.get_template_list():
            if template.template_name == name:
                return True

    @icontrol_folder
    def get_monitors(self, folder='Common'):
        monitors = self.lb_monitor.get_template_list() 
        return monitors


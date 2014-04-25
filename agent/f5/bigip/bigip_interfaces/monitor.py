##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.bigip import exceptions
from f5.common.logger import Log
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import icontrol_rest_folder

from suds import WebFault


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
        if not self.exists(name=name, mon_type=mon_type, folder=folder):
            template = self.lb_monitor.typefactory.create(
                                    'LocalLB.Monitor.MonitorTemplate')
            template.template_name = name
            template.template_type = self._get_monitor_type(mon_type)

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

            if str(mon_type) == 'PING':
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
                    Log.error('Monitor',
                              'tried to create a Monitor when exists')
                    return False
                else:
                    raise wf
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, mon_type=None, folder='Common'):
        if not mon_type:
            mon_type = self.get_type(name=name, folder=folder)
        if mon_type and self.exists(name=name,
                                    mon_type=mon_type,
                                    folder=folder):
            try:
                self.lb_monitor.delete_template([name])
            except WebFault as wf:
                if "is in use" in str(wf.message):
                    return False
            return True
        return False

    @icontrol_folder
    def get_type(self, name=None, folder='Common'):
        try:
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
                return None
        except WebFault as wf:
            if "was not found" in str(wf.message):
                return None
            else:
                raise

    @icontrol_folder
    def get_interval(self, name=None, mon_type=None, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                    'LocalLB.Monitor.IntPropertyType').ITYPE_INTERVAL
            return self.lb_monitor.get_template_integer_property(
                                        [name], [prop_type])[0].value

    @icontrol_folder
    def set_interval(self, name=None,
                     mon_type=None, interval=5, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder):
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
    def get_timeout(self, name=None, mon_type=None, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                        'LocalLB.Monitor.IntPropertyType').ITYPE_TIMEOUT
            return self.lb_monitor.get_template_integer_property(
                                            [name], [prop_type])[0].value

    @icontrol_folder
    def set_timeout(self, name=None, mon_type=None,
                    timeout=16, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder):
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
    def get_send_string(self, name=None, mon_type=None, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_SEND
            return self.lb_monitor.get_template_string_property(
                                        [name], [prop_type])[0].value

    @icontrol_folder
    def set_send_string(self, name=None, mon_type=None,
                        send_text=None, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder) and \
           send_text:
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
    def get_recv_string(self, name=None, mon_type=None, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder):
            prop_type = self.lb_monitor.typefactory.create(
                         'LocalLB.Monitor.StrPropertyType').STYPE_RECEIVE
            return self.lb_monitor.get_template_string_property(
                                            [name], [prop_type])[0].value

    @icontrol_folder
    def set_recv_string(self, name=None, mon_type=None,
                        recv_text=None, folder='Common'):
        if self.exists(name=name, mon_type=mon_type, folder=folder) and \
           recv_text:
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
        elif type_str == 'PING':
            return monitor_temp_type.TTYPE_GATEWAY_ICMP
        elif type_str == 'ICMP':
            return monitor_temp_type.TTYPE_GATEWAY_ICMP
        elif type_str == 'UDP':
            return monitor_temp_type.TTYPE_UDP
        elif type_str == 'INBAND':
            return monitor_temp_type.TTYPE_INBAND
        else:
            raise exceptions.UnknownMonitorType(
                                        'Unknown monitor %s' % type_str)

    def _get_monitor_rest_type(self, type_str):
        type_str = type_str.upper()
        if type_str == 'TCP':
            return 'tcp'
        elif type_str == 'HTTP':
            return 'http'
        elif type_str == 'HTTPS':
            return 'https'
        elif type_str == 'PING':
            return 'gateway-icmp'
        elif type_str == 'ICMP':
            return 'gateway-icmp'
        elif type_str == 'UDP':
            return 'udp'
        elif type_str == 'INBAND':
            return 'inband'
        else:
            raise exceptions.UnknownMonitorType(
                                        'Unknown monitor %s' % type_str)

    #TODO: turn this into iControl ReST.
    #That will require us to know the type in every call
    #to exists, because it's in the URL path.

    @icontrol_rest_folder
    def exists(self, name=None, mon_type=None, folder='Common'):
        if name and mon_type:
            mon_type = self._get_monitor_rest_type(mon_type)
            request_url = self.bigip.icr_url + '/ltm/monitor/' + mon_type + '/'
            request_url += '~' + folder + '~' + name
            response = self.bigip.icr_session.get(request_url)
            if response.status_code < 400:
                return True
            else:
                return False
        else:
            return False

        #for template in self.lb_monitor.get_template_list():
        #    if template.template_name == name:
        #        return True

    @icontrol_folder
    def get_monitors(self, folder='Common'):
        monitors = self.lb_monitor.get_template_list()
        return monitors

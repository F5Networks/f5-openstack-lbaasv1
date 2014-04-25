##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

#from f5.common.logger import Log
#from f5.bigip.bigip_interfaces import icontrol_rest_folder
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import domain_address

#import json
#import requests
#import urllib


class ARP(object):

    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['Networking.ARP'])

        # iControl helper objects
        self.net_arp = self.bigip.icontrol.Networking.ARP

    #@icontrol_rest_folder
    #@domain_address
    #def create(self, ip_address=None, mac_address=None, folder='Common'):
    #    Log.debug('ARP::create',"ip_address=%s, mac_address=%s, folder=%s"
    #              % (ip_address, mac_address, folder))
    #    if not self.exists(ip_address=ip_address, folder=folder):
    #        payload = dict()
    #        payload['name'] = ip_address
    #        payload['partition'] = folder
    #        payload['ipAddress'] = ip_address
    #        payload['macAddress'] = mac_address
    #        request_url = self.icr_url + '/net/arp/'
    #        response = self.icr_session.post(request_url,
    #                              data=json.dumps(payload))
    #        Log.debug('ARP::create response',
    #                  '%s' % response.json())
    #        if response.status_code < 400:
    #            return True
    #        else:
    #            return False
    #    else:
    #        return False
    @icontrol_folder
    @domain_address
    def create(self, ip_address=None, mac_address=None, folder='Common'):
        if not self.exists(ip_address=ip_address, folder=folder):
            # ARP entries can't handle %0 on them like other
            # TMOS objects.
            ip_address = self._remove_route_domain_zero(ip_address)
            entry = \
              self.net_arp.typefactory.create('Networking.ARP.StaticEntry')
            entry.address = ip_address
            entry.mac_address = mac_address
            self.net_arp.add_static_entry([entry])

    #@icontrol_rest_folder
    #@domain_address
    #def delete(self, ip_address=None, folder='Common'):
    #    if self.exists(ip_address=ip_address, folder=folder):
    #        request_url = self.icr_url + '/net/arp/'
    #        request_url += '~' + folder + '~' + urllib.quote(ip_address)
    #        response = self.icr_session.delete(request_url)
    #        if response.status_code < 400:
    #            return True
    #        else:
    #            return False
    #    else:
    #        return False

    @icontrol_folder
    @domain_address
    def delete(self, ip_address=None, folder='Common'):
        if self.exists(ip_address=ip_address, folder=folder):
            # ARP entries can't handle %0 on them like other
            # TMOS objects.
            ip_address = self._remove_route_domain_zero(ip_address)
            self.net_arp.delete_static_entry_v2(
                                ['/' + folder + '/' + ip_address])

    #@icontrol_rest_folder
    #@domain_address
    #def get(self, ip_address=None, folder='Common'):
    #    if ip_address:
    #        request_url = self.icr_url + '/net/arp/'
    #        request_url += '~' + folder + '~' + urllib.quote(ip_address)
    #        response = self.icr_session.get(request_url)
    #        Log.debug('ARP::get response',
    #                  '%s' % response.json())
    #        if response.status_code < 400:
    #            response_obj = json.loads(response.text)
    #            return [response_obj]
    #        else:
    #            return []
    #    else:
    #        request_filter = 'partition eq ' + folder
    #        request_url = self.icr_url + '/net/arp'
    #        request_url += '?$filter=' + request_filter
    #        response = self.icr_session.get(request_url)
    #        Log.debug('ARP::get response',
    #                  '%s' % response.json())
    #        if response.status_code < 400:
    #            response_obj = json.loads(response.text)
    #            if 'items' in response_obj:
    #                return response_obj['items']
    #            else:
    #                return []
    #        else:
    #            return []

    #@icontrol_rest_folder
    #def delete_all(self, folder='Common'):
    #    entries = self.get(folder=folder)
    #    for entry in entries:
    #        request_url = self.icr_url + '/net/arp/'
    #        request_url += '~' + entry['partition'] + '~' + \
    #                       urllib.quote(entry['name'])
    #        response = self.icr_session.delete(request_url)
    @icontrol_folder
    def delete_all(self, folder='Common'):
        self.net_arp.delete_all_static_entries()

    #@icontrol_rest_folder
    #@domain_address
    #def exists(self, ip_address=None, folder='Common'):
    #    request_url = self.icr_url + '/net/arp/'
    #    request_url += '~' + folder + '~' + urllib.quote(ip_address)
    #
    #    response = self.icr_session.get(request_url)
    #    Log.debug('ARP::exists response',
    #                  '%s' % response.text)
    #    if response.status_code < 400:
    #        return json.loads(response.text)
    #    else:
    #        return None
    @icontrol_folder
    @domain_address
    def exists(self, ip_address=None, folder='Common'):
        # ARP entries can't handle %0 on them like other
        # TMOS objects.
        ip_address = self._remove_route_domain_zero(ip_address)
        if '/' + folder + '/' + ip_address in \
                  self.net_arp.get_static_entry_list():
            return True
        else:
            return False

    def _remove_route_domain_zero(self, ip_address):
        decorator_index = ip_address.find('%0')
        if decorator_index > 0:
            ip_address = ip_address[:decorator_index]
        return ip_address

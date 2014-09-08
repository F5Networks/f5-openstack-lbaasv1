##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common.logger import Log
from f5.bigip.bigip_interfaces import icontrol_rest_folder

import json


class L2GRE(object):

    def __init__(self, bigip):
        self.bigip = bigip

    @icontrol_rest_folder
    def create_multipoint_profile(self, name=None, folder='Common'):
        if not self.profile_exists(name=name, folder=folder):
            payload = dict()
            payload['name'] = name
            payload['partition'] = folder
            payload['defaultsFrom'] = 'gre'
            payload['floodingType'] = 'multipoint'
            payload['encapsulation'] = 'transparent-ethernet-bridging'
            request_url = self.bigip.icr_url + '/net/tunnels/gre/'
            response = self.bigip.icr_session.post(request_url,
                                  data=json.dumps(payload))
            if response.status_code < 400:
                return True
            else:
                Log.error('L2GRE', response.text)
                return False
        else:
            return False

    @icontrol_rest_folder
    def delete_profile(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/net/tunnels/gre/'
        request_url += '~' + folder + '~' + name

        response = self.bigip.icr_session.delete(request_url)

        if response.status_code < 400:
            return True
        else:
            if response.status_code != 404:
                Log.error('L2GRE', response.text)
            return False

    @icontrol_rest_folder
    def create_multipoint_tunnel(self, name=None,
                                 profile_name=None,
                                 self_ip_address=None,
                                 greid=0,
                                 description=None,
                                 folder='Common'):
        if not self.tunnel_exists(name=name, folder=folder):
            payload = dict()
            payload['name'] = name
            payload['partition'] = folder
            payload['profile'] = profile_name
            payload['key'] = greid
            payload['localAddress'] = self_ip_address
            payload['remoteAddress'] = '0.0.0.0'
            if description:
                payload['description'] = description
            request_url = self.bigip.icr_url + '/net/tunnels/tunnel/'
            response = self.bigip.icr_session.post(request_url,
                                  data=json.dumps(payload))
            if response.status_code < 400:
                if not folder == 'Common':
                    self.bigip.route.add_vlan_to_domain(
                                    name=name,
                                    folder=folder)
                return True
            else:
                Log.error('L2GRE', response.text)
                return False
        else:
            return False

    @icontrol_rest_folder
    def delete_tunnel(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/net/tunnels/tunnel/'
        request_url += '~' + folder + '~' + name

        response = self.bigip.icr_session.delete(request_url)

        if response.status_code < 400:
            return True
        else:
            if response.status_code != 404:
                Log.error('L2GRE', response.text)
            return False

    @icontrol_rest_folder
    def get_fdb_entry(self,
                      tunnel_name=None,
                      mac=None,
                      folder='Common'):
        request_url = self.bigip.icr_url + '/net/fdb/tunnel/'
        request_url += '~' + folder + '~' + tunnel_name
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'records' in response_obj:
                if not mac:
                    return response_obj['records']
                else:
                    for record in response_obj['records']:
                        if record['name'] == mac:
                            return record
            return []
        else:
            if response.status_code != 404:
                Log.error('L2GRE', response.text)
            return []

    @icontrol_rest_folder
    def add_fdb_entry(self,
                      tunnel_name=None,
                      mac_address=None,
                      vtep_ip_address=None,
                      arp_ip_address=None,
                      folder=None):
        request_url = self.bigip.icr_url + '/net/fdb/tunnel/'
        request_url += '~' + folder + '~' + tunnel_name
        records = self.get_fdb_entry(tunnel_name=tunnel_name,
                                     mac=None,
                                     folder=folder)
        fdb_entry = dict()
        fdb_entry['name'] = mac_address
        fdb_entry['endpoint'] = vtep_ip_address
        records.append(fdb_entry)
        payload = dict()
        payload['records'] = records
        response = self.bigip.icr_session.put(request_url,
                                        data=json.dumps(payload))
        if response.status_code < 400:
            if arp_ip_address:
                if self.bigip.arp.create(ip_address=arp_ip_address,
                                         mac_address=mac_address,
                                         folder=folder):
                    return True
                else:
                    return False
            return True
        else:
            Log.error('L2GRE', response.text)
            return False

    @icontrol_rest_folder
    def delete_fdb_entry(self,
                         tunnel_name=None,
                         mac_address=None,
                         arp_ip_address=None,
                         folder='Common'):
        if arp_ip_address:
            self.bigip.arp.delete(ip_address=arp_ip_address,
                                  folder=folder)
        request_url = self.bigip.icr_url + '/net/fdb/tunnel/'
        request_url += '~' + folder + '~' + tunnel_name
        records = self.get_fdb_entry(tunnel_name=tunnel_name,
                                     mac=None,
                                     folder=folder)
        if not records:
            return False
        records = [record for record in records \
                         if record.get('name') != mac_address]
        if len(records) == 0:
            records = None
        payload = dict()
        payload['records'] = records
        response = self.bigip.icr_session.put(request_url,
                                        data=json.dumps(payload))
        if response.status_code < 400:
            return True
        else:
            if response.status_code != 404:
                Log.error('L2GRE', response.text)
            return False

    @icontrol_rest_folder
    def delete_all_fdb_entries(self,
                         tunnel_name=None,
                         folder='Common'):
        request_url = self.bigip.icr_url + '/net/fdb/tunnel/'
        request_url += '~' + folder + '~' + tunnel_name
        response = self.bigip.icr_session.put(request_url,
                                        data=json.dumps({'records': None}))
        if response.status_code < 400:
            return True
        else:
            Log.error('L2GRE', response.text)
            return False

    @icontrol_rest_folder
    def get_profiles(self, folder='Common'):
        request_url = self.bigip.icr_url + '/net/tunnels/gre'
        request_filter = 'partition eq ' + folder
        request_url += '?$filter=' + request_filter
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return_obj = json.loads(response.text)
            if 'items' in return_obj:
                return return_obj['items']
            else:
                return None
        else:
            if response.status_code != 404:
                Log.error('L2GRE', response.text)
            return None

    @icontrol_rest_folder
    def profile_exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/net/tunnels/gre/'
        request_url += '~' + folder + '~' + name

        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return json.loads(response.text)
        else:
            return None

    @icontrol_rest_folder
    def get_tunnels(self, folder='Common'):
        request_url = self.bigip.icr_url + '/net/tunnels/tunnel'
        request_filter = 'partition eq ' + folder
        request_url += '?$filter=' + request_filter
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return_obj = json.loads(response.text)
            if 'items' in return_obj:
                return return_obj['items']
            else:
                return None
        else:
            return None

    @icontrol_rest_folder
    def get_tunnel_with_description(self, description=None, folder='Common'):
        if description:
            request_url = self.bigip.icr_url + '/net/tunnels/tunnel/'
            request_filter = 'partition eq ' + folder
            request_url += '?$filter=' + request_filter
            response = self.bigip.icr_session.get(request_url)
            if response.status_code < 400:
                return_obj = json.loads(response.text)
                if 'items' in return_obj:
                    for tunnel in return_obj['items']:
                        if tunnel['description'] == description:
                            return tunnel
                return None
            else:
                return None
        else:
            return None

    @icontrol_rest_folder
    def tunnel_exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/net/tunnels/tunnel/'
        request_url += '~' + folder + '~' + name

        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return json.loads(response.text)
        else:
            return None

from f5.common.logger import Log
from f5.common import constants

import json
import requests


class L2GRE(object):

    def __init__(self, bigip):
        self.bigip = bigip

        icontrol = bigip.icontrol

        self.icr_session = requests.session()
        self.icr_session.auth = (icontrol.username,
                                     icontrol.password)
        self.icr_session.verify = False
        self.icr_session.headers.update(
                                 {'Content-Type': 'application/json'})
        self.icr_url = 'https://%s/mgmt/tm' % icontrol.hostname

    def create_multipoint_profile(self, name=None, folder='Common'):
        if not self.profile_exists(name=name, folder=folder):
            payload = dict()
            payload['name'] = name
            payload['partition'] = folder
            payload['defaultsFrom'] = 'gre'
            payload['floodingType'] = 'multipoint'
            payload['encapsulation'] = 'transparent-ethernet-bridging'
            request_url = self.icr_url + '/net/tunnels/gre/'
            response = self.icr_session.post(request_url,
                                  data=json.dumps(payload))
            if response.status_code < 400:
                return True
            else:
                return False
        else:
            return False

    def delete_profile(self, name=None, folder='Common'):
        request_url = self.icr_url + '/net/tunnels/gre/'
        request_url += '~' + folder + '~' + name

        response = self.icr_session.delete(request_url)

        if response.status_code < 400:
            return True
        else:
            return False

    def create_multipoint_tunnel(self, name=None,
                                 profile_name=None,
                                 self_ip_address=None,
                                 greid=0,
                                 folder='Common'):
        if not self.tunnel_exists(name=name, folder=folder):
            payload = dict()
            payload['name'] = name
            payload['partition'] = folder
            payload['profile'] = profile_name
            payload['key'] = greid
            payload['localAddress'] = self_ip_address
            payload['remoteAddress'] = '0.0.0.0'
            request_url = self.icr_url + '/net/tunnels/tunnel/'
            response = self.icr_session.post(request_url,
                                  data=json.dumps(payload))

            if response.status_code < 400:
                return True
            else:
                return False
        else:
            return False

    def delete_tunnel(self, name=None, folder='Common'):
        request_url = self.icr_url + '/net/tunnels/tunnel/'
        request_url += '~' + folder + '~' + name

        response = self.icr_session.delete(request_url)

        if response.status_code < 400:
            return True
        else:
            return False

    def get_fdb_entry(self,
                      tunnel_name=None,
                      mac=None,
                      folder='Common'):
        request_url = self.icr_url + '/net/fdb/tunnel'
        request_url += '/~' + folder + '~' + tunnel_name
        response = self.icr_session.get(request_url)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'records' in response_obj:
                if not mac:
                    return response_obj['records']
                else:
                    for record in response_obj['records']:
                        if record['name'] == mac:
                            return record
                return None
        else:
            return None

    def add_fdb_entry(self,
                      tunnel_name=None,
                      mac_address=None,
                      vtep_ip_address=None,
                      folder=None):
        request_url = self.icr_url + '/net/fdb/tunnel'
        request_url += '/~' + folder + '~' + tunnel_name

        records = []
        fdb_entry = dict()
        fdb_entry['name'] = mac_address
        fdb_entry['endpoint'] = vtep_ip_address
        records.append(fdb_entry)
        payload = dict()
        payload['records'] = records

        response = self.icr_session.put(request_url,
                                        data=json.dumps(payload))
        if response.status_code < 400:
            return True
        else:
            return False

    def delete_fdb_entry(self,
                         tunnel_name=None,
                         mac_address=None,
                         folder='Common'):

        request_url = self.icr_url + '/net/fdb/tunnel'
        request_url += '/~' + folder + '~' + tunnel_name

        records = self.get_fdb_entry(self,
                                     tunnel_name=tunnel_name,
                                     mac=None,
                                     folder='Common')
        if not records:
            return False

        records[:] = [record for record in records \
                         if record.get('name') != mac_address]
        payload = dict()
        payload['records'] = records

        response = self.icr_session.put(request_url,
                                        data=json.dumps(payload))
        if response.status_code < 400:
            return True
        else:
            return False

    def get_profiles(self, folder='Common'):
        request_url = self.icr_url + '/net/tunnels/gre'
        request_filter = 'partition eq ' + folder
        request_url += '?$filter=' + request_filter
        response = self.icr_session.get(request_url)
        if response.status_code < 400:
            return_obj = json.loads(response.text)
            return return_obj['items']
        else:
            return None

    def profile_exists(self, name=None, folder='Common'):
        request_url = self.icr_url + '/net/tunnels/gre'
        request_url += '/~' + folder + '~' + name

        response = self.icr_session.get(request_url)
        if response.status_code < 400:
            return json.loads(response.text)
        else:
            return None

    def get_tunnels(self, folder='Common'):
        request_url = self.icr_url + '/net/tunnels/gre'
        request_filter = 'partition eq ' + folder
        request_url += '?$filter=' + request_filter
        response = self.icr_session.get(request_url)
        if response.status_code < 400:
            return_obj = json.loads(response.text)
            return return_obj['items']
        else:
            return None

    def tunnel_exists(self, name=None, folder='Common'):
        request_url = self.icr_url + '/net/tunnels/tunnel'
        request_url += '/~' + folder + '~' + name

        response = self.icr_session.get(request_url)
        if response.status_code < 400:
            return json.loads(response.text)
        else:
            return None

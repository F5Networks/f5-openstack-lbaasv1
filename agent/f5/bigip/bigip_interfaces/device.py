##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

import time
import json

from suds import WebFault
from f5.common.logger import Log
from f5.common import constants as const

from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder


# Management - Device
class Device(object):
    def __init__(self, bigip):
        self.bigip = bigip
        self.bigip.devicename = None

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(
                                           ['Management.Device',
                                            'Management.Trust']
                                           )

        # iControl helper objects
        self.mgmt_dev = self.bigip.icontrol.Management.Device
        self.mgmt_trust = self.bigip.icontrol.Management.Trust

        # create empty lock instance ID
        self.lock = None

    def get_device_name(self):
        if not self.bigip.devicename:
            request_url = self.bigip.icr_url + '/cm/device'
            request_filter = '/?$select=name,selfDevice'
            request_filter += '&filter partition eq Common'
            request_url += request_filter
            response = self.bigip.icr_session.get(request_url, data=None)
            if response.status_code < 400:
                response_obj = json.loads(response.text)
                if 'items' in response_obj:
                    devices = response_obj['items']
                    for device in devices:
                        if device['selfDevice'] == 'true':
                            self.bigip.devicename = device['name']
        return self.bigip.devicename

    def get_all_device_names(self):
        request_url = self.bigip.icr_url + '/cm/device'
        request_filter = '/?$select=name&filter partition eq Common'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'items' in response_obj:
                devices = response_obj['items']
                device_names = []
                for device in devices:
                    device_names.append(device['name'])
                return device_names
        else:
            return []

    def get_lock(self):
        current_lock = self._get_lock()
        new_lock = int(time.time())

        self.bigip.system.set_folder('/Common')
        if current_lock:
            if (new_lock - current_lock) > const.CONNECTION_TIMEOUT:
                Log.info('Device', 'Locking device %s with lock %s'
                           % (self.mgmt_dev.get_local_device(), new_lock))
                self._set_lock(new_lock)
                return True
            else:
                return False
        else:
            Log.info('Device', 'Locking device %s with lock %s'
                       % (self.mgmt_dev.get_local_device(), new_lock))
            self._set_lock(int(time.time()))
            return True

    def release_lock(self):
        self.bigip.system.set_folder('/Common')
        dev_name = self.mgmt_dev.get_local_device()
        current_lock = self._get_lock()

        if current_lock == self.lock:
            Log.info('Device', 'Releasing device lock for %s'
                       % self.mgmt_dev.get_local_device())
            self.mgmt_dev.set_comment([dev_name], [''])
            return True
        else:
            Log.info('Device', 'Device has foreign lock instance on %s '
                       % self.mgmt_dev.get_local_device() + ' with lock %s '
                       % current_lock)
            return False

    def _get_lock(self):
        self.bigip.system.set_folder('/Common')
        dev_name = self.mgmt_dev.get_local_device()
        current_lock = self.mgmt_dev.get_comment([dev_name])[0]
        if current_lock.startswith(const.DEVICE_LOCK_PREFIX):
            return int(current_lock.replace(const.DEVICE_LOCK_PREFIX, ''))

    def _set_lock(self, lock):
        self.bigip.system.set_folder('/Common')
        dev_name = self.mgmt_dev.get_local_device()
        self.lock = lock
        lock_comment = const.DEVICE_LOCK_PREFIX + str(lock)
        self.mgmt_dev.set_comment([dev_name], [lock_comment])

    def get_mgmt_addr(self):
        request_url = self.bigip.icr_url + '/cm/device/~Common'
        request_url += '~' + self.get_device_name()
        request_filter = '/?$select=managementIp'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            return response_obj['managementIp']
        else:
            return None
        #self.bigip.system.set_folder('/Common')
        #return self.mgmt_dev.get_management_address(
        #                        [self.get_device_name()])[0]

    def get_configsync_addr(self):
        request_url = self.bigip.icr_url + '/cm/device/~Common'
        request_url += '~' + self.get_device_name()
        request_filter = '/?$select=configsyncIp'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            return response_obj['configsyncIp']
        else:
            return None
        #self.bigip.system.set_folder('/Common')
        #return self.mgmt_dev.get_configsync_address(
        #                        [self.get_device_name()])[0]

    @domain_address
    def set_configsync_addr(self, ip_address=None, folder='/Common'):
        self.bigip.system.set_folder('/Common')
        if not ip_address:
            ip_address = 'none'
        self.mgmt_dev.set_configsync_address([self.get_device_name()],
                                             [ip_address])

    def get_primary_mirror_addr(self):
        request_url = self.bigip.icr_url + '/cm/device/~Common'
        request_url += '~' + self.get_device_name()
        request_filter = '/?$select=mirrorIp'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            return response_obj['mirrorIp']
        else:
            return None
        #self.bigip.system.set_folder('/Common')
        #return self.mgmt_dev.get_primary_mirror_address(
        #                                   [self.get_device_name()])[0]

    @domain_address
    def set_primary_mirror_addr(self, ip_address=None, folder='/Common'):
        self.bigip.system.set_folder('/Common')
        if not ip_address:
            ip_address = 'none'
        self.mgmt_dev.set_primary_mirror_address([self.get_device_name()],
                                                 [ip_address])

    @domain_address
    def set_secondary_mirror_addr(self, ip_address=None, folder='/Common'):
        self.bigip.system.set_folder('/Common')
        if not ip_address:
            ip_address = 'none'
        self.mgmt_dev.set_secondary_mirror_address([self.get_device_name()],
                                                 [ip_address])

    def get_failover_addrs(self):
        request_url = self.bigip.icr_url + '/cm/device/~Common'
        request_url += '~' + self.get_device_name()
        request_filter = '/?$select=unicastAddress'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            return_addresses = []
            uas = response_obj['unicastAddress']
            for ua in uas:
                return_addresses.append(ua['ip'])
            return return_addresses
        else:
            return []
        #self.bigip.system.set_folder('/Common')
        #return self.mgmt_dev.get_unicast_addresses(
        #                                           [self.get_device_name()]
        #                                           )[0]

    def set_failover_addrs(self, ip_address=None, folder='/Common'):
        self.bigip.system.set_folder('/Common')
        if not ip_address:
            ip_address = ['none']
        if not isinstance(ip_address, list):
            ip_address = [ip_address]
        seq = self.mgmt_dev.typefactory.create('Common.StringSequence')
        unicast_defs = []
        for addr in ip_address:
            ipport_def = self.mgmt_dev.typefactory.create(
                                            'Common.IPPortDefinition')
            ipport_def.address = self._wash_address(ip_address=addr,
                                                    folder=folder)
            ipport_def.port = 1026
            unicast_def = self.mgmt_dev.typefactory.create(
                                   'Management.Device.UnicastAddress')
            unicast_def.effective = ipport_def
            unicast_def.source = ipport_def
            unicast_defs.append(unicast_def)
        seq.item = unicast_defs
        self.mgmt_dev.set_unicast_addresses([self.get_device_name()],
                                            [seq])

    @domain_address
    def _wash_address(self, ip_address=None, folder=None):
        return ip_address

    def get_failover_state(self):
        self.bigip.system.set_folder('/Common')
        current_dev_name = self.get_device_name()
        return self.mgmt_dev.get_failover_state([current_dev_name])[0]

    def get_device_group(self):
        request_url = self.bigip.icr_url + '/cm/device-group'
        request_filter = '/?$select=name,type'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'items' in response_obj:
                dsgs = response_obj['items']
                for dsg in dsgs:
                    if dsg['type'] == 'sync-failover':
                        return dsg['name']
                return None
        else:
            return None

        #self.bigip.system.set_folder('/')
        #device_groups = self.mgmt_dg.get_list()
        #device_group_types = self.mgmt_dg.get_type(device_groups)
        #self.bigip.system.set_folder('/Common')
        #for i in range(len(device_group_types)):
        #    if device_group_types[i] == 'DGT_FAILOVER':
        #        return os.path.basename(device_groups[i])
        #return None

    @icontrol_folder
    def remove_from_device_group(self, name=None, folder='/Common'):
        self.bigip.system.set_folder('/Common')
        if not name:
            name = self.get_device_group()

        if name:
            device_entry_seq = self.mgmt_dev.typefactory.create(
                                        'Common.StringSequence')
            device_entry_seq.values = [self.bigip.add_folder(
                                        'Common',
                                         self.get_device_name())]
            device_entry_seq_seq = self.mgmt_dev.typefactory.create(
                                        'Common.StringSequenceSequence')
            device_entry_seq_seq.values = [device_entry_seq]
            try:
                self.bigip.cluster.mgmt_dg.remove_device(
                                        [name],
                                        device_entry_seq_seq)
            except WebFault as wf:
                if not "was not found" in str(wf.message):
                    raise

    def remove_all_peers(self):
        self.bigip.system.set_folder('/Common')
        current_dev_name = self.get_device_name()
        devs_to_remove = []
        for dev in self.get_all_device_names():
            if dev != current_dev_name:
                devs_to_remove.append(dev)
        if devs_to_remove:
            self.mgmt_trust.remove_device(devs_to_remove)
        self.remove_metadata({
                              'root_device_name': None,
                              'root_device_mgmt_address': None})

    def reset_trust(self, new_name):
        self.bigip.system.set_folder('/Common')
        self.remove_all_peers()
        self.mgmt_trust.reset_all(new_name, False, '', '')
        self.remove_metadata({
                              'root_device_name': None,
                              'root_device_mgmt_address': None})
        self.bigip.devicename = None
        self.get_device_name()

    def set_metadata(self, device_dict):
        self.bigip.system.set_folder('/Common')
        local_device = self.mgmt_dev.get_local_device()
        if isinstance(device_dict, dict):
            str_comment = json.dumps(device_dict)
            self.mgmt_dev.set_description([local_device],
                                      [str_comment])
        else:
            self.mgmt_dev.set_description([local_device],
                                      [device_dict])

    def get_metadata(self, device=None):
        self.bigip.system.set_folder('/Common')
        if not device:
            device = self.mgmt_dev.get_local_device()
        str_comment = self.mgmt_dev.get_description(
                    [device])[0]
        try:
            return json.loads(str_comment)
        except:
            return {}

    def remove_metadata(self, remove_dict, device=None):
        self.bigip.system.set_folder('/Common')
        if not device:
            device = self.mgmt_dev.get_local_device()
        if isinstance(remove_dict, dict):
            str_comment = self.mgmt_dev.get_description(
                                    [device])[0]
            try:
                existing_dict = json.loads(str_comment)
                for key in remove_dict:
                    if key in existing_dict:
                        del(existing_dict[key])
                str_comment = json.dumps(existing_dict)
                self.mgmt_dev.set_description([device],
                                      [str_comment])
            except:
                self.mgmt_dev.set_description([device], [''])
        else:
            self.mgmt_dev.set_description([device], [''])

    def update_metadata(self, device_dict, device=None):
        self.bigip.system.set_folder('/Common')
        if not device:
            device = self.mgmt_dev.get_local_device()
        if isinstance(device_dict, dict):
            str_comment = self.mgmt_dev.get_description(
                                    [device])[0]
            try:
                existing_dict = json.loads(str_comment)
            except:
                existing_dict = {}
            for key in device_dict:
                if not device_dict[key]:
                    if key in existing_dict:
                        del(existing_dict[key])
                else:
                    existing_dict[key] = device_dict[key]
            str_comment = json.dumps(existing_dict)
            self.mgmt_dev.set_description([device],
                                      [str_comment])

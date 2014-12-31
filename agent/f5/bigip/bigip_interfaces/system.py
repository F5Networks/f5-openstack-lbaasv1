# Copyright 2014 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from f5.common.logger import Log
from f5.common import constants as const
from f5.bigip import exceptions
from f5.bigip.bigip_interfaces import log

from suds import WebFault

import json
import time
import uuid


class System(object):
    def __init__(self, bigip):
        self.bigip = bigip

        self.bigip.icontrol.add_interfaces(['Management.Folder',
                                            'System.Session',
                                            'System.SystemInfo',
                                            'System.VCMP']
                                           )

        # iControl helper objects
        self.mgmt_folder = self.bigip.icontrol.Management.Folder
        self.sys_session = self.bigip.icontrol.System.Session
        self.sys_info = self.bigip.icontrol.System.SystemInfo
        self.sys_vcmp = self.bigip.icontrol.System.VCMP

        # create stubs to hold static system params to avoid redundant calls
        self.version = None
        self.current_folder = None
        self.systeminfo = None
        self.exempt_folders = ['/', 'Common']
        self.existing_folders = {}
        self.existint_folders_updated = None

    @log
    def folder_exists(self, folder):
        if folder:
            folder = str(folder).replace('/', '')
            if folder == 'Common':
                return True
            if folder in self.existing_folders:
                now = time.time()
                if self.existint_folders_updated:
                    if ((now - self.existint_folders_updated)
                            < const.FOLDER_CACHE_TIMEOUT):
                        return True
                    else:
                        del self.existing_folders[folder]
            request_url = self.bigip.icr_url + '/sys/folder/'
            request_url += '~' + folder
            request_url += '?$select=name'
            response = self.bigip.icr_session.get(
                request_url, timeout=const.CONNECTION_TIMEOUT)
            if response.status_code < 400:
                self.existing_folders[folder] = 1
                return True
            elif response.status_code == 404:
                return False
            else:
                Log.error('folder', response.text)
                raise exceptions.SystemQueryException(response.text)
        return False

    @log
    def create_folder(self, folder, change_to=False):
        if folder:
            folder = str(folder).replace('/', '')
            request_url = self.bigip.icr_url + '/sys/folder/'
            payload = dict()
            payload['name'] = folder
            payload['subPath'] = '/'
            payload['fullPath'] = '/' + folder
            payload['hidden'] = False
            payload['inheritedDevicegroup'] = True
            payload['inheritedTrafficGroup'] = True

            response = self.bigip.icr_session.post(
                request_url, data=json.dumps(payload),
                timeout=const.CONNECTION_TIMEOUT)
            if response.status_code < 400:
                if change_to:
                    self.existing_folders[folder] = 1
                    self.set_folder(folder)
                else:
                    self.set_folder('/Common')
                return True
            else:
                Log.error('folder', response.text)
                raise exceptions.SystemCreationException(response.text)
        return False

    # Force iControl SOAP context into root folder.
    # This is typically done before deleting a folder.
    # We need to ensure the internal context of the iControl
    # SOAP portal is not associated with a folder before
    # the folder is deleted or the SOAP portal will become
    # inoperative.
    # We need to do a fake query and fake command
    # because setting your active folder, by itself, does
    # not do anything.
    def force_root_folder(self):
        self.sys_session.set_active_folder('/')
        self.current_folder = '/'
        self.mgmt_folder.get_list()
        fakename = '/set-folder-workaround-'+str(uuid.uuid4())[0:8]
        try:
            self.mgmt_folder.delete_folder([fakename])
        except WebFault as e:
            pass

    @log
    def delete_folder(self, folder):
        if folder:
            folder = str(folder).replace('/', '')
            request_url = self.bigip.icr_url + '/sys/folder/~' + folder
            response = self.bigip.icr_session.delete(
                request_url, timeout=const.CONNECTION_TIMEOUT)
            if response.status_code < 400:
                if folder in self.existing_folders:
                    del self.existing_folders[folder]
                self.set_folder('/Common')
                return True
            elif response.status_code == 404:
                return True
            else:
                Log.error('folder', response.text)
                raise exceptions.SystemDeleteException(response.text)
        return False

    @log
    def get_folders(self):
        request_url = self.bigip.icr_url + '/sys/folder/'
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(
            request_url, timeout=const.CONNECTION_TIMEOUT)
        return_list = []
        if response.status_code < 400:
            return_obj = json.loads(response.text)
            if 'items' in return_obj:
                for folder in return_obj['items']:
                    return_list.append(folder['name'])
        elif response.status_code != 404:
            Log.error('folder', response.text)
            raise exceptions.SystemQueryException(response.text)
        return return_list

    @log
    def set_folder(self, folder):
        if not folder:
            msg = 'set_folder failed: No folder specified!'
            Log.error('System', msg)
            raise exceptions.SystemUpdateException(msg)

        if not self.folder_exists(folder):
            msg = 'set_folder:set_active_folder failed, ' + \
                  'folder does not exist!'
            Log.error('System', msg)
            raise exceptions.SystemUpdateException(msg)

        if not str(folder).startswith('/'):
            folder = '/' + folder
        if self.current_folder and folder == self.current_folder:
            return
        try:
            self.sys_session.set_active_folder(folder)
            self.current_folder = folder
        except WebFault as wf:
            Log.error('System',
                      'set_folder:set_active_folder failed: ' +
                      str(wf.message))
            raise exceptions.SystemUpdateException(wf.message)

    @log
    def purge_folder_contents(self, folder, bigip=None):
        if not bigip:
            bigip = self.bigip
        if not folder in self.exempt_folders:
            bigip.virtual_server.delete_all(folder=folder)
            bigip.pool.delete_all(folder=folder)
            bigip.monitor.delete_all(folder=folder)
            bigip.snat.delete_all(folder=folder)
            bigip.virtual_server.delete_all_presistence_profiles(folder=folder)
            bigip.virtual_server.delete_all_http_profiles(folder=folder)
            bigip.rule.delete_all(folder=folder)
            bigip.arp.delete_all(folder=folder)
            bigip.selfip.delete_all(folder=folder)
            bigip.vlan.delete_all(folder=folder)
            bigip.l2gre.delete_all(folder=folder)
            bigip.route.delete_domain(folder=folder)
        else:
            Log.error('folder',
                      'Request to purge exempt folder %s ignored.' % folder)

    @log
    def purge_folder(self, folder, bigip=None):
        if not bigip:
            bigip = self.bigip
        if not folder in self.exempt_folders:
            bigip.system.delete_folder(bigip.decorate_folder(folder))
        else:
            Log.error('folder',
                      'Request to purge exempt folder %s ignored.' % folder)

    @log
    def purge_orphaned_folders_contents(self, known_folders, bigip=None):
        if not bigip:
            bigip = self.bigip
        existing_folders = bigip.system.get_folders()
        # remove all folders which are default
        existing_folders.remove('/')
        existing_folders.remove('Common')
        # remove all folders which are not managed
        # with this object prefix
        for folder in existing_folders:
            if not folder.startswith(self.OBJ_PREFIX):
                existing_folders.remove(folder)
        for folder in known_folders:
            decorated_folder = bigip.decorate_folder(folder)
            if decorated_folder in existing_folders:
                existing_folders.remove(decorated_folder)
        # anything left should be purged
        if existing_folders:
            Log.debug('system',
                      'purging orphaned folders contents: %s'
                      % existing_folders)
        for folder in existing_folders:
            try:
                bigip.system.purge_folder_contents(folder, bigip)
            except Exception as e:
                Log.error('purge_orphaned_folders_contents', e.message)

    @log
    def purge_orphaned_folders(self, known_folders, bigip=None):
        if not bigip:
            bigip = self.bigip
        existing_folders = bigip.system.get_folders()
        # remove all folders which are default
        existing_folders.remove('/')
        existing_folders.remove('Common')
        # remove all folders which are not managed
        # with this object prefix
        for folder in existing_folders:
            if not folder.startswith(self.OBJ_PREFIX):
                existing_folders.remove(folder)
        for folder in known_folders:
            decorated_folder = bigip.decorate_folder(folder)
            if decorated_folder in existing_folders:
                existing_folders.remove(decorated_folder)
        # anything left should be purged
        if existing_folders:
            Log.debug('system', 'purging orphaned folders: %s'
                      % existing_folders)
        for folder in existing_folders:
            try:
                bigip.system.purge_folder(folder, bigip)
            except Exception as e:
                Log.error('purge_orphaned_folders', e.message)

    @log
    def purge_all_folders(self, bigip=None):
        if not bigip:
            bigip = self.bigip
        existing_folders = bigip.system.get_folders()
        for folder in existing_folders:
            if folder.startswith(bigip.system.OBJ_PREFIX):
                bigip.system.purge_folder(folder)

    @log
    def get_hostname(self):
        request_url = self.bigip.icr_url + \
            '/sys/global-settings?$select=hostname'
        response = self.bigip.icr_session.get(
            request_url, timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            return response_obj['hostname']
        else:
            raise exceptions.SystemQueryException(response.text)

    @log
    def set_hostname(self, hostname):
        request_url = self.bigip.icr_url + '/sys/global-settings'
        response = self.bigip.icr_session.put(
            request_url, data=json.dumps({'hostname': hostname}),
            timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            return True
        else:
            raise exceptions.SystemUpdateException(response.text)

    @log
    def get_ntp_server(self):
        request_url = self.bigip.icr_url + \
            '/sys/ntp?$select=servers'
        response = self.bigip.icr_session.get(
            request_url, timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'servers' in response_obj:
                return response_obj['servers'][0]
            else:
                return None
        else:
            raise exceptions.SystemQueryException(response.text)

    @log
    def set_ntp_server(self, addr):
        request_url = self.bigip.icr_url + '/sys/ntp'
        if not isinstance(addr, list):
            addr = [addr]
        response = self.bigip.icr_session.put(
            request_url, data=json.dumps({'servers': addr}),
            timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            return True
        else:
            raise exceptions.SystemUpdateException(response.text)

    @log
    def get_active_modules(self):
        request_url = self.bigip.icr_url + '/cm/device'
        request_url += '?$select=activeModules,selfDevice'
        response = self.bigip.icr_session.get(
            request_url, timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'items' in response_obj:
                for device in response_obj['items']:
                    if device['selfDevice']:
                        return device['activeModules']
        else:
            raise exceptions.SystemQueryException(response.text)

    @log
    def get_platform(self):
        if not self.systeminfo:
            try:
                self.systeminfo = self.sys_info.get_system_information()
            except Exception as e:
                raise exceptions.SystemQueryException(e.message)
        return self.systeminfo.product_category

    @log
    def get_serial_number(self):
        if not self.systeminfo:
            try:
                self.systeminfo = self.sys_info.get_system_information()
            except Exception as e:
                raise exceptions.SystemQueryException(e.message)
        return self.systeminfo.chassis_serial

    @log
    def get_version(self):
        if not self.version:
            try:
                self.version = self.sys_info.get_version()
            except Exception as e:
                raise exceptions.SystemQueryException(e.message)
        return self.version

    @log
    def get_major_version(self):
        return self.get_version().split('_v')[1].split('.')[0]

    @log
    def get_minor_version(self):
        return self.get_version().split('_v')[1].split('.')[1]

    @log
    def get_provision_extramb(self):
        request_url = self.bigip.icr_url + '/sys/db/provision.extramb'
        response = self.bigip.icr_session.get(
            request_url, timeout=const.CONNECTION_TIMEOUT)

        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'value' in response_obj:
                return response_obj['value']
            return 0
        else:
            raise exceptions.SystemQueryException(response.text)

    @log
    def set_provision_extramb(self, extramdb=500):
        request_url = self.bigip.icr_url + '/sys/db/provision.extramb'
        response = self.bigip.icr_session.put(
            request_url, data=json.dumps({'value': extramdb}),
            timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            return True
        else:
            raise exceptions.SystemUpdateException(response.text)

    @log
    def get_tunnel_sync(self):
        request_url = self.bigip.icr_url + '/sys/db/iptunnel.configsync'
        response = self.bigip.icr_session.get(
            request_url, timeout=const.CONNECTION_TIMEOUT)

        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'value' in response_obj:
                return response_obj['value']
            return None
        elif response.status_code != 404:
            raise exceptions.SystemQueryException(response.text)

    @log
    def set_tunnel_sync(self, enabled=False):
        request_url = self.bigip.icr_url + '/sys/db/iptunnel.configsync'
        if enabled:
            response = self.bigip.icr_session.put(
                request_url, data=json.dumps({'value': 'enable'}),
                timeout=const.CONNECTION_TIMEOUT)
        else:
            response = self.bigip.icr_session.put(
                request_url, data=json.dumps({'value': 'disable'}),
                timeout=const.CONNECTION_TIMEOUT)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'value' in response_obj:
                return response_obj['value']
            return None
        elif response.status_code != 404:
            raise exceptions.SystemUpdateException(response.text)

##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common.logger import Log
from suds import WebFault
from httplib import BadStatusLine

import requests
import json


class System(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['System.Session',
                                            'System.Inet',
                                            'System.SystemInfo',
                                            'Management.Folder',
                                            'Management.LicenseAdministration']
                                           )

        # iControl helper objects
        self.sys_session = self.bigip.icontrol.System.Session
        self.sys_inet = self.bigip.icontrol.System.Inet
        self.sys_info = self.bigip.icontrol.System.SystemInfo
        self.mgmt_folder = self.bigip.icontrol.Management.Folder
        self.mgmt_license = \
            self.bigip.icontrol.Management.LicenseAdministration

        # create stubs to hold static system params to avoid redundant calls
        self.version = None
        self.current_folder = None
        self.systeminfo = None

    def folder_exists(self, folder):
        try:
            if not str(folder).startswith('/'):
                folder = '/' + folder
            self.sys_session.set_active_folder(folder)
            self.current_folder = folder
        except WebFault as wf:
            if "was not found" in str(wf.message):
                return False
            else:
                raise
        else:
            if self.current_folder:
                self.sys_session.set_active_folder(self.current_folder)
            return True

    def create_folder(self, folder, change_to=False):
        self.set_folder('/')
        if not folder.startswith('/'):
            folder = '/' + folder
        try:
            self.mgmt_folder.create([folder])
        except BadStatusLine:
            Log.error('System',
                      "Irregular iControl response creating folder %s"
                      % folder)
        if change_to:
            self.sys_session.set_active_folder(folder)
            self.current_folder = folder
        else:
            self.set_folder('/Common')
            self.current_folder = '/Common'

    def delete_folder(self, folder):
        self.set_folder('/')
        self.mgmt_folder.delete_folder([folder])
        self.set_folder('/Common')

    def get_folders(self):
        self.set_folder('/')
        folders = self.mgmt_folder.get_list()
        self.set_folder('/Common')
        return folders

    def set_folder(self, folder):
        if not str(folder).startswith('/'):
            folder = '/' + folder
        if self.current_folder and folder == self.current_folder:
            return
        try:
            self.sys_session.set_active_folder(folder)
            self.current_folder = folder
        except WebFault as wf:
            if "was not found" in str(wf.message):
                if folder == '/' or 'Common' in folder:
                    # don't try to recover from this
                    raise
                try:
                    self._create_folder_and_domain(folder, self.bigip)
                except WebFault as wf:
                    Log.error('System',
                              'set_folder:create failed: ' + str(wf.message))
                    raise
            else:
                Log.error('System',
                          'set_folder:set_active_folder failed: ' + \
                          str(wf.message))
                raise

    # TODO: this belongs in a higher level cluster abstraction
    def _create_folder_and_domain(self, folder, bigip):
        if bigip.sync_mode == 'replication':
            # presumably whatever is operating on the current bigip
            # will do the same on every bigip, so no need to replicate
            bigip.system.create_folder(folder, change_to=True)
            if bigip.route_domain_required:
                bigip.route._create_domain(folder=folder)
        else:
            self.create_folder(folder, change_to=True)
            if len(bigip.group_bigips) > 1:
                # folder must sync before route domains are created.
                dg = bigip.device.get_device_group()
                bigip.cluster.sync(dg)
                # get_device_group and sync will change the current
                # folder.
                self.sys_session.set_active_folder(folder)
                self.current_folder = folder
            if bigip.route_domain_required:
                if len(bigip.group_bigips) > 1:
                    for b in bigip.group_bigips:
                        b.route._create_domain(folder=folder)
                else:
                    bigip.route._create_domain(folder=folder)

    def get_hostname(self):
        return self.sys_inet.get_hostname()

    def set_hostname(self, hostname):
        self.sys_inet.set_hostname(hostname)

    def get_ntp_server(self):
        return self.sys_inet.get_ntp_server_address()[0]

    def set_ntp_server(self, addr):
        self.sys_inet.set_ntp_server_address([addr])

    def get_platform(self):
        if not self.systeminfo:
            self.systeminfo = self.sys_info.get_system_information()
        return self.systeminfo.product_category

    def get_serial_number(self):
        if not self.systeminfo:
            self.systeminfo = self.sys_info.get_system_information()
        return self.systeminfo.chassis_serial

    def get_version(self):
        if not self.version:
            self.version = self.sys_info.get_version()

        return self.version

    def get_major_version(self):
        return self.get_version().split('_v')[1].split('.')[0]

    def get_minor_version(self):
        return self.get_version().split('_v')[1].split('.')[1]

    def get_provision_extramb(self):
        request_url = self.bigip.icr_url + '/sys/db/provision.extramb'
        response = self.bigip.icr_session.get(request_url)

        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'value' in response_obj:
                return response_obj['value']
            return 0
        else:
            return 0

    def set_provision_extramb(self, extramdb=500):
        request_url = self.bigip.icr_url + '/sys/db/provision.extramb'
        response = self.bigip.icr_session.put(request_url,
                                        data=json.dumps({'value': extramdb}))
        if response.status_code < 400:
            return True
        else:
            return False

    def get_tunnel_sync(self):
        request_url = self.bigip.icr_url + '/sys/db/iptunnel.configsync'
        response = self.bigip.icr_session.get(request_url)

        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'value' in response_obj:
                return response_obj['value']
            return None
        else:
            return None

    def set_tunnel_sync(self, enabled=False):
        request_url = self.bigip.icr_url + '/sys/db/iptunnel.configsync'
        if enabled:
            response = self.bigip.icr_session.put(request_url,
                                        data=json.dumps({'value': 'enable'}))
        else:
            response = self.bigip.icr_session.put(request_url,
                                        data=json.dumps({'value': 'disable'}))
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if 'value' in response_obj:
                return response_obj['value']
            return None
        else:
            return None

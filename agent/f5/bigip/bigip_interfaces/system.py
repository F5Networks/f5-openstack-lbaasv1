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

import logging

LOG = logging.getLogger(__name__)


class System(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['System.Session',
                                            'System.Inet',
                                            'System.SystemInfo',
                                            'Management.Folder'])

        # iControl helper objects
        self.sys_session = self.bigip.icontrol.System.Session
        self.sys_inet = self.bigip.icontrol.System.Inet
        self.sys_info = self.bigip.icontrol.System.SystemInfo
        self.mgmt_folder = self.bigip.icontrol.Management.Folder

        # create stubs to hold static system params to avoid redundant calls
        self.version = None
        self.platform = None

    def create_folder(self, folder, change_to=False):
        self.set_folder('/')
        if not folder.startswith('/'):
            folder = '/' + folder
        self.mgmt_folder.create([folder])
        if change_to:
            self.sys_session.set_active_folder(folder)
        else:
            self.set_folder('/Common')

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
        try:
            self.sys_session.set_active_folder(folder)
        except WebFault as wf:
            if "was not found" in str(wf.message):
                try:
                    self.create_folder(folder, change_to=True)
                except WebFault as wf:
                    LOG.error("System.set_folder:create_folder failed: " + str(wf.message))
                if self.bigip.route_domain_required:
                    try:
                        self.bigip.route.create_domain(folder=folder)
                    except WebFault as wf:
                        LOG.error("System.set_folder:create_domain failed: " + str(wf.message))


    def get_hostname(self):
        return self.sys_inet.get_hostname()

    def set_hostname(self, hostname):
        self.sys_inet.set_hostname(hostname)

    def get_ntp_server(self):
        return self.sys_inet.get_ntp_server_address()[0]

    def set_ntp_server(self, addr):
        self.sys_inet.set_ntp_server_address([addr])

    def get_platform(self):
        if not self.platform:
            self.platform = self.sys_info.get_system_information().platform

        return self.platform

    def get_version(self):
        if not self.version:
            self.version = self.sys_info.get_version()

        return self.version

    def get_major_version(self):
        return self.get_version().split('_v')[1].split('.')[0]

    def get_minor_version(self):
        return self.get_version().split('_v')[1].split('.')[1]

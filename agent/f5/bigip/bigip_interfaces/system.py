# System


class System(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['System.Session',
                                            'System.Inet',
                                            'System.SystemInfo'])

        # iControl helper objects
        self.sys_session = self.bigip.icontrol.System.Session
        self.sys_inet = self.bigip.icontrol.System.Inet
        self.sys_info = self.bigip.icontrol.System.SystemInfo

        # create stubs to hold static system params to avoid redundant calls
        self.version = None
        self.platform = None

    def set_folder(self, folder):
        self.sys_session.set_active_folder(folder)

    def get_hostname(self):
        return self.sys_inet.get_hostname()

    def set_hostname(self, hostname):
        self.sys_inet.set_hostname(hostname)

    def get_ntp_server(self):
        return self.sys_inet.get_ntp_server_address()[0]

    def set_ntp_server(self, addr):
        self.sys_inet.set_ntp_server_address([addr])

    def set_active_folder(self, folder):
        self.sys_session.set_active_folder(folder)

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

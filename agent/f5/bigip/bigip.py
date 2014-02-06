import os
import logging

from f5.bigip.pycontrol import pycontrol as pc
from f5.common import constants as const

from f5.bigip.bigip_interfaces.cluster import Cluster
from f5.bigip.bigip_interfaces.device import Device
from f5.bigip.bigip_interfaces.monitor import Monitor
from f5.bigip.bigip_interfaces.pool import Pool
from f5.bigip.bigip_interfaces.route import Route
from f5.bigip.bigip_interfaces.selfip import SelfIP
from f5.bigip.bigip_interfaces.stat import Stat
from f5.bigip.bigip_interfaces.system import System
from f5.bigip.bigip_interfaces.virtual_server import VirtualServer
from f5.bigip.bigip_interfaces.vlan import Vlan

LOG = logging.getLogger(__name__)


class BigIP(object):
    def __init__(self, hostname, username, password, timeout=None):
        # get icontrol connection stub
        self.icontrol = self._get_icontrol(hostname, username, password)

        # interface instance cache
        self.interfaces = {}

    @property
    def system(self):
        if 'system' in self.interfaces:
            return self.interfaces['system']
        else:
            system = System(self)
            self.interfaces['system'] = system
            return system

    @property
    def device(self):
        if 'device' in self.interfaces:
            return self.interfaces['device']
        else:
            device = Device(self)
            self.interfaces['device'] = device
            return device

    @property
    def cluster(self):
        if 'cluster' in self.interfaces:
            return self.interfaces['cluster']
        else:
            cluster = Cluster(self)
            self.interfaces['cluster'] = cluster
            return cluster

    @property
    def stat(self):
        if 'stat' in self.interfaces:
            return self.interfaces['stat']
        else:
            stat = Stat(self)
            self.interfaces['stat'] = stat
            return stat

    @property
    def vlan(self):
        if 'vlan' in self.interfaces:
            return self.interfaces['vlan']
        else:
            vlan = Vlan(self)
            self.interfaces['vlan'] = vlan
            return vlan

    @property
    def selfip(self):
        if 'selfip' in self.interfaces:
            return self.interfaces['selfip']
        else:
            selfip = SelfIP(self)
            self.interfaces['selfip'] = selfip
            return selfip

    @property
    def route(self):
        if 'route' in self.interfaces:
            return self.interfaces['route']
        else:
            route = Route(self)
            self.interfaces['route'] = route
            return route

    @property
    def virtual_server(self):
        if 'virtual_server' in self.interfaces:
            return self.interfaces['virtual_server']
        else:
            virtual_server = VirtualServer(self)
            self.interfaces['virtual_server'] = virtual_server
            return virtual_server

    @property
    def monitor(self):
        if 'monitor' in self.interfaces:
            return self.interfaces['monitor']
        else:
            monitor = Monitor(self)
            self.interfaces['monitor'] = monitor
            return monitor

    @property
    def pool(self):
        if 'pool' in self.interfaces:
            return self.interfaces['pool']
        else:
            pool = Pool(self)
            self.interfaces['pool'] = pool
            return pool

    def set_timeout(self, timeout):
        self.icontrol.set_timeout(timeout)

    def set_folder(self, name, folder='/Common'):
        if not folder.startswith("/"):
            folder += "/"
        if not hasattr(self, 'folder'):
            self.system.set_active_folder(folder)
            self.folder = folder
        else:
            if not self.folder == folder:
                self.system.set_active_folder(folder)
                self.folder = folder
        if name:
            if not name.startswith(folder + "/"):
                return "/" + folder + "/" + name
            else:
                return name
        else:
            return None

    def get_route_domain_index_for_folder(self, folder='/Common'):
        if folder == '/Common':
            return 0
        else:
            #TO DO: add the call to get route domain for a folder
            return 1

    @staticmethod
    def _get_icontrol(hostname, username, password, timeout=None):
        #Logger.log(Logger.DEBUG,
        #           "Opening iControl connections to %s for interfaces %s"
        #            % (self.hostname, self.interfaces))

        if os.path.exists(const.WSDL_CACHE_DIR):
            icontrol = pc.BIGIP(hostname=hostname,
                                username=username,
                                password=password,
                                directory=const.WSDL_CACHE_DIR,
                                wsdls=[])
        else:
            icontrol = pc.BIGIP(hostname=hostname,
                                username=username,
                                password=password,
                                fromurl=True,
                                wsdls=[])

        if timeout:
            icontrol.set_timeout(timeout)
        else:
            icontrol.set_timeout(const.CONNECTION_TIMEOUT)

        return icontrol

    @staticmethod
    def ulong_to_int(ulong_64):
        high = ulong_64.high
        low = ulong_64.low

        if high < 0:
            high += (1 << 32)
        if low < 0:
            low += (1 << 32)

        return long((high << 32) | low)

    @staticmethod
    def add_folder(folder, name):
        folder = str(folder).replace("/", "")
        if not str(name).startswith("/" + folder + "/"):
            return "/" + folder + "/" + name
        else:
            return name


def icontrol_folder(method):
    """Decorator to put the right folder on iControl object."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        if ('name' in kwargs) and ('folder' in kwargs):
            kwargs['name'] = instance.bigip.set_folder(kwargs['name'],
                                                       kwargs['folder'])
        return method(*args, **kwargs)
    return wrapper


def route_domain_address_decorate(method):
    """Decorator to put the right route domain decoration an address."""
    def wrapper(*args, **kwargs):
        instance = args[0]
        if 'folder' in kwargs:
            folder = kwargs['folder']
            for name in kwargs:
                if str(name).find('ip_address') > 0:
                    rid = instance.bigip.get_route_domain_index_for_folder(
                                                                        folder)
                if rid > 0:
                    kwargs[name] += "%" + rid
        return method(*args, **kwargs)
    return wrapper

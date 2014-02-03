import os
import netaddr.ip as ip
import time

from f5.pycontrol import pycontrol as pc
from common import constants as const
from common.logger import Log

from f5.bigip_interfaces.cluster import Cluster
from f5.bigip_interfaces.device import Device
from f5.bigip_interfaces.monitor import Monitor
from f5.bigip_interfaces.pool import Pool
from f5.bigip_interfaces.route import Route
from f5.bigip_interfaces.selfip import SelfIP
from f5.bigip_interfaces.stat import Stat
from f5.bigip_interfaces.system import System
from f5.bigip_interfaces.virtual_server import VirtualServer
from f5.bigip_interfaces.vlan import Vlan


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
            icontrol.set_timeout(const.IFC_SCRIPT_TIMEOUT)

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
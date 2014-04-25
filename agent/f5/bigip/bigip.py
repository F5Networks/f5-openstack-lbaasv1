##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

import os
import logging
import requests

from f5.bigip.pycontrol import pycontrol as pc
from f5.common import constants as const
from f5.bigip import bigip_interfaces

from f5.bigip.bigip_interfaces.cluster import Cluster
from f5.bigip.bigip_interfaces.device import Device
from f5.bigip.bigip_interfaces.monitor import Monitor
from f5.bigip.bigip_interfaces.pool import Pool
from f5.bigip.bigip_interfaces.route import Route
from f5.bigip.bigip_interfaces.rule import Rule
from f5.bigip.bigip_interfaces.selfip import SelfIP
from f5.bigip.bigip_interfaces.snat import SNAT
from f5.bigip.bigip_interfaces.nat import NAT
from f5.bigip.bigip_interfaces.stat import Stat
from f5.bigip.bigip_interfaces.system import System
from f5.bigip.bigip_interfaces.virtual_server import VirtualServer
from f5.bigip.bigip_interfaces.vlan import Vlan
from f5.bigip.bigip_interfaces.vxlan import VXLAN
from f5.bigip.bigip_interfaces.l2gre import L2GRE
from f5.bigip.bigip_interfaces.arp import ARP

LOG = logging.getLogger(__name__)


class BigIP(object):
    def __init__(self, hostname, username, password,
                 timeout=None, address_isolation=True,
                 strict_route_isolation=False):
        # get icontrol connection stub
        self.icontrol = self._get_icontrol(hostname, username, password)

        self.icr_session = requests.session()
        self.icr_session.auth = (username, password)
        self.icr_session.verify = False
        self.icr_session.headers.update(
                                 {'Content-Type': 'application/json'})
        self.icr_url = 'https://%s/mgmt/tm' % hostname

        if address_isolation:
            self.route_domain_required = True
        else:
            self.route_domain_required = False
        if strict_route_isolation:
            self.strict_route_isolation = True
        else:
            self.strict_route_isolation = False
        # interface instance cache
        self.interfaces = {}
        self.group_bigips = []
        self.sync_mode = const.DEFAULT_SYNC_MODE

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
    def vxlan(self):
        if 'vxlan' in self.interfaces:
            return self.interfaces['vxlan']
        else:
            vxlan = VXLAN(self)
            self.interfaces['vxlan'] = vxlan
            return vxlan

    @property
    def l2gre(self):
        if 'l2gre' in self.interfaces:
            return self.interfaces['l2gre']
        else:
            l2gre = L2GRE(self)
            self.interfaces['l2gre'] = l2gre
            return l2gre

    @property
    def arp(self):
        if 'arp' in self.interfaces:
            return self.interfaces['arp']
        else:
            arp = ARP(self)
            self.interfaces['arp'] = arp
            return arp

    @property
    def selfip(self):
        if 'selfip' in self.interfaces:
            return self.interfaces['selfip']
        else:
            selfip = SelfIP(self)
            self.interfaces['selfip'] = selfip
            return selfip

    @property
    def snat(self):
        if 'snat' in self.interfaces:
            return self.interfaces['snat']
        else:
            snat = SNAT(self)
            self.interfaces['snat'] = snat
            return snat

    @property
    def nat(self):
        if 'nat' in self.interfaces:
            return self.interfaces['nat']
        else:
            nat = NAT(self)
            self.interfaces['nat'] = nat
            return nat

    @property
    def route(self):
        if 'route' in self.interfaces:
            return self.interfaces['route']
        else:
            route = Route(self)
            self.interfaces['route'] = route
            return route

    @property
    def rule(self):
        if 'rule' in self.interfaces:
            return self.interfaces['rule']
        else:
            rule = Rule(self)
            self.interfaces['rule'] = rule
            return rule

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
            folder = "/" + folder
        #if not hasattr(self, 'folder'):
        #    self.system.set_folder(folder)
        #    self.folder = folder
        #else:
        #    if not self.folder == folder:
        #        self.system.set_folder(folder)
        #        self.folder = folder
        self.system.set_folder(folder)
        if name:
            if not name.startswith(folder + "/"):
                return folder + "/" + name
            else:
                return name
        else:
            return None

    def set_rest_folder(self, name, folder='/Common'):
        folder = folder.replace('/', '')
        folder = '~' + folder
        if name:
            if not name.startswith(folder + "/"):
                return folder + '~' + name
            else:
                name = name.replace('/', '~')
                return name
        else:
            return None

    def decorate_folder(self, folder='Common'):
        folder = str(folder).replace('/', '')
        return bigip_interfaces.prefixed(folder)

    def get_domain_index(self, folder='/Common'):
        if folder == '/Common' or folder == 'Common':
            return 0
        else:
            return self.route.get_domain(folder=folder)

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
    def int_to_ulong(integer):
        ulong = type('ULong', (object,), {})
        ulong.low = 0
        ulong.high = 0
        if integer < 0:
            integer = -1 * integer
            binval = bin(integer)[2:]
            bitlen = len(binval)
            if bitlen > 32:
                ulong.low = int((binval[(bitlen - 32):]), 2)
                ulong.high = int((binval[:(bitlen - 32)]), 2)
            else:
                ulong.low = int(binval, 2)
                ulong.high = 0
            ulong.low = -1 * ulong.low
            ulong.high = -1 * ulong.high
            return ulong
        else:
            binval = bin(integer)[2:]
            bitlen = len(binval)
            if bitlen > 32:
                ulong.low = int((binval[(bitlen - 32):]), 2)
                ulong.high = int((binval[:(bitlen - 32)]), 2)
            else:
                ulong.low = int(binval, 2)
                ulong.high = 0
            return ulong

    @staticmethod
    def add_folder(folder, name):
        folder = str(folder).replace("/", "")
        if not str(name).startswith("/" + folder + "/"):
            return "/" + folder + "/" + name
        else:
            return name

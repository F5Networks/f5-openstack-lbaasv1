import os

from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder

# Local Traffic - Virtual Server


class VirtualServer(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.VirtualServer')
        # iControl helper objects
        self.lb_vs = self.bigip.icontrol.LocalLB.VirtualServer

    @domain_address
    def create(self, name=None, ip_address=None, mask=None,
               port=None, protocol=None, vlan_name=None, folder='/Common'):
        if not self.exists(name=name, folder=folder):
            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                                        'Common.VirtualServerDefinition')
            vs_def.name = name
            vs_def.address = ip_address

            if port:
                vs_def.port = port
            else:
                vs_def.port = 0

            vs_def.protocol = self._get_protocol_type(protocol)
            vs_defs = [vs_def]

            # virtual server resources
            res = self.lb_vs.typefactory.create(
                            'LocalLB.VirtualServer.VirtualServerResource')
            vs_vs_type = self.lb_vs.typefactory.create(
                                'LocalLB.VirtualServer.VirtualServerType')
            res.type = vs_vs_type.RESOURCE_TYPE_POOL
            resources = [res]

            # virtual server profiles
            prof_seq = self.lb_vs.typefactory.create(
                      'LocalLB.VirtualServer.VirtualServerProfileSequence')
            profiles = [prof_seq]

            # virtual server creation
            self.lb_vs.create(vs_defs, [mask], resources, profiles)

            # TODO: remove SNAT automap for all VIPs when routing is finished
            self.lb_vs.set_snat_automap([name])

            # add enabled VLANs
            enabled_state = self.lb_vs.typefactory.create(
                                        'Common.EnabledState').STATE_ENABLED
            filter_list = self.lb_vs.typefactory.create(
                                           'Common.VLANFilterList')
            filter_list.state = enabled_state
            filter_list.vlans = [vlan_name]

            self.lb_vs.set_vlan([name], [filter_list])

    def delete(self, name=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.delete_virtual_server([name])

    def get_pool(self, name=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_vs.get_default_pool_name([name])[0]

    def set_pool(self, name=None, pool_name=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            if self.bigip.pool.exists(pool_name):
                self.lb_vs.set_default_pool_name([name], [pool_name])
            elif not pool_name:
                self.lb_vs.set_default_pool_name([name], [''])

    @domain_address
    def set_addr_port(self, name=None, ip_address=None,
                      port=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            # TODO: virtual server definition in device spec needs a port
            if not port:
                port = 0
            dest = self.lb_vs.typefactory.create('Common.AddressPort')
            dest.address = ip_address
            dest.port = port
            self.lb_vs.set_destination_v2([name], [dest])

    def get_addr(self, name=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return os.path.basename(addr_port.address)

    def get_port(self, name=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return int(addr_port.port)

    @domain_address
    def set_mask(self, name=None, netmask=None, folder='/Common'):
        if self.exists(name=name, folder='folder'):
            self.lb_vs.set_wildmask([name], [netmask])

    def get_mask(self, name=None, folder='/Common'):
        if self.exists(name=name, folder='folder'):
            return self.lb_vs.get_wildmask([name])[0]

    def set_protocol(self, name=None, protocol=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            protocol_type = self._get_protocol_type(protocol)
            self.lb_vs.set_protocol([name], [protocol_type])

    def get_protocol(self, name=None, folder='/Common'):
        if self.exists(name=name, folder=folder):
            protocol_type = self.lb_vs.get_protocol([name])[0]

            if protocol_type == 'PROTOCOL_ICMP':
                return 'ICMP'
            elif protocol_type == 'PROTOCOL_UDP':
                return 'UDP'
            else:
                return 'TCP'

    def _get_protocol_type(self, protocol_str):
        protocol_str = str.upper(protocol_str)
        protocol_type = self.lb_vs.typefactory.create('Common.ProtocolType')

        if protocol_str == 'ICMP':
            return protocol_type.PROTOCOL_ICMP
        elif protocol_str == 'UDP':
            return protocol_type.PROTOCOL_UDP
        else:
            return protocol_type.PROTOCOL_TCP

    @icontrol_folder
    def exists(self, name=None, folder='/Common'):
        if name in self.lb_vs.get_list():
            return True
        else:
            return False

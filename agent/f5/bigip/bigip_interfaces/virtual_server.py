from netaddr import IPAddress
import os

# Local Traffic - Virtual Server


class VirtualServer(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.VirtualServer')
        # iControl helper objects
        self.lb_vs = self.bigip.icontrol.LocalLB.VirtualServer

    def create(self, name, addr, mask, port, protocol, vlan_name):
        if IPAddress(addr) and not self.exists(name):
            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                                        'Common.VirtualServerDefinition')
            vs_def.name = name
            vs_def.address = addr

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

    def delete(self, name):
        if self.exists(name):
            self.lb_vs.delete_virtual_server([name])

    def get_pool(self, name):
        if self.exists(name):
            return self.lb_vs.get_default_pool_name([name])[0]

    def set_pool(self, name, pool_name):
        if self.exists(name):
            if self.bigip.pool.exists(pool_name):
                self.lb_vs.set_default_pool_name([name], [pool_name])
            elif not pool_name:
                self.lb_vs.set_default_pool_name([name], [''])

    def set_addr_port(self, name, addr, port):
        if self.exists(name):
            # TODO: virtual server definition in device spec needs a port
            if not port:
                port = 0
            dest = self.lb_vs.typefactory.create('Common.AddressPort')
            dest.address = addr
            dest.port = port
            self.lb_vs.set_destination_v2([name], [dest])

    def get_addr(self, name):
        if self.exists(name):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return os.path.basename(addr_port.address)

    def get_port(self, name):
        if self.exists(name):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return int(addr_port.port)

    def set_mask(self, name, mask):
        if self.exists(name):
            self.lb_vs.set_wildmask([name], [mask])

    def get_mask(self, name):
        if self.exists(name):
            return self.lb_vs.get_wildmask([name])[0]

    def set_protocol(self, name, protocol):
        if self.exists(name):
            protocol_type = self._get_protocol_type(protocol)
            self.lb_vs.set_protocol([name], [protocol_type])

    def get_protocol(self, name):
        if self.exists(name):
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

    def exists(self, name):
        if name in self.lb_vs.get_list():
            return True
        else:
            return False

import os

from f5.common import constants as const

from f5.bigip.bigip_interfaces import domain_address, icontrol_folder, \
    strip_folder_and_prefix

from neutron.common import log

# Local Traffic - Virtual Server


class VirtualServer(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(
                                           ['LocalLB.VirtualServer',
                                            'LocalLB.VirtualAddressV2']
                                           )
        # iControl helper objects
        self.lb_vs = self.bigip.icontrol.LocalLB.VirtualServer
        self.lb_va = self.bigip.icontrol.LocalLB.VirtualAddressV2

    @icontrol_folder
    @domain_address
    def create(self, name=None, ip_address=None, mask=None,
               port=None, protocol=None, vlan_name=None,
               traffic_group=None, folder='Common'):

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

            if self.bigip.vlan.exists(name=vlan_name, folder=folder):
                # add enabled VLANs
                enabled_state = self.lb_vs.typefactory.create(
                    'Common.EnabledState').STATE_ENABLED
                filter_list = self.lb_vs.typefactory.create(
                    'Common.VLANFilterList')
                filter_list.state = enabled_state
                filter_list.vlans = [vlan_name]

                self.lb_vs.set_vlan([name], [filter_list])

            if not traffic_group:
                traffic_group = \
                  const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.lb_va.set_traffic_group([ip_address], [traffic_group])

    @icontrol_folder
    def create_ip_forwarder(self, name=None, ip_address=None,
                            mask=None, vlan_name=None,
                            traffic_group=None, folder='Common'):
        if not self.exists(name=name, folder=folder):
            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                'Common.VirtualServerDefinition')
            vs_def.name = name
            vs_def.address = ip_address
            vs_def.port = 0
            protocol_type = self.lb_vs.typefactory.create(
                                                 'Common.ProtocolType')
            vs_def.protocol = protocol_type.PROTOCOL_ANY
            vs_defs = [vs_def]

            # virtual server resources
            res = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerResource')
            vs_vs_type = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerType')
            res.type = vs_vs_type.RESOURCE_TYPE_IP_FORWARDING
            resources = [res]

            # virtual server profiles
            prof_seq = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerProfileSequence')
            profiles = [prof_seq]

            # virtual server creation
            self.lb_vs.create(vs_defs, [mask], resources, profiles)

            if self.bigip.vlan.exists(name=vlan_name, folder=folder):
                # add enabled VLANs
                enabled_state = self.lb_vs.typefactory.create(
                    'Common.EnabledState').STATE_ENABLED
                filter_list = self.lb_vs.typefactory.create(
                    'Common.VLANFilterList')
                filter_list.state = enabled_state
                filter_list.vlans = [vlan_name]

                self.lb_vs.set_vlan([name], [filter_list])

            if not traffic_group:
                traffic_group = \
                  const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.lb_va.set_traffic_group([ip_address], [traffic_group])

    @icontrol_folder
    def create_fastl4(self, name=None, ip_address=None,
                            mask=None, vlan_name=None,
                            traffic_group=None, folder='Common'):
        if not self.exists(name=name, folder=folder):
            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                'Common.VirtualServerDefinition')
            vs_def.name = name
            vs_def.address = ip_address
            vs_def.port = 0
            protocol_type = self.lb_vs.typefactory.create(
                                                 'Common.ProtocolType')
            vs_def.protocol = protocol_type.PROTOCOL_ANY
            vs_defs = [vs_def]

            # virtual server resources
            res = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerResource')
            vs_vs_type = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerType')
            res.type = vs_vs_type.RESOURCE_TYPE_FAST_L4
            resources = [res]

            # virtual server profiles
            prof_seq = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerProfileSequence')
            profiles = [prof_seq]

            # virtual server creation
            self.lb_vs.create(vs_defs, [mask], resources, profiles)

            if self.bigip.vlan.exists(name=vlan_name, folder=folder):
                # add enabled VLANs
                enabled_state = self.lb_vs.typefactory.create(
                    'Common.EnabledState').STATE_ENABLED
                filter_list = self.lb_vs.typefactory.create(
                    'Common.VLANFilterList')
                filter_list.state = enabled_state
                filter_list.vlans = [vlan_name]

                self.lb_vs.set_vlan([name], [filter_list])

            if not traffic_group:
                traffic_group = \
                  const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.lb_va.set_traffic_group([ip_address], [traffic_group])

    @icontrol_folder
    def enable_virtual_server(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_enabled_state([name], ['STATE_ENABLED'])
            return True
        else:
            return False

    @icontrol_folder
    def disable_virtual_server(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_enabled_state([name], ['STATE_DISABLED'])
            return True
        else:
            return False

    @log.log
    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.delete_virtual_server([name])

    @icontrol_folder
    def get_pool(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            pool_name = self.lb_vs.get_default_pool_name([name])[0]
            return strip_folder_and_prefix(pool_name)

    @icontrol_folder
    def set_pool(self, name=None, pool_name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            if self.bigip.pool.exists(name=pool_name, folder=folder):
                self.lb_vs.set_default_pool_name([name], [pool_name])
            elif not pool_name:
                self.lb_vs.set_default_pool_name([name], [''])

    @icontrol_folder
    @domain_address
    def set_addr_port(self, name=None, ip_address=None,
                      port=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            # TODO: virtual server definition in device spec needs a port
            if not port:
                port = 0
            dest = self.lb_vs.typefactory.create('Common.AddressPort')
            dest.address = ip_address
            dest.port = port
            self.lb_vs.set_destination_v2([name], [dest])

    @icontrol_folder
    def get_addr(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return os.path.basename(addr_port.address).split('%')[0]

    @icontrol_folder
    def get_port(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return int(addr_port.port)

    @icontrol_folder
    @domain_address
    def set_mask(self, name=None, netmask=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_wildmask([name], [netmask])

    @icontrol_folder
    def get_mask(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_vs.get_wildmask([name])[0]

    @icontrol_folder
    def set_protocol(self, name=None, protocol=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            protocol_type = self._get_protocol_type(protocol)
            self.lb_vs.set_protocol([name], [protocol_type])

    @icontrol_folder
    def get_protocol(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            protocol_type = self.lb_vs.get_protocol([name])[0]

            if protocol_type == 'PROTOCOL_ICMP':
                return 'ICMP'
            elif protocol_type == 'PROTOCOL_UDP':
                return 'UDP'
            else:
                return 'TCP'

    @icontrol_folder
    def set_description(self, name=None, description=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_description([name], [description])

    @icontrol_folder
    def get_description(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_vs.get_description([name])[0]

    @icontrol_folder
    def set_traffic_group(self, name=None, traffic_group=None,
                          folder='Common'):
        if self.exists(name=name, folder=folder):
            address_port = self.lb_vs.get_destination_v2([name])[0]
            self._set_vitrual_address_traffic_group(name=address_port.address,
                                                    folder=folder)

    @icontrol_folder
    def get_traffic_group(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            address_port = self.lb_vs.get_destination_v2([name])[0]
            return self._get_vitrual_address_traffic_group(
                                                    name=address_port.address,
                                                    folder=folder)

    @icontrol_folder
    def set_connection_limit(self, name=None, connection_limit=0,
                             folder='Common'):
        ulong = self.bigip.int_to_ulong(connection_limit)
        common_ulong = self.lb_vs.typefactory.create('Common.ULong64')
        common_ulong.low = ulong.low
        common_ulong.high = ulong.high
        self.lb_vs.set_connection_limit([name], [common_ulong])

    @icontrol_folder
    def get_connection_limit(self, name=None,
                             folder='Common'):
        return self.bigip.ulong_to_int(
                             self.lb_vs.get_connection_limit([name])[0])

    @icontrol_folder
    def set_snat_automap(self, name=None, folder='Common'):
        self.lb_vs.set_source_address_translation_automap([name])

    @icontrol_folder
    def set_snat_pool(self, name=None, pool_name=None, folder='Common'):
        self.lb_vs.set_source_address_translation_snat_pool([name],
                                                            [pool_name])

    @icontrol_folder
    def remove_snat(self, name=None, folder='Common'):
        self.lb_vs.set_source_address_translation_none([name])

    def _get_protocol_type(self, protocol_str):
        protocol_str = protocol_str.upper()
        protocol_type = self.lb_vs.typefactory.create('Common.ProtocolType')

        if protocol_str == 'ICMP':
            return protocol_type.PROTOCOL_ICMP
        elif protocol_str == 'UDP':
            return protocol_type.PROTOCOL_UDP
        else:
            return protocol_type.PROTOCOL_TCP

    @icontrol_folder
    def _get_vitrual_address_traffic_group(self, name=None, folder='Common'):
        return self.lb_va.get_traffic_group([name])[0]

    @icontrol_folder
    def _set_vitrual_address_traffic_group(self, name=None, folder='Common'):
        return self.lb_va.get_traffic_group([name])[0]

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        self.bigip.system.set_folder(folder)
        if name in self.lb_vs.get_list():
            return True
        else:
            return False

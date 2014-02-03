import os
from f5.common import constants as const


# Networking - Self-IP
class SelfIP(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('Networking.SelfIPV2')

        # iControl helper objects
        self.net_self = self.bigip.icontrol.Networking.SelfIPV2

    def create(self, name, addr, mask, vlan_name, floating):
        if not self.exists(name) and self.bigip.vlan.exists(vlan_name):
            enabled_state = self.net_self.typefactory.create(
                                        'Common.EnabledState').STATE_ENABLED
            traffic_group = const.SHARED_CONFIG_DEFAULT_TRAFFIC_GROUP
            if floating:
                traffic_group = \
                    const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP

            self.net_self.create([name],
                                 [vlan_name],
                                 [addr],
                                 [mask],
                                 [traffic_group],
                                 [enabled_state])

    def delete(self, name):
        if self.exists(name):
            self.net_self.delete_self_ip([name])

    def get_all(self):
        return self.net_self.get_list()

    def get_addrs(self):
        return map(os.path.basename, self.net_self.get_address(self.get_all()))

    def get_addr(self, name):
        if self.exists(name):
            return self.net_self.get_address([name])[0]

    def get_mask(self, name):
        if self.exists(name):
            return self.net_self.get_netmask([name])[0]

    def set_mask(self, name, mask):
        if self.exists(name):
            self.net_self.set_netmask([name], [mask])

    def get_vlan(self, name):
        self.net_self.get_vlan([name])[0]

    def set_port_lockdown_allow_all(self, name):
        self._set_port_lockdown_mode(name, "ALLOW_MODE_ALL")

    def set_port_lockdown_allow_default(self, name):
        self._set_port_lockdown_mode(name, "ALLOW_MODE_DEFAULTS")

    def set_port_lockdown_allow_none(self, name):
        self._set_port_lockdown_mode(name, "ALLOW_MODE_NONE")

    def get_floating_addrs(self, prefix):
        names = [x for x in self.net_self.get_list() if x.startswith(prefix)]
        floats = []

        if names:
            for i, traffic_group in enumerate(
                                    self.net_self.get_traffic_group(names)):
                if traffic_group == \
                    const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP:
                    floats.append(names[i])

            return map(os.path.basename, self.net_self.get_address(floats))
        else:
            return []

    def _set_port_lockdown_mode(self, name, mode):
        # remove any existing access lists
        self._reset_port_lockdown_allow_list(name)

        access_list = self.net_self.typefactory.create(
                                    'Networking.SelfIPV2.ProtocolPortAccess')
        access_list.mode = mode
        access_list.protocol_ports = []

        # set new access list
        self.net_self.add_allow_access_list([name], [access_list])

    def _reset_port_lockdown_allow_list(self, name):
        access_list = self.net_self.get_allow_access_list([name])
        self.net_self.remove_allow_access_list([name], access_list)

    def exists(self, name):
        #if name in map(os.path.basename, self.net_self.get_list()):
        if name in self.net_self.get_list():
            return True

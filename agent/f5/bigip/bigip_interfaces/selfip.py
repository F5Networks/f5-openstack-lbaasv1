import os
from f5.common import constants as const

from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder

# Networking - Self-IP
from neutron.common import log


class SelfIP(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('Networking.SelfIPV2')

        # iControl helper objects
        self.net_self = self.bigip.icontrol.Networking.SelfIPV2

    @icontrol_folder
    @domain_address
    @log.log
    def create(self, name=None, ip_address=None, netmask=None,
               vlan_name=None, floating=False, traffic_group=None,
               folder='Common'):
        if not self.exists(name=name, folder=folder) and \
               self.bigip.vlan.exists(name=vlan_name, folder=folder):
            enabled_state = self.net_self.typefactory.create(
                                        'Common.EnabledState').STATE_ENABLED
            if not traffic_group:
                traffic_group = const.SHARED_CONFIG_DEFAULT_TRAFFIC_GROUP
                if floating:
                    traffic_group = \
                       const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.net_self.create([name],
                                 [vlan_name],
                                 [ip_address],
                                 [netmask],
                                 [traffic_group],
                                 [enabled_state])
            return True
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_self.delete_self_ip([name])
            return True
        else:
            return False

    @icontrol_folder
    def get_all(self, folder='Common'):
        return self.net_self.get_list()

    @icontrol_folder
    def get_addrs(self, folder='Common'):
        return map(os.path.basename,
                   self.net_self.get_address(
                            self.get_all(folder=folder)))

    @icontrol_folder
    def get_addr(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.net_self.get_address([name])[0]

    @icontrol_folder
    def get_mask(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.net_self.get_netmask([name])[0]

    @icontrol_folder
    @domain_address
    def set_mask(self, name=None, netmask=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_self.set_netmask([name], [netmask])
            return True
        else:
            return False

    @icontrol_folder
    def get_vlan(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_self.get_vlan([name])[0]

    @icontrol_folder
    def set_vlan(self, name=None, vlan_name=None, folder='Common'):
        if self.exists(name=name, folder=folder) and \
           self.bigip.vlan.exists(name=vlan_name, folder=folder):
            self.net_self.set_vlan([name], [vlan_name])
            return True
        else:
            return False

    @icontrol_folder
    def set_description(self, name=None, description=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_self.set_description([name], [description])
            return True
        else:
            return False

    @icontrol_folder
    def get_description(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.net_self.get_description([name])[0]

    @icontrol_folder
    def set_traffic_group(self, name=None, traffic_group=None,
                          folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_self.set_traffic_group([name], [traffic_group])
            return True
        else:
            return False

    @icontrol_folder
    def get_traffic_group(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.net_self.get_traffic_group([name])[0]

    @icontrol_folder
    def set_port_lockdown_allow_all(self, name=None, folder='Commmon'):
        if self.exists(name=name, folder=folder):
            self._set_port_lockdown_mode(name, "ALLOW_MODE_ALL")
            return True
        else:
            return False

    @icontrol_folder
    def set_port_lockdown_allow_default(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self._set_port_lockdown_mode(name, "ALLOW_MODE_DEFAULTS")
            return True
        else:
            return False

    @icontrol_folder
    def set_port_lockdown_allow_none(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self._set_port_lockdown_mode(name, "ALLOW_MODE_NONE")
            return True
        else:
            return False

    @icontrol_folder
    def get_floating_addrs(self, prefix=None, folder='Common'):
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

    def _set_port_lockdown_mode(self, name=None, mode=None, folder='Common'):
        # remove any existing access lists
        self._reset_port_lockdown_allow_list(name)

        access_list = self.net_self.typefactory.create(
                                    'Networking.SelfIPV2.ProtocolPortAccess')
        access_list.mode = mode
        access_list.protocol_ports = []

        # set new access list
        self.net_self.add_allow_access_list([name], [access_list])

    def _reset_port_lockdown_allow_list(self, name=None, folder='Common'):
        access_list = self.net_self.get_allow_access_list([name])
        self.net_self.remove_allow_access_list([name], access_list)

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        self.bigip.system.set_folder(folder=folder)
        if name in self.net_self.get_list():
            return True

from f5.common import constants as const

from f5.bigip.bigip_interfaces import icontrol_folder

import os

# Networking - VLAN


class Vlan(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['Networking.VLAN',
                                            'Networking.SelfIPV2'])

        # iControl helper objects
        self.net_vlan = self.bigip.icontrol.Networking.VLAN
        self.net_self = self.bigip.icontrol.Networking.SelfIPV2

    @icontrol_folder
    def create(self, name=None, vlanid=None, interface=None,
               folder='Common', description=None):
        if not self.exists(name=name, folder=folder):
            mem_seq = self.net_vlan.typefactory.create(
                                    'Networking.VLAN.MemberSequence')
            fs_state = self.net_vlan.typefactory.create(
                                    'Common.EnabledState').STATE_DISABLED
            if interface:
                mem_entry = self.net_vlan.typefactory.create(
                                    'Networking.VLAN.MemberEntry')
                mem_entry.member_name = interface
                mem_entry.member_type = self.net_vlan.typefactory.create(
                                'Networking.MemberType').MEMBER_INTERFACE

                # use tagged interface for hardware platforms,
                # untagged for VE
                if self.bigip.system.get_platform().startswith(
                                    const.BIGIP_VE_PLATFORM_ID):
                    mem_entry.tag_state = self.net_vlan.typefactory.create(
                                'Networking.MemberTagType').MEMBER_UNTAGGED
                else:
                    mem_entry.tag_state = self.net_vlan.typefactory.create(
                                'Networking.MemberTagType').MEMBER_TAGGED

                mem_seq.item = mem_entry
            self.net_vlan.create_v2([name],
                                    [int(vlanid)],
                                    [mem_seq],
                                    [fs_state],
                                    [90])
            if description:
                self.net_vlan.set_description([name], [description])
            if not folder == 'Common':
                self.bigip.route.add_vlan_to_domain(name=name, folder=folder)
            return True
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if not self._in_use(name) and self.exists(name):
            self.net_vlan.delete_vlan([name])
            return True
        else:
            return False

    @icontrol_folder
    def get_all(self, folder='Common'):
        return self.net_vlan.get_list()

    @icontrol_folder
    def get_id(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return int(self.net_vlan.get_vlan_id([name])[0])

    @icontrol_folder
    def set_id(self, name=None, vlanid=0, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_vlan.set_vlan_id([name], [int(vlanid)])
            return True
        else:
            return False

    @icontrol_folder
    def get_interface(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            members = self.net_vlan.get_member([name])

            if len(members[0]) > 0:
                return self.net_vlan.get_member([name])[0][0].member_name

    @icontrol_folder
    def set_interface(self, name=None, interface='1.1', folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_vlan.remove_all_members([name])
            if interface:
                member_seq = self.net_vlan.typefactory.create(
                                'Networking.VLAN.MemberSequence')
                member_entry = self.net_vlan.typefactory.create(
                                'Networking.VLAN.MemberEntry')
                member_entry.member_name = interface
                member_type = self.net_vlan.typefactory.create(
                                'Networking.MemberType').MEMBER_INTERFACE
                member_entry.member_type = member_type
                # use tagged interface for hardware platforms,
                # untagged for VE
                if self.bigip.system.get_platform().startswith(
                                const.BIGIP_VE_PLATFORM_ID):
                    tag_state = self.net_vlan.typefactory.create(
                                'Networking.MemberTagType').MEMBER_UNTAGGED
                    member_entry.tag_state = tag_state
                else:
                    tag_state = self.net_vlan.typefactory.create(
                                'Networking.MemberTagType').MEMBER_TAGGED
                    member_entry.tag_state = tag_state
                member_seq.item = member_entry
                self.net_vlan.add_member([name], [member_seq])
            return True
        else:
            return False

    def get_vlan_hash(self, interface, vlanid):
        return "vlan-" + str(interface).replace(".", "-") + "-" + str(vlanid)

    @icontrol_folder
    def get_vlan_name_by_description(self, description=None, folder='Common'):
        vlans = self.net_vlan.get_list()
        descriptions = self.net_vlan.get_description(vlans)
        for i in range(len(descriptions)):
            if descriptions[i] == description:
                return os.path.basename(vlans[i])
        return None

    @icontrol_folder
    def set_description(self, name=None, description=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_vlan.set_description([name], [description])
            return True
        else:
            return False

    @icontrol_folder
    def get_description(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.net_vlan.get_description([name])[0]

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        if name:
            if name.startswith('/Common/'):
                self.bigip.system.set_folder('/Common')
            if name in self.net_vlan.get_list():
                return True

    @icontrol_folder
    def _in_use(self, name=None, folder='Common'):
        self_ips = self.net_self.get_list()
        if len(self_ips) > 0:
            if name in self.net_self.get_vlan(self_ips):
                return True

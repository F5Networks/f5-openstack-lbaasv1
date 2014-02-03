from common import constants as const


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

    def create(self, name, vlanid, interface):
        if not self.exists(name):
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

    def delete(self, name):
        if not self._in_use(name) and self.exists(name):
            self.net_vlan.delete_vlan([name])

    def get_all(self):
        return self.net_vlan.get_list()

    def get_id(self, name):
        if self.exists(name):
            return int(self.net_vlan.get_vlan_id([name])[0])

    def set_id(self, name, vlanid):
        if self.exists(name):
            self.net_vlan.set_vlan_id([name], [int(vlanid)])

    def get_interface(self, name):
        if self.exists(name):
            members = self.net_vlan.get_member([name])

            if len(members[0]) > 0:
                return self.net_vlan.get_member([name])[0][0].member_name

    def set_interface(self, name, interface):
        if self.exists(name):
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

    def exists(self, name):
        if name in self.net_vlan.get_list():
            return True

    def _in_use(self, name):
        self_ips = self.net_self.get_list()
        if len(self_ips) > 0:
            if name in self.net_self.get_vlan(self_ips):
                return True

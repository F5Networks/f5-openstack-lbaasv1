""" Module for managing L2 configuration on F5 BIG-IP """
# pylint: disable=no-self-use

from neutron.openstack.common import log as logging
from neutron.common import constants as q_const

from f5.bigip import exceptions as f5ex
from f5.bigip.bigip_interfaces import prefixed
from f5.bigip import bigip as f5_bigip
from f5.bigip.exceptions import \
    VLANCreationException, VLANDeleteException

from time import sleep, time
import random

from suds import WebFault

LOG = logging.getLogger(__name__)


def _get_tunnel_name(network):
    """ BIG-IP object name for a tunnel """
    tunnel_type = network['provider:network_type']
    tunnel_id = network['provider:segmentation_id']
    return 'tunnel-' + str(tunnel_type) + '-' + str(tunnel_id)


def _get_tunnel_fake_mac(network, local_ip):
    """ create a fake mac for l2 records for tunnels """
    network_id = str(network['provider:segmentation_id']).rjust(4, '0')
    mac_prefix = '02:' + network_id[:2] + ':' + network_id[2:4] + ':'
    ip_parts = local_ip.split('.')
    if len(ip_parts) > 3:
        mac = [int(ip_parts[-3]),
               int(ip_parts[-2]),
               int(ip_parts[-1])]
    else:
        ip_parts = local_ip.split(':')
        if len(ip_parts) > 3:
            mac = [int('0x' + ip_parts[-3], 16),
                   int('0x' + ip_parts[-2], 16),
                   int('0x' + ip_parts[-1], 16)]
        else:
            mac = [random.randint(0x00, 0x7f),
                   random.randint(0x00, 0xff),
                   random.randint(0x00, 0xff)]
    return mac_prefix + ':'.join("%02x" % octet for octet in mac)


def get_vcmp_guest(vcmp_host, bigip):
    """Get vCMP Guest associated with bigip (if any)"""
    for vcmp_guest in vcmp_host['guests']:
        if vcmp_guest['mgmt_addr'] == bigip.icontrol.hostname:
            return vcmp_guest
    return None


class BigipL2Manager(object):
    """ Class for configuring L2 networks and FDB entries """
    def __init__(self, driver):
        self.driver = driver

        self.l2pop_rpc = None

        self.interface_mapping = {}
        self.tagging_mapping = {}

        # map format is   phynet:interface:tagged
        for maps in self.driver.conf.f5_external_physical_mappings:
            intmap = maps.split(':')
            net_key = str(intmap[0]).strip()
            if len(intmap) > 3:
                net_key = net_key + ':' + str(intmap[3]).strip()
            self.interface_mapping[net_key] = str(intmap[1]).strip()
            self.tagging_mapping[net_key] = str(intmap[2]).strip()
            LOG.debug(_('physical_network %s = interface %s, tagged %s'
                        % (net_key, intmap[1], intmap[2])))

        self.__vcmp_hosts = []
        self._init_vcmp_hosts()

    def get_vcmp_host(self, bigip):
        """Get vCMP Host associated with bigip (if any)"""
        for vcmp_host in self.__vcmp_hosts:
            for vcmp_guest in vcmp_host['guests']:
                if vcmp_guest['mgmt_addr'] == bigip.icontrol.hostname:
                    return vcmp_host
        return None

    def _init_vcmp_hosts(self):
        """Initialize vCMP Hosts.  Includes establishing a bigip connection
           to the vCMP host and determining associated vCMP Guests."""
        if not self.driver.conf.icontrol_vcmp_hostname:
            # No vCMP Hosts. Check if any vCMP Guests exist.
            # Flag issue in log.
            self.check_vcmp_host_assignments()
            return

        vcmp_hostnames = self.driver.conf.icontrol_vcmp_hostname.split(',')
        for vcmp_hostname in vcmp_hostnames:
            # vCMP Host Attributes
            vcmp_host = {}
            vcmp_host['bigip'] = f5_bigip.BigIP(
                vcmp_hostname,
                self.driver.conf.icontrol_username,
                self.driver.conf.icontrol_password, 5)
            vcmp_host['guests'] = []

            # vCMP Guest Attributes
            guest_names = vcmp_host['bigip'].system.sys_vcmp.get_list()
            guest_mgmts = vcmp_host['bigip'].\
                system.sys_vcmp.get_management_address(guest_names)

            for guest_name, guest_mgmt in zip(guest_names, guest_mgmts):
                # Only add vCMP Guests with BIG-IP that has been registered
                if guest_mgmt.address in self.driver.get_bigip_hosts():
                    vcmp_guest = {}
                    vcmp_guest['name'] = guest_name
                    vcmp_guest['mgmt_addr'] = guest_mgmt.address
                    vcmp_host['guests'].append(vcmp_guest)

            self.__vcmp_hosts.append(vcmp_host)

        self.check_vcmp_host_assignments()

        # Output vCMP Hosts/Guests in log
        for vcmp_host in self.__vcmp_hosts:
            for vcmp_guest in vcmp_host['guests']:
                LOG.debug(('vCMPHost[%s] vCMPGuest[%s] - mgmt: %s' %
                          (vcmp_host['bigip'].icontrol.hostname,
                           vcmp_guest['name'], vcmp_guest['mgmt_addr'])))

    def check_vcmp_host_assignments(self):
        """Check that all vCMP Guest bigips have a host assignment"""
        LOG.debug(('Check registered bigips to ensure vCMP Guests '
                   'have a vCMP host assignment'))

        for bigip in self.driver.get_all_bigips():
            system_info = bigip.system.sys_info.get_system_information()
            if system_info.platform == 'Z101':
                if self.get_vcmp_host(bigip):
                    LOG.debug(('vCMP host found for vCMP Guest %s' %
                               bigip.icontrol.hostname))
                else:
                    LOG.error(('vCMP host not found for vCMP Guest %s' %
                               bigip.icontrol.hostname))
            else:
                LOG.debug(('BIG-IP %s is not a vCMP Guest' %
                           bigip.icontrol.hostname))

    def is_common_network(self, network):
        """ Does this network belong in the /Common folder? """
        return network['shared'] or \
            (network['id'] in self.driver.conf.common_network_ids) or \
            ('router:external' in network and
             network['router:external'] and
             (network['id'] in self.driver.conf.common_external_networks))

    def get_vlan_name(self, network, hostname):
        """ Construct a consistent vlan name """
        net_key = network['provider:physical_network']
        # look for host specific interface mapping
        if net_key + ':' + hostname in self.interface_mapping:
            interface = self.interface_mapping[net_key + ':' + hostname]
            tagged = self.tagging_mapping[net_key + ':' + hostname]
        # look for specific interface mapping
        elif net_key in self.interface_mapping:
            interface = self.interface_mapping[net_key]
            tagged = self.tagging_mapping[net_key]
        # use default mapping
        else:
            interface = self.interface_mapping['default']
            tagged = self.tagging_mapping['default']

        if tagged:
            vlanid = network['provider:segmentation_id']
        else:
            vlanid = 0

        vlan_name = "vlan-" + \
                    str(interface).replace(".", "-") + \
                    "-" + str(vlanid)
        if len(vlan_name) > 15:
            vlan_name = 'vlan-tr-' + str(vlanid)
        return vlan_name

    def assure_bigip_network(self, bigip, network):
        """ Ensure bigip has configured network object """
        if not network:
            LOG.error(_('assure_bigip_network: '
                        'Attempted to assure a network with no id..skipping.'))
            return

        if network['id'] in bigip.assured_networks:
            return

        if network['id'] in self.driver.conf.common_network_ids:
            LOG.debug(_('assure_bigip_network: '
                        'Network is a common global network... skipping.'))
            return

        LOG.debug("assure_bigip_network network: %s" % str(network))
        start_time = time()
        if self.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = network['tenant_id']

        # setup all needed L2 network segments
        if network['provider:network_type'] == 'flat':
            self._assure_device_network_flat(network, bigip, network_folder)
        elif network['provider:network_type'] == 'vlan':
            self._assure_device_network_vlan(network, bigip, network_folder)
        elif network['provider:network_type'] == 'vxlan':
            self._assure_device_network_vxlan(network, bigip, network_folder)
        elif network['provider:network_type'] == 'gre':
            self._assure_device_network_gre(network, bigip, network_folder)
        else:
            error_message = 'Unsupported network type %s.' \
                            % network['provider:network_type'] + \
                            ' Cannot setup network.'
            LOG.error(_(error_message))
            raise f5ex.InvalidNetworkType(error_message)
        bigip.assured_networks.append(network['id'])
        if time() - start_time > .001:
            LOG.debug("        assure bigip network took %.5f secs" %
                      (time() - start_time))

    def _assure_device_network_flat(self, network, bigip, network_folder):
        """ Ensure bigip has configured flat vlan (untagged) """
        interface = self.interface_mapping['default']
        vlanid = 0

        # Do we have host specific mappings?
        net_key = network['provider:physical_network']
        if net_key + ':' + bigip.icontrol.hostname in \
                self.interface_mapping:
            interface = self.interface_mapping[
                net_key + ':' + bigip.icontrol.hostname]
        # Do we have a mapping for this network
        elif net_key in self.interface_mapping:
            interface = self.interface_mapping[net_key]

        vlan_name = self.get_vlan_name(network,
                                       bigip.icontrol.hostname)

        self._assure_vcmp_device_network(bigip,
                                         vlan={'name': vlan_name,
                                               'folder': network_folder,
                                               'id': vlanid,
                                               'interface': interface,
                                               'network': network})

        if self.get_vcmp_host(bigip):
            interface = None

        bigip.vlan.create(name=vlan_name,
                          vlanid=0,
                          interface=interface,
                          folder=network_folder,
                          description=network['id'])

    def _assure_device_network_vlan(self, network, bigip, network_folder):
        """ Ensure bigip has configured tagged vlan """
        # VLAN names are limited to 64 characters including
        # the folder name, so we name them foolish things.

        interface = self.interface_mapping['default']
        tagged = self.tagging_mapping['default']
        vlanid = 0

        # Do we have host specific mappings?
        net_key = network['provider:physical_network']
        if net_key + ':' + bigip.icontrol.hostname in \
                self.interface_mapping:
            interface = self.interface_mapping[
                net_key + ':' + bigip.icontrol.hostname]
            tagged = self.tagging_mapping[
                net_key + ':' + bigip.icontrol.hostname]
        # Do we have a mapping for this network
        elif net_key in self.interface_mapping:
            interface = self.interface_mapping[net_key]
            tagged = self.tagging_mapping[net_key]

        if tagged:
            vlanid = network['provider:segmentation_id']
        else:
            vlanid = 0

        vlan_name = self.get_vlan_name(network,
                                       bigip.icontrol.hostname)

        self._assure_vcmp_device_network(bigip,
                                         vlan={'name': vlan_name,
                                               'folder': network_folder,
                                               'id': vlanid,
                                               'interface': interface,
                                               'network': network})

        if self.get_vcmp_host(bigip):
            interface = None

        bigip.vlan.create(name=vlan_name,
                          vlanid=vlanid,
                          interface=interface,
                          folder=network_folder,
                          description=network['id'])

    def _assure_device_network_vxlan(self, network, bigip, network_folder):
        """ Ensure bigip has configured vxlan """
        if not bigip.local_ip:
            error_message = 'Cannot create tunnel %s on %s' \
                % (network['id'], bigip.icontrol.hostname)
            error_message += ' no VTEP SelfIP defined.'
            LOG.error('VXLAN:' + error_message)
            raise f5ex.MissingVTEPAddress('VXLAN:' + error_message)

        tunnel_name = _get_tunnel_name(network)
        # create the main tunnel entry for the fdb records
        bigip.vxlan.create_multipoint_tunnel(
            name=tunnel_name,
            profile_name='vxlan_ovs',
            self_ip_address=bigip.local_ip,
            vxlanid=network['provider:segmentation_id'],
            description=network['id'],
            folder=network_folder)
        # notify all the compute nodes we are VTEPs
        # for this network now.
        if self.driver.conf.l2_population:
            fdb_entries = {network['id']:
                           {'ports': {
                            bigip.local_ip: [q_const.FLOODING_ENTRY]
                            },
                            'network_type':
                               network['provider:network_type'],
                            'segment_id':
                               network['provider:segmentation_id']}}
            self.l2pop_rpc.add_fdb_entries(self.driver.context, fdb_entries)

    def _assure_device_network_gre(self, network, bigip, network_folder):
        """ Ensure bigip has configured gre tunnel """
        if not bigip.local_ip:
            error_message = 'Cannot create tunnel %s on %s' \
                % (network['id'], bigip.icontrol.hostname)
            error_message += ' no VTEP SelfIP defined.'
            LOG.error('L2GRE:' + error_message)
            raise f5ex.MissingVTEPAddress('L2GRE:' + error_message)

        tunnel_name = _get_tunnel_name(network)

        bigip.l2gre.create_multipoint_tunnel(
            name=tunnel_name,
            profile_name='gre_ovs',
            self_ip_address=bigip.local_ip,
            greid=network['provider:segmentation_id'],
            description=network['id'],
            folder=network_folder)
        # notify all the compute nodes we are VTEPs
        # for this network now.
        if self.driver.conf.l2_population:
            fdb_entries = {network['id']:
                           {'ports': {
                            bigip.local_ip: [q_const.FLOODING_ENTRY]
                            },
                            'network_type':
                               network['provider:network_type'],
                            'segment_id':
                               network['provider:segmentation_id']}}
            self.l2pop_rpc.add_fdb_entries(self.driver.context, fdb_entries)

    def _assure_vcmp_device_network(self, bigip, vlan):
        """For vCMP Guests, add VLAN to vCMP Host, associate VLAN with
           vCMP Guest, and remove VLAN from /Common on vCMP Guest."""
        vcmp_host = self.get_vcmp_host(bigip)
        if not vcmp_host:
            return

        # Create the VLAN on the vCMP Host
        try:
            vcmp_host['bigip'].vlan.create(name=vlan['name'],
                                           vlanid=vlan['id'],
                                           interface=vlan['interface'],
                                           folder='/Common',
                                           description=vlan['network']['id'])
            LOG.debug(('Created VLAN %s on vCMP Host %s' %
                      (vlan['name'], vcmp_host['bigip'].icontrol.hostname)))
        except VLANCreationException as exc:
            LOG.error(
                ('Exception creating VLAN %s on vCMP Host %s:%s' %
                 (vlan['name'], vcmp_host['bigip'].icontrol.hostname, exc)))

        # Associate the VLAN with the vCMP Guest
        vcmp_guest = get_vcmp_guest(vcmp_host, bigip)
        try:
            vlan_seq = vcmp_host['bigip'].system.sys_vcmp.typefactory.\
                create('Common.StringSequence')
            vlan_seq.values = prefixed(vlan['name'])
            vlan_seq_seq = vcmp_host['bigip'].system.sys_vcmp.typefactory.\
                create('Common.StringSequenceSequence')
            vlan_seq_seq.values = [vlan_seq]
            vcmp_host['bigip'].system.sys_vcmp.add_vlan([vcmp_guest['name']],
                                                        vlan_seq_seq)
            LOG.debug(('Associated VLAN %s with vCMP Guest %s' %
                       (vlan['name'], vcmp_guest['mgmt_addr'])))
        except WebFault as exc:
            LOG.error(('Exception associating VLAN %s to vCMP Guest %s: %s '
                      % (vlan['name'], vcmp_guest['mgmt_addr'], exc)))

        # Wait for the VLAN to propagate to /Common on vCMP Guest
        full_path_vlan_name = '/Common/' + prefixed(vlan['name'])
        try:
            vlan_created = False
            for _ in range(0, 30):
                if full_path_vlan_name in bigip.vlan.get_all(folder='/Common'):
                    vlan_created = True
                    break
                LOG.debug(('Wait for VLAN %s to be created on vCMP Guest %s.'
                          % (full_path_vlan_name, vcmp_guest['mgmt_addr'])))
                sleep(1)

            if vlan_created:
                LOG.debug(('VLAN %s exists on vCMP Guest %s.' %
                          (full_path_vlan_name, vcmp_guest['mgmt_addr'])))
            else:
                LOG.error(('VLAN %s does not exist on vCMP Guest %s.' %
                          (full_path_vlan_name, vcmp_guest['mgmt_addr'])))
        except WebFault as exc:
            LOG.error(('Exception waiting for vCMP Host VLAN %s to '
                       'be created on vCMP Guest %s: %s' %
                      (vlan['name'], vcmp_guest['mgmt_addr'], exc)))
        except Exception as exc:
            LOG.error(('Exception waiting for vCMP Host VLAN %s to '
                       'be created on vCMP Guest %s: %s' %
                      (vlan['name'], vcmp_guest['mgmt_addr'], exc)))

        # Delete the VLAN from the /Common folder on the vCMP Guest
        try:
            bigip.vlan.delete(name=vlan['name'],
                              folder='/Common')
            LOG.debug(('Deleted VLAN %s from vCMP Guest %s' %
                      (full_path_vlan_name, vcmp_guest['mgmt_addr'])))
        except VLANDeleteException as exc:
            LOG.error(('Exception deleting VLAN %s from vCMP Guest %s: %s' %
                      (full_path_vlan_name, vcmp_guest['mgmt_addr'], exc)))
        except Exception as exc:
            LOG.error(('Exception deleting VLAN %s from vCMP Guest %s: %s' %
                      (full_path_vlan_name, vcmp_guest['mgmt_addr'], exc)))

    def delete_bigip_network(self, bigip, network):
        """ Delete network on bigip """
        if network['id'] in self.driver.conf.common_network_ids:
            LOG.debug(_('skipping delete of common network %s'
                        % network['id']))
            return
        if self.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = network['tenant_id']
        if network['provider:network_type'] == 'vlan':
            self._delete_device_vlan(bigip, network, network_folder)
        elif network['provider:network_type'] == 'flat':
            self._delete_device_flat(bigip, network, network_folder)
        elif network['provider:network_type'] == 'vxlan':
            self._delete_device_vxlan(bigip, network, network_folder)
        elif network['provider:network_type'] == 'gre':
            self._delete_device_gre(bigip, network, network_folder)
        else:
            LOG.error(_('Unsupported network type %s. Can not delete.'
                        % network['provider:network_type']))
        if network['id'] in bigip.assured_networks:
            bigip.assured_networks.remove(network['id'])

    def _delete_device_vlan(self, bigip, network, network_folder):
        """ Delete tagged vlan on specific bigip """
        vlan_name = self.get_vlan_name(network,
                                       bigip.icontrol.hostname)
        bigip.vlan.delete(name=vlan_name,
                          folder=network_folder)
        self._delete_vcmp_device_network(bigip, vlan_name)

    def _delete_device_flat(self, bigip, network, network_folder):
        """ Delete untagged vlan on specific bigip """
        vlan_name = self.get_vlan_name(network,
                                       bigip.icontrol.hostname)
        bigip.vlan.delete(name=vlan_name,
                          folder=network_folder)
        self._delete_vcmp_device_network(bigip, vlan_name)

    def _delete_device_vxlan(self, bigip, network, network_folder):
        """ Delete vxlan tunnel on specific bigip """
        tunnel_name = _get_tunnel_name(network)

        bigip.vxlan.delete_all_fdb_entries(tunnel_name=tunnel_name,
                                           folder=network_folder)
        bigip.vxlan.delete_tunnel(name=tunnel_name,
                                  folder=network_folder)
        # notify all the compute nodes we no longer have
        # VTEPs for this network now.
        if self.driver.conf.l2_population:
            fdb_entries = {network['id']:
                           {'ports':
                            {bigip.local_ip:
                             [q_const.FLOODING_ENTRY]},
                            'network_type':
                            network['provider:network_type'],
                            'segment_id':
                            network['provider:segmentation_id']}}
            self.l2pop_rpc.remove_fdb_entries(self.driver.context,
                                              fdb_entries)

    def _delete_device_gre(self, bigip, network, network_folder):
        """ Delete gre tunnel on specific bigip """
        tunnel_name = _get_tunnel_name(network)

        # for each known vtep_endpoints to this tunnel
        bigip.l2gre.delete_all_fdb_entries(tunnel_name=tunnel_name,
                                           folder=network_folder)
        bigip.l2gre.delete_tunnel(name=tunnel_name,
                                  folder=network_folder)
        # notify all the compute nodes we no longer
        # VTEPs for this network now.
        if self.driver.conf.l2_population:
            fdb_entries = {network['id']:
                           {'ports': {
                            bigip.local_ip:
                            [q_const.FLOODING_ENTRY]},
                            'network_type':
                            network['provider:network_type'],
                            'segment_id':
                            network['provider:segmentation_id']}}
            self.l2pop_rpc.remove_fdb_entries(self.driver.context,
                                              fdb_entries)

    def _delete_vcmp_device_network(self, bigip, vlan_name):
        """For vCMP Guests, disassociate VLAN from vCMP Guest and
           delete VLAN from vCMP Host."""
        vcmp_host = self.get_vcmp_host(bigip)
        if not vcmp_host:
            return

        # Remove VLAN association from the vCMP Guest
        vcmp_guest = get_vcmp_guest(vcmp_host, bigip)
        try:
            vlan_seq = vcmp_host['bigip'].system.sys_vcmp.typefactory.\
                create('Common.StringSequence')
            vlan_seq.values = prefixed(vlan_name)
            vlan_seq_seq = vcmp_host['bigip'].system.sys_vcmp.typefactory.\
                create('Common.StringSequenceSequence')
            vlan_seq_seq.values = [vlan_seq]
            vcmp_host['bigip'].system.sys_vcmp.remove_vlan(
                [vcmp_guest['name']], vlan_seq_seq)
            LOG.debug(('Removed VLAN %s association from vCMP Guest %s' %
                      (vlan_name, vcmp_guest['mgmt_addr'])))
        except WebFault as webfault:
            LOG.error(('Exception removing VLAN %s association from vCMP '
                       'Guest %s:%s' %
                       (vlan_name, vcmp_guest['mgmt_addr'], webfault)))
        except Exception as exc:
            LOG.error(('Exception removing VLAN %s association from vCMP '
                       'Guest %s:%s' %
                       (vlan_name, vcmp_guest['mgmt_addr'], exc)))

        # Delete VLAN from vCMP Host.  This will fail if any other vCMP Guest
        # is using this VLAN
        try:
            vcmp_host['bigip'].vlan.delete(name=vlan_name,
                                           folder='/Common')
            LOG.debug(('Deleted VLAN %s from vCMP Host %s' %
                      (vlan_name, vcmp_host['bigip'].icontrol.hostname)))
        except WebFault as webfault:
            LOG.error(('Exception deleting VLAN %s from vCMP Host %s:%s' %
                      (vlan_name, vcmp_host['bigip'].icontrol.hostname,
                       webfault)))
        except Exception as exc:
            LOG.error(('Exception deleting VLAN %s from vCMP Host %s:%s' %
                      (vlan_name, vcmp_host['bigip'].icontrol.hostname, exc)))

    def update_bigip_vip_l2(self, bigip, vip):
        """ Update vip l2 records """
        network = vip['network']
        if network:
            if self.is_common_network(network):
                net_folder = 'Common'
            else:
                net_folder = vip['tenant_id']
            fdb_info = {'network': network,
                        'ip_address': None,
                        'mac_address': None}
            self.add_bigip_fdbs(bigip, net_folder, fdb_info, vip)

    def delete_bigip_vip_l2(self, bigip, vip):
        """ Delete vip l2 records """
        network = vip['network']
        if network:
            if self.is_common_network(network):
                net_folder = 'Common'
            else:
                net_folder = vip['tenant_id']
            fdb_info = {'network': network,
                        'ip_address': None,
                        'mac_address': None}
            self.delete_bigip_fdbs(bigip, net_folder, fdb_info, vip)

    def add_bigip_fdbs(self, bigip, net_folder, fdb_info, vteps_by_type):
        """ Add fdb records for a mac/ip with specified vteps """
        network = fdb_info['network']
        net_type = network['provider:network_type']
        vteps_key = net_type + '_vteps'
        if vteps_key in vteps_by_type:
            vteps = vteps_by_type[vteps_key]
            if net_type == 'gre':
                self.add_gre_fdbs(bigip, net_folder, fdb_info, vteps)
            elif net_type == 'vxlan':
                self.add_vxlan_fdbs(bigip, net_folder, fdb_info, vteps)

    def add_gre_fdbs(self, bigip, net_folder, fdb_info, vteps):
        """ Add gre fdb records """
        network = fdb_info['network']
        ip_address = fdb_info['ip_address']
        mac_address = fdb_info['mac_address']
        tunnel_name = _get_tunnel_name(network)
        for vtep in vteps:
            if mac_address:
                mac_addr = mac_address
            else:
                mac_addr = _get_tunnel_fake_mac(network, vtep)
            bigip.l2gre.add_fdb_entry(tunnel_name=tunnel_name,
                                      mac_address=mac_addr,
                                      vtep_ip_address=vtep,
                                      arp_ip_address=ip_address,
                                      folder=net_folder)

    def add_vxlan_fdbs(self, bigip, net_folder, fdb_info, vteps):
        """ Add vxlan fdb records """
        network = fdb_info['network']
        ip_address = fdb_info['ip_address']
        mac_address = fdb_info['mac_address']
        tunnel_name = _get_tunnel_name(network)
        for vtep in vteps:
            if mac_address:
                mac_addr = mac_address
            else:
                mac_addr = _get_tunnel_fake_mac(network, vtep)
            bigip.vxlan.add_fdb_entry(tunnel_name=tunnel_name,
                                      mac_address=mac_addr,
                                      vtep_ip_address=vtep,
                                      arp_ip_address=ip_address,
                                      folder=net_folder)

    def delete_bigip_fdbs(self, bigip, net_folder, fdb_info, vteps_by_type):
        """ Delete fdb records for a mac/ip with specified vteps """
        network = fdb_info['network']
        net_type = network['provider:network_type']
        vteps_key = net_type + '_vteps'
        if vteps_key in vteps_by_type:
            vteps = vteps_by_type[vteps_key]
            if net_type == 'gre':
                self.delete_gre_fdbs(bigip, net_folder, fdb_info, vteps)
            elif net_type == 'vxlan':
                self.delete_vxlan_fdbs(bigip, net_folder, fdb_info, vteps)

    def delete_gre_fdbs(self, bigip, net_folder, fdb_info, vteps):
        """ delete gre fdb records """
        network = fdb_info['network']
        ip_address = fdb_info['ip_address']
        mac_address = fdb_info['mac_address']
        tunnel_name = _get_tunnel_name(network)
        for vtep in vteps:
            if mac_address:
                mac_addr = mac_address
            else:
                mac_addr = _get_tunnel_fake_mac(network, vtep)
            bigip.l2gre.delete_fdb_entry(tunnel_name=tunnel_name,
                                         mac_address=mac_addr,
                                         arp_ip_address=ip_address,
                                         folder=net_folder)

    def delete_vxlan_fdbs(self, bigip, net_folder, fdb_info, vteps):
        """ delete vxlan fdb records """
        network = fdb_info['network']
        ip_address = fdb_info['ip_address']
        mac_address = fdb_info['mac_address']
        tunnel_name = _get_tunnel_name(network)
        for vtep in vteps:
            if mac_address:
                mac_addr = mac_address
            else:
                mac_addr = _get_tunnel_fake_mac(network, vtep)
            bigip.vxlan.delete_fdb_entry(tunnel_name=tunnel_name,
                                         mac_address=mac_addr,
                                         arp_ip_address=ip_address,
                                         folder=net_folder)

    def fdb_add(self, fdb_entries):
        """ Add L2 records for MAC addresses behind tunnel endpoints """
        for network in fdb_entries:
            self._fdb_add_for_network(network, fdb_entries[network])

    def _fdb_add_for_network(self, network, net_entries):
        """ Add L2 records for a specific network """
        net = {'name': network,
               'provider:network_type':
               net_entries['network_type'],
               'provider:segmentation_id':
               net_entries['segment_id']
               }
        tunnel_name = _get_tunnel_name(net)
        add_fdb = {}
        for vtep in net_entries['ports']:
            self._fdb_add_for_vtep(network, net_entries, vtep, add_fdb)

        if len(add_fdb) > 0:
            if net_entries['network_type'] == 'vxlan':
                for bigip in self.driver.get_all_bigips():
                    bigip.vxlan.add_fdb_entries(tunnel_name=tunnel_name,
                                                fdb_entries=add_fdb)
            if net_entries['network_type'] == 'gre':
                for bigip in self.driver.get_all_bigips():
                    bigip.l2gre.add_fdb_entries(tunnel_name=tunnel_name,
                                                fdb_entries=add_fdb)

    def _fdb_add_for_vtep(self, network, net_entries, vtep, add_fdb):
        """ Add L2 records for a specific network+vtep """
        for bigip in self.driver.get_all_bigips():
            _fdb_add_for_bigip(network, net_entries, vtep, bigip, add_fdb)

    def fdb_remove(self, fdb_entries):
        """ Remove L2 records for MAC addresses behind tunnel endpoints """
        for network in fdb_entries:
            self._fdb_remove_for_network(network, fdb_entries[network])

    def _fdb_remove_for_network(self, network, net_entries):
        """ Remove L2 records for a specific network """
        net = {'name': network,
               'provider:network_type':
               net_entries['network_type'],
               'provider:segmentation_id':
               net_entries['segment_id']
               }
        tunnel_name = _get_tunnel_name(net)
        remove_fdb = {}
        for vtep in net_entries['ports']:
            self._fdb_remove_for_vtep(network, net_entries,
                                      vtep, remove_fdb)
        if len(remove_fdb) > 0:
            if net_entries['network_type'] == 'vxlan':
                for bigip in self.driver.get_all_bigips():
                    delete_fdb_entries = bigip.vxlan.delete_fdb_entries
                    delete_fdb_entries(tunnel_name=tunnel_name,
                                       fdb_entries=remove_fdb)
            if net_entries['network_type'] == 'gre':
                for bigip in self.driver.get_all_bigips():
                    delete_fdb_entries = bigip.l2gre.delete_fdb_entries
                    delete_fdb_entries(tunnel_name=tunnel_name,
                                       fdb_entries=remove_fdb)

    def _fdb_remove_for_vtep(self, network, net_entries,
                             vtep, remove_fdb):
        """ Figure out fdb entries to remove for a specific vtep """
        for bigip in self.driver.get_all_bigips():
            _fdb_remove_for_bigip(network, net_entries, vtep, bigip,
                                  remove_fdb)

    def fdb_update(self, fdb_entries):
        """ Update L2 records for MAC addresses behind tunnel endpoints """
        for network in fdb_entries:
            self._fdb_update_for_network(network, fdb_entries[network])

    def _fdb_update_for_network(self, network, net_entries):
        """ Update L2 records for a specific network """
        net = {'name': network,
               'provider:network_type':
               net_entries['network_type'],
               'provider:segmentation_id':
               net_entries['segment_id']
               }
        tunnel_name = _get_tunnel_name(net)
        update_fdb = {}
        for vtep in net_entries['ports']:
            self._fdb_update_for_vtep(network, net_entries, vtep, update_fdb)

        if len(update_fdb) > 0:
            if net_entries['network_type'] == 'vxlan':
                for bigip in self.driver.get_all_bigips():
                    bigip.vxlan.add_fdb_entries(tunnel_name=tunnel_name,
                                                fdb_entries=update_fdb)
            if net_entries['network_type'] == 'gre':
                for bigip in self.driver.get_all_bigips():
                    bigip.l2gre.add_fdb_entries(tunnel_name=tunnel_name,
                                                fdb_entries=update_fdb)

    def _fdb_update_for_vtep(self, network, net_entries,
                             vtep, update_fdb):
        """ Update L2 records for a specific network+vtep """
        for bigip in self.driver.get_all_bigips():
            _fdb_update_for_bigip(network, net_entries, vtep, bigip,
                                  update_fdb)

    def get_network_name(self, bigip, network):
        """ This constructs a name for a tunnel or vlan interface """
        preserve_network_name = False
        if network['id'] in self.driver.conf.common_network_ids:
            network_name = self.driver.conf.common_network_ids[network['id']]
            preserve_network_name = True
        elif network['provider:network_type'] == 'vlan':
            network_name = self.get_vlan_name(network,
                                              bigip.icontrol.hostname)
        elif network['provider:network_type'] == 'flat':
            network_name = self.get_vlan_name(network,
                                              bigip.icontrol.hostname)
        elif network['provider:network_type'] == 'vxlan':
            network_name = _get_tunnel_name(network)
        elif network['provider:network_type'] == 'gre':
            network_name = _get_tunnel_name(network)
        else:
            error_message = 'Unsupported network type %s.' \
                            % network['provider:network_type'] + \
                            ' Cannot setup selfip or snat.'
            LOG.error(_(error_message))
            raise f5ex.InvalidNetworkType(error_message)
        return network_name, preserve_network_name


def _fdb_add_for_bigip(network, net_entries, vtep, bigip, add_fdb):
    """ Figure out fdb entries to add for a specific network+vtep+bigip """
    net = {'name': network,
           'provider:network_type':
           net_entries['network_type'],
           'provider:segmentation_id':
           net_entries['segment_id']
           }
    tunnel_name = _get_tunnel_name(net)
    if vtep == bigip.local_ip:
        return
    folder = None
    if net_entries['network_type'] == 'gre':
        folder = bigip.l2gre.get_tunnel_folder(
            tunnel_name=tunnel_name)
    if net_entries['network_type'] == 'vxlan':
        folder = bigip.vxlan.get_tunnel_folder(
            tunnel_name=tunnel_name)
    if not folder:
        return
    entries = net_entries['ports'][vtep]
    for ent in entries:
        if ent[0] == '00:00:00:00:00:00':
            continue
        if not tunnel_name in add_fdb:
            add_fdb[tunnel_name] = {}
        add_fdb[tunnel_name]['folder'] = folder
        if not 'records' in add_fdb[tunnel_name]:
            add_fdb[tunnel_name]['records'] = {}
        add_fdb[tunnel_name]['records'][ent[0]] = {
            'endpoint': vtep,
            'ip_address': ent[1]}


def _fdb_remove_for_bigip(network, net_entries, vtep, bigip, remove_fdb):
    """ Figure out fdb entries to remove for a specific network+vtep+bigip """
    if vtep == bigip.local_ip:
        return

    net = {'name': network,
           'provider:network_type':
           net_entries['network_type'],
           'provider:segmentation_id':
           net_entries['segment_id']
           }
    tunnel_name = _get_tunnel_name(net)
    folder = None
    if net_entries['network_type'] == 'gre':
        folder = bigip.l2gre.get_tunnel_folder(
            tunnel_name=tunnel_name)
    if net_entries['network_type'] == 'vxlan':
        folder = bigip.vxlan.get_tunnel_folder(
            tunnel_name=tunnel_name)
    if not folder:
        return
    entries = net_entries['ports'][vtep]
    for ent in entries:
        if ent[0] == '00:00:00:00:00:00':
            continue
        if not tunnel_name in remove_fdb:
            remove_fdb[tunnel_name] = {}
        remove_fdb[tunnel_name]['folder'] = folder
        if not 'records' in remove_fdb[tunnel_name]:
            remove_fdb[tunnel_name]['records'] = {}
        remove_fdb[tunnel_name]['records'][ent[0]] = {
            'endpoint': vtep,
            'ip_address': ent[1]}


def _fdb_update_for_bigip(network, net_entries, vtep, bigip, update_fdb):
    """ Figure out fdb entries to update for a specific network+vtep+bigip """
    if vtep == bigip.local_ip:
        return

    net = {'name': network,
           'provider:network_type':
           net_entries['network_type'],
           'provider:segmentation_id':
           net_entries['segment_id']
           }
    tunnel_name = _get_tunnel_name(net)
    folder = None
    if net_entries['network_type'] == 'gre':
        folder = bigip.l2gre.get_tunnel_folder(
            tunnel_name=tunnel_name)
    if net_entries['network_type'] == 'vxlan':
        folder = bigip.l2gre.get_tunnel_folder(
            tunnel_name=tunnel_name)
    if not folder:
        return
    entries = net_entries['ports'][vtep]
    for ent in entries:
        if ent[0] != '00:00:00:00:00:00':
            if not tunnel_name in update_fdb:
                update_fdb[tunnel_name] = {}
            update_fdb[tunnel_name]['folder'] = folder
            if not 'records' in update_fdb[tunnel_name]:
                update_fdb[tunnel_name]['records'] = {}
            update_fdb[tunnel_name]['records'][ent[0]] = {
                'endpoint': vtep,
                'ip_address': ent[1]}

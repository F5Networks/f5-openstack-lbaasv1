""" F5 Networks LBaaS Driver using iControl API of BIG-IP """
# Copyright 2014 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# pylint: disable=broad-except,star-args,no-self-use
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants as plugin_const
from neutron.common.exceptions import NeutronException

from f5.bigip import exceptions as f5ex
from neutron.services.loadbalancer.drivers.f5.bigip.selfips \
    import BigipSelfIpManager
from neutron.services.loadbalancer.drivers.f5.bigip.snats \
    import BigipSnatManager

import itertools
import netaddr

LOG = logging.getLogger(__name__)


class NetworkBuilderDirect(object):
    """Create network connectivity for a bigip """
    def __init__(self, conf, driver, bigip_l2_manager=None):
        self.conf = conf
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager
        self.bigip_selfip_manager = BigipSelfIpManager(
            driver, bigip_l2_manager)
        self.bigip_snat_manager = BigipSnatManager(
            driver, bigip_l2_manager)

    def initialize_tunneling(self):
        """ setup tunneling
            setup VTEP tunnels if needed """
        vtep_folder = self.conf.f5_vtep_folder
        vtep_selfip_name = self.conf.f5_vtep_selfip_name
        local_ips = []

        for bigip in self.driver.get_all_bigips():

            if not vtep_folder or vtep_folder.lower() == 'none':
                vtep_folder = 'Common'

            if vtep_selfip_name and \
               not vtep_selfip_name.lower() == 'none':

                # profiles may already exist
                bigip.vxlan.create_multipoint_profile(
                    name='vxlan_ovs', folder='Common')
                bigip.l2gre.create_multipoint_profile(
                    name='gre_ovs', folder='Common')
                # find the IP address for the selfip for each box
                local_ip = bigip.selfip.get_addr(vtep_selfip_name, vtep_folder)
                if local_ip:
                    bigip.local_ip = local_ip
                    local_ips.append(local_ip)
                else:
                    raise f5ex.MissingVTEPAddress(
                        'device %s missing vtep selfip %s'
                        % (bigip.device_name,
                           '/' + vtep_folder + '/' +
                           vtep_selfip_name))
        return local_ips

    def prep_service_networking(self, service, traffic_group):
        """ Assure network connectivity is established on all
            bigips for the service. """
        if self.conf.f5_global_routed_mode or not service['pool']:
            return

        if self.conf.icontrol_config_mode == 'iapp':
            # if in iapp mode, we wait for a vip before doing anything.
            have_vip = ('vip' in service and
                        'id' in service['vip'] and
                        'address' in service['vip'] and
                        service['vip']['address'])
            if not have_vip or \
                    service['vip']['status'] == plugin_const.PENDING_DELETE:
                return

        # Per Device Network Connectivity (VLANs or Tunnels)
        subnetsinfo = _get_subnets_to_assure(service)
        for (assure_bigip, subnetinfo) in \
                itertools.product(self.driver.get_all_bigips(), subnetsinfo):
            self.bigip_l2_manager.assure_bigip_network(
                assure_bigip, subnetinfo['network'])
            self.bigip_selfip_manager.assure_bigip_selfip(
                assure_bigip, service, subnetinfo)

        # L3 Shared Config
        assure_bigips = self.driver.get_config_bigips()
        for subnetinfo in subnetsinfo:
            if self.conf.f5_snat_addresses_per_subnet > 0:
                self._assure_subnet_snats(assure_bigips, service, subnetinfo)

            if subnetinfo['is_for_member'] and not self.conf.f5_snat_mode:
                self._allocate_gw_addr(subnetinfo)
                for assure_bigip in assure_bigips:
                    # if we are not using SNATS, attempt to become
                    # the subnet's default gateway.
                    self.bigip_selfip_manager.assure_gateway_on_subnet(
                        assure_bigip, subnetinfo, traffic_group)

    def _assure_subnet_snats(self, assure_bigips, service, subnetinfo):
        """ Ensure snat for subnet exists on bigips """
        tenant_id = service['pool']['tenant_id']
        subnet = subnetinfo['subnet']
        assure_bigips = \
            [bigip for bigip in assure_bigips
                if tenant_id not in bigip.assured_tenant_snat_subnets or
                subnet['id'] not in
                bigip.assured_tenant_snat_subnets[tenant_id]]
        if len(assure_bigips):
            snat_addrs = self.bigip_snat_manager.get_snat_addrs(
                subnetinfo, tenant_id)
            for assure_bigip in assure_bigips:
                self.bigip_snat_manager.assure_bigip_snats(
                    assure_bigip, subnetinfo, snat_addrs, tenant_id)

    def _allocate_gw_addr(self, subnetinfo):
        """ Create a name for the port and for the IP Forwarding
            Virtual Server as well as the floating Self IP which
            will answer ARP for the members """
        network = subnetinfo['network']
        if not network:
            LOG.error(_('Attempted to create default gateway'
                        ' for network with no id.. skipping.'))
            return

        subnet = subnetinfo['subnet']
        gw_name = "gw-" + subnet['id']
        ports = self.driver.plugin_rpc.get_port_by_name(port_name=gw_name)
        if len(ports) < 1:
            need_port_for_gateway = True

        # There was no port on this agent's host, so get one from Neutron
        if need_port_for_gateway:
            try:
                rpc = self.driver.plugin_rpc
                new_port = rpc.create_port_on_subnet_with_specific_ip(
                    subnet_id=subnet['id'], mac_address=None,
                    name=gw_name, ip_address=subnet['gateway_ip'])
                LOG.info(_('gateway IP for subnet %s will be port %s'
                           % (subnet['id'], new_port['id'])))
            except Exception as exc:
                ermsg = 'Invalid default gateway for subnet %s:%s - %s.' \
                    % (subnet['id'],
                       subnet['gateway_ip'],
                       exc.message)
                ermsg += " SNAT will not function and load balancing"
                ermsg += " support will likely fail. Enable f5_snat_mode."
                LOG.error(_(ermsg))
        return True

    def post_service_networking(self, service, all_subnet_hints):
        """ Assure networks are deleted from big-ips """
        if self.conf.f5_global_routed_mode:
            return

        # L2toL3 networking layer
        # Non Shared Config -  Local Per BIG-IP
        self.update_bigip_l2(service)

        # in iapp mode, we only delete networking if the vip exists
        # and is in pending delete. Otherwise we assume the networking
        # has not been created yet or was already deleted.
        if self.conf.icontrol_config_mode == 'iapp':
            have_vip = ('vip' in service and
                        'id' in service['vip'] and
                        'address' in service['vip'] and
                        service['vip']['address'])
            if not have_vip or \
                    service['vip']['status'] != plugin_const.PENDING_DELETE:
                return

        # Delete shared config objects
        deleted_names = set()
        for bigip in self.driver.get_config_bigips():
            LOG.debug('    post_service_networking: calling '
                      '_assure_delete_networks del nets sh for bigip %s %s'
                      % (bigip.device_name, all_subnet_hints))
            subnet_hints = all_subnet_hints[bigip.device_name]
            deleted_names = deleted_names.union(
                self._assure_delete_nets_shared(bigip, service,
                                                subnet_hints))

        # avoids race condition:
        # deletion of shared ip objects must sync before we
        # remove the selfips or vlans from the peer bigips.
        self.driver.sync_if_clustered()

        # Delete non shared config objects
        for bigip in self.driver.get_all_bigips():
            LOG.debug('    post_service_networking: calling '
                      '    _assure_delete_networks del nets ns for bigip %s'
                      % bigip.device_name)
            if self.conf.f5_sync_mode == 'replication':
                subnet_hints = all_subnet_hints[bigip.device_name]
            else:
                # If in autosync mode, then the IP operations were performed
                # on just the primary big-ip, and so that is where the subnet
                # hints are stored. So, just use those hints for every bigip.
                device_name = self.driver.get_bigip().device_name
                subnet_hints = all_subnet_hints[device_name]
            deleted_names = deleted_names.union(
                self._assure_delete_nets_nonshared(
                    bigip, service, subnet_hints))

        for port_name in deleted_names:
            LOG.debug('    post_service_networking: calling '
                      '    del port %s'
                      % port_name)
            self.driver.plugin_rpc.delete_port_by_name(
                port_name=port_name)

    def update_bigip_l2(self, service):
        """ Update fdb entries on bigip """
        vip = service['vip']
        pool = service['pool']

        have_vip = ('vip' in service and
                    'id' in service['vip'] and
                    'address' in service['vip'] and
                    service['vip']['address'])

        delete_all = False
        if self.conf.icontrol_config_mode == 'iapp':
            # no vip means no iapp deployed means no config
            if not have_vip:
                return
            # deleting vip means whole iapp and all objects
            # with l2 entries should have been removed from bigips
            if service['vip']['status'] == plugin_const.PENDING_DELETE:
                delete_all = True

        for bigip in self.driver.get_all_bigips():
            for member in service['members']:
                if member['status'] == plugin_const.PENDING_DELETE \
                        or delete_all:
                    self.delete_bigip_member_l2(bigip, pool, member)
                else:
                    self.update_bigip_member_l2(bigip, pool, member)
            if 'id' in vip:
                if vip['status'] == plugin_const.PENDING_DELETE:
                    self.delete_bigip_vip_l2(bigip, vip)
                else:
                    self.update_bigip_vip_l2(bigip, vip)

    def update_bigip_member_l2(self, bigip, pool, member):
        """ update pool member l2 records """
        network = member['network']
        if network:
            ip_address = member['address']
            if self.bigip_l2_manager.is_common_network(network):
                net_folder = 'Common'
                ip_address = ip_address + '%0'
            else:
                net_folder = pool['tenant_id']
            fdb_info = {'network': network,
                        'ip_address': ip_address,
                        'mac_address': member['port']['mac_address']}
            self.bigip_l2_manager.add_bigip_fdbs(
                bigip, net_folder, fdb_info, member)

    def delete_bigip_member_l2(self, bigip, pool, member):
        """ Delete pool member l2 records """
        network = member['network']
        if network:
            if member['port']:
                ip_address = member['address']
                if self.bigip_l2_manager.is_common_network(network):
                    net_folder = 'Common'
                    ip_address = ip_address + '%0'
                else:
                    net_folder = pool['tenant_id']
                fdb_info = {'network': network,
                            'ip_address': ip_address,
                            'mac_address': member['port']['mac_address']}
                self.bigip_l2_manager.delete_bigip_fdbs(
                    bigip, net_folder, fdb_info, member)
            else:
                LOG.error(_('Member on SDN has no port. Manual '
                            'removal on the BIG-IP will be '
                            'required. Was the vm instance '
                            'deleted before the pool member '
                            'was deleted?'))

    def update_bigip_vip_l2(self, bigip, vip):
        """ Update vip l2 records """
        network = vip['network']
        if network:
            if self.bigip_l2_manager.is_common_network(network):
                net_folder = 'Common'
            else:
                net_folder = vip['tenant_id']
            fdb_info = {'network': network,
                        'ip_address': None,
                        'mac_address': None}
            self.bigip_l2_manager.add_bigip_fdbs(
                bigip, net_folder, fdb_info, vip)

    def delete_bigip_vip_l2(self, bigip, vip):
        """ Delete vip l2 records """
        network = vip['network']
        if network:
            if self.bigip_l2_manager.is_common_network(network):
                net_folder = 'Common'
            else:
                net_folder = vip['tenant_id']
            fdb_info = {'network': network,
                        'ip_address': None,
                        'mac_address': None}
            self.bigip_l2_manager.delete_bigip_fdbs(
                bigip, net_folder, fdb_info, vip)

    def _assure_delete_nets_shared(self, bigip, service, subnet_hints):
        """ Assure shared configuration (which syncs) is deleted """
        deleted_names = set()
        tenant_id = service['pool']['tenant_id']
        delete_gateway = self.bigip_selfip_manager.delete_gateway_on_subnet
        for subnetinfo in _get_subnets_to_delete(bigip, service, subnet_hints):
            try:
                if not self.conf.f5_snat_mode:
                    gw_name = delete_gateway(bigip, subnetinfo)
                    deleted_names.add(gw_name)
                my_deleted_names, my_in_use_subnets = \
                    self.bigip_snat_manager.delete_bigip_snats(
                        bigip, subnetinfo, tenant_id)
                deleted_names = deleted_names.union(my_deleted_names)
                for in_use_subnetid in my_in_use_subnets:
                    subnet_hints['check_for_delete_subnets'].pop(
                        in_use_subnetid, None)
            except NeutronException as exc:
                LOG.error("assure_delete_nets_shared: exception: %s"
                          % str(exc.msg))
            except Exception as exc:
                LOG.error("assure_delete_nets_shared: exception: %s"
                          % str(exc.message))

        return deleted_names

    def _assure_delete_nets_nonshared(self, bigip, service, subnet_hints):
        """ Delete non shared base objects for networks """
        deleted_names = set()
        for subnetinfo in _get_subnets_to_delete(bigip, service, subnet_hints):
            try:
                network = subnetinfo['network']
                if self.bigip_l2_manager.is_common_network(network):
                    network_folder = 'Common'
                else:
                    network_folder = service['pool']['tenant_id']

                subnet = subnetinfo['subnet']
                if self.conf.f5_populate_static_arp:
                    bigip.arp.delete_by_subnet(subnet=subnet['cidr'],
                                               mask=None,
                                               folder=network_folder)
                local_selfip_name = "local-" + bigip.device_name + \
                                    "-" + subnet['id']
                bigip.selfip.delete(name=local_selfip_name,
                                    folder=network_folder)
                deleted_names.add(local_selfip_name)

                self.bigip_l2_manager.delete_bigip_network(bigip, network)

                if subnet['id'] not in subnet_hints['do_not_delete_subnets']:
                    subnet_hints['do_not_delete_subnets'].append(subnet['id'])
            except NeutronException as exc:
                LOG.error("assure_delete_nets_nonshared: exception: %s"
                          % str(exc.msg))
            except Exception as exc:
                LOG.error("assure_delete_nets_nonshared: exception: %s"
                          % str(exc.message))

        return deleted_names


def _get_subnets_to_assure(service):
    """ Examine service and return active networks """
    networks = dict()
    if 'id' in service['vip'] and \
            not service['vip']['status'] == plugin_const.PENDING_DELETE:
        network = service['vip']['network']
        subnet = service['vip']['subnet']
        networks[network['id']] = {'network': network,
                                   'subnet': subnet,
                                   'is_for_member': False}

    for member in service['members']:
        if not member['status'] == plugin_const.PENDING_DELETE:
            network = member['network']
            subnet = member['subnet']
            networks[network['id']] = {'network': network,
                                       'subnet': subnet,
                                       'is_for_member': True}
    return networks.values()


def _get_subnets_to_delete(bigip, service, subnet_hints):
    """ Clean up any Self IP, SNATs, networks, and folder for
        services items that we deleted. """
    subnets_to_delete = []
    for subnetinfo in subnet_hints['check_for_delete_subnets'].values():
        subnet = subnetinfo['subnet']
        if not subnet:
            continue
        if not _ips_exist_on_subnet(bigip, service, subnet):
            subnets_to_delete.append(subnetinfo)
    return subnets_to_delete


def _ips_exist_on_subnet(bigip, service, subnet):
    """ Does the big-ip have any IP addresses on this subnet? """
    LOG.debug("_ips_exist_on_subnet entry %s" % str(subnet['cidr']))
    ipsubnet = netaddr.IPNetwork(subnet['cidr'])
    # Are there any virtual addresses on this subnet?
    get_vs = bigip.virtual_server.get_virtual_service_insertion
    virtual_services = get_vs(folder=service['pool']['tenant_id'])
    for virt_serv in virtual_services:
        (_, dest) = virt_serv.items()[0]
        LOG.debug("            _ips_exist_on_subnet: checking vip %s"
                  % str(dest['address']))
        if netaddr.IPAddress(dest['address']) in ipsubnet:
            LOG.debug("            _ips_exist_on_subnet: found")
            return True

    # If there aren't any virtual addresses, are there
    # node addresses on this subnet?
    get_node_addr = bigip.pool.get_node_addresses
    nodes = get_node_addr(folder=service['pool']['tenant_id'])
    for node in nodes:
        LOG.debug("            _ips_exist_on_subnet: checking node %s"
                  % str(node))
        if netaddr.IPAddress(node) in ipsubnet:
            LOG.debug("        _ips_exist_on_subnet: found")
            return True

    LOG.debug("            _ips_exist_on_subnet exit %s"
              % str(subnet['cidr']))
    # nothing found
    return False

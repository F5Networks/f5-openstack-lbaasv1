""" Classes and routines for managing BIG-IP self-ips """
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
try:
    from neutron.openstack.common import log as logging
except ImportError:
    from oslo_log import log as logging
import netaddr

LOG = logging.getLogger(__name__)


class BigipSelfIpManager(object):
    """ Class for managing BIG-IP selfips """

    def __init__(self, driver, bigip_l2_manager, l3_binding):
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager
        self.l3_binding = l3_binding

    def assure_bigip_selfip(self, bigip, service, subnetinfo):
        """ Create selfip on the BIG-IP """
        network = subnetinfo['network']
        if not network:
            LOG.error(_('Attempted to create selfip and snats'
                        ' for network with no id... skipping.'))
            return
        subnet = subnetinfo['subnet']

        tenant_id = service['pool']['tenant_id']
        # If we have already assured this subnet.. return.
        # Note this cache is periodically cleared in order to
        # force assurance that the configuration is present.
        if tenant_id in bigip.assured_tenant_snat_subnets and \
                subnet['id'] in bigip.assured_tenant_snat_subnets[tenant_id]:
            return

        selfip_address = self._get_bigip_selfip_address(bigip, subnet)
        selfip_address += '%' + str(network['route_domain_id'])

        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = service['pool']['tenant_id']

        (network_name, preserve_network_name) = \
            self.bigip_l2_manager.get_network_name(bigip, network)

        bigip.selfip.create(
            name="local-" + bigip.device_name + "-" + subnet['id'],
            ip_address=selfip_address,
            netmask=netaddr.IPNetwork(subnet['cidr']).netmask,
            vlan_name=network_name,
            floating=False,
            folder=network_folder,
            preserve_vlan_name=preserve_network_name)
        # TO DO: we need to only bind the local SelfIP to the
        # local device... not treat it as if it was floating
        if self.l3_binding:
            self.l3_binding.bind_address(subnet_id=subnet['id'],
                                         ip_address=selfip_address)

    def _get_bigip_selfip_address(self, bigip, subnet):
        """ Get ip address for selfip to use on BIG-IP """
        selfip_name = "local-" + bigip.device_name + "-" + subnet['id']
        ports = self.driver.plugin_rpc.get_port_by_name(port_name=selfip_name)
        if len(ports) > 0:
            port = ports[0]
        else:
            port = self.driver.plugin_rpc.create_port_on_subnet(
                subnet_id=subnet['id'],
                mac_address=None,
                name=selfip_name,
                fixed_address_count=1)
        return port['fixed_ips'][0]['ip_address']

    def assure_gateway_on_subnet(self, bigip, subnetinfo, traffic_group):
        """ called for every bigip only in replication mode.
            otherwise called once """
        subnet = subnetinfo['subnet']
        if subnet['id'] in bigip.assured_gateway_subnets:
            return

        network = subnetinfo['network']
        (network_name, preserve_network_name) = \
            self.bigip_l2_manager.get_network_name(bigip, network)

        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
            network_name = '/Common/' + network_name
        else:
            network_folder = subnet['tenant_id']

        # Select a traffic group for the floating SelfIP
        floating_selfip_name = "gw-" + subnet['id']
        netmask = netaddr.IPNetwork(subnet['cidr']).netmask

        bigip.selfip.create(name=floating_selfip_name,
                            ip_address=subnet['gateway_ip'],
                            netmask=netmask,
                            vlan_name=network_name,
                            floating=True,
                            traffic_group=traffic_group,
                            folder=network_folder,
                            preserve_vlan_name=preserve_network_name)

        if self.l3_binding:
            self.l3_binding.bind_address(subnet_id=subnet['id'],
                                         ip_address=subnet['gateway_ip'])

        # Setup a wild card ip forwarding virtual service for this subnet
        gw_name = "gw-" + subnet['id']
        bigip.virtual_server.create_ip_forwarder(
            name=gw_name, ip_address='0.0.0.0',
            mask='0.0.0.0',
            vlan_name=network_name,
            traffic_group=traffic_group,
            folder=network_folder,
            preserve_vlan_name=preserve_network_name)

        # Setup the IP forwarding virtual server to use the Self IPs
        # as the forwarding SNAT addresses
        bigip.virtual_server.set_snat_automap(name=gw_name,
                                              folder=network_folder)
        bigip.assured_gateway_subnets.append(subnet['id'])

    def delete_gateway_on_subnet(self, bigip, subnetinfo):
        """ called for every bigip only in replication mode.
            otherwise called once """
        network = subnetinfo['network']
        if not network:
            LOG.error(_('Attempted to delete default gateway'
                        ' for network with no id... skipping.'))
            return
        subnet = subnetinfo['subnet']
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = subnet['tenant_id']

        floating_selfip_name = "gw-" + subnet['id']
        if self.driver.conf.f5_populate_static_arp:
            bigip.arp.delete_by_subnet(subnet=subnetinfo['subnet']['cidr'],
                                       mask=None,
                                       folder=network_folder)
        bigip.selfip.delete(name=floating_selfip_name,
                            folder=network_folder)

        if self.l3_binding:
            self.l3_binding.unbind_address(subnet_id=subnet['id'],
                                           ip_address=subnet['gateway_ip'])

        gw_name = "gw-" + subnet['id']
        bigip.virtual_server.delete(name=gw_name,
                                    folder=network_folder)

        if subnet['id'] in bigip.assured_gateway_subnets:
            bigip.assured_gateway_subnets.remove(subnet['id'])
        return gw_name

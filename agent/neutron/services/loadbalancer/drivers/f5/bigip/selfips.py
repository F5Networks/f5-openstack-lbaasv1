""" Classes and routines for managing BIG-IP self-ips """
from neutron.openstack.common import log as logging
import netaddr

LOG = logging.getLogger(__name__)


class BigipSelfIpManager(object):
    """ Class for managing BIG-IP selfips """

    def __init__(self, driver, bigip_l2_manager):
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager

    def assure_bigip_selfip(self, bigip, service, subnetinfo):
        """ Create selfip on the BIG-IP """
        network = subnetinfo['network']
        if not network:
            LOG.error(_('Attempted to create selfip and snats'
                        ' for network with no id... skipping.'))
            return
        subnet = subnetinfo['subnet']
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        pool = service['pool']
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = pool['tenant_id']

        (network_name, preserve_network_name) = \
            self.bigip_l2_manager.get_network_name(bigip, network)

        bigip.selfip.create(
            name="local-" + bigip.device_name + "-" + subnet['id'],
            ip_address=self._get_bigip_selfip_address(bigip, subnet),
            netmask=netaddr.IPNetwork(subnet['cidr']).netmask,
            vlan_name=network_name,
            floating=False,
            folder=network_folder,
            preserve_vlan_name=preserve_network_name)

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

    def assure_gateway_on_subnet(self, bigip, subnetinfo):
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
        vip_tg = self.driver.get_least_gw_traffic_group()

        bigip.selfip.create(name=floating_selfip_name,
                            ip_address=subnet['gateway_ip'],
                            netmask=netmask,
                            vlan_name=network_name,
                            floating=True,
                            traffic_group=vip_tg,
                            folder=network_folder,
                            preserve_vlan_name=preserve_network_name)

        # Get the actual traffic group if the Self IP already existed
        vip_tg = bigip.selfip.get_traffic_group(name=floating_selfip_name,
                                                folder=subnet['tenant_id'])

        # Setup a wild card ip forwarding virtual service for this subnet
        gw_name = "gw-" + subnet['id']
        bigip.virtual_server.create_ip_forwarder(
            name=gw_name, ip_address='0.0.0.0',
            mask='0.0.0.0',
            vlan_name=network_name,
            traffic_group=vip_tg,
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

        gw_name = "gw-" + subnet['id']
        bigip.virtual_server.delete(name=gw_name,
                                    folder=network_folder)

        if subnet['id'] in bigip.assured_gateway_subnets:
            bigip.assured_gateway_subnets.remove(subnet['id'])
        return gw_name

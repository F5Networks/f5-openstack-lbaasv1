""" Classes and routing for configuring snats
    and snat addresses on big-ips """
from neutron.openstack.common import log as logging
import os
from time import time

LOG = logging.getLogger(__name__)


class BigipSnatManager(object):
    """ Class for managing BIG-IP snats """

    def __init__(self, driver, bigip_l2_manager):
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager

    def get_snat_addrs(self, subnetinfo, tenant_id):
        """ Get the ip addresses for snat depending on HA mode """
        if self.driver.conf.f5_ha_type == 'standalone':
            return self._get_snat_addrs_standalone(subnetinfo)
        elif self.driver.conf.f5_ha_type == 'pair':
            return self._get_snat_addrs_pair(subnetinfo)
        elif self.driver.conf.f5_ha_type == 'scalen':
            return self._get_snat_addrs_scalen(subnetinfo, tenant_id)

    def _get_snat_addrs_standalone(self, subnetinfo):
        """ Get the ip addresses for snat in standalone HA mode """
        subnet = subnetinfo['subnet']
        snat_addrs = []

        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)
            ports = self.driver.plugin_rpc.get_port_by_name(
                port_name=index_snat_name)
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.driver.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            snat_addrs.append(ip_address)
        return snat_addrs

    def _get_snat_addrs_pair(self, subnetinfo):
        """ Get the ip addresses for snat in pair HA mode """
        subnet = subnetinfo['subnet']

        snat_addrs = []
        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)
            start_time = time()
            ports = self.driver.plugin_rpc.get_port_by_name(
                port_name=index_snat_name)
            LOG.debug("        assure_snat:"
                      "get_port_by_name took %.5f secs" %
                      (time() - start_time))
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.driver.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            snat_addrs.append(ip_address)
        return snat_addrs

    def _get_snat_addrs_scalen(self, subnetinfo, tenant_id):
        """ Get the ip addresses for snat in scalen HA mode """
        subnet = subnetinfo['subnet']
        snat_addrs = []

        traffic_group = self.driver.tenant_to_traffic_group(tenant_id)
        base_traffic_group = os.path.basename(traffic_group)
        snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)

            ports = self.driver.plugin_rpc.get_port_by_name(
                port_name=index_snat_name)
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.driver.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            snat_addrs.append(ip_address)
        return snat_addrs

    def assure_bigip_snats(self, bigip, subnetinfo, snat_addrs, tenant_id):
        """ Ensure Snat Addresses are configured on a bigip.
            Called for every bigip only in replication mode.
            otherwise called once and synced. """
        network = subnetinfo['network']

        snat_info = {}
        if self.bigip_l2_manager.is_common_network(network):
            snat_info['network_folder'] = 'Common'
        else:
            snat_info['network_folder'] = tenant_id
        snat_info['pool_name'] = tenant_id
        snat_info['pool_folder'] = tenant_id
        snat_info['addrs'] = snat_addrs

        if self.driver.conf.f5_ha_type == 'standalone':
            self._assure_snats_standalone(bigip, subnetinfo, snat_info)
        elif self.driver.conf.f5_ha_type == 'pair':
            self._assure_snats_pair(bigip, subnetinfo, snat_info)
        elif self.driver.conf.f5_ha_type == 'scalen':
            self._assure_snats_scalen(bigip, subnetinfo, snat_info, tenant_id)

    def _assure_snats_standalone(self, bigip, subnetinfo, snat_info):
        """ Configure the ip addresses for snat in standalone HA mode """
        network = subnetinfo['network']
        subnet = subnetinfo['subnet']
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        # Create SNATs on traffic-group-local-only
        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            ip_address = snat_info['addrs'][i]
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            tglo = '/Common/traffic-group-local-only'
            bigip.snat.create(name=index_snat_name,
                              ip_address=ip_address,
                              traffic_group=tglo,
                              snat_pool_name=snat_info['pool_name'],
                              folder=snat_info['network_folder'],
                              snat_pool_folder=snat_info['pool_folder'])

        bigip.assured_snat_subnets.append(subnet['id'])

    def _assure_snats_pair(self, bigip, subnetinfo, snat_info):
        """ Configure the ip addresses for snat in pair HA mode """
        network = subnetinfo['network']
        subnet = subnetinfo['subnet']
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            ip_address = snat_info['addrs'][i]
            if self.bigip_l2_manager.is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            bigip.snat.create(name=index_snat_name,
                              ip_address=ip_address,
                              traffic_group='traffic-group-1',
                              snat_pool_name=snat_info['pool_name'],
                              folder=snat_info['network_folder'],
                              snat_pool_folder=snat_info['pool_folder'])

        bigip.assured_snat_subnets.append(subnet['id'])

    def _assure_snats_scalen(self, bigip, subnetinfo, snat_info, tenant_id):
        """ Configure the ip addresses for snat in scalen HA mode """
        network = subnetinfo['network']
        subnet = subnetinfo['subnet']
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        traffic_group = self.driver.tenant_to_traffic_group(tenant_id)
        base_traffic_group = os.path.basename(traffic_group)
        snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            ip_address = snat_info['addrs'][i]
            index_snat_name = snat_name + "_" + str(i)

            if self.bigip_l2_manager.is_common_network(network):
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name

            bigip.snat.create(
                name=index_snat_name,
                ip_address=ip_address,
                traffic_group=traffic_group,
                snat_pool_name=snat_info['pool_name'],
                folder=snat_info['network_folder'],
                snat_pool_folder=snat_info['pool_folder'])

        bigip.assured_snat_subnets.append(subnet['id'])

    def delete_bigip_snats(self, bigip, subnetinfo, tenant_id):
        """ Assure shared snat configuration (which syncs) is deleted
            Called for every bigip only in replication mode,
            otherwise called once.
        """
        if not subnetinfo['network']:
            LOG.error(_('Attempted to delete selfip and snats'
                        ' for missing network ... skipping.'))
            return set()

        deleted_names = set()
        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        if self.driver.conf.f5_snat_addresses_per_subnet > 0:
            # failover mode dictates SNAT placement on traffic-groups
            if self.driver.conf.f5_ha_type == 'standalone':
                deleted_names = self._delete_bigip_snats_standalone(
                    bigip, subnetinfo, tenant_id)
            elif self.driver.conf.f5_ha_type == 'pair':
                deleted_names = self._delete_bigip_snats_pair(
                    bigip, subnetinfo, tenant_id)
            elif self.driver.conf.f5_ha_type == 'scalen':
                deleted_names = self._delete_bigip_snats_scalen(
                    bigip, subnetinfo, tenant_id)

        subnet = subnetinfo['subnet']
        if subnet['id'] in bigip.assured_snat_subnets:
            bigip.assured_snat_subnets.remove(subnet['id'])

        return deleted_names

    def _delete_bigip_snats_standalone(self, bigip, subnetinfo, tenant_id):
        """ Assure snats deleted in standalone mode """
        network = subnetinfo['network']
        subnet = subnetinfo['subnet']
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = tenant_id
        snat_pool_name = tenant_id

        deleted_names = set()
        # Delete SNATs on traffic-group-local-only
        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                tmos_snat_name = '/Common/' + index_snat_name
            else:
                tmos_snat_name = index_snat_name
            bigip.snat.remove_from_pool(
                name=snat_pool_name,
                member_name=tmos_snat_name,
                folder=tenant_id)
            if bigip.snat.delete(
                    name=tmos_snat_name,
                    folder=network_folder,
                    snat_pool_folder=tenant_id):
                # Only if it still exists and can be
                # deleted because it is not in use can
                # we safely delete the neutron port
                deleted_names.add(index_snat_name)
        return deleted_names

    def _delete_bigip_snats_pair(self, bigip, subnetinfo, tenant_id):
        """ Assure snats deleted in HA Pair mode """
        network = subnetinfo['network']
        subnet = subnetinfo['subnet']
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = tenant_id
        snat_pool_name = tenant_id

        deleted_names = set()
        # Delete SNATs on traffic-group-1
        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                tmos_snat_name = '/Common/' + index_snat_name
            else:
                tmos_snat_name = index_snat_name
            bigip.snat.remove_from_pool(
                name=snat_pool_name,
                member_name=tmos_snat_name,
                folder=tenant_id)
            if bigip.snat.delete(
                    name=tmos_snat_name,
                    folder=network_folder,
                    snat_pool_folder=tenant_id):
                # Only if it still exists and can be
                # deleted because it is not in use can
                # we safely delete the neutron port
                deleted_names.add(index_snat_name)
        return deleted_names

    def _delete_bigip_snats_scalen(self, bigip, subnetinfo, tenant_id):
        """ Assure snats deleted in scalen mode """
        network = subnetinfo['network']
        subnet = subnetinfo['subnet']
        if self.bigip_l2_manager.is_common_network(network):
            network_folder = 'Common'
        else:
            network_folder = tenant_id
        snat_pool_name = tenant_id

        deleted_names = set()

        # Delete SNATs on all provider defined traffic groups
        traffic_group = self.driver.tenant_to_traffic_group(tenant_id)
        base_traffic_group = os.path.basename(traffic_group)
        snat_name = "snat-" + base_traffic_group + "-" + subnet['id']
        for i in range(self.driver.conf.f5_snat_addresses_per_subnet):
            index_snat_name = snat_name + "_" + str(i)
            if self.bigip_l2_manager.is_common_network(network):
                tmos_snat_name = "/Common/" + index_snat_name
            else:
                tmos_snat_name = index_snat_name
            bigip.snat.remove_from_pool(
                name=snat_pool_name,
                member_name=tmos_snat_name,
                folder=tenant_id)
            if bigip.snat.delete(
                    name=tmos_snat_name,
                    folder=network_folder,
                    snat_pool_folder=tenant_id):
                # Only if it still exists and can be
                # deleted because it is not in use can
                # we safely delete the neutron port
                deleted_names.add(index_snat_name)
        return deleted_names

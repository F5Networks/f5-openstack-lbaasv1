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
from time import time

from neutron.services.loadbalancer.drivers.f5.bigip.lbaas \
    import LBaaSBuilder

from neutron.services.loadbalancer.drivers.f5.bigip.pools \
    import BigipPoolManager
from neutron.services.loadbalancer.drivers.f5.bigip.vips \
    import BigipVipManager

LOG = logging.getLogger(__name__)


class LBaaSBuilderDirect(LBaaSBuilder):
    """F5 LBaaS Driver for BIG-IP using iControl
       to create objects (vips, pools) directly,
       (rather than using an iApp - LBaaSBuilderiApp)."""

    def __init__(self, conf, driver, bigip_l2_manager=None):
        super(LBaaSBuilderDirect, self).__init__(
            conf, driver, bigip_l2_manager)
        self.bigip_pool_manager = BigipPoolManager(self, self.bigip_l2_manager)
        self.bigip_vip_manager = BigipVipManager(self, self.bigip_l2_manager)

    def assure_service(self, service, traffic_group):
        """ Assure that the service is configured """
        if not service['pool']:
            return

        bigips = self.driver.get_config_bigips()
        all_subnet_hints = {}
        for prep_bigip in bigips:
            # check_for_delete_subnets:
            #     keep track of which subnets we should check to delete
            #     for a deleted vip or member
            # do_not_delete_subnets:
            #     If we add an IP to a subnet we must not delete the subnet
            all_subnet_hints[prep_bigip.device_name] = \
                {'check_for_delete_subnets': {},
                 'do_not_delete_subnets': []}

        self._check_monitor_delete(service)

        start_time = time()
        self._assure_pool_create(service['pool'])
        LOG.debug("    _assure_pool_create took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_pool_monitors(service)
        LOG.debug("    _assure_pool_monitors took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_members(service, all_subnet_hints)
        LOG.debug("    _assure_members took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_vip(service, traffic_group, all_subnet_hints)
        LOG.debug("    _assure_vip took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self._assure_pool_delete(service)
        LOG.debug("    _assure_pool_delete took %.5f secs" %
                  (time() - start_time))

        return all_subnet_hints

    def _assure_pool_create(self, pool):
        """ Provision Pool - Create/Update """
        # Service Layer (Shared Config)
        for bigip in self.driver.get_config_bigips():
            self.bigip_pool_manager.assure_bigip_pool_create(bigip, pool)

    def _assure_pool_monitors(self, service):
        """
            Provision Health Monitors - Create/Update
        """
        # Service Layer (Shared Config)
        for bigip in self.driver.get_config_bigips():
            self.bigip_pool_manager.assure_bigip_pool_monitors(bigip, service)

    def _assure_members(self, service, all_subnet_hints):
        """
            Provision Members - Create/Update
        """
        # Service Layer (Shared Config)
        for bigip in self.driver.get_config_bigips():
            subnet_hints = all_subnet_hints[bigip.device_name]
            self.bigip_pool_manager.assure_bigip_members(
                bigip, service, subnet_hints)

        # avoids race condition:
        # deletion of pool member objects must sync before we
        # remove the selfip from the peer bigips.
        self.driver.sync_if_clustered()

    def _assure_vip(self, service, traffic_group, all_subnet_hints):
        """ Ensure the vip is on all bigips. """
        vip = service['vip']
        if 'id' not in vip:
            return

        bigips = self.driver.get_config_bigips()
        for bigip in bigips:
            subnet_hints = all_subnet_hints[bigip.device_name]
            subnet = vip['subnet']

            if vip['status'] == plugin_const.PENDING_CREATE or \
               vip['status'] == plugin_const.PENDING_UPDATE:
                self.bigip_vip_manager.assure_bigip_create_vip(
                    bigip, service, traffic_group)
                if subnet and subnet['id'] in \
                        subnet_hints['check_for_delete_subnets']:
                    del subnet_hints['check_for_delete_subnets'][subnet['id']]
                if subnet and subnet['id'] not in \
                        subnet_hints['do_not_delete_subnets']:
                    subnet_hints['do_not_delete_subnets'].append(subnet['id'])

            elif vip['status'] == plugin_const.PENDING_DELETE:
                self.bigip_vip_manager.assure_bigip_delete_vip(bigip, service)
                if subnet and subnet['id'] not in \
                        subnet_hints['do_not_delete_subnets']:
                    subnet_hints['check_for_delete_subnets'][subnet['id']] = \
                        {'network': vip['network'],
                         'subnet': subnet,
                         'is_for_member': False}

        # avoids race condition:
        # deletion of vip address must sync before we
        # remove the selfip from the peer bigips.
        self.driver.sync_if_clustered()

    def _assure_pool_delete(self, service):
        """ Assure pool is deleted from big-ip """
        if service['pool']['status'] != plugin_const.PENDING_DELETE:
            return

        # Service Layer (Shared Config)
        for bigip in self.driver.get_config_bigips():
            self.bigip_pool_manager.assure_bigip_pool_delete(bigip, service)

    def _check_monitor_delete(self, service):
        """If the pool is being deleted, then delete related objects"""
        if service['pool']['status'] == plugin_const.PENDING_DELETE:
            # Everything needs to be go with the pool, so overwrite
            # service state to appropriately remove all elements
            service['vip']['status'] = plugin_const.PENDING_DELETE
            for member in service['members']:
                member['status'] = plugin_const.PENDING_DELETE
            for monitor in service['pool']['health_monitors_status']:
                monitor['status'] = plugin_const.PENDING_DELETE

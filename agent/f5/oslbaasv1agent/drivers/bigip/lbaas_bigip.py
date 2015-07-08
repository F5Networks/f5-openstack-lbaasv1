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
try:
    from neutron.openstack.common import log as logging
except ImportError:
    from oslo_log import log as logging
from neutron.plugins.common import constants as plugin_const
from time import time

from f5.oslbaasv1agent.drivers.bigip.lbaas import \
    LBaaSBuilder, LBaaSBuilderIApp, get_tenant_service_var
from f5.oslbaasv1agent.drivers.bigip.pools import \
    BigipPoolManager
from f5.oslbaasv1agent.drivers.bigip.vips import \
    BigipVipManager

from f5.bigip.interfaces import prefixed

LOG = logging.getLogger(__name__)


class LBaaSBuilderBigipObjects(LBaaSBuilder):
    """F5 LBaaS Driver using iControl for BIG-IP to
       create objects (vips, pools) - not using an iApp. """

    def __init__(self, conf, driver, bigip_l2_manager=None, l3_binding=None):
        super(LBaaSBuilderBigipObjects, self).__init__(conf, driver)
        self.bigip_l2_manager = bigip_l2_manager
        self.l3_binding = l3_binding
        self.bigip_pool_manager = BigipPoolManager(self, self.bigip_l2_manager)
        self.bigip_vip_manager = BigipVipManager(self,
                                                 self.bigip_l2_manager,
                                                 self.l3_binding)

    def assure_service(self, service, traffic_group, all_subnet_hints):
        """ Assure that the service is configured """
        if not service['pool']:
            return

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


class LBaaSBuilderBigipIApp(LBaaSBuilderIApp):
    """ LBaaS Builder for BIG-IP using iApp """

    _F5_LBAAS_IAPP_TEMPLATE_NAME = "f5.lbaas"

    def __init__(self, conf, driver, bigip_l2_manager=None):
        super(LBaaSBuilderBigipIApp, self).__init__(conf, driver)
        self.bigip_l2_manager = bigip_l2_manager
        self.varkey = 'variables'

    def assure_service(self, service, traffic_group, all_subnet_hints):
        LOG.debug("    assure_service 1")
        for bigip in self.driver.get_config_bigips():
            subnet_hints = all_subnet_hints[bigip.device_name]
            self.assure_bigip_service(bigip, service, subnet_hints)

    def assure_bigip_service(self, bigip, service, subnet_hints):
        """ Configure the service """
        pool = service['pool']
        project_id = pool['tenant_id']
        tenant_name = self.get_bigip_tenant_name(project_id)

        tenant_service = self.generate_bigip_service(service)
        LOG.debug("    assure_bigip_service tenant_service: %s"
                  % str(tenant_service))

        pool_id = pool['id']
        service_name = self.get_bigip_service_name(pool_id)
        existing_service = bigip.iapp.get_service(
            service_name, folder=tenant_name)

        LOG.debug("    assure_bigip_service existing_service: %s"
                  % str(existing_service))
        if pool['status'] != plugin_const.PENDING_DELETE:
            if existing_service:

                LOG.debug("    assure_bigip_service existing service: %s"
                          % str(existing_service))
                tenant_service['generation'] = existing_service['generation']
                tenant_service['selfLink'] = existing_service['selfLink']
                tenant_service['execute-action'] = 'definition'

                LOG.debug("    assure_bigip_service updating service: %s"
                          % str(tenant_service))
                bigip.iapp.update_service(
                    service_name, folder=tenant_name, service=tenant_service)
                LOG.debug("    assure_bigip_service updated service.")
            else:
                LOG.debug("    assure_bigip_service creating service: %s"
                          % str(tenant_service))
                bigip.iapp.create_service(
                    name=service_name, folder=tenant_name,
                    service=tenant_service)
        elif existing_service:
            bigip.iapp.delete_service(service_name, folder=tenant_name)
        # try to delete nodes for deleted pool members
        bigip.pool.delete_all_nodes(folder=tenant_name)
        bigip.pool.delete_all_nodes(folder='/Common')
        # need to optimize this
        subnet_hints['check_for_delete_subnets'] = \
            self._get_all_subnets(service)

    @staticmethod
    def get_bigip_tenant_name(project_id):
        """ Generate tenant name """
        return project_id

    @staticmethod
    def get_bigip_service_name(pool_id):
        """ Generate service name """
        return prefixed(pool_id)

    def generate_bigip_service(self, os_service):
        """ Generate tenant service """
        tenant_service = {}

        pool_id = os_service['pool']['id']

        # {
        #     ...,
        #     "name": "someServiceName",
        #     ...
        # }
        tenant_service['name'] = self.get_bigip_service_name(pool_id)

        tenant_service['template'] = '/Common/%s' \
            % self._F5_LBAAS_IAPP_TEMPLATE_NAME

        # {
        #     ...,
        #     "vars":
        #         [
        #             pool vars, VIP vars, app stats vars
        #         ],
        #     ...
        # }
        tenant_service['variables'] = []

        self.fill_in_pool_info(tenant_service, os_service)
        self.fill_in_vip_info(tenant_service, os_service)
        tenant_service['variables'].append(
            get_tenant_service_var('app_stats', 'enabled'))

        #     "tables":
        #         [
        #             pool members
        #         ],
        #     ...
        # }
        tenant_service['tables'] = []

        self.fill_in_pool_members_table(tenant_service, os_service, True)

        return tenant_service

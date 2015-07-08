""" Tenants Manager """
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
from f5.bigip import exceptions as f5ex
from eventlet import greenthread
import logging as std_logging

LOG = logging.getLogger(__name__)


class BigipTenantManager(object):
    """Create network connectivity for a bigip """
    def __init__(self, conf, driver):
        self.conf = conf
        self.driver = driver

    def assure_tenant_created(self, service):
        """ Create tenant partition. """
        tenant_id = service['pool']['tenant_id']
        traffic_group = self.driver._service_to_traffic_group(service)
        traffic_group = '/Common/' + traffic_group

        # create tenant folder
        for bigip in self.driver.get_config_bigips():
            folder = bigip.decorate_folder(tenant_id)
            if not bigip.system.folder_exists(folder):
                bigip.system.create_folder(
                    folder, change_to=True, traffic_group=traffic_group)

        # folder must sync before route domains are created.
        self.driver.sync_if_clustered()

        # create tenant route domain
        if self.conf.use_namespaces:
            for bigip in self.driver.get_all_bigips():
                folder = bigip.decorate_folder(tenant_id)
                if not bigip.route.domain_exists(folder):
                    bigip.route.create_domain(
                        folder, self.conf.f5_route_domain_strictness)

    def assure_tenant_cleanup(self, service, all_subnet_hints):
        """ Delete tenant partition.
            Called for every bigip only in replication mode,
            otherwise called once.
        """
        for bigip in self.driver.get_config_bigips():
            subnet_hints = all_subnet_hints[bigip.device_name]
            self._assure_bigip_tenant_cleanup(bigip, service, subnet_hints)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_bigip_tenant_cleanup(self, bigip, service, subnet_hints):
        """ if something was deleted check whether to do
            domain+folder teardown """
        tenant_id = service['pool']['tenant_id']
        if service['pool']['status'] == plugin_const.PENDING_DELETE or \
                len(subnet_hints['check_for_delete_subnets']) > 0:
            existing_monitors = bigip.monitor.get_monitors(folder=tenant_id)
            existing_pools = bigip.pool.get_pools(folder=tenant_id)
            existing_vips = bigip.virtual_server.get_virtual_service_insertion(
                folder=tenant_id)

            if not (existing_monitors or existing_pools or existing_vips):
                if self.conf.f5_sync_mode == 'replication':
                    self._remove_tenant_replication_mode(bigip, tenant_id)
                else:
                    self._remove_tenant_autosync_mode(bigip, tenant_id)

    def _remove_tenant_replication_mode(self, bigip, tenant_id):
        """ Remove tenant in replication sync-mode """
        for domain_name in bigip.route.get_domain_names(folder=tenant_id):
            bigip.route.delete_domain(folder=tenant_id, name=domain_name)
        sudslog = std_logging.getLogger('suds.client')
        sudslog.setLevel(std_logging.FATAL)
        bigip.system.force_root_folder()
        sudslog.setLevel(std_logging.ERROR)
        try:
            bigip.system.delete_folder(folder=bigip.decorate_folder(tenant_id))
        except f5ex.SystemDeleteException:
            bigip.system.purge_folder_contents(
                folder=bigip.decorate_folder(tenant_id))
            bigip.system.delete_folder(folder=bigip.decorate_folder(tenant_id))

    def _remove_tenant_autosync_mode(self, bigip, tenant_id):
        """ Remove tenant in autosync sync-mode """
        # all domains must be gone before we attempt to delete
        # the folder or it won't delete due to not being empty
        for set_bigip in self.driver.get_all_bigips():
            set_bigip.route.delete_domain(folder=tenant_id)
            sudslog = std_logging.getLogger('suds.client')
            sudslog.setLevel(std_logging.FATAL)
            set_bigip.system.force_root_folder()
            sudslog.setLevel(std_logging.ERROR)

        # we need to ensure that the following folder deletion
        # is clearly the last change that needs to be synced.
        self.driver.sync_if_clustered()
        greenthread.sleep(5)
        try:
            bigip.system.delete_folder(folder=bigip.decorate_folder(tenant_id))
        except f5ex.SystemDeleteException:
            bigip.system.purge_folder_contents(
                folder=bigip.decorate_folder(tenant_id))
            bigip.system.delete_folder(folder=bigip.decorate_folder(tenant_id))

        # Need to make sure this folder delete syncs before
        # something else runs and changes the current folder to
        # the folder being deleted which will cause big problems.
        self.driver.sync_if_clustered()

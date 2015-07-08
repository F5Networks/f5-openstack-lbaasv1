""" Module for configuring LBaaS on BIG-IP using an iApp via BIG-IQ """
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

# pylint: disable=broad-except
try:
    from neutron.openstack.common import log as logging
except ImportError:
    from oslo_log import log as logging
from neutron.common.exceptions import InvalidConfigurationOption
from neutron.plugins.common import constants as plugin_const
import novaclient.v1_1.client as nvclient
import neutronclient.v2_0.client as neclient

from f5.bigiq import bigiq as bigiq_interface
from f5.oslbaasv1agent.drivers.bigip.lbaas import \
    LBaaSBuilderIApp, get_tenant_service_var

import string
import uuid
import threading
import time

LOG = logging.getLogger(__name__)


class LBaaSBuilderBigiqIApp(LBaaSBuilderIApp):
    """Makes REST calls against a BIG-IQ to support OpenStack LBaaS

    This class is used as the interface between OpenStack and a BIG-IQ.
    It contains the logic to take any OpenStack LBaaS request/work and
    make the appropriate REST calls to a BIG-IQ which in turn will
    configure any BIG-IPs it is managing as necessary to support load
    balancing.
    """

    _F5_LBAAS_IAPP_TEMPLATE_NAME = "f5.lbaas"

    _MANAGED_DEVICE_KIND = 'shared:resolver:device-groups:' \
        'restdeviceresolverdevicestate'

    _LBAAS_PROVIDER_TEMPLATE_NAME = "OpenStack-LBaaS-Template"

    def __init__(self, conf, driver):
        super(LBaaSBuilderBigiqIApp, self).__init__(conf, driver)

        self._validate_required_config()

        # Set the RPC to the plugin to None so we don't end up
        # trying to access the attribute if we haven't initialized
        # the RPC instance yet -- gets set in the agent manager
        self.agent_id = None
        self.driver_config = {}

        self._connectors_by_id = {}
        self._connectors_by_name = {}

        self._connectors_lock = threading.Lock()

        self._bigiq = None
        self._init_connection()
        self.varkey = 'vars'

    def _validate_required_config(self):
        """ Validate Configuration """
        if not self.conf.bigiq_hostname:
            raise InvalidConfigurationOption(
                opt_name='bigiq_hostname',
                opt_value='Valid hostname')

        if not self.conf.bigiq_admin_username:
            raise InvalidConfigurationOption(
                opt_name='bigiq_admin_username',
                opt_value='Valid username')

        if not self.conf.bigiq_admin_password:
            raise InvalidConfigurationOption(
                opt_name='bigiq_admin_password',
                opt_value='Valid password')

        if not self.conf.openstack_keystone_uri:
            raise InvalidConfigurationOption(
                opt_name='openstack_keystone_uri',
                opt_value='Valid URI to the Keystone service')

        if not self.conf.openstack_admin_username:
            raise InvalidConfigurationOption(
                opt_name='openstack_admin_username',
                opt_value='Valid username')

        if not self.conf.openstack_admin_password:
            raise InvalidConfigurationOption(
                opt_name='openstack_admin_password',
                opt_value='Valid password')

        if not self.conf.bigip_management_username:
            raise InvalidConfigurationOption(
                opt_name='bigip_management_username',
                opt_value='Valid username')

        if not self.conf.bigip_management_password:
            raise InvalidConfigurationOption(
                opt_name='bigip_management_password',
                opt_value='Valid password')

    def _init_connection(self):
        """ Create connection to bigiq """
        self._bigiq = bigiq_interface.BIGIQ(
            self.conf.bigiq_hostname, self.conf.bigiq_admin_username,
            self.conf.bigiq_admin_password)

        # Generate an ID for this driver based on the hostname of the
        # BIG-IQ we are communicating with. This will be used later
        # to generate an ID for machine hosting this agent.
        self.agent_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS, self.conf.bigiq_hostname))

        self.driver_config = {}
        self.driver_config['bigiq_endpoints'] = {self.conf.bigiq_hostname: {}}

        self._discover_openstack_connectors(self._bigiq)

    def _discover_openstack_connectors(self, bigiq):
        """ Find connectors for openstack """
        self._connectors_by_id = {}
        self._connectors_by_name = {}

        connectors = bigiq.get_cloud_connectors(
            bigiq_interface.BIGIQ.CC_TYPE_OPENSTACK)

        for connector in connectors:
            if 'connectorId' in connector and 'name' in connector:
                LOG.info(_("Mapping a discovered connector with a"
                           " 'connectorId' of '%s' and a 'name' of '%s'"
                           % (connector['connectorId'], connector['name'])))

                self._connectors_by_id[connector['connectorId']] = connector
                self._connectors_by_name[connector['name']] = connector
            else:
                if 'connectorId' not in connector and 'name' not in connector:
                    LOG.info(_("Can't map a connector because it doesn't"
                               " have the key named 'connectorId' and the "
                               "key named 'name'"))
                elif 'connectorId' not in connector:
                    LOG.info(_("Can't map the connector with the 'name' of "
                               "'%s' because it doesn't have a key named "
                               " 'connectorId'" % connector['name']))
                else:
                    LOG.info(_("Can't map the connector with the 'connectorId'"
                               " of '%s' because it doesn't have a key named "
                               "'name'" % connector['connectorId']))

    def assure_service(self, service, traffic_group, all_subnet_hints):
        """ Configure service on bigip """
        self._assure_connector_and_tenant(service)
        self._assure_managed_devices(service)
        self._assure_provider_template()
        self._assure_tenant_service(service)

    def exists(self, service):
        """ Does service exist? """
        # We are interested in catching an exception here when we
        # try to get a tenant service.
        # If we do get one we know that the tenant service doesn't exist.
        try:
            project_id = service['pool']['tenant_id']

            tenant_name = LBaaSBuilderBigiqIApp.get_bigiq_tenant_name(
                project_id)

            pool_id = service['pool']['id']

            service_name = LBaaSBuilderBigiqIApp.get_bigiq_service_name(
                pool_id)

            self._bigiq.get_tenant_service(tenant_name, service_name)

            return True
        except:
            return False

    def _assure_connector_and_tenant(self, service):
        """ Make sure bigiq connector and tenant exists """
        project_id = service['pool']['tenant_id']

        # The name of the OpenStack connectors will be based off of the
        # OpenStack project ID
        connector_name = LBaaSBuilderBigiqIApp._connector_name(
            project_id)

        # We use a lock here to avoid creating multiple connectors that have
        # the same 'name' data member. This lock is required because the
        # plugin identifies a connector off of its 'name' data member
        # where as BIG-IQ Cloud identifies a connector off of its 'connectorId'
        # data member (i.e. 'connectorId' is the primary and natural key).
        # If we don't lock here we have a race between when we decide to make
        # a connector for the first time and get the response from BIG-IQ and
        # map it vs. when we check if the connector is created again.
        with self._connectors_lock:
            if not self._connectors_by_name.get(connector_name):
                LOG.info(_("Didn't see a connector with the name of '%s' on "
                           "the BIG-IQ. Creating a new connector and tenant."
                           % connector_name))

                connector = LBaaSBuilderBigiqIApp._cloud_connector(
                    project_id,
                    self.conf.openstack_keystone_uri,
                    self.conf.openstack_admin_username,
                    self.conf.openstack_admin_password)

                connector = self._bigiq.post_cloud_connector(
                    bigiq_interface.BIGIQ.CC_TYPE_OPENSTACK,
                    connector)

                LOG.info(_("Mapping a created connector with a 'connectorId' "
                           "of '%s' and a 'name' of '%s'"
                           % (connector['connectorId'], connector['name'])))

                self._connectors_by_name[connector['name']] = connector
                self._connectors_by_id[connector['connectorId']] = connector

                tenant = LBaaSBuilderBigiqIApp._tenant(
                    project_id, connector['selfLink'])

                self._bigiq.post_tenant(tenant)
                LOG.debug("Sleeping until devices are discovered....")
                time.sleep(15)

    def _assure_managed_devices(self, service):
        """Ensures that any BIG-IP instances for the OpenStack project
           are managed OpenStack connectors periodically look for any BIG-IP
           instances in a project that it didn't previously know about.
           If it finds one it tries to manage the BIG-IP. The best that it
           can do is manage it as a cloud device that isn't fully discovered
           since its credentials weren't known.

           This method looks for those BIG-IPs that aren't fully managed yet
           and updates their credentials so that they become fully managed.

           :param dict service: A dictionary representing the OpenStack
           LBaaS service
        """
        project_id = service['pool']['tenant_id']

        connector = self._connectors_by_name[
            LBaaSBuilderBigiqIApp._connector_name(project_id)]

        # Get any BIG-IP instances associated with this OpenStack project
        # that we have tried to manage, whether they are truly managed or
        # not at this point.
        managed_devices = self._bigiq.get_related(
            LBaaSBuilderBigiqIApp._MANAGED_DEVICE_KIND,
            connector['selfLink'], True)
        LOG.debug("Got managed devices: %s" % str(managed_devices))

        undiscovered_devices = []

        # Find any devices that aren't truly managed. They will show up as
        # an undiscovered device and their autodiscover stat will say admin
        # credentials need to be provided to complete the discovery
        for managed_device in managed_devices:
            # Skip any null JSON values (None in Python) or empty JSON
            # objects (empty dictionary in JSON)
            if not managed_device:
                continue

            LOG.debug("process managed device: %s" % str(managed_device))
            if ('state' in managed_device and
                    managed_device['state'] == 'UNDISCOVERED' and
                    'selfLink' in managed_device and
                    managed_device['selfLink']):

                # We convert the 'selfLink' of the device into a remote URL
                # for the stats of it
                # as we are eventually going to check if it wasn't
                # discovered as it needs admin credentials
                managed_device['selfLink'] = string.replace(
                    managed_device['selfLink'] + '/stats',
                    'localhost', self._bigiq.hostname, 1)

                LOG.debug("found undiscovered device: %s"
                          % str(managed_device))
                undiscovered_devices.append(managed_device)

        for undiscovered_device in undiscovered_devices:
            get_result = self._bigiq.get(undiscovered_device['selfLink'])
            LOG.debug("bigiq.get(%s) returns %s"
                      % (undiscovered_device['selfLink'], str(get_result)))
            stats = get_result['entries']
            LOG.debug("stats: %s" % str(stats))

            npw = 'Please provide admin username and ' + \
                  'password to complete device discovery.'
            hsca = 'health.summary.cloud.autodiscover'

            if 'health.summary.cloud.autodiscover' in stats:
                if stats[hsca]['description'] == npw:
                    LOG.debug("posting cloud device at %s with %s %s" %
                              (undiscovered_device['address'],
                               self.conf.bigip_management_username,
                               self.conf.bigip_management_password)
                              )
                self._bigiq.post_cloud_device(
                    undiscovered_device['address'],
                    self.conf.bigip_management_username,
                    self.conf.bigip_management_password)
            else:
                LOG.debug(
                    "non matching description: [%s] [%s] " %
                    (stats['health.summary.cloud.autodiscover']['description'],
                     'Please provide admin username and password to '
                     'complete device discovery.'))

    def _assure_provider_template(self):
        """ Make sure template exists on bigiq """
        # We are interested in catching an exception here as it denotes that
        # there is not provider template if one is thrown.
        try:
            self._bigiq.get_provider_template(
                LBaaSBuilderBigiqIApp._LBAAS_PROVIDER_TEMPLATE_NAME)
        except:
            self._create_lbaas_provider_template()

    def _create_lbaas_provider_template(self):
        """ Create template """
        uri_path = bigiq_interface.BIGIQ.build_remote_uri_path(
            bigiq_interface.BIGIQ.NS_CM_URI_SEGMENT,
            bigiq_interface.BIGIQ.SUB_CM_NS_CLOUD_URI_SEGMENT,
            bigiq_interface.BIGIQ.CLOUD_TEMPLATES_URI_SEGMENT,
            bigiq_interface.BIGIQ.CLOUD_IAPP_URI_SEGMENTS,
            LBaaSBuilderBigiqIApp._F5_LBAAS_IAPP_TEMPLATE_NAME,
            bigiq_interface.BIGIQ.CLOUD_PROVIDERS_URI_SEGMENT)

        for attempt in range(1, 241):
            try:
                provider_template = self._bigiq.get_resource_example(uri_path)
                break
            except:
                LOG.debug("Resource template missing! Attempt %d" % attempt)
                time.sleep(5)

        # Lets change the default name of the template as well as add the
        # 'properties' data member and the 'cloudConnectorReference' property
        # since it doesn't come on the example provider template by default
        provider_template['templateName'] = \
            LBaaSBuilderBigiqIApp._LBAAS_PROVIDER_TEMPLATE_NAME

        # We will modify the vars and table vars so that each var is tenant
        # editable since we will be POSTing the serice as if we were tenants.
        # If we don't then we won't be able to correlate all of the data in
        # the OpenStack service model to a tenant service
        variables = provider_template['overrides']['vars']

        for variable in variables:
            if 'provider' in variable:
                variable['defaultValue'] = variable['provider']
                del variable['provider']

        tables = provider_template['overrides']['tables']

        for table in tables:
            columns = table['columns']

            for column in columns:
                if 'provider' in column:
                    column['defaultValue'] = column['provider']
                    del column['provider']

        provider_template['properties'] = []

        # We don't set a provider value for the cloud connector since we
        # don't have an OpenStack connector that supports multitenancy.
        # Because of this we are creating an OpenStack connector per
        # OpenStack project and thus will need to be able to select the
        # cloud connector each time we POST the template.
        cloud_connector_ref_property = {}
        cloud_connector_ref_property['id'] = 'cloudConnectorReference'
        cloud_connector_ref_property['displayName'] = 'Cloud connector'
        cloud_connector_ref_property['isRequired'] = True
        cloud_connector_ref_property['defaultValue'] = ''

        provider_template['properties'].append(cloud_connector_ref_property)

        provider_template = self._bigiq.post_provider_template(
            provider_template)

    def _assure_tenant_service(self, service):
        """ Configure the service """
        pool = service['pool']
        project_id = pool['tenant_id']

        connector = self._connectors_by_name[self._connector_name(project_id)]

        tenant_service = self.generate_bigiq_service(service, connector)

        pool_id = service['pool']['id']
        tenant_name = self.get_bigiq_tenant_name(project_id)
        service_name = self.get_bigiq_service_name(pool_id)
        try:
            existing_service = self._bigiq.get_tenant_service(
                tenant_name, service_name)
        except:
            existing_service = None

        if pool['status'] != plugin_const.PENDING_DELETE:
            if existing_service:
                tenant_service['generation'] = existing_service['generation']
                tenant_service['selfLink'] = existing_service['selfLink']

                self._bigiq.put_tenant_service(
                    tenant_name, service_name, tenant_service)
            else:
                # We check to see if there are any tables on the service that
                # we are going to create before doing so. If there were tables
                # it would indicate that there were pool members for this app
                # that we are about to create. If there aren't any tables
                # the pool members) we don't actually create the service yet.
                # If we deploy the app to much when it doesn't have
                # any pool members then we will provision to many fixed IPs
                # and floating IPs for VIPs. This is because the first time we
                # deploy and provision those networking resources the Nova
                # service does't get updated on them right away. As a result
                # our nodes that we build off of the Nova instances don't
                # have the correct networking information when we build them.
                # As a result it looks like we need to continuing
                # provisioning resources.
                LOG.debug("post_tenant_service: %s" % str(tenant_service))
                self._bigiq.post_tenant_service(
                    self.get_bigiq_tenant_name(project_id),
                    tenant_service)
                if ('vip' in service and
                        'id' in service['vip'] and
                        'address' in service['vip'] and
                        service['vip']['address'] and
                        service['vip']['status'] !=
                        plugin_const.PENDING_DELETE):
                    self.allow_vip_on_bigips(
                        project_id, service['vip']['address'])
        else:
            if existing_service:
                self._bigiq.delete_tenant_service(tenant_name, service_name)
        LOG.debug("assure_tenant_service exit")

    @staticmethod
    def _connector_name(project_id):
        """ Generate connector name """
        return 'OpenStack-LBaaS-Connector-%s' % project_id

    @staticmethod
    def _cloud_connector(
            project_id, openstack_keystone_uri,
            openstack_admin_username, openstack_admin_password):
        """ Generate Cloud Connector """
        connector = {}
        get_conn_name = LBaaSBuilderBigiqIApp._connector_name
        connector['name'] = get_conn_name(project_id)
        connector['description'] = "Connector for OpenStack LBaaS for " \
                                   "project with the ID of '%s'" % project_id

        connector['parameters'] = []

        param = {}
        param['id'] = 'OpenStackUri'
        param['value'] = openstack_keystone_uri

        connector['parameters'].append(param)

        param = {}
        param['id'] = 'OpenStackUserName'
        param['value'] = openstack_admin_username

        connector['parameters'].append(param)

        param = {}
        param['id'] = 'OpenStackPassword'
        param['value'] = openstack_admin_password

        connector['parameters'].append(param)

        param = {}
        param['id'] = 'OpenStackTenantID'
        param['value'] = project_id

        connector['parameters'].append(param)

        return connector

    @staticmethod
    def _tenant(project_id, cloud_connector_self_link):
        """ Generate Tenant """
        tenant = {}
        tenant['name'] = LBaaSBuilderBigiqIApp.get_bigiq_tenant_name(
            project_id)
        tenant['description'] = 'BIG-IQ tenant created by the F5 Device ' \
            ' LBaaS plugin for use with the OpenStack' \
            ' project with an ID of %s' % project_id

        tenant['cloudConnectorReferences'] = []

        cloud_connector_reference = {}
        cloud_connector_reference['link'] = cloud_connector_self_link

        tenant['cloudConnectorReferences'].append(cloud_connector_reference)

        return tenant

    def get_nova_client(self, tenant_id):
        """Create nova client."""
        uri = self.conf.openstack_keystone_uri
        if not uri.endswith('/v2.0'):
            uri += '/v2.0'
        LOG.debug(
            'creating nova client %s' %
            str({'username': self.conf.openstack_admin_username,
                 'api_key': self.conf.openstack_admin_password,
                 'project_id': tenant_id,
                 'auth_url': uri}))
        return nvclient.Client(username=self.conf.openstack_admin_username,
                               api_key=self.conf.openstack_admin_password,
                               project_id=tenant_id,
                               tenant_id=tenant_id,
                               auth_url=uri)

    def get_neutron_client(self, tenant_id):
        """Create Neutron client."""
        uri = self.conf.openstack_keystone_uri
        if not uri.endswith('/v2.0'):
            uri += '/v2.0'
        LOG.debug(
            'creating neutron client %s' %
            str({'username': self.conf.openstack_admin_username,
                 'api_key': self.conf.openstack_admin_password,
                 'project_id': tenant_id,
                 'auth_url': uri}))
        return neclient.Client(username=self.conf.openstack_admin_username,
                               password=self.conf.openstack_admin_password,
                               tenant_id=tenant_id,
                               auth_url=uri)

    def allow_vip_on_bigips(self, tenant_id, vip_addr):
        """ allow vip on service port """
        nova_admin = self.get_nova_client(tenant_id)
        servers = nova_admin.servers.list(detailed=True)
        for server in servers:
            if 'bigip' in server.name:
                self.allow_vip_on_bigip_port(server, vip_addr)

    def allow_vip_on_bigip_port(self, bigip, vip_addr):
        """ allow vip on bigip port """
        tenant_id = bigip.tenant_id
        neutron_client = self.get_neutron_client(tenant_id)

        # get external subnet
        external_subnet = None
        subnets = neutron_client.list_subnets(tenant_id=tenant_id)['subnets']
        for subnet in subnets:
            if 'external' in subnet['name']:
                external_subnet = subnet
        if not external_subnet:
            LOG.error("No bigip external subnet found")
            return

        # get external subnet port
        ext_port = LBaaSBuilderBigiqIApp.get_instance_subnet_port(
            neutron_client, bigip, external_subnet)
        if not ext_port:
            LOG.error("No bigip external network port found")
            return
        LOG.debug("bigip ext port before update: %s" % str(ext_port))

        # update port to allow vip
        port_update = {'port':
                       {'allowed_address_pairs': [{'ip_address': vip_addr}]}}
        neutron_client.update_port(ext_port['id'], port_update)
        ext_port = LBaaSBuilderBigiqIApp.get_instance_subnet_port(
            neutron_client, bigip, external_subnet)
        LOG.debug("bigip ext port after update: %s" % str(ext_port))

    @staticmethod
    def get_instance_subnet_port(neutron_client, instance, subnet):
        """Get port for an instance on a specific subnet"""
        port_list = neutron_client.list_ports(device_id=instance.id)['ports']
        for port in port_list:
            if port['fixed_ips'][0]['subnet_id'] == subnet['id']:
                return port
        return None

    def check_tenant_bigiq_readiness(self, service):
        """Dispatch service: Get service handler"""
        readiness = {'found_bigips': False}
        nova_admin = self.get_nova_client(service['pool']['tenant_id'])
        servers = nova_admin.servers.list(detailed=True)
        for server in servers:
            LOG.debug("Looking for bigip: server name: %s metadata: %s" %
                      (server.name, server.metadata))
            if 'bigip' in server.name:
                LOG.debug("Found bigip. Maybe using bigiq.")
                readiness['found_bigips'] = True
            # Did this bigip opt out of lbaas?
            if 'lbaas_enable' in server.metadata and \
                    not server.metadata['lbaas_enable']:
                readiness['found_bigips'] = False
        return readiness

    @staticmethod
    def get_bigiq_tenant_name(project_id):
        """ Generate tenant name """
        return 'OpenStack-Project-%s' % project_id

    @staticmethod
    def get_bigiq_service_name(pool_id):
        """ Generate service name """
        return 'OpenStack-LBaaS-Service-%s' % pool_id

    def generate_bigiq_service(self, os_service, connector):
        """ Generate tenant service """
        tenant_service = {}

        pool_id = os_service['pool']['id']

        # {
        #     ...,
        #     "name": "someServiceName",
        #     ...
        # }
        tenant_service['name'] = self.get_bigiq_service_name(pool_id)

        # {
        #     ...,
        #     "tenantTemplateReference":
        #         {
        #             "link": "https://localhost/mgmt/cm/cloud/tenant/" +
        #                 "templates/iapp/OpenStack-LBaaS-Template"
        #         },
        #     ...
        # }
        tenant_service['tenantTemplateReference'] = \
            {'link': 'https://localhost/mgmt/cm/'
                     'cloud/tenant/templates/iapp/%s'
                     % self._LBAAS_PROVIDER_TEMPLATE_NAME}

        # {
        #     ...,
        #     "vars":
        #         [
        #             pool vars, VIP vars, app stats vars
        #         ],
        #     ...
        # }
        tenant_service[self.varkey] = []

        self.fill_in_pool_info(tenant_service, os_service)
        self.fill_in_vip_info(
            tenant_service, os_service, bigiq_workaround=True)

        tenant_service[self.varkey].append(
            get_tenant_service_var('app_stats', 'enabled'))

        # {
        #     ...,
        #     "tables":
        #         [
        #             pool members
        #         ],
        #     ...
        # }
        tenant_service['tables'] = []

        self.fill_in_pool_members_table(tenant_service, os_service, False)

        # {
        #     ...,
        #     "properties":
        #         [
        #             {
        #                 "id": "cloudConnectorReference",
        #                 "value": "https://localhost/mgmt/cm/cloud/" +
        #         "connectors/openstack/2d595e4f-8cec-4c5b-b921-0fbf1fec6cb5"
        #             }
        #         ],
        #     ...
        # }
        tenant_service['properties'] = []

        tenant_service['properties'].append(
            {'id': 'cloudConnectorReference',
             'value': connector['selfLink']})

        return tenant_service

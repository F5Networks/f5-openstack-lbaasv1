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
from neutron.services.loadbalancer import constants as os_lb_consts
from time import time

from neutron.services.loadbalancer.drivers.f5.bigip.lbaas \
    import LBaaSBuilder
from neutron.services.loadbalancer.drivers.f5.bigip.pools \
    import BigipPoolManager
from neutron.services.loadbalancer.drivers.f5.bigip.vips \
    import BigipVipManager

from f5.bigip.interfaces import prefixed

LOG = logging.getLogger(__name__)


class LBaaSBuilderBigipObjects(LBaaSBuilder):
    """F5 LBaaS Driver using iControl for BIG-IP to
       create objects (vips, pools) - not using an iApp. """

    def __init__(self, conf, driver, bigip_l2_manager=None):
        super(LBaaSBuilderBigipObjects, self).__init__(conf, driver)
        self.bigip_l2_manager = bigip_l2_manager
        self.bigip_pool_manager = BigipPoolManager(self, self.bigip_l2_manager)
        self.bigip_vip_manager = BigipVipManager(self, self.bigip_l2_manager)

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


class LBaaSBuilderBigipIApp(LBaaSBuilder):
    """ LBaaS Builder for BIG-IP using iApp """

    _F5_LBAAS_IAPP_TEMPLATE_NAME = "f5.lbaas"

    def __init__(self, conf, driver):
        super(LBaaSBuilderBigipIApp, self).__init__(conf, driver)
        self.conf = conf

    def assure_service(self, service, traffic_group, all_subnet_hints):
        for bigip in self.driver.get_config_bigips():
            subnet_hints = all_subnet_hints[bigip.device_name]
            self.assure_bigip_service(bigip, service, subnet_hints)

    def assure_bigip_service(self, bigip, service, subnet_hints):
        """ Configure the service """
        project_id = service['pool']['tenant_id']
        tenant_name = LBaaSBuilderBigipIApp.get_bigip_tenant_name(project_id)

        if not ('vip' in service and
                'id' in service['vip'] and
                'address' in service['vip'] and
                service['vip']['address']):
            return

        tenant_service = LBaaSBuilderBigipIApp.generate_bigip_service(
            bigip, self.conf, service)

        # We are interested in catching an exception here when we try to get
        # a tenant service. If we do get one we know that the tenant service
        # doesn't exist and that we should create it if need be.
        # If we don't get an exception we should update the existing one
        # or delete the existing one if need be.
        try:

            pool_id = service['pool']['id']

            service_name = LBaaSBuilderBigipIApp.get_bigip_service_name(
                pool_id)

            existing_service = bigip.iapp.get_service(
                service_name, folder=tenant_name)

            if existing_service:
                LOG.debug("existing service: %s" % str(existing_service))
            # We check to see if there are any tables on the service that
            # we are going to update before doing so. If there were tables
            # it would indicate that there were pool members for this app
            # and thus we should create it. If there aren't any then we
            # delete the app if it was already deployed.
            if tenant_service['tables']:
                tenant_service['generation'] = existing_service['generation']
                tenant_service['selfLink'] = existing_service['selfLink']

                LOG.debug("updating service: %s" % str(tenant_service))
                bigip.iapp.update_service(
                    service_name, folder=tenant_name,
                    service=tenant_service)
                LOG.debug("updated service: %s" % str(tenant_service))
            else:
                bigip.iapp.delete(service_name, folder=tenant_name)
        except:
            # We check to see if there are any tables on the service that we
            # are going to create before doing so. If there were tables it
            # would indicate that there were pool members for this app the we
            # are about to create. If there aren't any tables (and thus pool
            # members) we don't actually create the service yet.
            # If we deploy the app to much when it doesn't
            # have any pool members then we will provision to many fixed IPs
            # and floating IPs for VIPs. This is because the first time we
            # deploy and provision those networking resources the Nova
            # service does't get updated on them right away. As a result our
            # nodes that we build off of the Nova instances don't have the
            # correct networking information when we build them.
            # As a result it looks like we need to continuing
            # provisioning resources.
            if not tenant_service['tables']:
                return

            LOG.debug("creating service: %s" % str(tenant_service))
            bigip.iapp.create_service(
                name=service_name, folder=tenant_name, service=tenant_service)

    @staticmethod
    def get_bigip_tenant_name(project_id):
        """ Generate tenant name """
        return project_id

    @staticmethod
    def get_bigip_service_name(pool_id):
        """ Generate service name """
        return prefixed(pool_id)

    @staticmethod
    def generate_bigip_service(bigip, conf, os_service):
        """ Generate tenant service """
        tenant_service = {}

        pool_id = os_service['pool']['id']

        # {
        #     ...,
        #     "name": "someServiceName",
        #     ...
        # }
        tenant_service['name'] = LBaaSBuilderBigipIApp.get_bigip_service_name(
            pool_id)

        tenant_service['template'] = '/Common/%s' \
            % LBaaSBuilderBigipIApp._F5_LBAAS_IAPP_TEMPLATE_NAME
        #    {'link': 'https://localhost/mgmt/iapp/service'
        #             '/templates/%s'

        # {
        #     ...,
        #     "vars":
        #         [
        #             pool vars, VIP vars, app stats vars
        #         ],
        #     ...
        # }
        tenant_service['variables'] = []

        fill_in_pool_info(tenant_service, os_service)
        fill_in_vip_info(bigip, conf, tenant_service, os_service)
        tenant_service['variables'].append(
            get_tenant_service_var('app_stats', 'enabled'))

        #     "tables":
        #         [
        #             pool members
        #         ],
        #     ...
        # }
        tenant_service['tables'] = []

        fill_in_pool_members_table(
            bigip, conf, tenant_service, os_service)

        return tenant_service


def fill_in_pool_info(tenant_service, os_service):
    """ Fill in pool info on tenant service """
    # {
    #     ...,
    #     "vars":
    #         [
    #             ...,
    #             {
    #                 "name":"pool__lb_method",
    #                 "value":"round-robin"
    #             },
    #             {
    #                 "name":"pool__monitor",
    #                 "value":"http"
    #             },
    #             ...
    #         ],
    #     ...
    # }

    # The 'vars' key and the list for its value should have already been
    # created on 'tenant_service'
    os_pool = os_service.get('pool')

    # This isn't required per the f5.lbaas iApp template
    pool_lb_method_var = _pool_lb_method_var(os_pool)

    if pool_lb_method_var:
        tenant_service['variables'].append(pool_lb_method_var)

    # This isn't required per the f5.lbaas iApp template
    pool_monitor_var = \
        _pool_monitor_var(os_service)

    if pool_monitor_var:
        tenant_service['variables'].append(pool_monitor_var)


_LTM_LB_METHODS = {
    os_lb_consts.LB_METHOD_LEAST_CONNECTIONS: 'least-connections-members',
    os_lb_consts.LB_METHOD_ROUND_ROBIN: 'round-robin',
    os_lb_consts.LB_METHOD_SOURCE_IP: 'least-connections-node'}


def _pool_lb_method_var(os_pool):
    """ Generate pool lb method """
    # This isn't required per the f5.lbaas iApp template
    if not (os_pool and 'lb_method' in os_pool and os_pool['lb_method']):
        return None

    ltm_lb_method = _LTM_LB_METHODS.get(os_pool['lb_method'])

    if not ltm_lb_method:
        LOG.info(_('Unsupported OpenStack load balancing method %s - '
                   'the default LTM load balancing method specified '
                   'in the iApp template will be used'
                   % os_pool['lb_method']))

        return None

    return get_tenant_service_var(
        'pool__lb_method', ltm_lb_method)

# Note that we aren't mapping OpenStack health monitor types to
# LTM monitor types.
# We are actually mapping them to the keys of the 'monitor' map in
# the f5.lbaas iApp template. The template itself will then map them
# to the proper LTM monitor types.
# Note that we also don't support the HTTPS OpenStack health monitor type.
_IAPP_TEMPLATE_MONITOR_TYPES = {
    os_lb_consts.HEALTH_MONITOR_HTTP: 'http',
    os_lb_consts.HEALTH_MONITOR_PING: 'ping',
    os_lb_consts.HEALTH_MONITOR_TCP: 'tcp'}


def _pool_monitor_var(os_service):
    """ Generate pool monitor """
    # This isn't required per the f5.lbaas iApp template.
    # We use the OpenStack service model which has the 'health_monitors'
    # key on it vs. looking for a monitor on the OpenStack pool because 1)
    # the OpenStack service model that gets constructed by the
    # plugin driver only has the monitor IDs on each pool as returned
    # by the OpenStack LoadBalancerPluginDb class and
    # 2) the information is eventually retrieved and added to the
    # 'health_monitors'
    # key of the OpenStack service model as done by the F5
    # LoadBalancerCallbacks
    # class (see get_service_by_pool_id method)
    if not (os_service and 'health_monitors' in os_service
            and os_service['health_monitors']):
        return None

    for health_monitor in os_service['health_monitors']:
        if not 'type' in health_monitor:
            continue

        templ_map = _IAPP_TEMPLATE_MONITOR_TYPES
        iapp_template_monitor_type = templ_map.get(health_monitor['type'])

        if not iapp_template_monitor_type:
            #LOG.info(_('Unsupported OpenStack health monitor type %s'
            #            ' - the default LTM health monitor specified '
            #            'in the iApp template will be used'
            #            % health_monitor['type']))

            continue

        # There is a limitation on how many OpenStack health monitors
        # you can use because of our iApp today since it only
        # supports one. In theory we would be able to
        # support multiple by updating our iApp to do so.
        return get_tenant_service_var(
            'pool__monitor', iapp_template_monitor_type)


def fill_in_vip_info(bigip, conf, tenant_service, os_service):
    """ Fill in vip info on tenant service """
    # {
    #     ...,
    #     "vars":
    #         [
    #             ...,
    #             {
    #                 "name":"vip__addr",
    #                 "value":"0.0.0.0"
    #             },
    #             {
    #                 "name":"vip__persist",
    #                 "value":"http-cookie"
    #             },
    #             {
    #                 "name":"vip__cookie",
    #                 "value":"jsessionid"
    #             },
    #             {
    #                 "name":"vip__port",
    #                 "value":"80"
    #             },
    #             {
    #                 "name":"vip__protocol",
    #                 "value":"http"
    #             },
    #             {
    #                 "name":"vip__state",
    #                 "value":"enabled"
    #             },
    #             ...
    #         ],
    #     ...
    # }

    # The 'vars' key and the list for its value should have already
    # been created on 'tenant_service'
    os_vip = os_service.get('vip')
    os_pool = os_service.get('pool')
    os_tenant_id = os_pool['tenant_id']

    # This is required per the f5.lbaas iApp template
    vip_addr_var = _vip_addr_var(bigip, conf, os_vip, os_tenant_id)
    tenant_service['variables'].append(vip_addr_var)

    # This is a workaround where we add an additional var named
    # 'pool__addr' to the tenant service we are POSTing/PUTting.
    # This is because the IAppServiceWorker.java on the BIG-IP queries
    # for iApp service info via the IAppServiceMcpHelper.java. The
    # iApp service helper has the method named 'appScalarVarsToPojo'
    # where it looks at all of the app vars and tries to determine which
    # ones correspond to the VIP address and port. If it finds them it
    # then updates the server tier references. Specifically the iApp
    # service helper is looking for the vars named 'pool__addr',
    # 'basic__addr', 'pool__port', and 'basic__port'. The f5.lbaas
    # template uses the vars 'vip__addr' and 'vip__port' and as a result
    # iApp service worker # doesn't get a list of updated server tiers.
    # As a result when the # VirtualServerStatsAggregationWorker.java
    # queries for the iApp service info (via views and the cache workers)
    # it doesn't get any can't correspond any stats to any virtual servers
    # on the BIG-IQ. Thus there are no virtual server stats.
    # We also aren't getting app stats which we believe is a result of us
    # not getting virtual server stats. In adding the 'pool__addr' var
    # we hope that it gets stored in MCP, the iApp server helper sees it
    # and can correctly update the server tier info which will hopefully
    # give us stats. We don't change the 'vip__addr' var name to
    # 'pool__addr' as we want to leave the presentation
    # and implementation of the f5.lbaas iApp the same.
    #tenant_service['vars'].append(
    #    get_tenant_service_var('pool__addr', vip_addr_var['value']))

    vip_persist_var = _vip_persist_var(os_vip)

    # The f5.lbaas iApp template doesn't require this variable to be
    # filled in for us to deploy it. If the method doesn't returns
    # None we skip adding it to the template we will deploy.
    if vip_persist_var:
        tenant_service['variables'].append(vip_persist_var)

    vip_cookie_var = _vip_cookie_var(os_vip)

    # The f5.lbaas iApp template doesn't require this variable to be
    # filled in for us to deploy it. If the method doesn't returns None
    # we skip adding it to the template we will deploy.
    if vip_cookie_var:
        tenant_service['variables'].append(vip_cookie_var)

    vip_port_var = _vip_port_var(os_vip)

    # The f5.lbaas iApp template doesn't require this variable to be
    # filled in for us to deploy it. If the method doesn't returns None
    # we skip adding it to the template we will deploy.
    if vip_port_var:
        tenant_service['variables'].append(vip_port_var)
        # The 'pool__port' var has the same story as the 'pool__addr'
        # var from above.
        tenant_service['variables'].append(
            get_tenant_service_var('pool__port', vip_port_var['value']))

    vip_protocol_var = _vip_protocol_var(os_vip)

    # The f5.lbaas iApp template doesn't require this variable to be
    # filled in for us to deploy it. If the method doesn't returns
    # None we skip adding it to the template we will deploy.
    if vip_protocol_var:
        tenant_service['variables'].append(vip_protocol_var)

    vip_state_var = _vs_state_var(os_vip)

    # The f5.lbaas iApp template doesn't require this variable to be
    # filled in for us to deploy it. If the method doesn't returns
    # None we skip adding it to the template we will deploy.
    if vip_state_var:
        tenant_service['variables'].append(vip_state_var)


def _vip_addr_var(bigip, conf, os_vip, tenant_id):
    """ Generate vip addr from os vip """
    # This is required per the f5.lbaas iApp template
    if not (os_vip and 'id' in os_vip and os_vip['id']
            and 'address' in os_vip and os_vip['address']):
        return _default_dynamic_vip_addr_var()

    vip_address = os_vip['address']
    network = os_vip['network']
    if is_common_network(network, conf):
        vip_address += '%0'
    else:
        vip_address += ('%' + str(bigip.get_domain_index(tenant_id)))
    return get_tenant_service_var('vip__addr', vip_address)


def is_common_network(network, conf):
    """ Does this network belong in the /Common folder? """
    return network['shared'] or \
        (network['id'] in conf.common_network_ids) or \
        ('router:external' in network and
         network['router:external'] and
         (network['id'] in conf.common_external_networks))


def _default_dynamic_vip_addr_var():
    """ Generate default dynamic vip addr """
    return get_tenant_service_var('vip__addr', '0.0.0.0')


# Note that we aren't mapping OpenStack VIP session persistence types
# to LTM persistence types. We are actually mapping them to the keys of
# the 'persist' map in the f5.lbaas
# iApp template. The template itself will then map them to the proper
# LTM persistence types.
_IAPP_TEMPLATE_PERSIST_TYPES = {
    os_lb_consts.SESSION_PERSISTENCE_APP_COOKIE: 'app-cookie',
    os_lb_consts.SESSION_PERSISTENCE_HTTP_COOKIE: 'http-cookie',
    os_lb_consts.SESSION_PERSISTENCE_SOURCE_IP: 'source-ip'}


def _vip_persist_var(os_vip):
    """ Generate vip persist var """
    # This isn't required per the f5.lbaas iApp template
    if not (os_vip and
            'id' in os_vip and os_vip['id'] and
            'session_persistence' in os_vip and
            os_vip['session_persistence'] and
            'type' in os_vip['session_persistence']
            and os_vip['session_persistence']['type']):
        return None
    templ_map = _IAPP_TEMPLATE_PERSIST_TYPES
    iapp_template_persist_type = templ_map.get(
        os_vip['session_persistence']['type'])

    if not iapp_template_persist_type:
        LOG.info(_('Unsupported OpenStack VIP session persistence'
                   ' type %s - the default LTM persistence type '
                   'specified in the iApp template will be used'
                   % os_vip['session_persistence']['type']))

        return None

    return get_tenant_service_var('vip__persist', iapp_template_persist_type)


def _vip_cookie_var(os_vip):
    """ Generate vip cookie var """
    # This isn't required per the f5.lbaas iApp template
    if not (os_vip and
            'id' in os_vip and os_vip['id'] and
            'session_persistence' in os_vip and
            os_vip['session_persistence'] and
            'type' in os_vip['session_persistence'] and
            os_vip['session_persistence']['type'] and
            os_lb_consts.SESSION_PERSISTENCE_APP_COOKIE ==
            os_vip['session_persistence']['type'] and
            'cookie_name' in os_vip['session_persistence'] and
            os_vip['session_persistence']['cookie_name']):
        return None

    return get_tenant_service_var(
        'vip__cookie', os_vip['session_persistence']['cookie_name'])


def _vip_port_var(os_vip):
    """ Generate vip port var """
    # This isn't required per the f5.lbaas iApp template
    if not (os_vip and 'id' in os_vip and os_vip['id']
            and 'protocol_port' in os_vip and os_vip['protocol_port']):
        return None

    return get_tenant_service_var('vip__port', os_vip['protocol_port'])


_LTM_PROFILE_TYPES = {
    os_lb_consts.PROTOCOL_HTTP: 'http',
    os_lb_consts.PROTOCOL_TCP: 'tcp'}


def _vip_protocol_var(os_vip):
    """ Generate vip protocol var """
    # This isn't required per the f5.lbaas iApp template
    if not (os_vip and 'id' in os_vip and os_vip['id'] and
            'protocol' in os_vip and os_vip['protocol']):
        return None

    prof_map = _LTM_PROFILE_TYPES
    ltm_profile_type = prof_map.get(os_vip['protocol'])

    if not ltm_profile_type:
        LOG.info(_('Unsupported OpenStack VIP protocol %s - the default'
                   ' LTM profile type specified in the iApp '
                   'template will be used' % os_vip['protocol']))

        return None

    return get_tenant_service_var('vip__protocol', ltm_profile_type)


_LTM_VS_STATES = \
    {True: 'enabled', False: 'disabled'}


def _vs_state_var(os_vip):
    """ Generate vs state """
    # This isn't required per the f5.lbaas iApp template
    if not (os_vip and 'id' in os_vip and os_vip['id'] and
            'admin_state_up' in os_vip and
            isinstance(os_vip['admin_state_up'], bool)):
        return None

    return get_tenant_service_var(
        'vip__state',
        _LTM_VS_STATES[os_vip['admin_state_up']])


def fill_in_pool_members_table(bigip, conf, tenant_service, os_service):
    """ Fill in pool members """
    # {
    #     ...,
    #     "tables":
    #         [
    #             {
    #                 "name": "pool__members",
    #                 "columns":
    #                     [
    #                         "addr",
    #                         "connection_limit",
    #                         "port",
    #                         "state"
    #                     ],
    #                 "rows":
    #                     [
    #                         [
    #                             "",
    #                             "10000",
    #                             "80",
    #                             ""
    #                         ]
    #                     ]
    #             }
    #         ],
    #     ...
    # }

    # The 'tables' key and the list for its value should have
    # already been created on 'tenant_service'
    pool_members_table = {}
    pool_members_table['name'] = 'pool__members'
    pool_members_table['column-names'] = \
        ['addr', 'connection_limit', 'port', 'state']
    pool_members_table['rows'] = []

#         if not (os_vip and 'id' in os_vip and os_vip['id'] and
# 'admin_state_up' in os_vip and isinstance(os_vip['admin_state_up'], bool)):
    if 'members' in os_service and os_service['members']:

        tenant_id = os_service['pool']['tenant_id']
        for os_member in os_service['members']:
            network = os_member['network']
            member_address = os_member['address']
            if is_common_network(network, conf):
                member_address += '%0'
            else:
                member_address += \
                    ('%' + str(bigip.get_domain_index(tenant_id)))

            if os_member and 'address' in os_member and \
                    os_member['address'] and 'protocol_port' in os_member \
                    and os_member['protocol_port']:
                pool_members_table['rows'].append(
                    {'row': [member_address,
                             '10000', os_member['protocol_port'], 'enabled']})

        # We only add the table if there are any members for us to add.
        # If we add it without any member the iApp blows up
        # when it tries to do '[join $members]' when it is creating
        # the pool.
        tenant_service['tables'].append(pool_members_table)


def get_tenant_service_var(var_name, var_value):
    """ Generate tenant service var """
    return {'name': var_name, 'value': var_value}

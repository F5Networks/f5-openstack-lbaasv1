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

from abc import abstractmethod
from neutron.plugins.common import constants as plugin_const

try:
    from neutron.openstack.common import log as logging
    from neutron.services.loadbalancer import constants as os_lb_consts
except ImportError:
    from oslo_log import log as logging
    from neutron_lbaas.services.loadbalancer import constants as os_lb_consts

LOG = logging.getLogger(__name__)


class LBaaSBuilder(object):
    """ This is an abstract base class. """
    def __init__(self, conf, driver):
        self.conf = conf
        self.driver = driver
        self.varkey = None

    @abstractmethod
    def assure_service(self, service, traffic_group, all_subnet_hints):
        """ Assure that the service is configured """
        # Abstract Method
        pass

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


_LTM_LB_METHODS = {
    os_lb_consts.LB_METHOD_LEAST_CONNECTIONS: 'least-connections-member',
    os_lb_consts.LB_METHOD_ROUND_ROBIN: 'round-robin',
    os_lb_consts.LB_METHOD_SOURCE_IP: 'least-connections-node'}


_LTM_PROFILE_TYPES = {
    os_lb_consts.PROTOCOL_HTTP: 'http',
    os_lb_consts.PROTOCOL_TCP: 'tcp'}


# Note that we aren't mapping OpenStack VIP session persistence types
# to LTM persistence types. We are actually mapping them to the keys of
# the 'persist' map in the f5.lbaas
# iApp template. The template itself will then map them to the proper
# LTM persistence types.
_IAPP_TEMPLATE_PERSIST_TYPES = {
    os_lb_consts.SESSION_PERSISTENCE_APP_COOKIE: 'app-cookie',
    os_lb_consts.SESSION_PERSISTENCE_HTTP_COOKIE: 'http-cookie',
    os_lb_consts.SESSION_PERSISTENCE_SOURCE_IP: 'source-ip'}


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


_LTM_VS_STATES = \
    {True: 'enabled', False: 'disabled'}


class LBaaSBuilderIApp(LBaaSBuilder):
    """ Common routines between bigip and bigiq for deploying an iApp """
    def __init__(self, conf, driver, bigip_l2_manager=None):
        super(LBaaSBuilderIApp, self).__init__(conf, driver)
        self.bigip_l2_manager = bigip_l2_manager

    @staticmethod
    def _get_all_subnets(service):
        """ Examine service and return active networks """
        subnets = dict()
        if 'id' in service['vip']:
            vip = service['vip']
            if 'network' in vip and vip['network']:
                network = service['vip']['network']
                subnet = service['vip']['subnet']
                subnets[subnet['id']] = {'network': network,
                                         'subnet': subnet,
                                         'is_for_member': False}

        for member in service['members']:
            if 'network' in member and member['network']:
                network = member['network']
                subnet = member['subnet']
                subnets[subnet['id']] = {'network': network,
                                         'subnet': subnet,
                                         'is_for_member': True}
        return subnets

    def fill_in_pool_info(self, tenant_service, os_service):
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
        pool_lb_method_var = LBaaSBuilderIApp._pool_lb_method_var(os_pool)

        if pool_lb_method_var:
            tenant_service[self.varkey].append(pool_lb_method_var)

        # This isn't required per the f5.lbaas iApp template
        pool_monitor_var = \
            LBaaSBuilderIApp._pool_monitor_var(os_service)

        if pool_monitor_var:
            tenant_service[self.varkey].append(pool_monitor_var)

    @staticmethod
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

        return get_tenant_service_var('pool__lb_method', ltm_lb_method)

    @staticmethod
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
        if not (os_service and
                'health_monitors' in os_service and
                os_service['health_monitors']):
            return None

        for health_monitor in os_service['health_monitors']:
            if 'type' not in health_monitor:
                continue

            templ_map = _IAPP_TEMPLATE_MONITOR_TYPES
            iapp_template_monitor_type = templ_map.get(health_monitor['type'])

            if not iapp_template_monitor_type:
                # LOG.info(_('Unsupported OpenStack health monitor type %s'
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

    def fill_in_vip_info(self, tenant_service, os_service,
                         bigiq_workaround=False):
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
        have_vip = ('vip' in os_service and
                    'id' in os_service['vip'] and
                    'address' in os_service['vip'] and
                    os_service['vip']['address'] and
                    os_service['vip']['status'] != plugin_const.PENDING_DELETE)
        if not have_vip:
            vip_state_var = get_tenant_service_var('vip__state', 'delete')
            tenant_service[self.varkey].append(vip_state_var)
            return

        os_vip = os_service.get('vip')

        # This is required per the f5.lbaas iApp template
        vip_addr_var = self._vip_addr_var(os_vip)
        tenant_service[self.varkey].append(vip_addr_var)

        vip_mask_var = self._vip_mask_var(os_vip)
        tenant_service[self.varkey].append(vip_mask_var)

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
        if bigiq_workaround:
            tenant_service[self.varkey].append(
                get_tenant_service_var('pool__addr', vip_addr_var['value']))

        vip_persist_var = self._vip_persist_var(os_vip)

        # The f5.lbaas iApp template doesn't require this variable to be
        # filled in for us to deploy it. If the method doesn't returns
        # None we skip adding it to the template we will deploy.
        if vip_persist_var:
            tenant_service[self.varkey].append(vip_persist_var)

        vip_cookie_var = self._vip_cookie_var(os_vip)

        # The f5.lbaas iApp template doesn't require this variable to be
        # filled in for us to deploy it. If the method doesn't returns None
        # we skip adding it to the template we will deploy.
        if vip_cookie_var:
            tenant_service[self.varkey].append(vip_cookie_var)

        vip_port_var = self._vip_port_var(os_vip)

        # The f5.lbaas iApp template doesn't require this variable to be
        # filled in for us to deploy it. If the method doesn't returns None
        # we skip adding it to the template we will deploy.
        if vip_port_var:
            tenant_service[self.varkey].append(vip_port_var)
            # The 'pool__port' var has the same story as the 'pool__addr'
            # var from above.
            tenant_service[self.varkey].append(
                get_tenant_service_var('pool__port', vip_port_var['value']))

        vip_protocol_var = self._vip_protocol_var(os_vip)

        # The f5.lbaas iApp template doesn't require this variable to be
        # filled in for us to deploy it. If the method doesn't returns
        # None we skip adding it to the template we will deploy.
        if vip_protocol_var:
            tenant_service[self.varkey].append(vip_protocol_var)

        vip_state_var = self._vs_state_var(os_vip)

        # The f5.lbaas iApp template doesn't require this variable to be
        # filled in for us to deploy it. If the method doesn't returns
        # None we skip adding it to the template we will deploy.
        if vip_state_var:
            tenant_service[self.varkey].append(vip_state_var)

    def _vip_addr_var(self, os_vip):
        """ Generate vip addr var """
        vip_address = os_vip['address']
        return get_tenant_service_var('vip__addr', vip_address)

    def _vip_mask_var(self, os_vip):
        """ Generate vip mask var """
        vip_address = os_vip['address']
        if len(vip_address.split(':')) > 2:
            # ipv6
            vip_mask = 'ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'
        else:
            # ipv4
            vip_mask = '255.255.255.255'
        return get_tenant_service_var('vip__mask', vip_mask)

    @staticmethod
    def _vip_persist_var(os_vip):
        """ Generate vip persist var """
        # This isn't required per the f5.lbaas iApp template
        if not (os_vip and
                'id' in os_vip and os_vip['id'] and
                'session_persistence' in os_vip and
                os_vip['session_persistence'] and
                'type' in os_vip['session_persistence'] and
                os_vip['session_persistence']['type']):
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

        return get_tenant_service_var(
            'vip__persist', iapp_template_persist_type)

    @staticmethod
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

    @staticmethod
    def _vip_port_var(os_vip):
        """ Generate vip port var """
        # This isn't required per the f5.lbaas iApp template
        if not (os_vip and
                'id' in os_vip and
                os_vip['id'] and
                'protocol_port' in os_vip and
                os_vip['protocol_port']):
            return None

        return get_tenant_service_var('vip__port', os_vip['protocol_port'])

    @staticmethod
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

    @staticmethod
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

    def fill_in_pool_members_table(
            self, tenant_service, os_service, bigip_format):
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
        columns = ['addr', 'connection_limit', 'port', 'state']
        if bigip_format:
            pool_members_table['column-names'] = columns
        else:
            # bigiq
            pool_members_table['columns'] = columns
        pool_members_table['rows'] = []

        if 'members' in os_service and os_service['members']:
            for os_member in os_service['members']:
                if not (os_member and
                        'address' in os_member and
                        os_member['address'] and
                        'protocol_port' in os_member and
                        os_member['protocol_port'] and
                        os_member['status'] != plugin_const.PENDING_DELETE):
                    continue
                member_address = os_member['address']
                if bigip_format:
                    iapp_pool_member = {'row': [member_address, '10000',
                                                os_member['protocol_port'],
                                                'enabled']}
                else:
                    # bigiq
                    iapp_pool_member = [member_address, '10000',
                                        os_member['protocol_port'], '']
                pool_members_table['rows'].append(iapp_pool_member)

        tenant_service['tables'].append(pool_members_table)


def get_tenant_service_var(var_name, var_value):
    """ Generate tenant service var """
    return {'name': var_name, 'value': var_value}

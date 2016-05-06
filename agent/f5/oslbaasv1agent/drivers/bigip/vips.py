""" Classes and functions for configuring virtual servers on BIG-IP """
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

# pylint: disable=no-self-use
try:
    from neutron.openstack.common import log as logging
except ImportError:
    from oslo_log import log as logging
from neutron.plugins.common import constants as plugin_const
from f5.bigip import interfaces as bigip_interfaces

LOG = logging.getLogger(__name__)
APP_COOKIE_RULE_PREFIX = 'app_cookie_'
RPS_THROTTLE_RULE_PREFIX = 'rps_throttle_'


class BigipVipManager(object):
    """ Class for managing vips on bigip """
    def __init__(self, driver, bigip_l2_manager, l3_binding):
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager
        self.l3_binding = l3_binding

    def assure_bigip_create_vip(self, bigip, service, traffic_group):
        """ Called for every bigip only in replication mode,
            otherwise called once for autosync mode. """
        vip = service['vip']
        pool = service['pool']
        ip_address = vip['address']
        snat_pool_name = None
        network = vip['network']
        preserve_network_name = False

        if self.driver.conf.f5_global_routed_mode:
            network_name = None
        else:
            (network_name, preserve_network_name) = \
                self.bigip_l2_manager.get_network_name(bigip, network)

            if self.bigip_l2_manager.is_common_network(network):
                network_name = '/Common/' + network_name

            if self.driver.conf.f5_snat_mode and \
               self.driver.conf.f5_snat_addresses_per_subnet > 0:
                tenant_id = pool['tenant_id']
                snat_pool_name = bigip_interfaces.decorate_name(tenant_id,
                                                                tenant_id)

        vip_info = {'network_name': network_name,
                    'preserve_network_name': preserve_network_name,
                    'ip_address': ip_address,
                    'traffic_group': traffic_group,
                    'snat_pool_name': snat_pool_name}

        just_added_vip = self._create_bigip_vip(bigip, service, vip_info)

        if vip['status'] == plugin_const.PENDING_CREATE or \
           vip['status'] == plugin_const.PENDING_UPDATE or \
           just_added_vip:
            self._update_bigip_vip(bigip, service)
            if self.l3_binding:
                self.l3_binding.bind_address(subnet_id=vip['subnet_id'],
                                             ip_address=ip_address)

    def assure_bigip_delete_vip(self, bigip, service):
        """ Remove vip from big-ip """
        vip = service['vip']
        bigip_vs = bigip.virtual_server

        LOG.debug(_('Vip: deleting VIP %s' % vip['id']))
        bigip_vs.remove_and_delete_persist_profile(
            name=vip['id'],
            folder=vip['tenant_id'])
        bigip_vs.delete(name=vip['id'], folder=vip['tenant_id'])

        bigip.rule.delete(name=RPS_THROTTLE_RULE_PREFIX +
                          vip['id'],
                          folder=vip['tenant_id'])

        bigip_vs.delete_uie_persist_profile(
            name=APP_COOKIE_RULE_PREFIX + vip['id'],
            folder=vip['tenant_id'])

        bigip.rule.delete(name=APP_COOKIE_RULE_PREFIX +
                          vip['id'],
                          folder=vip['tenant_id'])
        if self.l3_binding:
            self.l3_binding.unbind_address(subnet_id=vip['subnet_id'],
                                           ip_address=vip['address'])

    def _create_bigip_vip(self, bigip, service, vip_info):
        """ Create vip on big-ip """
        vip = service['vip']

        network_name = vip_info['network_name']
        preserve_network_name = vip_info['preserve_network_name']
        ip_address = vip_info['ip_address']
        vip_tg = vip_info['traffic_group']
        snat_pool_name = vip_info['snat_pool_name']

        bigip_vs = bigip.virtual_server

        # This is where you could decide to use a fastl4
        # or a standard virtual server.  The problem
        # is making sure that if someone updates the
        # vip protocol or a session persistence that
        # required you change virtual service types
        # would have to make sure a virtual of the
        # wrong type does not already exist or else
        # delete it first. That would cause a service
        # disruption. It would be better if the
        # specification did not allow you to update
        # L7 attributes if you already created a
        # L4 service.  You should have to delete the
        # vip and then create a new one.  That way
        # the end user expects the service outage.

        virtual_type = 'fastl4'
        if 'protocol' in vip:
            if vip['protocol'] == 'HTTP' or \
               vip['protocol'] == 'HTTPS':
                virtual_type = 'standard'
        if 'session_persistence' in vip:
            if vip['session_persistence'] == \
               'APP_COOKIE':
                virtual_type = 'standard'

        # Hard code to standard until we decide if we
        # want to handle the check/delete before create
        # and document the service outage associated
        # with deleting a virtual service. We'll leave
        # the steering logic for create in place.
        # Be aware the check/delete before create
        # is not in the logic below because it means
        # another set of interactions with the device
        # we don't need unless we decided to handle
        # shifting from L4 to L7 or from L7 to L4

        # virtual_type = 'standard'

        folder = vip['tenant_id']
        if '.' in ip_address:
            mask = '255.255.255.255'
        else:
            mask = None
        if virtual_type == 'standard':
            if bigip_vs.create(
                name=vip['id'],
                ip_address=ip_address,
                mask=mask,
                port=int(vip['protocol_port']),
                protocol=vip['protocol'],
                vlan_name=network_name,
                traffic_group=vip_tg,
                use_snat=self.driver.conf.f5_snat_mode,
                snat_pool=snat_pool_name,
                folder=folder,
                preserve_vlan_name=preserve_network_name
            ):
                return True
        else:
            if bigip_vs.create_fastl4(
                name=vip['id'],
                ip_address=ip_address,
                mask=mask,
                port=int(vip['protocol_port']),
                protocol=vip['protocol'],
                vlan_name=network_name,
                traffic_group=vip_tg,
                use_snat=self.driver.conf.f5_snat_mode,
                snat_pool=snat_pool_name,
                folder=folder,
                preserve_vlan_name=preserve_network_name
            ):
                return True

    def _update_bigip_vip(self, bigip, service):
        """ Update vip on big-ip """
        vip = service['vip']
        pool = service['pool']
        bigip_vs = bigip.virtual_server

        desc = vip['name'] + ':' + vip['description']
        bigip_vs.set_description(name=vip['id'],
                                 description=desc,
                                 folder=pool['tenant_id'])

        bigip_vs.set_pool(name=vip['id'],
                          pool_name=pool['id'],
                          folder=pool['tenant_id'])
        if vip['admin_state_up']:
            bigip_vs.enable_virtual_server(name=vip['id'],
                                           folder=pool['tenant_id'])
        else:
            bigip_vs.disable_virtual_server(name=vip['id'],
                                            folder=pool['tenant_id'])

        if 'session_persistence' in vip and vip['session_persistence']:
            # branch on persistence type
            persistence_type = vip['session_persistence']['type']
            set_persist = bigip_vs.set_persist_profile
            set_fallback_persist = bigip_vs.set_fallback_persist_profile

            if persistence_type == 'SOURCE_IP':
                # add source_addr persistence profile
                LOG.debug('adding source_addr primary persistence')
                set_persist(name=vip['id'],
                            profile_name='/Common/source_addr',
                            folder=vip['tenant_id'])
            elif persistence_type == 'HTTP_COOKIE':
                # HTTP cookie persistence requires an HTTP profile
                LOG.debug('adding http profile and' +
                          ' primary cookie persistence')
                bigip_vs.add_profile(name=vip['id'],
                                     profile_name='/Common/http',
                                     folder=vip['tenant_id'])
                # add standard cookie persistence profile
                set_persist(name=vip['id'],
                            profile_name='/Common/cookie',
                            folder=vip['tenant_id'])
                if pool['lb_method'] == 'SOURCE_IP':
                    set_fallback_persist(name=vip['id'],
                                         profile_name='/Common/source_addr',
                                         folder=vip['tenant_id'])
            elif persistence_type == 'APP_COOKIE':
                self._set_bigip_vip_cookie_persist(bigip, service)
        else:
            bigip_vs.remove_all_persist_profiles(name=vip['id'],
                                                 folder=vip['tenant_id'])

        if vip['connection_limit'] > 0 and 'protocol' in vip:
            # spec says you need to do this for HTTP
            # and HTTPS, but unless you can decrypt
            # you can't measure HTTP rps for HTTPs
            conn_limit = int(vip['connection_limit'])
            if vip['protocol'] == 'HTTP':
                LOG.debug('adding http profile and RPS throttle rule')
                # add an http profile
                bigip_vs.add_profile(
                    name=vip['id'],
                    profile_name='/Common/http',
                    folder=vip['tenant_id'])
                # create the rps irule
                rule_definition = \
                    self._create_http_rps_throttle_rule(conn_limit)
                # try to create the irule
                bigip.rule.create(name=RPS_THROTTLE_RULE_PREFIX + vip['id'],
                                  rule_definition=rule_definition,
                                  folder=vip['tenant_id'])
                # for the rule text to update becuase
                # connection limit may have changed
                bigip.rule.update(name=RPS_THROTTLE_RULE_PREFIX + vip['id'],
                                  rule_definition=rule_definition,
                                  folder=vip['tenant_id'])
                # add the throttle to the vip
                rule_name = RPS_THROTTLE_RULE_PREFIX + vip['id']
                bigip_vs.add_rule(name=vip['id'], rule_name=rule_name,
                                  priority=500, folder=vip['tenant_id'])
            else:
                LOG.debug('setting connection limit')
                # if not HTTP.. use connection limits
                bigip_vs.set_connection_limit(name=vip['id'],
                                              connection_limit=conn_limit,
                                              folder=pool['tenant_id'])
        else:
            # clear throttle rule
            LOG.debug('removing RPS throttle rule if present')
            rule_name = RPS_THROTTLE_RULE_PREFIX + vip['id']
            bigip_vs.remove_rule(name=vip['id'],
                                 rule_name=rule_name,
                                 priority=500,
                                 folder=vip['tenant_id'])
            # clear the connection limits
            LOG.debug('removing connection limits')
            bigip_vs.set_connection_limit(name=vip['id'],
                                          connection_limit=0,
                                          folder=pool['tenant_id'])

    def _set_bigip_vip_cookie_persist(self, bigip, service):
        """ Setup VIP Cookie Persistence """
        vip = service['vip']
        pool = service['pool']
        bigip_vs = bigip.virtual_server

        set_persist = bigip_vs.set_persist_profile
        set_fallback_persist = bigip_vs.set_fallback_persist_profile

        # application cookie persistence requires
        # an HTTP profile
        LOG.debug('adding http profile'
                  ' and primary universal persistence')
        bigip_vs.add_profile(name=vip['id'],
                             profile_name='/Common/http',
                             folder=vip['tenant_id'])
        # make sure they gave us a cookie_name
        if 'cookie_name' in vip['session_persistence']:
            cookie_name = vip['session_persistence']['cookie_name']
            # create and add irule to capture cookie
            # from the service response.
            rule_definition = self._create_app_cookie_persist_rule(cookie_name)
            # try to create the irule
            rule_name = APP_COOKIE_RULE_PREFIX + vip['id']
            if bigip.rule.create(name=rule_name,
                                 rule_definition=rule_definition,
                                 folder=vip['tenant_id']):
                # create universal persistence profile
                bigip_vs.create_uie_profile(
                    name=APP_COOKIE_RULE_PREFIX + vip['id'],
                    rule_name=APP_COOKIE_RULE_PREFIX + vip['id'],
                    folder=vip['tenant_id'])
            # set persistence profile
            profile_name = APP_COOKIE_RULE_PREFIX + vip['id']
            set_persist(name=vip['id'],
                        profile_name=profile_name,
                        folder=vip['tenant_id'])
            if pool['lb_method'] == 'SOURCE_IP':
                profile_name = '/Common/source_addr'
                set_fallback_persist(name=vip['id'],
                                     profile_name=profile_name,
                                     folder=vip['tenant_id'])
        else:
            # if they did not supply a cookie_name
            # just default to regualar cookie peristence
            set_persist(name=vip['id'],
                        profile_name='/Common/cookie',
                        folder=vip['tenant_id'])
            if pool['lb_method'] == 'SOURCE_IP':
                profile_name = '/Common/source_addr'
                set_fallback_persist(name=vip['id'],
                                     profile_name=profile_name,
                                     folder=vip['tenant_id'])

    def _create_app_cookie_persist_rule(self, cookiename):
        """ Create rule for cookie persistence """
        rule_text = "when HTTP_REQUEST {\n"
        rule_text += " if { [HTTP::cookie " + str(cookiename)
        rule_text += "] ne \"\" }{\n"
        rule_text += "     persist uie [string tolower [HTTP::cookie \""
        rule_text += cookiename + "\"]] 3600\n"
        rule_text += " }\n"
        rule_text += "}\n\n"
        rule_text += "when HTTP_RESPONSE {\n"
        rule_text += " if { [HTTP::cookie \"" + str(cookiename)
        rule_text += "\"] ne \"\" }{\n"
        rule_text += "     persist add uie [string tolower [HTTP::cookie \""
        rule_text += cookiename + "\"]] 3600\n"
        rule_text += " }\n"
        rule_text += "}\n\n"
        return rule_text

    def _create_http_rps_throttle_rule(self, req_limit):
        """ Create http throttle rule """
        rule_text = "when HTTP_REQUEST {\n"
        rule_text += " set expiration_time 300\n"
        rule_text += " set client_ip [IP::client_addr]\n"
        rule_text += " set req_limit " + str(req_limit) + "\n"
        rule_text += " set curr_time [clock seconds]\n"
        rule_text += " set timekey starttime\n"
        rule_text += " set reqkey reqcount\n"
        rule_text += " set request_count [session lookup uie $reqkey]\n"
        rule_text += " if { $request_count eq \"\" } {\n"
        rule_text += "   set request_count 1\n"
        rule_text += "   session add uie $reqkey $request_count "
        rule_text += " $expiration_time\n"
        rule_text += "   session add uie $timekey [expr {$curr_time - 2}]"
        rule_text += " [expr {$expiration_time + 2}]\n"
        rule_text += " } else {\n"
        rule_text += "   set start_time [session lookup uie $timekey]\n"
        rule_text += "   incr request_count\n"
        rule_text += "   session add uie $reqkey $request_count"
        rule_text += " $expiration_time\n"
        rule_text += "   set elapsed_time [expr {$curr_time - $start_time}]\n"
        rule_text += "   if {$elapsed_time < 60} {\n"
        rule_text += "     set elapsed_time 60\n"
        rule_text += "   }\n"
        rule_text += "   set curr_rate [expr {$request_count /"
        rule_text += "($elapsed_time/60)}]\n"
        rule_text += "   if {$curr_rate > $req_limit}{\n"
        rule_text += "     HTTP::respond 503 throttled \"Retry-After\" 60\n"
        rule_text += "   }\n"
        rule_text += " }\n"
        rule_text += "}\n"
        return rule_text

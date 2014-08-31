##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common import constants as const
from f5.common.logger import Log
from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import icontrol_rest_folder
from f5.bigip.bigip_interfaces import strip_folder_and_prefix

from suds import WebFault
import os
import time
import urllib


class VirtualServer(object):

    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(
                                           ['LocalLB.VirtualServer',
                                            'LocalLB.VirtualAddressV2',
                                            'LocalLB.ProfilePersistence',
                                            'LocalLB.ProfileHttp']
                                           )
        # iControl helper objects
        self.lb_vs = self.bigip.icontrol.LocalLB.VirtualServer
        self.lb_va = self.bigip.icontrol.LocalLB.VirtualAddressV2
        self.lb_persist = self.bigip.icontrol.LocalLB.ProfilePersistence
        self.lb_http = self.bigip.icontrol.LocalLB.ProfileHttp

    @icontrol_folder
    @domain_address
    def create(self, name=None, ip_address=None, mask=None,
               port=None, protocol=None, vlan_name=None,
               traffic_group=None, use_snat=True,
               snat_pool=None, folder='Common', preserve_vlan_name=False):

        if not self.exists(name=name, folder=folder):

            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                'Common.VirtualServerDefinition')
            vs_def.name = name

            if str(ip_address).endswith('%0'):
                ip_address = ip_address[:-2]

            vs_def.address = ip_address

            if port:
                vs_def.port = port
            else:
                vs_def.port = 0

            vs_def.protocol = self._get_protocol_type(protocol)
            vs_defs = [vs_def]

            # virtual server resources
            res = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerResource')
            vs_vs_type = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerType')
            res.type = vs_vs_type.RESOURCE_TYPE_POOL
            resources = [res]

            # virtual server profiles
            prof_seq = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerProfileSequence')
            profiles = [prof_seq]

            # virtual server creation
            try:
                self.lb_vs.create(vs_defs, [mask], resources, profiles)
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('VirtualServer',
                        'tried to create a Virtual Server when exists')
                    return False
                else:
                    raise wf

            if use_snat:
                if snat_pool:
                    self.lb_vs.set_snat_pool([name], [snat_pool])
                else:
                    self.lb_vs.set_snat_automap([name])

            # add enabled VLANs
            if vlan_name:
                enabled_state = self.lb_vs.typefactory.create(
                    'Common.EnabledState').STATE_ENABLED
                filter_list = self.lb_vs.typefactory.create(
                    'Common.VLANFilterList')
                filter_list.state = enabled_state
                filter_list.vlans = [vlan_name]

                self.lb_vs.set_vlan([name], [filter_list])

            count = 0
            while not self.virtual_address_exists(named_address=ip_address,
                                                  folder=folder):
                time.sleep(2)
                count += 1
                if count == 5:
                    Log.error('VirtualServer',
                              'Address not found after create')
                    break


            if not traffic_group:
                traffic_group = \
                      const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.lb_va.set_traffic_group([ip_address], [traffic_group])
            return True

    @icontrol_folder
    def create_ip_forwarder(self, name=None, ip_address=None,
                            mask=None, vlan_name=None,
                            traffic_group=None, use_snat=True,
                            snat_pool=None, folder='Common',
                            preserve_vlan_name=False):
        if not self.exists(name=name, folder=folder):
            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                'Common.VirtualServerDefinition')
            vs_def.name = name
            vs_def.address = ip_address
            vs_def.port = 0
            protocol_type = self.lb_vs.typefactory.create(
                                                 'Common.ProtocolType')
            vs_def.protocol = protocol_type.PROTOCOL_ANY
            vs_defs = [vs_def]

            # virtual server resources
            res = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerResource')
            vs_vs_type = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerType')
            res.type = vs_vs_type.RESOURCE_TYPE_IP_FORWARDING
            resources = [res]

            # virtual server profiles
            prof_seq = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerProfileSequence')
            profiles = [prof_seq]

            # virtual server creation
            try:
                self.lb_vs.create(vs_defs, [mask], resources, profiles)
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('VirtualServer',
                        'tried to create a Virtual Server when exists')
                    return False
                else:
                    raise wf

            if use_snat:
                if snat_pool:
                    self.lb_vs.set_snat_pool([name], [snat_pool])
                else:
                    self.lb_vs.set_snat_automap([name])

            # add enabled VLANs
            if vlan_name:
                enabled_state = self.lb_vs.typefactory.create(
                    'Common.EnabledState').STATE_ENABLED
                filter_list = self.lb_vs.typefactory.create(
                    'Common.VLANFilterList')
                filter_list.state = enabled_state
                filter_list.vlans = [vlan_name]

                self.lb_vs.set_vlan([name], [filter_list])

            count = 0
            while not self.virtual_address_exists(named_address=ip_address,
                                                  folder=folder):
                time.sleep(2)
                count += 1
                if count == 5:
                    Log.error('VirtualServer',
                              'Address not found after create')
                    break

            if not traffic_group:
                traffic_group = \
                      const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.lb_va.set_traffic_group([ip_address], [traffic_group])
            return True

    @icontrol_folder
    def create_fastl4(self, name=None, ip_address=None, mask=None,
               port=None, protocol=None, vlan_name=None,
               traffic_group=None, use_snat=True,
               snat_pool=None, folder='Common',
               preserve_vlan_name=False):

        if not self.exists(name=name, folder=folder):

            # virtual server definition
            vs_def = self.lb_vs.typefactory.create(
                'Common.VirtualServerDefinition')
            vs_def.name = name

            if str(ip_address).endswith('%0'):
                ip_address = ip_address[:-2]

            vs_def.address = ip_address

            if port:
                vs_def.port = port
            else:
                vs_def.port = 0

            vs_def.protocol = self._get_protocol_type(protocol)
            vs_defs = [vs_def]

            # virtual server resources
            res = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerResource')
            vs_vs_type = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerType')
            res.type = vs_vs_type.RESOURCE_TYPE_FAST_L4
            resources = [res]

            # virtual server profiles
            prof_seq = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerProfileSequence')
            profiles = [prof_seq]

            # virtual server creation
            try:
                self.lb_vs.create(vs_defs, [mask], resources, profiles)
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('VirtualServer',
                        'tried to create a Virtual Server when exists')
                    return False
                else:
                    raise wf

            if use_snat:
                if snat_pool:
                    self.lb_vs.set_snat_pool([name], [snat_pool])
                else:
                    self.lb_vs.set_snat_automap([name])

            # add enabled VLANs
            if vlan_name:
                enabled_state = self.lb_vs.typefactory.create(
                    'Common.EnabledState').STATE_ENABLED
                filter_list = self.lb_vs.typefactory.create(
                    'Common.VLANFilterList')
                filter_list.state = enabled_state
                filter_list.vlans = [vlan_name]

                self.lb_vs.set_vlan([name], [filter_list])

            count = 0
            while not self.virtual_address_exists(named_address=ip_address,
                                                  folder=folder):
                time.sleep(2)
                count += 1
                if count == 5:
                    Log.error('VirtualServer',
                              'Address not found after create')
                    break

            if not traffic_group:
                traffic_group = \
                      const.SHARED_CONFIG_DEFAULT_FLOATING_TRAFFIC_GROUP
            self.lb_va.set_traffic_group([ip_address], [traffic_group])
            return True

    @icontrol_folder
    def add_profile(self, name=None, profile_name=None,
                    client_context=True, server_context=True,
                    folder='Common'):
        if profile_name.startswith("/Common"):
            profile_name = strip_folder_and_prefix(profile_name)
        Log.debug('VirtualServer', 'Does the following profile exist? %s %s'
                  % (name, profile_name))
        if not self.virtual_server_has_profile(name=name,
                                           profile_name=profile_name,
                                           client_context=client_context,
                                           server_context=server_context,
                                           folder=folder):
            profile_context = 'PROFILE_CONTEXT_TYPE_ALL'
            if client_context and not server_context:
                profile_context = 'PROFILE_CONTEXT_TYPE_CLIENT'
            elif not client_context and server_context:
                profile_context = 'PROFILE_CONTEXT_TYPE_SERVER'
            vsp = self.lb_vs.typefactory.create(
              'LocalLB.VirtualServer.VirtualServerProfile')
            vsp.profile_name = profile_name
            vsp.profile_context = profile_context
            vsp_seq = self.lb_vs.typefactory.create(
              'LocalLB.VirtualServer.VirtualServerProfileSequence')
            vsp_seq.values = [vsp]
            vsp_seq_seq = self.lb_vs.typefactory.create(
              'LocalLB.VirtualServer.VirtualServerProfileSequenceSequence')
            vsp_seq_seq.values = [vsp_seq]
            self.lb_vs.add_profile([name], vsp_seq_seq)
            return True
        else:
            return False

    @icontrol_folder
    def remove_profile(self, name=None, profile_name=None,
                       client_context=True, server_context=True,
                       folder='Common'):
        if profile_name.startswith("/Common"):
            profile_name = strip_folder_and_prefix(profile_name)
        if self.virtual_server_has_profile(name=name,
                                           profile_name=profile_name,
                                           client_context=client_context,
                                           server_context=server_context,
                                           folder=folder):
            profile_context = 'PROFILE_CONTEXT_TYPE_ALL'
            if client_context and not server_context:
                profile_context = 'PROFILE_CONTEXT_TYPE_CLIENT'
            elif not client_context and server_context:
                profile_context = 'PROFILE_CONTEXT_TYPE_SERVER'
            vsp = self.lb_vs.typefactory.create(
              'LocalLB.VirtualServer.VirtualServerProfile')
            vsp.profile_name = profile_name
            vsp.profile_context = profile_context
            vsp_seq = self.lb_vs.typefactory.create(
              'LocalLB.VirtualServer.VirtualServerProfileSequence')
            vsp_seq.values = [vsp]
            vsp_seq_seq = self.lb_vs.typefactory.create(
              'LocalLB.VirtualServer.VirtualServerProfileSequenceSequence')
            vsp_seq_seq.values = [vsp_seq]
            self.lb_vs.remove_profile([name], vsp_seq_seq)
            return True
        else:
            return False

    @icontrol_folder
    def virtual_server_has_profile(self, name=None, profile_name=None,
                       client_context=True,
                       server_context=True,
                       folder='Common'):
        if self.exists(name=name, folder=folder):
            profile_name = strip_folder_and_prefix(profile_name)
            profiles = self.get_profiles(name=name, folder=folder)
            for profile in profiles:
                if profile_name in profile:
                    if client_context and \
                             profile.get(profile_name)['client_context']:
                        return True
                    if server_context and \
                             profile.get(profile_name)['server_context']:
                        return True
            return False
        else:
            return False

    @icontrol_folder
    def http_profile_exists(self, name=None, folder='Common'):
        if name:
            for http_profile in self.lb_vs.get_list():
                if strip_folder_and_prefix(http_profile) == \
                   strip_folder_and_prefix(name):
                    return True
            return False
        else:
            return False

    @icontrol_folder
    def get_profiles(self, name=None, folder='Common'):
        return_profiles = []
        if self.exists(name=name, folder=folder):
            profiles = self.lb_vs.get_profile([name])[0]
            for profile in profiles:
                p = {}
                profile_name = \
                    strip_folder_and_prefix(profile.profile_name)
                p[profile_name] = {}
                if profile.profile_context == "PROFILE_CONTEXT_TYPE_ALL":
                    p[profile_name]['client_context'] = True
                    p[profile_name]['server_context'] = True
                elif profile.profile_context == "PROFILE_CONTEXT_TYPE_CLIENT":
                    p[profile_name]['client_context'] = True
                    p[profile_name]['server_context'] = False
                elif profile.profile_context == "PROFILE_CONTEXT_TYPE_SERVER":
                    p[profile_name]['client_context'] = False
                    p[profile_name]['server_context'] = True
                p[profile_name]['type'] = "'" + profile.profile_type + "'"
                return_profiles.append(p)
        return return_profiles

    @icontrol_folder
    def create_http_profile(self, name=None, xff=True, pipelining=False,
                            unknown_verbs=False, server_agent=None,
                            folder='Common'):
        if not self.http_profile_exists(name=name, folder=folder):
            try:
                self.lb_http.create([name])
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('VirtualServer',
                        'tried to create a HTTP Profile when exists')
                else:
                    raise wf

        enabled_mode = self.lb_http.typefactory.create(
                                    'LocalLB.ProfileProfileMode')
        enabled_mode.value = 'PROFILE_MODE_ENABLED'
        enabled_mode.default_flag = False

        disabled_mode = self.lb_http.typefactory.create(
                                    'LocalLB.ProfileProfileMode')
        disabled_mode.value = 'PROFILE_MODE_ENABLED'
        disabled_mode.default_flag = False

        if xff:
            self.lb_http.set_insert_xforwarded_for_header_mode([name],
                                                               [enabled_mode])
        else:
            self.lb_http.set_insert_xforwarded_for_header_mode([name],
                                                               [disabled_mode])

        if server_agent:
            agent_string = self.lb_http.typefactory.create(
                                                       'LocalLB.ProfileString')
            agent_string.value = server_agent
            agent_string.default_flag = False
            self.lb_http.set_server_agent_name([name], [agent_string])

        if not pipelining or not unknown_verbs:
            major_version = self.bigip.system.get_major_version()
            minor_version = self.bigip.system.get_minor_version()
            if major_version < 11:
                return True
            if minor_version < 5:
                return True
        else:
            return True

        try:
            pt_mode_allow = self.lb_http.typefactory.create(
                                'LocalLB.ProfileHttp.ProfilePassthroughMode')
            pt_mode_allow.value = 'HTTP_PASSTHROUGH_MODE_ALLOW'
            pt_mode_allow.default_flag = False

            pt_mode_reject = self.lb_http.typefactory.create(
                                'LocalLB.ProfileHttp.ProfilePassthroughMode')
            pt_mode_reject.value = 'HTTP_PASSTHROUGH_MODE_REJECT'
            pt_mode_reject.default_flag = False

            if pipelining:
                self.lb_http.set_pipelining_mode_v2([name], [pt_mode_allow])
            else:
                self.lb_http.set_pipelining_mode_v2([name], [pt_mode_reject])

            if unknown_verbs:
                self.lb_http.set_passthrough_unknown_method_mode([name],
                                                            [pt_mode_allow])
            else:
                self.lb_http.set_passthrough_unknown_method_mode([name],
                                                            [pt_mode_reject])
        except Exception as e:
            Log.error('VirtualServer',
                      'Could not set HTTP profile pass-through options %s'
                      % (e.message))

        return True

    @icontrol_folder
    def create_uie_profile(self, name=None, rule_name=None, folder='Common'):
        try:
            self.lb_persist.create([name], ['PERSISTENCE_MODE_UIE'])
            prof_str = \
                self.lb_persist.typefactory.create('LocalLB.ProfileString')
            prof_str.value = rule_name
            prof_str.default_flag = False
            self.lb_persist.set_rule([name], [prof_str])
        except WebFault as wf:
            if "already exists in partition" in str(wf.message):
                Log.error('VirtualServer',
                    'tried to create a UIE persist profile when exists')
                return False
            else:
                raise wf

    @icontrol_rest_folder
    def uie_persist_profile_exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/persistence/universal/'
        request_url += '~' + folder + '~' + name
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False

    def delete_uie_persist_profile(self, name=None, folder='Common'):
        if self.uie_persist_profile_exists(name, folder):
            self.delete_persist_profile(name, folder)

    @icontrol_folder
    def delete_persist_profile(self, name=None, folder='Common'):
        try:
            self.lb_persist.delete_profile([name])
            return True
        except WebFault:
            return False
        return False

    @icontrol_folder
    def virtual_server_has_rule(self, name=None,
                                rule_name=None, folder='Common'):
        for rule in self.lb_vs.get_rule([name])[0]:
            if rule.rule_name == rule_name:
                return True
        return False

    @icontrol_folder
    def add_rule(self, name=None, rule_name=None,
                     priority=500, folder='Common'):
        if self.exists(name=name, folder=folder):
            if not self.virtual_server_has_rule(name=name,
                                                rule_name=rule_name,
                                                folder=folder):
                vs_rule = self.lb_vs.typefactory.create(
                    'LocalLB.VirtualServer.VirtualServerRule')
                vs_rule.rule_name = rule_name
                vs_rule.priority = priority
                vs_rule_seq = self.lb_vs.typefactory.create(
                    'LocalLB.VirtualServer.VirtualServerRuleSequence')
                vs_rule_seq.values = [vs_rule]
                vs_rule_seq_seq = self.lb_vs.typefactory.create(
                    'LocalLB.VirtualServer.VirtualServerRuleSequenceSequence')
                vs_rule_seq_seq.values = [vs_rule_seq]
                self.lb_vs.add_rule([name], vs_rule_seq_seq)
                return True
        return False

    @icontrol_folder
    def remove_rule(self, name=None, rule_name=None,
                    priority=500, folder='Common'):
        if self.exists(name=name, folder=folder):
            if self.virtual_server_has_rule(name=name,
                                            rule_name=rule_name,
                                            folder=folder):
                vs_rule = self.lb_vs.typefactory.create(
                    'LocalLB.VirtualServer.VirtualServerRule')
                vs_rule.rule_name = rule_name
                vs_rule.priority = priority
                vs_rule_seq = self.lb_vs.typefactory.create(
                    'LocalLB.VirtualServer.VirtualServerRuleSequence')
                vs_rule_seq.values = [vs_rule]
                vs_rule_seq_seq = self.lb_vs.typefactory.create(
                    'LocalLB.VirtualServer.VirtualServerRuleSequenceSequence')
                vs_rule_seq_seq.values = [vs_rule_seq]
                self.lb_vs.remove_rule([name], vs_rule_seq_seq)
                return True
        return False

    @icontrol_folder
    def set_persist_profile(self, name=None, profile_name=None,
                                folder='Common'):
        if self.exists(name=name, folder=folder):
            Log.debug('VirtualServer', 'resetting persistence.')
            self.lb_vs.remove_all_persistence_profiles([name])
            if profile_name.startswith('/Common'):
                profile_name = strip_folder_and_prefix(profile_name)
            try:
                vsp = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerPersistence')
                vsp.profile_name = profile_name
                vsp.default_profile = True
                vsp_seq = self.lb_vs.typefactory.create(
                'LocalLB.VirtualServer.VirtualServerPersistenceSequence')
                vsp_seq.values = [vsp]
                vsp_seq_seq = self.lb_vs.typefactory.create(
            'LocalLB.VirtualServer.VirtualServerPersistenceSequenceSequence')
                vsp_seq_seq.values = [vsp_seq]
                Log.debug('VirtualServer', 'adding persistence %s'
                          % profile_name)
                self.lb_vs.add_persistence_profile([name], vsp_seq_seq)
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('VirtualServer',
                    'tried to set source_addr persistence when exists')
                return False
            else:
                raise wf
        else:
            return False

    @icontrol_folder
    def set_fallback_persist_profile(self, name=None, profile_name=None,
                                     folder='Common'):
        if self.exists(name=name, folder=folder):
            if profile_name.startswith('/Common'):
                profile_name = strip_folder_and_prefix(profile_name)
            try:
                self.lb_vs.set_fallback_persistence_profile([name],
                                                            [profile_name])
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('VirtualServer',
                    'tried to set source_addr persistence when exists')
                return False
            else:
                raise wf
        else:
            return False

    @icontrol_folder
    def remove_all_persist_profiles(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.remove_all_persistence_profiles([name])
            return True
        else:
            return False

    @icontrol_folder
    def remove_and_delete_persist_profile(self, name=None,
                                          profile_name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            persist_profiles = self.lb_vs.get_persistence_profile([name])[0]
            fb_profiles = \
                      self.lb_vs.get_fallback_persistence_profile([name])
            profile_names_to_remove = []
            profiles_to_remove = []
            rules_to_remove = []
            for p in persist_profiles:
                if profile_name:
                    if profile_name.startswith('/Common'):
                        profile_name = strip_folder_and_prefix(profile_name)
                    if profile_name == p['profile_name']:
                        rule_name = \
                    self.lb_persist.get_rule([p['profile_name']])[0]['value']
                        if rule_name:
                            rules_to_remove.append(rule_name)
                        profiles_to_remove.append(p)
                        profile_names_to_remove.append(p['profile_name'])
                else:
                    rule_name = \
                     self.lb_persist.get_rule([p['profile_name']])[0]['value']
                    if rule_name:
                            rules_to_remove.append(rule_name)
                    profiles_to_remove.append(p)
                    if not p['profile_name'].startswith('/Common'):
                        profile_names_to_remove.append(p['profile_name'])
            if len(profiles_to_remove) > 0:
                if len(fb_profiles):
                    self.lb_vs.set_fallback_persistence_profile([name], [None])
                vsp_seq = self.lb_vs.typefactory.create(
                 'LocalLB.VirtualServer.VirtualServerPersistenceSequence')
                vsp_seq.values = profiles_to_remove
                vsp_seq_seq = self.lb_vs.typefactory.create(
            'LocalLB.VirtualServer.VirtualServerPersistenceSequenceSequence')
                vsp_seq_seq.values = [vsp_seq]
                self.lb_vs.remove_persistence_profile([name], vsp_seq_seq)
                if len(profile_names_to_remove) > 0:
                    self.lb_persist.delete_profile(profile_names_to_remove)
            if len(rules_to_remove) > 0:
                self.bigip.rule.lb_rule.delete_rule(rules_to_remove)
            return True
        else:
            return False

    @icontrol_folder
    def enable_virtual_server(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_enabled_state([name], ['STATE_ENABLED'])
            return True
        else:
            return False

    @icontrol_folder
    def disable_virtual_server(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_enabled_state([name], ['STATE_DISABLED'])
            return True
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.delete_virtual_server([name])

    @icontrol_folder
    def get_pool(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            pool_name = self.lb_vs.get_default_pool_name([name])[0]
            return strip_folder_and_prefix(pool_name)

    @icontrol_folder
    def set_pool(self, name=None, pool_name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            if self.bigip.pool.exists(name=pool_name, folder=folder):
                self.lb_vs.set_default_pool_name([name], [pool_name])
            elif not pool_name:
                self.lb_vs.set_default_pool_name([name], [''])

    @icontrol_folder
    @domain_address
    def set_addr_port(self, name=None, ip_address=None,
                      port=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            # TODO: virtual server definition in device spec needs a port
            if not port:
                port = 0
            dest = self.lb_vs.typefactory.create('Common.AddressPort')
            dest.address = ip_address
            dest.port = port
            self.lb_vs.set_destination_v2([name], [dest])

    @icontrol_folder
    def get_addr(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return os.path.basename(addr_port.address).split('%')[0]

    @icontrol_folder
    def get_port(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            addr_port = self.lb_vs.get_destination_v2([name])[0]
            return int(addr_port.port)

    @icontrol_folder
    @domain_address
    def set_mask(self, name=None, netmask=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_wildmask([name], [netmask])

    @icontrol_folder
    def get_mask(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_vs.get_wildmask([name])[0]

    @icontrol_folder
    def set_protocol(self, name=None, protocol=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            protocol_type = self._get_protocol_type(protocol)
            self.lb_vs.set_protocol([name], [protocol_type])

    @icontrol_folder
    def get_protocol(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            protocol_type = self.lb_vs.get_protocol([name])[0]

            if protocol_type == 'PROTOCOL_ICMP':
                return 'ICMP'
            elif protocol_type == 'PROTOCOL_UDP':
                return 'UDP'
            else:
                return 'TCP'

    @icontrol_folder
    def set_description(self, name=None, description=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.lb_vs.set_description([name], [description])

    @icontrol_folder
    def get_description(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_vs.get_description([name])[0]

    @icontrol_folder
    def set_traffic_group(self, name=None, traffic_group=None,
                          folder='Common'):
        if self.exists(name=name, folder=folder):
            address_port = self.lb_vs.get_destination_v2([name])[0]
            self._set_virtual_address_traffic_group(named_address=address_port.address,
                                                    folder=folder)

    @icontrol_folder
    def get_traffic_group(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            address_port = self.lb_vs.get_destination_v2([name])[0]
            return self._get_virtual_address_traffic_group(
                                                    named_address=address_port.address,
                                                    folder=folder)
        else:
            Log.error('vs', 'vs does not exist: %s in %s' % (name, folder))

    @icontrol_folder
    def set_connection_limit(self, name=None, connection_limit=0,
                             folder='Common'):
        ulong = self.bigip.int_to_ulong(connection_limit)
        common_ulong = self.lb_vs.typefactory.create('Common.ULong64')
        common_ulong.low = ulong.low
        common_ulong.high = ulong.high
        self.lb_vs.set_connection_limit([name], [common_ulong])

    @icontrol_folder
    def get_connection_limit(self, name=None,
                             folder='Common'):
        return self.bigip.ulong_to_int(
                             self.lb_vs.get_connection_limit([name])[0])

    @icontrol_folder
    def set_snat_automap(self, name=None, folder='Common'):
        self.lb_vs.set_source_address_translation_automap([name])

    @icontrol_folder
    def set_snat_pool(self, name=None, pool_name=None, folder='Common'):
        self.lb_vs.set_source_address_translation_snat_pool([name],
                                                            [pool_name])

    @icontrol_folder
    def remove_snat(self, name=None, folder='Common'):
        self.lb_vs.set_source_address_translation_none([name])

    @icontrol_folder
    def get_statisitcs(self, name=None, folder='Common'):
        stats = self.lb_vs.get_statistics([name])[0][0].statistics
        return_stats = {}
        for stat in stats:
            return_stats[stat.type] = self.bigip.ulong_to_int(stat.value)
        return return_stats

    @icontrol_folder
    def get_virtual_service_insertion(self, folder='Common'):
        virtual_services = []
        vs = self.lb_vs.get_list()
        if len(vs) > 0:
            vd = self.lb_vs.get_destination_v2(vs)
            vn = self.lb_vs.get_wildmask(vs)
            vp = self.lb_vs.get_protocol(vs)
            protocols = {
                         'PROTOCOL_ANY': 'any',
                         'PROTOCOL_TCP': 'tcp',
                         'PROTOCOL_UDP': 'udp',
                         'PROTOCOL_ICMP': 'icmp',
                         'PROTOCOL_SCTP': 'sctp'
                        }
            for i in range(len(vs)):
                name = strip_folder_and_prefix(vs[i])
                address = strip_folder_and_prefix(
                                vd[i]['address']).split('%')[0]
                service = {name: {}}
                service[name]['address'] = address
                service[name]['netmask'] = vn[i]
                service[name]['protocol'] = protocols[vp[i]]
                service[name]['port'] = vd[i]['port']
                virtual_services.append(service)
        return virtual_services

    def _get_protocol_type(self, protocol_str):
        protocol_str = protocol_str.upper()
        protocol_type = self.lb_vs.typefactory.create('Common.ProtocolType')

        if protocol_str == 'ICMP':
            return protocol_type.PROTOCOL_ICMP
        elif protocol_str == 'UDP':
            return protocol_type.PROTOCOL_UDP
        else:
            return protocol_type.PROTOCOL_TCP

    @icontrol_folder
    def _get_virtual_address_traffic_group(self, named_address=None, folder='Common'):
        return self.lb_va.get_traffic_group([named_address])[0]

    @icontrol_folder
    def _set_virtual_address_traffic_group(self, named_address=None, folder='Common'):
        return self.lb_va.get_traffic_group([named_address])[0]

    @icontrol_rest_folder
    def exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/virtual/'
        request_url += '~' + folder + '~' + name
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False
        #if name in self.lb_vs.get_list():
        #    return True
        #else:
        #    return False

    @icontrol_rest_folder
    def virtual_address_exists(self, named_address=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/virtual-address/'
        request_url += '~' + folder + '~' + urllib.quote(named_address)
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False

        #if named_address in self.lb_va.get_list():
        #    return True
        #else:
        #    return False

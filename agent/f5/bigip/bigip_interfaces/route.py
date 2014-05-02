##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common.logger import Log
from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder

from suds import WebFault
import netaddr


class Route(object):
    def __init__(self, bigip):
        self.bigip = bigip
        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['Networking.RouteTableV2',
                                            'Networking.RouteDomainV2'])

        # iControl helper objects
        self.net_route = self.bigip.icontrol.Networking.RouteTableV2
        self.net_domain = self.bigip.icontrol.Networking.RouteDomainV2

    @domain_address
    def create(self, name=None, dest_ip_address=None, dest_mask=None,
               gw_ip_address=None, folder='Common'):
        if not self.exists(name=None, folder=folder) and \
           netaddr.IPAddress(dest_ip_address) and \
           netaddr.IPAddress(gw_ip_address):
            dest = self.net_route.typefactory.create(
                    'Networking.RouteTableV2.RouteDestination')
            dest.address = dest_ip_address
            dest.netmask = dest_mask
            attr = self.net_route.typefactory.create(
                    'Networking.RouteTableV2.RouteAttribute')
            attr.gateway = gw_ip_address
            try:
                self.net_route2.create_static_route([name], [dest], [attr])
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('Route',
                              'tried to create a Route when exists')
                    return False
                else:
                    raise wf
        else:
            return False

    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            self.net_route2.delete_static_route([name])
            return True
        else:
            return False

    def get_vlans_in_domain(self, folder='Common'):
        try:
            return self.net_domain.get_vlan([self._get_domain_name(folder)])[0]
        except WebFault as wf:
            Log.error('Route',
                      'Error getting vlans in rt domain %s: %s' %
                      (self._get_domain_name(folder), str(wf.message)))
            raise wf

    @icontrol_folder
    def add_vlan_to_domain(self, name=None, folder='Common'):
        if not name in self.get_vlans_in_domain(folder):
            rd_entry_seq = self.net_domain.typefactory.create(
                                            'Common.StringSequence')
            rd_entry_seq.values = [name]
            rd_entry_seq_seq = self.net_domain.typefactory.create(
                                            'Common.StringSequenceSequence')
            rd_entry_seq_seq.values = [rd_entry_seq]
            self.net_domain.add_vlan([self._get_domain_name(folder)],
                                     rd_entry_seq_seq)
            return True

    @icontrol_folder
    def create_domain(self, folder='Common'):
        return self._create_domain(folder)

    def _create_domain(self, folder='Common'):
        ids = [self._get_next_domain_id()]
        domains = [self._get_domain_name(folder)]
        self.net_domain.create(domains, ids, [[]])
        if self.bigip.strict_route_isolation:
            strict_state = self.net_domain.typefactory.create(
                                    'Common.EnabledState').STATE_ENABLED
            self.net_domain.set_strict_state(domains, [strict_state])
        else:
            strict_state = self.net_domain.typefactory.create(
                                    'Common.EnabledState').STATE_DISABLED
            self.net_domain.set_strict_state(domains, [strict_state])
            self.net_domain.set_parent(domains, ['/Common/0'])
        return ids[0]

    @icontrol_folder
    def delete_domain(self, folder='Common'):
        if self.domain_exists(folder=folder):
            try:
                domains = [self._get_domain_name(folder)]
                self.net_domain.delete_route_domain(domains)
            except WebFault as wf:
                if "is referenced" in str(wf.message):
                    Log.error('Route', 'delete route domain %s failed %s'
                              % (folder, wf.message))
                    return False
                elif "All objects must be removed" in str(wf.message):
                    Log.error('Route', 'delete route domain %s failed %s'
                              % (folder, wf.message))
                    return False
                else:
                    raise wf
            return True
        else:
            return False

    @icontrol_folder
    def domain_exists(self, folder='Common'):
        return self._domain_exists(folder)

    def _domain_exists(self, folder='Common'):
        domain_name = self._get_domain_name(folder)
        all_route_domains = self.net_domain.get_list()
        if domain_name in all_route_domains:
            return True
        else:
            return False

    @icontrol_folder
    def get_domain(self, folder='Common'):
        try:
            return self.net_domain.get_identifier(
                 [self._get_domain_name(folder)])[0]
        except WebFault as wf:
            if "was not found" in str(wf.message):
                return self.create_domain(folder)

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        if name in self.net_route2.get_static_route_list():
            return True

    def _get_domain_name(self, folder='Common'):
        folder = folder.replace('/', '')
        return '/' + folder + '/' + folder

    def _get_next_domain_id(self):
        self.bigip.system.set_folder('/')
        self.bigip.system.sys_session.set_recursive_query_state(1)
        all_route_domains = self.net_domain.get_list()
        if len(all_route_domains) > 1:
            all_identifiers = sorted(
                self.net_domain.get_identifier(all_route_domains))
            self.bigip.system.set_folder('Common')
            self.bigip.system.sys_session.set_recursive_query_state(0)
        else:
            self.bigip.system.set_folder('Common')
            self.bigip.system.sys_session.set_recursive_query_state(0)
            return 1
        lowest_available_index = 1
        for i in range(len(all_identifiers)):
            if all_identifiers[i] < lowest_available_index:
                if len(all_identifiers) > (i + 1):
                    if all_identifiers[i + 1] > lowest_available_index:
                        return lowest_available_index
                    else:
                        lowest_available_index = lowest_available_index + 1
        else:
            return lowest_available_index

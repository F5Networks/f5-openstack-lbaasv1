##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common.logger import Log
from f5.common import constants as const
from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import icontrol_rest_folder

from suds import WebFault


class SNAT(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(
                                           ['LocalLB.SNATPool',
                                            'LocalLB.SNATTranslationAddressV2']
                                           )

        # iControl helper objects
        self.lb_snatpool = self.bigip.icontrol.LocalLB.SNATPool
        self.lb_snataddress = \
                   self.bigip.icontrol.LocalLB.SNATTranslationAddressV2

    @icontrol_folder
    @domain_address
    def create(self, name=None, ip_address=None,
               traffic_group=None, snat_pool_name=None,
               folder='Common'):

        if not self.exists(name=name, folder=folder):
            if not traffic_group:
                traffic_group = const.SHARED_CONFIG_DEFAULT_TRAFFIC_GROUP
            try:
                self.lb_snataddress.create([name],
                                           [ip_address],
                                           [traffic_group])
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('SNAT',
                              'tried to create a SNAT when exists')
                else:
                    raise wf

        if snat_pool_name:
            if self.pool_exists(name=snat_pool_name, folder=folder):
                self.add_to_pool(name=snat_pool_name,
                             member_name=name,
                             folder=folder)
                return True
            else:
                try:
                    self.create_pool(name=snat_pool_name,
                             member_name=name,
                             folder=folder)
                    return True
                except WebFault as wf:
                    if "already exists in partition" in str(wf.message):
                        Log.error('SNAT',
                                  'tried to create a SNATPool when exists')
                    else:
                        raise wf
        return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            try:
                self.lb_snataddress.delete_translation_address([name])
            except WebFault as wf:
                if "is still referenced by a snat pool" \
                                                           in str(wf.message):
                    Log.debug('SNAT',
                             'Can not delete SNAT address %s ..still in use.'
                             % name)
                    return False
                else:
                    raise wf
            return True
        else:
            # Odd logic compared to other delete.
            # we need this because of the dependency
            # on the SNAT address in other pools
            return True

    @icontrol_folder
    def get_all(self, folder='Common'):
        return self.lb_snataddress.get_list()

    @icontrol_folder
    def create_pool(self, name=None, member_name=None, folder='Common'):
        if not self.pool_exists(name=name, folder=folder):
            string_seq = \
             self.lb_snatpool.typefactory.create('Common.StringSequence')
            string_seq_seq = \
             self.lb_snatpool.typefactory.create(
                                         'Common.StringSequenceSequence')
            string_seq.values = [member_name]
            string_seq_seq.values = [string_seq]
            try:
                self.lb_snatpool.create_v2([name], string_seq_seq)
            except WebFault as wf:
                if "already exists" in str(wf.message):
                    Log.error('SNAT',
                              'SNAT Pool exists but was not in returned list.')
                    self.lb_snatpool.add_member_v2([name], string_seq_seq)
                else:
                    raise
        else:
            existing_members = self.lb_snatpool.get_member_v2([name])[0]
            if not member_name in existing_members:
                string_seq = \
                 self.lb_snatpool.typefactory.create('Common.StringSequence')
                string_seq_seq = \
            self.lb_snatpool.typefactory.create(
                                             'Common.StringSequenceSequence')
                string_seq.values = member_name
                string_seq_seq.values = [string_seq]
                self.lb_snatpool.add_member_v2([name], string_seq_seq)
        return True

    @icontrol_folder
    def add_to_pool(self, name=None, member_name=None, folder='Common'):
        if self.pool_exists(name=name, folder=folder):
            existing_members = self.lb_snatpool.get_member_v2([name])[0]
            if not member_name in existing_members:
                string_seq = \
                 self.lb_snatpool.typefactory.create('Common.StringSequence')
                string_seq_seq = \
            self.lb_snatpool.typefactory.create(
                                             'Common.StringSequenceSequence')
                string_seq.values = member_name
                string_seq_seq.values = [string_seq]
                self.lb_snatpool.add_member_v2([name], string_seq_seq)
        return True

    @icontrol_folder
    def remove_from_pool(self, name=None, member_name=None, folder='Common'):
        existing_members = self.lb_snatpool.get_member_v2([name])[0]
        if member_name in existing_members:
            string_seq = \
             self.lb_snatpool.typefactory.create('Common.StringSequence')
            string_seq_seq = \
        self.lb_snatpool.typefactory.create('Common.StringSequenceSequence')
            string_seq.values = member_name
            string_seq_seq.values = [string_seq]
            try:
                self.lb_snatpool.remove_member_v2([name], string_seq_seq)
                return True
            except WebFault as wf:
                if "must reference at least one translation address" \
                                                           in str(wf.message):
                    Log.debug('SNAT',
                    'removing SNATPool because last member is being removed')
                    self.lb_snatpool.delete_snat_pool([name])
                    return True
        return False

    @icontrol_rest_folder
    def pool_exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/snatpool/'
        request_url += '~' + folder + '~' + name
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False

        #if name in self.lb_snatpool.get_list():
        #    return True
        #else:
        #    return False

    @icontrol_rest_folder
    def exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/snat-translation/'
        request_url += '~' + folder + '~' + name
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False

        #snat_addrs = self.lb_snataddress.get_list()
        #if name in snat_addrs:
        #    return True
        #else:
        #    return False

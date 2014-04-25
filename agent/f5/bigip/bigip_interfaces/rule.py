##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common.logger import Log
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import icontrol_rest_folder

from suds import WebFault


class Rule(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.Rule')

        # iControl helper objects
        self.lb_rule = self.bigip.icontrol.LocalLB.Rule

    @icontrol_folder
    def create(self, name=None, rule_definition=None, folder='Common'):
        if not self.exists(name=name, folder=folder):
            rule_def = self.lb_rule.typefactory.create(
                                        'LocalLB.Rule.RuleDefinition')
            rule_def.rule_name = name
            rule_def.rule_definition = rule_definition
            try:
                self.lb_rule.create([rule_def])
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    Log.error('Rule',
                              'tried to create a Rule when exists')
                    self.update(name=name,
                                rule_definition=rule_definition,
                                folder=folder)
                    return True
                else:
                    raise wf
        else:
            return False

    @icontrol_folder
    def update(self, name=None, rule_definition=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            rule_def = self.lb_rule.typefactory.create(
                                        'LocalLB.Rule.RuleDefinition')
            rule_def.rule_name = name
            rule_def.rule_definition = rule_definition
            self.lb_rule.modify_rule([rule_def])
            return True
        else:
            return False

    @icontrol_folder
    def delete(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            try:
                self.lb_rule.delete_rule([name])
            except WebFault as wf:
                if "is in use" in str(wf.message):
                    return False
            return True
        else:
            return False

    @icontrol_folder
    def get_rule(self, name=None, folder='Common'):
        if self.exists(name=name, folder=folder):
            return self.lb_rule.query_rule([name])[0]
        else:
            return False

    @icontrol_rest_folder
    def exists(self, name=None, folder='Common'):
        request_url = self.bigip.icr_url + '/ltm/rule/'
        request_url += '~' + folder + '~' + name
        request_url += '?$select=name'
        response = self.bigip.icr_session.get(request_url)
        if response.status_code < 400:
            return True
        else:
            return False

        #for rule_name in self.lb_rule.get_list():
        #    if rule_name == name:
        #        return True
        #return False

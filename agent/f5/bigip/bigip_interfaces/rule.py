from f5.common import constants as const
from f5.bigip import exceptions
from f5.bigip.bigip_interfaces import domain_address
from f5.bigip.bigip_interfaces import icontrol_folder
from f5.bigip.bigip_interfaces import strip_folder_and_prefix

from suds import WebFault
import os
import netaddr

import logging

LOG = logging.getLogger(__name__)


class Rule(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interface('LocalLB.Rule')

        # iControl helper objects
        self.lb_rule = self.bigip.icontrol.LocalLB.Rule

    @icontrol_folder
    def create(self, name=None, rule_definition=None, folder='Common'):
        if not self.exists(name, folder):
            rule_def = self.lb_rule.typefactory.create(
                                        'LocalLB.Rule.RuleDefinition')
            rule_def.rule_name = name
            rule_def.rule_definition = rule_definition
            try:
                self.lb_rule.create([rule_def])
                return True
            except WebFault as wf:
                if "already exists in partition" in str(wf.message):
                    LOG.error(_(
                        'tried to create a Rule when exists'))
                    return False
                else:
                    raise wf
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

    @icontrol_folder
    def exists(self, name=None, folder='Common'):
        for rule_name in self.lb_rule.get_list():
            if rule_name == name:
                return True
        return False

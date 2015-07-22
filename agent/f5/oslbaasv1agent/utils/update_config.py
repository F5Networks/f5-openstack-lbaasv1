#!/usr/bin/env python

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
import os
import shutil


def _inplace_change(filename, old_string, new_string):
    s = open(filename).read()
    if old_string in s:
        print("Changing %s to %s" % (old_string, new_string))
        s = s.replace(old_string, new_string)
        f = open(filename, 'w')
        f.write(s)
        f.flush()
        f.close()
    else:
        print("No occurances of %s found." % old_string)


def update_configuration():
    print("checking for old configuration file file format..")
    old_agent_config = '/etc/neutron/f5-bigip-lbaas-agent.ini'
    backup_agent_config = '/etc/neutron/f5-bigip-lbaas-agent.ini.bak'
    dist_agent_config = '/etc/neutron/f5-oslbaasv1-agent.ini.dist'
    new_agent_config = '/etc/neutron/f5-oslbaasv1-agent.ini'

    old_ns_path = 'neutron.services.loadbalancer.drivers.f5.bigip'
    new_ns_path = 'f5.oslbaasv1agent.drivers.bigip'

    if os.path.isfile(old_agent_config):
        print("saving backup of %s to %s" % (old_agent_config,
                                             backup_agent_config))
        shutil.copy2(old_agent_config, backup_agent_config)
        print("saving a clean %s to %s " % (new_agent_config,
                                            dist_agent_config))
        shutil.move(new_agent_config, dist_agent_config)
        print("copying old config %s to %s" % (old_agent_config,
                                               new_agent_config))
        shutil.move(old_agent_config, new_agent_config)
        print ("changing instance of %s in %s to %s" % (old_ns_path,
                                                        new_agent_config,
                                                        new_ns_path))
        _inplace_change(new_agent_config, old_ns_path, new_ns_path)

if __name__ == "__main__":
    update_configuration()

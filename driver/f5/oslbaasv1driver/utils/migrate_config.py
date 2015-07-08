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
import shutil


def migrate_configuration():
    neutron_config = '/etc/neutron/neutron.conf'
    old_ns_path = 'neutron.services.loadbalancer.drivers.f5'
    new_ns_path = 'f5.oslbaasv1driver.drivers'
    print("saving backup of %s to %s" % (neutron_config,
                                         neutron_config + '.bak'))
    shutil.copy2(neutron_config, neutron_config + '.bak')
    print ("changing instance of %s in %s to %s" % (old_ns_path,
                                                    neutron_config,
                                                    new_ns_path))
    _inplace_change(neutron_config, old_ns_path, new_ns_path)


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


if __name__ == "__main__":
    migrate_configuration()

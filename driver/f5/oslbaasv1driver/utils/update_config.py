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
import os


def update_configuration():
    neutron_config = '/etc/neutron/neutron.conf'
    lbaas_config = '/etc/neutron/neutron_lbaas.conf'
    old_ns_path = 'neutron.services.loadbalancer.drivers.f5'
    new_ns_path = 'f5.oslbaasv1driver.drivers'
    old_conf_line = 'service_provider=LOADBALANCER:F5:' + \
                    old_ns_path + \
                    '.plugin_driver.F5PluginDriver'
    new_conf_line = 'service_provider=LOADBALANCER:F5:' + \
                    new_ns_path + \
                    '.plugin_driver.F5PluginDriver'
    if os.path.isfile(neutron_config):
        service_providers = _service_providers(_read_file(neutron_config))
        if old_conf_line in service_providers:
            _backup_file(neutron_config)
            _inplace_change(neutron_config, old_ns_path, new_ns_path)
        if new_conf_line not in service_providers:
            _add_service_provider(neutron_config, '# ' + new_conf_line)
    if os.path.isfile(lbaas_config):
        service_providers = _service_providers(_read_file(lbaas_config))
        if old_conf_line in service_providers:
            _backup_file(lbaas_config)
            _inplace_change(lbaas_config, old_ns_path, new_ns_path)
        if new_conf_line not in service_providers:
            _add_service_provider(lbaas_config, '# ' + new_conf_line)


def _backup_file(filename):
    print("saving backup of %s to %s" % (filename,
                                         filename + '.bak'))
    shutil.copy2(filename, filename + '.bak')


def _read_file(filename):
    with open(filename) as f:
        return f.readlines()
    f.close()


def _service_providers(content):
    in_section = False
    providers = []
    for line in content:
        if str(line).startswith('[service_providers]'):
            in_section = True
            continue
        if in_section:
            if not str(line).startswith('['):
                if str(line).startswith('#'):
                    line = line[1:]
                providers.append(str(line).strip())
            else:
                in_section = False
    return providers


def _add_service_provider(filename, configline):
    if not str(configline).endswith('\n'):
        configline = configline + '\n'
    f = open(filename, "r")
    contents = f.readlines()
    f.close()
    in_providers = False
    for i in range(len(contents)):
        if str(contents[i]).startswith('[service_providers]'):
            in_providers = True
            continue
        if in_providers:
            if not str(contents[i]).startswith('#'):
                contents.insert(i, configline)
                break
    f = open(filename, "w")
    contents = "".join(contents)
    f.write(contents)
    f.close()


def _inplace_change(filename, old_string, new_string):
    print ("searching for instances of %s in %s to %s" % (old_string,
                                                          filename,
                                                          new_string))
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
    update_configuration()

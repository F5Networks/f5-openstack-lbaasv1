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
import sys
import os


def print_usage():
    message = '\nUsage:\n'
    message += '   generate_env.py [provider_name] [environment_prefix]\n\n'
    message += '      provider_name - lowercase string which is visible for\n'
    message += '       the tenant to select the environment.\n'
    message += '      environment_prefix - string used to prefix objects in\n'
    message += '       in the environment as well as used in the RPC queues.\n'
    print(message)


def add_service_provider(filename, configline):
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


def generate_driver(provider_name, environment_prefix):
    my_path = os.path.dirname(__file__)

    mn = "plugin_driver_" + str(environment_prefix).title()

    driver_module_filename = \
        my_path + '/../drivers/' + \
        mn + '.py'

    if os.path.isfile(driver_module_filename):
        print("ERROR: plugin module %s already exists"
              % driver_module_filename)
        sys.exit(1)

    cln = "F5PluginDriver" + str(environment_prefix).title()
    mf = open(driver_module_filename, 'w')
    mf.write("from f5.oslbaasv1driver.drivers")
    mf.write(".plugin_driver import F5PluginDriver\n\n\n")
    mf.write("class " + cln + "(F5PluginDriver):\n")
    mf.write("    \"\"\" Plugin Driver for ")
    mf.write(environment_prefix + " environment\"\"\"\n\n")
    mf.write("    def __init__(self, plugin, env='")
    mf.write(environment_prefix + "'):\n")
    mf.write("        super(" + cln + ", self).__init__(plugin, env)\n")
    mf.close()

    confline = "# service_provider=LOADBALANCER:"
    confline += str(provider_name).upper()
    confline += ":f5.oslbaasv1driver.drivers."
    confline += mn
    confline += "." + cln

    lb_conf = '/etc/neutron/neutron_lbaas.conf'
    neutron_conf = '/etc/neutron/neutron.conf'

    if os.path.isfile(lb_conf):
        add_service_provider(lb_conf, confline)
    elif os.path.isfile(neutron_conf):
        add_service_provider(neutron_conf, confline)
    else:
        print('\n\nAdd the following line to your config file:\n')
        print(confline)
        print('\n\n')

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print_usage()
        exit(1)
    generate_driver(sys.argv[1], sys.argv[2])

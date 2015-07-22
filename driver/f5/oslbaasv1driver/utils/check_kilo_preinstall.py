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
import subprocess

required_kilo_packages = ['python-neutron', 'python-neutron-lbaas']


def is_kilo_install():
    cmd = ['rpm', '-q', 'python-neutron']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    (res, stat) = p.communicate()  # @UnusedVariable
    try:
        kilo_index = str(res).index('2015.')
        if kilo_index > 0:
            return True
    except ValueError:
        return False


def check_required_kilo_packages():
    if is_kilo_install():
        cmd = ['rpm', '-qa', '--qf', '%{NAME}\n']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        (res, stat) = p.communicate()  # @UnusedVariable
        package_list = res.split()
        for package in package_list:
            if package in required_kilo_packages:
                required_kilo_packages.remove(package)

        if required_kilo_packages:
            print('the following required packages are not installed: %s'
                  % required_kilo_packages)
            sys.exit(-1)

if __name__ == "__main__":
    check_required_kilo_packages()

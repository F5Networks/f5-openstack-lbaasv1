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
import sys

from distutils.core import setup

version = os.environ['VERSION']
release = os.environ['RELEASE']
project_dir = os.environ['PROJECT_DIR']

data_files = [('/usr/share/doc/f5-oslbaasv1-driver',
               [project_dir + '/doc/f5-oslbaasv1-readme.pdf',
                project_dir + '/SUPPORT'])]

if 'bdist_deb' in sys.argv:
    stdebcfg = open('stdeb.cfg', 'w')
    stdebcfg.write('[DEFAULT]\n')
    stdebcfg.write('Package: f5-oslbaasv1-driver\n')
    stdebcfg.write('Debian-Version: ' + release + '\n')
    stdebcfg.write('Depends: f5-bigip-common, neutron-server\n')
    stdebcfg.close()

setup(
    name='f5-oslbaasv1-driver',
    version=version,
    description='F5 LBaaSv1 Driver for OpenStack',
    long_description='F5 LBaaSv1 Driver for OpenStack',
    license='Apache License, Version 2.0',
    author='F5 DevCentral',
    author_email='devcentral@f5.com',
    url='http://devcentral.f5.com/openstack',
    py_modules=['f5.oslbaasv1driver.drivers.agent_scheduler',
                'f5.oslbaasv1driver.drivers.plugin_driver',
                'f5.oslbaasv1driver.drivers.rpc'],
    packages=['f5.oslbaasv1driver',
              'f5.oslbaasv1driver.drivers',
              'f5.oslbaasv1driver.utils'],
    data_files=data_files)

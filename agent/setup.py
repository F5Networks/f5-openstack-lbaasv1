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

from distutils.core import setup

version = os.environ['VERSION']
release = os.environ['RELEASE']
project_dir = os.environ['PROJECT_DIR']

data_files = [('/usr/bin',
               [project_dir + '/agent/usr/bin/f5-bigip-lbaas-agent']),
              ('/etc/neutron',
               [project_dir + '/agent/etc/neutron/f5-bigip-lbaas-agent.ini']),
              ('/usr/share/doc/f5-bigip-lbaas-agent',
               [project_dir + '/doc/f5lbaas-readme.pdf',
                project_dir + '/SUPPORT'])]

if 'bdist_rpm' in sys.argv:
    os.environ['ADD_INIT_STARTUP_SCRIPT'] = 'true'

if 'bdist_deb' in sys.argv:
    stdebcfg = open('stdeb.cfg', 'w')
    stdebcfg.write('[DEFAULT]\n')
    stdebcfg.write('Package: f5-bigip-lbaas-agent\n')
    stdebcfg.write('Debian-Version: ' + release + '\n')
    stdebcfg.close()

if 'ADD_INIT_STARTUP_SCRIPT' in os.environ:
    data_files.append(('/etc/init.d',
                [project_dir + '/agent/etc/init.d/f5-bigip-lbaas-agent']))

setup(name='f5-bigip-lbaas-agent',
      description='F5 LBaaS Agent for OpenStack',
      version=version,
      author='F5 DevCentral',
      author_email='devcentral@f5.com',
      url='http://devcentral.f5.com/openstack',
      py_modules=[
         'neutron.services.loadbalancer.drivers.f5.bigip.agent',
         'neutron.services.loadbalancer.drivers.f5.bigip.agent_api',
         'neutron.services.loadbalancer.drivers.f5.bigip.agent_manager',
         'neutron.services.loadbalancer.drivers.f5.bigip.constants',
         'neutron.services.loadbalancer.drivers.f5.bigip.icontrol_driver'],
      packages=[
         'f5',
         'f5.common',
         'f5.bigip',
         'f5.bigip.bigip_interfaces',
         'f5.bigip.pycontrol'],
         data_files=data_files
     )

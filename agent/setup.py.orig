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

from distutils.core import setup
import platform

data_files = [('/usr/bin', ['usr/bin/f5-bigip-lbaas-agent']),
             ('/etc/neutron', ['etc/neutron/f5-bigip-lbaas-agent.ini'])]

dist = platform.dist()[0]
if dist == 'centos' or dist == 'redhat':
    data_files.append(('/etc/init.d', ['etc/init.d/f5-bigip-lbaas-agent']))

setup(name='f5-bigip-lbaas-agent',
      version='1.0.5.icehouse-1',
      description='F5 LBaaS Agent for OpenStack',
      author='F5 DevCentral',
      author_email='devcentral@f5.com',
      url='http://devcentral.f5.com/f5',
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

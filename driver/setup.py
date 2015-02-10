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

data_files = [('/usr/share/doc/f5-lbaas-driver',
               [project_dir + '/doc/f5lbaas-readme.pdf',
                project_dir + '/SUPPORT'])]

if 'bdist_deb' in sys.argv:
    stdebcfg = open('stdeb.cfg', 'w')
    stdebcfg.write('[DEFAULT]\n')
    stdebcfg.write('Package: f5-lbaas-driver\n')
    stdebcfg.write('Debian-Version: ' + release + '\n')
    stdebcfg.close()

setup(name='f5-lbaas-driver',
      version=version,
      description='F5 LBaaS Driver for OpenStack',
      long_description='F5 LBaaS Driver for OpenStack',
      license='Apache License, Version 2.0',
      author='F5 DevCentral',
      author_email='devcentral@f5.com',
      url='http://devcentral.f5.com/openstack',
      packages=['neutron.services.loadbalancer.drivers.f5',
                'neutron.services.loadbalancer.drivers.f5.log'],
      data_files=data_files
     )

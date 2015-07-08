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
               [project_dir + '/agent/usr/bin/f5-oslbaasv1-agent']),
              ('/etc/neutron',
               [project_dir + '/agent/etc/neutron/f5-oslbaasv1-agent.ini']),
              ('/usr/share/doc/f5-oslbaasv1-agent',
               [project_dir + '/doc/f5-oslbaasv1-readme.pdf',
                project_dir + '/SUPPORT'])]

if 'bdist_rpm' in sys.argv:
    os.environ['ADD_INIT_STARTUP_SCRIPT'] = 'true'

if 'bdist_deb' in sys.argv:
    stdebcfg = open('stdeb.cfg', 'w')
    stdebcfg.write('[DEFAULT]\n')
    stdebcfg.write('Package: f5-oslbaasv1-agent\n')
    stdebcfg.write('Debian-Version: ' + release + '\n')
    stdebcfg.write('Depends: f5-bigip-common\n')
    stdebcfg.close()

if 'ADD_INIT_STARTUP_SCRIPT' in os.environ:
    data_files.append(
        ('/etc/init.d',
         [project_dir + '/agent/etc/init.d/f5-oslbaasv1-agent'])
    )
    data_files.append(
        ('/etc/systemd/system',
         [project_dir +
          '/agent/etc/systemd/system/f5-oslbaasv1-agent.service'])
    )

setup(name='f5-oslbaasv1-agent',
      description='F5 LBaaSv1 Agent for OpenStack',
      long_description='F5 LBaaSv1 Agent for OpenStack',
      license='Apache License, Version 2.0',
      version=version,
      author='F5 DevCentral',
      author_email='devcentral@f5.com',
      url='http://devcentral.f5.com/openstack',
      py_modules=[
                  'f5.oslbaasv1agent.drivers.bigip.agent',
                  'f5.oslbaasv1agent.drivers.bigip.agent_api',
                  'f5.oslbaasv1agent.drivers.bigip.agent_manager',
                  'f5.oslbaasv1agent.drivers.bigip.constants',
                  'f5.oslbaasv1agent.drivers.bigip.rpc',
                  'f5.oslbaasv1agent.drivers.bigip.fdb_connector',
                  'f5.oslbaasv1agent.drivers.bigip.fdb_connector_ml2',
                  'f5.oslbaasv1agent.drivers.bigip.lbaas_driver',
                  'f5.oslbaasv1agent.drivers.bigip.icontrol_driver',
                  'f5.oslbaasv1agent.drivers.bigip.lbaas',
                  'f5.oslbaasv1agent.drivers.bigip.lbaas_iapp',
                  'f5.oslbaasv1agent.drivers.bigip.lbaas_bigip',
                  'f5.oslbaasv1agent.drivers.bigip.lbaas_bigiq',
                  'f5.oslbaasv1agent.drivers.bigip.l3_binding',
                  'f5.oslbaasv1agent.drivers.bigip.l2',
                  'f5.oslbaasv1agent.drivers.bigip.network_direct',
                  'f5.oslbaasv1agent.drivers.bigip.pools',
                  'f5.oslbaasv1agent.drivers.bigip.selfips',
                  'f5.oslbaasv1agent.drivers.bigip.snats',
                  'f5.oslbaasv1agent.drivers.bigip.tenants',
                  'f5.oslbaasv1agent.drivers.bigip.vcmp',
                  'f5.oslbaasv1agent.drivers.bigip.vips',
                  'f5.oslbaasv1agent.drivers.bigip.constants',
                  'f5.oslbaasv1agent.utils.migrate_config'
      ],
      packages=['f5.oslbaasv1agent',
                'f5.oslbaasv1agent.drivers',
                'f5.oslbaasv1agent.drivers.bigip',
                'f5.oslbaasv1agent.utils'],
      data_files=data_files,
      package_data={
          'f5.oslbaasv1agent': ['iapps/*']
      },
      classifiers=['Development Status :: 5 - Production/Stable',
                   'License :: OSI Approved :: Apache Software License',
                   'Environment :: OpenStack',
                   'Operating System :: OS Independent',
                   'Programming Language :: Python',
                   'Intended Audience :: System Administrators',
                   'Intended Audience :: Telecommunications Industry']
      )

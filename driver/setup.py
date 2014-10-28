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

setup(name='f5-lbaas-driver',
      version='1.0.5.icehouse-1',
      description='F5 LBaaS Driver for OpenStack',
      author='John Gruber',
      author_email='j.gruber@f5.com',
      url='http://devcentral.f5.com/f5',
      packages=['neutron.services.loadbalancer.drivers.f5',
                'neutron.services.loadbalancer.drivers.f5.log'],
     )

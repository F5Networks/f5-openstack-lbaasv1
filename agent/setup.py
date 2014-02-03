#!/usr/bin/env python

from distutils.core import setup

setup(name='f5-bigip-lbaas-agent',
      version='1.0',
      description='F5 LBaaS Agent for OpenStack',
      author='John Gruber',
      author_email='j.gruber@f5.com',
      url='http://devcentral.f5.com/f5',
      py_modules=['neutron.services.loadbalancer.drivers.f5.bigip.agent',
                  'neutron.services.loadbalancer.drivers.f5.bigip.agent_api',
                  'neutron.services.loadbalancer.drivers.f5.bigip.agent_manager',
                  'neutron.services.loadbalancer.drivers.f5.bigip.icontrol_driver'],
      packages=  ['f5', 'f5.common', 'f5.bigip', 'f5.bigip.bigip_interfaces', 'f5.bigip.pycontrol'],
      data_files=[('/usr/bin', ['usr/bin/f5-bigip-lbaas-agent']),
                  ('/etc/neutron', ['etc/neutron/f5-bigip-lbaas-agent.ini'])]

     )


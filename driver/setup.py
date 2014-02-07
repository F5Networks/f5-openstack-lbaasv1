#!/usr/bin/env python

from distutils.core import setup

setup(name='f5-lbaas-driver',
      version='1.0',
      description='F5 LBaaS Driver for OpenStack',
      author='John Gruber',
      author_email='j.gruber@f5.com',
      url='http://devcentral.f5.com/f5',
      packages=['neutron.services.loadbalancer.drivers.f5',
                'neutron.services.loadbalancer.drivers.f5.log'],
     )

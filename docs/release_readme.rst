f5-openstack-lbaasv1
====================

Release Version
---------------

**1.0.12**

Compatibility
-------------

+-------------------------------------+--------------------------+
| Product                             | Version(s)               |
+=====================================+==========================+
| OpenStack LBaaSv1                   | Havana - Kilo            |
+-------------------------------------+--------------------------+
| BIG-IP                              | 11.5.x, 11.6.x, 12.0.x   |
+-------------------------------------+--------------------------+
| Red Hat Enterprise Linux / CentOS   | 6, 7                     |
+-------------------------------------+--------------------------+
| Ubuntu                              | 12.04, 14.04             |
+-------------------------------------+--------------------------+

Package Contents
----------------

-  Release Readme (this document)
-  Support.md
-  build

   -  deb\_dist : Ubuntu installation files
   -  el6 : Red Hat / CentOS 6 installation files
   -  el7 : Red Hat / CentOS 7 installation files

Installation
------------

Prerequisites:
~~~~~~~~~~~~~~

-  OpenStack Neutron network deployment
-  Licensed BIG-IP (hardware or virtual edition)

Red Hat / CentOS
~~~~~~~~~~~~~~~~

1. Install the F5 BIG-IP common libraries.

   ::

       # rpm -ivh f5-bigip-common_1.0.12.noarch.el7.rpm

2. Install the plugin driver.

   ::

       # rpm -i f5-lbaas-driver-1.0.12.noarch.el7.rpm 

3. Install the agent.

   ::

       # rpm -i f5-bigip-lbaas-agent-1.0.12.noarch.el7.rpm

Ubuntu
~~~~~~

1. Install the F5 BIG-IP common libraries.

   ::

       # dpkg -i f5-bigip-common_1.0.12_all.deb

2. Install the plugin driver.

   ::

       # dpkg -i f5-lbaas-driver_1.0.12_all.deb

3. Install the plugin agent.

   ::

       # dpkg -i f5-bigip-lbaas-agent_1.0.12_all.deb

Contact
-------

f5\_openstack\_lbaasv1@f5.com

Copyright
---------

Copyright 2016 F5 Networks Inc.

Support
-------

See Support.md.

License
-------

Apache V2.0
-----------

Licensed under the Apache License, Version 2.0 (the "License"); you may
not use this file except in compliance with the License. You may obtain
a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the `License <http://www.apache.org/licenses/LICENSE-2.0>`__ for the
specific language governing permissions and limitations under the
License.

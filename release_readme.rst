Release Information
===================

**TIP: Don't want to read the raw version of this document? View it online at http://f5-openstack-lbaasv1.readthedocs.org/en/latest/.**

Release Version
---------------

1.0.14-final

Compatibility
-------------

+-------------------------------------+--------------------------+
| Product                             | Version(s)               |
+=====================================+==========================+
| OpenStack LBaaSv1                   | Icehouse - Kilo          |
+-------------------------------------+--------------------------+
| BIG-IP®                             | 11.5.x, 11.6.x, 12.0.x   |
+-------------------------------------+--------------------------+
| Red Hat Enterprise Linux / CentOS   | 6, 7                     |
+-------------------------------------+--------------------------+
| Ubuntu                              | 12.04, 14.04             |
+-------------------------------------+--------------------------+


Package Contents
----------------
-  Release Readme (this document)
-  SUPPORT.md
-  build

   -  deb_dist : Ubuntu installation files
   -  el6 : Red Hat / CentOS 6 installation files
   -  el7 : Red Hat / CentOS 7 installation files

Overview
--------

The F5® OpenStack LBaaSv1 plugin allows you to orchestrate BIG-IP® load balancing services – including virtual IPs, pools, device service groups, and health monitoring – in an OpenStack environment.

Before You Begin
----------------

You will need the following to use the F5® OpenStack LBaaSv1 plugin.

-  Licensed BIG-IP® (hardware or virtual edition)
-  OpenStack Icehouse - Kilo Neutron network deployment

.. note::

    In order to use the Neutron command set, you need source a user file
    that has admin permissions.

    .. code-block:: text

        $ source keystonerc_admin


Installation
------------

Debian / Ubuntu
```````````````

1. Install the F5® BIG-IP® common libraries.

   .. code-block:: text

      # dpkg -i build/deb_dist/f5-bigip-common_1.0.14-final_all.deb

2. Install the plugin driver.

   .. code-block:: text

      # dpkg -i build/deb_dist/f5-lbaas-driver_1.0.14-final_all.deb

3. Install the plugin agent.

   .. code-block:: text

      # dpkg -i build/deb_dist/f5-bigip-lbaas-agent_1.0.14-final_all.deb


Red Hat / CentOS
````````````````

1. Install the F5® BIG-IP® common libraries.
   
   .. code-block:: text

      # rpm -i build/el7/f5-bigip-common_1.0.14-final.noarch.el7.rpm

2. Install the plugin driver.
  
   .. code-block:: text

      # rpm -i build/el7/f5-lbaas-driver-1.0.14-final.noarch.el7.rpm

3. Install the agent.
  
   .. code-block:: text

      # rpm -i build/el7/f5-bigip-lbaas-agent-1.0.14-final.noarch.el7.rpm


Upgrading
---------

If you are upgrading from an earlier version, F5® recommends that you uninstall the current version before installing the new version.

.. note::

    Perform the following steps on every server running the F5® agent.


1. Make a copy of the F5® agent configuration file. An existing configuration file in */etc/neutron* will be overwritten during installation.

    .. code-block:: text

        # cp /etc/neutron/f5-oslbaasv1-agent.ini ~/

2. Stop and remove the old version of the libraries, plugin driver and agent.

    **Debian/Ubuntu**

    .. code-block:: text

        # service f5-oslbaasv1-agent stop
        # dpkg -r f5-bigip-common f5-lbaas-driver f5-bigip-lbaas-agent

    **Red Hat/CentOS**

    .. code-block:: text

        # service f5-oslbaasv1-agent stop
        # yum remove f5-bigip-common.noarch f5-oslbaasv1-agent.noarch f5-oslbaasv1-driver.noarch

3. Follow the installation instructions in the `previous section <#installation>`_.

4. Restore the F5® agent configuration file.

   Compare the backup file with the new one created during installation to make sure only the necessary settings for your deployment are modified. Then, copy your configuration file back into */etc/neutron/*.

    .. code-block:: text

        # sudo cp ~/f5-oslbaasv1-agent.ini /etc/neutron/f5-oslbaasv1-agent.ini


Copyright
---------
Copyright 2013-2016 F5 Networks, Inc.

Support
-------
See SUPPORT.md.

License
-------

Apache V2.0
```````````
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
ou may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
implied.
See the License for the specific language governing permissions and
limitations under the License.



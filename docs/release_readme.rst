Release Information
===================

Release Version
---------------

|release|

Compatibility
-------------

.. include:: includes/ref_compatibility.rst
    :start-line: 3

Package Contents
----------------
-  Release Readme (this document)
-  Support.md
-  build
   -  deb_dist : Ubuntu installation files
   -  el6 : Red Hat / CentOS 6 installation files
   -  el7 : Red Hat / CentOS 7 installation files

Overview
--------

.. include:: includes/concept_overview-brief.rst
    :start-line: 3

Before You Begin
----------------

You will need the following to use the F5® OpenStack LBaaSv1 plugin.

-  Licensed BIG-IP® (hardware or virtual edition)
-  OpenStack |openstack| Neutron network deployment

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

      # dpkg -i build/deb_dist/f5-bigip-common_1.0.12-final_all.deb

2. Install the plugin driver.

   .. code-block:: text

      # dpkg -i build/deb_dist/f5-lbaas-driver_1.0.12-final_all.deb

3. Install the plugin agent.

   .. code-block:: text

      # dpkg -i build/deb_dist/f5-bigip-lbaas-agent_1.0.12-final_all.deb

Red Hat / CentOS
````````````````

1. Install the F5® BIG-IP® common libraries.
   
   .. code-block:: text

      # rpm -i build/el7/f5-bigip-common_1.0.12-final.noarch.el7.rpm

2. Install the plugin driver.
  
   .. code-block:: text

      # rpm -i build/el7/f5-lbaas-driver-1.0.12-final.noarch.el7.rpm

3. Install the agent.
  
   .. code-block:: text

      # rpm -i build/el7/f5-bigip-lbaas-agent-1.0.12-final.noarch.el7.rpm

Upgrading
---------

If you are upgrading from an earlier version, F5® recommends that you uninstall the current version before installing the new version.

.. note::

    Perform the following steps on every server running the F5® agent.


1. Make a copy of the F5® agent configuration file. An existing configuration file in */etc/neutron* will be overwritten during installation.

.. code-block:: text

    # cp /etc/neutron/f5-oslbaasv1-agent.ini ~/

2. Stop and remove the old version of the libraries, plugin driver and agent.

.. topic:: Debian / Ubuntu

    .. code-block:: text

        # service f5-oslbaasv1-agent stop
        # dpkg -r f5-bigip-common f5-lbaas-driver f5-bigip-lbaas-agent

.. topic::  Red Hat / CentOS

   .. code-block:: text

        # service f5-oslbaasv1-agent stop
        # yum remove f5-bigip-common.noarch f5-oslbaasv1-agent.noarch f5-oslbaasv1-driver.noarch

3. Follow the installation instructions in the `previous section <#installation>`_.

4. Restore the F5® agent configuration file.

   Compare the backup file with the new one created during installation to make sure only the necessary settings for your deployment are modified. Then, copy your configuration file back into */etc/neutron/*.

.. code-block:: text

    # sudo cp ~/f5-oslbaasv1-agent.ini /etc/neutron/f5-oslbaasv1-agent.ini


.. include:: ../README.rst
    :start-line: 134
    :end-line: 165

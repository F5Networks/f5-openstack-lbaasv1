Deploying the F5® OpenStack LBaaSv1 Plugin
------------------------------------------

.. include:: includes/topic_deployment-intro.rst

Before you begin
````````````````
.. include:: release_readme.rst
    :start-line: 32
    :end-line: 46

Downloads
`````````
You can download a `release package <https://github.com/F5Networks/f5-openstack-lbaasv1/releases>`_ directly from GitHub using ``curl`` or ``wget``. Then, un-tar the package into the location of your choice.

.. topic:: Example:

    .. code-block:: text

        # curl -L -O https://github.com/F5Networks/f5-openstack-lbaasv1/releases/download/1.0.12final/f5-lbaasv1_1.0.12final.tgz
        # tar -xf f5-lbaasv1_1.0.12final.tgz


Installation
````````````
Debian/Ubuntu
~~~~~~~~~~~~~
.. include:: release_readme.rst
    :start-line: 52
    :end-line: 70

RedHat/CentOS
~~~~~~~~~~~~~
.. include:: release_readme.rst
    :start-line: 73
    :end-line: 91

Upgrading
`````````
.. include:: release_readme.rst
    :start-line: 94
    :end-line: 132


.. _configure-lbaasv1-plugin:

Configuration
`````````````
.. include:: includes/topic_configure-lbaasv1-agent.rst

.. include:: includes/topic_configure-neutron-service.rst

.. include:: includes/topic_set-agent-scheduler.rst

.. include:: includes/topic_restart-neutron-service.rst

.. include:: includes/topic_restart-http-service.rst

.. include:: includes/topic_start-the-agent.rst

Once the agent has been installed and configured, you can use the :ref:`Neutron agent commands <neutron-agent-commands>` to manage it.

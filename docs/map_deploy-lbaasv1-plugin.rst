.. _deploy-lbaasv1-plugin:

Deploying the F5® OpenStack LBaaSv1 Plugin
------------------------------------------

.. include:: includes/topic_deployment-intro.rst

.. _before-you-begin:

Before you begin
````````````````
.. include:: ../release_readme.rst
    :start-line: 40
    :end-line: 54

.. _downloads:

Downloads
`````````
You can download a `release package <https://github.com/F5Networks/f5-openstack-lbaasv1/releases>`_ directly from GitHub using ``curl`` or ``wget``. Then, un-tar the package into the location of your choice.

.. topic:: Example:

    .. code-block:: text

        # curl -L -O https://github.com/F5Networks/f5-openstack-lbaasv1/releases/download/1.0.14final/f5-lbaasv1_1.0.14final.tgz
        # tar -xf f5-lbaasv1_1.0.14final.tgz

.. _installation:

Installation
````````````
.. _install-deb:

Debian/Ubuntu
~~~~~~~~~~~~~
.. include:: ../release_readme.rst
    :start-line: 64
    :end-line: 83

.. _install-rpm:

RedHat/CentOS
~~~~~~~~~~~~~
.. include:: ../release_readme.rst
    :start-line: 86
    :end-line: 105

.. _upgrade-package:

Upgrading
`````````
.. include:: ../release_readme.rst
    :start-line: 108
    :end-line: 148


.. _configure-lbaasv1-plugin:

Configuration
`````````````
.. _configure-lbaasv1-agent:

.. include:: includes/topic_configure-lbaasv1-agent.rst

.. _configure-neutron-service:

.. include:: includes/topic_configure-neutron-service.rst

.. _set-agent-scheduler:

.. include:: includes/topic_set-agent-scheduler.rst

.. _restart-neutron-service:

.. include:: includes/topic_restart-neutron-service.rst

.. _restart-http-service:

.. include:: includes/topic_restart-http-service.rst

.. _start-the-agent:

.. include:: includes/topic_start-the-agent.rst

Once the agent has been installed and configured, you can use the :ref:`Neutron agent commands <neutron-agent-commands>` to manage it.

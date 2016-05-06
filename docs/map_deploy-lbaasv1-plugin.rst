.. _deploy-lbaasv1-plugin:

Deploying the F5® OpenStack LBaaSv1 Plugin
------------------------------------------

.. include:: includes/topic_deployment-intro.rst

.. _before-you-begin:

Before you begin
````````````````
.. include:: ../release_readme.rst
    :start-line: 33
    :end-line: 47

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
    :start-line: 53
    :end-line: 72

.. _install-rpm:

RedHat/CentOS
~~~~~~~~~~~~~
.. include:: ../release_readme.rst
    :start-line: 75
    :end-line: 94

.. _upgrade-package:

Upgrading
`````````
.. include:: ../release_readme.rst
    :start-line: 97
    :end-line: 137


.. _configure-lbaasv1-plugin:

Configuration
`````````````

.. include:: includes/topic_configure-lbaasv1-agent.rst

.. include:: includes/topic_configure-neutron-service.rst

.. include:: includes/topic_set-agent-scheduler.rst

.. include:: includes/topic_restart-neutron-service.rst

.. include:: includes/topic_restart-http-service.rst

.. include:: includes/topic_start-the-agent.rst

.. seealso::

    Once the agent has been installed and configured, you can use the :ref:`Neutron agent commands <neutron-agent-commands>` to manage it.

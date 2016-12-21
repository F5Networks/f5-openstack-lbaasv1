.. _deploy-lbaasv1-plugin:

Deploying the F5® OpenStack LBaaSv1 Plugin
------------------------------------------

.. include:: includes/topic_deployment-intro.rst

.. _before-you-begin:

Before you begin
````````````````
.. include:: ../release_readme.rst
    :start-line: 45
    :end-line: 60


.. _downloads:

Downloads
`````````
.. include:: includes/topic_downloads.rst
    :start-line: 5

.. _installation:

Installation
````````````

.. _install-deb:

Debian/Ubuntu
~~~~~~~~~~~~~

.. include:: ../release_readme.rst
    :start-line: 66
    :end-line: 85


.. _install-rpm:

RedHat/CentOS
~~~~~~~~~~~~~
.. include:: ../release_readme.rst
    :start-line: 88
    :end-line: 107


.. _upgrade-package:

Upgrading
`````````
.. include:: ../release_readme.rst
    :start-line: 110
    :end-line: 150



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

    Once the agent has been installed and configured, you can use the :ref:`Neutron agent commands <map_neutron-agent-commands>` to manage it.

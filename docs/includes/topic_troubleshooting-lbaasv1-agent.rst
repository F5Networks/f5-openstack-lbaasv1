Troubleshooting the F5® LBaaSv1 Agent
`````````````````````````````````````

If the ``f5-oslbaasv1-agent`` doesn't appear when you run ``neutron agent-list``, the agent is not running.

The options below can be useful for troubleshooting:

* Check the logs:

.. code-block:: text

    # less /var/log/neutron/f5-oslbaasv1-agent.log

* Check the status of the f5-os-lbaasv1-agent service:

.. code-block:: text

    # systemctl status f5-oslbaasv1-agent \\ RedHat/CentOS
    # service f5-oslbaasv1-agent status   \\ Debian/Ubuntu

* Make sure you don't have more than one agent running on the same host with the same ``environment_prefix``.

.. code-block:: text

    # environment_prefix = uuid \\ This is the default setting

* Make sure the iControl® hostname, username, and password in the config file are correct and that you can actually connect to the BIG-IP®.

* Make sure the VTEP lines in the config file are commented (#) out if you're not using VTEP.

.. code-block:: text

    #
    #f5_vtep_folder = 'Common'
    #f5_vtep_selfip_name = 'vtep'
    #

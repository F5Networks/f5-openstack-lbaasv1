Default Environment Options
```````````````````````````

The F5® OpenStack LBaaSv1 plugin allows for the use of three default environment names - test, dev, and prod. As shown in the excerpt from :file:`/etc/neutron/f5-oslbaasv1-agent.ini` below, the service provider entries in :file:`/etc/neutron/neutron_lbaas` correspond to each agent's unique ``environment_prefix``.

.. code-block:: shell

    # For a test environment:
    #
    # Set your agent's environment_prefix to 'test'
    #
    # and add the following line to your LBaaS service_provider config
    # on the neutron server:
    #
    # service_provider = LOADBALANCER:TEST:f5.oslbaasv1driver.drivers.plugin_driver.F5®PluginDriverTest
    #
    # For a dev environment:
    #
    # Set your agent's environment_prefix to 'dev'
    #
    # and add the following line to your LBaaS service_provider config
    # on the neutron server:
    #
    # service_provider = LOADBALANCER:DEV:f5.oslbaasv1driver.drivers.plugin_driver.F5®PluginDriverDev
    #
    # For a prod environment:
    #
    # Set your agent's environment_prefix to 'prod'
    #
    # and add the following line to your LBaaS service_provider config
    # on the neutron server:
    #
    # service_provider = LOADBALANCER:PROD:f5.oslbaasv1driver.drivers.plugin_driver.F5®PluginDriverProd


After making changes to  :file:`/etc/neutron/f5-oslbaasv1-agent.ini` and :file:`/etc/neutron/neutron_lbaas`, restart the ``neutron-server`` process.

.. code-block:: shell

    # service neutron-server restart

Run ``neutron agent-list`` to view the list of active agents on your host to verify that the agent is up and running. If you do not see the ``f5-oslbaasv1-agent`` listed, you may need to restart the service.

.. code-block:: shell

    # service f5-oslbaasv1-agent restart

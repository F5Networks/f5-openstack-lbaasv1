Custom Environments
```````````````````

You can use a driver-generating module to create custom environments. On each Neutron controller which will host your custom environment, run the following command:

.. code-block:: shell

    # python -m f5.oslbaasv1driver.utils.generate_env.py provider_name environment_prefix


.. topic:: Example: Add the custom environment 'DFW1'.

    .. code-block:: shell

        # python -m f5.oslbaasv1driver.utils.generate_env.py DFW1 DFW1

    The command creates a driver class and a corresponding ``service_provider`` entry in :file:`/etc/neutron/neutron_lbaas`.

    .. code-block:: shell

        # service_provider = LOADBALANCER:DFW1:f5.oslbaasv1driver.drivers.plugin_driver_Dfw1.F5®PluginDriverDfw1

    Remove the comment (`#`) from the beginning of the new ``service_provider`` line to activate the driver.

    Then, restart the ``neutron-server`` service.

    .. code-block:: shell

        # service neutron-server restart


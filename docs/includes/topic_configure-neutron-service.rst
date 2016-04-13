Configuring the Neutron Service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Neutron service settings are found in :file:`/etc/neutron/neutron_lbaas.conf`. Edit the ``Default`` and ``Service Providers`` sections as shown below to tell Neutron to use the F5® LBaaSv1 service provider driver.

.. note::

    In the service providers section, the ``f5.os.lbaasv1driver`` entry will be present, but commented out.
    **Uncomment this line to identify the F5® plugin as the LBaaSv1 service provider.**
    Add ``:default`` to the end of the line as shown below to set it as the default LBaaSv1 service provider.

    .. code-block:: text

        # vi /etc/neutron/neutron_lbaas.conf
        [DEFAULT]
        loadbalancer_plugin = neutron.services.loadbalancer.plugin.LoadBalancerPlugin
        ...
        [service providers]
        service_provider = LOADBALANCER:F5:f5.oslbaasv1driver.drivers.plugin_driver.F5PluginDriver:default

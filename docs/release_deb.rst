Configuration - Ubuntu
======================

Version
-------

F5 OpenStack LBaaSv1 plugin v |release| for OpenStack |openstack|.

Before you begin
----------------

In order to use the Neutron command set, you need source a user file
that has admin permissions. (for example, ``source keystonerc_admin``).

Configure the F5 LBaaSv1 Plugin
-------------------------------

#. Configure the agent (*/etc/neutron/f5-oslbaasv1-agent.ini*).

#. Configure the Neutron service to use the F5 plugin.
   
   **NOTE:** In the service providers section, the ``f5.oslbaasv1driver`` entry will most
   likely be present, but commented out. *Uncomment this line and
   comment out the HA proxy line to identify the F5 plugin as the LBaaS
   service provider.*  Add ':default' to the end of the line as shown
   below to set it as the default LBaaS service.

   .. code-block:: shell

        # vi /etc/neutron/neutron_lbaas.conf
        [DEFAULT]
        loadbalancer_plugin = neutron.services.loadbalancer.plugin.LoadBalancerPlugin
        ...
        [service providers]
        service_provider = LOADBALANCER:F5:f5.oslbaasv1driver.drivers.plugin_driver.F5PluginDriver:default

#. Restart the neutron service:
   
   .. code-block:: shell

        # service neutron-server restart

#. Restart the http service:
   
   .. code-block:: shell

        # service apache2 restart

#. Start the agent:
   
   .. code-block:: shell

        # service f5-oslbaasv1-agent start

To check the status of the agent:
   
   .. code-block:: shell

        # neutron agent-list
        # neutron agent-show <agent_id>


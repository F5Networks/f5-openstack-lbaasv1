Configuration - Ubuntu
======================

Version
-------

F5® OpenStack LBaaSv1 plugin **v1.0.14-final** for OpenStack **Icehouse - Kilo**.

Configure the F5® LBaaSv1 Plugin
--------------------------------

1. Configure the agent (*/etc/neutron/f5-oslbaasv1-agent.ini*).

    **NOTE:** You must at minimum set the iControl® address, username, and password for the BIG-IP®(s) you will be managing and identify if the BIG-IP® is internal or external (i.e., running within your stack or outside of it).

    .. code-block:: text

        # vi /etc/neutron/f5-oslbaasv1-agent.ini
        ...
        #
        f5_device_type = external
        #
        ...
        #
        icontrol_hostname = 192.168.1.245
        #
        icontrol_username = admin
        #
        icontrol_password = admin
        #
        ...

2. Configure the Neutron service to use the F5® plugin.
   
   **NOTE:** In the service providers section, the ``f5.oslbaasv1driver`` entry will most
   likely be present, but commented out. *Uncomment this line and
   comment out the HA proxy line to identify the F5® plugin as the LBaaS
   service provider.*  Add ``:default`` to the end of the line as shown
   below to set F5 as the default LBaaS service provider.

    .. code-block:: text

        # vi /etc/neutron/neutron_lbaas.conf
        [DEFAULT]
        loadbalancer_plugin = neutron.services.loadbalancer.plugin.LoadBalancerPlugin
        ...
        [service providers]
        service_provider=LOADBALANCER:F5:f5.oslbaasv1driver.drivers.plugin_driver.F5PluginDriver:default

3. Restart the neutron service:
   
    .. code-block:: text

        # service neutron-server restart

4. Enable LBaaS on the Controller Node

    **NOTE:** This step may be necessary in Icehouse and Juno. It is not needed in Kilo.

    .. code-block:: text

        # vi local_settings.py
        OPENSTACK_NEUTRON_NETWORK = { 'enable_lb': True, ...}"

5. Restart the http service:
   
    .. code-block:: text

        # service apache2 restart

6. Start the agent:
   
    .. code-block:: text

        # service f5-oslbaasv1-agent start


**TIP:** Use the commands shown below to check if the agent is running.
   
    .. code-block:: text

        # neutron agent-list
        # neutron agent-show <agent_id>

For more information, please see the `project documentation <http://f5-openstack-lbaasv1.readthedocs.org/en/latest/>`_.


Copyright
---------
Copyright 2013-2016 F5 Networks, Inc.

Support
-------
See SUPPORT.md.

License
-------

Apache V2.0
```````````
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
ou may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
implied.
See the License for the specific language governing permissions and
limitations under the License.

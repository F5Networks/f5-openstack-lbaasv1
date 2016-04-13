Running Multiple Agents on the Same Host
````````````````````````````````````````

.. warning::

    You should never run two agents *for the same environment* on the same host, as the hostname is used to help Neutron distinguish between agents. Multiple agent processes for *different environments* -- meaning each agent is associated with a different iControl endpoint -- can run on the same host.

.. topic:: To configure multiple agents on the same host:

    1. Create a new environment.

    .. code-block:: text

        python -m f5.oslbaasv1driver.utils.generate_env dsc4 dsc4


    2. Add a service provider driver entry in :file:`/etc/neutron/neutron_lbaas` to activate the new environment.

    .. code-block:: text
        :emphasize-lines: 8

        [service_providers]
        # Must be in form:
        # service_provider=<service_type>:<name>:<driver>[:default]
        # List of allowed service types includes LOADBALANCER
        # Combination of <service type> and <name> must be unique; <driver> must also be unique
        # This is multiline option
        # service_provider=LOADBALANCER:name:lbaas_plugin_driver_path:default
        service_provider=LOADBALANCER:DSC4:f5.oslbaasv1driver.drivers.plugin_driver_Dsc4.F5PluginDriverDsc4
        service_provider=LOADBALANCER:F5:f5.oslbaasv1driver.drivers.plugin_driver.F5PluginDriver
        service_provider=LOADBALANCER:Haproxy:neutron_lbaas.services.loadbalancer.drivers.haproxy.plugin_driver.HaproxyOnHostPluginDriver:default


    3. Create a unique configuration file for each agent.

    .. code-block:: text

        # cd /etc/neutron
        # cp f5-oslbaasv1-agent.conf f5-oslbaasv1-agent-dsc4.conf

    4. Edit the new config file as needed.

    .. note::

        Each agent configuration file must have a unique iControl® endpoint.

    5. Create additional ``upstart``, ``init.d``, or ``systemd`` service definitions for additional agents, using the default service definitions as a guide.

    **Example: Ubuntu**

    .. code-block:: text

        # cd /etc/init
        # cp f5-oslbaasv1-agent.conf f5-oslbaasv1-agent-dsc4.conf

        \\ Edit the new agent start config file
        # exec start-stop-daemon --start --chuid neutron --exec /usr/bin/f5-oslbaasv1-agent --config-file=/etc/neutron/f5-oslbaasv1-agent-dsc4.ini --config-file=/etc/neutron/neutron.conf --log-file=/var/log/neutron/f5-oslbaasv1-agent-dsc4.log

    6. Start the new agent using the name of its unique ``upstart``, ``init.d``, or ``systemd`` service name.

    .. code-block:: text

        # service f5-oslbaasv1-agent-dsc4 start

    7. Restart ``neutron-server``.

    .. code-block:: text

        # service neutron-server restart


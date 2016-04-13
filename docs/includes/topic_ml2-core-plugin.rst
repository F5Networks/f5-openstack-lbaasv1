ML2 Core Plugin
```````````````

Neutron is configured to use the `ML2 <https://wiki.openstack.org/wiki/Neutron/ML2>`_ core plugin by default. This configuration should appear in :file:`/etc/neutron/neutron.conf` as shown below.

    .. code-block:: shell

        core_plugin = neutron.plugins.ml2.plugin.Ml2Plugin


Differentiated Services and Scale Out
-------------------------------------

The F5® LBaaSv1 plugin supports deployments where multiple BIG-IP® environments are required. In a differentiated service environment, each F5® driver will work as described above **with the exception** that each environment has its own messaging queue. The Tenant scheduler for each environment only considers agents within that environment. Configuring multiple environments with corresponding distinct ``neutron_lbaas`` service provider entries is the only way to allow a tenant to select its environment through the LBaaS API. The first section of :file:`/etc/neutron/f5-oslbaasv1-agent.ini` provides information regarding configuration of multiple environments.

.. topic:: To configure differentiated LBaaSv1 provisioning:

    1. Install the agent and driver on each host that requires LBaaSv1 provisioning.

    2. Assign the agent an environment-specific name in :file:`/etc/neutron/f5-oslbaasv1-agent.ini`.

    3. Create a service provider entry for each agent in :file:`/etc/neutron/neutron_lbaas` that corresponds to the unique agent name you assigned.

.. warning::

    A differentiated BIG-IP® environment can not share anything. This precludes the use of vCMP for differentiated environments because vCMP guests share global VLAN IDs.



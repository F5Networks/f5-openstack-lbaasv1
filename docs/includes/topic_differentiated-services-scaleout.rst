.. _differentiated-services-scaleout:

Differentiated Services and Scale Out
-------------------------------------

The F5® LBaaSv1 plugin supports deployments where multiple BIG-IP® environments are required. In a differentiated service environment, the F5® driver for each environment has its own messaging queue. The tenant scheduler for each environment can only assign tasks to agents running in that environment.

.. tip::

    The first section of the F5® agent config file - :file:`/etc/neutron/f5-oslbaasv1-agent.ini` - provides information regarding the configuration of multiple environments.

.. topic:: To configure differentiated LBaaSv1 provisioning:

    1. Install the agent and driver on each host that requires LBaaSv1 provisioning.

    2. Assign an environment-specific name to the F5® agent in :file:`/etc/neutron/f5-oslbaasv1-agent.ini`.

    3. Create a service provider entry corresponding to each agent's unique name in :file:`/etc/neutron/neutron_lbaas` .


.. warning::

    A differentiated BIG-IP® environment can not share anything. This precludes the use of vCMP for differentiated environments because vCMP guests share global VLAN IDs.


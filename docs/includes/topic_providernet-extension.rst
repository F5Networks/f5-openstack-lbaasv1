Providernet Extension
`````````````````````
The Neutron ``providernet`` extension allows you to configure a provider network that can be mapped directly to an existing physical network.

The F5® LBaaSv1 agent uses ``providernet`` attributes to establish an L2 connection to BIG-IP® devices. If your Neutron network doesn't use the ``providernet`` extension, the F5® agent will not be able to correctly provision L2 isolation and tenancy on your BIG-IP® devices.

.. topic:: To see if your Neutron networks support the providernet extension:

    .. tip::

        The \*starred\* attributes must be present for the agent to function properly.

    .. code-block:: text

        # neutron net-show <network_name>
        +-----------------------------+--------------------------------------+
        | Field                       | Value                                |
        +-----------------------------+--------------------------------------+
        | admin_state_up              | True                                 |
        | id                          | 07f92400-4bb6-4ebc-9b5e-eb8ffcd5b34c |
        | name                        | Provider-VLAN-62                     |
        | *provider:network_type*     | vlan                                 |
        | *provider:physical_network* | ph-eth3                              |
        | *provider:segmentation_id*  | 62                                   |
        | router:external             | False                                |
        | shared                      | True                                 |
        | status                      | ACTIVE                               |
        | subnets                     | a89aa39e-3a8e-4f2f-9b57-45aa052b87bf |
        | tenant_id                   | 3aef8f59a43943359932300f634513b3     |
        +-----------------------------+--------------------------------------+


.. seealso::

    - `OpenStack Networking Guide - Provider networks with Open vSwitch <http://docs.openstack.org/kilo/networking-guide/scenario_provider_ovs.html>`_ (Kilo)
    - `OpenStack Administrator Guide <http://docs.openstack.org/admin-guide/networking_adv-features.html>`_

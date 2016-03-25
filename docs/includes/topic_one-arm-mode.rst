One-Arm Mode
````````````

In one-arm mode, VIP and Members can be provisioned from the same
Neutron subnet.

.. code-block:: shell

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini settings      |
    +======================================+======================================+
    | One-arm                              | f5_global_routed_mode = False        |
    |                                      | f5_snat_mode = True                  |
    |                                      |                                      |
    |                                      | optional settings:                   |
    |                                      | f5_snat_addresses_per_subnet = n     |
    |                                      |                                      |
    |                                      | where if n is 0, the virtual server  |
    |                                      | will use AutoMap SNAT. If n is > 0,  |
    |                                      | n number of SNAT addresses will be   |
    |                                      | allocated from the Member subnet per |
    |                                      | active traffic group.                |
    +--------------------------------------+--------------------------------------+

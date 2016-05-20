Multiple-Arm mode
`````````````````

Multiple-arm mode is, essentially, multiple one-arm deployments. In each arm, VIPs and members are provisioned from a specific Neutron subnet.

.. code-block:: shell

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | Multiple-arm                         | f5_global_routed_mode = False        |
    |                                      | f5_snat_mode = True                  |
    |                                      |                                      |
    |                                      | optional settings:                   |
    |                                      | f5_snat_addresses_per_subnet = n     |
    |                                      |                                      |
    |                                      | where if n is 0, the virtual server  |
    |                                      | will use AutoMap SNAT. If n is > 0,  |
    |                                      | n number of SNAT addresses will be   |
    |                                      | allocated from the member subnet per |
    |                                      | active traffic group.                |
    +--------------------------------------+--------------------------------------+




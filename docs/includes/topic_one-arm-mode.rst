One-Arm Mode
````````````

In a one-arm deployment, BIG-IP® has a single (hence, one-arm) connection to the router. VIPs and members are provisioned from a single Neutron subnet. Use of SNATs is required; you can opt to either allocate SNAT addresses automatically, or specify a number of SNAT addresses to make available from the subnet's existing IP address pool (``f5_snat_addresses_per_subnet``).

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
    |                                      | allocated from the member subnet per |
    |                                      | active traffic group.                |
    +--------------------------------------+--------------------------------------+

.. seealso::

    * `BIG-IP TMOS: Implementations > Configuring a One-Arm Deployment <https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-implementations-12-0-0/33.html?sr=53479995>`_
    * `BIG-IP TMOS: Routing Administration > NATs and SNATs <https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-routing-administration-12-0-0/8.html?sr=53483459>`_


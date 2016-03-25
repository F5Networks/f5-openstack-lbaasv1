Gateway Routed Mode
```````````````````

In gateway routed mode, attemps will be made to create a default gateway
forwarding service on the BIG-IP® Device Service Group for Member Neutron
subnets.

.. code-block:: text

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | Gateway routed mode                  | f5_global_routed_mode = False        |
    |                                      | f5_snat_mode = False                 |
    |                                      |                                      |
    +--------------------------------------+--------------------------------------+

For the Neutron network topologies requiring dynamic L2 and L3
provisioning of the BIG-IP® devices -- **which includes all network topologies
except global routed mode** -- the F5® LBaaSv1 iControl® driver supports the following:

-  Provider VLANs - VLANs defined by the admin tenant and shared with other tenants
-  Tenant VLANs - VLANs defined by the admin tenant *for* other tenants, or defined
   by the tenants themselves
-  Tenant GRE Tunnels - GRE networks defined by the tenant
-  Tenant VxLAN Tunnels - VxLAN networks defined by the tenant


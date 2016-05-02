L2 Adjacent Mode
````````````````

.. important::

    L2 adjacent mode is the default mode.

In L2 adjacent mode, the F5® agent provisions L2 networks -- including VLANs and overlay tunnels -- by associating a specific BIG-IP® device with each tenant network that has a VIP or pool member. L3 addresses for BIG-IP® `SelfIPs`_ and `SNATs`_ are dynamically allocated from Neutron tenant subnets associated with LBaaSv1 VIPs or members. VIP listeners are restricted to their designated Neutron tenant network.

L2 adjacent mode follows the `micro-segmentation <https://devcentral.f5.com/articles/microservices-versus-microsegmentation>`__ security model for gateways. Since each BIG-IP® device is L2-adjacent to all tenant networks for which LBaaSv1 objects are provisioned, the traffic flows do not logically pass through another L3 forwarding device. Instead, traffic flows are restricted to direct L2 communication between the cloud network element and the BIG-IP®.

.. code-block:: shell

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | L2 Adjacent mode                     | f5_global_routed_mode = False        |
    +--------------------------------------+--------------------------------------+



.. _SelfIPs: https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-routing-administration-12-0-0/6.html#conceptid
.. _SNATs: https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-routing-administration-12-0-0/8.html#unique_427846607

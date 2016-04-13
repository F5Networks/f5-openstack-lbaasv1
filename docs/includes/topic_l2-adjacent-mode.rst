L2 Adjacent Mode
````````````````
.. note::

    L2 adjacent mode is the default mode.

In L2 adjacent mode, the F5® OpenStack LBaaSv1 agent attempts to provision L2 networks -- including VLANs and overlay tunnels -- by associating a specific BIG-IP® device with each tenant network that has a VIP or pool member. VIP listeners are restricted to their designated Neutron tenant network. L3 addresses associated with pool members are automatically allocated from Neutron subnets.

L2 adjacent mode follows the `micro-segmentation <https://devcentral.f5.com/articles/microservices-versus-microsegmentation>`__ security model for gateways. Since each BIG-IP® device is L2-adjacent to all tenant networks for which LBaaSv1 objects are provisioned, the traffic flows do not logically pass through another L3 forwarding device. Instead, traffic flows are restricted to direct L2 communication between the cloud network element and the BIG-IP® devices.

.. code-block:: shell

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | L2 Adjacent mode                     | f5_global_routed_mode = False        |
    +--------------------------------------+--------------------------------------+

Because the agents manage the BIG-IP® device associations for many tenant
networks, L2 adjacent mode is a much more complex orchestration. It
dynamically allocates L3 addresses from Neutron tenant subnets for BIG-IP®
SelfIPs and SNAT translation addresses. These additional L3 addresses
are allocated from the Neutron subnets associated with LBaaSv1 VIPs or
Members.

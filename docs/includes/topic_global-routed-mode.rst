Global routed mode
``````````````````

In global routed mode, all VIPs are assumed routable from clients and all members are assumed routable from  BIG-IP®. All L2 and L3 objects, including routes, must be pre-provisioned on the BIG-IP® prior to provisioning LBaaSv1 services.

Global routed mode uses BIG-IP® `AutoMap SNAT®`_ for all VIPs. Because no explicit SNAT pools are defined, you should create enough `SelfIP`_ addresses to handle anticipated connection loads.

.. warning::

    In global routed mode, there is no network segregation between tenant services on the BIG-IP®. Likewise, overlapping IP address spaces for tenant objects is not available.


.. code-block:: shell

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | Global Routed mode                   | f5_global_routed_mode = True         |
    +--------------------------------------+--------------------------------------+


.. _AutoMap SNAT®: https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-routing-administration-12-0-0/8.html#unique_1573359865
.. _SelfIP: https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-routing-administration-12-0-0/6.html#conceptid

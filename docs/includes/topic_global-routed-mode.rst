Global routed mode
``````````````````

In global routed mode, all VIPs are assumed routable from clients and
all Members are assumed routable from the BIG-IP® devices themselves. All
L2 and L3 objects, including routes, must be pre-provisioned on the BIG-IP®
Device Service Group prior to LBaaSv1 provisioning.

.. code-block:: shell

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | Global Routed mode                   | f5_global_routed_mode = True         |
    +--------------------------------------+--------------------------------------+

Global routed mode uses BIG-IP® AutoMap SNAT® for all VIPs. Because no
explicit SNAT pools are being defined, sufficient Self IP addresses
should be created to handle connection loads.

.. warning::

    In global routed mode, because all access to and from the
    BIG-IP® devices is assumed globally routed, there is no network segregation
    between tenant services on the BIG-IP® devices themselves. Overlapping IP
    address spaces for tenant objects is likewise not available.

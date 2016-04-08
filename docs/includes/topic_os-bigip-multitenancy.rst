OpenStack and BIG-IP® Multi-tenancy
-----------------------------------

BIG-IP®'s multi-tenancy functionality allows you to create partitions for individual tenants. By default, new objects are always created in the ``/Common`` partition. By creating tenant partitions, you can provision BIG-IP® services as needed for individual projects.

.. topic:: To configure the F5® agent for multi-tenancy:

    1. Edit :file:`/etc/neutron/f5-oslbaasv1-agent.ini`.

        .. code-block:: text

            ###############################################################################
            #  L3 Segmentation Mode Settings
            ###############################################################################
            #
            ...
            #
            f5_global_routed_mode = False
            #
            # Allow overlapping IP subnets across multiple tenants.
            # This creates route domains on big-ip in order to
            # separate the tenant networks.
            #
            # This setting is forced to False if
            # f5_global_routed_mode = True.
            #
            use_namespaces = True
            #
            # When use_namespaces is True there is normally only one route table
            # allocated per tenant. However, this limit can be increased by
            # changing the max_namespaces_per_tenant variable. This allows one
            # tenant to have overlapping IP subnets.
            ...
            #
            max_namespaces_per_tenant = 1
            #
            # Dictates the strict isolation of the routing
            # tables.  If you set this to True, then all
            # VIPs and Members must be in the same tenant
            # or less they can't communicate.
            #
            # This setting is only valid if use_namespaces = True.
            #
            f5_route_domain_strictness = False
            #
            ...


..    If the Neutron network associated with a VIP or member is set to be shared (``shared=True``) and the F5® LBaaSv1 agent is set to ``f5_global_routed_mode = False``, all L2 and L3 objects are created in the ``/Common`` administrative partition and associated with route domain 0 (zero) on all BIG-IP® devices.

.. todo:: investigate whether neutron network has to be set to ``shared=True`` or ``shared=False`` when using multi-tenancy.

.. seealso::

    * BIG-IP® <https://support.f5.com/kb/en-us/products/big-ip_ltm/manuals/product/tmos-routing-administration-12-0-0/9.html#conceptid>`_
OpenStack and BIG-IP® Multinenancy
----------------------------------

By default, all BIG-IP® objects are created in administrative partitions associated with the OpenStack ``tenant_id`` for the pool. If the :file:`/etc/neutron/f5-oslbaasv1-agent.ini` setting for ``use_namespaces`` is set to ``True``, and :ref:`global routed mode <global-routed-mode>` is set to ``False``, a BIG-IP® route domain is created for each tenant. This provides segmentation for IP address spaces between tenants.

If an associated Neutron network for a VIP or member is shown as ``shared=True`` and the F5® LBaaSv1 agent is not in :ref:`global routed mode <global-routed-mode>`, all associated L2 and L3 objects are created in the ``/Common`` administrative partition and associated with route domain 0 (zero) on all BIG-IP® devices.


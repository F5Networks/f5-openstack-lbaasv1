Overview
````````

The F5® agent supports a variety of network topologies, configurable on either BIG-IP® hardware or Virtual Edition (VE).

.. important::

    Throughout our documentation, we refer to 'overcloud' and 'undercloud' deployments.

    :dfn:`overcloud`
        - BIG-IP® is deployed within your OpenStack cloud;
        - requires a BIG-IP® VE;
        - typically uses :ref:`Global Routed Mode <global-routed-mode>`.

    :dfn:`undercloud`
        - BIG-IP® is deployed outside of your OpenStack cloud;
        - can use either physical devices or VE;
        - requires :ref:`L2-Adjacent Mode <l2-adjacent-mode>` to tunnel (VXLAN or GRE) traffic between the BIG-IP® and tenants in the cloud.

The F5® LBaaSv1 plugin supports the following Neutron network topologies which require dynamic L2 and L3
provisioning of BIG-IP® devices.

-  :dfn:`Provider VLANs` - VLANs defined by the admin tenant and shared with other tenants
-  :dfn:`Tenant VLANs` - VLANs defined by the admin tenant *for* other tenants, or defined by the tenants themselves
-  :dfn:`Tenant GRE Tunnels` - GRE networks defined by the tenant
-  :dfn:`Tenant VxLAN Tunnels` - VxLAN networks defined by the tenant


VLANs
`````

For VLAN connectivity, the F5® BIG-IP® devices use a mapping between the
Neutron ``network provider:physical_network`` attribute and TMM
interface names. This is analogous to the Open vSwitch agents mapping
between the Neutron ``network provider:physical_network`` and the
interface bridge name. The mapping is created in :file:`/etc/neutron/f5-oslbaasv1-agent.ini`, using the ``f5_external_physical_mappings`` setting. The name of the ``provider:physical_network`` entries can be added to a comma separated
list with mappings to the TMM interface or LAG trunk name, and a boolean
attribute to specify if 802.1q tagging will be applied.

.. topic:: Example 1

    This configuration maps the ``provider:physical_network`` containing 'ph-eth3' to TMM
    interface 1.1 with 802.1q tagging.

    .. code-block:: text

        f5_external_physical_mappings = ph-eth3:1.1:True

A default mapping should be included for cases where the ``provider:physical_network`` does not match any configuration settings. A default mapping simply uses the word 'default' instead of a known ``provider:physical_network`` attribute.


.. topic:: Example 2.

    The configuration below includes the previously illustrated ``ph-eth3`` map, a default map, and LAG trunk mapping.

    .. code-block:: text

        f5_external_physical_mappings = default:1.1:True, ph-eth3:1.1:True, ph-eth4:lag-trunk-1:True


.. warning::

    The default Open vSwitch Neutron networking does not support VLAN tagging by guest instances. Each guest interface is treated as an access port and all VLAN tags will be stripped before frames reach the physical network infrastructure. To allow a BIG-IP® VE guest to function in L2 Adjacent mode using VLANs as your tenant network type, the software networking infrastructure which strips VLAN tags from frames must be bypassed.

    You can bypass the software bridge using the ``ip``, ``brctl``, and ``ovs-vsctl`` commands on the compute node after the BIG-IP® VE guest instances have been created. This process is **not** automated by any Neutron agent. This requirement only applies to BIG-IP® VE when running as a Nova guest instance.

VLANs
`````

In order to establish connectivity between a BIG-IP® and VLAN, you need to map an interface on the BIG-IP® to an interface on the physical network. In the example below, the BIG-IP interface 1.1 is mapping to the eth0 interface on the hypervisor on which it's running; in turn, eth0 maps to the bridges that provide connectivity from the compute node to the VLAN. The external bridge (br-ex) should have a corresponding ``provider:physical_network`` attribute.

.. seealso::

    F5 OpenStack Configuration Guide: Configure the Neutron Network -> `Configure the Bridge <http://f5-openstack-docs.readthedocs.io/en/1.0/guides/map_neutron-network-initial-setup.html#configure-the-ovs-bridge>`_.

.. topic:: To create the mapping, edit :file:`/etc/neutron/f5-oslbaasv1-agent.ini`.

    .. tip::

        The ``f5_external_physical_mappings`` setting supports multiple, comma-separated entries. It's good practice to include a default mapping, for cases where the ``provider:physical_network`` does not match any configuration settings. A default mapping simply uses the word 'default' instead of a known ``provider:physical_network`` attribute.

.. code-block:: text
    :emphasize-lines: 31

    ###############################################################################
    #  L2 Segmentation Mode Settings
    ###############################################################################
    #
    # Device VLAN to interface and tag mapping
    #
    # For pools or VIPs created on networks with type VLAN we will map
    # the VLAN to a particular interface and state if the VLAN tagging
    # should be enforced by the external device or not. This setting
    # is a comma separated list of the following format:
    #
    #    physical_network:interface_name:tagged, physical_network:interface_name:tagged
    #
    # where :
    #   physical_network corresponds to provider:physical_network attributes
    #   interface_name is the name of an interface or LAG trunk
    #   tagged is a boolean (True or False)
    #
    # If a network does not have a provider:physical_network attribute,
    # or the provider:physical_network attribute does not match in the
    # configured list, the 'default' physical_network setting will be
    # applied. At a minimum you must have a 'default' physical_network
    # setting.
    #
    # standalone example:
    #   f5_external_physical_mappings = default:1.1:True
    #
    # pair or scalen example (1.1 and 1.2 are used for HA purposes):
    #   f5_external_physical_mappings = default:1.3:True
    #
    f5_external_physical_mappings = default:1.1:True
    #








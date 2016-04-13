Tunnels
```````

For GRE and VxLAN tunnels, the F5® BIG-IP® devices expect to communicate with Open vSwitch VTEPs. The VTEP addresses for Open vSwitch VTEPs are learned from their registered Neutron agent configuration's ``tunneling_ip`` attribute.

.. topic:: Example:

    .. code-block:: text

        # neutron agent-show 034bddd0-0ac3-457a-9e2c-ed456dc2ad53
        +---------------------+--------------------------------------+
        | Field               | Value                                |
        +---------------------+--------------------------------------+
        | admin_state_up      | True                                 |
        | agent_type          | Open vSwitch agent                   |
        | alive               | True                                 |
        | binary              | neutron-openvswitch-agent            |
        | configurations      | {                                    |
        |                     |      "tunnel_types": [               |
        |                     |           "gre"                      |
        |                     |      ],                              |
        |                     |      "tunneling_ip": "10.1.0.35",    |
        |                     |      "bridge_mappings": {            |
        |                     |           "ph-eth3": "br-eth3"       |
        |                     |      },                              |
        |                     |      "l2_population": true,          |
        |                     |      "devices": 4                    |
        |                     | }                                    |
        | created_at          | 2013-11-15 05:00:23                  |
        | description         |                                      |
        | heartbeat_timestamp | 2014-04-22 16:58:21                  |
        | host                | sea-osp-cmp-001                      |
        | id                  | 034bddd0-0ac3-457a-9e2c-ed456dc2ad53 |
        | started_at          | 2014-04-17 22:39:30                  |
        | topic               | N/A                                  |
        +---------------------+--------------------------------------+

The F5® LBaaSv1 agent supports the ML2 L2 population service in that overlay tunnels for Member IP access are only built to Open vSwitch agents hosting Members. When using the ML2 population service, you can also elect to use static ARP entries for BIG-IP® devices to avoid flooding. This setting is found in :file:`/etc/neutron/f5-oslbaasv1-agent.ini`.

.. code-block:: text

    # Static ARP population for members on tunnel networks
    #
    # This is a boolean True or False value which specifies
    # that if a Pool Member IP address is associated with a gre
    # or vxlan tunnel network, in addition to a tunnel fdb
    # record being added, that a static arp entry will be created to
    # avoid the need to learn the member's MAC address via flooding.
    #
    f5_populate_static_arp = True


The necessary ML2 port binding extensions and segmentation model are defined by default with the community ML2 core plugin and Open vSwitch agents on the compute nodes.

When VIPs are placed on tenant overlay networks, the F5® LBaaSv1 agent sends tunnel update RPC messages to the Open vSwitch agents to inform them of BIG-IP® device VTEPs. This allows tenant guest virtual machines or network node services to interact with the BIG-IP®-provisioned VIPs across overlay networks.

BIG-IP® VTEP addresses should be added to the associated agent's config file (:file:`/etc/neutron/f5-oslbaasv1-agent.ini`).

.. code-block:: text

    # Device Tunneling (VTEP) selfips
    #
    # This is a single entry or comma separated list of cidr (h/m) format
    # selfip addresses, one per BIG-IP device, to use for VTEP addresses.
    #
    # If no gre or vxlan tunneling is required, these settings should be
    # commented out or set to None.
    #
    #f5_vtep_folder = 'Common'
    #f5_vtep_selfip_name = 'vtep'


Run ``neutron agent-show <agent-id>`` to view/verify the VTEP configurations. The VTEP addresses are listed as ``tunneling_ips``.

.. code-block:: text

    # neutron agent-show 014ada1a-91ab-4408-8a81-7be6c4ea8113
    +---------------------+-----------------------------------------------------------------------+
    | Field               | Value                                                                 |
    +---------------------+-----------------------------------------------------------------------+
    | admin_state_up      | True                                                                  |
    | agent_type          | Loadbalancer agent                                                    |
    | alive               | True                                                                  |
    | binary              | f5-bigip-lbaas-agent                                                  |
    | configurations      | {                                                                     |
    |                     |      "icontrol_endpoints": {                                          |
    |                     |           "10.0.64.165": {                                            |
    |                     |                "device_name": "host-10-0-64-165.openstack.f5se.com",  |
    |                     |                "platform": "Virtual Edition",                         |
    |                     |                "version": "BIG-IP_v11.6.0",                           |
    |                     |                "serial_number": "b720f143-a632-464c-4db92773f2a0"     |
    |                     |           },                                                          |
    |                     |           "10.0.64.164": {                                            |
    |                     |                "device_name": "host-10-0-64-164.openstack.f5se.com",  |
    |                     |                "platform": "Virtual Edition",                         |
    |                     |                "version": "BIG-IP_v11.6.0",                           |
    |                     |                "serial_number": "e1b1f439-72c3-5240-4358bbc45dff"     |
    |                     |           }                                                           |
    |                     |      },                                                               |
    |                     |      "request_queue_depth": 0,                                        |
    |                     |      "environment_prefix": "dev",                                     |
    |                     |      "tunneling_ips":                                                 |
    |                     |           "10.0.63.126",                                              |
    |                     |           "10.0.63.125"                                               |
    |                     |      ],                                                               |
    |                     |      "common_networks": {},                                           |
    |                     |      "services": 0,                                                   |
    |                     |      "environment_capacity_score": 0,                                 |
    |                     |      "tunnel_types": [                                                |
    |                     |           "gre"                                                       |
    |                     |      ],                                                               |
    |                     |      "environment_group_number": 1,                                   |
    |                     |      "bridge_mappings": {                                             |
    |                     |           "default": "1.3"                                            |
    |                     |      },                                                               |
    |                     |      "global_routed_mode": false                                      |
    |                     | }                                                                     |
    | created_at          | 2015-08-19 13:08:15                                                   |
    | description         |                                                                       |
    | heartbeat_timestamp | 2015-08-20 15:19:15                                                   |
    | host                | sea-osp-ctl-001:f5acc0d3-24d6-5c64-bc75-866dd26310a4                  |
    | id                  | 014ada1a-91ab-4408-8a81-7be6c4ea8113                                  |
    | started_at          | 2015-08-19 17:30:44                                                   |
    | topic               | f5-lbaas-process-on-agent                                             |
    +---------------------+-----------------------------------------------------------------------+


.. _neutron-agent-commands:

Neutron Agent Commands
~~~~~~~~~~~~~~~~~~~~~~

You can use Neutron ``agent`` commands to manage agent processes via the CLI.

.. include:: ../../release_readme.rst
    :start-line: 37
    :end-line: 46

.. topic:: List all agents

    .. code-block:: text

        $ neutron agent-list
        +--------------------------------------+--------------------+----------------------------------------------+-------+----------------+---------------------------+
        | id                                   | agent_type         | host                                         | alive | admin_state_up | binary                    |
        +--------------------------------------+--------------------+----------------------------------------------+-------+----------------+---------------------------+
        | 11b4c7ca-aaf9-4ac8-8b9f-2003e021cf23 | Metadata agent     | host-29                                      | :-)   | True           | neutron-metadata-agent    |
        | 13c25ea9-ca58-4b69-af27-fb1ea8824f65 | L3 agent           | host-29                                      | :-)   | True           | neutron-l3-agent          |
        | 4c71878e-ac49-4a60-81d3-af3793705460 | Open vSwitch agent | host-29                                      | :-)   | True           | neutron-openvswitch-agent |
        | 4e9df1b2-4fb7-4d01-8758-ca139038b0c8 | Loadbalancer agent | host-29                                      | :-)   | True           | neutron-lbaas-agent       |
        | 640c19de-4362-4c4e-88b1-650092e62169 | DHCP agent         | host-29                                      | :-)   | True           | neutron-dhcp-agent        |
        | e4921123-000c-4172-8a79-72e8f0d357e2 | Loadbalancer agent | host-29:3eb793cb-fa51-549d-a15b-253ce5405fcf | :-)   | True           | f5-oslbaasv1-agent        |
        +--------------------------------------+--------------------+----------------------------------------------+-------+----------------+---------------------------+


.. topic:: Show details for a specific agent

    $ neutron agent-show <agent-id>

    .. code-block:: text

        # neutron agent-show e4921123-000c-4172-8a79-72e8f0d357e2
        +---------------------+--------------------------------------------------------------------------+
        | Field               | Value                                                                    |
        +---------------------+--------------------------------------------------------------------------+
        | admin_state_up      | True                                                                     |
        | agent_type          | Loadbalancer agent                                                       |
        | alive               | True                                                                     |
        | binary              | f5-oslbaasv1-agent                                                       |
        | configurations      | {                                                                        |
        |                     |      "icontrol_endpoints": {                                             |
        |                     |           "10.190.6.253": {                                              |
        |                     |                "device_name": "host-10-20-0-4.int.lineratesystems.com",  |
        |                     |                "platform": "Virtual Edition",                            |
        |                     |                "version": "BIG-IP_v11.6.0",                              |
        |                     |                "serial_number": "65d1af65-d236-407a-779a9e02c4d9"        |
        |                     |           }                                                              |
        |                     |      },                                                                  |
        |                     |      "request_queue_depth": 0,                                           |
        |                     |      "environment_prefix": "",                                           |
        |                     |      "tunneling_ips": [],                                                |
        |                     |      "common_networks": {},                                              |
        |                     |      "services": 0,                                                      |
        |                     |      "environment_capacity_score": 0,                                    |
        |                     |      "tunnel_types": [                                                   |
        |                     |           "gre",                                                         |
        |                     |           "vlan",                                                        |
        |                     |           "vxlan"                                                        |
        |                     |      ],                                                                  |
        |                     |      "environment_group_number": 1,                                      |
        |                     |      "bridge_mappings": {                                                |
        |                     |           "default": "1.1"                                               |
        |                     |      },                                                                  |
        |                     |      "global_routed_mode": false                                         |
        |                     | }                                                                        |
        | created_at          | 2016-02-12 23:13:40                                                      |
        | description         |                                                                          |
        | heartbeat_timestamp | 2016-02-16 17:35:11                                                      |
        | host                | host-29:3eb793cb-fa51-549d-a15b-253ce5405fcf                             |
        | id                  | e4921123-000c-4172-8a79-72e8f0d357e2                                     |
        | started_at          | 2016-02-12 23:13:40                                                      |
        | topic               | f5-lbaas-process-on-agent                                                |
        +---------------------+--------------------------------------------------------------------------+


.. seealso::

    :ref:`Troubleshooting the F5® LBaaSv1 Agent <troubleshooting-agent>`

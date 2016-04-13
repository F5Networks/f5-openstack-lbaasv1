Neutron Agent Binding
`````````````````````

Neutron LBaaSv1 binds pools to specific agents for the life of the pool. The redundancy allows other agents running in the same environment to handle requests if the bound agent is not active.

.. note::

    If the bound agent is inactive, it's expected that it will be brought back online. If an agent is deleted, all pools bound to it should also be deleted. Run ``neutron lb-pool-list-on-agent <agent-id>`` to identify all pools associated with an agent.

.. _multiple-controllers-redundancy:

Multiple Controllers and Redundancy
-----------------------------------

The F5® LBaaSv1 plugin driver runs within the Neutron controller. When the Neutron community LBaaS plugin loads the
driver, it creates a global messaging queue that will be used for all inbound callbacks and status update requests from F5® LBaaSv1 agents.

.. tip::

    To run multiple queues, see the :ref:`differentiated services <differentiated-services-scaleout>` section.

In an environment with multiple Neutron controllers, the F5® drivers all listen to the same message queue, providing controller redundancy and scale-out.

.. note::

    All Neutron controllers must use the same Neutron database to avoid state problems with concurrently-running controller instances.

If you choose to deploy multiple agents with the same BIG-IP® ``environment_prefix``, **each agent must run on a different host**. The F5® agent uses the Neutron messaging configurations found in the file :file:`/etc/neutron/neutron.conf`. To make sure the messaging settings on each host match those of the controller, we recommend copying :file:`/etc/neutron/neutron.conf` from the controller to each host.

Each F5® agent will communicate with its configured iControl® endpoint(s) to do the following:

 * Verify that the BIG-IP® system(s) meet minimal requirements.
 * Create a unique named queue to process provisioning requests from the F5® driver.
 * Report as a valid F5® LBaaSv1 agent via the standard Neutron controller agent status queue.

The agents report their status to the agent queue on a periodic basis (every 10 seconds, by default; this can be configured in :file:`/etc/neutron/f5-oslbaasv1-agent.ini`).

When a Neutron controller receives a request for a new pool, the F5® LBaaSv1 driver invokes the tenant scheduler. The scheduler queries all active F5® agents and determines what, if any, existing pools are bound to each agent. If the driver locates an active agent that already has a bound pool for the same ``tenant_id`` as the newly-requested pool, the driver selects that agent. Otherwise, the driver selects an active agent at random. The request to create the pool service is sent to the selected agent's task queue. When the provisioning task is complete, the agent reports the outcome to the LBaaSv1 callback queue. The driver processes the agent's report and updates the Neutron database. The agent which handled the provisioning task is bound to the pool for the pool's lifetime (in other words, that agent will handle all tasks for that pool as long as the agent and/or pool are active).

If a bound agent is inactive, the tenant scheduler looks for other agents with the same ``environment_prefix`` as the bound agent. The scheduler assigns the task to the first active agent with a matching ``environment_prefix`` that it finds. The pool remains bound to the original (currently inactive) agent with the expectation that the agent will eventually be brought back online. If the agent cannot be brought back online, communication with all pools managed by that agent is lost.

.. warning::

     If you delete an agent, you should also delete all pools bound to that agent.

     Run ``neutron lb-pool-list-on-agent <agent-id>`` to identify all pools associated with an agent.

F5® LBaaSv1 Plugin
``````````````````

The F5® LBaaSv1 service provider driver runs within the Neutron controller processes. It utilizes Neutron RPC messaging queues to issue provisioning tasks to F5® LBaaSv1 agent processes.

When an LBaaSv1 API interface is invoked, the F5® LBaaSv1 driver schedules tasks to an F5® agent based on the agent's availability (determined from the standard Neutron agent status messages). The agent starts, and communicates with, a configured BIG-IP®, then registers its own named queue where it will receive tasks from the Neutron controller(s).

The The F5® agent makes callbacks to the F5® drivers to query additional Neutron network, port, and subnet information; allocate Neutron objects (for example, fixed IP addresses); and report provisioning and pool status. These callback requests are placed on an RPC message queue processed by all listening F5® drivers in a round robin fashion. Since all Neutron controller processes are working transactionally off the same backend database, it doesn't matter which of the available Neutron controller processes handles the requests.





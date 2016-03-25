F5® LBaaSv1 Driver and Agent Placement
``````````````````````````````````````

The F5® LBaaSv1 driver should be installed on at least one Neutron controller. Installing drivers on additional controllers scales out communications to Neutron.

The F5® LBaaSv1 agent should be installed on at least on Neutron controller. Installing additional agents on different hosts in the same BIG-IP® environment (in other words, hosts that have the same BIG-IP® ``environment_prefix`` and iControl® endpoint settings) adds scheduled redundancy to the provision process. See :ref:`BIG-IP® Environments <bigip-environments>` for more information.

Network Operation Mode
``````````````````````

The F5® OpenStack LBaaSv1 plugin supports two modes of network operation: :ref:`global routed mode <global-routed-mode>` and :ref:`L2 adjacent mode <l2-adjacent-mode>` (the default). The Neutron core provider requirements are different for each mode; the modes are described in detail later in this document. You can configure this in the ``L3 Segmentation Mode Settings`` section of the agent configuration file, as described in :ref:`Configuring the F5® LBaaSv1 agent <configure-lbaasv1-agent>`.

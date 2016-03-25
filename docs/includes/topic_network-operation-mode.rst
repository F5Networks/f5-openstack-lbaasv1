Network Operation Mode
``````````````````````

The F5® OpenStack LBaaSv1 plugin supports two modes of network operation: `global routed mode <#id4>`_ and `L2 adjacent mode <#id5>`_ (the default). The Neutron core provider requirements are different for each mode; the modes are described in detail later in this document. You can configure this in the ``L3 Segmentation Mode Settings`` section of the agent configuration file, as described in `Configuring the F5® LBaaSv1 agent <#configuring-the-f5-lbaasv1-agent>`_.

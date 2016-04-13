Configuring the F5® LBaaSv1 Agent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The agent settings are found in :file:`/etc/neutron/f5-oslbaasv1-agent.ini`. See the :ref:`Sample Agent Config file <agent-config-file>` for detailed explanations of all available settings.

.. important::

    At minimum, you will need to edit the ``Device Settings``, ``Device Driver - iControl Driver Setting``, and ``L3 Segmentation Mode Settings`` sections of the config file.

    Be sure to provide the iControl® hostname, username, and password; without this information, the agent will not be able to connect to the BIG-IP® and will not run.

    The installation process automatically starts an agent process; after you configure the ``/etc/neutron/f5-oslbaasv1-agent.init`` file, `restart the agent process <.. _start-the-agent>`.



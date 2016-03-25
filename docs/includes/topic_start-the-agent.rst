Start/Restart the agent
~~~~~~~~~~~~~~~~~~~~~~~

The agent may start running automatically upon installation. Taking this step will start or restart the service, depending on the agent's current status.

.. code-block:: text

    # service f5-oslbaasv1-agent start


.. note::

    If you want to start with clean logs, you should remove the log file first:

    .. code-block:: text

        # rm /var/log/neutron/f5-oslbaasv1-agent.log

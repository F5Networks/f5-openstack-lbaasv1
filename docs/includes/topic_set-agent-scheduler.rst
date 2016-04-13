Set the agent scheduler (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the default section of your :file:`neutron.conf` file, the ``f5_loadbalancer_pool_scheduler_driver`` variable can be set to an alternative agent scheduler. The default value for this setting, ``f5.oslbaasv1driver.drivers.agent_scheduler.TenantScheduler``, causes LBaaSv1 pools to be distributed within an environment with tenant affinity.

.. warning::

    You should only provide an alternate scheduler if you have an alternate service placement requirement and your own scheduler.

.. :todo: create agent scheduler guide and link to here in ``seealso`` box.

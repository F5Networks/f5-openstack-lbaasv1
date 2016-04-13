BIG-IP® Environments
````````````````````

Two agents which have different iControl® endpoint settings (in other words, agents that are provisioning different sets of BIG-IP® devices) can not be configured with the same ``environment_prefix``.

The scheduler uses the ``environment_prefix`` as a unique identifier for the agent process. If you use the same ``environment_prefix`` for two  agents that are managing separate BIG-IP® devices, the scheduler will confuse them, most likely resulting in errors.

See :ref:`Running Multiple Agents on the Same Host <multiple-agents-same-host>` for more information.



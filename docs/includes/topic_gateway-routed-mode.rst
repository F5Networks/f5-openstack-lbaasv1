Gateway Routed Mode
```````````````````

In gateway routed mode, the F5® agent attempts to create a default gateway forwarding service on the BIG-IP®  for member Neutron subnets.

.. code-block:: text

    +--------------------------------------+--------------------------------------+
    | Topology                             | f5-oslbaasv1-agent.ini setting       |
    +======================================+======================================+
    | Gateway routed mode                  | f5_global_routed_mode = False        |
    |                                      | f5_snat_mode = False                 |
    |                                      |                                      |
    +--------------------------------------+--------------------------------------+


.. todo: requires clarification, reference(s) to BIG-IP manuals; updated diagram.

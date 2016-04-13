Overview
--------

The F5® OpenStack LBaaSv1 plugin allows you to orchestrate BIG-IP® load
balancing services -- including virtual IPs, pools, device service
groups, and health monitoring -- in an OpenStack environment.

The F5® LBaaSv1 agent translates 'OpenStack' to 'BIG-IP®', so to speak,
allowing you to provision BIG-IP® Local Traffic Manager® (LTM®) services in an OpenStack environment.

The diagram below shows a sample OpenStack environment using
the F5® plugin for OpenStack LBaaSv1. The LBaaSv1 agent communicates with
a BIG-IP® platform or Virtual Edition via iControl® REST. The load balancing
service request is handled by the BIG-IP® according to its
configurations; it can then connect, discover, and/or deploy to the
cloud-based apps or vms in the OpenStack project network.

.. image media/openstack_lbaas_env_example.png

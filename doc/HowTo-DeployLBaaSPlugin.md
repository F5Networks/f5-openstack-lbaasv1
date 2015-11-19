---
layout: docs_page
title: How to Deploy the F5 LBaaS Plug-In
---

How to Deploy the F5 LBaaS Plug-in in OpenStack
=======================

#Overview
Use these instructions to install the F5 LBaaS Plug-in and deploy it in your OpenStack cloud.

#Prerequisites

1. A running OpenStack installation on either Red Hat/CentOS v7 or 6.7 or Ubuntu 14.0.4.

2. The [F5 LBaaS plug-in](https://devcentral.f5.com/d/openstack-neutron-lbaas-driver-and-agent).

3. BIG-IP hardware or licensed BIG-IP VE software.

#Tasks

## Install the Driver on the Neutron Server

    **NOTE:** Errors and other relevant log messages are stored on the Neutron server in */var/log/neutron/server.log*.

### For Red Hat/CentOS:

`rpm -i f5-lbaas-driver-1.0.7-1.noarch.rpm`

### For Ubuntu:

`dpkg -i f5-lbaas-driver_1.0.7-1_all.deb`

    **NOTE:** The actual names of the packages may vary from version to version.

## Configure Neutron

1. Add the lines below to the Neutron configuration file \(*/etc/neutron/neutron.conf*\).  

   `[DEFAULT]`  
   `service\_plugins=neutron.services.l3\_router.l3\_router\_plugin.L3RouterPlugin,neutron.services.firewall.fwaas\_plugin.FirewallPlugin.neutron.services.loadbalancer.plugin.LoadBalancerPlugin,neutron.services.vpn.plugin.VPNDriverPlugin,neutron.services.metering.metering_plugin.MeteringPlugin`

  * **If you're only using F5 LBaaS, you must also add the following lines:**  
   `[service_providers]`
   `service\_provider=LOADBALANCER:f5:neutron.services.loadbalancer.drivers.f5.plugin_driver.F5PluginDriver:default`

  * **The option below supports both F5 (the default) and HA Proxy:**  
   `[service_providers]`  
   `service\_provider=LOADBALANCER:f5:neutron.services.loadbalancer.drivers.f5.plugin_driver.F5PluginDriver:default`  
   `service_provider=LOADBALANCER:Haproxy:neutron.services.loadbalancer.drivers.haproxy.plugin\_driver.HaproxyOnHostPluginDriver`

2. Save the changes to your config file.  

## Restart Neutron

Restart the Neutron server by running the following command:

`service neutron-server restart`

# What's Next?


[Deploy the F5 LBaaS Agent]({{ f5-os-agent/HowTo-DeployLBaaSAgent.html | prepend: site.url }})

# Additional Resources

[F5 TMOS Virtual Edition OpenStack Deployment Guide]({{ f5-os-odk/HowTo-DeployVEinOS.html | prepend: site.url }})

[OpenStack Deployment Tips]({{ f5-os-odk/OpenStackDeploymentTips.html | prepend: site.url }})

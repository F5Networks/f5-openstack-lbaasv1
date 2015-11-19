---
layout: docs_page
title: Install the F5 LBaaS Plug-In
tags: lbaasv1, plug-in
resource: true
---

# Overview

{% include lbaasv1_overview.html %}

## Prerequisites

{% include lbaasv1_prerequisites.html %}

# Tasks

## Install the F5 LBaaS Plug-in on the Neutron Server

{% include lbaasv1_install_the_neutron_server_overview-note.html %}

### RedHat/CentOS

{% include lbaasv1_install_the_driver_neutron_server_redhat-centos.html %}

### Ubuntu

{% include lbaasv1_install_the_driver_neutron_server_ubuntu.html %}

## Configure the Neutron Server

{% include lbaasv1_install_the_driver_neutron_server_set-default-lbaas-service.html %}

{% include lbaasv1_install_the_driver_neutron_server_set-default-lbaas-service-provider.html %}

1. Save the changes to the Neutron server config file.

## Restart the Neutron Server

{% include lbaasv1_install_the_driver_neutron_server_restart.html %}
---
layout: default
title: BUILD
---

The source code is python and thus is not specific to a 
particular CPU architecture. 

The build process was designed to be run on an Ubuntu 12.04
workstation. It requires build tools which are not suitable
for a production server.

To install all required packages to build both Debian and 
RPM packages on an Ubuntu 12.04 workstation, run:

    sudo apt-get install make python-stdeb fakeroot python-all rpm

To build Debian and RPM binary packages run:

    make

The packages will be placed in the build directory for the project.

The f5-lbaas-driver can then be distributed to the Neutron controller(s)
and installed. The f5-bigip-lbaas-agent can be distributed to host(s)
which will run the agent process and installed.



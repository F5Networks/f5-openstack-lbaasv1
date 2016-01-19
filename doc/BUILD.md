---
layout: default
title: BUILD
---

Debian Packages
---------------
In order to build debian packages use Docker/debian/Dockerfile to create a container that has the necessary prerequisites installed
to create a package for the Trusty Ubuntu disto.

$ docker build -t deb-pkg-builder ./Docker/debian

Then package the driver, agent, and common code by executing:

$ docker run -v "$PWD:/var/build" deb-pkg-builder /bin/bash /build-debs.sh

The debs are in the following directories:

./agent/deb_dist
./common/deb_dist
./driver/deb_dist

RPM Packages
------------
In order to build RPMs use Docker/redhad/Dockerfile to create a container that has the necessary prerequisites installed to build
a package for Centos/RedHat 7.

$ docker build -t rpm-pkg-builder ./Docker/redhat

hen package the driver, agent, and common code by executing:

$ docker run -v "$PWD:/var/build" rpm-pkg-builder /bin/bash /build-rpms.sh

The rpms are in the following directories:

./agent/dist
./common/dist
./driver/dist



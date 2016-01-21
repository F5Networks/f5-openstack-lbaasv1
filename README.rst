f5-openstack-lbassv1
====================

|Build Status|

Introduction
------------

This repo houses the code for the F5 OpenStack LBaaSv1 plugin. Please
see the
`documentation <http://f5networks.github.io/f5-openstack-docs>`__ for
more information.

Installation & Configuration
----------------------------

See the
`documentation <http://f5networks.github.io/f5-openstack-docs>`__.

Filing Issues
-------------

| If you find an issue we would love to hear about it. Please let us
know by
| filing an issue in this repository and tell us as much as you can
about what
| you found and how you found it.

Contributing
------------

See `Contributing <CONTRIBUTING.md>`__

Build
-----

Debian Packages
```````````````

| In order to build debian packages use Docker/debian/Dockerfile to
create a container that has the necessary prerequisites installed
| to create a package for the Trusty Ubuntu disto.

::

    $ docker build -t deb-pkg-builder ./Docker/debian

Then package the driver, agent, and common code by executing:

::

    $ docker run -v "$PWD:/var/build" deb-pkg-builder /bin/bash /build-debs.sh

The debs are in the following directories:

| ./agent/deb\_dist
| ./common/deb\_dist
| ./driver/deb\_dist

RPM Packages
````````````

| In order to build RPMs use Docker/redhad/Dockerfile to create a
container that has the necessary prerequisites installed to build
| a package for Centos/RedHat 7.

::

    $ docker build -t rpm-pkg-builder ./Docker/redhat

Then package the driver, agent, and common code by executing:

::

    $ docker run -v "$PWD:/var/build" rpm-pkg-builder /bin/bash /build-rpms.sh

The rpms are in the following directories:

| ./agent/dist
| ./common/dist
| ./driver/dist

PyPI
----

To make a PyPI package...

::

    bash
    python setup.py sdist

Test
----

Before you open a pull request, your code must have passing
`pytest <http://pytest.org>`__ unit tests. In addition, you should
include a set of functional tests written to use a real BIG-IP device
for testing. Information on how to run our set of tests is included
below.

Unit Tests
``````````

We use pytest for our unit tests

#. If you haven't already, install the required test packages and the
   requirements.txt in your virtual environment.

   ::

       shell
       $ pip install hacking pytest pytest-cov
       $ pip install -r requirements.txt

#. | Run the tests and produce a coverage repor. The
   ``--cov-report=html`` will
   | create a ``htmlcov/`` directory that you can view in your browser
   to see the
   | missing lines of code.

   ::

       shell
       py.test --cov ./icontrol --cov-report=html
       open htmlcov/index.html

Style Checks
````````````

| We use the hacking module for our style checks (installed as part of
| step 1 in the Unit Test section).

::

    shell
    flake8 ./

Contact
-------

f5_openstack_lbaasv1@f5.com

Copyright
---------

Copyright 2013-2016 F5 Networks Inc.

Support
-------

See `Support <SUPPORT.md>`__

License
-------

Apache V2.0
```````````

| Licensed under the Apache License, Version 2.0 (the "License");
| you may not use this file except in compliance with the License.
| You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

| Unless required by applicable law or agreed to in writing, software
| distributed under the License is distributed on an "AS IS" BASIS,
| WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
implied.
| See the License for the specific language governing permissions and
| limitations under the License.

Contributor License Agreement
`````````````````````````````

| Individuals or business entities who contribute to this project must
have completed and submitted the `F5 Contributor License
Agreement <http://f5networks.github.io/f5-openstack-docs/cla_landing/index.html>`__
to Openstack_CLA@f5.com prior to their
| code submission being included in this project.

.. |Build Status| .. image:: https://travis-ci.org/F5Networks/f5-openstack-lbaasv1.svg?branch=1.0
   :target: https://travis-ci.org/F5Networks/f5-openstack-lbaasv1

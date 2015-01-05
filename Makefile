# NOTE:
# 
# You need to install these packages on Ubunutu 12.04 to make this work:
# 
#     sudo apt-get install make python-stdeb fakeroot python-all rpm
# 
# 
PROJECT_DIR := $(shell pwd)
VERSION := $(shell cat VERSION|tr -d '\n';)
RELEASE := $(shell cat RELEASE|tr -d '\n';)

default: debs rpms

debs: build/f5-lbaas-driver_$(VERSION)_all.deb \
      build/f5-bigip-lbaas-agent_$(VERSION)_all.deb

rpms: build/f5-lbaas-driver-$(VERSION).noarch.rpm \
      build/f5-bigip-lbaas-agent-$(VERSION).noarch.rpm

build/f5-lbaas-driver_$(VERSION)_all.deb:
	(cd driver; \
	rm -rf deb_dist; \
	export PROJECT_DIR=$(PROJECT_DIR); \
	export VERSION=$(VERSION); \
	export RELEASE=$(RELEASE); \
	python setup.py --command-packages=stdeb.command bdist_deb; \
	rm -f stdeb.cfg; \
        ) 
	mkdir -p build
	cp driver/deb_dist/f5-lbaas-driver_$(VERSION)-$(RELEASE)_all.deb build/


build/f5-bigip-lbaas-agent_$(VERSION)_all.deb:
	(cd agent; \
	rm -rf deb_dist; \
	export PROJECT_DIR=$(PROJECT_DIR); \
	export VERSION=$(VERSION); \
	export RELEASE=$(RELEASE); \
	python setup.py --command-packages=stdeb.command bdist_deb; \
	rm -f stdeb.cfg; \
        )
	mkdir -p build
	cp agent/deb_dist/f5-bigip-lbaas-agent_$(VERSION)-$(RELEASE)_all.deb build


build/f5-lbaas-driver-$(VERSION).noarch.rpm:
	(cd driver; \
	export PROJECT_DIR=$(PROJECT_DIR); \
	export VERSION=$(VERSION); \
	export RELEASE=$(RELEASE); \
	python setup.py bdist_rpm --release $(RELEASE); \
        ) 
	mkdir -p build
	cp driver/dist/f5-lbaas-driver-$(VERSION)-$(RELEASE).noarch.rpm build

build/f5-bigip-lbaas-agent-$(VERSION).noarch.rpm:
	(cd agent; \
	export PROJECT_DIR=$(PROJECT_DIR); \
	export VERSION=$(VERSION); \
	export RELEASE=$(RELEASE); \
	python setup.py bdist_rpm --release $(RELEASE); \
	)
	mkdir -p build
	cp agent/dist/f5-bigip-lbaas-agent-$(VERSION)-$(RELEASE).noarch.rpm build

pdf:
	html2pdf $(PROJECT_DIR)/doc/f5lbaas-readme.html \
            $(PROJECT_DIR)/doc/f5lbaas-readme.pdf

clean: clean-debs clean-rpms 

clean-debs:
	find . -name "*.pyc" -exec rm -rf {} \;
	rm -f driver/MANIFEST
	rm -f agent/MANIFEST
	rm -f build/f5-bigip-lbaas-agent_*.deb
	(cd agent; \
	rm -rf deb_dist; \
        )
	rm -f build/f5-lbaas-driver_*.deb
	(cd driver; \
	rm -rf deb_dist; \
        )

clean-rpms:
	find . -name "*.pyc" -exec rm -rf {} \;
	rm -f driver/MANIFEST
	rm -f agent/MANIFEST 
	rm -f build/f5-bigip-lbaas-agent-*.rpm
	(cd agent; \
	rm -rf dist; \
	rm -rf /build/bdist.linux-x86_64; \
        )
	rm -f build/f5-lbaas-driver-*.rpm
	(cd driver; \
	rm -rf dist; \
	rm -rf build/bdist.linux-x86_64; \
        )

BDIR := neutron/services/loadbalancer/drivers/f5/bigip
IDIR := f5/bigip/interfaces
NDIR := /usr/lib/python2.7/dist-packages/neutron
pep8:
	(cd agent; \
         pep8 $(BDIR)/fdb_connector.py; \
         pep8 $(BDIR)/fdb_connector_ml2.py; \
         pep8 $(BDIR)/icontrol_driver.py; \
         pep8 $(BDIR)/l2.py; \
         pep8 $(BDIR)/lbaas.py; \
         pep8 $(BDIR)/lbaas_direct.py; \
         pep8 $(BDIR)/selfips.py; \
         pep8 $(BDIR)/snats.py; \
         pep8 $(BDIR)/pools.py; \
         pep8 $(BDIR)/vcmp.py; \
         pep8 $(BDIR)/vips.py; \
         pep8 $(BDIR)/utils.py; \
         pep8 $(IDIR)/__init__.py; \
         pep8 $(IDIR)/arp.py; \
         pep8 $(IDIR)/cluster.py; \
         pep8 $(IDIR)/device.py; \
         pep8 $(IDIR)/l2gre.py; \
         pep8 $(IDIR)/monitor.py; \
         pep8 $(IDIR)/nat.py; \
         pep8 $(IDIR)/pool.py; \
         pep8 $(IDIR)/route.py; \
         pep8 $(IDIR)/rule.py; \
         pep8 $(IDIR)/selfip.py; \
         pep8 $(IDIR)/snat.py; \
         pep8 $(IDIR)/system.py; \
         pep8 $(IDIR)/virtual_server.py; \
         pep8 $(IDIR)/vlan.py; \
         pep8 $(IDIR)/vxlan.py; \
        )

PYHOOK := 'import sys;sys.path.insert(1,".")'
PYLINT := pylint --additional-builtins=_ --init-hook=$(PYHOOK)

pylint:
	(cd agent; \
         > neutron/__init__.py; \
         > neutron/services/__init__.py; \
         > neutron/services/loadbalancer/__init__.py; \
         > neutron/services/loadbalancer/drivers/__init__.py; \
         ln -s $(NDIR)/common neutron/common; \
         ln -s $(NDIR)/openstack neutron/openstack; \
         ln -s $(NDIR)/plugins neutron/plugins; \
         ln -s $(NDIR)/services/constants neutron/services/constants; \
         ln -s $(NDIR)/services/loadbalancer/constants.py \
               neutron/services/loadbalancer/constants.py; \
         $(PYLINT) $(BDIR)/fdb_connector.py; \
         $(PYLINT) $(BDIR)/fdb_connector_ml2.py; \
         $(PYLINT) $(BDIR)/icontrol_driver.py; \
         $(PYLINT) $(BDIR)/lbaas.py; \
         $(PYLINT) $(BDIR)/lbaas_direct.py; \
         $(PYLINT) $(BDIR)/l2.py; \
         $(PYLINT) $(BDIR)/selfips.py; \
         $(PYLINT) $(BDIR)/snats.py; \
         $(PYLINT) $(BDIR)/pools.py; \
         $(PYLINT) $(BDIR)/vcmp.py; \
         $(PYLINT) $(BDIR)/vips.py; \
         $(PYLINT) $(BDIR)/utils.py; \
         $(PYLINT) $(IDIR)/__init__.py; \
         $(PYLINT) $(IDIR)/arp.py; \
         $(PYLINT) $(IDIR)/system.py; \
         echo $(PYLINT) $(IDIR)/virtual_server.py; \
         $(PYLINT) $(IDIR)/vxlan.py; \
         rm -v neutron/plugins; \
         rm -v neutron/openstack; \
         rm -v neutron/common; \
         rm -v neutron/services/constants; \
         rm -v neutron/services/loadbalancer/constants.py; \
         rm -v neutron/services/loadbalancer/drivers/__init__.py; \
         rm -v neutron/services/loadbalancer/__init__.py; \
         rm -v neutron/services/__init__.py; \
         rm -v neutron/__init__.py; \
        )


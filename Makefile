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
	html2pdf $(PROJECT_DIR)/doc/f5lbaas-readme.html $(PROJECT_DIR)/doc/f5lbaas-readme.pdf

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

pylint:
	(cd agent; \
         > neutron/__init__.py; \
         > neutron/services/__init__.py; \
         > neutron/services/loadbalancer/__init__.py; \
         > neutron/services/loadbalancer/drivers/__init__.py; \
         ln -s /usr/lib/python2.7/dist-packages/neutron/common neutron/common; \
         ln -s /usr/lib/python2.7/dist-packages/neutron/openstack neutron/openstack; \
         ln -s /usr/lib/python2.7/dist-packages/neutron/plugins neutron/plugins; \
         ln -s /usr/lib/python2.7/dist-packages/neutron/services/constants neutron/services/constants; \
         ln -s /usr/lib/python2.7/dist-packages/neutron/services/loadbalancer/constants.py neutron/services/loadbalancer/constants.py; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/icontrol_driver.py | \
            more; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/l2.py | \
            more; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/selfips.py | \
            more; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/snats.py | \
            more; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/pools.py | \
            more; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/vips.py | \
            more; \
         pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                neutron/services/loadbalancer/drivers/f5/bigip/utils.py | \
            more; \
         echo pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                f5/bigip/bigip_interfaces/system.py | \
            more; \
         echo pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                f5/bigip/bigip_interfaces/vxlan.py | \
            more; \
         echo pylint --additional-builtins=_ \
                --init-hook='import sys;sys.path.insert(1,".")' \
                f5/bigip/bigip_interfaces/arp.py | \
            more; \
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

pep8:
	(cd agent; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/icontrol_driver.py; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/l2.py; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/selfips.py; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/snats.py; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/pools.py; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/vips.py; \
         pep8 neutron/services/loadbalancer/drivers/f5/bigip/utils.py; \
         pep8 f5/bigip/bigip_interfaces/__init__.py; \
         pep8 f5/bigip/bigip_interfaces/arp.py; \
         pep8 f5/bigip/bigip_interfaces/cluster.py; \
         pep8 f5/bigip/bigip_interfaces/device.py; \
         pep8 f5/bigip/bigip_interfaces/system.py; \
         pep8 f5/bigip/bigip_interfaces/vxlan.py; \
        )


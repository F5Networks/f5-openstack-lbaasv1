# NOTE:
# 
# You need to install these packages on Ubunutu 12.04 to make this work:
# 
#     sudo apt-get install make python-stdeb fakeroot python-all rpm
# 
# 

VERSION := $(shell cat VERSION_ID|tr -d '\n'; echo -n '.'; cat BUILD_ID|tr -d '\n'; echo -n '-1')
RPM_VERSION := $(shell cat VERSION_ID|tr -d '\n'; echo -n '.'; cat BUILD_ID|tr -d '\n'|tr '-' '_'; echo -n '_1')

PPA_DIST=precise
GPG_KEY=E1E513EF

default: debs rpms

debs: build/f5-lbaas-driver_$(VERSION)_all.deb \
      build/f5-bigip-lbaas-agent_$(VERSION)_all.deb

rpms: build/f5-lbaas-driver-$(VERSION).noarch.rpm \
      build/f5-bigip-lbaas-agent-$(VERSION).noarch.rpm

deb_source: build/f5-lbaas-driver_$(VERSION)_source.deb \
        build/f5-bigip-lbaas-agent_$(VERSION)_source.deb


build/f5-lbaas-driver_$(VERSION)_all.deb:
	(cd driver; \
	rm -rf deb_dist; \
	sed -i.orig "s/\(.*version=\).*/\1\'$(VERSION)\',/g" setup.py; \
	python setup.py --command-packages=stdeb.command bdist_deb; \
        ) 
	mkdir -p build
	cp driver/deb_dist/f5-lbaas-driver_$(VERSION)-1_all.deb build/

build/f5-lbaas-driver_$(VERSION)_source.deb:
	(cd driver; \
	rm -rf deb_dist; \
	sed -i.orig "s/\(.*version=\).*/\1\'$(VERSION)\',/g" setup.py; \
        python setup.py --command-packages=stdeb.command sdist_dsc --suite $(PPA_DIST); \
        cd deb_dist/f5-lbaas-driver-$(VERSION); \
        dpkg-buildpackage -rfakeroot -S -k$(GPG_KEY); \
        )

build/f5-bigip-lbaas-agent_$(VERSION)_all.deb:
	(cd agent; \
	rm -rf deb_dist; \
	sed -i.orig "s/\(.*version=\).*/\1\'$(VERSION)\',/g" setup.py; \
	python setup.py --command-packages=stdeb.command bdist_deb; \
        )
	mkdir -p build
	cp agent/deb_dist/f5-bigip-lbaas-agent_$(VERSION)-1_all.deb build

build/f5-bigip-lbaas-agent_$(VERSION)_source.deb:
	(cd agent; \
	rm -rf deb_dist; \
	sed -i.orig "s/\(.*version=\).*/\1\'$(VERSION)\',/g" setup.py; \
        python setup.py --command-packages=stdeb.command sdist_dsc --suite $(PPA_DIST); \
        cd deb_dist/f5-bigip-lbaas-agent-$(VERSION); \
        dpkg-buildpackage -rfakeroot -S -k$(GPG_KEY); \
        )

build/f5-lbaas-driver-$(VERSION).noarch.rpm:
	(cd driver; \
	python setup.py bdist_rpm; \
        ) 
	mkdir -p build
	cp driver/dist/f5-lbaas-driver-$(RPM_VERSION)-1.noarch.rpm build

build/f5-bigip-lbaas-agent-$(VERSION).noarch.rpm:
	(cd agent; \
	python setup.py bdist_rpm; \
	)
	mkdir -p build
	cp agent/dist/f5-bigip-lbaas-agent-$(RPM_VERSION)-1.noarch.rpm build

clean: clean-debs clean-rpms 

clean-debs: 
	rm -f build/f5-bigip-lbaas-agent_*.deb
	(cd agent; \
	rm -rf deb_dist; \
        )
	rm -f build/f5-lbaas-driver_*.deb
	(cd driver; \
	rm -rf deb_dist; \
        )

clean-rpms: 
	rm -f build/f5-bigip-lbaas-agent-*.rpm
	(cd agent; \
	rm -rf dist; \
        )
	rm -f build/f5-lbaas-driver-*.rpm
	(cd driver; \
	rm -rf dist; \
        )


# NOTE:
# 
# You need to install these packages on Ubunutu 12.04 to make this work:
# 
#     sudo apt-get install make python-stdeb fakeroot python-all rpm
# 
# 

VERSION=1.1

default: debs rpms

debs: build/f5-lbaas-driver_$(VERSION)-1_all.deb \
      build/f5-bigip-lbaas-agent_$(VERSION)-1_all.deb

rpms: build/f5-lbaas-driver-$(VERSION)-1.noarch.rpm \
      build/f5-bigip-lbaas-agent-$(VERSION)-1.noarch.rpm


build/f5-lbaas-driver_$(VERSION)-1_all.deb:
	(cd driver; \
	rm -rf deb_dist; \
	sed -i.orig "s/\(.*version=\).*/\1\'$(VERSION)\',/g" setup.py; \
	python setup.py --command-packages=stdeb.command bdist_deb; \
        ) 
	mkdir -p build
	cp driver/deb_dist/f5-lbaas-driver_$(VERSION)-1_all.deb build/

build/f5-bigip-lbaas-agent_$(VERSION)-1_all.deb:
	(cd agent; \
	rm -rf deb_dist; \
	sed -i.orig "s/\(.*version=\).*/\1\'$(VERSION)\',/g" setup.py; \
	python setup.py --command-packages=stdeb.command bdist_deb; \
        )
	mkdir -p build
	cp agent/deb_dist/f5-bigip-lbaas-agent_$(VERSION)-1_all.deb build

build/f5-lbaas-driver-$(VERSION)-1.noarch.rpm:
	(cd driver; \
	python setup.py bdist_rpm; \
        ) 
	mkdir -p build
	cp driver/dist/f5-lbaas-driver-$(VERSION)-1.noarch.rpm build


build/f5-bigip-lbaas-agent-$(VERSION)-1.noarch.rpm:
	(cd agent; \
	python setup.py bdist_rpm; \
	)
	mkdir -p build
	cp agent/dist/f5-bigip-lbaas-agent-$(VERSION)-1.noarch.rpm build

clean: clean-debs clean-rpms 

clean-debs: 
	rm build/f5-bigip-lbaas-agent_*.deb
	(cd agent; \
	rm -rf deb_dist; \
        )
	rm build/f5-lbaas-driver_*.deb
	(cd driver; \
	rm -rf deb_dist; \
        )

clean-rpms: 
	rm build/f5-bigip-lbaas-agent-*.rpm
	(cd agent; \
	rm -rf dist; \
        )
	rm -f build/f5-lbaas-driver-*.rpm
	(cd driver; \
	rm -rf dist; \
        )


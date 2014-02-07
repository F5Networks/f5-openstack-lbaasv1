# NOTE:
# 
# You need to install these packages on Ubunutu 12.04 to make this work:
# 
#     sudo apt-get install make python-stdeb fakeroot python-all
# 

default: driver/deb_dist/python-f5-lbaas-driver_1.0-1_all.deb \
         agent/deb_dist/python-f5-bigip-lbaas-agent_1.0-1_all.deb


driver/deb_dist/python-f5-lbaas-driver_1.0-1_all.deb: driver/setup.py \
               driver/neutron/services/loadbalancer/drivers/f5/* \
               driver/neutron/services/loadbalancer/drivers/f5/log/*
	(cd driver; \
	rm -rf deb_dist; \
	python setup.py --command-packages=stdeb.command bdist_deb; \
	dpkg -c deb_dist/python-f5-lbaas-driver_1.0-1_all.deb; \
        ) 

agent/deb_dist/python-f5-bigip-lbaas-agent_1.0-1_all.deb: agent/setup.py agent/debian/* \
               agent/neutron/services/loadbalancer/drivers/f5/* \
               agent/neutron/services/loadbalancer/drivers/f5/bigip/*
	(cd agent; \
	rm -rf deb_dist; \
	python setup.py --command-packages=stdeb.command bdist_deb; \
	dpkg -c deb_dist/python-f5-bigip-lbaas-agent_1.0-1_all.deb; \
        )

clean: 
	(cd agent; \
	rm -rf deb_dist; \
        )
	(cd driver; \
	rm -rf deb_dist; \
        )

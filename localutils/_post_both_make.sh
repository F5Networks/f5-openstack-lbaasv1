cd /root/f5-lbaas
make clean
make
service python-f5-bigip-lbaas-agent stop
service neutron-server stop
rm /var/log/neutron/f5-bigip-lbaas-agent.log
rm /var/log/neutron/server.log
apt-get -q -y remove python-f5-bigip-lbaas-agent
apt-get -q -y remove python-f5-lbaas-driver
dpkg -i /root/f5-lbaas/agent/deb_dist/python-f5-bigip-lbaas-agent_1.0-1_all.deb
dpkg -i /root/f5-lbaas/driver/deb_dist/python-f5-lbaas-driver_1.0-1_all.deb
service neutron-server start



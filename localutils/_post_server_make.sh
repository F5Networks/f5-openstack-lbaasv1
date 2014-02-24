cd /root/f5-lbaas
make clean
make
service neutron-server stop
apt-get -q -y remove python-f5-lbaas-driver
dpkg -i /root/f5-lbaas/driver/deb_dist/python-f5-lbaas-driver_1.0-1_all.deb 
rm /var/log/neutron/server.log
service neutron-server start


cd /root/f5-lbaas
make clean
make
service python-f5-bigip-lbaas-agent stop
rm /var/log/neutron/f5-bigip-lbaas-agent.log
apt-get -q -y remove python-f5-bigip-lbaas-agent
dpkg -i /root/f5-lbaas/agent/deb_dist/python-f5-bigip-lbaas-agent_1.0-1_all.deb


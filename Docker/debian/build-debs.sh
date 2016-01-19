#!/bin/bash

echo "Building debian packages..."

cp -R /var/build /tmp
make -C /tmp/build debs
cp -R /tmp/build/agent/deb_dist /var/build/agent
cp -R /tmp/build/common/deb_dist /var/build/common
cp -R /tmp/build/driver/deb_dist /var/build/driver



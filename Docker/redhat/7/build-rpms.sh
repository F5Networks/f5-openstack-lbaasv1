#!/bin/bash

echo "Building RedHat packages..."

cp -R /var/build /tmp
make -C /tmp/build rpms
cp -R /tmp/build/agent/dist /var/build/agent
cp -R /tmp/build/common/dist /var/build/common
cp -R /tmp/build/driver/dist /var/build/driver




#!/bin/bash

echo "Building debian packages..."

cp -R /var/bdir /tmp
make -C /tmp/bdir debs
mkdir -p /var/bdir/build
cp -R /tmp/bdir/agent/deb_dist /var/bdir/build
cp -R /tmp/bdir/common/deb_dist /var/bdir/build
cp -R /tmp/bdir/driver/deb_dist /var/bdir/build



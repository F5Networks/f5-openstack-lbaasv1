#!/bin/sh

#  project_buildScript.sh
#  
#
#  Created by Jodie Putrino on 11/23/15.
#

# clone the website source repo into the travis project directory
pwd
echo "git clone -b develop --verbose git@github.com:jputrino/f5-openstack-docs.git"
git clone -b develop --verbose git@github.com:jputrino/f5-openstack-docs.git

cp -R f5-openstack-docs/_includes doc/
cp -R f5-openstack-docs/_layouts doc/
cp -R f5-openstack-docs/assets doc/
cp f5-openstack-docs/_config.yml doc/

# move the dir where the content lives into _includes for reuse
mv doc/f5-os-lbaasv1/ doc/_includes/

echo "ls -l doc/_includes/f5-os-lbaasv1/"
ls -l doc/_includes/f5-os-lbaasv1/

# build the site with Jekyll
cd doc
echo "Building site with Jekyll"
bundle exec jekyll build -d ./site_build --config _config.yml,_lbaasconfig.yml

# check the html and validate links with html-proofer
#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./site_build

echo "copying site_build to $HOME"
cp -R site_build $HOME/site_build
cd $HOME/site_build
echo "listing contents of $HOME/site_build"
ls -la

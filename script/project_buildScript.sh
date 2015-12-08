#!/bin/sh

#  project_buildScript.sh
#  
#
#  Created by Jodie Putrino on 11/23/15.
#
echo "pwd"
pwd


echo "cd $HOME"
cd $HOME
pwd

# clone the website source repo into the travis build dir
echo "git clone --verbose git@github.com:jputrino/f5-openstack-docs.git"
git clone -b develop --verbose git@github.com:jputrino/f5-openstack-docs.git

# cd back into the project dir
echo "cd /home/travis/build/jputrino/openstack-f5-lbaasv1"
cd /home/travis/build/jputrino/openstack-f5-lbaasv1
echo "pwd"
pwd

# copy the formatting and styling content from the docs repo in the project dir
echo "copying formatting and styling content to $TRAVISREPOSLUG/doc"

echo "cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml"
cp $HOME/f5-openstack-docs/_config.yml doc/

#echo "mkdir ./doc/_layouts"
#mkdir ./doc/_layouts

echo "cp -R $HOME/f5-openstack-docs/_layouts/ doc/"
cp -R $HOME/f5-openstack-docs/_layouts/ doc/

#echo "mkdir ./doc/_includes"
#mkdir ./doc/_includes

echo "cp -R $HOME/f5-openstack-docs/_includes doc/_includes/"
cp -R $HOME/f5-openstack-docs/_includes doc/_includes/

#echo "mkdir ./doc/assets"
#mkdir ./doc/assets

echo "cp -R $HOME/f5-openstack-docs/assets doc/assets/"
cp -R $HOME/f5-openstack-docs/assets doc/assets/

echo "ls -l doc/"
ls -l doc/

echo "ls -l doc/_includes/"
ls -l doc/_includes/

echo "ls -l doc/_layouts/"
ls -l doc/_layouts/

# move the dir where the content lives into _includes for reuse
mv ./doc/f5-os-lbaasv1/ ./doc/_includes/

echo "ls -l doc/_includes/f5-os-lbaasv1/"
ls -l doc/_includes/f5-os-lbaasv1/

# build the site with Jekyll

echo "Building site with Jekyll"
bundle exec jekyll build --verbose --trace -s ./doc -d ./site_build --config ./doc/_config.yml,./doc/_lbaasconfig.yml

# check the html and validate links with html-proofer
#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./site_build

echo "copying site_build to $HOME"
cp -R ./site_build/ $HOME/site_build
cd $HOME/site_build

ls -l

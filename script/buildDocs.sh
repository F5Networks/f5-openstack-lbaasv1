#!/usr/bin/env sh

#  docScript.sh
#  
#
#  Created by Jodie Putrino on 11/18/15.
#

#install gems in Gemfile
#bundle install

# clone the website source repo

git clone --verbose https://github.com/jputrino/f5-openstack-docs.git

mkdir 

# copy content of doc directory into new temp folder
echo "copying doc directory into ~/temp_site"
cp -R ./$TRAVISREPOSLUG/doc ./temp_site/doc

# build site
echo "building site with jekyll"
bundle exec jekyll build --config _lbaasconfig.yml -s ./temp_site/ -d ./site_build

#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./site_build

echo "copying docs to $HOME"
cp -R ./site_build/doc $HOME/site_build

echo "listing contents of $HOME/site_build"
ls -a $HOME/site_build

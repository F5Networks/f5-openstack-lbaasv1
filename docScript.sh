#!/usr/bin/env sh

#  docScript.sh
#  
#
#  Created by Jodie Putrino on 10/27/15.
#

#install gems in Gemfile
#bundle install

# remove the temp directory if it currently exists
rm -rf ./temp_site

# create new jekyll site framework
echo "creating new jekyll site in temp_site directory"
bundle exec jekyll new temp_site

# copy content of doc directory into new temp folder
echo "copying doc directory into temp_site"
cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc ./temp_site/doc

# build site
echo "building site with jekyll"
bundle exec jekyll build -s ./temp_site/ -d ./site_build

#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./temp_site

cp -R ./site_build/doc $HOME/build

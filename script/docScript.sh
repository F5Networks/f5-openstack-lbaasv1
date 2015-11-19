#!/usr/bin/env sh

#  docScript.sh
#  
#
#  Created by Jodie Putrino on 10/27/15.
#

#install gems in Gemfile
#bundle install

# remove the project directory if it currently exists
#rm -rf ./f5-os-lbaasv1


# copy content of doc directory into project folder
echo "copying $TRAVISREPOSLUG/doc into f5-openstack-docs/"
cp -R ./$TRAVISREPOSLUG/doc/ f5-openstack-docs/f5-os-lbaasv1

# build site
echo "building site with jekyll"
bundle exec jekyll build --verbose --trace --config _lbaasconfig.yml -s f5-openstack-docs -d ./site_build

#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./site_build

echo "copying site_build to $HOME"
cp -R ./site_build/ $HOME/$TRAVISREPOSLUG

cd $HOME/site_build

ls




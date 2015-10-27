#!/usr/bin/env sh

#  docScript.sh
#  
#
#  Created by Jodie Putrino on 10/27/15.
#

#install gems in Gemfile
#bundle install

# remove the lbaas_site directory if it currently exists
rm -rf ./lbaas_site

# create new jekyll site framework
bundle exec jekyll new lbaas_site

# copy content of doc directory into new site
cp -R ./doc ./lbaas_site

# build site
cd ./lbaas_site
bundle exec jekyll build

#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./_site

cp -R ./lbaas_site/_site $HOME/build

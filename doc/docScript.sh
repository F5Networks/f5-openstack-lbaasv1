#!/usr/bin/env sh

#  docScript.sh
#  
#
#  Created by Jodie Putrino on 10/27/15.
#

#install gems in Gemfile
#bundle install


# run script to convert files
bundle exec jekyll build -d ./f5-lbaasv1

#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./site_build

cp -R ./f5-lbaasv1 $HOME/f5-lbaasv1

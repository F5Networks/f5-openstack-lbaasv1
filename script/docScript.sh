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

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
# build site
echo "building site with jekyll"
cd /home/travis/build/jputrino/f5-openstack-docs
bundle exec jekyll build --verbose --trace --config ./_config.yml,./_lbaasconfig.yml -d ./site_build
<<<<<<< HEAD
<<<<<<< HEAD
=======

# copy content of doc directory into project folder
#echo "copying $TRAVISREPOSLUG/doc into f5-openstack-docs/"
#cp -R ./$TRAVISREPOSLUG/doc/ f5-openstack-docs/f5-os-lbaasv1

# build site
echo "building site with jekyll"
cd jputrino/f5-openstack-docs
bundle exec jekyll build --verbose --trace --config _lbaasconfig.yml -d ./site_build
<<<<<<< HEAD
>>>>>>> 5a1da6b... Fixes: content re-use trial take 5
=======
# build site
echo "building site with jekyll"
cd /home/travis/build/jputrino/f5-openstack-docs
<<<<<<< HEAD
bundle exec jekyll build --verbose --trace --config ./f5-os-lbaasv1/_lbaasconfig.yml -d ./site_build
>>>>>>> 50e890e... Fixes: Content reuse configurations.
=======
bundle exec jekyll build --verbose --trace --config ./_config.yml,./_includes/f5-os-lbaasv1/_lbaasconfig.yml -d ./site_build
>>>>>>> 7edf285... Fixes: I modified the build scripts and repo jekyll config file.
=======
>>>>>>> d752546... Fixes: travis build # 71 errored
=======
>>>>>>> 5a1da6b... Fixes: content re-use trial take 5
=======
# build site
echo "building site with jekyll"
cd /home/travis/build/jputrino/f5-openstack-docs
<<<<<<< HEAD
bundle exec jekyll build --verbose --trace --config ./f5-os-lbaasv1/_lbaasconfig.yml -d ./site_build
>>>>>>> 50e890e... Fixes: Content reuse configurations.
=======
bundle exec jekyll build --verbose --trace --config ./_config.yml,./_includes/f5-os-lbaasv1/_lbaasconfig.yml -d ./site_build
>>>>>>> 7edf285... Fixes: I modified the build scripts and repo jekyll config file.
=======
>>>>>>> d752546... Fixes: travis build # 71 errored

#echo "proofing site with htmlproofer"
#bundle exec htmlproof ./site_build

echo "copying site_build to $HOME"
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
cp -R ./site_build/_includes/f5-os-lbaasv1 $HOME/site_build/_includes
cp -R ./site_build/f5-os-lbaasv1 $HOME/site_build/f5-os-lbaasv1
=======
cp -R ./site_build/ $HOME/site_build
=======
cp -R ./site_build/f5-os-lbaasv1/ $HOME/site_build
>>>>>>> 50e890e... Fixes: Content reuse configurations.

>>>>>>> 01794ed... Fixes: Content re-use trial take 4
cd $HOME/site_build

ls -l

=======
cp -R ./site_build/_includes/f5-os-lbaasv1 $HOME/site_build/_includes
cp -R ./site_build/f5-os-lbaasv1 $HOME/site_build/f5-os-lbaasv1
cd $HOME/site_build

ls -l
>>>>>>> 7edf285... Fixes: I modified the build scripts and repo jekyll config file.
=======
cp -R ./site_build/ $HOME/$TRAVISREPOSLUG
=======
cp -R ./site_build/ $HOME/site_build
>>>>>>> 01794ed... Fixes: Content re-use trial take 4
=======
cp -R ./site_build/f5-os-lbaasv1/ $HOME/site_build
>>>>>>> 50e890e... Fixes: Content reuse configurations.

cd $HOME/site_build

ls
>>>>>>> 8adc1e8... Fixes: Content re-use trial run
=======
cp -R ./site_build/_includes/f5-os-lbaasv1 $HOME/site_build/_includes
cp -R ./site_build/f5-os-lbaasv1 $HOME/site_build/f5-os-lbaasv1
cd $HOME/site_build

ls -l
>>>>>>> 7edf285... Fixes: I modified the build scripts and repo jekyll config file.




#!/bin/sh

#  project_buildScript.sh
#  
#
#  Created by Jodie Putrino on 11/23/15.
#
echo "pwd"
pwd

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
echo "cd $HOME"
cd $HOME
=======
echo "cd /home/travis/build/jputrino"
<<<<<<< HEAD
<<<<<<< HEAD
cd /home/travis/build/jputrino
>>>>>>> 75e09e2... Fixes: add corrected map file for 'install the f5 lbaas plug-in'
=======
=======
echo "cd $HOME"
>>>>>>> 3a14336... Fixes: build issues
cd $HOME
>>>>>>> d777465... Fixes: travis build 86 errored
=======
echo "cd /home/travis/build/jputrino"
cd /home/travis/build/jputrino
>>>>>>> 75e09e2... Fixes: add corrected map file for 'install the f5 lbaas plug-in'
=======
=======
echo "cd $HOME"
>>>>>>> 3a14336... Fixes: build issues
cd $HOME
>>>>>>> d777465... Fixes: travis build 86 errored

echo "pwd"
pwd

# clone the website source repo into the travis build dir
echo "git clone --verbose git@github.com:jputrino/f5-openstack-docs.git"
git clone --verbose git@github.com:jputrino/f5-openstack-docs.git

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
# cd back into the project dir
echo "cd /home/travis/build/jputrino/openstack-f5-lbaasv1"
cd /home/travis/build/jputrino/openstack-f5-lbaasv1
echo "pwd"
pwd

# copy the formatting and styling content from the docs repo in the project dir
echo "copying formatting and styling content to $TRAVISREPOSLUG/doc"
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD

echo "cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml"
cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml

echo "mkdir ./doc/_layouts"
mkdir ./doc/_layouts

echo "cp -R $HOME/f5-openstack-docs/_layouts/ doc/_layouts/"
cp -R $HOME/f5-openstack-docs/_layouts/ doc/_layouts/

echo "mkdir ./doc/_includes"
mkdir ./doc/_includes
echo "cp -R $HOME/f5-openstack-docs/_includes doc/_includes/"
cp -R $HOME/f5-openstack-docs/_includes doc/_includes/

echo "mkdir ./doc/assets"
mkdir ./doc/assets
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
=======
=======
# cd back into the project dir
echo "cd /home/travis/build/jputrino/openstack-f5-lbaasv1"
>>>>>>> 27c64b4... Fixes: I need to use the formatting assets from the website repo to build pages in the project repo.
cd /home/travis/build/jputrino/openstack-f5-lbaasv1
echo "pwd"
pwd

# copy the formatting and styling content from the docs repo in the project dir
echo "copying formatting and styling content to $TRAVISREPOSLUG/doc"
<<<<<<< HEAD
=======
cp /home/travis/build/jputrino/f5-openstack-docs/_config.yml ./doc
>>>>>>> 69f93de... Fixes: travis build 79 failed
=======
cp /home/travis/build/jputrino/f5-openstack-docs/_config.yml ./doc/_config.yml
<<<<<<< HEAD
>>>>>>> e3188c4... Fixes: travis build 80 failed
=======
mkdir ./doc/_layouts
>>>>>>> 927cc35... Fixes: travis build 85 errored
cp -R /home/travis/build/jputrino/f5-openstack-docs/_layouts/ ./doc/_layouts
=======
=======

>>>>>>> 3a14336... Fixes: build issues
echo "cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml"
cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml

echo "mkdir ./doc/_layouts"
mkdir ./doc/_layouts

echo "cp -R $HOME/f5-openstack-docs/_layouts/ doc/_layouts/"
cp -R $HOME/f5-openstack-docs/_layouts/ doc/_layouts/

echo "mkdir ./doc/_includes"
>>>>>>> d777465... Fixes: travis build 86 errored
mkdir ./doc/_includes
echo "cp -R $HOME/f5-openstack-docs/_includes doc/_includes/"
cp -R $HOME/f5-openstack-docs/_includes doc/_includes/

echo "mkdir ./doc/assets"
mkdir ./doc/assets
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

<<<<<<< HEAD
>>>>>>> 75e09e2... Fixes: add corrected map file for 'install the f5 lbaas plug-in'
=======
ls -l
>>>>>>> 27c64b4... Fixes: I need to use the formatting assets from the website repo to build pages in the project repo.
=======
=======
# cd back into the project dir
echo "cd /home/travis/build/jputrino/openstack-f5-lbaasv1"
>>>>>>> 27c64b4... Fixes: I need to use the formatting assets from the website repo to build pages in the project repo.
cd /home/travis/build/jputrino/openstack-f5-lbaasv1
echo "pwd"
pwd

# copy the formatting and styling content from the docs repo in the project dir
echo "copying formatting and styling content to $TRAVISREPOSLUG/doc"

echo "cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml"
cp $HOME/f5-openstack-docs/_config.yml doc/_config.yml

echo "mkdir ./doc/_layouts"
mkdir ./doc/_layouts

echo "cp -R $HOME/f5-openstack-docs/_layouts/ doc/_layouts/"
cp -R $HOME/f5-openstack-docs/_layouts/ doc/_layouts/

echo "mkdir ./doc/_includes"
mkdir ./doc/_includes
echo "cp -R $HOME/f5-openstack-docs/_includes doc/_includes/"
cp -R $HOME/f5-openstack-docs/_includes doc/_includes/

echo "mkdir ./doc/assets"
mkdir ./doc/assets
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

<<<<<<< HEAD
>>>>>>> 75e09e2... Fixes: add corrected map file for 'install the f5 lbaas plug-in'
=======
ls -l
>>>>>>> 27c64b4... Fixes: I need to use the formatting assets from the website repo to build pages in the project repo.

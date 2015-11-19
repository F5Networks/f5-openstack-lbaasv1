#!/usr/bin/env sh

#  buildDocs.sh
#  
#
#  Created by Jodie Putrino on 11/18/15.
#
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
echo "pwd"
=======
>>>>>>> 7edf285... Fixes: I modified the build scripts and repo jekyll config file.
=======
>>>>>>> 7edf285... Fixes: I modified the build scripts and repo jekyll config file.
pwd

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
=======
echo "pwd"
=======
>>>>>>> 5a1da6b... Fixes: content re-use trial take 5
pwd
=======
cd /home/travis/build/jputrino
>>>>>>> 50e890e... Fixes: Content reuse configurations.

<<<<<<< HEAD
>>>>>>> 264fd36... Summary -- I edited buildDocs.sh (added an 'echo' line before every command so I can see exactly where the build is failing).
echo "cd /home/travis/build/jputrino"
cd /home/travis/build/jputrino
=======
pwd
>>>>>>> 5a1da6b... Fixes: content re-use trial take 5
=======
=======
echo "pwd"
pwd

echo "cd /home/travis/build/jputrino"
>>>>>>> 264fd36... Summary -- I edited buildDocs.sh (added an 'echo' line before every command so I can see exactly where the build is failing).
cd /home/travis/build/jputrino
>>>>>>> 50e890e... Fixes: Content reuse configurations.
=======
# clone the website source repo into the travis build dir
<<<<<<< HEAD
<<<<<<< HEAD
cd home/travis/build
>>>>>>> 01794ed... Fixes: Content re-use trial take 4
=======
cd ..
>>>>>>> 5a1da6b... Fixes: content re-use trial take 5
=======
>>>>>>> 50e890e... Fixes: Content reuse configurations.

<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
echo "pwd"
pwd
=======
# clone the website source repo into the travis build dir
<<<<<<< HEAD
<<<<<<< HEAD
cd home/travis/build
>>>>>>> 01794ed... Fixes: Content re-use trial take 4
=======
cd ..
>>>>>>> 5a1da6b... Fixes: content re-use trial take 5
=======
>>>>>>> 50e890e... Fixes: Content reuse configurations.
=======
echo "pwd"
pwd
>>>>>>> 264fd36... Summary -- I edited buildDocs.sh (added an 'echo' line before every command so I can see exactly where the build is failing).
=======
echo "pwd"
pwd
>>>>>>> 264fd36... Summary -- I edited buildDocs.sh (added an 'echo' line before every command so I can see exactly where the build is failing).

# clone the website source repo into the travis build dir
echo "git clone --verbose git@github.com:jputrino/f5-openstack-docs.git"
git clone --verbose git@github.com:jputrino/f5-openstack-docs.git

# change to the f5-openstack-docs dir
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
echo "cd /home/travis/build/jputrino/f5-openstack-docs"
cd /home/travis/build/jputrino/f5-openstack-docs

echo "mkdir ./f5-os-lbaasv1"
mkdir ./f5-os-lbaasv1

#echo "mkdir ./_includes/f5-os-lbaasv1"
#mkdir ./_includes/f5-os-lbaasv1

# copy _lbaasconfig.yml to f5-openstack-docs/
#echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/_lbaasconfig.yml ."
#cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/_lbaasconfig.yml .

# copy the os-lbaasv1 source files into the f5-openstack-docs/_includes dir
echo "cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/* ./_includes/f5-os-lbaasv1"
cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/* ./_includes/f5-os-lbaasv1
ls -l ./_includes/f5-os-lbaasv1

# copy the os-lbaasv1 files into the os-f5-lbaasv1 dir
echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.md ./f5-os-lbaasv1"
cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.md ./f5-os-lbaasv1

echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.html ./f5-os-lbaasv1"
cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.html ./f5-os-lbaasv1
=======
cd jputrino/f5-openstack-docs
>>>>>>> 01794ed... Fixes: Content re-use trial take 4
=======
=======
echo "cd /home/travis/build/jputrino/f5-openstack-docs"
>>>>>>> 264fd36... Summary -- I edited buildDocs.sh (added an 'echo' line before every command so I can see exactly where the build is failing).
cd /home/travis/build/jputrino/f5-openstack-docs
>>>>>>> 50e890e... Fixes: Content reuse configurations.

echo "mkdir ./f5-os-lbaasv1"
mkdir ./f5-os-lbaasv1

#echo "mkdir ./_includes/f5-os-lbaasv1"
#mkdir ./_includes/f5-os-lbaasv1

# copy _lbaasconfig.yml to f5-openstack-docs/
#echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/_lbaasconfig.yml ."
#cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/_lbaasconfig.yml .

# copy the os-lbaasv1 source files into the f5-openstack-docs/_includes dir
echo "cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/* ./_includes/f5-os-lbaasv1"
cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/* ./_includes/f5-os-lbaasv1
ls -l ./_includes/f5-os-lbaasv1

# copy the os-lbaasv1 files into the os-f5-lbaasv1 dir
echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.md ./f5-os-lbaasv1"
cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.md ./f5-os-lbaasv1

echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.html ./f5-os-lbaasv1"
cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.html ./f5-os-lbaasv1
=======
cd jputrino/f5-openstack-docs
>>>>>>> 01794ed... Fixes: Content re-use trial take 4
=======
=======
echo "cd /home/travis/build/jputrino/f5-openstack-docs"
>>>>>>> 264fd36... Summary -- I edited buildDocs.sh (added an 'echo' line before every command so I can see exactly where the build is failing).
cd /home/travis/build/jputrino/f5-openstack-docs
>>>>>>> 50e890e... Fixes: Content reuse configurations.

echo "mkdir ./f5-os-lbaasv1"
mkdir ./f5-os-lbaasv1

#echo "mkdir ./_includes/f5-os-lbaasv1"
#mkdir ./_includes/f5-os-lbaasv1

# copy _lbaasconfig.yml to f5-openstack-docs/
#echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/_lbaasconfig.yml ."
#cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/_lbaasconfig.yml .

# copy the os-lbaasv1 source files into the f5-openstack-docs/_includes dir
echo "cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/* ./_includes/f5-os-lbaasv1"
cp -R /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/_includes/* ./_includes/f5-os-lbaasv1
ls -l ./_includes/f5-os-lbaasv1

# copy the os-lbaasv1 files into the os-f5-lbaasv1 dir
echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.md ./f5-os-lbaasv1"
cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.md ./f5-os-lbaasv1

echo "cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.html ./f5-os-lbaasv1"
cp /home/travis/build/jputrino/openstack-f5-lbaasv1/doc/*.html ./f5-os-lbaasv1


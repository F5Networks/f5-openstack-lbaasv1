#!/usr/bin/env sh

#  docScript2.sh
#  
#
#  Created by Jodie Putrino on 10/27/15.
#

#install gems in Gemfile
bundle install

#install Pandoc from source
set -ex
wget https://github.com/jgm/pandoc/archive/1.15.1.tar.gz
tar -xzvf pandoc-1.15.1.tar.gz
cd pandoc-1.15.1 && ./configure --prefix=/usr && make && sudo make install

# run script to convert files
FILES="*.md"
for f in $FILES
do
# extension="${f##*.}"
filename="${f%.*}"
echo "Converting $f to $filename.html"
pandoc "$f" -t html5 -o "$filename.html"
# uncomment this line to delete the source file.
# rm $f
done

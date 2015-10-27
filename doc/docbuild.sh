#!/usr/bin/env bash
set -e # halt script on error

FILES=*.md
for f in $FILES
do
# extension="${f##*.}"
filename="${f%.*}"
echo "Converting $f to $filename.html"
`pandoc -s $f -f markdown -t html5 -o $filename.html`
# uncomment this line to delete the source file.
# rm $f
done

#echo "proofing site with htmlproofer"
#bundle exec htmlproof

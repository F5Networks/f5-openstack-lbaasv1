#!/bin/bash

LAB_HOST=10.1.0.39

cat ./_pre_both_make.sh | ssh root@$LAB_HOST
rsync -avz -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" --progress /data/project/f5-lbaas root@$LAB_HOST:/root/
cat ./_post_both_make.sh | ssh root@$LAB_HOST


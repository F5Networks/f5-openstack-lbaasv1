#!/bin/bash

rsync -avz -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" --progress /data/project/f5-lbaas root@10.1.0.39:/root/


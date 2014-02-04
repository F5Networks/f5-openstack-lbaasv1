import os

if os.path.exists('/etc/init.d'):
    os.symlink('/lib/init/upstart-job',
               '/etc/init.d/f5-bigip-lbaas-agent')

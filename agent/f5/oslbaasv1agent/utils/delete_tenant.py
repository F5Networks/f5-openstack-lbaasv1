#!/usr/bin/env python

# Copyright 2014 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import sys

from oslo.config import cfg

from f5.bigip import bigip


def print_usage():
    message = '\nUsage:\n'
    message += '  python -m delete_tenant'
    message += ' --tenant-id=[tenant_id] '
    message += ' --config-file=f5-oslbaasv1-agent.ini\n\n'
    message += '   tenant-id - uuid of the tenant to remove from the BIG-IPs\n'
    print(message)


def delete_tenant(tenant_id, bigips):
    for bigip in bigips:
        try:
            bigip.system.purge_folder_contents(folder=tenant_id)
            bigip.system.purge_folder(folder=tenant_id)
        except Exception as exc:
            if str(exc.message).index('was not found') > 0:
                print('tenant %s has not objects on %s'
                      % (tenant_id, bigip.device.get_device_name()))

if __name__ == "__main__":

    OPTS = [
        cfg.StrOpt(
            'tenant-id',
            default=None
        )
    ]

    cfg.CONF.register_cli_opts(opts=OPTS)

    BIGIP_OPTS = [
        cfg.StrOpt(
            'environment_prefix', default=''
        ),
        cfg.StrOpt(
            'icontrol_hostname', default='192.168.245.100'
        ),
        cfg.StrOpt(
            'icontrol_username', default='admin'
        ),
        cfg.StrOpt(
            'icontrol_password', default='admin', secret=True
        )
    ]

    cfg.CONF.register_opts(opts=BIGIP_OPTS)

    cfg.CONF()

    if (cfg.CONF.tenant_id is None) or (cfg.CONF.config_file is None):
        print_usage()
        sys.exit(1)

    print('Using agent configuration file %s' % cfg.CONF.config_file)

    hostnames = cfg.CONF.icontrol_hostname.split(',')
    hostnames = [item.strip() for item in hostnames]
    hostnames = sorted(hostnames)

    username = cfg.CONF.icontrol_username
    password = cfg.CONF.icontrol_password

    bigips = []
    for name in hostnames:
        bigip.bigip_interfaces.OBJ_PREFIX = cfg.CONF.environment_prefix + '_'
        bigips.append(bigip.BigIP(name, username, password))

    delete_tenant(cfg.CONF.tenant_id, bigips)

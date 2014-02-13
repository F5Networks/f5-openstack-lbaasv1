from oslo.config import cfg
from neutron.common import log
from neutron.openstack.common import log as logging
from neutron.common.exceptions import InvalidConfigurationOption
from neutron.services.loadbalancer import constants as lb_const
from neutron.services.loadbalancer.drivers.f5.bigip \
                                     import agent_manager as am
from f5.bigip import bigip
from f5.common import constants as f5const
from f5.bigip import exceptions as f5ex

import netaddr

LOG = logging.getLogger(__name__)
NS_PREFIX = 'qlbaas-'

__VERSION__ = '0.1.1'

OPTS = [
    cfg.StrOpt(
        'icontrol_hostname',
        help=_('The hostname (name or IP address) to use for iControl access'),
    ),
    cfg.StrOpt(
        'icontrol_username',
        help=_('The username to use for iControl access'),
    ),
    cfg.StrOpt(
        'icontrol_password',
        help=_('The password to use for iControl access'),
    )
]


class iControlDriver(object):

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(OPTS)
        self.pool_to_port_id = {}
        self.bigip = None
        self.connected = False

        self._init_connection()

        LOG.debug(_('iControlDriver initialized: hostname:%s username:%s'
                    % (self.hostname, self.username)))

    @am.is_connected
    @log.log
    def sync(self, logical_config):
        pass

    @am.is_connected
    @log.log
    def create_vip(self, vip, network):
        self._assure_network(network)
        vip_network = netaddr.IPNetwork(network['subnet']['cidr'])
        vip_netmask = str(vip_network.netmask())
        self.bigip.virtual_server.create(name=vip['id'],
                                         ip_address=vip['address'],
                                         mask=vip[vip_netmask],
                                         port=vip['protocol_port'],
                                         protocol=['TCP'],
                                         vlan_name=network['id'],
                                         folder=vip['tenant_id'])
        if 'id' in vip['pool']:
            self.bigip.virtual_server.set_pool(
                                         name=vip['id'],
                                         pool_name=vip['pool']['id'],
                                         folder=vip['tenant_id']
                                        )
        return True

    @am.is_connected
    @log.log
    def update_vip(self, old_vip, vip, old_network, network):
        return True

    @am.is_connected
    @log.log
    def delete_vip(self, vip, network):
        self.bigip.virtual_server.delete(name=vip['id'],
                                   folder=vip['tenant_id'])
        if network:
            if network['type'] == 'vlan' or network['type'] == 'flat':
                self.bigip.vlan.delete(name=network['id'],
                                       folder=network['tenant_id'])
        return True

    @am.is_connected
    @log.log
    def create_pool(self, pool, network):

        self._assure_network(network)

        self.bigip.pool.create(name=pool['id'],
                               lb_method=pool['lb_method'],
                               description=pool['name'],
                               folder=pool['tenant_id']
                              )
        for member in pool['members']:
            # force tenancy on pool
            member['tenant_id'] = pool['tenant_id']
            self.create_member(member, network)

        for health_monitor in pool['health_monitors']:
            self.create_pool_health_monitor(health_monitor, pool, network)

        return True

    @am.is_connected
    @log.log
    def update_pool(self, old_pool, pool, old_network, network):
        return True

    @am.is_connected
    @log.log
    def delete_pool(self, pool, network):
        # WARNIG network might be NONE if
        # pool deleted by periodic task
        self.bigip.pool.delete(name=pool['id'],
                                   folder=pool['tenant_id'])
        if network:
            if network['type'] == 'vlan' or network['type'] == 'flat':
                self.bigip.vlan.delete(name=network['id'],
                                       folder=network['tenant_id'])
        return True

    @am.is_connected
    @log.log
    def create_member(self, member, network):
        self.bigip.pool.add_member(name=member['id'],
                                   ip_address=member['address'],
                                   port=member['protocol_port'],
                                   folder=member['tenant_id'])
        return True

    @am.is_connected
    @log.log
    def update_member(self, old_member, member, old_network, network):
        return True

    @am.is_connected
    @log.log
    def delete_member(self, member, network):
        self.bigip.pool.remove_member(name=member['id'],
                                      ip_address=member['address'],
                                      port=member['protocol_port'],
                                      folder=member['tenant_id'])
        return True

    @am.is_connected
    @log.log
    def create_pool_health_monitor(self, health_monitor, pool, network):
        timeout = int(health_monitor['timeout']) * \
                  int(health_monitor['max_retries'])
        self.bigip.monitor.create(
                                  name=health_monitor['id'],
                                  mon_type=health_monitor['type'],
                                  interval=int(health_monitor['delay']),
                                  timeout=timeout,
                                  send_text=None,
                                  recv_text=None,
                                  folder=pool['tenant_id'])
        self.bigip.pool.add_monitor(name=pool['id'],
                                    monitor_name=health_monitor['id'],
                                    folder=pool['tenant_id'])
        return True

    @am.is_connected
    @log.log
    def update_health_monitor(self, old_health_monitor,
                              health_monitor, pool, network):
        return True

    @am.is_connected
    @log.log
    def delete_pool_health_monitor(self, health_monitor, pool, network):
        self.bigip.pool.remove_monitor(name=pool['id'],
                                       monitor_name=health_monitor['id'],
                                       folder=pool['tenant_id'])
        self.bigip.monitor.delete(name=health_monitor['id'],
                                  folder=pool['tenant_id'])
        return True

    # @am.is_connected
    @log.log
    def get_stats(self, logical_service):

        bytecount = 0
        connections = 0
        stats = {}
        stats[lb_const.STATS_IN_BYTES] = bytecount
        stats[lb_const.STATS_OUT_BYTES] = bytecount * 5
        stats[lb_const.STATS_ACTIVE_CONNECTIONS] = connections
        stats[lb_const.STATS_TOTAL_CONNECTIONS] = connections * 10

        #example
        # stats['members'] = {'members':
        #                     {
        #                      member['uuid']:{'status':member['status']},
        #                      member['uuid']:{'status': member['status']}
        #                     }          }
        #                    }

        # need to get members for this pool and update their status
        members = {'members': {}}
        if hasattr(logical_service, 'members'):
            for member in logical_service['members']:
                members['members'][member['uuid']:{'status':member['status']}]
        stats['members'] = members
        return stats

    @log.log
    def remove_orphans(self, known_pool_ids):
        raise NotImplementedError()

    def _assure_network(self, network):
        if network['network_type'] == 'vlan':
            if network['shared']:
                network_folder = 'Common'
            else:
                network_folder = network['id']

            if not self.bigip.vlan.exists(name=network['id'],
                                          folder=network_folder):
                self.bigip.vlan.create(name=network['id'],
                                       vlanid=network['segmentation_id'],
                                       interface='1.1',
                                       folder=network_folder,
                                       description=network['name'])
        if network['network_type'] == 'flat':
            if network['shared']:
                network_folder = 'Common'
            else:
                network_folder = network['id']

            if not self.bigip.vlan.exists(name=network['id'],
                                          folder=network_folder):
                self.bigip.vlan.create(name=network['id'],
                                       vlanid=0,
                                       interface='1.1',
                                       folder=network_folder,
                                       description=network['name'])
        elif network['network_type'] == 'local':
            if network['shared']:
                network_folder = 'Common'
            else:
                network_folder = network['id']

            if not self.bigip.vlan.exists(name=network['name'],
                                          folder=network_folder):
                self.bigip.vlan.create(name=network['name'],
                                       vlanid=0,
                                       interface='1.1',
                                       folder=network_folder,
                                       description=network['name'])

    def _init_connection(self):
        try:
            if not self.connected:
                if not self.conf.icontrol_hostname:
                    raise InvalidConfigurationOption(
                                 opt_name='icontrol_hostname',
                                 opt_value='valid hostname or IP address')
                if not self.conf.icontrol_username:
                    raise InvalidConfigurationOption(
                                 opt_name='icontrol_username',
                                 opt_value='valid username')
                if not self.conf.icontrol_password:
                    raise InvalidConfigurationOption(
                                 opt_name='icontrol_password',
                                 opt_value='valid password')

                self.hostname = self.conf.icontrol_hostname
                self.username = self.conf.icontrol_username
                self.password = self.conf.icontrol_password

                LOG.debug(_('opening iControl connection to %s @ %s' % (
                                                                self.username,
                                                                self.hostname)
                            ))
                self.bigip = bigip.BigIP(self.hostname,
                                         self.username,
                                         self.password)

                # device validate
                major_version = self.bigip.system.get_major_version()
                if major_version < f5const.MIN_TMOS_MAJOR_VERSION:
                    raise f5ex.MajorVersionValidateFailed(
                            'device must be at least TMOS %s.%s'
                            % (f5const.MIN_TMOS_MAJOR_VERSION,
                               f5const.MIN_TMOS_MINOR_VERSION))
                minor_version = self.bigip.system.get_minor_version()
                if minor_version < f5const.MIN_TMOS_MINOR_VERSION:
                    raise f5ex.MinorVersionValidateFailed(
                            'device must be at least TMOS %s.%s'
                            % (f5const.MIN_TMOS_MAJOR_VERSION,
                               f5const.MIN_TMOS_MINOR_VERSION))

                LOG.debug(_('connected to iControl device %s @ %s ver %s.%s'
                            % (self.username, self.hostname,
                               major_version, minor_version)))

                self.connected = True

        except Exception as e:
            LOG.error(_('Could not communicate with iControl device: %s'
                           % e.message))

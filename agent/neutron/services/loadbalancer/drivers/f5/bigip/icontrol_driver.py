from oslo.config import cfg
from neutron.common import log
from neutron.openstack.common import log as logging
from neutron.common.exceptions import InvalidConfigurationOption
from neutron.services.loadbalancer import constants as lb_const
from f5.bigip import bigip
from f5.common import constants as f5const
from f5.bigip import exceptions as f5ex

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

        if not self.conf.icontrol_hostname:
            raise InvalidConfigurationOption(opt_name='icontrol_hostname',
                                   opt_value='valid hostname or IP address')
        if not self.conf.icontrol_username:
            raise InvalidConfigurationOption(opt_name='icontrol_username',
                                             opt_value='valid username')
        if not self.conf.icontrol_password:
            raise InvalidConfigurationOption(opt_name='icontrol_password',
                                             opt_value='valid password')

        self.hostname = self.conf.icontrol_hostname
        self.username = self.conf.icontrol_username
        self.password = self.conf.icontrol_password

        LOG.debug(_('opening iControl connection to %s @ %s' % (self.username,
                                                                self.hostname)
                    ))

        self.bigip = bigip.BigIP(self.hostname, self.username, self.password)

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

        LOG.debug(_('iControlDriver initialized: hostname:%s username:%s'
                    % (self.hostname, self.username)))

    @log.log
    def sync(self, logical_config):
        pass

    @log.log
    def create_vip(self, vip, network):
        return True

    @log.log
    def update_vip(self, old_vip, vip, old_network, network):
        return True

    @log.log
    def delete_vip(self, vip, network):
        return True

    @log.log
    def create_pool(self, pool, network):
        #pool_id = pool['id']
        #pool_name = pool['name']
        #pool_tenant_id = pool['tenant_id']

        #l2_tenant_id = network['tenant_id']
        #l2_type = network['network_type']
        #l2_segmentation_id = network['segmentation_id']
        #l2_name = network['name']

        #if not l2_type in constants.VALID_L2_TYPES:
        #    raise exceptions.InvalidNetworkType(
        #            'network type was %s, must be in %s'
        #            % (l2_type, constants.VALID_L2_TYPES))
        #if l2_type == 'local':
        #    if self.bigip.vlan.exists(l2_name):
        return True

    @log.log
    def update_pool(self, old_pool, pool, old_network, network):
        return True

    @log.log
    def delete_pool(self, pool, network):
        # WARNIG network might be NONE if
        # pool deleted by periodic task
        return True

    @log.log
    def create_member(self, member, network):
        return True

    @log.log
    def update_member(self, old_member, member, old_network, network):
        return True

    @log.log
    def delete_member(self, member, network):
        return True

    @log.log
    def create_pool_health_monitor(self, health_monitor, pool, network):
        return True

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool, network):
        return True

    @log.log
    def delete_pool_health_monitor(self, health_monitor, pool, network):
        return True

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

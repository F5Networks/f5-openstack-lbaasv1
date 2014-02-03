from oslo.config import cfg
from neutron.common import log
from neutron.openstack.common import log as logging
from neutron.common.exceptions import InvalidConfigurationOption

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

        LOG.debug(_('iControlDriver initialized: hostname:%s username:%s'
                    % (self.hostname, self.username)))

    @log.log
    def sync(self, logical_config):
        pass

    @log.log
    def create_vip(self, vip, network):
        pass

    @log.log
    def update_vip(self, old_vip, vip, old_network, network):
        pass

    @log.log
    def delete_vip(self, vip, network):
        pass

    @log.log
    def create_pool(self, pool, network):
        pass

    @log.log
    def update_pool(self, old_pool, pool, old_network, network):
        pass

    @log.log
    def delete_pool(self, pool, network):
        pass

    @log.log
    def create_member(self, member, network):
        pass

    @log.log
    def update_member(self, old_member, member, old_network, network):
        pass

    @log.log
    def delete_member(self, member, network):
        pass

    @log.log
    def create_pool_health_monitor(self, health_monitor, pool, network):
        pass

    @log.log
    def update_health_monitor(self, context, old_health_monitor,
                              health_monitor, pool, network):
        pass

    @log.log
    def delete_pool_health_monitor(self, health_monitor, pool, network):
        pass

    @log.log
    def get_stats(self, pool):
        return None

    @log.log
    def remove_orphans(self, known_pool_ids):
        raise NotImplementedError()

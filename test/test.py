import gettext
gettext.install('test')

from oslo.config import cfg
from neutron.plugins.common import constants as plugin_const
from neutron.services.loadbalancer.drivers.f5.bigip.icontrol_driver \
    import iControlDriver, OPTS as icontrol_OPTS

conf = cfg.CONF
conf.register_opts(icontrol_OPTS)

conf.icontrol_hostname = '10.144.64.93,10.144.64.94'
conf.f5_external_physical_mappings = ["default:1.3:True"]
conf.icontrol_config_mode = 'iapp'

# These should be registered using OPTS in the agent_manager
# but we would rather not import the agent_manager because of
# the class dependencies.
conf.use_namespaces = True
conf.f5_global_routed_mode = False

driver = iControlDriver(conf, False)

service = {'pool': {'id': 'pool_id_1',
                    'status': plugin_const.PENDING_CREATE,
                    'tenant_id': '45d34b03a8f24465a5ad613436deb773'},

           'members': [{'id': 'member_id_1',
                        'status': plugin_const.PENDING_CREATE,
                        'address': '10.10.1.2',
                        'network': {'id': 'net_id_1', 'shared': False},
                        'protocol_port': "80"},

                       {'id': 'member_id_2',
                        'status': plugin_const.PENDING_CREATE,
                        'address': '10.10.1.4',
                        'network': {'id': 'net_id_1', 'shared': False},
                        'protocol_port': "80"}],

           'vip': {'id': 'vip_id_1',
                   'status': plugin_const.PENDING_CREATE,
                   'address': '10.20.1.99',
                   'network': {'id': 'net_id_1', 'shared': False}}}

driver.sync(service)


""" Module for managing L3 to L2 port bindings on F5 BIG-IP in Neutron """
# pylint: disable=no-self-use

from neutron.openstack.common import log as logging
from f5.bigip import exceptions as f5ex

LOG = logging.getLogger(__name__)


class AllowedAddressPairs(object):
    """ Class for configuring L3 address bindings to L2 ports """
    def __init__(self, conf, vcmp_manager, fdb_connector):
        self.conf = conf
        self.l3_binding_mappings = {}

        LOG.debug(_('reading static L3 address bindings'))
        for subnet_id in conf.l3_binding_static_mappings:
            binding_list = conf.l3_binding_static_mappings[subnet_id]
            if isinstance(binding_list, list):
                for (port_id, device_id) in binding_list:
                    if port_id:
                        if subnet_id in self.l3_binding_mappings:
                            self.l3_binding_mappings[subnet_id] = binding_list
                        else:
                            self.l3_binding_mappings[subnet_id] = \
                               self.l3_binding_mappings + binding_list
                        LOG.debug(_('subnet %s bound to port: %s, device %s'
                            % (subnet_id, port_id, device_id)))

    def bind_address(self, subnet_id=None, ip_address=None):
        pass

    def unbind_address(self, subnet_id=None, ip_address=None):
        pass

    def _discover_local_selfips(self):
        pass


class NuageL3Binding(object):
    """ Class for configuring L3 address bindings to L2 ports """
    def __init__(self, conf, vcmp_manager, fdb_connector):
        self.conf = conf
        self.l3_binding_mappings = {}

        LOG.debug(_('reading static L3 address bindings'))
        for subnet_id in conf.l3_binding_static_mappings:
            binding_list = conf.l3_binding_static_mappings[subnet_id]
            if isinstance(binding_list, list):
                for (port_id, device_id) in binding_list:
                    if port_id:
                        if subnet_id in self.l3_binding_mappings:
                            self.l3_binding_mappings[subnet_id] = binding_list
                        else:
                            self.l3_binding_mappings[subnet_id] = \
                               self.l3_binding_mappings + binding_list
                        LOG.debug(_('subnet %s bound to port: %s, device %s'
                            % (subnet_id, port_id, device_id)))

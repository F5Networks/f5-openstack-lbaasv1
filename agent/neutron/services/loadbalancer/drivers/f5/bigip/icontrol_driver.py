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

import urllib2
import netaddr
import os

import threading

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

    # containers
    __bigips = {}
    __traffic_groups = []

    # mappings
    __device_to_bigip = {}
    __vips_to_traffic_group = {}
    __gw_to_traffic_group = {}

    # scheduling counts
    __vips_on_traffic_groups = {}
    __gw_on_traffic_groups = {}

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(OPTS)
        self.pool_to_port_id = {}
        self.connected = False

        self.lock = threading.Lock()

        self._init_connection()

        LOG.debug(_('iControlDriver initialized to %d hosts with username:%s'
                    % (len(self.__bigips), self.username)))
        self.interface_mapping = {}
        self.tagging_mapping = {}

        mappings = str(self.conf.f5_external_physical_mappings).split(",")
        # map format is   phynet:interface:tagged
        for maps in mappings:
            intmap = maps.split(':')
            intmap[0] = str(intmap[0]).strip()
            self.interface_mapping[intmap[0]] = str(intmap[1]).strip()
            self.tagging_mapping[intmap[0]] = str(intmap[2]).strip()
            LOG.debug(_('physical_network %s = BigIP interface %s, tagged %s'
                        % (intmap[0], intmap[1], intmap[2])
                        ))

    @am.is_connected
    @log.log
    def sync(self, service):
        self.lock.acquire()
        try:
            self._assure_service_networks(service)
            self._assure_service(service)
            return True
        finally:
            self.lock.release()

    @am.is_connected
    @log.log
    def create_vip(self, vip, service):
        return True

    @am.is_connected
    @log.log
    def update_vip(self, old_vip, vip, service):
        return True

    @am.is_connected
    @log.log
    def delete_vip(self, vip, service):
        return True

    @am.is_connected
    @log.log
    def create_pool(self, pool, service):
        return True

    @am.is_connected
    @log.log
    def update_pool(self, old_pool, pool, service):
        return True

    @am.is_connected
    @log.log
    def delete_pool(self, pool, service):
        return True

    @am.is_connected
    @log.log
    def create_member(self, member, service):
        return True

    @am.is_connected
    @log.log
    def update_member(self, old_member, member, service):
        return True

    @am.is_connected
    @log.log
    def delete_member(self, member, service):
        return True

    @am.is_connected
    @log.log
    def create_pool_health_monitor(self, health_monitor, pool, service):
        self._assure_service(service)
        return True

    @am.is_connected
    @log.log
    def update_health_monitor(self, old_health_monitor,
                              health_monitor, pool, service):
        return True

    @am.is_connected
    @log.log
    def delete_pool_health_monitor(self, health_monitor, pool, service):
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

    def _delete_service(self, service):
        bigip = self._get_bigip()
        bigip.virtual_server.delete(name=service['vip']['id'],
                                    folder=service['pool']['tenant_id'])
        if service['vip']['id'] in self.__vips_to_traffic_group:
            tg = self.__vips_to_traffic_group[service['vip']['id']]
            self.__vips_on_traffic_groups[tg] = \
                              self.__vips_on_traffic_groups[tg] - 1
            del(self.__vips_to_traffic_groups[service['vip']['id']])
        bigip.pool.delete(name=service['pool']['id'],
                          folder=service['pool']['tenant_id'])
        for monitor in service['pool']['health_monitors']:
            bigip.monitor.delete(name=monitor['id'],
                                 folder=monitor['tenant_id'])

    def _assure_service(self, service):
        if 'id' in service['vip']:
            bigip = self._get_bigip()

            #
            # Provision Pool - Create/Update
            #

            if not bigip.pool.create(name=service['pool']['id'],
                              lb_method=service['pool']['lb_method'],
                              description=service['pool']['name'] + \
                              ':' + service['pool']['description'],
                              folder=service['pool']['tenant_id']):
                # make sure pool attributes are correct
                bigip.pool.set_lb_method(name=service['pool']['id'],
                                    lb_method=service['pool']['lb_method'])
                bigip.pool.set_description(name=service['pool']['id'],
                                    description=service['pool']['name'] + \
                                      ':' + service['pool']['description'])
            #
            # Provision Health Monitors - Create/Update
            #

            for monitor in service['health_monitors']:
                timeout = int(monitor['max_retries']) * int(monitor['timeout'])
                if not bigip.monitor.create(name=monitor['id'],
                                     mon_type=monitor['type'],
                                     interval=monitor['delay'],
                                     timeout=timeout,
                                     send_text=None,
                                     recv_text=None,
                                     folder=monitor['tenant_id']):
                    # make sure monitor attributes are correct
                    bigip.monitor.set_interval(name=monitor['id'],
                                     interval=monitor['delay'])
                    bigip.monitor.set_timeout(name=monitor['id'],
                                              timeout=timeout)

            existing_monitors = bigip.pool.get_monitors()
            for monitor in service['health_monitors']:
                if not bigip.pool.add_monitor(name=service['pool']['id'],
                                    monitor_name=monitor['id'],
                                    folder=service['pool']['tenant_id']):
                    existing_monitors.remove[monitor]
            # get rid of monitors no long in service definition
            for monitor in existing_monitors:
                bigip.monitor.delete(name=monitor['id'])

            #
            # Provision Members - Create/Update
            #

            # current members
            existing_members = bigip.pool.get_members(
                                    name=service['pool']['id'],
                                    folder=service['pool']['tenant_id'])
            # create any new members
            for member in service['members']:
                if not bigip.pool.add_member(name=service['pool']['id'],
                                      ip_address=member['address'],
                                      port=int(member['protocol_port']),
                                      folder=service['pool']['tenant_id']):
                    for existing_member in existing_members:
                        if member['address'] == \
                               existing_member['addr'] and \
                           member['protocol_port'] == \
                                existing_member['port']:
                            existing_members.remove(existing_member)
            # remove any members which are not long in the service
            for need_to_delete in existing_members:
                bigip.pool.remove_member(
                                     name=service['pool']['id'],
                                     ip_address=need_to_delete['addr'],
                                     port=int(need_to_delete['port']),
                                     folder=service['pool']['tenant_id']
                                    )
            # make sure member attributes are provisioned
            using_ratio = False
            for member in service['members']:
                if member['admin_state_up']:
                    bigip.pool.enable_member(name=member['id'],
                                    ip_address=member['address'],
                                    port=int(member['protocol_port']),
                                    folder=service['pool']['tenant_id'])
                else:
                    bigip.pool.disable_member(name=member['id'],
                                    ip_address=member['address'],
                                    port=int(member['protocol_port']),
                                    folder=service['pool']['tenant_id'])
                if member['weight'] > 0:
                    bigip.pool.set_member_ration(
                                    name=service['pool']['id'],
                                    ip_address=member['address'],
                                    port=int(member['protocol_port']),
                                    ratio=int(member['ratio']),
                                    folder=service['pool']['tenant_id']
                                   )
                    using_ratio = True
            # if members are using weights, change the LB to RATIO
            if using_ratio:
                bigip.pool.set_lb_method(
                                    name=service['pool']['id'],
                                    lb_method='RATIO',
                                    folder=service['pool']['tenant_id'])
            #
            # Provision Virtual Service - Create/Update
            #

            vlan_name = service['vip']['network']['id']
            if service['vip']['network']['shared']:
                vlan_name = '/Common/' + vlan_name

            tg = self._get_least_vips_traffic_group()

            if bigip.virtual_server.create(
                                name=service['vip']['id'],
                                ip_address=['vip']['address'],
                                mask='255.255.255.255',
                                port=int(service['vip']['protocol_port']),
                                protocol=service['vip']['protocol'],
                                vlan_name=vlan_name,
                                traffic_group=tg,
                                folder=service['pool']['tenant_id']
                               ):
                # created update driver traffic group mapping
                tg = bigip.virtual_server.get_traffic_group(
                                      name=service['vip']['ip'],
                                      folder=service['pool']['tenant_id'])
                self.__vips_to_traffic_group[service['vip']['ip']] = tg

            bigip.virtual_server.set_description(name=service['vip']['id'],
                                     description=service['vip']['name'] + \
                                     ':' + service['vip']['description'])

            bigip.virtual_server.set_pool(name=service['vip']['id'],
                                      pool_name=service['pool']['id'],
                                      folder=service['pool']['tenant_id'])

            if service['vip']['admin_state_up']:
                bigip.virtual_server.disable_virtual_server(
                                    name=service['vip']['id'],
                                    folder=service['pool']['tenant_id'])
            else:
                bigip.virtual_server.enable_virtual_server(
                                    name=service['vip']['id'],
                                    folder=service['pool']['tenant_id'])

            #TODO: fix session peristence
            if 'session_persistence' in service:
                type = service['vip']['session_persistence']['type']
                if type == 'HTTP_COOKIE':
                    pass
                elif type == 'APP_COOKIE':
                    pass
                elif type == 'SOURCE_IP':
                    pass

            #TODO: fix vitual service protocol
            if 'protocol' in service['vip']:
                protocol = service['vip']['protocol']
                if protocol == 'HTTP':
                    pass
                if protocol == 'HTTPS':
                    pass
                if protocol == 'TCP':
                    pass

            if service['vip']['connection_limit'] > 0:
                bigip.virtual_server.set_connection_limit(
                        name=service['vip']['id'],
                        connection_limit=int(
                                service['vip']['connection_limit']),
                        folder=service['pool']['tenant_id'])
            else:
                bigip.virtual_server.set_connection_limit(
                        name=service['vip']['id'],
                        connection_limit=0,
                        folder=service['pool']['tenant_id'])

    def _assure_service_networks(self, service):
        if 'id' in service['vip']:
            assured_networks = []
            self._assure_network(service['pool']['network'])
            assured_networks.append(service['pool']['network']['id'])
            # does the pool network need a self-ip or snat addresses?
            assured_networks.append(service['pool']['network']['id'])
            if 'id' in service['vip']['network']:
                if not service['vip']['network']['id'] in assured_networks:
                    self._assure_network(service['vip']['network'])
                    assured_networks.append(service['vip']['network']['id'])
                # all VIPs get a non-floating self IP on each device
                self._assure_local_selfip_snat(service['vip'], service)

            for member in service['members']:
                if not member['network']['id'] in assured_networks:
                    self._assure_network(member['network'])
                if 'id'in service['vip']['network'] and \
                 (not service['vip']['subnet']['id'] == member['subnet']['id']):
                    # each member gets a local self IP on each device
                    self._assure_local_selfip_snat(member, service)
                # if we are not using SNATS, attempt to become
                # the subnet's default gateway.
                if not self.conf.f5_snat_mode:
                    self._assure_floating_default_gateway(member, service)

    def _delete_service_networks(self, service):
        #bigip = self._get_bigip()
        # vips
        #vips_left = bigip.virtual_service.get_virtual_services(
        #                                  folder=service['pool']['tenant_id'])
        # clean up member network
        #nodes_left = bigip.pool.get_nodes(folder=service['pool']['tenant_id'])
        # any nodes on the member's subnet?
            
        # delete default gateway vs
            
        # self floating selfip
            
        # delete snats
            
        # delete non-floating selfips
            
        # delete network

        # clean up vip network
        
        # try to remove the non-floating selfips

        # clean up pool network
        pass

    def _assure_network(self, network):
        # setup all needed L2 network segments on all BigIPs
        for bigip in self.__bigips.values():
            if network['provider:network_type'] == 'vlan':
                if network['shared']:
                    network_folder = 'Common'
                else:
                    network_folder = network['tenant_id']

                interface = self.interface_mapping['default']
                tagged = True
                vlanid = 0

                if network['provider:physical_network'] in \
                                            self.interface_mapping:
                    interface = self.interface_mapping[
                              network['provider:physical_network']]
                    tagged = self.tagging_mapping[
                              network['provider:physical_network']]
                    if tagged:
                        vlanid = network['provider:segmentation_id']

                bigip.vlan.create(name=network['id'],
                                           vlanid=vlanid,
                                           interface=interface,
                                           folder=network_folder,
                                           description=network['name'])

            if network['provider:network_type'] == 'flat':
                if network['shared']:
                    network_folder = 'Common'
                else:
                    network_folder = network['id']
                interface = self.interface_mapping['default']
                vlanid = 0
                if network['provider:physical_network'] in \
                                            self.interface_mapping:
                    interface = self.interface_mapping[
                              network['provider:physical_network']]

                bigip.vlan.create(name=network['id'],
                                           vlanid=0,
                                           interface=interface,
                                           folder=network_folder,
                                           description=network['name'])

    def _assure_local_selfip_snat(self, service_object, service):

        # Setup non-floating Self IPs on all BigIPs
        vlan_name = service_object['network']['id']
        snat_pool_name = service_object['subnet']['tenant_id']
        # Where to put all these objects?
        network_folder = service_object['subnet']['tenant_id']
        if service_object['network']['shared']:
            network_folder = 'Common'

        # On each BIG-IP create the local Self IP for this subnet
        for bigip in self.__bigips.values():

            local_selfip_name = "local-" \
            + bigip.device.get_device_name() \
            + "-" + service_object['subnet']['id']

            ip_address = None
            if 'subnet_ports' in service_object:
                for port in service_object['subnet_ports']:
                    if port['name'] == local_selfip_name:
                        if port['fixed_ips'][0]['subnet_id'] == \
                           service_object['subnet']['id']:
                            ip_address = port['fixed_ips'][0]['ip_address']
                if not ip_address:
                    new_port = self.plugin_rpc.create_port_on_subnet(
                                subnet_id=service_object['subnet']['id'],
                                mac_address=None,
                                name=local_selfip_name,
                                fixed_address_count=1)
                    ip_address = new_port['fixed_ips'][0]['ip_address']
                netmask = netaddr.IPNetwork(
                               service_object['subnet']['cidr']).netmask

            bigip.selfip.create(name=local_selfip_name,
                                ip_address=ip_address,
                                netmask=netmask,
                                vlan_name=vlan_name,
                                floating=False,
                                folder=network_folder)

        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        if self.conf.f5_snat_addresses_per_subnet > 0:
            # failover mode dictates SNAT placement on traffic-groups
            if self.conf.f5_ha_type == 'standalone':
                # Create SNATs on traffic-group-local-only
                bigip = self._get_bigip()
                snat_name = 'snat-traffic-group-local-only-' + \
                 service_object['subnet']['id']
                snat_name = snat_name[0:60]
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    ip_address = None
                    index_snat_name = snat_name + "_" + str(i)
                    if 'subnet_ports' in service_object:
                        for port in service_object['subnet_ports']:
                            if port['name'] == index_snat_name:
                                if port['fixed_ips'][0]['subnet_id'] == \
                                   service_object['subnet']['id']:
                                    ip_address = \
                                       port['fixed_ips'][0]['ip_address']
                    if not ip_address:
                        new_port = self.plugin_rpc.create_port_on_subnet(
                            subnet_id=service_object['subnet']['id'],
                            mac_address=None,
                            name=index_snat_name,
                            fixed_address_count=1)
                        ip_address = new_port['fixed_ips'][0]['ip_address']

                    bigip.snat.create(
                     name=index_snat_name,
                     ip_address=ip_address,
                     traffic_group='/Common/traffic-group-local-only',
                     snat_pool_name=snat_pool_name,
                     folder=network_folder
                    )

            elif self.conf.f5_ha_type == 'ha':
                # Create SNATs on traffic-group-1
                bigip = self._get_bigip()
                snat_name = 'snat-traffic-group-1' + \
                 service_object['subnet']['id']
                snat_name = snat_name[0:60]
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    ip_address = None
                    index_snat_name = snat_name + "_" + str(i)
                    if 'subnet_ports' in service_object:
                        for port in service_object['subnet_ports']:
                            if port['name'] == index_snat_name:
                                if port['fixed_ips'][0]['subnet_id'] == \
                                   service_object['subnet']['id']:
                                    ip_address = \
                                       port['fixed_ips'][0]['ip_address']
                    if not ip_address:
                        new_port = self.plugin_rpc.create_port_on_subnet(
                            subnet_id=service_object['subnet']['id'],
                            mac_address=None,
                            name=index_snat_name,
                            fixed_address_count=1)
                        ip_address = new_port['fixed_ips'][0]['ip_address']

                    bigip.snat.create(
                     name=index_snat_name,
                     ip_address=ip_address,
                     traffic_group='/Common/traffic-group-1',
                     snat_pool_name=snat_pool_name,
                     folder=network_folder
                    )
            elif self.conf.f5_ha_type == 'scalen':
                # create SNATs on all provider defined traffic groups
                bigip = self._get_bigip()
                for traffic_group in self.__traffic_groups:
                    for i in range(self.conf.f5_snat_addresses_per_subnet):
                        snat_name = "snat-" + traffic_group + "-" + \
                         service_object['subnet']['id']
                        snat_name = snat_name[0:60]
                        ip_address = None
                        index_snat_name = snat_name + "_" + str(i)
                        if 'subnet_ports' in service_object:
                            for port in service_object['subnet_ports']:
                                if port['name'] == index_snat_name:
                                    fixed_ip = port['fixed_ips'][0]
                                    if fixed_ip['subnet_id'] == \
                                       service_object['subnet']['id']:
                                        ip_address = \
                                        port['fixed_ips'][0]['ip_address']
                        if not ip_address:
                            new_port = \
                              self.plugin_rpc.create_port_on_subnet(
                                subnet_id=service_object['subnet']['id'],
                                mac_address=None,
                                name=index_snat_name,
                                fixed_address_count=1
                              )
                            ip_address = \
                               new_port['fixed_ips'][0]['ip_address']
                        bigip.snat.create(
                         name=index_snat_name,
                         ip_address=ip_address,
                         traffic_group=traffic_group,
                         snat_pool_name=snat_pool_name,
                         folder=network_folder
                        )

    def _assure_floating_default_gateway(self, service_object, service):

        bigip = self._get_bigip()

        # Do we already have a port with the gateway_ip belonging
        # to this agent's host?
        need_port_for_gateway = True
        for port in service_object['subnet_ports']:
            for fixed_ips in port['fixed_ips']:
                if fixed_ips['ip_address'] == \
                    service_object['subnet']['gateway_ip']:
                    need_port_for_gateway = False

        # Create a name for the port and for the IP Forwarding Virtual Server
        # as well as the floating Self IP which will answer ARP for the members
        gw_name = "gw-" + service_object['subnet']['id']
        floating_selfip_name = "gw-" + service_object['subnet']['id']
        netmask = netaddr.IPNetwork(
                               service_object['subnet']['cidr']).netmask
        # There was not port on this agent's host, so get one from Neutron
        if need_port_for_gateway:
            try:
                self.plugin_rpc.create_port_on_subnet_with_specific_ip(
                            subnet_id=service_object['subnet']['id'],
                            mac_address=None,
                            name=gw_name,
                            ip_address=service_object['subnet']['gateway_ip'])
            except Exception as e:
                ermsg = 'Invalid default gateway for subnet %s:%s - %s.' \
                % (service_object['subnet']['id'],
                   service_object['subnet']['gateway_ip'],
                   e.message)
                ermsg += " SNAT will not function and load balancing"
                ermsg += " support will likely fail. Enable f5_snat_mode"
                ermsg += " and f5_source_monitor_from_member_subnet."
                LOG.error(_(ermsg))

        # Go ahead and setup a floating SelfIP with the subnet's
        # gateway_ip address on this agent's device service group
        vlan_name = service_object['network']['id']
        network_folder = service_object['subnet']['tenant_id']
        # Where to put all these objects?
        if service_object['network']['shared']:
            vlan_name = '/Common/' + vlan_name
            network_folder = 'Common'

        # Select a traffic group for the floating SelfIP
        tg = self._get_least_gw_traffic_group()
        bigip.selfip.create(
                            name=floating_selfip_name,
                            ip_address=service_object['subnet']['gateway_ip'],
                            netmask=netmask,
                            vlan_name=vlan_name,
                            floating=True,
                            traffic_group=tg,
                            folder=network_folder)

        # Get the actual traffic group if the Self IP already existed
        tg = bigip.self.get_traffic_group(name=floating_selfip_name,
                                folder=service_object['subnet']['tenant_id'])

        # Setup a wild card ip forwarding virtual service for this subnet
        bigip.virtual_server.create_ip_forwarder(self,
                            name=gw_name, ip_address='0.0.0.0',
                            mask='0.0.0.0',
                            vlan_name=vlan_name,
                            traffic_group=tg,
                            folder=network_folder)

        # Setup the IP forwarding virtual server to use the Self IPs
        # as the forwarding SNAT addresses
        bigip.virtual_server.set_snat_automap(name=gw_name,
                            folder=network_folder)

    def _get_least_vips_traffic_group(self):
        traffic_group = '/Common/traffic-group-1'
        lowest_count = 0
        for tg in self.__vips_on_traffic_groups:
            if self.__vips_on_traffic_groups[tg] <= lowest_count:
                traffic_group = self.__vips_on_traffic_groups[tg]
        return traffic_group

    def _get_least_gw_traffic_group(self):
        traffic_group = '/Common/traffic-group-1'
        lowest_count = 0
        for tg in self.__gw_on_traffic_groups:
            if self.__gw_on_traffic_groups[tg] <= lowest_count:
                traffic_group = self.__gw_on_traffic_groups[tg]
        return traffic_group

    def _get_bigip(self):
        hostnames = sorted(self.__bigips)
        for i in range(len(hostnames)):
            try:
                bigip = self.__bigips[hostnames[i]]
                bigip.system.sys_session.set_active_folder('/Common')
                return bigip
            except urllib2.URLError:
                pass
        else:
            raise urllib2.URLError('cannot communicate to any bigips')

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

                self.hostnames = sorted(
                                    self.conf.icontrol_hostname.split(','))

                self.agent_id = self.hostnames[0]

                self.username = self.conf.icontrol_username
                self.password = self.conf.icontrol_password

                LOG.debug(_('opening iControl connections to %s @ %s' % (
                                                            self.username,
                                                            self.hostnames[0])
                            ))

                # connect to inital device:
                first_bigip = bigip.BigIP(self.hostnames[0],
                                        self.username,
                                        self.password,
                                        5,
                                        self.conf.use_namespaces)
                self.__bigips[self.hostnames[0]] = first_bigip

                # if there was only one address supplied and
                # this is not a standalone device, get the
                # devices trusted by this device.
                if len(self.hostnames) < 2:
                    if not first_bigip.cluster.get_sync_status() == \
                                                              'Standalone':
                        this_devicename = \
                             self.device.device.mgmt_dev.get_local_device()
                        devices = first_bigip.device.get_all_device_names()
                        devices.remove[this_devicename]
                        self.hostnames = self.hostnames + \
                    first_bigip.device.mgmt_dev.get_management_address(devices)
                    else:
                        LOG.debug(_(
                            'only one host connected and it is Standalone.'))
                # populate traffic groups
                first_bigip.system.set_folder(folder='/Common')
                self.__traffic_groups = first_bigip.cluster.mgmt_tg.get_list()
                if '/Common/traffic-group-local-only' in self.__traffic_groups:
                    self.__traffic_groups.remove(
                                    '/Common/traffic-group-local-only')
                if '/Common/traffic-group-1' in self.__traffic_groups:
                    self.__traffic_groups.remove('/Common/traffic-group-1')
                for tg in self.__traffic_groups:
                    self.__gw_on_traffic_groups[tg] = 0
                    self.__vips_on_traffic_groups[tg] = 0

                # connect to the rest of the devices
                for host in self.hostnames[1:]:
                    hostbigip = bigip.BigIP(host,
                                            self.username,
                                            self.password,
                                            5,
                                            self.conf.use_namespaces)
                    self.__bigips[host] = hostbigip

                # validate device versions
                for host in self.__bigips:
                    hostbigip = self.__bigips[host]
                    major_version = hostbigip.system.get_major_version()
                    if major_version < f5const.MIN_TMOS_MAJOR_VERSION:
                        raise f5ex.MajorVersionValidateFailed(
                                'device %s must be at least TMOS %s.%s'
                                % (host,
                                   f5const.MIN_TMOS_MAJOR_VERSION,
                                   f5const.MIN_TMOS_MINOR_VERSION))
                    minor_version = hostbigip.system.get_minor_version()
                    if minor_version < f5const.MIN_TMOS_MINOR_VERSION:
                        raise f5ex.MinorVersionValidateFailed(
                                'device %s must be at least TMOS %s.%s'
                                % (host,
                                   f5const.MIN_TMOS_MAJOR_VERSION,
                                   f5const.MIN_TMOS_MINOR_VERSION))

                    self.__device_to_bigip[
                         hostbigip.device.get_device_name()] = hostbigip

                    LOG.debug(_('connected to iControl %s @ %s ver %s.%s'
                                % (self.username, host,
                                   major_version, minor_version)))

                self.connected = True

        except Exception as e:
            LOG.error(_('Could not communicate with all iControl devices: %s'
                           % e.message))

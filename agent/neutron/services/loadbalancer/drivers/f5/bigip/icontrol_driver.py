from oslo.config import cfg
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants as plugin_const
from neutron.common.exceptions import InvalidConfigurationOption
from neutron.services.loadbalancer import constants as lb_const
from neutron.services.loadbalancer.drivers.f5.bigip \
    import agent_manager as am
from f5.bigip import bigip as f5_bigip
from f5.common import constants as f5const
from f5.bigip import exceptions as f5ex
from f5.bigip import bigip_interfaces

from eventlet import greenthread

import uuid
import urllib2
import netaddr
import datetime
from time import time
import logging as std_logging

LOG = logging.getLogger(__name__)
NS_PREFIX = 'qlbaas-'
APP_COOKIE_RULE_PREFIX = 'app_cookie_'
RPS_THROTTLE_RULE_PREFIX = 'rps_throttle_'

__VERSION__ = '0.1.1'

OPTS = [
    cfg.StrOpt(
        'icontrol_hostname',
        help=_('The hostname (name or IP address) to use for iControl access'),
    ),
    cfg.StrOpt(
        'icontrol_username',
        default='admin',
        help=_('The username to use for iControl access'),
    ),
    cfg.StrOpt(
        'icontrol_password',
        default='admin',
        secret=True,
        help=_('The password to use for iControl access'),
    ),
    cfg.IntOpt(
        'icontrol_connection_retry_interval',
        default=10,
        help=_('How many seconds to wait between retry connection attempts'),
    ),
    cfg.StrOpt(
        'sync_mode',
        default='autosync',
        help=_('The sync mechanism: autosync or replication'),
    ),
]

def request_index(request_queue, request_id):
    for request in request_queue:
        if request[0] == request_id:
            return request_queue.index(request)

def serialized(method_name):
    def real_serialized(method):
        """Decorator to serialize calls to configure via iControl"""
        def wrapper(*args, **kwargs):
            # args[0] must be an instance of iControlDriver
            service_queue = args[0].service_queue
            my_request_id = uuid.uuid4()

            service = None
            if len(args) > 0:
                last_arg = args[-1]
                if isinstance(last_arg, dict) and ('pool' in last_arg):
                    service = last_arg
            if 'service' in kwargs:
                service = kwargs['service']

            # Consolidate create_member requests for the same pool.
            #
            # NOTE: The following block of code alters the state of
            # a queue that other greenthreads are waiting behind.
            # This code assumes it will not be preempted by another
            # greenthread while running. It does not do I/O or call any
            # other monkey-patched code which might cause a context switch.
            # To avoid race conditions, DO NOT add logging to this code
            # block.
            num_requests = len(service_queue)
            if num_requests > 1 and method_name == 'create_member':
                cur_pool_id = service['pool']['id']
                cur_index = num_requests - 1
                # do not attempt to replace the first entry (index 0)
                # because it may already be in process.
                while cur_index > 0:
                    (check_request, check_method, check_service) = \
                        service_queue[cur_index]
                    if check_service['pool']['id'] != cur_pool_id:
                        cur_index -= 1
                        continue
                    if check_method != 'create_member':
                        break
                    # move this request up in the queue and return
                    # so that existing thread can handle it
                    service_queue[cur_index] = \
                        (check_request, check_method, service)
                    return
            # End of code block which assumes no preemption.

            req = (my_request_id, method_name, service)
            service_queue.append(req)
            reqs_ahead_of_us = request_index(service_queue, my_request_id)
            while reqs_ahead_of_us != 0:
                if reqs_ahead_of_us == 1:
                    # it is almost our turn. get ready
                    waitsecs = .01
                else:
                    waitsecs = reqs_ahead_of_us * .5
                if waitsecs > .01:
                    LOG.debug('%s request %s is blocking'
                          ' for %.2f secs - queue depth: %d'
                          % (str(method_name), my_request_id,
                             waitsecs, len(service_queue)))
                greenthread.sleep(waitsecs)
                reqs_ahead_of_us = request_index(service_queue, my_request_id)
            else:
                LOG.debug('%s request %s is running with queue depth: %d'
                          % (str(method_name), my_request_id,
                             len(service_queue)))
            try:
                start_time = time()
                result = method(*args, **kwargs)
                LOG.debug('%s request %s took %.5f secs'
                          % (str(method_name), my_request_id,
                             time() - start_time))
            except:
                LOG.error('%s request %s FAILED'
                          % (str(method_name), my_request_id))
                raise
            finally:
                service_queue.pop(0)
            return result
        return wrapper
    return real_serialized


def check_monitor_delete(service):
    if service['pool']['status'] == plugin_const.PENDING_DELETE:
        # Everything needs to be go with the pool, so overwrite
        # service state to appropriately remove all elements
        service['vip']['status'] = plugin_const.PENDING_DELETE
        for member in service['members']:
            member['status'] = plugin_const.PENDING_DELETE
        for monitor in service['pool']['health_monitors_status']:
            monitor['status'] = plugin_const.PENDING_DELETE


class iControlDriver(object):

    # containers
    __bigips = {}
    __traffic_groups = []

    # mappings
    __vips_to_traffic_group = {}
    __gw_to_traffic_group = {}

    # scheduling counts
    __vips_on_traffic_groups = {}
    __gw_on_traffic_groups = {}

    __service_locks = {}

    def __init__(self, conf):
        self.conf = conf
        self.conf.register_opts(OPTS)
        self.plugin_rpc = None
        self.connected = False
        self.service_queue = []

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


    @serialized('sync')
    @am.is_connected
    def sync(self, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('create_vip')
    @am.is_connected
    def create_vip(self, vip, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('update_vip')
    @am.is_connected
    def update_vip(self, old_vip, vip, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('delete_vip')
    @am.is_connected
    def delete_vip(self, vip, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('create_pool')
    @am.is_connected
    def create_pool(self, pool, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('update_pool')
    @am.is_connected
    def update_pool(self, old_pool, pool, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('delete_pool')
    @am.is_connected
    def delete_pool(self, pool, service):
        self._assure_service(service)

    @serialized('create_member')
    @am.is_connected
    def create_member(self, member, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('update_member')
    @am.is_connected
    def update_member(self, old_member, member, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('delete_member')
    @am.is_connected
    def delete_member(self, member, service):
        self._assure_service_networks(service)
        self._assure_service(service)

    @serialized('create_pool_health_monitor')
    @am.is_connected
    def create_pool_health_monitor(self, health_monitor, pool, service):
        self._assure_service(service)
        return True

    @serialized('update_health_monitor')
    @am.is_connected
    def update_health_monitor(self, old_health_monitor,
                              health_monitor, pool, service):
        self._assure_service(service)
        return True

    @serialized('delete_pool_health_monitor')
    @am.is_connected
    def delete_pool_health_monitor(self, health_monitor, pool, service):
        # Two behaviors of the plugin dictate our behavior here.
        # 1. When a plug-in deletes a monitor that is not being
        # used by a pool, it does not notify the drivers. Therefore,
        # we need to aggresively remove monitors that are not in use.
        # 2. When a plug-in deletes a monitor which is being
        # used by one or more pools, it calls delete_pool_health_monitor
        # against the driver that owns each pool, but it does not
        # set status to PENDING_DELETE in the health_monitors_status
        # list for the pool monitor. This may be a bug or perhaps this
        # is intended to be a synchronous process.
        #
        # In contrast, when a pool monitor association is deleted, the
        # PENDING DELETE status is set properly, so this code will
        # run unnecessarily in that case.
        for status in service['pool']['health_monitors_status']:
            if status['monitor_id'] == health_monitor['id']:
                # Signal to our own code that we should delete the
                # pool health monitor. The plugin should do this.
                status['status'] = plugin_const.PENDING_DELETE

        self._assure_service(service)
        return True

    @serialized('get_stats')
    @am.is_connected
    def get_stats(self, service):
        # use pool stats because the pool_id is the
        # the service definition... not the vip
        #
        stats = {}

        bigip = self._get_bigip()

        # It appears that stats are collected for pools in a pending delete
        # state which means that if those messages are queued (or delayed)
        # it can result in the process of a stats request after the pool
        # and tenant are long gone
        if not bigip.system.folder_exists(
                '/uuid_' + service['pool']['tenant_id']):
            return None

        pool = service['pool']
        bigip_stats = bigip.pool.get_statistics(name=pool['id'],
                                                folder=pool['tenant_id'])
        if 'STATISTIC_SERVER_SIDE_BYTES_IN' in bigip_stats:
            stats[lb_const.STATS_IN_BYTES] = \
                bigip_stats['STATISTIC_SERVER_SIDE_BYTES_IN']
            stats[lb_const.STATS_OUT_BYTES] = \
                bigip_stats['STATISTIC_SERVER_SIDE_BYTES_OUT']
            stats[lb_const.STATS_ACTIVE_CONNECTIONS] = \
                bigip_stats['STATISTIC_SERVER_SIDE_CURRENT_CONNECTIONS']
            stats[lb_const.STATS_TOTAL_CONNECTIONS] = \
                bigip_stats['STATISTIC_SERVER_SIDE_TOTAL_CONNECTIONS']

            # need to get members for this pool and update their status
            get_mon_status = bigip.pool.get_members_monitor_status
            states = get_mon_status(name=pool['id'],
                                    folder=pool['tenant_id'])
            # format is data = {'members': { uuid:{'status':'state1'},
            #                             uuid:{'status':'state2'}} }
            members = {'members': {}}
            if hasattr(service, 'members'):
                for member in service['members']:
                    for state in states:
                        if state == 'MONITOR_STATUS_UP':
                            members['members'][member['id']] = 'ACTIVE'
                        else:
                            members['members'][member['id']] = 'DOWN'
            stats['members'] = members

            return stats
        else:
            return None

    def remove_orphans(self, known_pool_ids):
        raise NotImplementedError()

    def non_connected(self):
        now = datetime.datetime.now()
        if (now - self.__last_connect_attempt).total_seconds() > \
                self.conf.icontrol_connection_retry_interval:
            self.connected = False
            self._init_connection()

    # A context used for storing information used to sync
    # the service request with the current configuration
    class AssureServiceContext:
        def __init__(self):
            self.device_group = None
            # keep track of which subnets we should check to delete
            # for a deleted vip or member
            self.check_for_delete_subnets = {}

            # If we add an IP to a subnet we must not delete the subnet
            self.do_not_delete_subnets = []

    class SubnetInfo:
        def __init__(self, network=None, subnet=None, subnet_ports=None):
            self.network = network
            self.subnet = subnet
            self.subnet_ports = subnet_ports

    def _assure_service(self, service):
        bigip = self._get_bigip()
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        ctxs = {}
        for prep_bigip in bigips:
            ctxs[prep_bigip.device_name] = self.AssureServiceContext()

        check_monitor_delete(service)

        start_time = time()
        self.assure_pool_create(service['pool'], bigip)
        LOG.debug("    assure_pool_create took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.assure_pool_monitors(service, bigip)
        LOG.debug("    assure_pool_monitors took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.assure_members(service, bigip, ctxs)
        LOG.debug("    assure_members took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.assure_vip(service, bigip, ctxs)
        LOG.debug("    assure_vip took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.assure_pool_delete(service, bigip)
        LOG.debug("    assure_pool_delete took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.assure_delete_networks(service, bigip, ctxs)
        LOG.debug("    assure_delete_networks took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.assure_tenant_cleanup(service, bigip, ctxs)
        LOG.debug("    assure_tenant_cleanup took %.5f secs" %
                  (time() - start_time))

        start_time = time()
        self.sync_if_clustered(bigip)
        LOG.debug("    sync took %.5f secs" % (time() - start_time))

    #
    # Provision Pool - Create/Update
    #
    def assure_pool_create(self, pool, bigip):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            self._assure_pool_create(pool, bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_pool_create(self, pool, bigip, on_last_bigip):
        if not pool['status'] == plugin_const.PENDING_DELETE:
            desc = pool['name'] + ':' + pool['description']
            if not bigip.pool.create(name=pool['id'],
                                     lb_method=pool['lb_method'],
                                     description=desc,
                                     folder=pool['tenant_id']):

                if pool['status'] == plugin_const.PENDING_UPDATE:
                    # make sure pool attributes are correct
                    bigip.pool.set_lb_method(name=pool['id'],
                                             lb_method=pool['lb_method'])
                    bigip.pool.set_description(name=pool['id'],
                                               description=desc)
                    if on_last_bigip:
                        update_pool = self.plugin_rpc.update_pool_status
                        update_pool(pool['id'],
                                    status=plugin_const.ACTIVE,
                                    status_description='pool updated')
            else:
                if on_last_bigip:
                    update_pool = self.plugin_rpc.update_pool_status
                    update_pool(pool['id'],
                                status=plugin_const.ACTIVE,
                                status_description='pool created')

    #
    # Provision Health Monitors - Create/Update
    #
    def assure_pool_monitors(self, service, bigip):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            self._assure_pool_monitors(service, bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_pool_monitors(self, service, bigip, on_last_bigip):
        pool = service['pool']
        # Current monitors on the pool according to BigIP
        existing_monitors = bigip.pool.get_monitors(name=pool['id'],
                                                    folder=pool['tenant_id'])
        #LOG.debug(_("Pool: %s before assurance has monitors: %s"
        #            % (pool['id'], existing_monitors)))

        health_monitors_status = {}
        for monitor in pool['health_monitors_status']:
            health_monitors_status[monitor['monitor_id']] = \
                monitor['status']

        # Current monitor associations according to Neutron
        for monitor in service['health_monitors']:
            found_existing_monitor = monitor['id'] in existing_monitors
            if monitor['id'] in health_monitors_status and \
                health_monitors_status[monitor['id']] == \
                    plugin_const.PENDING_DELETE:
                bigip.pool.remove_monitor(name=pool['id'],
                                          monitor_name=monitor['id'],
                                          folder=pool['tenant_id'])
                if on_last_bigip:
                    self.plugin_rpc.health_monitor_destroyed(
                        health_monitor_id=monitor['id'],
                        pool_id=pool['id'])
                # not sure if the monitor might be in use
                try:
                    bigip.monitor.delete(name=monitor['id'],
                                         folder=pool['tenant_id'])
                except:
                    pass
            else:
                update_status = False
                if not found_existing_monitor:
                    timeout = int(monitor['max_retries']) * \
                              int(monitor['timeout'])
                    bigip.monitor.create(name=monitor['id'],
                                         mon_type=monitor['type'],
                                         interval=monitor['delay'],
                                         timeout=timeout,
                                         send_text=None,
                                         recv_text=None,
                                         folder=monitor['tenant_id'])
                    self.update_monitor(bigip, monitor, set_times=False)
                    update_status = True
                else:
                    if health_monitors_status[monitor['id']] == \
                            plugin_const.PENDING_UPDATE:
                        self.update_monitor(bigip, monitor)
                        update_status = True

                if not found_existing_monitor:
                    bigip.pool.add_monitor(name=pool['id'],
                                       monitor_name=monitor['id'],
                                       folder=pool['tenant_id'])
                    update_status = True

                if update_status and on_last_bigip:
                    self.plugin_rpc.update_health_monitor_status(
                                    pool_id=pool['id'],
                                    health_monitor_id=monitor['id'],
                                    status=plugin_const.ACTIVE,
                                    status_description='monitor active')

            if found_existing_monitor:
                existing_monitors.remove(monitor['id'])

        LOG.debug(_("Pool: %s removing monitors %s"
                    % (pool['id'], existing_monitors)))
        # get rid of monitors no longer in service definition
        for monitor in existing_monitors:
            bigip.monitor.delete(name=monitor,
                                 folder=pool['tenant_id'])

    def update_monitor(self, bigip, monitor, set_times=True):
        if set_times:
            timeout = int(monitor['max_retries']) * \
                      int(monitor['timeout'])
            # make sure monitor attributes are correct
            bigip.monitor.set_interval(name=monitor['id'],
                               interval=monitor['delay'],
                               folder=monitor['tenant_id'])
            bigip.monitor.set_timeout(name=monitor['id'],
                              timeout=timeout,
                              folder=monitor['tenant_id'])

        if monitor['type'] == 'HTTP' or monitor['type'] == 'HTTPS':
            if 'url_path' in monitor:
                send_text = "GET " + monitor['url_path'] + \
                                                " HTTP/1.0\\r\\n\\r\\n"
            else:
                send_text = "GET / HTTP/1.0\\r\\n\\r\\n"

            if 'expected_codes' in monitor:
                try:
                    if monitor['expected_codes'].find(",") > 0:
                        status_codes = \
                            monitor['expected_codes'].split(',')
                        recv_text = "HTTP/1\.(0|1) ("
                        for status in status_codes:
                            int(status)
                            recv_text += status + "|"
                        recv_text = recv_text[:-1]
                        recv_text += ")"
                    elif monitor['expected_codes'].find("-") > 0:
                        status_range = \
                            monitor['expected_codes'].split('-')
                        start_range = status_range[0]
                        int(start_range)
                        stop_range = status_range[1]
                        int(stop_range)
                        recv_text = \
                            "HTTP/1\.(0|1) [" + \
                            start_range + "-" + \
                            stop_range + "]"
                    else:
                        int(monitor['expected_codes'])
                        recv_text = "HTTP/1\.(0|1) " + \
                                    monitor['expected_codes']
                except:
                    LOG.error(_(
                        "invalid monitor expected_codes %s,"
                        " setting to 200"
                        % monitor['expected_codes']))
                    recv_text = "HTTP/1\.(0|1) 200"
            else:
                recv_text = "HTTP/1\.(0|1) 200"

            LOG.debug('setting monitor send: %s, receive: %s'
                      % (send_text, recv_text))

            bigip.monitor.set_send_string(name=monitor['id'],
                                          send_text=send_text,
                                          folder=monitor['tenant_id'])
            bigip.monitor.set_recv_string(name=monitor['id'],
                                          recv_text=recv_text,
                                          folder=monitor['tenant_id'])
    #
    # Provision Members - Create/Update
    #
    def assure_members(self, service, bigip, ctxs):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            ctx = ctxs[bigip.device_name]
            self._assure_members(service, bigip, ctx, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_members(self, service, bigip, ctx, on_last_bigip):
        start_time = time()
        # Current members on the BigIP
        pool = service['pool']
        existing_members = bigip.pool.get_members(
                                name=pool['id'],
                                folder=pool['tenant_id'])
        LOG.debug("        assure_members get members took %.5f secs" %
                  (time() - start_time))
        #LOG.debug(_("Pool: %s before assurance has membership: %s"
        #            % (pool['id'], existing_members)))

        # Flag if we need to change the pool's LB method to
        # include weighting by the ratio attribute
        using_ratio = False
        # Members according to Neutron
        for member in service['members']:
            member_start_time = time()
            network = member['network']
            subnet = member['subnet']
            #LOG.debug(_("Pool %s assuring member %s:%d - status %s"
            #            % (pool['id'],
            #               member['address'],
            #               member['protocol_port'],
            #               member['status'])
            #            ))

            ip_address = member['address']
            if network['shared']:
                ip_address = ip_address + '%0'

            found_existing_member = None
            for existing_member in existing_members:
                if member['address'] == existing_member['addr'] and \
                        member['protocol_port'] == existing_member['port']:
                    found_existing_member = existing_member
                    break

            # Delete those pending delete
            if member['status'] == plugin_const.PENDING_DELETE:
                bigip.pool.remove_member(name=pool['id'],
                                  ip_address=ip_address,
                                  port=int(member['protocol_port']),
                                  folder=pool['tenant_id'])
                # avoids race condition:
                # deletion of pool member objects must sync before we
                # remove the selfip from the peer bigips.
                self.sync_if_clustered(bigip)
                try:
                    if on_last_bigip:
                        self.plugin_rpc.member_destroyed(member['id'])
                except Exception as exc:
                    LOG.error(_("Plugin delete member %s error: %s"
                                % (member['id'], exc.message)
                                ))
                if subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.check_for_delete_subnets[subnet['id']] = \
                                                self.SubnetInfo(
                                                    network,
                                                    subnet,
                                                    member['subnet_ports'])
            else:
                just_added = False
                if not found_existing_member:
                    start_time = time()
                    result = bigip.pool.add_member(
                                      name=pool['id'],
                                      ip_address=ip_address,
                                      port=int(member['protocol_port']),
                                      folder=pool['tenant_id'],
                                      no_checks=True)
                    just_added = True
                    LOG.debug("            bigip.pool.add_member took %.5f" %
                              (time() - start_time))
                    if result:
                        #LOG.debug(_("Pool: %s added member: %s:%d"
                        #% (pool['id'],
                        #   member['address'],
                        #   member['protocol_port'])))
                        if on_last_bigip:
                            rpc = self.plugin_rpc
                            start_time = time()
                            rpc.update_member_status(
                                member['id'],
                                status=plugin_const.ACTIVE,
                                status_description='member created')
                            LOG.debug("            update_member_status"
                                      " took %.5f secs" %
                                      (time() - start_time))
                if just_added or \
                        member['status'] == plugin_const.PENDING_UPDATE:
                    # Is it enabled or disabled?
                    # no_checks because we add the member above if not found
                    start_time = time()
                    if member['admin_state_up']:
                        bigip.pool.enable_member(name=pool['id'],
                                    ip_address=ip_address,
                                    port=int(member['protocol_port']),
                                    folder=pool['tenant_id'],
                                    no_checks=True)
                    else:
                        bigip.pool.disable_member(name=pool['id'],
                                    ip_address=ip_address,
                                    port=int(member['protocol_port']),
                                    folder=pool['tenant_id'],
                                    no_checks=True)
                    LOG.debug("            member enable/disable"
                              " took %.5f secs" %
                              (time() - start_time))
                    # Do we have weights for ratios?
                    if member['weight'] > 0:
                        start_time = time()
                        if not (just_added and int(member['weight'] == 1)):
                            bigip.pool.set_member_ratio(
                                    name=pool['id'],
                                    ip_address=ip_address,
                                    port=int(member['protocol_port']),
                                    ratio=int(member['weight']),
                                    folder=pool['tenant_id'],
                                    no_checks=True)
                        if time() - start_time > .0001:
                            LOG.debug("            member set ratio"
                                      " took %.5f secs" %
                                      (time() - start_time))
                        using_ratio = True

                    if on_last_bigip:
                        if member['status'] == plugin_const.PENDING_UPDATE:
                            start_time = time()
                            self.plugin_rpc.update_member_status(
                                    member['id'],
                                    status=plugin_const.ACTIVE,
                                    status_description='member updated')
                            LOG.debug("            update_member_status"
                                      " took %.5f secs" %
                                      (time() - start_time))
                if subnet['id'] in ctx.check_for_delete_subnets:
                    del(ctx.check_for_delete_subnets[subnet['id']])
                if subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.do_not_delete_subnets.append(subnet['id'])

            # Remove member from the list of members big-ip needs to remove
            if found_existing_member:
                existing_members.remove(found_existing_member)
            #LOG.debug(_("Pool: %s assured member: %s:%d"
            #        % (pool['id'],
            #           member['address'],
            #           member['protocol_port'])))
            if time() - member_start_time > .001:
                LOG.debug("        assuring member %s took %.5f secs" %
                          (member['address'], time() - member_start_time))
                   

        #LOG.debug(_("Pool: %s removing members %s"
        #            % (pool['id'], existing_members)))
        # remove any members which are no longer in the service
        for need_to_delete in existing_members:
            bigip.pool.remove_member(
                                 name=pool['id'],
                                 ip_address=need_to_delete['addr'],
                                 port=int(need_to_delete['port']),
                                 folder=pool['tenant_id'])
        # if members are using weights, change the LB to RATIO
        start_time = time()
        if using_ratio:
            #LOG.debug(_("Pool: %s changing to ratio based lb"
            #        % pool['id']))
            bigip.pool.set_lb_method(
                                name=pool['id'],
                                lb_method='RATIO',
                                folder=pool['tenant_id'])

            # This is probably not required.
            #if on_last_bigip:
            #    self.plugin_rpc.update_pool_status(
            #                pool['id'],
            #                status=plugin_const.ACTIVE,
            #                status_description='pool now using ratio lb')
        if time() - start_time > .001:
            LOG.debug("        assure_members setting pool lb method" +
                      " took %.5f secs" % (time() - start_time))

    def assure_vip(self, service, bigip, ctxs):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            ctx = ctxs[bigip.device_name]
            self._assure_vip(service, bigip, ctx, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_vip(self, service, bigip, ctx, on_last_bigip):
        vip = service['vip']
        pool = service['pool']
        bigip_vs = bigip.virtual_server
        if 'id' in vip:
            network = vip['network']
            subnet = vip['subnet']
            subnet_ports = vip['subnet_ports']
            #
            # Provision Virtual Service - Create/Update
            #
            vlan_name = self._get_vlan_name(network)
            ip_address = vip['address']
            if network['shared']:
                vlan_name = '/Common/' + vlan_name
                ip_address = ip_address + "%0"
            if vip['status'] == plugin_const.PENDING_DELETE:
                LOG.debug(_('Vip: deleting VIP %s' % vip['id']))
                bigip_vs.remove_and_delete_persist_profile(
                                        name=vip['id'],
                                        folder=vip['tenant_id'])
                bigip_vs.delete(name=vip['id'], folder=vip['tenant_id'])

                bigip.rule.delete(name=RPS_THROTTLE_RULE_PREFIX +
                                  vip['id'],
                                  folder=vip['tenant_id'])
                # avoids race condition:
                # deletion of vip address must sync before we
                # remove the selfip from the peer bigips.
                self.sync_if_clustered(bigip)

                if vip['id'] in self.__vips_to_traffic_group:
                    vip_tg = self.__vips_to_traffic_group[vip['id']]
                    self.__vips_on_traffic_groups[vip_tg] = \
                                  self.__vips_on_traffic_groups[vip_tg] - 1
                    del(self.__vips_to_traffic_group[vip['id']])
                if subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.check_for_delete_subnets[subnet['id']] = \
                                                self.SubnetInfo(network,
                                                                subnet,
                                                                subnet_ports)
                try:
                    if on_last_bigip:
                        self.plugin_rpc.vip_destroyed(vip['id'])
                except Exception as exc:
                    LOG.error(_("Plugin delete vip %s error: %s"
                                % (vip['id'], exc.message)
                                ))
            else:
                vip_tg = self._get_least_vips_traffic_group()

                snat_pool_name = None
                if self.conf.f5_snat_mode and \
                   self.conf.f5_snat_addresses_per_subnet > 0:
                    snat_pool_name = bigip_interfaces.decorate_name(
                                    pool['tenant_id'],
                                    pool['tenant_id'])

                # This is where you could decide to use a fastl4
                # or a standard virtual server.  The problem
                # is making sure that if someone updates the
                # vip protocol or a session persistence that
                # required you change virtual service types
                # would have to make sure a virtual of the
                # wrong type does not already exist or else
                # delete it first. That would cause a service
                # disruption. It would be better if the
                # specification did not allow you to update
                # L7 attributes if you already created a
                # L4 service.  You should have to delete the
                # vip and then create a new one.  That way
                # the end user expects the service outage.

                #virtual_type = 'fastl4'
                #if 'protocol' in vip:
                #    if vip['protocol'] == 'HTTP' or \
                #       vip['protocol'] == 'HTTPS':
                #        virtual_type = 'standard'
                #if 'session_persistence' in vip:
                #    if vip['session_persistence'] == \
                #       'APP_COOKIE':
                #        virtual_type = 'standard'

                # Hard code to standard until we decide if we
                # want to handle the check/delete before create
                # and document the service outage associated
                # with deleting a virtual service. We'll leave
                # the steering logic for create in place.
                # Be aware the check/delete before create
                # is not in the logic below because it means
                # another set of interactions with the device
                # we don't need unless we decided to handle
                # shifting from L4 to L7 or from L7 to L4

                virtual_type = 'standard'

                if virtual_type == 'standard':
                    if bigip_vs.create(name=vip['id'],
                                       ip_address=ip_address,
                                       mask='255.255.255.255',
                                       port=int(vip['protocol_port']),
                                       protocol=vip['protocol'],
                                       vlan_name=vlan_name,
                                       traffic_group=vip_tg,
                                       use_snat=self.conf.f5_snat_mode,
                                       snat_pool=snat_pool_name,
                                       folder=pool['tenant_id']):
                        # created update driver traffic group mapping
                        vip_tg = bigip_vs.get_traffic_group(
                                        name=vip['ip'],
                                        folder=pool['tenant_id'])
                        self.__vips_to_traffic_group[vip['ip']] = vip_tg
                        if on_last_bigip:
                            self.plugin_rpc.update_vip_status(
                                            vip['id'],
                                            status=plugin_const.ACTIVE,
                                            status_description='vip created')
                else:
                    if bigip_vs.create_fastl4(
                                    name=vip['id'],
                                    ip_address=ip_address,
                                    mask='255.255.255.255',
                                    port=int(vip['protocol_port']),
                                    protocol=vip['protocol'],
                                    vlan_name=vlan_name,
                                    traffic_group=vip_tg,
                                    use_snat=self.conf.f5_snat_mode,
                                    snat_pool=snat_pool_name,
                                    folder=pool['tenant_id']):
                        # created update driver traffic group mapping
                        vip_tg = bigip_vs.get_traffic_group(
                                        name=vip['ip'],
                                        folder=pool['tenant_id'])
                        self.__vips_to_traffic_group[vip['ip']] = vip_tg
                        if on_last_bigip:
                            self.plugin_rpc.update_vip_status(
                                            vip['id'],
                                            status=plugin_const.ACTIVE,
                                            status_description='vip created')

                if vip['status'] == plugin_const.PENDING_CREATE or \
                   vip['status'] == plugin_const.PENDING_UPDATE:

                    desc = vip['name'] + ':' + vip['description']
                    bigip_vs.set_description(name=vip['id'],
                                             description=desc)

                    bigip_vs.set_pool(name=vip['id'],
                                      pool_name=pool['id'],
                                      folder=pool['tenant_id'])
                    if vip['admin_state_up']:
                        bigip_vs.enable_virtual_server(
                                    name=vip['id'],
                                    folder=pool['tenant_id'])
                    else:
                        bigip_vs.disable_virtual_server(
                                    name=vip['id'],
                                    folder=pool['tenant_id'])

                    if 'session_persistence' in vip:
                        # branch on persistence type
                        persistence_type = \
                               vip['session_persistence']['type']

                        if persistence_type == 'SOURCE_IP':
                            # add source_addr persistence profile
                            LOG.debug('adding source_addr primary persistence')
                            bigip_vs.set_persist_profile(
                                name=vip['id'],
                                profile_name='/Common/source_addr',
                                folder=vip['tenant_id'])
                        elif persistence_type == 'HTTP_COOKIE':
                            # HTTP cookie persistence requires an HTTP profile
                            LOG.debug('adding http profile and' +
                                      ' primary cookie persistence')
                            bigip_vs.add_profile(
                                name=vip['id'],
                                profile_name='/Common/http',
                                folder=vip['tenant_id'])
                            # add standard cookie persistence profile
                            bigip_vs.set_persist_profile(
                                name=vip['id'],
                                profile_name='/Common/cookie',
                                folder=vip['tenant_id'])
                            if pool['lb_method'] == 'SOURCE_IP':
                                bigip_vs.set_fallback_persist_profile(
                                    name=vip['id'],
                                    profile_name='/Common/source_addr',
                                    folder=vip['tenant_id'])
                        elif persistence_type == 'APP_COOKIE':
                            # application cookie persistence requires
                            # an HTTP profile
                            LOG.debug('adding http profile'
                                      ' and primary universal persistence')
                            bigip_vs.virtual_server.add_profile(
                                name=vip['id'],
                                profile_name='/Common/http',
                                folder=vip['tenant_id'])
                            # make sure they gave us a cookie_name
                            if 'cookie_name' in \
                          vip['session_persistence']['cookie_name']:
                                cookie_name = \
                          vip['session_persistence']['cookie_name']
                                # create and add irule to capture cookie
                                # from the service response.
                                rule_definition = \
                          self._create_app_cookie_persist_rule(cookie_name)
                                # try to create the irule
                                if bigip.rule.create(
                                        name=APP_COOKIE_RULE_PREFIX +
                                             vip['id'],
                                        rule_definition=rule_definition,
                                        folder=vip['tenant_id']):
                                    # create universal persistence profile
                                    bigip_vs.create_uie_profile(
                                        name=APP_COOKIE_RULE_PREFIX +
                                              vip['id'],
                                        rule_name=APP_COOKIE_RULE_PREFIX +
                                                  vip['id'],
                                        folder=vip['tenant_id'])
                                # set persistence profile
                                bigip_vs.set_persist_profile(
                                        name=vip['id'],
                                        profile_name=APP_COOKIE_RULE_PREFIX +
                                                 vip['id'],
                                        folder=vip['tenant_id'])
                                if pool['lb_method'] == 'SOURCE_IP':
                                    bigip_vs.set_fallback_persist_profile(
                                        name=vip['id'],
                                        profile_name='/Common/source_addr',
                                        folder=vip['tenant_id'])
                            else:
                                # if they did not supply a cookie_name
                                # just default to regualar cookie peristence
                                bigip_vs.set_persist_profile(
                                       name=vip['id'],
                                       profile_name='/Common/cookie',
                                       folder=vip['tenant_id'])
                                if pool['lb_method'] == 'SOURCE_IP':
                                    bigip_vs.set_fallback_persist_profile(
                                        name=vip['id'],
                                        profile_name='/Common/source_addr',
                                        folder=vip['tenant_id'])
                    else:
                        bigip_vs.remove_all_persist_profiles(
                                        name=vip['id'],
                                        folder=vip['tenant_id'])

                    rule_name = 'http_throttle_' + vip['id']

                    if vip['connection_limit'] > 0 and \
                       'protocol' in vip:
                        # spec says you need to do this for HTTP
                        # and HTTPS, but unless you can decrypt
                        # you can't measure HTTP rps for HTTPs... Duh..
                        if vip['protocol'] == 'HTTP':
                            LOG.debug('adding http profile'
                                      ' and RPS throttle rule')
                            # add an http profile
                            bigip_vs.add_profile(
                                name=vip['id'],
                                profile_name='/Common/http',
                                folder=vip['tenant_id'])
                            # create the rps irule
                            rule_definition = \
                              self._create_http_rps_throttle_rule(
                                            vip['connection_limit'])
                            # try to create the irule
                            bigip.rule.create(
                                    name=RPS_THROTTLE_RULE_PREFIX +
                                     vip['id'],
                                    rule_definition=rule_definition,
                                    folder=vip['tenant_id'])
                            # add the throttle to the vip
                            bigip_vs.add_rule(
                                        name=vip['id'],
                                        rule_name=RPS_THROTTLE_RULE_PREFIX +
                                              vip['id'],
                                        priority=500,
                                        folder=vip['tenant_id'])
                        else:
                            LOG.debug('setting connection limit')
                            # if not HTTP.. use connection limits
                            bigip_vs.set_connection_limit(
                                name=vip['id'],
                                connection_limit=int(
                                        vip['connection_limit']),
                                folder=pool['tenant_id'])
                    else:
                        # clear throttle rule
                        LOG.debug('removing RPS throttle rule if present')
                        bigip_vs.remove_rule(
                                            name=RPS_THROTTLE_RULE_PREFIX +
                                            vip['id'],
                                            rule_name=rule_name,
                                            priority=500,
                                            folder=vip['tenant_id'])
                        # clear the connection limits
                        LOG.debug('removing connection limits')
                        bigip_vs.set_connection_limit(
                                name=vip['id'],
                                connection_limit=0,
                                folder=pool['tenant_id'])

                    if on_last_bigip:
                        self.plugin_rpc.update_vip_status(
                                            vip['id'],
                                            status=plugin_const.ACTIVE,
                                            status_description='vip updated')
                if subnet['id'] in ctx.check_for_delete_subnets:
                    del(ctx.check_for_delete_subnets[subnet['id']])
                if subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.do_not_delete_subnets.append(subnet['id'])

    def assure_pool_delete(self, service, bigip):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            self._assure_pool_delete(service, bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_pool_delete(self, service, bigip, on_last_bigip):
        # Remove the pool if it is pending delete
        if service['pool']['status'] == plugin_const.PENDING_DELETE:
            LOG.debug(_('Deleting Pool %s' % service['pool']['id']))
            bigip.pool.delete(name=service['pool']['id'],
                              folder=service['pool']['tenant_id'])
            try:
                if on_last_bigip:
                    self.plugin_rpc.pool_destroyed(service['pool']['id'])
            except Exception as exc:
                LOG.error(_("Plugin delete pool %s error: %s"
                            % (service['pool']['id'], exc.message)
                            ))

    def assure_delete_networks(self, service, bigip, ctxs):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_last_bigip = (bigip is bigips[-1])
            ctx = ctxs[bigip.device_name]
            self._assure_delete_networks(service, bigip, ctx, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_delete_networks(self, service, bigip, ctx, on_last_bigip):
        # Clean up any Self IP, SNATs, networks, and folder for
        # services items that we deleted.
        for subnetinfo in ctx.check_for_delete_subnets.values():
            network = subnetinfo.network
            subnet = subnetinfo.subnet
            delete_subnet_objects = True
            ipsubnet = netaddr.IPNetwork(subnet['cidr'])
            # Are there any virtual addresses on this subnet
            virtual_services = \
                        bigip.virtual_server.get_virtual_service_insertion(
                                        folder=service['pool']['tenant_id'])
            for virt_serv in virtual_services:
                (vs_name, dest) = virt_serv.items()[0]
                if netaddr.IPAddress(dest['address']) in ipsubnet:
                    delete_subnet_objects = False
                    break
            if delete_subnet_objects:
                # If there aren't any virtual addresses, are there
                # node addresses on this subnet
                nodes = bigip.pool.get_node_addresses(
                                folder=service['pool']['tenant_id'])
                for node in nodes:
                    if netaddr.IPAddress(node) in ipsubnet:
                        delete_subnet_objects = False
                        break
            if delete_subnet_objects:
                # Since no virtual addresses or nodes found
                # go ahead and try to delete the Self IP
                # and SNATs
                if not self.conf.f5_snat_mode:
                    self._delete_gateway_on_subnet(subnetinfo,
                                                   bigip, on_last_bigip)
                # Since no virtual addresses or nodes found
                # go ahead and try to delete the Self IP
                # and SNATs
                self._delete_selfip_and_snats(service,
                                              self.SubnetInfo(network, subnet),
                                              bigip, on_last_bigip)
                # avoids race condition:
                # deletion of ip objects must sync before we
                # remove the vlan from the peer bigips.
                self.sync_if_clustered(bigip)
                try:
                    self._delete_network(network, bigip, on_last_bigip)
                except:
                    pass
                # Flag this network so we won't try to go through
                # this same process if a deleted member is on
                # this same subnet.
                if subnet['id'] not in ctx.do_not_delete_subnets:
                    ctx.do_not_delete_subnets.append(subnet['id'])

    def assure_tenant_cleanup(self, service, bigip, ctxs):
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            ctx = ctxs[bigip.device_name]
            self._assure_tenant_cleanup(service, bigip, ctx)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_tenant_cleanup(self, service, bigip, ctx):
        # if something was deleted check whether to do domain+folder teardown
        if service['pool']['status'] == plugin_const.PENDING_DELETE or \
                len(ctx.check_for_delete_subnets) > 0:
            existing_monitors = bigip.monitor.get_monitors(
                                    folder=service['pool']['tenant_id'])
            existing_pools = bigip.pool.get_pools(
                                    folder=service['pool']['tenant_id'])
            existing_vips = bigip.virtual_server.get_virtual_service_insertion(
                                    folder=service['pool']['tenant_id'])

            if not existing_monitors and \
               not existing_pools and \
               not existing_vips:
                self.remove_tenant(service, bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def remove_tenant(self, service, bigip):
        try:
            if self.conf.sync_mode == 'replication':
                bigip.route.delete_domain(
                            folder=service['pool']['tenant_id'])
                bigip.system.delete_folder(folder='/uuid_' +
                                             service['pool']['tenant_id'])
            else:
                # syncing the folder delete seems to cause problems,
                # so try deleting it on each device
                clustered = (len(self.__bigips.values()) > 1)
                if clustered:
                    bigip.device_group = bigip.device.get_device_group()
                # turn off sync on all devices so we can prevent
                # a sync from another device doing it
                for set_bigip in self.__bigips.values():
                    set_bigip.system.set_folder('/Common')
                    if clustered:
                        set_bigip.cluster.mgmt_dg.set_autosync_enabled_state(
                                     [bigip.device_group], ['STATE_DISABLED'])
                # all domains must be gone before we attempt to delete
                # the folder or it won't delete due to not being empty
                for set_bigip in self.__bigips.values():
                    set_bigip.route.delete_domain(
                            folder=service['pool']['tenant_id'])
                    set_bigip.system.set_folder('/Common')
                    set_bigip.system.delete_folder(folder='/uuid_' +
                                             service['pool']['tenant_id'])
                # turn off sync on all devices so we can delete the folder
                # on each device individually
                for set_bigip in self.__bigips.values():
                    set_bigip.system.set_folder('/Common')
                    if clustered:
                        set_bigip.cluster.mgmt_dg.set_autosync_enabled_state(
                                                    [bigip.device_group],
                                                    ['STATE_ENABLED'])
                if clustered:
                    # Need to make sure this folder delete syncs before
                    # something else runs and changes the current folder to
                    # the folder being deleted which will cause big problems.
                    self.sync_if_clustered(bigip)
        except:
            LOG.error("Error cleaning up tenant " +
                               service['pool']['tenant_id'])

    def _assure_service_networks(self, service):
        start_time = time()
        bigip = self._get_bigip()
        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            bigips = [bigip]
        for bigip in bigips:
            on_first_bigip = (bigip is bigips[0])
            on_last_bigip = (bigip is bigips[-1])
            self.__assure_service_networks(service,
                        bigip, on_first_bigip, on_last_bigip)
        if time() - start_time > .001:
            LOG.debug("    assure_service_networks took %.5f secs" %
                      (time() - start_time))

    # called for every bigip only in replication mode.
    # otherwise called once
    def __assure_service_networks(self, service,
              bigip, on_first_bigip, on_last_bigip):

        if 'id' in service['vip']:
            if not service['vip']['status'] == plugin_const.PENDING_DELETE:
                network = service['vip']['network']
                subnet = service['vip']['subnet']
                self._assure_network(network,
                                     bigip, on_first_bigip, on_last_bigip)
                self._assure_selfip_and_snats(service,
                                        self.SubnetInfo(network, subnet),
                                        bigip, on_first_bigip, on_last_bigip)

        for member in service['members']:
            if not member['status'] == plugin_const.PENDING_DELETE:
                network = member['network']
                subnet = member['subnet']
                start_time = time()
                self._assure_network(network, bigip,
                                     on_first_bigip, on_last_bigip)
                if time() - start_time > .001:
                    LOG.debug("        __assure_service_networks:"
                              "assure_network took %.5f secs" %
                              (time() - start_time))
                # each member gets a local self IP on each device
                start_time = time()
                self._assure_selfip_and_snats(service,
                                     self.SubnetInfo(network, subnet),
                                     bigip, on_first_bigip, on_last_bigip)
                if time() - start_time > .001:
                    LOG.debug("        __assure_service_networks:"
                              "assure_selfip_snat took %.5f secs" %
                              (time() - start_time))
                # if we are not using SNATS, attempt to become
                # the subnet's default gateway.
                if not self.conf.f5_snat_mode:
                    self._assure_gateway_on_subnet(
                            self.SubnetInfo(network,
                                            subnet,
                                            member['subnet_ports']),
                            bigip, on_first_bigip, on_last_bigip)

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_network(self, network, bigip, on_first_bigip, on_last_bigip):
        start_time = time()
        if self.conf.sync_mode == 'replication' and not on_first_bigip:
            # already did this work
            return

        bigips = bigip.group_bigips
        for bigip in bigips:
            if network['id'] in bigip.assured_networks:
                continue
            self.__assure_network(network, bigip)
            bigip.assured_networks.append(network['id'])
        if time() - start_time > .001:
            LOG.debug("        assure network took %.5f secs" %
                           (time() - start_time))

    # called for every bigip in every sync mode
    def __assure_network(self, network, bigip):

        # setup all needed L2 network segments
        if network['provider:network_type'] == 'vlan':
            if network['shared']:
                network_folder = 'Common'
            else:
                network_folder = network['tenant_id']

            # VLAN names are limited to 64 characters including
            # the folder name, so we name them foolish things.

            interface = self.interface_mapping['default']
            tagged = self.tagging_mapping['default']
            vlanid = 0

            if network['provider:physical_network'] in \
                                        self.interface_mapping:
                interface = self.interface_mapping[
                          network['provider:physical_network']]
                tagged = self.tagging_mapping[
                          network['provider:physical_network']]

            if tagged:
                vlanid = network['provider:segmentation_id']
            else:
                vlanid = 0

            vlan_name = self._get_vlan_name(network)

            bigip.vlan.create(name=vlan_name,
                              vlanid=vlanid,
                              interface=interface,
                              folder=network_folder,
                              description=network['id'])

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

            vlan_name = self._get_vlan_name(network)

            bigip.vlan.create(name=vlan_name,
                              vlanid=0,
                              interface=interface,
                              folder=network_folder,
                              description=network['id'])

        # TODO: add vxlan

        # TODO: add gre

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_selfip_and_snats(self, service, subnetinfo,
                                 bigip, on_first_bigip, on_last_bigip):

        network = subnetinfo.network
        subnet = subnetinfo.subnet
        pool = service['pool']
        # Sync special case:
        # In replication mode, even though assure_selfip_and_snats
        # is called for each bigip, we allocate a floating ip later that needs
        # to be the same for every bigip. We could allocate the ips and pass
        # them back to so they can be used multiple times, but its easier to
        # just do all the work here. This function is called for every big-ip
        # but we only want to do this work once, so we'll only do this on the
        # first bigip.
        if self.conf.sync_mode == 'replication' and not on_first_bigip:
            # we already did this work
            return

        # Where to put all these objects?
        network_folder = pool['tenant_id']
        if network['shared']:
            network_folder = 'Common'
        vlan_name = self._get_vlan_name(network)

        # These selfs are unique to each big-ip
        for set_bigip in bigip.group_bigips:
            if subnet['id'] in set_bigip.assured_snat_subnets:
                continue
            self.create_local_selfip(set_bigip, subnet,
                                     network_folder, vlan_name)

        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        #
        if self.conf.f5_snat_addresses_per_subnet > 0:
            snat_pool_name = pool['tenant_id']

            if self.conf.f5_ha_type == 'standalone':
                self.assure_snats_standalone(bigip, subnetinfo,
                                             snat_pool_name,
                                             network_folder,
                                             pool['tenant_id'])
            elif self.conf.f5_ha_type == 'ha':
                self.assure_snats_ha(bigip, subnetinfo,
                                     snat_pool_name,
                                     network_folder,
                                     pool['tenant_id'])
            elif self.conf.f5_ha_type == 'scalen':
                self.assure_snats_scalen(bigip, subnetinfo,
                                     snat_pool_name,
                                     network_folder,
                                     pool['tenant_id'])

    # called for every bigip
    def create_local_selfip(self, bigip, subnet, network_folder, vlan_name):
        local_selfip_name = "local-" + bigip.device_name + "-" + subnet['id']

        ports = self.plugin_rpc.get_port_by_name(
                                    port_name=local_selfip_name)
        #LOG.debug("got ports: %s" % ports)
        if len(ports) > 0:
            ip_address = ports[0]['fixed_ips'][0]['ip_address']
        else:
            new_port = self.plugin_rpc.create_port_on_subnet(
                        subnet_id=subnet['id'],
                        mac_address=None,
                        name=local_selfip_name,
                        fixed_address_count=1)
            ip_address = new_port['fixed_ips'][0]['ip_address']
        netmask = netaddr.IPNetwork(
                           subnet['cidr']).netmask
        bigip.selfip.create(name=local_selfip_name,
                            ip_address=ip_address,
                            netmask=netmask,
                            vlan_name=vlan_name,
                            floating=False,
                            folder=network_folder)

    def assure_snats_standalone(self, bigip, subnetinfo,
                                snat_pool_name,
                                snat_folder,
                                snat_pool_folder):
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        if subnet['id'] in bigip.assured_snat_subnets:
            return

        # Create SNATs on traffic-group-local-only
        snat_name = 'snat-traffic-group-local-only-' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)
            ports = self.plugin_rpc.get_port_by_name(
                                    port_name=index_snat_name)
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            if network['shared']:
                ip_address = ip_address + '%0'
            if network['shared']:
                index_snat_name = '/Common/' + index_snat_name

            tglo = '/Common/traffic-group-local-only',
            bigip.self.create_snat(
                       name=index_snat_name,
                       ip_address=ip_address,
                       traffic_group=tglo,
                       snat_pool_name=None,
                       folder=snat_folder)
            bigip.snat.create_pool(name=snat_pool_name,
                                   member_name=index_snat_name,
                                   folder=snat_pool_folder)

        bigip.assured_snat_subnets.append(subnet['id'])

    def assure_snats_ha(self, bigip, subnetinfo,
                        snat_pool_name,
                        snat_folder,
                        snat_pool_folder):
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        all_assured = True
        for set_bigip in bigip.group_bigips:
            if subnet['id'] not in set_bigip.assured_snat_subnets:
                all_assured = False
                break
        if all_assured:
            return

        snat_name = 'snat-traffic-group-1' + subnet['id']
        for i in range(self.conf.f5_snat_addresses_per_subnet):
            ip_address = None
            index_snat_name = snat_name + "_" + str(i)
            start_time = time()
            ports = self.plugin_rpc.get_port_by_name(
                                    port_name=index_snat_name)
            LOG.debug("        assure_snat:"
                      "get_port_by_name took %.5f secs" %
                      (time() - start_time))
            if len(ports) > 0:
                ip_address = ports[0]['fixed_ips'][0]['ip_address']
            else:
                new_port = self.plugin_rpc.create_port_on_subnet(
                    subnet_id=subnet['id'],
                    mac_address=None,
                    name=index_snat_name,
                    fixed_address_count=1)
                ip_address = new_port['fixed_ips'][0]['ip_address']
            if network['shared']:
                ip_address = ip_address + '%0'
                index_snat_name = '/Common/' + index_snat_name
            if self.conf.sync_mode == 'replication':
                bigips = bigip.group_bigips
            else:
                bigips = [bigip]
            for set_bigip in bigips:
                if subnet['id'] in set_bigip.assured_snat_subnets:
                    continue
                set_bigip.snat.create(
                           name=index_snat_name,
                           ip_address=ip_address,
                           traffic_group='/Common/traffic-group-1',
                           snat_pool_name=None,
                           folder=snat_folder)
                set_bigip.snat.create_pool(name=snat_pool_name,
                                       member_name=index_snat_name,
                                       folder=snat_pool_folder)

        for set_bigip in bigip.group_bigips:
            if subnet['id'] in set_bigip.assured_snat_subnets:
                continue
            set_bigip.assured_snat_subnets.append(subnet['id'])

    def assure_snats_scalen(self, bigip, subnetinfo,
                            snat_pool_name,
                            snat_folder,
                            snat_pool_folder):
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        all_assured = True
        for set_bigip in bigip.group_bigips:
            if subnet['id'] not in set_bigip.assured_snat_subnets:
                all_assured = False
                break
        if all_assured:
            return
        # create SNATs on all provider defined traffic groups
        for traffic_group in self.__traffic_groups:
            for i in range(self.conf.f5_snat_addresses_per_subnet):
                snat_name = "snat-" + traffic_group + \
                            "-" + subnet['id']
                ip_address = None
                index_snat_name = snat_name + "_" + str(i)

                ports = self.plugin_rpc.get_port_by_name(
                                    port_name=index_snat_name)
                if len(ports) > 0:
                    ip_address = ports[0]['fixed_ips'][0]['ip_address']
                else:
                    new_port = self.plugin_rpc.create_port_on_subnet(
                                             subnet_id=subnet['id'],
                                             mac_address=None,
                                             name=index_snat_name,
                                             fixed_address_count=1)
                    ip_address = new_port['fixed_ips'][0]['ip_address']
                if network['shared']:
                    ip_address = ip_address + '%0'
                if network['shared']:
                    index_snat_name = '/Common/' + index_snat_name
                if self.conf.sync_mode == 'replication':
                    bigips = bigip.group_bigips
                else:
                    # this is a synced object,
                    # so only do it once in sync modes
                    bigips = [bigip]
                for set_bigip in bigips:
                    if subnet['id'] in set_bigip.assured_snat_subnets:
                        continue
                    set_bigip.snat.create(
                               name=index_snat_name,
                               ip_address=ip_address,
                               traffic_group=traffic_group,
                               snat_pool_name=None,
                               folder=snat_folder)
                    set_bigip.snat.create_pool(name=snat_pool_name,
                                   member_name=index_snat_name,
                                   folder=snat_pool_folder)

        for set_bigip in bigip.group_bigips:
            if subnet['id'] in set_bigip.assured_snat_subnets:
                continue
            set_bigip.assured_snat_subnets.append(subnet['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _assure_gateway_on_subnet(self, subnetinfo,
                                  bigip, on_first_bigip, on_last_bigip):

        network = subnetinfo.network
        subnet = subnetinfo.subnet
        subnet_ports = subnetinfo.subnet_ports

        # Sync special case:
        # In replication mode, even though _assure_floating_default_gateway is
        # called for each bigip, we allocate a floating ip later that needs to
        # be the same for every bigip. We could allocate the ips and pass them
        # back to so they can be used multiple times, but its easier to just
        # do all the work here. This function is called for every big-ip but we
        # only want to do this work once, so we'll only do this on the
        # first bigip
        if self.conf.sync_mode == 'replication' and not on_first_bigip:
            # we already did this work
            return

        # Do we already have a port with the gateway_ip belonging
        # to this agent's host?
        #
        # This is another way to check if you want to iterate
        # through all ports owned by this device
        #
        # for port in subnet_ports:
        #    if not need_port_for_gateway:
        #        break
        #    for fixed_ips in port['fixed_ips']:
        #        if fixed_ips['ip_address'] == \
        #            subnet['gateway_ip']:
        #            need_port_for_gateway = False
        #            break

        # Create a name for the port and for the IP Forwarding Virtual Server
        # as well as the floating Self IP which will answer ARP for the members
        gw_name = "gw-" + subnet['id']
        floating_selfip_name = "gw-" + subnet['id']
        netmask = netaddr.IPNetwork(subnet['cidr']).netmask
        ports = self.plugin_rpc.get_port_by_name(port_name=gw_name)
        if len(ports) < 1:
            need_port_for_gateway = True

        # There was not port on this agent's host, so get one from Neutron
        if need_port_for_gateway:
            try:
                new_port = \
                  self.plugin_rpc.create_port_on_subnet_with_specific_ip(
                            subnet_id=subnet['id'],
                            mac_address=None,
                            name=gw_name,
                            ip_address=subnet['gateway_ip'])
                subnet_ports.append(new_port)
            except Exception as exc:
                ermsg = 'Invalid default gateway for subnet %s:%s - %s.' \
                    % (subnet['id'],
                       subnet['gateway_ip'],
                       exc.message)
                ermsg += " SNAT will not function and load balancing"
                ermsg += " support will likely fail. Enable f5_snat_mode"
                ermsg += " and f5_source_monitor_from_member_subnet."
                LOG.error(_(ermsg))

        # Go ahead and setup a floating SelfIP with the subnet's
        # gateway_ip address on this agent's device service group

        network_folder = subnet['tenant_id']
        vlan_name = self._get_vlan_name(network)
        # Where to put all these objects?
        if network['shared']:
            network_folder = 'Common'
            vlan_name = '/Common/' + vlan_name

        # Select a traffic group for the floating SelfIP
        vip_tg = self._get_least_gw_traffic_group()

        if self.conf.sync_mode == 'replication':
            bigips = bigip.group_bigips
        else:
            # these are synced objects, so only create them once in sync modes
            bigips = [bigip]
        for bigip in bigips:
            if subnet['id'] in bigip.assured_gateway_subnets:
                continue
            bigip.selfip.create(
                            name=floating_selfip_name,
                            ip_address=subnet['gateway_ip'],
                            netmask=netmask,
                            vlan_name=vlan_name,
                            floating=True,
                            traffic_group=vip_tg,
                            folder=network_folder)

            # Get the actual traffic group if the Self IP already existed
            vip_tg = bigip.self.get_traffic_group(name=floating_selfip_name,
                                    folder=subnet['tenant_id'])

            # Setup a wild card ip forwarding virtual service for this subnet
            bigip.virtual_server.create_ip_forwarder(
                            name=gw_name, ip_address='0.0.0.0',
                            mask='0.0.0.0',
                            vlan_name=vlan_name,
                            traffic_group=vip_tg,
                            folder=network_folder)

            # Setup the IP forwarding virtual server to use the Self IPs
            # as the forwarding SNAT addresses
            bigip.virtual_server.set_snat_automap(name=gw_name,
                                folder=network_folder)
            bigip.assured_gateway_subnets.append(subnet['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _delete_network(self, network, bigip, on_last_bigip):
        if self.conf.sync_mode == 'replication':
            bigips = [bigip]
        else:
            bigips = bigip.group_bigips

        # setup all needed L2 network segments on all BigIPs
        for set_bigip in bigips:
            if network['provider:network_type'] == 'vlan':
                if network['shared']:
                    network_folder = 'Common'
                else:
                    network_folder = network['tenant_id']
                vlan_name = self._get_vlan_name(network)
                set_bigip.vlan.delete(name=vlan_name,
                                  folder=network_folder)

            if network['provider:network_type'] == 'flat':
                if network['shared']:
                    network_folder = 'Common'
                else:
                    network_folder = network['id']
                vlan_name = self._get_vlan_name(network)
                set_bigip.vlan.delete(name=vlan_name,
                                  folder=network_folder)
            # TODO: add vxlan

            # TODO: add gre

            if network['id'] in set_bigip.assured_networks:
                set_bigip.assured_networks.remove(network['id'])

    # called for every bigip only in replication mode.
    # otherwise called once
    def _delete_selfip_and_snats(self, service, subnetinfo,
                                 bigip, on_last_bigip):
        network = subnetinfo.network
        subnet = subnetinfo.subnet
        network_folder = service['pool']['tenant_id']
        if network['shared']:
            network_folder = 'Common'
        snat_pool_name = service['pool']['tenant_id']
        # Setup required SNAT addresses on this subnet
        # based on the HA requirements
        if self.conf.f5_snat_addresses_per_subnet > 0:
            # failover mode dictates SNAT placement on traffic-groups
            if self.conf.f5_ha_type == 'standalone':
                # Create SNATs on traffic-group-local-only
                snat_name = 'snat-traffic-group-local-only-' + subnet['id']
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    index_snat_name = snat_name + "_" + str(i)
                    if network['shared']:
                        tmos_snat_name = "/Common/" + index_snat_name
                    else:
                        tmos_snat_name = index_snat_name
                    bigip.snat.remove_from_pool(name=snat_pool_name,
                                         member_name=tmos_snat_name,
                                         folder=service['pool']['tenant_id'])
                    if bigip.snat.delete(name=tmos_snat_name,
                                         folder=network_folder):
                        # Only if it still exists and can be
                        # deleted because it is not in use can
                        # we safely delete the neutron port
                        if on_last_bigip:
                            self.plugin_rpc.delete_port_by_name(
                                            port_name=index_snat_name)
            elif self.conf.f5_ha_type == 'ha':
                # Create SNATs on traffic-group-1
                snat_name = 'snat-traffic-group-1' + subnet['id']
                for i in range(self.conf.f5_snat_addresses_per_subnet):
                    index_snat_name = snat_name + "_" + str(i)
                    if network['shared']:
                        tmos_snat_name = "/Common/" + index_snat_name
                    else:
                        tmos_snat_name = index_snat_name
                    bigip.snat.remove_from_pool(name=snat_pool_name,
                                        member_name=tmos_snat_name,
                                        folder=service['pool']['tenant_id'])
                    if bigip.snat.delete(name=tmos_snat_name,
                                         folder=network_folder):
                        # Only if it still exists and can be
                        # deleted because it is not in use can
                        # we safely delete the neutron port
                        if on_last_bigip:
                            self.plugin_rpc.delete_port_by_name(
                                            port_name=index_snat_name)
            elif self.conf.f5_ha_type == 'scalen':
                # create SNATs on all provider defined traffic groups
                for traffic_group in self.__traffic_groups:
                    for i in range(self.conf.f5_snat_addresses_per_subnet):
                        snat_name = "snat-" + traffic_group + \
                                    "-" + subnet['id']
                        index_snat_name = snat_name + "_" + str(i)
                        if network['shared']:
                            tmos_snat_name = "/Common/" + index_snat_name
                        else:
                            tmos_snat_name = index_snat_name
                        bigip.snat.remove_from_pool(name=snat_pool_name,
                                        member_name=tmos_snat_name,
                                        folder=service['pool']['tenant_id'])
                        if bigip.snat.delete(name=tmos_snat_name,
                                                 folder=network_folder):
                            # Only if it still exists and can be
                            # deleted because it is not in use can
                            # we safely delete the neutron port
                            if on_last_bigip:
                                self.plugin_rpc.delete_port_by_name(
                                                port_name=index_snat_name)

        # delete_selfip_and_snats called for every bigip only
        # in replication mode. otherwise called once
        if self.conf.sync_mode == 'replication':
            bigips = [bigip]
        else:
            bigips = bigip.group_bigips
        for bigip in bigips:
            local_selfip_name = "local-" + bigip.device_name + \
                                "-" + subnet['id']
            bigip.selfip.delete(name=local_selfip_name,
                                folder=network_folder)
            self.plugin_rpc.delete_port_by_name(port_name=local_selfip_name)

        for bigip in bigip.group_bigips:
            if subnet['id'] in bigip.assured_snat_subnets:
                bigip.assured_snat_subnets.remove(subnet['id'])


    # called for every bigip only in replication mode.
    # otherwise called once
    def _delete_gateway_on_subnet(self, subnetinfo, bigip, on_last_bigip):

        network = subnetinfo.network
        subnet = subnetinfo.subnet
        subnet_ports = subnetinfo.subnet_ports
        # Create a name for the port and for the IP Forwarding Virtual Server
        # as well as the floating Self IP which will answer ARP for the members
        gw_name = "gw-" + subnet['id']
        floating_selfip_name = "gw-" + subnet['id']

        # Go ahead and setup a floating SelfIP with the subnet's
        # gateway_ip address on this agent's device service group

        network_folder = subnet['tenant_id']
        if network['shared']:
            network_folder = 'Common'

        bigip.selfip.delete(name=floating_selfip_name,
                            folder=network_folder)

        # Setup a wild card ip forwarding virtual service for this subnet
        bigip.virtual_server.delete(name=gw_name,
                                    folder=network_folder)

        if on_last_bigip:
            # remove neutron default gateway port
            gateway_port_id = None
            for port in subnet_ports:
                if gateway_port_id:
                    break
                for fixed_ips in port['fixed_ips']:
                    if str(fixed_ips['ip_address']).strip() == \
                            str(subnet['gateway_ip']).strip():
                        gateway_port_id = port['id']
                        break

            # There was not port on this agent's host, so get one from Neutron
            if gateway_port_id:
                try:
                    self.plugin_rpc.delete_port(port_id=gateway_port_id,
                                                mac_address=None)
                except Exception as exc:
                    ermsg = 'Error on delete gateway port' + \
                            ' for subnet %s:%s - %s.' \
                            % (subnet['id'],
                               subnet['gateway_ip'],
                               exc.message)
                    ermsg += " You will need to delete this manually"
                    LOG.error(_(ermsg))
        if subnet['id'] in bigip.assured_gateway_subnets:
            bigip.assured_gateway_subnets.remove(subnet['id'])

    def _get_least_vips_traffic_group(self):
        ret_traffic_group = '/Common/traffic-group-1'
        lowest_count = 0
        vips_on_tgs = self.__vips_on_traffic_groups
        for traffic_group in vips_on_tgs:
            if vips_on_tgs[traffic_group] <= lowest_count:
                ret_traffic_group = vips_on_tgs[traffic_group]
        return ret_traffic_group

    def _get_least_gw_traffic_group(self):
        ret_traffic_group = '/Common/traffic-group-1'
        lowest_count = 0
        for traffic_group in self.__gw_on_traffic_groups:
            if self.__gw_on_traffic_groups[traffic_group] <= lowest_count:
                ret_traffic_group = self.__gw_on_traffic_groups[traffic_group]
        return ret_traffic_group

    def _get_bigip(self):
        hostnames = sorted(self.__bigips)
        for i in range(len(hostnames)):
            try:
                bigip = self.__bigips[hostnames[i]]
                bigip.system.set_folder('/Common')
                return bigip
            except urllib2.URLError:
                pass
        else:
            raise urllib2.URLError('cannot communicate to any bigips')

    def _get_vlan_name(self, network):
        interface = self.interface_mapping['default']
        tagged = self.tagging_mapping['default']
        ppn = 'provider:physical_network'

        if network[ppn] in self.interface_mapping:
            interface = self.interface_mapping[network[ppn]]
            tagged = self.tagging_mapping[network[ppn]]

        if tagged:
            vlanid = network['provider:segmentation_id']
        else:
            vlanid = 0

        return "vlan-" + str(interface).replace(".", "-") + "-" + str(vlanid)

    def _create_app_cookie_persist_rule(self, cookiename):
        rule_text = "when HTTP_REQUEST {\n"
        rule_text += " if { [HTTP::cookie " + str(cookiename)
        rule_text += "] ne \"\" }{\n"
        rule_text += "     persist uie [string tolower [HTTP::cookie \""
        rule_text += cookiename + "\"]] 3600\n"
        rule_text += " }\n"
        rule_text += "}\n\n"
        rule_text += "when HTTP_RESPONSE {\n"
        rule_text += " if { [HTTP::cookie \"" + str(cookiename)
        rule_text += "\"] ne \"\" }{\n"
        rule_text += "     persist add uie [string tolower [HTTP::cookie \""
        rule_text += cookiename + "\"]] 3600\n"
        rule_text += " }\n"
        rule_text += "}\n\n"
        return rule_text

    def _create_http_rps_throttle_rule(self, req_limit):
        rule_text = "when HTTP_REQUEST {\n"
        rule_text += " set expiration_time 300\n"
        rule_text += " set client_ip [IP::client_addr]\n"
        rule_text += " set req_limit " + str(req_limit) + "\n"
        rule_text += " set curr_time [clock seconds]\n"
        rule_text += " set timekey starttime\n"
        rule_text += " set reqkey reqcount\n"
        rule_text += " set request_count [session lookup uie $reqkey]\n"
        rule_text += " if { $request_count eq \"\" } {\n"
        rule_text += "   set request_count 1\n"
        rule_text += "   session add uie $reqkey $request_count "
        rule_text += "$expiration_time\n"
        rule_text += "   session add uie $timekey [expr {$curr_time - 2}]"
        rule_text += "[expr {$expiration_time + 2}]\n"
        rule_text += " } else {\n"
        rule_text += "   set start_time [session lookup uie $timekey]\n"
        rule_text += "   incr request_count\n"
        rule_text += "   session add uie $reqkey $request_count"
        rule_text += "$expiration_time\n"
        rule_text += "   set elapsed_time [expr {$curr_time - $start_time}]\n"
        rule_text += "   if {$elapsed_time < 60} {\n"
        rule_text += "     set elapsed_time 60\n"
        rule_text += "   }\n"
        rule_text += "   set curr_rate [expr {$request_count /"
        rule_text += "($elapsed_time/60)}]\n"
        rule_text += "   if {$curr_rate > $req_limit}{\n"
        rule_text += "     HTTP::respond 503 throttled \"Retry-After\" 60\n"
        rule_text += "   }\n"
        rule_text += " }\n"
        rule_text += "}\n"
        return rule_text

    def _init_connection(self):
        if not self.connected:
            try:
                self.__last_connect_attempt = datetime.datetime.now()

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
                first_bigip = f5_bigip.BigIP(self.hostnames[0],
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
                        first_bigip.system.set_folder('/Common')
                        this_devicename = \
                         first_bigip.device.mgmt_dev.get_local_device()
                        devices = first_bigip.device.get_all_device_names()
                        devices.remove(this_devicename)
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
                for traffic_group in self.__traffic_groups:
                    self.__gw_on_traffic_groups[traffic_group] = 0
                    self.__vips_on_traffic_groups[traffic_group] = 0

                # connect to the rest of the devices
                for host in self.hostnames[1:]:
                    hostbigip = f5_bigip.BigIP(host,
                                            self.username,
                                            self.password,
                                            5,
                                            self.conf.use_namespaces)
                    self.__bigips[host] = hostbigip

                if self.conf.debug and f5const.LOG_MODE == 'dev':
                    sudslog = std_logging.getLogger('suds.client')
                    sudslog.setLevel(std_logging.DEBUG)

                bigips = self.__bigips.values()
                for set_bigip in bigips:
                    set_bigip.group_bigips = bigips
                    set_bigip.sync_mode = self.conf.sync_mode
                    set_bigip.assured_networks = []
                    set_bigip.assured_snat_subnets = []
                    set_bigip.assured_gateway_subnets = []


                if self.conf.sync_mode == 'replication':
                    autosync_state = 'STATE_DISABLED'
                else:
                    autosync_state = 'STATE_ENABLED'
                for set_bigip in bigips:
                    device_group = set_bigip.device.get_device_group()
                    if device_group:
                        set_bigip.cluster.mgmt_dg.set_autosync_enabled_state(
                                [device_group], [autosync_state])

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

                    hostbigip.device_name = hostbigip.device.get_device_name()

                    LOG.debug(_('connected to iControl %s @ %s ver %s.%s'
                                % (self.username, host,
                                   major_version, minor_version)))

                self.connected = True
            except Exception as exc:
                LOG.error(_('Could not communicate with all ' +
                            'iControl devices: %s' % exc.message))

    # should be moved to cluster abstraction
    def sync_if_clustered(self, bigip):
        if self.conf.sync_mode == 'replication':
            return
        if len(bigip.group_bigips) > 1:
            if not bigip.device_group:
                bigip.device_group = bigip.device.get_device_group()
            bigip.cluster.sync(bigip.device_group)

    @serialized('backup_configuration')
    @am.is_connected
    def backup_configuration(self):
        for bigip in self.__bigips.values():
            bigip.system.set_folder('/Common')
            bigip.cluster.save_base_config()
            bigip.cluster.save_service_config()

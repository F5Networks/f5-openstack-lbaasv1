""" Classes and functions for configuring load balancing pools on bigip """
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

# pylint: disable=no-self-use,broad-except
try:
    from neutron.openstack.common import log as logging
    from neutron.services.loadbalancer import constants as lb_const
except ImportError:
    from oslo_log import log as logging
    from neutron_lbaas.services.loadbalancer import constants as lb_const
from neutron.plugins.common import constants as plugin_const
from time import time

LOG = logging.getLogger(__name__)


class BigipPoolManager(object):
    """ Class for managing pool """

    def __init__(self, driver, bigip_l2_manager):
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager

    def assure_bigip_pool_create(self, bigip, pool):
        """ Create pool on the bigip """
        if not pool['status'] == plugin_const.PENDING_DELETE:
            desc = pool['name'] + ':' + pool['description']
            bigip.pool.create(name=pool['id'],
                              lb_method=pool['lb_method'],
                              description=desc,
                              folder=pool['tenant_id'])
            if pool['status'] == plugin_const.PENDING_UPDATE:
                # make sure pool attributes are correct
                bigip.pool.set_lb_method(name=pool['id'],
                                         lb_method=pool['lb_method'],
                                         folder=pool['tenant_id'])
                bigip.pool.set_description(name=pool['id'],
                                           description=desc,
                                           folder=pool['tenant_id'])

    def assure_bigip_pool_delete(self, bigip, service):
        """ Assure pool is deleted from big-ip """
        LOG.debug(_('Deleting Pool %s' % service['pool']['id']))
        bigip.pool.delete(name=service['pool']['id'],
                          folder=service['pool']['tenant_id'])

    def assure_bigip_pool_monitors(self, bigip, service):
        """ Create pool monitors on bigip """
        pool = service['pool']
        # Current monitors on the pool according to BigIP
        existing_monitors = bigip.pool.get_monitors(name=pool['id'],
                                                    folder=pool['tenant_id'])

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
                # not sure if the monitor might be in use
                try:
                    LOG.debug(_('Deleting %s monitor /%s/%s'
                                % (monitor['type'],
                                   pool['tenant_id'],
                                   monitor['id'])))
                    bigip.monitor.delete(name=monitor['id'],
                                         mon_type=monitor['type'],
                                         folder=pool['tenant_id'])
                # pylint: disable=bare-except
                except:
                    pass
                # pylint: enable=bare-except
            else:
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
                    self._update_monitor(bigip, monitor, set_times=False)
                else:
                    if health_monitors_status[monitor['id']] == \
                            plugin_const.PENDING_UPDATE:
                        self._update_monitor(bigip, monitor)

                if not found_existing_monitor:
                    bigip.pool.add_monitor(name=pool['id'],
                                           monitor_name=monitor['id'],
                                           folder=pool['tenant_id'])

            if found_existing_monitor:
                existing_monitors.remove(monitor['id'])

        LOG.debug(_("Pool: %s removing monitors %s"
                    % (pool['id'], existing_monitors)))
        # get rid of monitors no longer in service definition
        for monitor in existing_monitors:
            bigip.monitor.delete(name=monitor,
                                 mon_type=None,
                                 folder=pool['tenant_id'])

    def _update_monitor(self, bigip, monitor, set_times=True):
        """ Update monitor on bigip """
        if set_times:
            timeout = int(monitor['max_retries']) * \
                int(monitor['timeout'])
            # make sure monitor attributes are correct
            bigip.monitor.set_interval(name=monitor['id'],
                                       mon_type=monitor['type'],
                                       interval=monitor['delay'],
                                       folder=monitor['tenant_id'])
            bigip.monitor.set_timeout(name=monitor['id'],
                                      mon_type=monitor['type'],
                                      timeout=timeout,
                                      folder=monitor['tenant_id'])

        if monitor['type'] == 'HTTP' or monitor['type'] == 'HTTPS':
            self._update_http_monitor(bigip, monitor)

    def _update_http_monitor(self, bigip, monitor):
        """ Update pool monitor on bigip """
        if 'url_path' in monitor:
            send_text = "GET " + monitor['url_path'] + \
                " HTTP/1.0\\r\\n\\r\\n"
        else:
            send_text = "GET / HTTP/1.0\\r\\n\\r\\n"

        if 'expected_codes' in monitor:
            try:
                if monitor['expected_codes'].find(",") > 0:
                    status_codes = monitor['expected_codes'].split(',')
                    recv_text = "HTTP/1.(0|1) ("
                    for status in status_codes:
                        int(status)
                        recv_text += status + "|"
                    recv_text = recv_text[:-1]
                    recv_text += ")"
                elif monitor['expected_codes'].find("-") > 0:
                    status_range = monitor['expected_codes'].split('-')
                    start_range = status_range[0]
                    int(start_range)
                    stop_range = status_range[1]
                    int(stop_range)
                    recv_text = "HTTP/1.(0|1) [" + \
                        start_range + "-" + \
                        stop_range + "]"
                else:
                    int(monitor['expected_codes'])
                    recv_text = "HTTP/1.(0|1) " + monitor['expected_codes']
            except Exception as exc:
                LOG.error(_(
                    "invalid monitor: %s, expected_codes %s, setting to 200"
                    % (exc, monitor['expected_codes'])))
                recv_text = "HTTP/1.(0|1) 200"
        else:
            recv_text = "HTTP/1.(0|1) 200"

        LOG.debug('setting monitor send: %s, receive: %s'
                  % (send_text, recv_text))

        bigip.monitor.set_send_string(name=monitor['id'],
                                      mon_type=monitor['type'],
                                      send_text=send_text,
                                      folder=monitor['tenant_id'])
        bigip.monitor.set_recv_string(name=monitor['id'],
                                      mon_type=monitor['type'],
                                      recv_text=recv_text,
                                      folder=monitor['tenant_id'])

    def assure_bigip_members(self, bigip, service, subnet_hints):
        """ Ensure pool members are on bigip """
        pool = service['pool']
        start_time = time()
        # Does pool exist... If not don't bother
        if not bigip.pool.exists(name=pool['id'], folder=pool['tenant_id']):
            return
        # Current members on the BigIP
        pool['existing_members'] = bigip.pool.get_members(
            name=pool['id'], folder=pool['tenant_id'])
        # Flag if we need to change the pool's LB method to
        # include weighting by the ratio attribute
        any_using_ratio = False
        # Members according to Neutron
        for member in service['members']:
            member_hints = \
                self._assure_bigip_member(bigip, subnet_hints, pool, member)
            if member_hints['using_ratio']:
                any_using_ratio = True

            # Remove member from the list of members bigip needs to remove
            if member_hints['found_existing']:
                pool['existing_members'].remove(member_hints['found_existing'])

        LOG.debug(_("Pool: %s removing members %s"
                    % (pool['id'], pool['existing_members'])))
        # remove any members which are no longer in the service
        for need_to_delete in pool['existing_members']:
            bigip.pool.remove_member(name=pool['id'],
                                     ip_address=need_to_delete['addr'],
                                     port=int(need_to_delete['port']),
                                     folder=pool['tenant_id'])

        # if members are using weights, change the LB to RATIO
        if any_using_ratio:
            # LOG.debug(_("Pool: %s changing to ratio based lb"
            #        % pool['id']))
            if pool['lb_method'] == lb_const.LB_METHOD_LEAST_CONNECTIONS:
                bigip.pool.set_lb_method(name=pool['id'],
                                         lb_method='RATIO_LEAST_CONNECTIONS',
                                         folder=pool['tenant_id'])
            else:
                bigip.pool.set_lb_method(name=pool['id'],
                                         lb_method='RATIO',
                                         folder=pool['tenant_id'])
        else:
            # We must update the pool lb_method for the case where
            # the pool object was not updated, but the member
            # used to have a weight (setting ration) and now does
            # not.
            bigip.pool.set_lb_method(name=pool['id'],
                                     lb_method=pool['lb_method'],
                                     folder=pool['tenant_id'])
        if time() - start_time > .001:
            LOG.debug("        _assure_members setting pool lb method" +
                      " took %.5f secs" % (time() - start_time))

    def _assure_bigip_member(self, bigip, subnet_hints, pool, member):
        """ Ensure pool member is on bigip """
        start_time = time()

        network = member['network']
        subnet = member['subnet']
        member_hints = {'found_existing': None,
                        'using_ratio': False,
                        'deleted_members': []}

        ip_address = member['address']
        for existing_member in pool['existing_members']:
            if ip_address.startswith(existing_member['addr']) and \
               (member['protocol_port'] == existing_member['port']):
                member_hints['found_existing'] = existing_member
                break

        # Delete those pending delete
        if member['status'] == plugin_const.PENDING_DELETE:
            self._assure_bigip_delete_member(bigip, pool, member, ip_address)
            member_hints['deleted_members'].append(member)
            if subnet and \
               subnet['id'] not in subnet_hints['do_not_delete_subnets']:
                subnet_hints['check_for_delete_subnets'][subnet['id']] = \
                    {'network': network,
                     'subnet': subnet,
                     'is_for_member': True}
        else:
            just_added = False
            if not member_hints['found_existing']:
                add_start_time = time()
                port = int(member['protocol_port'])
                if bigip.pool.add_member(name=pool['id'],
                                         ip_address=ip_address,
                                         port=port,
                                         folder=pool['tenant_id'],
                                         no_checks=True):
                    just_added = True
                LOG.debug("           bigip.pool.add_member %s took %.5f" %
                          (ip_address, time() - add_start_time))
            if just_added or member['status'] == plugin_const.PENDING_UPDATE:
                member_info = {'pool': pool, 'member': member,
                               'ip_address': ip_address,
                               'just_added': just_added}
                member_hints['using_ratio'] = \
                    self._assure_update_member(bigip, member_info)
            if subnet and \
               subnet['id'] in subnet_hints['check_for_delete_subnets']:
                del subnet_hints['check_for_delete_subnets'][subnet['id']]
            if subnet and \
               subnet['id'] not in subnet_hints['do_not_delete_subnets']:
                subnet_hints['do_not_delete_subnets'].append(subnet['id'])

        if time() - start_time > .001:
            LOG.debug("        assuring member %s took %.5f secs" %
                      (member['address'], time() - start_time))
        return member_hints

    def _assure_update_member(self, bigip, member_info):
        """ Update properties of pool member on bigip """
        pool = member_info['pool']
        member = member_info['member']
        ip_address = member_info['ip_address']
        just_added = member_info['just_added']

        using_ratio = False
        # Is it enabled or disabled?
        # no_checks because we add the member above if not found
        start_time = time()
        member_port = int(member['protocol_port'])
        if member['admin_state_up']:
            bigip.pool.enable_member(name=pool['id'],
                                     ip_address=ip_address,
                                     port=member_port,
                                     folder=pool['tenant_id'],
                                     no_checks=True)
        else:
            bigip.pool.disable_member(name=pool['id'],
                                      ip_address=ip_address,
                                      port=member_port,
                                      folder=pool['tenant_id'],
                                      no_checks=True)
        LOG.debug("            member enable/disable took %.5f secs" %
                  (time() - start_time))
        # Do we have weights for ratios?
        if member['weight'] > 1:
            if not just_added:
                start_time = time()
                set_ratio = bigip.pool.set_member_ratio
                set_ratio(name=pool['id'],
                          ip_address=ip_address,
                          port=member_port,
                          ratio=int(member['weight']),
                          folder=pool['tenant_id'],
                          no_checks=True)
                if time() - start_time > .0001:
                    LOG.debug("            member set ratio took %.5f secs" %
                              (time() - start_time))
            using_ratio = True

        return using_ratio

    def _assure_bigip_delete_member(self, bigip,
                                    pool, member, ip_address):
        """ Ensure pool member is deleted from bigip """
        member_port = int(member['protocol_port'])
        bigip.pool.remove_member(name=pool['id'],
                                 ip_address=ip_address,
                                 port=member_port,
                                 folder=pool['tenant_id'])

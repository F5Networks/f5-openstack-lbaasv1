""" F5 Networks LBaaS Driver using iControl API of BIG-IP """
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
# pylint: disable=broad-except,star-args,no-self-use
from neutron.openstack.common import log as logging
from neutron.plugins.common import constants as plugin_const
from eventlet import greenthread

LOG = logging.getLogger(__name__)


class LBaaSBuilder(object):
    """ F5 LBaaS Driver for BIG-IP using iControl
        to create objects (vips, pools) directly,
        (rather than using an iApp - LBaaSBuilderiApp).

        This is an abstract base class.
    """
    def __init__(self, conf, driver, bigip_l2_manager=None):
        self.conf = conf
        self.driver = driver
        self.bigip_l2_manager = bigip_l2_manager

    def assure_service(self, service, traffic_group):
        """ Assure that the service is configured """
        pass

    def _check_monitor_delete(self, service):
        """If the pool is being deleted, then delete related objects"""
        if service['pool']['status'] == plugin_const.PENDING_DELETE:
            # Everything needs to be go with the pool, so overwrite
            # service state to appropriately remove all elements
            service['vip']['status'] = plugin_const.PENDING_DELETE
            for member in service['members']:
                member['status'] = plugin_const.PENDING_DELETE
            for monitor in service['pool']['health_monitors_status']:
                monitor['status'] = plugin_const.PENDING_DELETE

    def _sync_if_clustered(self):
        """ sync device group if not in replication mode """
        if self.conf.f5_ha_type == 'standalone' or \
                self.conf.f5_sync_mode == 'replication' or \
                len(self.driver.get_all_bigips()) < 2:
            return
        bigip = self.driver.get_bigip()
        self._sync_with_retries(bigip)

    def _sync_with_retries(self, bigip, force_now=False,
                           attempts=4, retry_delay=130):
        """ sync device group """
        for attempt in range(1, attempts + 1):
            LOG.debug('Syncing Cluster... attempt %d of %d'
                      % (attempt, attempts))
            try:
                if attempt != 1:
                    force_now = False
                bigip.cluster.sync(bigip.device_group_name,
                                   force_now=force_now)
                LOG.debug('Cluster synced.')
                return
            except Exception as exc:
                LOG.error('ERROR: Cluster sync failed: %s' % exc)
                if attempt == attempts:
                    raise
                LOG.error('Wait another %d seconds for devices '
                          'to recover from failed sync.' % retry_delay)
                greenthread.sleep(retry_delay)

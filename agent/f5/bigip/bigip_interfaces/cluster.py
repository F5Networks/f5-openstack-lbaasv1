##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common import constants as const
from f5.common.logger import Log
from f5.bigip.exceptions import BigIPClusterPeerAddFailure
from f5.bigip.exceptions import BigIPDeviceLockAcquireFailed
from f5.bigip.exceptions import BigIPClusterSyncFailure

import time
import os
import json


# Management - Cluster
class Cluster(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(
                                           ['Management.Device',
                                            'Management.DeviceGroup',
                                            'Management.TrafficGroup',
                                            'Management.Trust',
                                            'System.ConfigSync'])

        # iControl helper objects
        self.mgmt_dev = self.bigip.icontrol.Management.Device
        self.mgmt_dg = self.bigip.icontrol.Management.DeviceGroup
        self.mgmt_trust = self.bigip.icontrol.Management.Trust
        self.mgmt_tg = self.bigip.icontrol.Management.TrafficGroup
        self.sys_sync = self.bigip.icontrol.System.ConfigSync

    def get_sync_status(self):
        return self.mgmt_dg.get_sync_status_overview().status

    def save_base_config(self):
        self.sys_sync.save_configuration(filename="",
                                         save_flag="SAVE_BASE_LEVEL_CONFIG")

    def save_service_config(self):
        self.sys_sync.save_configuration(filename="",
                                         save_flag="SAVE_HIGH_LEVEL_CONFIG")

    def save_full_config(self):
        self.sys_sync.save_configuration(filename="",
                                         save_flag="SAVE_FULL")

    # force_now=True is typically used for initial sync.
    # In order to avoid sync problems, you should wait until devices
    # in the group are connected.
    def sync(self, name, force_now=False):
        sync_start_time = time.time()
        self.bigip.system.set_folder('/Common')
        dev_name = self.mgmt_dev.get_local_device()
        sleep_delay = const.SYNC_DELAY

        attempts = 0
        if force_now:
            self.sys_sync.synchronize_to_group_v2(name, dev_name, True)
            time.sleep(sleep_delay)
            attempts += 1

        while attempts < const.MAX_SYNC_ATTEMPTS:
            state = self.get_sync_status()
            if state in ['Standalone',
                         'In Sync',
                        ]:
                break

            elif state == 'Awaiting Initial Sync':
                attempts += 1
                Log.info('Cluster',
                    "Device %s - Synchronizing initial config to group %s"
                    % (dev_name, name))
                self.sys_sync.synchronize_to_group_v2(name, dev_name, True)
                time.sleep(sleep_delay)

            elif state in ['Disconnected',
                            'Not All Devices Synced',
                            'Changes Pending',
                           ]:
                attempts += 1

                last_log_time = 0
                now = time.time()
                wait_start_time = now
                # Keep checking the sync state in a quick loop.
                # We want to detect In Sync as quickly as possible.
                while now - wait_start_time < sleep_delay:
                    # Only log once per second
                    if now - last_log_time >= 1:
                        Log.info('Cluster',
                            'Device %s, Group %s not synced. '
                            % (dev_name, name) + \
                            'Waiting. State is: %s'
                            % state)
                        last_log_time = now
                    state = self.get_sync_status()
                    if state in ['Standalone',
                                 'In Sync',
                                ]:
                        break
                    time.sleep(.5)
                    now = time.time()
                else:
                    # if we didn't break out due to the group being in sync
                    # then attempt to force a sync.
                    self.sys_sync.synchronize_to_group_v2(name, dev_name, True)
                    sleep_delay += const.SYNC_DELAY
                    # no need to sleep here because we already spent the sleep
                    # interval checking status.
                    continue

                # Only a break from the inner while loop due to Standalone or
                # In Sync will reach here.
                # Normal exit of the while loop reach the else statement
                # above which continues the outer loop
                break

            elif state == 'Sync Failure':
                Log.info('Cluster',
                "Device %s - Synchronization failed for %s"
                % (dev_name, name))
                Log.debug('Cluster', 'SYNC SECONDS (Sync Failure): ' + \
                            str(time.time() - sync_start_time))
                raise BigIPClusterSyncFailure(
                   'Device service group %s' % name + \
                   ' failed after ' + \
                   '%s attempts.' % const.MAX_SYNC_ATTEMPTS + \
                   ' Correct sync problem manually' + \
                   ' according to sol13946 on ' + \
                   ' support.f5.com.')
            else:
                attempts += 1
                Log.info('Cluster',
                "Device %s " % dev_name \
                + "Synchronizing config attempt %s to group %s:"
                % (attempts, name) \
                + " current state: %s" % state)
                self.sys_sync.synchronize_to_group_v2(name, dev_name, True)
                time.sleep(sleep_delay)
                sleep_delay += const.SYNC_DELAY
        else:
            if state == 'Disconnected':
                Log.debug('Cluster',
                          'SYNC SECONDS(Disconnected): ' + \
                              str(time.time() - sync_start_time))
                raise BigIPClusterSyncFailure(
                        'Device service group %s' % name + \
                        ' could not reach a sync state' + \
                        ' because they can not communicate' + \
                        ' over the sync network. Please' + \
                        ' check connectivity.')
            else:
                Log.debug('Cluster', 'SYNC SECONDS(Timeout): ' + \
                              str(time.time() - sync_start_time))
                raise BigIPClusterSyncFailure(
                    'Device service group %s' % name + \
                    ' could not reach a sync state after ' + \
                    '%s attempts.' % const.MAX_SYNC_ATTEMPTS + \
                    ' It is in %s state currently.' % state + \
                    ' Correct sync problem manually' + \
                    ' according to sol13946 on ' + \
                    ' support.f5.com.')

        Log.debug('Cluster', 'SYNC SECONDS(Success): ' + \
                      str(time.time() - sync_start_time))

    def sync_failover_dev_group_exists(self, name):
        dev_groups = map(os.path.basename, self.mgmt_dg.get_list())
        dev_group_types = self.mgmt_dg.get_type(dev_groups)

        try:
            index = dev_groups.index(name)
        except ValueError:
            return False

        if dev_group_types[index] == 'DGT_FAILOVER':
            return True

    def add_peer(self, name, mgmt_ip_address, username, password):
        if not self.peer_exists(name):
            if self.bigip.device.get_lock():
                local_device = self.bigip.device.get_device_name()
                local_mgmt_address = self.bigip.device.get_mgmt_addr()
                root_mgmt_dict = {
                                   'root_device_name': local_device,
                                   'root_device_mgmt_address':
                                                       local_mgmt_address
                                 }
                local_md = self.bigip.device.get_metadata()
                if 'root_device_name' in local_md.keys():
                    md_device_name = os.path.basename(
                                             local_md['root_device_name'])
                    if md_device_name:
                        if not md_device_name == local_device:
                            raise BigIPClusterPeerAddFailure('the device' \
                                     + ' used to peer %s ' % name \
                                     + ' was already itself peered from root' \
                                     + ' device: %s'
                                           % local_md['root_device_name'])
                self.bigip.device.update_metadata(root_mgmt_dict)
                Log.info('Cluster', 'Device %s - adding peer %s'
                                   % (local_device, name))
                self.mgmt_trust.add_authority_device(mgmt_ip_address,
                                                     username,
                                                     password,
                                                     name,
                                                     '', '',
                                                     '', '')
                attempts = 0
                while attempts < const.PEER_ADD_ATTEMPTS_MAX:
                    if self.get_sync_status() == "OFFLINE":
                        self.mgmt_trust.remove_device([name])
                        self.mgmt_trust.add_authority_device(mgmt_ip_address,
                                                             username,
                                                             password,
                                                             name,
                                                             '', '',
                                                             '', '')
                    else:
                        self.bigip.device.release_lock()
                        return
                    time.sleep(const.PEER_ADD_ATTEMPT_DELAY)
                    attempts += 1
                else:
                    raise BigIPClusterPeerAddFailure(
                    'Could not add peer device %s' % name +
                    ' as a trust for device %s'
                    % os.path.basename(self.mgmt_dev.get_local_device()) +
                    ' after % attempts' % const.PEER_ADD_ATTEMPTS_MAX
                    )
            else:
                raise BigIPDeviceLockAcquireFailed(
                    'Unable to obtain device lock for device %s'
                    % os.path.basename(self.mgmt_dev.get_local_device())
                    )

    def get_peer_addr(self, name):
        if self.peer_exists(name):
            return self.mgmt_dev.get_management_address([name])[0]

    def peer_exists(self, name):
        if name in map(os.path.basename, self.mgmt_dev.get_list()):
            return True
        else:
            return False

    def cluster_exists(self, name):
        request_url = self.bigip.icr_url + '/cm/device-group/~Common'
        request_url += '~' + name
        request_filter = '/?$select=name,type'
        request_url += request_filter
        response = self.bigip.icr_session.get(request_url, data=None)
        if response.status_code < 400:
            response_obj = json.loads(response.text)
            if response_obj['type'] == 'sync-failover':
                return True
            else:
                return False
        else:
            return False
        #self.bigip.system.set_folder('/Common')
        #return self.mgmt_dev.get_management_address(
        #                        [self.get_device_name()])[0]
        #self.bigip.system.set_folder('/')
        #dgs = self.mgmt_dg.get_list()
        #self.bigip.system.set_folder('/Common')
        #if name in map(os.path.basename, dgs):
        #    if 'DGT_FAILOVER' == self.mgmt_dg.get_type([name])[0]:
        #        return True
        #    else:
        #        return False
        #else:
        #    return False

    def create(self, name, autosync=True):
        if not self.cluster_exists(name):
            self.mgmt_dg.create([name],
                                ['DGT_FAILOVER'])
            self.mgmt_dg.set_network_failover_enabled_state(
                                                [name],
                                                ['STATE_ENABLED']
                                                )
            if autosync:
                self.mgmt_dg.set_autosync_enabled_state(
                                                [name],
                                                ['STATE_ENABLED']
                                                )
            else:
                self.mgmt_dg.set_autosync_enabled_state(
                                                [name],
                                                ['STATE_DISABLED']
                                                )
            return True
        else:
            return False

    def delete(self, name):
        if self.cluster_exists(name):
            self.mgmt_dg.delete_device_group([name])
            return True
        else:
            return False

    def devices(self, name):
        if self.cluster_exists(name):
            return map(os.path.basename,
                       self.mgmt_dg.get_device([name])[0])
        else:
            return []

    def add_devices(self, name, device_names):
        if not isinstance(device_names, list):
            device_names = [device_names]
        for i in range(len(device_names)):
            device_names[i] = self.bigip.add_folder('Common',
                                                     device_names[i])
        device_entry_seq = self.mgmt_dev.typefactory.create(
                                'Common.StringSequence')
        device_entry_seq.values = device_names
        device_entry_seq_seq = self.mgmt_dev.typefactory.create(
                                'Common.StringSequenceSequence')
        device_entry_seq_seq.values = [device_entry_seq]
        self.mgmt_dg.add_device([name],
                                device_entry_seq_seq)

    def remove_devices(self, name, device_names):
        if not isinstance(device_names, list):
            device_names = [device_names]
        for i in range(len(device_names)):
            device_names[i] = self.bigip.add_folder(
                                'Common', device_names[i])
        device_entry_seq = self.mgmt_dev.typefactory.create(
                                'Common.StringSequence')
        device_entry_seq.values = device_names
        device_entry_seq_seq = self.mgmt_dev.typefactory.create(
                                'Common.StringSequenceSequence')
        device_entry_seq_seq.values = [device_entry_seq]
        self.mgmt_dg.remove_device([name],
                                   device_entry_seq_seq)

    def remove_all_devices(self, name):
        self.mgmt_dg.remove_all_devices([name])

    def remove_device(self, name, device_name):
        existing_devices = self.devices(name)
        if not device_name in existing_devices:
            self.bigip.device.remove_from_device_group()

    def set_metadata(self, name, cluster_dict):
        if isinstance(cluster_dict, dict):
            str_comment = json.dumps(cluster_dict)
            self.mgmt_dg.set_description([name][str_comment])
        else:
            self.mgmt_dg.set_description([name],
                                      [cluster_dict])

    def get_metadata(self, name):
        str_comment = self.mgmt_dg.get_description([name])[0]
        try:
            return json.loads(str_comment)
        except:
            return None

    def remove_metadata(self, name, remove_dict):
        if isinstance(remove_dict, dict):
            str_comment = self.mgmt_dg.get_description(
                                    [name])[0]
            try:
                existing_dict = json.loads(str_comment)
                for key in remove_dict:
                    if key in existing_dict:
                        del(existing_dict[key])
                str_comment = json.dumps(existing_dict)
                self.mgmt_dg.set_description([name],
                                      [str_comment])
            except:
                self.mgmt_dev.set_description([name], [''])
        else:
            self.mgmt_dev.set_description([name], [''])

    def update_metadata(self, name, cluster_dict):
        if isinstance(cluster_dict, dict):
            str_comment = self.mgmt_dg.get_description(
                                    [name])[0]
            try:
                existing_dict = json.loads(str_comment)
            except:
                existing_dict = {}

            for key in cluster_dict:
                if not cluster_dict[key]:
                    if key in existing_dict:
                        del(existing_dict[key])
                else:
                    existing_dict[key] = cluster_dict[key]

            str_comment = json.dumps(existing_dict)
            self.mgmt_dg.set_description([name],
                                      [str_comment])

    def create_traffic_group(self, name):
        if isinstance(name, list):
            self.mgmt_tg.create(name)
        else:
            self.mgmt_tg.create([name])

    def delete_traffic_group(self, name):
        if isinstance(name, list):
            self.mgmt_tg.delete_traffic_group(name)
        else:
            self.mgmt_tg.delete_traffic_group([name])

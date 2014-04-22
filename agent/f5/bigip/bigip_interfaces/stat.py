##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

from f5.common import constants as const

import time


class Stat(object):
    def __init__(self, bigip):
        self.bigip = bigip

        # add iControl interfaces if they don't exist yet
        self.bigip.icontrol.add_interfaces(['System.SystemInfo',
                                            'System.Statistics'])

        # iControl helper objects
        self.sys_info = self.bigip.icontrol.System.SystemInfo
        self.sys_stat = self.bigip.icontrol.System.Statistics

    def get_composite_score(self):
        cpu_score = self.get_cpu_health_score() * \
                    const.DEVICE_HEALTH_SCORE_CPU_WEIGHT
        mem_score = self.get_mem_health_score() * \
                    const.DEVICE_HEALTH_SCORE_MEM_WEIGHT
        cps_score = self.get_cps_health_score() * \
                    const.DEVICE_HEALTH_SCORE_CPS_WEIGHT

        total_weight = const.DEVICE_HEALTH_SCORE_CPU_WEIGHT + \
                       const.DEVICE_HEALTH_SCORE_MEM_WEIGHT + \
                       const.DEVICE_HEALTH_SCORE_CPS_WEIGHT

        return int((cpu_score + mem_score + cps_score) / total_weight)

    # returns percentage of TMM memory currently in use
    def get_mem_health_score(self):
        # use TMM memory usage for memory health
        stat_type = self.sys_stat.typefactory.create(
                                    'Common.StatisticType')

        for stat in self.sys_stat.get_all_tmm_statistics(
                                    ['0.0']).statistics[0].statistics:
            if stat.type == stat_type.STATISTIC_MEMORY_TOTAL_BYTES:
                total_memory = float(self.bigip.ulong_to_int(stat.value))
            if stat.type == stat_type.STATISTIC_MEMORY_USED_BYTES:
                used_memory = float(self.bigip.ulong_to_int(stat.value))

        if total_memory and used_memory:
            score = int(100 * \
                    ((total_memory - used_memory) / total_memory))
            return score
        else:
            return 0

    def get_cpu_health_score(self):
        cpu_stats = self.sys_info.get_cpu_usage_information()
        used_cycles = 1
        idle_cycles = 1

        for cpus in cpu_stats.usages:
            used_cycles += self.bigip.ulong_to_int(cpus.user)
            used_cycles += self.bigip.ulong_to_int(cpus.system)
            idle_cycles = self.bigip.ulong_to_int(cpus.idle)

        score = int(100 - \
                (100 * (float(used_cycles) / float(idle_cycles))))
        return score

    def get_cps_health_score(self):
        count_init = self._get_tcp_accepted_count()
        time.sleep(const.DEVICE_HEALTH_SCORE_CPS_PERIOD)
        count_final = self._get_tcp_accepted_count()
        cps = (count_final - count_init) \
              / const.DEVICE_HEALTH_SCORE_CPS_PERIOD

        if cps >= const.DEVICE_HEALTH_SCORE_CPS_MAX:
            return 0
        else:
            score = int(100 - ((100 * float(cps)) \
            / float(const.DEVICE_HEALTH_SCORE_CPS_MAX)))
        return score

    def _get_tcp_accepted_count(self):
        stat_type = self.sys_stat.typefactory.create(
                                    'Common.StatisticType')

        for stat in self.sys_stat.get_tcp_statistics().statistics:
            if stat.type == stat_type.STATISTIC_TCP_ACCEPTED_CONNECTIONS:
                return self.bigip.ulong_to_int(stat.value)

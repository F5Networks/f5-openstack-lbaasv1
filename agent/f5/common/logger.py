##############################################################################
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright 2014 by F5 Networks and/or its suppliers. All rights reserved.
##############################################################################

import logging
import sys

from f5.common import constants as const


class Log(object):
    @staticmethod
    def debug(prefix, msg):
        Log._log('debug', prefix, msg)

    @staticmethod
    def error(prefix, msg):
        Log._log('error', prefix, msg)

    @staticmethod
    def crit(prefix, msg):
        Log._log('crit', prefix, msg)

    @staticmethod
    def info(prefix, msg):
        Log._log('info', prefix, msg)

    @staticmethod
    def _log(level, prefix, msg):
        log_string = prefix + ': ' + msg
        log = logging.getLogger(__name__)
        out_hdlr = logging.StreamHandler(sys.stdout)
        out_hdlr.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        log.addHandler(out_hdlr)

        if level == 'debug':
            log.debug(log_string)
        elif level == 'error':
            log.error(log_string)
        elif level == 'crit':
            log.critical(log_string)
        else:
            log.info(log_string)

        log.removeHandler(out_hdlr)

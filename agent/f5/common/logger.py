import logging
import sys

from common import constants as const
#from Insieme.Logger import Logger


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

        if const.LOG_MODE == 'dev':
            log = logging.getLogger(__name__)
            out_hdlr = logging.StreamHandler(sys.stdout)
            out_hdlr.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            out_hdlr.setLevel(const.LOG_LEVEL)
            log.addHandler(out_hdlr)
            log.setLevel(const.LOG_LEVEL)

            if level == 'debug':
                log.debug(log_string)
            elif level == 'error':
                log.error(log_string)
            elif level == 'crit':
                log.critical(log_string)
            else:
                log.info(log_string)

            log.removeHandler(out_hdlr)

            logging.getLogger('suds.client').setLevel(logging.DEBUG)
        #else:
        #    if level == 'debug':
        #        Logger.log(Logger.DEBUG, log_string)
        #    elif level == 'error':
        #        Logger.log(Logger.ERROR, log_string)
        #    elif level == 'crit':
        #        Logger.log(Logger.CRIT, log_string)
        #    else:
        #        Logger.log(Logger.INFO, log_string)

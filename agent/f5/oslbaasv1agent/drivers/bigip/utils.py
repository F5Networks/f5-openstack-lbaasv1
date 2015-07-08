""" Utility classes and functions """
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
try:
    from neutron.openstack.common import log as logging
except ImportError:
    from oslo_log import log as logging
from eventlet import greenthread
from time import time
import uuid

LOG = logging.getLogger(__name__)


def serialized(method_name):
    """Outer wrapper in order to specify method name"""
    def real_serialized(method):
        """Decorator to serialize calls to configure via iControl"""
        def wrapper(*args, **kwargs):
            """ Necessary wrapper """
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

            # num_requests = len(service_queue)

            # queue optimization

            # if num_requests > 1 and method_name == 'create_member':
            #    cur_pool_id = service['pool']['id']
                # cur_index = num_requests - 1
                #  do not attempt to replace the first entry (index 0)
                #  because it may already be in process.
                # while cur_index > 0:
                #    (check_request, check_method, check_service) = \
                #        service_queue[cur_index]
                #    if check_service['pool']['id'] != cur_pool_id:
                #        cur_index -= 1
                #        continue
                #    if check_method != 'create_member':
                #        break
                # move this request up in the queue and return
                # so that existing thread can handle it
                #    service_queue[cur_index] = \
                #        (check_request, check_method, service)
                #    return

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
            try:
                LOG.debug('%s request %s is running with queue depth: %d'
                          % (str(method_name), my_request_id,
                             len(service_queue)))
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


def request_index(request_queue, request_id):
    """ Get index of request in request queue """
    for request in request_queue:
        if request[0] == request_id:
            return request_queue.index(request)

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
from oslo import messaging
from neutron.common.rpc import get_client


class RpcProxy(object):
    '''
    This class is created to restore the class behavior of Icehouse
    and Juno RpcProxy so a single driver can be use for all releases.
    The original RpcProxy class has changed as oslo messaging was
    adopted. Kilo releases removed the RpcProxy class because the
    migration to oslo messaging was complete. This change broke
    backwards compatibility.
    '''
    RPC_API_NAMESPACE = None

    def __init__(self, topic, default_version, version_cap=None):
        super(RpcProxy, self).__init__()
        self.topic = topic
        target = messaging.Target(topic=topic, version=default_version)
        self._client = get_client(target, version_cap=version_cap)

    def make_msg(self, method, **kwargs):
        return {'method': method,
                'namespace': self.RPC_API_NAMESPACE,
                'args': kwargs}

    def call(self, context, msg, **kwargs):
        return self.__call_rpc_method(
            context, msg, rpc_method='call', **kwargs)

    def cast(self, context, msg, **kwargs):
        self.__call_rpc_method(context, msg, rpc_method='cast', **kwargs)

    def fanout_cast(self, context, msg, **kwargs):
        kwargs['fanout'] = True
        self.__call_rpc_method(context, msg, rpc_method='cast', **kwargs)

    def __call_rpc_method(self, context, msg, **kwargs):
        options = dict(
            ((opt, kwargs[opt])
             for opt in ('fanout', 'timeout', 'topic', 'version')
             if kwargs.get(opt))
        )
        if msg['namespace']:
            options['namespace'] = msg['namespace']

        if options:
            callee = self._client.prepare(**options)
        else:
            callee = self._client

        func = getattr(callee, kwargs['rpc_method'])
        return func(context, msg['method'], **msg['args'])


class RpcCallback(object):
    '''
    This class is created to restore the class behavior of Icehouse
    and Juno RpcCallback so a single driver can be use for all releases.
    The original RpcCallback class has changed as oslo messaging was
    adopted. Kilo releases removed the RpcProxy class because the
    migration to oslo messaging was complete. This change broke
    backwards compataibility.
    '''
    RPC_API_VERSION = '1.0'

    def __init__(self):
        super(RpcCallback, self).__init__()
        self.target = messaging.Target(version=self.RPC_API_VERSION)

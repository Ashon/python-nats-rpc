import os
import sys
sys.path.append(os.getcwd()) # noqa E402

from sanic import Sanic
from sanic.response import json

from nats_worker.core.driver import NatsDriver
from nats_worker.core.utils import get_module


class WorkerHttpProxy(object):
    conf = None
    app = None
    driver = None
    nats = None

    def __init__(self, settings):
        self.conf = settings

        _, serializer = get_module(self.conf.SERIALIZER_CLASS)
        self.driver = NatsDriver(
            urls=self.conf.NATS_URL.split(','),
            serializer=serializer)

        self.app = Sanic()
        self.app.listener('before_server_start')(self.setup)
        self.app.route('/<path:[^/].*?>', methods=['GET'])(self.resolve_message)

    async def setup(self, app, loop):
        """ Bind worker with sanic application eventloop
        """

        self.nats = await self.driver.get_connection(loop)

    def serialize_request_to_nats_message(self, request, path: str) -> (str, str):
        """Resolve path to nats topic, messages

        Request path convention
        - topic: {path.replace('/', '.'}.{method}.{param['_worker']}
        - message: GET params | POST body

        :Params
            - request: sanic request
            - path <str>: path of url

        :Returns
            <(str, str)>: tuple of topic, message
        """

        nats_route = '.'.join(item for item in (
            path.replace('/', '.'),
            request.method.lower(),
            request.args.get('_worker', '')
        ) if item)

        return (nats_route, request.args)

    async def resolve_message(self, request, path: str):
        (route, body) = self.serialize_request_to_nats_message(request, path)

        # data transport
        message = self.driver.serializer.serialize(body)
        response = await self.nats.request(route, message)

        return json({
            'route': route,
            'body': body,
            'response': response
        })

import asyncio
import time
import aiohttp
from aiohttp import web, BasicAuth
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from aiohttp_session import setup, get_session, SimpleCookieStorage
from .AioJsonSrv import AioJsonSrv
from .Wrapper import Wrapper
from .ObjectWrapper import ObjectWrapper
import ssl
import logging
import uuid

logger = logging.getLogger(__name__)


class AioRPCServ():
    '''The Server class which will serv up an object using RPC and
    WebSockets.'''

    def __init__(self, *, 
            class_to_instantiate=None,
            obj=None,
            timeout=5,
            watchdog_timeout=5,
            host_addr='0.0.0.0',
            port=8080,
            secure=True,
            cert='cert.pem',
            credentials

            ):
        '''
        Args:
            class_to_instantiate (class): the class of the object to instantiate
            timeout (int): The time after which an exception is raised if the
            method being served doesn't complete
            watchdog_timeout (int): the time in seconds after which the server 
            frees up the object being served to another client
            obj (object): The object to serve. Can use this or the class to
            instantiate
            host_addr (str): the address to serve on
            port (int): the port number to serve on
            cert (file_path): the path to the ssl certificate to use
        '''

        event_loop = asyncio.get_event_loop()

        if class_to_instantiate is not None:
            obj = Wrapper(cls=class_to_instantiate, cls_args=None, loop=event_loop,
                    timeout = timeout)
        if obj is None:
            raise Exception("Need a value for either class_to_instantiate or obj")
        else:
            obj = ObjectWrapper(obj=obj, loop=event_loop, timeout= timeout)
        self.json_srv = AioJsonSrv(obj=obj)

        self.host_addr = host_addr
        self.port = port
        self.secure = secure
        self.cert = cert
        self.watchdog_timeout = watchdog_timeout
        self.credentials = credentials


        self.event_loop = event_loop
        self.locked = False
        self.granted_sessions = {}
        asyncio.ensure_future(self.watch_dog(), loop=event_loop)
        self.end_time=None

    def kick_the_dog(self):
        self.end_time = self.event_loop.time()+self.watchdog_timeout

    async def get_access(self, request):
        session = await get_session(request)
        if self.locked:
            logger.debug("resource is already locked...")
            session['resource_granted']= 'False'
            message = 'Sorry resource is busy, try again in a while...'
        else:
            logger.debug("locking device..")
            self.locked = uuid.uuid4().hex
            session['authenticated'] = self.locked
            message = 'Resource granted'
            session['resource_granted'] = self.locked
            logger.debug("watchdog_timeout: {}".format(self.watchdog_timeout))
            logger.debug("event_loop.time: {}".format(self.event_loop.time()))
            self.kick_the_dog()
            logger.debug("end_time: {}".format(self.end_time))
        return web.Response(body=message.encode('utf-8'))

    async def watch_dog(self):
        '''used to remove the token after 10 seconds of inactivity'''
        while(True):
            #logger.debug("woof:end_time: {}".format(self.end_time))
            if self.end_time is not None:
                if self.event_loop.time() >= self.end_time:
                    logger.debug("event_loop.time(): {}".format(self.event_loop.time()))
                    logger.debug("end_time: {}".format(self.end_time))
                    #release the lock
                    logger.debug("releasing the lock due to timeout..")
                    self.locked = False
                    self.end_time = None
            #logger.debug(self.locked)
            await asyncio.sleep(1)


    async def root_handler(self, request):
        session = await get_session(request)
        last_visit = session.get('last_visit', 'Never')
        if last_visit == 'Never':
            message = "Welcome, I don't think you've visited here before."
        else:
            message = 'Welcome back, last visited: {} secs ago'.format(time.time() -
                    last_visit)
        session['last_visit'] = time.time()

        return web.Response(body=message.encode('utf-8'))

    async def ws_handler(self, request):

        session = await get_session(request)
        ws = web.WebSocketResponse()
        await ws.prepare(request)


        granted = session.get('resource_granted', None)
        logger.debug("granted: {} type(granted): {}".format(granted, type(granted)))

        _granted = False

        if granted is not None and granted == self.locked:
            _granted = True
            logger.debug("user is granted..")


        if not _granted:
            await ws.close()
            logger.debug("not granted...returning")
            return
            #await ws.close(code=999, message='Resource busy'.encode('utf-8'))
            #await ws.close(code=999, message='Resource busy'.encode('utf-8'))



        async for msg in ws:
            self.kick_the_dog()
            logger.debug("received msg: {}".format(msg.data))
            if self.locked == False:
                logger.debug('Timed Out waiting for client..')
                logger.debug('Attempting to reacquire lock')
                self.locked = granted
            elif self.locked != granted:
                logger.debug("somebody else now using the resource...goodbye")
                ws.close(code=999, message ='somebody else is now using resource due to timeout')
                return ws
            if msg.tp == aiohttp.MsgType.text:
                #if msg.data == 'close':
                #    await ws.close()
                #else:
                self.end_time = None #don't cause a timeout because of slowness on server side
                result_json, error = await self.json_srv.process_incoming(msg.data)
                ws.send_str(result_json)
            elif msg.tp == aiohttp.MsgType.error:
                logger.debug('ws connection closed with exception %s' % ws.exception())
            self.kick_the_dog()

        logger.debug("Unlocking device..")
        self.locked = False
        self.end_time = None
        logger.debug('websocket connection closed')

        return ws

    async def authenticate(self, request):
        session = await get_session(request)
        auth_request = request.headers.get('AUTHORIZATION', None)
        logger.debug('authentication: {}'.format(auth_request))
        if auth_request is not None:
            try:
                creds = BasicAuth.decode(auth_request)
                if creds.password == self.credentials.get(creds.login, ''):
                    logger.debug('Authenticated user: {}'.format(creds.login))
                    session['authenticated'] = 'True:{}'.format(creds.login)
                    return web.Response(body='logged in'.encode('utf-8'))
            except ValueError as e:
                pass
        return web.Response(body='login error'.encode('utf-8'))


    def run(self):
        event_loop = self.event_loop
        app = web.Application(loop=event_loop)
        #setup(app, SimpleCookieStorage())
        setup(app, EncryptedCookieStorage(b'Thirty  two  length  bytes  key.'))
        app.router.add_route('GET', '/', self.root_handler)
        if self.secure:
            path = '/wss'
        else:
            path = '/ws'
        app.router.add_route('GET', path, self.ws_handler)
        app.router.add_route('GET', '/get_access', self.get_access)
        app.router.add_route('GET', '/login', self.authenticate)
        if self.secure:
            print("Using ssl cert: {}".format(self.cert))
            sslcontext = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
            sslcontext.load_cert_chain(self.cert)
            web.run_app(app, host=self.host_addr, port=self.port, ssl_context=sslcontext)
        else:
            web.run_app(app, host=self.host_addr, port=self.port)

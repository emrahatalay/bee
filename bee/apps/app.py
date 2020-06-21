import sys
import logging
import datetime
import importlib
import asyncio as ai
import inspect
from pathlib import Path
from importlib import reload
import aioredis
from bee.core.utils import URLExpression, ConsoleToURLExpression
from bee.core.utils import MsgPackExpression
from bee.core.utils import JSONExpression
from bee.core.utils import Shortcuts, Action
from bee.core.utils import ModuleLoader
from bee.core.utils import BJSON
from bee.core.utils import Color
from bee.core.user import User

logging.basicConfig()

cpath = str(Path().absolute())
if cpath not in sys.path:
    sys.path.append(cpath)

import conf
try:
    import hooks
except Exception as e:
    pass


class App:
    def __init__(self, app_type, spath=None):
        self.app_type = app_type
        self.redis = None
        ai.gather(ai.async(self.setup_db()))
        ai.gather(ai.async(self.setup_redis()))
        ai.gather(ai.async(self.setup_internal_client()))
        self.conf = conf
        self.shortcuts = None
        self.spath = spath
        self.users = {}
        self.clients = set()
        self.debug = conf.APP_DEBUG
        self.uptime = datetime.datetime.now()
        self.tasks = []
        self.buff = ai.Queue()
        if spath:
            self.shortcuts = Shortcuts(self.spath)
        print(Color.g("- Starting {} application -".format(self.app_type)))

    def send(self, **kw):
        if self.app_type == "ws":
            if "_uid" in kw:
                uid = kw.pop("_uid")
                for cli, usr in self.users.items():
                    if usr.uid == uid:
                        cli.sendMessage(BJSON.encode(kw).encode("utf-8"), False)
                        break
    def bsend(self, **kw):
        if self.app_type == "ws":
            msg = BJSON.encode(kw).encode("utf-8")
            for cli, _ in self.users.items():
                cli.sendMessage(msg, False)

    def add_client(self, client):
        if client not in self.clients:
            self.clients.add(client)
        self.users[client] = User(self)

    def remove_client(self, client):
        if client in self.users:
            user = self.users[client]
            if user.is_authenticated:
                user.logout()
        if client in self.clients:
            self.clients.remove(client)

    def get_current_user(self, client):
        if client in self.users:
            return self.users[client]
        return None

    def publish(self, channel, **kw):
        ai.gather(ai.async(self._publish(channel, **kw)))

    async def _publish(self, channel, **kw):
        cname = "{}-{}".format(conf.REDIS_MPATTERN, channel)
        if "client" in kw and kw['client']:
            client = kw.pop("client")
            kw['_peer'] = client.peer
        await self.redis.publish(cname, BJSON.encode(kw))

    def set_init_params(self, params):
        self.init_params = params

    async def setup_internal_client(self):
        if hasattr(conf, "INTERNAL_CONNECTION") and conf.INTERNAL_CONNECTION:
            self.internal_reader, self.internal_writer = await ai.open_connection(
                conf.INTERNAL_CONNECTION_HOST, conf.INTERNAL_CONNECTION_PORT,
                loop=self.loop)
        else:
            self.internal_reader, self.internal_writer = (None, None)

    async def setup_redis(self):
        self.redis = await aioredis.create_redis_pool(
            (conf.REDIS_HOST, conf.REDIS_PORT),
            loop=self.loop,
            encoding="utf-8")
    async def setup_db(self):
        import gino
        from bee.models import db
        echo = conf.SA_ECHO
        if "--sa-debug=1" in self.init_params or "--sa-debug=0" in self.init_params:
            echo = True if "--sa-debug=1" in self.init_params else False
        if echo is False:
            logging.getLogger('sqlalchemy').setLevel(logging.ERROR)
        engine = await gino.create_engine(conf.SA_CONNECTION_STR, echo=echo)
        db.bind = engine
        if "--init-db" in self.init_params:
            for m in conf.APP_MODELS:
                if "." in m:
                    item = "models.{}".format(m.split(".")[0])
                    importlib.import_module(item)

            await db.gino.create_all()
        if "--exit" in self.init_params:
            await self.a_exit()
        self.db = db

    def start_services(self):
        self.start_listener()
        try:
            import services
        except Exception as e:
            print(Color.r(e))
        else:
            from inspect import getmembers, isfunction
            for t in [i for i in getmembers(services) if isfunction(i[1])]:
                self.tasks.append(self.loop.create_task(t[1](self)))

    def start_listener(self):
        self.tasks.append(self.loop.create_task(self.listener()))

    async def listener(self):
        if self.redis is None:
            print(Color.y("Waiting for (redis) connection..."))
            await ai.sleep(0.3)
            self.start_listener()
            return
        res = await self.redis.psubscribe("{}-*".format(conf.REDIS_MPATTERN))
        ch = res[0]
        while await ch.wait_message():
            try:
                craw, params = await ch.get_json()
            except Exception as e:
                print(e)
            else:
                cname = craw.decode("utf-8").replace(
                    "{}-".format(conf.REDIS_MPATTERN), "")
                f = "{}_message".format(self.app_type)
                try:
                    if hasattr(hooks, f):
                        await getattr(hooks, f)(self, cname, params=params)
                except Exception as e:
                    print(e)

    def kill_users(self):
        t = None
        for u in self.users:
            if u.ref == self:
                t = u
                break
        if t:
            t.logout()
            self.users.pop(t)
            from time import sleep
            sleep(4)

    def is_online(self, uid):
        return len([u for u in self.users.values() if u.uid == uid])

    async def a_exit(self):
        self.kill_users()
        for t in ai.Task.all_tasks():
            t.cancel()
        for t in self.tasks:
            t.cancel()
            try:
                await t
            except ai.CancelledError:
                pass
        self.loop.call_soon_threadsafe(self.loop.stop)

    def set_loop(self, loop):
        self.loop = loop

    def internal_cmd(self, cmd):
        if cmd in ["@reload_shortcuts", "@rl"]:
            self.shortcuts = Shortcuts(self.spath)
            print(Color.g("--ok--"))
        if cmd in ["@exit", "@€xit", "@e"]:
            print(Color.r("bye..."))
            ai.gather(ai.async(self.a_exit()))
        if cmd in ["@clear", "@clr", "@c"]:
            import os
            os.system('clear')
        if cmd == "@cdebug":
            self.debug = not self.debug
            print(Color.g("--debug: {}--".format(self.debug)))
        if cmd in ["@date", "@dt"]:
            print(Color.g(datetime.datetime.now()))
        if cmd in ["@uptime", "@up"]:
            print(Color.g("{} ago.".format(
                str(datetime.datetime.now()-self.uptime))))
        if cmd in ["@reload_conf", "@rc"]:
            try:
                reload(conf)
            except Exception as e:
                print(Color.r(e))
            else:
                self.conf = conf
                print(Color.g("--ok--"))

        if cmd.startswith("@cmdtocsv"):
            import csv
            import io
            path = cmd.split("@cmdtocsv")[1].strip()
            if not path.startswith("run/"):
                path = "run/{}".format(path)
            if not path.endswith(".cmd"):
                path = "{}.cmd".format(path)
            keys = []
            values = []
            for cmdx in open(path, 'r').readlines():
                cmd = cmdx.strip()
                if len(cmd) > 0:
                    line = self.cmd_to_csv(cmd)
                    if cmd:
                        if len(keys) == 0:
                            keys = list(line.keys())
                        values.append(list(line.values()))
            output = io.StringIO()
            writer = csv.writer(output)
            if keys:
                writer.writerow(keys)
            if values:
                writer.writerows(values)
            print(output.getvalue())

        if cmd.startswith("@run"):
            path = cmd.split("@run")[1].strip()
            if not path.startswith("run/"):
                path = "run/{}".format(path)
            if not path.endswith(".cmd"):
                path = "{}.cmd".format(path)
            try:
                for cmdx in open(path, 'r').readlines():
                    cmd = cmdx.strip()
                    if len(cmd) > 0:
                        if cmd.startswith("@run"):
                            pathx = "run/{}.cmd".format(
                                cmd.split("@run")[1].strip())

                            for ncmdx in open(pathx, 'r').readlines():
                                ncmd = ncmdx.strip()
                                if len(ncmd) > 0:
                                    if ncmd.startswith("@run"):
                                        print("We can't allow recursion!")
                                    else:
                                        print("+"*20, "-{}-".format(pathx))
                                        self.console_action(ncmd)
                                        print("-"*20)
                        else:
                            print("+"*20)
                            self.console_action(cmd)
                            print("-"*20)
            except Exception as e:
                print(Color.r(e))

        if cmd in ["@?"]:
            print(Color.g("@reload_shortcuts (@rl) : Reload shortcuts yaml"))
            print(Color.g("@exit (@e) : Exit"))
            print(Color.g("@clear (@c) : Clear screen"))
            print(Color.g("@cdebug : Switch debug"))
            print(Color.g("@date (@dt) : Print datetime"))
            print(Color.g("@uptime (@up) : Print app up and running time"))
            print(Color.g("@reload_conf (@rc) : Reload app config from conf.py"))
            print(Color.g("@run : Run any command file, under run/"))
            print(Color.y("Getting help"))
            print(Color.g("module.klass.function _help=1"))
            print(Color.y("Reloading action"))
            print(Color.g("module.klass.function _reload=1"))
            print(Color.y("Parameter(s) syntax"))
            print(Color.g("param='b+ True' param=True, [,b+] True,False,True"))
            print(Color.g("param='d+ 1.3' param=Decimal(1.3), [,d+] 1.2,1.4,0.7"))
            print(Color.g("param='f+ 1.4' param=float(1.4), [|f+] 1.4|1.5|1.7"))
            print(Color.g(("param='dt+ 17/11/2018 17:49:33' "
                           "param=datetime(2018, 11, 17, 17, 49, 33), "
                           "[|dt+] 17/11/2018 17:49:33|18/11/2018 17:49:33")))
            print(Color.g(("param='date+ 17/11/2018' param=date(2018, 11, 17)"
                           "[,date+] 17/11/2018,18/11/2018")))
            print(Color.g("param='i+ 3' param=int(3) [,i+] 3,4,5"))
            print(Color.g("param='s+ hello' param=str(hello) [,s+] a,b,c"))

    def _action(self, ue):
        if "_m" not in ue.data and "_f" in ue.data and self.shortcuts:
            short = self.shortcuts.apply(ue.data['_f'])
            if short and type(short) is dict:
                nshort = dict(short)
                ue.data.pop("_f")
                nshort.update(ue.data)
                return Action(nshort)
        else:
            return Action(ue.data)

    def cmd_to_csv(self, cmd):
        if cmd.startswith("@"):
            return
        try:
            ue = URLExpression(ConsoleToURLExpression(cmd).url)
        except Exception as e:
            print(Color.r(e, b=True))
        else:
            return ue.data['data']

    async def web_action(self, web, request):
        try:
            url = str(request.rel_url)
            if url.startswith("/"):
                url = url[1:]
            url = url.replace("/", ".")
            if url.count(".") != 2:
                return web.json_response({'error': 'invalid-request'})
            ue = URLExpression(url)
            action = self._action(ue)
        except Exception as e:
            print(Color.r(e, b=True))
            return web.json_response({'error 2': str(e)})
        else:
            if action:
                try:
                    ml = ModuleLoader("apps.web.actions", debug=self.debug)
                    mod = ml.load(action.m)
                    if mod is None:
                        return web.json_response({'error': 'unknown-mod'})
                    else:
                        return await self.web_execute(mod, action, request, web)
                except Exception as e:
                    return web.json_response({'error 3': str(e)})
            else:
                return web.json_response({'error', 'Unknown action!'})

    def console_action(self, cmd):
        if cmd.startswith("@"):
            self.internal_cmd(cmd.strip())
            return
        try:
            ue = URLExpression(ConsoleToURLExpression(cmd).url)
            action = self._action(ue)
        except Exception as e:
            print(Color.r(e, b=True))
        else:
            if action:
                ml = ModuleLoader("apps.console.actions", debug=self.debug)
                mod = ml.load(action.m)
                self.execute(mod, action)
            else:
                self.publish("error", "Unknown action")

    def b_ws_action(self, client, cmd):
        try:
            rcmd = MsgPackExpression(cmd)
        except Exception as e:
            print(Color.r(e, b=True))
        else:
            tcmds = []
            if type(rcmd.data) is not dict:
                for t in rcmd.data:
                    tcmds.append({data: t})
            else:
                tcmds = [rcmd]

            for cmd in tcmds:
                try:
                    action = self._action(cmd)
                    if action:
                        ml = ModuleLoader("apps.ws.actions", debug=self.debug)
                        mod = ml.load(action.m)
                        self.execute(mod, action, client=client)
                    else:
                        self.publish("error", "Unknown action", client=client)
                except Exception as e:
                    print(cmd, Color.r(e, b=True))

    def ws_action(self, client, cmd):
        try:
            rcmd = JSONExpression(cmd)
        except Exception as e:
            print(Color.r(e, b=True))
        else:
            tcmds = []
            if type(rcmd.data) is not dict:
                for t in rcmd.data:
                    temp = JSONExpression("{}")
                    temp.data = t
                    tcmds.append(temp)
            else:
                tcmds = [rcmd]

            for cmd in tcmds:
                try:
                    action = self._action(cmd)
                    if action:
                        ml = ModuleLoader("apps.ws.actions", debug=self.debug)
                        mod = ml.load(action.m)
                        self.execute(mod, action, client=client)
                    else:
                        self.publish("error", "Unknown action", client=client)
                except Exception as e:
                    print(cmd, Color.r(e, b=True))


    async def web_execute(self, mod, action, request, web):
        if mod is None:
            return web.json_response({
                'status': 500,
                'desc': "Module not found, action-> {}".format(action)})
        if action.ready is False:
            return web.json_response({
                'status': 500,
                'desc': "Action isn't ready!"})

        perm = True
        """
        perm = user.check_permission(action) or self.app_type == "console"
        if perm is False:
            self.publish("error", desc="Permission denied!",
                         detail="{}.{}.{}".format(action.m, action.c, action.f), client=client)
        """
        if action.ready:
            if action.reload_module:
                mod = reload(mod)
            try:
                klass = getattr(mod, action.c)
            except Exception as e:
                return web.json_response({'status': 500, 'desc': str(e)})

            if "_help" in action.data or "_h" in action.data:
                try:
                    ht = inspect.getdoc(getattr(klass, action.f))
                    if ht:
                        return web.json_response({'help': ht})
                    else:
                        return web.json_response({'help': 'Missing doc.'})
                    return
                except:
                    pass
            inst = klass(self)
            try:
                return await getattr(inst, action.f)(request, web, **action.data)
            except Exception as e:
                raise e
                return web.json_response({'status': 500, 'desc': str(e)})

    def execute(self, mod, action, client=None):
        if mod is None:
            self.publish(
                "error",
                desc="Module not found, action-> {}".format(action),
                client=client)
            return
        if action.ready is False:
            self.publish("error", desc="Action isn't ready!", client=client)

        if client in self.users:
            user = self.users[client]
        else:
            user = User(self)

        perm = user.check_permission(action) or self.app_type == "console"
        if perm is False:
            self.publish(
                "error",
                desc="Permission denied!",
                detail="{}.{}.{}".format(action.m, action.c, action.f),
                client=client)
        if action.ready and perm:
            if action.reload_module:
                self.publish(
                    "info",
                    desc="Reloading {}".format(mod),
                    client=client)
                mod = reload(mod)
            try:
                klass = getattr(mod, action.c)
            except Exception as e:
                self.publish("exp", desc=str(e), client=client)
                return
            if "_help" in action.data or "_h" in action.data:
                try:
                    ht = inspect.getdoc(getattr(klass, action.f))
                    if ht:
                        print(Color.g(ht))
                    else:
                        print(Color.y("Missing doc."))
                    return
                except:
                    pass
            if action.static:
                if hasattr(klass, action.f):
                    try:
                        getattr(klass, action.f)(self, **action.data)
                    except Exception as e:
                        self.publish("exp", desc=str(e), client=client)
            else:
                if action.sync:
                    try:
                        inst = klass(self, client=client)
                        if hasattr(inst, action.f):
                            getattr(inst, action.f)(**action.data)
                    except Exception as e:
                        self.publish("exp", desc=str(e), client=client)
                else:
                    inst = klass(self, client=client)
                    try:
                        ai.gather(ai.async(
                            getattr(inst, action.f)(**action.data)))
                    except Exception as e:
                        self.publish("exp", desc=str(e), client=client)

    def url_action(self, url):
        ue = URLExpression(url)
        self.action = self._action(ue)

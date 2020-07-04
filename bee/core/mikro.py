import asyncio as ai
import sys
import uvloop
import aioredis
ai.set_event_loop_policy(uvloop.EventLoopPolicy())

from pathlib import Path
cpath = str(Path().absolute())
if cpath not in sys.path:
    sys.path.append(cpath)

import conf

class Mikro:
    def __init__(self):
        self.redis = None
        self.loop = ai.get_event_loop()
        self.running = False
        if hasattr(self, "db_on"):
            ai.gather(ai.async(self.setup_db()))
        if hasattr(self, "redis_on"):
            ai.gather(ai.async(self.setup_redis()))

    def setup(self, *a, **k):
        pass

    async def clean(self):
        pass

    async def async_setup(self, *a, **k):
        pass

    async def check_status(self):
        await self.sleep(1)

    async def setup_db(self):
        import gino
        from bee.models import db
        engine = await gino.create_engine(conf.SA_CONNECTION_STR, echo=conf.SA_ECHO)
        db.bind = engine
        self.db = db

    async def setup_redis(self):
        self.redis = await aioredis.create_redis_pool(
            (conf.REDIS_HOST, conf.REDIS_PORT),
            loop=self.loop,
            encoding="utf-8")

    def start(self):
        self.running = True
        tasks = ai.async(self.async_setup())
        self.loop.run_until_complete(tasks)
        ai.gather(ai.async(self.check_status()))
        tasks = ai.gather(ai.async(self.process()))
        try:
            self.loop.run_until_complete(tasks)
        except KeyboardInterrupt:
            ctasks = ai.gather(ai.async(self.clean()))
            self.loop.run_until_complete(ctasks)
            tasks.cancel()
            self.loop.run_forever()
            self.loop.close()
            tasks.exception()
        finally:
            self.loop.close()

    @staticmethod
    def get_tasks():
        fns = [t for t in ai.Task.all_tasks() if t._state == "FINISHED"]
        for t in fns:
            ai.Task._all_tasks.remove(t)
        return ai.Task.all_tasks()

    def apply_tasks(self, items, **kwargs):
        return ai.wait(
            [self.loop.create_task(item) for item in items], **kwargs)

    async def gather(self, item):
        return ai.gather(self.loop.create_task(item))

    async def sleep(self, time):
        await ai.sleep(time)

    async def process(self):
        while self.running:
            await self.update()

    async def update(self):
        pass

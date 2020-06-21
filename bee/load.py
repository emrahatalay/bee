#!/usr/bin/env python

import asyncio
import sys
import uvloop
import importlib
import gzip
import json
from bee.models import db
from datetime import datetime

from colorama import init
init(autoreset=True)

from pathlib import Path
cpath = str(Path().absolute())
if cpath not in sys.path:
    sys.path.append(cpath)

from bee.core.utils import Color
import conf

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
loop = asyncio.get_event_loop()

async def main():
    if len(sys.argv) < 3:
        print(Color.r("Missing required parameters! (Define model and json file path)"))
        return
    name = sys.argv[1]
    path = sys.argv[2]
    is_rom = True if "--rom" in str.join(" ", sys.argv) else False
    model = None

    try:
        if name not in conf.APP_MODELS:
            print(Color.r("Unknown model! (checkout -> conf.APP_MODELS)"))
            return
        item = "models.{}".format(name.split(".")[0])
        a = importlib.import_module(item)
        model = getattr(a, name.split(".")[1])
    except Exception as e:
        print(Color.r(e))
        return

    try:
        if path.endswith(".gz"):
            with gzip.open(path) as f:
                data = json.load(f)
        else:
            with open(path) as f:
                data = json.load(f)
    except Exception as e:
        print(Color.r(e))
        return

    if data and model:
        start = datetime.now()
        engine = await db.set_bind(conf.SA_CONNECTION_STR)
        print(Color.y("Started: {}".format(start)))
        if is_rom:
            for d in data:
                item = model(**d)
                item.save()
        else:
            await model.insert().gino.all(*data)

        end = datetime.now()
        print(Color.y("Ended: {}, Duration: {}".format(end, end - start)))
    else:
        print(Color.r("Unable to load data or model"))
    return True



try:
    loop.run_until_complete(main())
except Exception as e:
    print(e)
finally:
    loop.close()

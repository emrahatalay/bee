#!/usr/bin/env python
import redis
import sys
from six import moves
from bee.core.utils import URLExpression, ConsoleToURLExpression, BJSON

from pathlib import Path
cpath = str(Path().absolute())
if cpath not in sys.path:
    sys.path.append(cpath)

from conf import REDIS_HOST, REDIS_PORT, REDIS_MPATTERN

q = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)

def main():
    if len(sys.argv) > 1:
        cmd = str.join(" ", sys.argv[1:])
        ue = URLExpression(ConsoleToURLExpression(cmd).url)
        if "_f" in ue.data and len(ue.data['data'].keys()) > 0:
            try:
                q.publish("{}-{}".format(REDIS_MPATTERN, ue.data['_f']),
                          BJSON.encode(ue.data['data']))
            except Exception as e:
                raise e

#!/usr/bin/env python
import asyncio
import sys
import uvloop
from colorama import init
init(autoreset=True)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
loop = asyncio.get_event_loop()

from .apps.app import App
app = App(app_type="console", spath='apps/console/shortcuts.yaml')
app.set_loop(loop)
app.start_services()
app.set_init_params(sys.argv)

class Console(asyncio.Protocol):
    def data_received(self, data):
        app.console_action(data.decode())

def main():
    try:
        stdin_pipe_reader = loop.connect_read_pipe(Console, sys.stdin)
        loop.run_until_complete(stdin_pipe_reader)
        loop.run_forever()
    except KeyboardInterrupt:
        app.kill_users()
    finally:
        loop.close()

if __name__ == "__main__":
    main()

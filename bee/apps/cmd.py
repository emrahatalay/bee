import inspect
from bee.core.utils import BJSON


class Cmd:
    def __init__(self, app, client=None):
        self.app = app
        self.db = self.app.db
        self.client = client

    def send(self, **kw):
        if self.app.app_type == "ws":
            if "_uid" in kw:
                uid = kw.pop("_uid")
                for cli, usr in self.app.users.items():
                    if usr.uid == uid:
                        cli.sendMessage(BJSON.encode(kw).encode("utf-8"), False)
                        break
            elif self.client:
                self.client.sendMessage(BJSON.encode(kw).encode("utf-8"), False)

    @staticmethod
    def get_param_or_none(items, item):
        if item in items:
            item = items.pop(item)
        else:
            item = None
        return (items, item)

    async def help(self, **kw):
        print("#"*30)
        name = "{}.{}".format(
            self.__module__.split("actions.")[1],
            self.__class__.__name__)
        for k, _ in inspect.getmembers(self, predicate=inspect.iscoroutinefunction):
            if "f" in kw:
                if kw['f'] != k:
                    continue
            if k != "help":
                if hasattr(self, "exclude_from_help"):
                    if k in getattr(self, "exclude_from_help"):
                        continue

                print("{}.{}".format(name, k))
                if "detail" in kw:
                    doc = getattr(self, k).__doc__
                    if doc:
                        print(doc)
                print("#"*30)

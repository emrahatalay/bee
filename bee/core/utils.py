import re
import yaml
import json
import enum
from datetime import datetime, date, time
from decimal import Decimal
from sqlalchemy import inspect
import inspect as ins
from termcolor import colored
from terminaltables import AsciiTable
import msgpack

class ModuleLoader:
    def __init__(self, moddir, debug=False):
        self.dir = moddir
        self.debug = debug

    def find_all(self, ex_mod=[], exclude=[]):
        from bee.apps.cmd import Cmd
        import os
        mods = []
        for _, _, fx in os.walk(self.dir.replace(".", "/")):
            for f in fx:
                if not f.startswith("_") and "#" not in f and "~" not in f and f.endswith(".py"):
                    mods.append(f.replace(".py", ""))
        perms = []
        for m in mods:
            if m in ex_mod:
                continue
            module = self.load(m)
            for n, kls in ins.getmembers(module):
                if ins.isclass(kls) and issubclass(kls, Cmd):
                    for nx, f in ins.getmembers(kls):
                        if ins.iscoroutinefunction(f) and nx not in exclude:
                            perms.append({'doc': ins.getdoc(f), 'module': m,
                                          'klass': n, 'function': nx})

        return perms


    def load(self, m):
        try:
            path = "{}.{}".format(self.dir, m)
            if self.debug:
                print("Call: ModuleLoader.load({} -> {})".format(m, path))
            mx = __import__(path)
            if "." in path:
                for i in path.split(".")[1:]:
                    mx = getattr(mx, i)
                mod = mx
            else:
                mod = getattr(mx, m)
        except Exception as e:
            print(Color.r("Exception: ModuleLoader.load({}): {}".format(m, e)))
            return None
        else:
            if self.debug:
                print("Success: ModuleLoader.load({})".format(m))
            return mod

class Action:
    def __init__(self, data):
        self.m = None
        self.c = None
        self.f = None
        self.data = None
        self.sync = False
        self.static = False
        self.reload_module = False
        self.dotchecker = re.compile(r'\.{2,}')
        self.ready = False
        self.parse(data)
    @classmethod
    def check_start(cls, item, hook="."):
        if item.startswith(hook):
            return item[1:]
        return item
    @classmethod
    def check_end(cls, item, hook="."):
        if item.endswith(hook):
            return item[:-1]
        return item
    @classmethod
    def check_all(cls, item, hook="."):
        item = cls.check_start(item, hook=hook)
        return cls.check_end(item, hook=hook)
    def parse(self, data):
        if "_m" in data and "_c" in data and "_f" in data:
            self.m = self.check_all(self.dotchecker.sub(".", data.pop("_m")))
            self.c = data.pop("_c")
            self.f = data.pop("_f")
            if "_st" in data["data"]:
                data['data'].pop("_st")
                self.static = True
            if "_sc" in data["data"]:
                data['data'].pop("_sc")
                self.sync = True
            if "_reload" in data["data"]:
                data['data'].pop("_reload")
                self.reload_module = True
            self.data = data.get("data", {})
            self.ready = True
        else:
            raise ValueError("Missing required parameters!")

    def __str__(self):
        return "Mod: {}, Cls: {}, Func: {}, Static: {}, Sync: {}, Params: {}".format(
            self.m, self.c, self.f, self.static, self.sync, self.data)

class Shortcuts:
    def __init__(self, path):
        try:
            self.shortcuts = yaml.safe_load(open(path))
        except Exception as e:
            print(e)
            self.ready = False
        else:
            self.ready = True

    def apply(self, f):
        if self.ready and f in self.shortcuts:
            return self.shortcuts.get(f)
        return f

class CustomCast:
    '''
        Usage: CustomCast.cast(str)
        b+ bool
        d+ Decimal
        f+ float
        dt+ datetime (d/m/Y H:M:S)
        date+ date(d/m/Y)
        i+ int
    '''
    aliases = {'b+': ['bool+'],
               'd+': ['decimal+', 'dec+'],
               'f+': ['float+'],
               'dt+': ['datetime+'],
               'date+': [],
               'i+': ['int+'],
               's+': ['str+']}

    @classmethod
    def clear(cls, value):
        for k in cls.aliases.keys():
            if value.startswith(k):
                return value.split(k)[1].strip()
        return value
    @classmethod
    def do(cls, value):
        cmap = {'b+': bool, 'd+': Decimal, 'f+': float,
                'dt+': lambda n: datetime.strptime(n, "%d/%m/%Y %H:%M:%S"),
                'date+': lambda n: datetime.strptime(n, "%d/%m/%Y").date(),
                'i+': int, 's+': str}

        for k, v in cmap.items():
            if k == 'b+':
                continue
            temp = "{} ".format(k)
            if value.startswith(temp) or any([True if k.startswith("{} ".format(k)) else False for k in cls.aliases[temp.strip()]]):
                try:
                    value = v(value.split(temp)[1])
                except Exception as e:
                    raise e
                else:
                    return value
        try:
            if value in ["True", "true", "b+ true", "b+ True"]:
                return True
            if value in ["False", "false", "b+ false", "b+ False"]:
                return False
        except Exception as e:
            raise e
        return value

    @classmethod
    def cast(cls, value):
        match = re.search(r"\[(\||,)(b\+|d\+|f\+|dt\+|date\+|i\+|s\+)\](.*)", value, re.MULTILINE | re.VERBOSE)
        if match:
            try:
                sep = match.group(1)
                itype = match.group(2)
                val = match.group(3)
                return [cls.do("{} {}".format(
                    itype.strip(), t.strip())) for t in val.split(sep)]
            except Exception as e:
                print(Color.r(e))
                return value
        else:
            return cls.do(value)

class URLExpression:
    def __init__(self, exp):
        self.parse(exp)
    def parse(self, exp):
        from urllib.parse import urlparse
        try:
            item = urlparse(exp)
            path = item.path.split(".")
            params = {}
            for i in item.query.split("&"):
                if "=" in i:
                    k, v = i.split("=")
                    v = CustomCast.cast(v)
                    params.update({k: v})
            self.data = {'data': params}
            if path:
                _f = path.pop(-1)
                self.data.update({'_f': _f})
            if path:
                _c = path.pop(-1)
                self.data.update({'_c': _c})
            if path:
                _m = str.join(".", path)
                self.data.update({'_m': _m})
        except Exception as e:
            raise e
    def __str__(self):
        return str.join(", ", ["{}={}".format(k, v) for k, v in self.data.items()])

class ConsoleToURLExpression:
    def __init__(self, exp):
        self.url = None
        self.parse(exp)

    def parse(self, exp):
        import shlex
        try:
            params = shlex.split(exp)
            cmd = params.pop(0).replace("/", ".")
            self.url = "{}?{}".format(cmd, str.join("&", params))
        except Exception as e:
            raise e

class JSONExpression:
    def __init__(self, exp):
        self.parse(exp)

    def parse(self, exp):
        self.data = BJSON.decode(exp)


class MsgPackExpression:
    def __init__(self, exp):
        self.parse(exp)
    def parse(self, exp):
        self.data = msgpack.unpackb(exp, encoding="utf-8")

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "_columns"):
            columns = obj._columns
            d = {}
            rh = obj._repr_hide if hasattr(obj, "_repr_hide") else []
            for k in columns.keys():
                if k in rh:
                    continue
                d[k] = getattr(obj, k)
            return d

        if hasattr(obj, '__table__'):
            columns = obj.__table__.columns
            d = {}
            for c in columns:
                if hasattr(c, "info"):
                    if "sensitive" in c.info and c.info['sensitive']:
                        continue
                fld = str(c).split('.')[1]
                v = getattr(obj, fld)
                d[fld] = v
            return d
        if isinstance(obj, enum.Enum):
            return "{}".format(obj.name)
        if isinstance(obj, complex):
            return [obj.real, obj.imag]
        if isinstance(obj, datetime) or isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, time):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

class BJSON:
    @classmethod
    def encode(cls, data):
        try:
            return json.dumps(data, cls=CustomJSONEncoder)
        except Exception as e:
            raise e

    @classmethod
    def decode(cls, data):
        try:
            return json.loads(data)
        except Exception as e:
            raise e

class Inspect:
    def __init__(self, item):
        self.mapper = inspect(item)
        self.cols = sorted([i.name for i in self.mapper.columns])
        import conf
        if hasattr(conf, "TABLE_HEADING_PRE_ORDER"):
            for k, i in enumerate(conf.TABLE_HEADING_PRE_ORDER):
                if i in self.cols:
                    self.cols.remove(i)
                    self.cols.insert(k, i)

        if hasattr(conf, "TABLE_HEADING_POST_ORDER"):
            for i in conf.TABLE_HEADING_POST_ORDER:
                if i in self.cols:
                    self.cols.remove(i)
                    self.cols.append(i)

    def get_rows(self):
        return [self.cols]

    def get_cols(self, c=None, ex=[], rename={}):
        if c and type(c) is list:
            self.cols = [cx if cx not in rename else rename[cx] for cx in c if cx in self.cols or cx in ex]
            return self.cols
        if ex:
            for e in ex:
                if e in rename:
                    self.cols.append(rename[e])
                else:
                    self.cols.append(e)
        return self.cols

class Color:
    @classmethod
    def _color(cls, msg, color, b=False, u=False):
        props = []
        if b:
            props.append("bold")
        if u:
            props.append("underline")
        return colored(msg, color, None, props)
    @classmethod
    def r(cls, msg, b=False, u=False):
        return cls._color(msg, "red", b=b, u=u)
    @classmethod
    def g(cls, msg, b=False, u=False):
        return cls._color(msg, "green", b=b, u=u)
    @classmethod
    def y(cls, msg, b=False, u=False):
        return cls._color(msg, "yellow", b=b, u=u)
    @classmethod
    def b(cls, msg, b=False, u=False):
        return cls._color(msg, "blue", b=b, u=u)
    @classmethod
    def m(cls, msg, b=False, u=False):
        return cls._color(msg, "magenta", b=b, u=u)
    @classmethod
    def c(cls, msg, b=False, u=False):
        return cls._color(msg, "cyan", b=b, u=u)

class Table:
    def __init__(self, rows):
        self.table = AsciiTable(rows)
    def __repr__(self):
        return Color.b(self.table.table)

class Core:
    @classmethod
    def usort(cls, items, skey, rev=False):
        import icu
        collator = icu.Collator.createInstance(icu.Locale("TR"))
        return sorted(items, key=lambda x: collator.getSortKey(getattr(x, skey)), reverse=rev)

    @classmethod
    def isort(cls, items, skey, rev=False):
        return sorted(items, key=lambda x: int(getattr(x, skey)), reverse=rev)

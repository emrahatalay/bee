from datetime import datetime
import re

class User:
    def __init__(self, ref):
        self.ref = ref
        self.uid = None
        self.is_authenticated = False
        self.entered = None
        self.ip = None
        self.app_type = None
        self.user = None
        self.perms = []
        self.params = []
    def __repr__(self):
        return "<User: uid: {}, is_authenticated: {}, entered: {}, ip: {}, app_type: {}, user: {}>".format(self.uid, self.is_authenticated, self.entered, self.ip, self.app_type, self.user)

    def get_param(self, parametre):
        try:
            return self.params[parametre]
        except Exception as e:
            print(e)
        return None

    def login(self, uid, ip, app_type, user, perms=[], params=[], agent=None):
        self.is_authenticated = True
        self.uid = uid
        self.entered = datetime.now()
        self.ip = ip
        self.app_type = app_type
        self.user = user
        self.perms = perms
        self.params = params

    def check_session(self):
        pass

    def logout(self):
        if self.is_authenticated:
            signal = self.user.event_dict("offline")
            self.ref.publish("orm", **signal)
        self.is_authenticated = False
        self.uid = None
        self.entered = None
        self.ip = None
        self.app_type = None
        self.user = None
        self.perms = []

    @classmethod
    def _check_per(cls, perms, action):
        for fa in perms:
            scheck = []
            if "m" in fa and fa["m"]:
                scheck.append(fa["m"] == action.m)
            if "c" in fa and fa["c"]:
                scheck.append(fa["c"] == action.c)
            if "f" in fa and fa["f"]:
                scheck.append(fa["f"] == action.f)
            if "params" in fa and fa['params']:
                for k, v in fa['params'].items():
                    if k in action.data and action.data.get(k):
                        scheck.append(True if re.match(v, str(action.data.get(k))) else False)
                    else:
                        scheck.append(False)
            if all(scheck):
                return True
        return None

    def check_permission(self, action):
        if hasattr(self.ref.conf, "FREE_ACTIONS"):
            p1 = self._check_per(self.ref.conf.FREE_ACTIONS, action)
            if p1:
                return p1
        p2 = self._check_per(self.perms, action)
        if p2:
            return p2

        if self.user:
            if self.user.is_active is False:
                return False
            if self.user.is_admin:
                return True
        return False

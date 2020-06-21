class Hook:
    def __init__(self, app, cname, params):
        self.app = app
        self.cname = cname
        self.params = params['params']

    async def process(self):
        pass




class Arbiter(object):
    """Arbiter maintains the workers processes alive.
    It launches, reloads or kills them if needed.
    """
    def __init__(self, app, conf=None):
        self.app = app
        self.conf = conf

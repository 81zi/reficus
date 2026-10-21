import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def P(pane_id):
    return {"type": "pane", "pane_id": pane_id}


def S(direction, first, second, ratio=0.5):
    return {"type": "split", "direction": direction, "ratio": ratio, "first": first, "second": second}


class TempEnv(unittest.TestCase):
    """Points every config/state path at a fresh temp dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self._env = dict(os.environ)
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self.root, "xdg")
        os.environ["HERDR_PLUGIN_CONFIG_DIR"] = os.path.join(self.root, "config", "81zi.reficus")
        os.environ["HERDR_PLUGIN_STATE_DIR"] = os.path.join(self.root, "state", "81zi.reficus")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

import os
import unittest

from helpers import P, S, TempEnv

import core
import keys
import settings


class CleanupTest(TempEnv):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.layout = {"workspace_id": "w1", "tab_id": "t1", "focused_pane_id": "A",
                       "zoomed": False, "root": S("right", P("A"), P("B"), ratio=0.7)}
        self._rpc = core.rpc, keys.rpc
        core.rpc = keys.rpc = self.fake_rpc
        os.makedirs(os.path.dirname(keys.config_toml_path()))

    def tearDown(self):
        core.rpc, keys.rpc = self._rpc
        super().tearDown()

    def fake_rpc(self, method, params=None):
        self.calls.append((method, params))
        if method == "layout.export":
            return {"layout": self.layout}
        if method == "layout.set_split_ratio":
            self.layout["root"]["ratio"] = params["ratio"]
        return {}

    def test_cleanup_restores_unbinds_disables_and_deletes(self):
        keys.write({"settings": "prefix+shift+f"})
        settings.save_config(settings.load_config())
        root = self.layout["root"]
        with settings.locked_state() as state:
            state["tabs"]["t1"] = {"sig": core.engine.signature(root), "snapshot": {"": 0.5}}
        message = core.cleanup()
        self.assertIn("disabled", message)
        self.assertEqual(self.layout["root"]["ratio"], 0.5)
        with open(keys.config_toml_path()) as f:
            self.assertNotIn("reficus", f.read())
        self.assertIn(("plugin.disable", {"plugin_id": "reficus"}), self.calls)
        self.assertFalse(os.path.exists(os.environ["HERDR_PLUGIN_CONFIG_DIR"]))
        self.assertFalse(os.path.exists(os.environ["HERDR_PLUGIN_STATE_DIR"]))


if __name__ == "__main__":
    unittest.main()

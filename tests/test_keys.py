import os
import unittest

from helpers import TempEnv

import keys

USER_CONFIG = """[ui]
sidebar = true

# my toggle for reficus
[[keys.command]]
key = "prefix+shift+z"
type = "plugin_action"
command = "local.reficus.toggle"
description = "reficus: toggle on/off"

[[keys.command]]
key = "prefix+y"
type = "shell"
command = "echo hi"
"""


class KeysTest(TempEnv):
    def setUp(self):
        super().setUp()
        self.reloads = []
        self.diagnostics = []
        self._rpc = keys.rpc
        keys.rpc = self.fake_rpc
        self.path = keys.config_toml_path()
        os.makedirs(os.path.dirname(self.path))

    def tearDown(self):
        keys.rpc = self._rpc
        super().tearDown()

    def fake_rpc(self, method, params=None):
        self.reloads.append(method)
        return {"diagnostics": self.diagnostics}

    def set_config(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def config(self):
        with open(self.path) as f:
            return f.read()

    def test_validate(self):
        self.assertIsNone(keys.validate("prefix+shift+f"))
        self.assertIsNotNone(keys.validate("prefix+shift"))
        self.assertIsNotNone(keys.validate("bad key\""))

    def test_conflict_with_herdr_default_and_custom_command(self):
        self.set_config(USER_CONFIG)
        self.assertIn("zoom", keys.conflict("toggle", "prefix+z", {}))
        self.assertIn("custom command", keys.conflict("toggle", "prefix+y", {}))
        self.assertIsNone(keys.conflict("toggle", "prefix+shift+z", {}))

    def test_write_adopts_hand_written_legacy_binding(self):
        self.set_config(USER_CONFIG)
        message, written = keys.write({"settings": "prefix+shift+f"})
        self.assertIn("saved", message)
        self.assertEqual(written["toggle"], "prefix+shift+z")
        text = self.config()
        self.assertNotIn("local.reficus", text)
        self.assertNotIn("my toggle for reficus", text)
        self.assertIn('command = "81zi.reficus.toggle"', text)
        self.assertIn('command = "81zi.reficus.settings"', text)
        self.assertIn('command = "echo hi"', text)
        self.assertEqual(self.reloads, ["server.reload_config"])

    def test_rewrite_is_idempotent_and_unbinds(self):
        keys.write({"settings": "prefix+shift+f"})
        self.assertEqual(keys.write({"settings": "prefix+shift+f"})[0], "keybindings unchanged")
        keys.write({"settings": None})
        self.assertNotIn(keys.BLOCK_START, self.config())

    def test_backups(self):
        self.set_config("[ui]\n")
        keys.write({"settings": "prefix+shift+f"})
        keys.write({"settings": "prefix+f"})
        with open(self.path + ".reficus-original") as f:
            self.assertEqual(f.read(), "[ui]\n")
        with open(self.path + ".reficus-backup") as f:
            self.assertIn("prefix+shift+f", f.read())

    def test_rejected_config_is_restored(self):
        self.set_config(USER_CONFIG)
        self.diagnostics = ["bad"]
        with self.assertRaises(ValueError):
            keys.write({"settings": "prefix+shift+f"})
        self.assertEqual(self.config(), USER_CONFIG)

    def test_writes_through_symlink(self):
        real = os.path.join(self.root, "dotfiles.toml")
        with open(real, "w") as f:
            f.write("[ui]\n")
        os.symlink(real, self.path)
        keys.write({"settings": "prefix+shift+f"})
        self.assertTrue(os.path.islink(self.path))
        with open(real) as f:
            self.assertIn(keys.BLOCK_START, f.read())


if __name__ == "__main__":
    unittest.main()

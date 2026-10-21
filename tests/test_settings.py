import json
import os
import unittest

from helpers import TempEnv

import settings


class SettingsTest(TempEnv):
    def write_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    def test_defaults_without_config(self):
        cfg = settings.load_config()
        self.assertEqual(cfg["strategy"], "weighted")
        self.assertEqual(cfg["profile"], "coding")

    def test_copies_config_and_state_from_legacy_id(self):
        self.write_json(os.path.join(self.root, "config", "local.reficus", "config.json"), {"ratio": 0.8})
        self.write_json(os.path.join(self.root, "state", "local.reficus", "state.json"), {"tabs": {"t": {}}})
        self.assertEqual(settings.load_config()["ratio"], 0.8)
        self.assertIn("t", settings.read_state()["tabs"])
        self.assertTrue(os.path.exists(settings.config_path()))

    def test_newest_previous_id_wins(self):
        self.write_json(os.path.join(self.root, "config", "local.reficus", "config.json"), {"ratio": 0.8})
        self.write_json(os.path.join(self.root, "config", "81zi.reficus", "config.json"), {"ratio": 0.9})
        self.assertEqual(settings.load_config()["ratio"], 0.9)

    def test_remove_data(self):
        settings.save_config(settings.load_config())
        with settings.locked_state() as state:
            state["tabs"]["t1"] = {}
        with settings.apply_lock():
            pass
        legacy = os.path.join(self.root, "config", "81zi.reficus", "config.json")
        self.write_json(legacy, {"ratio": 0.9})
        other = os.path.join(self.root, "state", "reficus", "notes.txt")
        with open(other, "w") as f:
            f.write("not ours")
        settings.remove_data()
        self.assertFalse(os.path.exists(os.environ["HERDR_PLUGIN_CONFIG_DIR"]))
        self.assertFalse(os.path.exists(os.path.dirname(legacy)))
        self.assertEqual(os.listdir(os.environ["HERDR_PLUGIN_STATE_DIR"]), ["notes.txt"])

    def test_existing_config_is_not_overwritten_by_legacy(self):
        self.write_json(settings.config_path(), {"ratio": 0.7})
        self.write_json(os.path.join(self.root, "config", "local.reficus", "config.json"), {"ratio": 0.8})
        self.assertEqual(settings.load_config()["ratio"], 0.7)

    def test_migrates_respect_manual(self):
        self.write_json(settings.config_path(), {"respect_manual": True})
        cfg = settings.load_config()
        self.assertEqual(cfg["on_manual_resize"], "pause")
        self.assertNotIn("respect_manual", cfg)

    def test_profiles_round_trip(self):
        cfg = settings.load_config()
        cfg["ratio"] = 0.9
        self.assertTrue(settings.profile_modified(cfg))
        settings.save_profile(cfg, "mine")
        settings.save_config(cfg)
        cfg = settings.load_config()
        self.assertEqual(cfg["profile"], "mine")
        self.assertFalse(settings.profile_modified(cfg))
        settings.apply_profile(cfg, "review")
        self.assertEqual(cfg["ratio"], 0.8)

    def test_partial_config_keeps_given_tunables(self):
        self.write_json(settings.config_path(), {"narrow_cols": 150})
        cfg = settings.load_config()
        self.assertEqual(cfg["narrow_cols"], 150)
        self.assertEqual(cfg["ratio"], 0.65)

    def test_partial_config_fills_from_active_profile(self):
        self.write_json(settings.config_path(), {"profile": "monitor", "agent_boost": 2.5})
        cfg = settings.load_config()
        self.assertEqual(cfg["strategy"], "equal")
        self.assertEqual(cfg["agent_boost"], 2.5)

    def test_unknown_profile_falls_back_to_manual(self):
        self.write_json(settings.config_path(), {"profile": "gone"})
        self.assertEqual(settings.load_config()["profile"], settings.MANUAL_PROFILE)

    def test_locked_state_persists(self):
        with settings.locked_state() as state:
            state["tabs"]["t1"] = {"paused": True}
        self.assertTrue(settings.read_state()["tabs"]["t1"]["paused"])


if __name__ == "__main__":
    unittest.main()

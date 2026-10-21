import unittest

from helpers import P, S

import engine
import settings

TREE = S("right", P("A"), S("down", P("B"), P("C")))


def plan(focused, tree=TREE, width=200, height=60, panes=None, frozen=(), **overrides):
    cfg = settings.effective(dict(settings.DEFAULTS, **overrides))
    return engine.Planner(cfg, focused, panes or {}, frozen).plan(tree, width, height)


class StrategyTest(unittest.TestCase):
    def test_weighted_gives_focused_pane_the_ratio(self):
        self.assertEqual(plan("A", S("right", P("A"), P("B"))), {(): 0.65})
        self.assertEqual(plan("B", S("right", P("A"), P("B"))), {(): 0.35})

    def test_weighted_nested(self):
        self.assertEqual(plan("C"), {(): 0.35, (True,): 0.35})

    def test_golden(self):
        self.assertEqual(plan("C", strategy="golden"), {(): 0.382, (True,): 0.382})

    def test_fixed_size(self):
        self.assertEqual(plan("C", strategy="fixed"), {(): 0.4, (True,): 0.3333})

    def test_accordion_respects_min_cols(self):
        self.assertEqual(plan("C", strategy="accordion")[()], 0.1)

    def test_equal(self):
        self.assertEqual(plan("C", strategy="equal"), {(): 0.5, (True,): 0.5})

    def test_ancestors_keeps_splits_off_the_focus_path(self):
        tree = S("right", S("down", P("A"), P("B"), ratio=0.3), P("C"))
        self.assertEqual(plan("C", tree, strategy="ancestors")[(False,)], 0.3)


class ConstraintTest(unittest.TestCase):
    def test_minimums_win_when_space_is_short(self):
        self.assertEqual(plan("A", width=30, height=4), {(): 0.5, (True,): 0.5})

    def test_axis_horizontal_leaves_stacked_splits(self):
        tree = S("right", P("A"), S("down", P("B"), P("C"), ratio=0.2))
        self.assertEqual(plan("C", tree, axis="horizontal")[(True,)], 0.2)

    def test_frozen_split_is_untouched(self):
        tree = S("right", P("A"), P("B"), ratio=0.42)
        self.assertEqual(plan("A", tree, frozen=[()]), {(): 0.42})

    def test_rule_max_cols(self):
        panes = {"A": engine.PaneInfo(rule={"max_cols": 50})}
        self.assertEqual(plan("A", S("right", P("A"), P("B")), panes=panes), {(): 0.25})

    def test_blocked_agent_grows(self):
        panes = {"B": engine.PaneInfo("blocked")}
        tree = S("right", P("A"), S("right", P("B"), P("C")))
        self.assertGreater(plan("A", tree, panes=panes, agent_boost=2.0)[(True,)], 0.5)


class TreeTest(unittest.TestCase):
    def test_signature_ignores_ratios(self):
        moved = S("right", P("A"), S("down", P("B"), P("C"), ratio=0.9), ratio=0.1)
        self.assertEqual(engine.signature(TREE), engine.signature(moved))

    def test_current_ratios_and_pane_ids(self):
        self.assertEqual(engine.current_ratios(TREE), {(): 0.5, (True,): 0.5})
        self.assertEqual(engine.pane_ids(TREE), ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()

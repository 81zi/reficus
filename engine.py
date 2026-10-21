"""Pure layout math: turn a herdr layout tree into target split ratios.

The tree is the `root` of `layout.export`: pane nodes {"type": "pane",
"pane_id"} and split nodes {"type": "split", "direction": "right"|"down",
"ratio", "first", "second"}. Ratio is the share of the first child. A split
path is a list of booleans from the root, True meaning "second child".

`panes` maps pane_id -> PaneInfo with everything the engine needs to know
about a pane besides the tree (agent status, matched rule). `frozen`
holds split paths whose ratio must not change (manual resizes in "keep" mode).
"""

GOLDEN = 0.618
ACCORDION_WEIGHT = 10000.0
RATIO_FLOOR = 0.02
INF = float("inf")


class PaneInfo:
    def __init__(self, agent_status=None, rule=None):
        self.agent_status = agent_status
        self.rule = rule or {}


def axis_of(direction):
    return "cols" if direction == "right" else "rows"


def axis_allowed(direction, axis_setting):
    if axis_setting == "horizontal":
        return direction == "right"
    if axis_setting == "vertical":
        return direction == "down"
    return True


def contains(node, pane_id):
    if node["type"] == "pane":
        return node.get("pane_id") == pane_id
    return contains(node["first"], pane_id) or contains(node["second"], pane_id)


class Planner:
    def __init__(self, cfg, focused, panes, frozen=()):
        self.cfg = cfg
        self.focused = focused
        self.panes = panes
        self.frozen = set(frozen)
        self.strategy = cfg["strategy"]
        rule = self._info(focused).rule
        ratio = rule.get("ratio") if rule.get("ratio") is not None else cfg["ratio"]
        self.ratio = GOLDEN if self.strategy == "golden" else min(max(float(ratio), 0.5), 0.95)
        if self.strategy == "accordion":
            self.focus_weight = ACCORDION_WEIGHT
        elif self.strategy == "equal":
            self.focus_weight = 1.0
        else:
            self.focus_weight = self.ratio / (1.0 - self.ratio)

    def _info(self, pane_id):
        return self.panes.get(pane_id) or PaneInfo()

    # Per-axis aggregates over subtrees. Along a split's own axis children
    # stack (sum); across it they sit side by side (max).
    def _fold(self, node, axis, leaf):
        if node["type"] == "pane":
            return leaf(node.get("pane_id"))
        first = self._fold(node["first"], axis, leaf)
        second = self._fold(node["second"], axis, leaf)
        return first + second if axis_of(node["direction"]) == axis else max(first, second)

    def weight(self, node, axis):
        def leaf(pane_id):
            if pane_id == self.focused:
                return self.focus_weight
            if self.strategy in ("equal", "golden", "fixed"):
                return 1.0
            status = self._info(pane_id).agent_status
            if status == "blocked":
                return float(self.cfg["agent_boost"])
            if status in ("idle", "done"):
                return float(self.cfg["idle_weight"])
            return 1.0

        return self._fold(node, axis, leaf)

    def min_need(self, node, axis):
        def leaf(pane_id):
            rule = self._info(pane_id).rule
            base = self.cfg["min_" + axis]
            if self.strategy == "accordion" and pane_id != self.focused:
                base = max(base, self.cfg["accordion_" + axis])
            if rule.get("min_" + axis) is not None:
                base = max(base, rule["min_" + axis])
            return float(base)

        return self._fold(node, axis, leaf)

    def max_cap(self, node, axis):
        def leaf(pane_id):
            cap = self._info(pane_id).rule.get("max_" + axis)
            return float(cap) if cap is not None else INF

        return self._fold(node, axis, leaf)

    def fixed_need(self, node, axis):
        def leaf(pane_id):
            if pane_id == self.focused:
                return float(self.cfg["fixed_" + axis])
            return self.min_need({"type": "pane", "pane_id": pane_id}, axis)

        return self._fold(node, axis, leaf)

    def desired_first(self, node, size, axis):
        first, second = node["first"], node["second"]
        ancestor = contains(node, self.focused)
        if self.strategy == "golden" and ancestor:
            share = self.ratio if contains(first, self.focused) else 1.0 - self.ratio
            return share * size
        if self.strategy == "fixed" and ancestor:
            if contains(first, self.focused):
                return self.fixed_need(first, axis)
            return size - self.fixed_need(second, axis)
        wf, ws = self.weight(first, axis), self.weight(second, axis)
        return size * wf / (wf + ws)

    def clamp(self, node, size, axis, first_size):
        first, second = node["first"], node["second"]
        cap_f, cap_s = self.max_cap(first, axis), self.max_cap(second, axis)
        first_size = min(first_size, cap_f)
        first_size = max(first_size, size - cap_s)
        min_f, min_s = self.min_need(first, axis), self.min_need(second, axis)
        if min_f + min_s >= size:
            return size * min_f / (min_f + min_s) if min_f + min_s else size / 2
        return min(max(first_size, min_f), size - min_s)

    def keeps_ratio(self, node):
        if not axis_allowed(node["direction"], self.cfg["axis"]):
            return True
        return self.strategy == "ancestors" and not contains(node, self.focused)

    def plan(self, node, width, height, path=None, out=None):
        """Returns {tuple(path): target_ratio} for every split in the tree."""
        path = path or []
        out = {} if out is None else out
        if node["type"] != "split":
            return out
        axis = axis_of(node["direction"])
        size = float(width if axis == "cols" else height)
        if tuple(path) in self.frozen or self.keeps_ratio(node) or size <= 0:
            ratio = node["ratio"]
        else:
            first_size = self.clamp(node, size, axis, self.desired_first(node, size, axis))
            ratio = min(max(first_size / size, RATIO_FLOOR), 1.0 - RATIO_FLOOR)
        out[tuple(path)] = round(ratio, 4)
        if axis == "cols":
            fw, fh, sw, sh = width * ratio, height, width * (1 - ratio), height
        else:
            fw, fh, sw, sh = width, height * ratio, width, height * (1 - ratio)
        self.plan(node["first"], fw, fh, path + [False], out)
        self.plan(node["second"], sw, sh, path + [True], out)
        return out


def current_ratios(node, path=None, out=None):
    path = path or []
    out = {} if out is None else out
    if node["type"] == "split":
        out[tuple(path)] = node["ratio"]
        current_ratios(node["first"], path + [False], out)
        current_ratios(node["second"], path + [True], out)
    return out


def signature(node):
    """Shape + pane ids, ignoring ratios. Changes when panes split/close/move."""
    if node["type"] == "pane":
        return node.get("pane_id") or "?"
    return "%s(%s,%s)" % (node["direction"][0], signature(node["first"]), signature(node["second"]))


def pane_ids(node):
    if node["type"] == "pane":
        return [node.get("pane_id")]
    return pane_ids(node["first"]) + pane_ids(node["second"])

#!/usr/bin/env python3
"""capacity_tmuxer.py（bash 版 CLI 的 Python 移植）与 tmux_backend 的测试。

运行: python test/capacity-tmuxer-test.py   （不需要真实 tmux）
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import capacity_tmuxer as ct  # noqa: E402
import tmux_backend as tb  # noqa: E402

CAP = "■ Selected model is at capacity. Please try a different model.\n\n› Ask Codex\n"
BUSY = "• Working (3s • esc to interrupt)\n"
IDLE = "› Ask Codex to do anything\n"


class FakeTmux:
    cmd = ["tmux"]

    def __init__(self, frames):
        self.frames = frames
        self.sent = []
        self.empty = True

    def list_panes(self, session=None):
        return [{"session": t.split(":")[0], "target": t, "command": "codex"}
                for t in sorted(self.frames) if session in (None, t.split(":")[0])]

    def capture(self, target, ansi=False):
        return self.frames.get(target)

    def composer_is_empty(self, target):
        return self.empty

    def send(self, target, text):
        self.sent.append((target, text))
        return True


class WatcherTest(unittest.TestCase):
    def setUp(self):
        self.t = 10000.0
        self.tmux = FakeTmux({"a:0.0": CAP, "b:0.0": CAP})
        self.cfg = ct.load_config({})
        self.logs = []
        self.w = ct.Watcher(["a"], self.cfg, self.tmux, clock=lambda: self.t,
                            out=self.logs.append)

    def test_defaults_match_bash_version(self):
        self.assertEqual((self.cfg["poll"], self.cfg["window"], self.cfg["backoff_start"],
                          self.cfg["backoff_max"], self.cfg["send_text"]),
                         (15, 20, 30, 900, "continue"))
        self.assertTrue(self.cfg["guard_composer"])
        self.assertFalse(ct.load_config({"GUARD_COMPOSER": "0"})["guard_composer"])

    def test_classify(self):
        self.assertEqual(ct.classify(BUSY, self.cfg)[0], "WORKING")
        self.assertEqual(ct.classify(CAP, self.cfg)[0], "CAPACITY")
        self.assertEqual(ct.classify(IDLE, self.cfg)[0], "IDLE")
        self.assertEqual(ct.classify(None, self.cfg)[0], "GONE")
        self.assertEqual(ct.classify(CAP + "\n" * 25 + IDLE, self.cfg)[0], "IDLE")

    def test_sends_only_to_whitelist_with_backoff(self):
        self.w.scan_once()
        self.assertEqual(self.tmux.sent, [("a:0.0", "continue")])
        self.t += 59
        self.w.scan_once()                  # 退避 60s 内不重发
        self.assertEqual(len(self.tmux.sent), 1)
        self.t += 1
        self.w.scan_once()
        self.assertEqual(len(self.tmux.sent), 2)
        self.assertEqual(self.w.backoff["a:0.0"], 120)

    def test_backoff_capped_and_reset_when_working(self):
        for _ in range(10):
            self.w.scan_once()
            self.t += 1000
        self.assertEqual(self.w.backoff["a:0.0"], 900)
        self.tmux.frames["a:0.0"] = BUSY
        self.w.scan_once()
        self.assertEqual(self.w.backoff["a:0.0"], 30)

    def test_idle_and_busy_never_send(self):
        self.tmux.frames["a:0.0"] = IDLE
        self.w.scan_once()
        self.tmux.frames["a:0.0"] = BUSY
        self.w.scan_once()
        self.assertEqual(self.tmux.sent, [])

    def test_guard_skips(self):
        self.tmux.empty = False
        self.w.scan_once()
        self.assertEqual(self.tmux.sent, [])
        self.assertIn("composer not empty", self.logs[-1])

    def test_status_render(self):
        out = ct.render_status(["a"], self.cfg, self.tmux)
        self.assertIn("a:0.0", out)
        self.assertIn("CAPACITY", out)

    def test_no_sessions_exit_code(self):
        old = os.environ.pop("WATCH_SESSIONS", None)
        try:
            self.assertEqual(ct.main([]), 2)
        finally:
            if old is not None:
                os.environ["WATCH_SESSIONS"] = old


class DetectTest(unittest.TestCase):
    def which(self, available):
        return lambda name: ("/x/" + name) if name in available else None

    def test_env_override(self):
        self.assertEqual(tb.detect_tmux_command({"TMUX_CMD": "wsl -e tmux"},
                                                which=self.which(()), windows=False),
                         ["wsl", "-e", "tmux"])
        self.assertEqual(tb.detect_tmux_command({"TMUX_CMD": "wsl -e tmux"},
                                                which=self.which(()), windows=True),
                         ["wsl", "-e", "tmux"])
        self.assertEqual(tb.detect_tmux_command(
            {"TMUX_CMD": '"C:\\Program Files\\tmux\\tmux.exe" -L x'},
            which=self.which(()), windows=True),
            ["C:\\Program Files\\tmux\\tmux.exe", "-L", "x"])

    def test_detection_order(self):
        self.assertEqual(tb.detect_tmux_command({}, self.which(("tmux", "psmux")), True),
                         ["/x/tmux"])
        self.assertEqual(tb.detect_tmux_command({}, self.which(("psmux", "wsl")), True),
                         ["/x/psmux"])
        self.assertEqual(tb.detect_tmux_command({}, self.which(("wsl",)), True),
                         ["wsl", "-e", "tmux"])
        self.assertIsNone(tb.detect_tmux_command({}, self.which(("wsl",)), False))
        self.assertIsNone(tb.detect_tmux_command({}, self.which(()), True))

    def test_missing_tmux_is_harmless(self):
        t = tb.Tmux(cmd=[])
        self.assertFalse(t.available)
        self.assertEqual(t.list_sessions(), [])
        self.assertFalse(t.send("x", "continue"))
        self.assertFalse(t.composer_is_empty("x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

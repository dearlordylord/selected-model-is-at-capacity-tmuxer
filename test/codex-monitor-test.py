#!/usr/bin/env python3
"""codex_monitor 的单元测试（不依赖真实 tmux）。运行: python3 test/codex-monitor-test.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import codex_monitor as cm  # noqa: E402

WORKING_FRAME = "› fix the bug\n\n• Working (12s • esc to interrupt)\n"
IDLE_FRAME = "• Done.\n\n› Ask Codex to do anything\n"
TYPED_FRAME = "• Done.\n\n› hello\n"
CAP_FRAME = "■ Selected model is at capacity. Please try a different model.\n\n› Ask Codex\n"


class FakeTmux:
    def __init__(self):
        self.frames = {"a:0.0": WORKING_FRAME}
        self.commands = {"a:0.0": "codex"}
        self.sent = []

    def list_sessions(self):
        names = sorted({t.split(":")[0] for t in self.frames})
        return [{"name": n, "windows": 1, "attached": False} for n in names]

    def list_panes(self):
        return [{"session": t.split(":")[0], "target": t, "command": self.commands.get(t, "bash")}
                for t in sorted(self.frames)]

    def capture(self, target, ansi=False):
        return self.frames.get(target)

    def send(self, target, text):
        self.sent.append((target, text))
        return True


class FixedRng:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def uniform(self, a, b):
        self.calls.append((a, b))
        return self.value


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.t = 1000.0
        self.tmux = FakeTmux()
        self.rng = FixedRng(120)
        self.m = cm.Monitor(tmux=self.tmux, clock=lambda: self.t, rng=self.rng)
        self.m.select(["a"])

    def advance(self, seconds):
        self.t += seconds
        self.m.tick()

    def pane(self):
        return self.m.panes["a:0.0"]

    def test_classify(self):
        cfg = cm.DEFAULT_CONFIG
        self.assertEqual(cm.classify(WORKING_FRAME, cfg)[0], cm.WORKING)
        self.assertEqual(cm.classify(IDLE_FRAME, cfg)[0], cm.STOPPED)
        self.assertEqual(cm.classify(CAP_FRAME, cfg)[0], cm.CAPACITY)
        old_cap = CAP_FRAME + "\n" * 30 + "› Ask Codex\n"
        self.assertEqual(cm.classify(old_cap, cfg)[0], cm.STOPPED)

    def test_detects_codex_sessions(self):
        self.tmux.frames["plain:0.0"] = "$ ls\n"
        self.tmux.frames["node:0.0"] = IDLE_FRAME
        self.tmux.commands["node:0.0"] = "node"
        m = cm.Monitor(tmux=self.tmux)
        self.assertEqual(sorted(m.auto_select()), ["a", "node"])

    def test_working_never_sends(self):
        for _ in range(100):
            self.advance(10)
        self.assertEqual(self.tmux.sent, [])
        self.assertIsNone(self.pane().stopped_since)

    def test_stop_then_random_wait_then_send(self):
        self.advance(5)
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(5)                      # 停止开始
        self.advance(29)                     # 29s < 30s 阈值
        self.assertIsNone(self.pane().next_send_at)
        self.advance(1)                      # 达到 30s，开始随机等待
        self.assertEqual(self.rng.calls, [(60, 300)])
        self.assertEqual(self.pane().wait_seconds, 120)
        self.advance(119)
        self.assertEqual(self.tmux.sent, [])
        self.advance(1)
        self.assertEqual(self.tmux.sent, [("a:0.0", "continue")])
        self.assertEqual(self.pane().send_count, 1)

    def test_repeat_after_send_uses_new_random_wait(self):
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(1)
        self.advance(30)
        self.advance(120)
        self.assertEqual(len(self.tmux.sent), 1)
        self.rng.value = 250
        self.advance(30)                     # 仍然停止，再次超过阈值
        self.assertEqual(self.pane().wait_seconds, 250)
        self.advance(249)
        self.assertEqual(len(self.tmux.sent), 1)
        self.advance(1)
        self.assertEqual(len(self.tmux.sent), 2)

    def test_recovery_cancels_plan(self):
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(1)
        self.advance(30)
        self.assertIsNotNone(self.pane().next_send_at)
        self.tmux.frames["a:0.0"] = WORKING_FRAME
        self.advance(5)
        self.assertIsNone(self.pane().next_send_at)
        self.advance(500)
        self.assertEqual(self.tmux.sent, [])

    def test_content_change_restarts_timer(self):
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(1)
        self.advance(20)
        self.tmux.frames["a:0.0"] = IDLE_FRAME + "› typing\n"
        self.advance(20)                     # 内容变化 → 重新计时
        self.assertEqual(self.pane().stopped_since, self.t)
        self.assertIsNone(self.pane().next_send_at)

    def start_idle_then_type(self):
        """停止状态下，用户在输入框里打字（输入框内容发生变化）。"""
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(1)                      # 首次观察，不算变化
        self.assertIsNone(self.pane().composer_changed_at)
        self.tmux.frames["a:0.0"] = TYPED_FRAME
        self.advance(5)
        return self.t                        # 输入框内容变化的时间

    def test_composer_changed_within_quiet_period_skips_manual_send(self):
        changed = self.start_idle_then_type()
        self.assertEqual(self.pane().composer_changed_at, changed)
        self.assertFalse(self.m.send_now("a:0.0"))
        self.assertEqual(self.tmux.sent, [])
        self.assertIn("20 秒内有变化", self.pane().note)
        self.advance(14)                     # 距变化 14s
        self.assertFalse(self.m.send_now("a:0.0"))
        self.advance(5)                      # 距变化 19s
        self.assertFalse(self.m.send_now("a:0.0"))
        self.advance(1)                      # 距变化 20s：静默期已过
        self.assertTrue(self.m.send_now("a:0.0"))
        self.assertEqual(self.tmux.sent, [("a:0.0", "continue")])

    def test_unchanged_nonempty_composer_does_not_block(self):
        # 输入框里有残留内容，但 20 秒内没变化 → 不再跳过
        self.tmux.frames["a:0.0"] = TYPED_FRAME
        self.advance(1)
        self.advance(30)                     # 超过阈值，安排随机等待（120s）
        self.advance(120)
        self.assertEqual(len(self.tmux.sent), 1)   # 已自动发送

    def test_quiet_zero_disables_check(self):
        self.m.update_config({"composer_quiet": 0})
        self.start_idle_then_type()
        self.assertTrue(self.m.send_now("a:0.0"))

    def test_quiet_period_is_configurable(self):
        self.m.update_config({"composer_quiet": 60})
        self.start_idle_then_type()
        self.advance(30)
        self.assertFalse(self.m.send_now("a:0.0"))
        self.advance(30)
        self.assertTrue(self.m.send_now("a:0.0"))

    def test_auto_send_rechecks_after_quiet_period(self):
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(1)
        # 计划发送前一刻输入框内容变了（发生在两次扫描之间）
        self.tmux.frames["a:0.0"] = TYPED_FRAME
        self.t += 3
        with self.m.lock:
            self.assertFalse(self.m._send(self.pane(), self.t))
        self.assertEqual(self.tmux.sent, [])
        self.assertEqual(self.pane().next_send_at, self.t + 20)

    def test_extract_composer(self):
        self.assertEqual(cm.extract_composer(IDLE_FRAME), "› Ask Codex to do anything")
        self.assertEqual(cm.extract_composer(TYPED_FRAME), "› hello")
        multi = "x\n\n› line one\n  line two\n\n  gpt medium · /p 83% left\n"
        self.assertEqual(cm.extract_composer(multi), "› line one\n  line two")
        self.assertIsNone(cm.extract_composer("no prompt here\n"))
        # 页脚变化不算输入框变化
        a = cm.extract_composer("› hi\n\n  gpt medium · /p 83% left\n")
        b = cm.extract_composer("› hi\n\n  gpt medium · /p 82% left\n")
        self.assertEqual(a, b)

    def test_capacity_only_trigger(self):
        self.m.update_config({"trigger": "capacity"})
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.advance(1)
        self.advance(1000)
        self.assertEqual(self.tmux.sent, [])
        self.tmux.frames["a:0.0"] = CAP_FRAME
        self.advance(1)
        self.advance(30)
        self.advance(120)
        self.assertEqual(len(self.tmux.sent), 1)

    def test_unselected_paused_and_disabled_do_not_send(self):
        self.tmux.frames["a:0.0"] = IDLE_FRAME
        self.m.set_running(False)
        self.advance(1)
        self.advance(1000)
        self.assertEqual(self.tmux.sent, [])
        self.m.set_running(True)
        self.m.set_pane_enabled("a:0.0", False)
        self.advance(1000)
        self.assertEqual(self.tmux.sent, [])
        self.m.set_pane_enabled("a:0.0", True)
        self.m.select([])
        self.advance(1000)
        self.assertEqual(self.tmux.sent, [])

    def test_config_validation(self):
        with self.assertRaises(ValueError):
            self.m.update_config({"wait_min": 500, "wait_max": 100})
        with self.assertRaises(ValueError):
            self.m.update_config({"nope": 1})
        with self.assertRaises(ValueError):
            self.m.update_config({"busy_re": "("})
        self.m.update_config({"wait_min": 10, "wait_max": 20})
        self.assertEqual(self.m.config["wait_max"], 20)

    def test_send_all_skips_working_and_unselected(self):
        self.tmux.frames["a:1.0"] = IDLE_FRAME
        self.tmux.frames["a:2.0"] = CAP_FRAME
        self.tmux.frames["b:0.0"] = IDLE_FRAME      # 未选中的会话
        self.tmux.commands["a:1.0"] = "codex"
        self.m.tick()
        sent = self.m.send_all()
        self.assertEqual(sorted(sent), ["a:1.0", "a:2.0"])   # a:0.0 工作中，b 未选中
        self.assertEqual(sorted(t for t, _ in self.tmux.sent), ["a:1.0", "a:2.0"])
        self.assertEqual(self.m.panes["a:1.0"].send_count, 1)

    def test_send_all_skips_panes_being_typed_in(self):
        self.tmux.frames["a:1.0"] = IDLE_FRAME
        self.tmux.frames["a:2.0"] = IDLE_FRAME
        self.m.tick()
        self.tmux.frames["a:1.0"] = TYPED_FRAME      # 用户正在这个 pane 输入
        self.advance(5)
        self.assertEqual(self.m.send_all(), ["a:2.0"])
        self.assertEqual(self.tmux.sent, [("a:2.0", "continue")])

    def test_snapshot_lists_selected_panes(self):
        self.tmux.frames["b:0.0"] = IDLE_FRAME
        self.m.tick()
        snap = self.m.snapshot()
        self.assertEqual([p["target"] for p in snap["panes"]], ["a:0.0"])
        self.assertEqual({s["name"]: s["selected"] for s in snap["sessions"]},
                         {"a": True, "b": False})


if __name__ == "__main__":
    unittest.main(verbosity=2)

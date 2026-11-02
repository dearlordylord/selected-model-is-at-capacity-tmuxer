"""codex_monitor — 监控 tmux 中的 Codex 任务，停止后随机等待再发送 continue。

纯标准库实现（Python 3.8+，Linux / macOS / Windows 通用）。核心逻辑（Monitor.tick）与 tmux 调用（Tmux）分离，
时钟与随机数均可注入，便于测试。
"""

import hashlib
import random
import re
import threading
import time
from collections import deque

from tmux_backend import Tmux  # noqa: F401  (re-exported for callers)

# 状态常量
WORKING = "WORKING"      # Codex 正在工作（检测到 esc to interrupt）
CAPACITY = "CAPACITY"    # 因 "Selected model is at capacity" 停止
STOPPED = "STOPPED"      # 已停止（空闲）
GONE = "GONE"            # pane 已消失

DEFAULT_CONFIG = {
    "poll": 5,                    # 扫描间隔（秒）
    "stop_threshold": 30,         # 停止超过多少秒才开始计划发送
    "wait_min": 60,               # 随机等待下限（秒）
    "wait_max": 300,              # 随机等待上限（秒）
    "send_text": "continue",      # 发送的文本
    "trigger": "any",             # any = 任何停止；capacity = 仅容量错误
    "guard_composer": True,       # 输入框非空时不发送
    "window": 20,                 # 底部多少行算"当前"
    "busy_re": r"esc to interrupt",
    "cap_re": r"Selected model is at capacity",
    "codex_re": r"OpenAI Codex|esc to interrupt|context left|"
                r"Selected model is at capacity|^\s*[›»] ",
}


def classify(text, cfg):
    """根据 pane 底部内容返回 (state, detail)。"""
    lines = text.rstrip("\n").split("\n")
    tail = lines[-int(cfg["window"]):]
    busy = re.compile(cfg["busy_re"], re.I)
    cap = re.compile(cfg["cap_re"], re.I)
    for line in tail:
        if busy.search(line):
            return WORKING, line.strip()
    for line in tail:
        if cap.search(line):
            return CAPACITY, line.strip()
    return STOPPED, ""


def looks_like_codex(command, text, cfg):
    if "codex" in (command or "").lower():
        return True
    return bool(text and re.search(cfg["codex_re"], text, re.I | re.M))


class PaneState:
    def __init__(self, target, session):
        self.target = target
        self.session = session
        self.command = ""
        self.is_codex = False
        self.state = STOPPED
        self.detail = ""
        self.enabled = True          # 是否对该 pane 自动发送
        self.last_hash = None
        self.stopped_since = None    # 本轮停止开始时间
        self.next_send_at = None     # 计划发送时间
        self.wait_seconds = None     # 本次随机等待时长
        self.last_sent_at = None
        self.send_count = 0
        self.note = ""
        self.preview = ""

    def to_dict(self, now):
        return {
            "target": self.target,
            "session": self.session,
            "command": self.command,
            "is_codex": self.is_codex,
            "state": self.state,
            "detail": self.detail,
            "enabled": self.enabled,
            "stopped_for": None if self.stopped_since is None
            else int(now - self.stopped_since),
            "send_in": None if self.next_send_at is None
            else max(0, int(self.next_send_at - now)),
            "wait_seconds": None if self.wait_seconds is None
            else int(self.wait_seconds),
            "last_sent_ago": None if self.last_sent_at is None
            else int(now - self.last_sent_at),
            "send_count": self.send_count,
            "note": self.note,
            "preview": self.preview,
        }


class Monitor:
    def __init__(self, tmux=None, clock=time.time, rng=None, config=None):
        self.tmux = tmux or Tmux()
        self.clock = clock
        self.rng = rng or random.Random()
        self.config = dict(DEFAULT_CONFIG)
        if config:
            self.config.update(config)
        self.lock = threading.RLock()
        self.running = True
        self.selected = set()
        self.sessions = []
        self.panes = {}
        self.logs = deque(maxlen=300)
        self._stop = threading.Event()
        self._wake = threading.Event()

    # ---- 日志 ---------------------------------------------------------------
    def log(self, msg):
        stamp = time.strftime("%H:%M:%S", time.localtime(self.clock()))
        self.logs.append(f"{stamp}  {msg}")

    # ---- 配置与选择 -----------------------------------------------------------
    def update_config(self, changes):
        with self.lock:
            cfg = dict(self.config)
            for key, value in changes.items():
                if key not in DEFAULT_CONFIG:
                    raise ValueError(f"未知配置项: {key}")
                default = DEFAULT_CONFIG[key]
                if isinstance(default, bool):
                    value = bool(value)
                elif isinstance(default, int):
                    value = int(value)
                    if value < 0:
                        raise ValueError(f"{key} 不能为负数")
                else:
                    value = str(value)
                if key.endswith("_re"):
                    try:
                        re.compile(value)
                    except re.error as exc:
                        raise ValueError(f"{key} 正则无效: {exc}") from None
                cfg[key] = value
            if cfg["trigger"] not in ("any", "capacity"):
                raise ValueError("trigger 只能是 any 或 capacity")
            if cfg["wait_min"] > cfg["wait_max"]:
                raise ValueError("等待下限不能大于上限")
            if cfg["poll"] < 1 or cfg["window"] < 1:
                raise ValueError("poll 与 window 至少为 1")
            self.config = cfg
            self.log("配置已更新")
        self._wake.set()

    def select(self, names):
        with self.lock:
            new = set(names)
            for name in sorted(new - self.selected):
                self.log(f"开始监控会话 {name}")
            for name in sorted(self.selected - new):
                self.log(f"停止监控会话 {name}")
            self.selected = new
        self._wake.set()

    def auto_select(self):
        """选中所有检测到 Codex 的会话。"""
        self.refresh()
        with self.lock:
            names = [s["name"] for s in self.sessions if s["is_codex"]]
        self.select(set(names) | self.selected)
        return names

    def set_running(self, running):
        with self.lock:
            self.running = bool(running)
            self.log("自动续跑已启动" if running else "自动续跑已暂停（仅显示状态）")
        self._wake.set()

    def set_pane_enabled(self, target, enabled):
        with self.lock:
            pane = self.panes.get(target)
            if pane is None:
                raise KeyError(target)
            pane.enabled = bool(enabled)
            self.log(f"{target} 自动发送已{'启用' if enabled else '禁用'}")

    def send_now(self, target):
        with self.lock:
            pane = self.panes.get(target)
            if pane is None:
                raise KeyError(target)
            return self._send(pane, self.clock(), manual=True)

    # ---- 扫描 ---------------------------------------------------------------
    def refresh(self):
        """刷新 tmux 会话/pane 列表，并对每个 pane 做状态分类。"""
        with self.lock:
            cfg = dict(self.config)
        sessions = self.tmux.list_sessions()
        panes = self.tmux.list_panes()
        captures = {}
        for p in panes:
            captures[p["target"]] = self.tmux.capture(p["target"])
        now = self.clock()
        with self.lock:
            seen = set()
            codex_sessions = set()
            for p in panes:
                target = p["target"]
                seen.add(target)
                pane = self.panes.get(target)
                if pane is None:
                    pane = self.panes[target] = PaneState(target, p["session"])
                pane.command = p["command"]
                text = captures.get(target)
                if text is None:
                    pane.state, pane.detail = GONE, ""
                    continue
                pane.is_codex = looks_like_codex(p["command"], text, cfg)
                if pane.is_codex:
                    codex_sessions.add(p["session"])
                self._observe(pane, text, now, cfg)
            for target in list(self.panes):
                if target not in seen:
                    del self.panes[target]
            self.sessions = [dict(s, is_codex=s["name"] in codex_sessions,
                                  selected=s["name"] in self.selected)
                             for s in sessions]

    def _observe(self, pane, text, now, cfg):
        lines = [l.rstrip() for l in text.rstrip("\n").split("\n")]
        pane.preview = "\n".join(lines[-12:])
        digest = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
        changed = digest != pane.last_hash
        pane.last_hash = digest
        pane.state, pane.detail = classify(text, cfg)
        if pane.state == WORKING:
            if pane.stopped_since is not None:
                pane.note = "已恢复工作"
            pane.stopped_since = None
            pane.next_send_at = pane.wait_seconds = None
            return
        if changed or pane.stopped_since is None:
            # 内容变化（例如用户在输入、或刚刚又报错）→ 重新计时
            pane.stopped_since = now
            pane.next_send_at = pane.wait_seconds = None

    def tick(self):
        self.refresh()
        now = self.clock()
        with self.lock:
            if not self.running:
                return
            cfg = self.config
            for pane in self.panes.values():
                if pane.session not in self.selected or not pane.enabled:
                    continue
                if pane.state not in (STOPPED, CAPACITY) or pane.stopped_since is None:
                    continue
                if cfg["trigger"] == "capacity" and pane.state != CAPACITY:
                    continue
                if pane.next_send_at is None:
                    if now - pane.stopped_since >= cfg["stop_threshold"]:
                        pane.wait_seconds = self.rng.uniform(cfg["wait_min"], cfg["wait_max"])
                        pane.next_send_at = now + pane.wait_seconds
                        pane.note = f"停止超过 {cfg['stop_threshold']}s，将在 {int(pane.wait_seconds)}s 后发送"
                        self.log(f"{pane.target} {pane.note}")
                elif now >= pane.next_send_at:
                    self._send(pane, now)

    def _send(self, pane, now, manual=False):
        cfg = self.config
        if cfg["guard_composer"] and not self.tmux.composer_is_empty(pane.target):
            pane.note = "输入框非空或无法确认，跳过发送"
            self.log(f"{pane.target} {pane.note}")
            if not manual:
                pane.wait_seconds = self.rng.uniform(cfg["wait_min"], cfg["wait_max"])
                pane.next_send_at = now + pane.wait_seconds
            return False
        ok = self.tmux.send(pane.target, cfg["send_text"])
        if ok:
            pane.send_count += 1
            pane.last_sent_at = now
            pane.note = f"已{'手动' if manual else '自动'}发送 \"{cfg['send_text']}\""
        else:
            pane.note = "发送失败"
        self.log(f"{pane.target} {pane.note}")
        # 发送后重新开始计时：若仍停止，会再次等待 阈值 + 随机时长
        pane.stopped_since = now
        pane.next_send_at = pane.wait_seconds = None
        return ok

    # ---- 线程 ---------------------------------------------------------------
    def snapshot(self):
        with self.lock:
            now = self.clock()
            return {
                "now": int(now),
                "running": self.running,
                "config": dict(self.config),
                "sessions": [dict(s, selected=s["name"] in self.selected)
                             for s in self.sessions],
                "panes": [p.to_dict(now) for p in sorted(
                    self.panes.values(), key=lambda p: p.target)
                    if p.session in self.selected],
                "logs": list(self.logs)[-100:],
            }

    def run_forever(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # 保证监控线程不会意外退出
                with self.lock:
                    self.log(f"扫描出错: {exc}")
            self._wake.wait(self.config["poll"])
            self._wake.clear()

    def start(self):
        t = threading.Thread(target=self.run_forever, daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop.set()
        self._wake.set()

"""capacity_tmuxer — bin/capacity-tmuxer（bash 版）的纯 Python 移植。

适用于 Windows（PowerShell / cmd）以及没有 bash、grep、sed 等命令的环境；
Linux、macOS 同样可用。行为与 bash 版一致：

  * 监控模式：只在 pane 底部出现 "Selected model is at capacity" 且 Codex 不在
    工作时，按指数退避（BACKOFF_START..BACKOFF_MAX）提交 continue；
  * --status-pane：只读的实时状态面板（WORKING / IDLE / CAPACITY）。

用法: capacity-tmuxer.py [--status-pane|-s] [SESSION ...]
      capacity-tmuxer.py web [--host H] [--port P] [--auto] [SESSION ...]

  会话名即白名单；未给出时读取 WATCH_SESSIONS（空格或逗号分隔）。
  "web" 子命令启动中文 Web 界面（见 README）。

可调参数（环境变量，括号内为默认值）：
  POLL=15            监控模式扫描间隔（秒）
  STATUS_POLL=2      --status-pane 刷新间隔（秒）
  WINDOW=20          底部多少行算"当前"
  CAP_RE='Selected model is at capacity'   容量错误（正则，忽略大小写）
  BUSY_RE='esc to interrupt'               出现即表示 Codex 正在工作
  BACKOFF_START=30   发送后首次等待（秒）
  BACKOFF_MAX=900    退避上限（秒）
  SEND_TEXT=continue 发送的文本
  GUARD_COMPOSER=1   只在输入框为空白占位符时发送
  TMUX_CMD           指定 tmux 命令（如 "psmux" 或 "wsl -e tmux"）
"""

import os
import re
import sys
import time

import tmux_backend


def _env_int(env, name, default):
    try:
        return int(env.get(name, default))
    except (TypeError, ValueError):
        raise SystemExit(f"错误: 环境变量 {name} 必须是整数")


def load_config(env=None):
    env = os.environ if env is None else env
    return {
        "poll": _env_int(env, "POLL", 15),
        "status_poll": _env_int(env, "STATUS_POLL", 2),
        "window": _env_int(env, "WINDOW", 20),
        "cap_re": env.get("CAP_RE") or "Selected model is at capacity",
        "busy_re": env.get("BUSY_RE") or "esc to interrupt",
        "backoff_start": _env_int(env, "BACKOFF_START", 30),
        "backoff_max": _env_int(env, "BACKOFF_MAX", 900),
        "send_text": env.get("SEND_TEXT") or "continue",
        "guard_composer": env.get("GUARD_COMPOSER", "1") == "1",
    }


def bottom_slice(text, window):
    lines = text.rstrip("\n").split("\n")
    return lines[-window:] if window > 0 else []


def classify(text, cfg):
    """返回 (STATE, detail)，STATE 为 WORKING / CAPACITY / IDLE / GONE。"""
    if text is None:
        return "GONE", ""
    busy = re.compile(cfg["busy_re"], re.I)
    cap = re.compile(cfg["cap_re"], re.I)
    tail = bottom_slice(text, cfg["window"])
    for line in tail:
        if busy.search(line):
            return "WORKING", line.strip()
    if any(cap.search(line) for line in tail):
        return "CAPACITY", "at capacity — waiting to resubmit"
    return "IDLE", ""


class Watcher:
    """监控模式的核心逻辑；tmux 与时钟可注入以便测试。"""

    def __init__(self, sessions, cfg, tmux, clock=time.time, out=print):
        self.sessions = sessions
        self.cfg = cfg
        self.tmux = tmux
        self.clock = clock
        self.out = out
        self.backoff = {}
        self.last_ts = {}

    def stamp(self):
        return time.strftime("%H:%M:%S", time.localtime(self.clock()))

    def scan_once(self):
        cfg = self.cfg
        for sess in self.sessions:
            for pane in self.tmux.list_panes(sess):
                target = pane["target"]
                text = self.tmux.capture(target)
                if text is None:
                    continue
                state, _ = classify(text, cfg)
                if state == "WORKING":
                    self.backoff[target] = cfg["backoff_start"]  # 恢复后重新开始
                    continue
                if state != "CAPACITY":
                    continue
                backoff = self.backoff.get(target, cfg["backoff_start"])
                if self.clock() - self.last_ts.get(target, 0) < backoff:
                    continue
                if cfg["guard_composer"] and not self.tmux.composer_is_empty(target):
                    self.out(f"{self.stamp()}  skip {target}: composer not empty (guard)")
                    continue
                self.tmux.send(target, cfg["send_text"])
                self.last_ts[target] = self.clock()
                backoff = min(backoff * 2, cfg["backoff_max"])
                self.backoff[target] = backoff
                self.out(f'{self.stamp()}  sent "{cfg["send_text"]}" -> {target} '
                         f"(next backoff {backoff}s)")

    def run(self):
        self.out(f"watching sessions: {' '.join(self.sessions)}  "
                 f"(poll {self.cfg['poll']}s, cap_re={self.cfg['cap_re']!r}, "
                 f"tmux={tmux_backend.describe(self.tmux.cmd)})")
        while True:
            self.scan_once()
            time.sleep(self.cfg["poll"])


def render_status(sessions, cfg, tmux):
    rows = [f"capacity-tmuxer  {time.strftime('%H:%M:%S')}   sessions: "
            f"{' '.join(sessions)}   (refresh {cfg['status_poll']}s)", "",
            f"{'PANE':<18}  {'STATE':<9}  DETAIL",
            f"{'------':<18}  {'-----':<9}  ------"]
    for sess in sessions:
        for pane in tmux.list_panes(sess):
            state, detail = classify(tmux.capture(pane["target"]), cfg)
            rows.append(f"{pane['target']:<18}  {state:<9}  {detail}")
    return "\n".join(rows)


def run_status_pane(sessions, cfg, tmux):
    sys.stdout.write("\033[?25l")                      # 隐藏光标
    try:
        while True:
            sys.stdout.write("\033[H\033[2J" + render_status(sessions, cfg, tmux) + "\n")
            sys.stdout.flush()
            time.sleep(cfg["status_poll"])
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\n")                # 恢复光标
        sys.stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    tmux_backend.enable_windows_ansi()

    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__.strip())
        return 0
    if argv[:1] == ["web"]:
        import web_server
        return web_server.main(argv[1:])

    status_mode = False
    if argv[:1] in (["--status-pane"], ["-s"]):
        status_mode = True
        argv = argv[1:]

    cfg = load_config()
    sessions = argv or [s for s in re.split(r"[,\s]+", os.environ.get("WATCH_SESSIONS", "")) if s]
    if not sessions:
        print("error: no sessions given (pass as args or set WATCH_SESSIONS)", file=sys.stderr)
        print("try: capacity-tmuxer --help", file=sys.stderr)
        return 2

    tmux = tmux_backend.Tmux()
    if not tmux.available:
        print("error: tmux not found (install tmux / psmux, use WSL, or set TMUX_CMD)",
              file=sys.stderr)
        return 127

    try:
        if status_mode:
            run_status_pane(sessions, cfg, tmux)
        else:
            Watcher(sessions, cfg, tmux, out=lambda m: print(m, flush=True)).run()
    except KeyboardInterrupt:
        pass
    return 0

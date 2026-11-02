"""tmux_backend — 跨平台的 tmux 调用封装（Linux / macOS / Windows）。

只依赖 Python 3.8+ 标准库，不需要 bash、grep、sed 等命令。

tmux 命令的选择顺序：
  1. 环境变量 TMUX_CMD（例如 "tmux"、"psmux"、"wsl -e tmux"、
     "C:\\msys64\\usr\\bin\\tmux.exe"）；
  2. PATH 中的 tmux（Linux、macOS、MSYS2、Cygwin、Git Bash 等）；
  3. PATH 中的 psmux（Windows 原生、兼容 tmux 命令的实现）；
  4. Windows 下若有 wsl，则使用 WSL 内的 tmux（wsl -e tmux）。
"""

import os
import shlex
import shutil
import subprocess
import sys
import time

import composer_guard

IS_WINDOWS = os.name == "nt"


def detect_tmux_command(env=None, which=shutil.which, windows=IS_WINDOWS):
    """返回 tmux 命令前缀（列表）；找不到时返回 None。"""
    env = os.environ if env is None else env
    override = (env.get("TMUX_CMD") or "").strip()
    if override:
        if windows and os.path.exists(override):
            return [override]          # 含空格的 Windows 路径
        return shlex.split(override, posix=not windows) if not windows \
            else [p.strip('"') for p in shlex.split(override, posix=False)]
    for name in ("tmux", "psmux"):
        path = which(name)
        if path:
            return [path]
    if windows and which("wsl"):
        return ["wsl", "-e", "tmux"]
    return None


def describe(cmd):
    return " ".join(cmd) if cmd else "(未找到)"


class Tmux:
    """对 tmux 命令的薄封装。所有方法失败时返回 None/False/空列表，不抛异常。"""

    def __init__(self, cmd=None):
        self.cmd = cmd if cmd is not None else detect_tmux_command()

    @property
    def available(self):
        return bool(self.cmd)

    def _run(self, *args):
        if not self.cmd:
            return None
        kwargs = {}
        if IS_WINDOWS:
            # 不弹出控制台窗口
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            res = subprocess.run(list(self.cmd) + list(args), capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=10,
                                 **kwargs)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if res.returncode != 0:
            return None
        return res.stdout.replace("\r\n", "\n")

    def list_sessions(self):
        out = self._run("list-sessions", "-F",
                        "#{session_name}\t#{session_windows}\t#{session_attached}")
        sessions = []
        for line in (out or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                try:
                    windows = int(parts[1] or 0)
                except ValueError:
                    windows = 0
                sessions.append({"name": parts[0], "windows": windows,
                                 "attached": parts[2] not in ("", "0")})
        return sessions

    def list_panes(self, session=None):
        fmt = ("#{session_name}\t#{session_name}:#{window_index}.#{pane_index}"
               "\t#{pane_current_command}")
        if session is None:
            out = self._run("list-panes", "-a", "-F", fmt)
        else:
            out = self._run("list-panes", "-s", "-t", session, "-F", fmt)
        panes = []
        for line in (out or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                panes.append({"session": parts[0], "target": parts[1],
                              "command": parts[2]})
        return panes

    def capture(self, target, ansi=False):
        args = ["capture-pane", "-p", "-t", target]
        if ansi:
            args.insert(1, "-e")
        return self._run(*args)

    def send(self, target, text):
        # -l 按字面发送；部分 tmux 兼容实现不支持 -l，则退回普通 send-keys
        if self._run("send-keys", "-t", target, "-l", text) is None:
            if self._run("send-keys", "-t", target, text) is None:
                return False
        time.sleep(0.4)  # 让输入框稳定后再回车
        return self._run("send-keys", "-t", target, "Enter") is not None

    def composer_is_empty(self, target):
        """输入框是否为空白占位符（纯 Python 判断，失败即视为非空）。"""
        frame = self.capture(target, ansi=True)
        if frame is None:
            return False
        return composer_guard.frame_is_empty(frame.rstrip("\n"))


def enable_windows_ansi():
    """让 Windows 控制台识别 ANSI 转义序列（Windows 10+）。"""
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

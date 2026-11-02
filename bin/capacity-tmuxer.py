#!/usr/bin/env python3
"""capacity-tmuxer 的 Python 版入口（Windows / Linux / macOS 通用，无需 bash）。

  python bin/capacity-tmuxer.py [--status-pane] SESSION ...   # 命令行监控
  python bin/capacity-tmuxer.py web [--auto] [--port 8765]    # 中文 Web 界面
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "lib"))

import capacity_tmuxer  # noqa: E402

if __name__ == "__main__":
    sys.exit(capacity_tmuxer.main())

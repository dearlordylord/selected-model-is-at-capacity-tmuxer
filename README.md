# selected-model-is-at-capacity-tmuxer

[English](README.en.md) | 中文

**当 [Codex CLI](https://github.com/openai/codex) 因
`Selected model is at capacity. Please try a different model.` 停下时，自动让它继续。**

如果你在 **tmux** 里运行 Codex 智能体，并且经常遇到

> ⚠ Selected model is at capacity. Please try a different model.

……智能体就会一直停在那里，直到你注意到并手动推它一下。本项目是一个小巧的
`bash` + `tmux` 看门狗：它监控指定的 tmux 会话，发现 Codex 停下（例如
"Selected model is at capacity"）后，自动提交 `continue`，让智能体继续工作——
同一个模型，无需人工看守。

现在还提供了一个 **中文 Web 界面**（`capacity-tmuxer-web`）：自动发现 tmux 会话
供你勾选，显示每个 Codex 任务的实时状态，并在停止超过 30 秒后随机等待 1–5 分钟
再发送 `continue`。

除了 `bash`、`tmux` 和标准 Unix 工具（Web 界面另需 Python 3，仅使用标准库）外
没有其他依赖。**Windows 用户**可以使用纯 Python 版本（不需要 bash、grep、sed 等
命令），在 PowerShell 中配合 tmux / psmux / WSL 中的 tmux 运行，详见
[Windows 支持](#windows-支持)。它从不改动 Codex 本身，只通过 `tmux capture-pane` 读取画面，
通过 `tmux send-keys` 输入文本。

## 演示

![capacity-tmuxer 检测到容量错误并提交 `continue`，Codex 恢复工作](docs/usage-demo.gif)

## 为什么用 tmux

Codex 的 TUI 是 **内联** 渲染的（不使用备用屏幕），所以它的对话记录就在普通的
tmux 回滚缓冲区里。这意味着 tmux 能读取 Codex 正在显示的画面，并向它的输入框
打字——不需要 API，也不需要插件。把 Codex 智能体跑在 tmux pane 里，再让本工具
指向这些会话即可。

## 环境要求

- `tmux`
- `bash`
- 标准 Unix 工具（`date`、`dirname`、`grep`、`readlink`、`sed`、`sleep`、`tail`）
- Python 3.8+（Web 界面与 Python 版需要，无第三方依赖）
- 运行在 tmux pane **内部** 的 Codex CLI

## 安装

```sh
git clone https://github.com/dearlordylord/selected-model-is-at-capacity-tmuxer.git
cd selected-model-is-at-capacity-tmuxer
chmod +x bin/capacity-tmuxer bin/capacity-tmuxer-web bin/capacity-tmuxer.py
# 可选：加入 PATH
ln -s "$PWD/bin/capacity-tmuxer" ~/.local/bin/capacity-tmuxer
ln -s "$PWD/bin/capacity-tmuxer-web" ~/.local/bin/capacity-tmuxer-web
```

## Windows 支持

Windows 下很多命令（`bash`、`grep`、`sed`、`tail` 等）不存在，因此提供了一个
**纯 Python 版本**，功能与 bash 版相同，只需要：

- Python 3.8+（[python.org](https://www.python.org/downloads/) 或
  `winget install Python.Python.3.12`）
- 以下任意一种 tmux：
  - **WSL 中的 tmux**（推荐）：在 WSL 里用 tmux 运行 Codex，Windows 端会自动通过
    `wsl -e tmux` 访问；
  - **MSYS2 / Cygwin / Git Bash 中的 tmux**：`tmux.exe` 在 PATH 中即可；
  - **psmux** 等 Windows 原生、兼容 tmux 命令的实现（需支持 `list-panes -F`、
    `capture-pane -p -e`、`send-keys`）。

tmux 命令按以下顺序自动查找：环境变量 `TMUX_CMD` → PATH 中的 `tmux` → `psmux`
→ `wsl -e tmux`。也可以手动指定：

```powershell
$env:TMUX_CMD = "wsl -e tmux"
$env:TMUX_CMD = "C:\msys64\usr\bin\tmux.exe"
```

在 PowerShell 中使用：

```powershell
git clone https://github.com/dearlordylord/selected-model-is-at-capacity-tmuxer.git
cd selected-model-is-at-capacity-tmuxer

# 中文 Web 界面（推荐），然后打开 http://127.0.0.1:8765
.\bin\capacity-tmuxer-web.ps1 --auto

# 命令行监控（与 bash 版相同的参数和环境变量）
.\bin\capacity-tmuxer.ps1 43 44
$env:POLL = "10"; .\bin\capacity-tmuxer.ps1 my-agent

# 状态面板
.\bin\capacity-tmuxer.ps1 --status-pane 43 44
```

如果提示"无法加载文件，因为在此系统上禁止运行脚本"，可以只对本次运行放开：

```powershell
powershell -ExecutionPolicy Bypass -File .\bin\capacity-tmuxer-web.ps1 --auto
```

cmd.exe 下可用 `bin\capacity-tmuxer.cmd` / `bin\capacity-tmuxer-web.cmd`；
也可以直接用 Python 运行（任何平台通用）：

```sh
python bin/capacity-tmuxer.py 43 44            # 命令行监控
python bin/capacity-tmuxer.py --status-pane 43 # 状态面板
python bin/capacity-tmuxer.py web --auto       # Web 界面
```

| 文件 | 用途 |
|---|---|
| `bin/capacity-tmuxer` | 原 bash 版（Linux / macOS） |
| `bin/capacity-tmuxer.py` | Python 版入口（全平台），`web` 子命令启动 Web 界面 |
| `bin/capacity-tmuxer.ps1`、`bin/capacity-tmuxer-web.ps1` | PowerShell 启动脚本 |
| `bin/capacity-tmuxer.cmd`、`bin/capacity-tmuxer-web.cmd` | cmd.exe 启动脚本 |
| `bin/capacity-tmuxer-web` | Web 界面（Linux / macOS） |
| `lib/composer_guard.py` | 输入框保护的 Python 移植，与 bash 版共用测试样例 |
| `lib/tmux_backend.py` | 跨平台 tmux 调用（自动识别 tmux / psmux / WSL） |

## Web 界面（推荐）

```sh
capacity-tmuxer-web --auto
# 然后在浏览器打开 http://127.0.0.1:8765
```

功能：

1. **自动发现 tmux 会话**：列出所有 tmux 会话，自动识别正在运行 Codex 的会话
   （带 `Codex` 标签），勾选即开始监控；也可一键"选中全部 Codex 会话"。
2. **停止检测与随机续跑**：某个 pane 中 Codex 的"工作中"标识（`esc to interrupt`）
   消失，且画面持续不变超过 **30 秒**，就判定为已停止；随后随机等待
   **1–5 分钟**（每次重新随机）再发送 `continue`。如果发送后仍然停止，会重新
   计时并再次随机等待。期间一旦 Codex 恢复工作，计划自动取消。
3. **实时状态**：每个 pane 显示状态（工作中 / 容量不足已停止 / 已停止 / 已消失）、
   已停止时长、发送倒计时、本次随机等待时长、累计发送次数、最近动作以及屏幕预览。
4. **在线调整参数**：阈值、等待范围、发送文本、触发条件（任何停止 / 仅容量错误）、
   输入框静默时间等都可以在页面上修改并立即生效。
5. **手动控制**：全局暂停/启动自动发送、按 pane 禁用自动发送、每个任务的"立即发送"
   按钮，以及向所有未在工作的任务发送的"全部立即发送"按钮。
6. **日志**：所有检测与发送动作都会记录在页面底部。

命令行参数：

| 参数 | 说明 |
|---|---|
| `会话名 ...` | 启动时即监控这些会话 |
| `--auto` | 启动时自动选中所有检测到 Codex 的会话 |
| `--paused` | 启动时暂停自动发送（只显示状态） |
| `--host` | 监听地址，默认 `127.0.0.1`（环境变量 `WEB_HOST`） |
| `--port` | 监听端口，默认 `8765`（环境变量 `WEB_PORT`） |
| `TMUX_CMD` | 环境变量，指定 tmux 命令（见 Windows 支持） |

后台运行：

```sh
nohup capacity-tmuxer-web --auto > ~/capacity-tmuxer-web.log 2>&1 &
```

> 安全提示：该页面可以向你的终端输入文本，默认只监听 `127.0.0.1`。不要在没有
> 额外保护的情况下把它暴露到公网。

页面上的默认参数：

| 参数 | 默认值 | 含义 |
|---|---|---|
| 停止判定阈值 | `30` 秒 | 停止多久后开始计划发送 |
| 随机等待下限 / 上限 | `60` / `300` 秒 | 每次发送前的随机等待范围 |
| 扫描间隔 | `5` 秒 | 多久扫描一次 tmux |
| 发送文本 | `continue` | 用于让智能体继续的文本 |
| 触发条件 | 任何停止 | 也可设为"仅模型容量不足错误" |
| 输入框静默时间 | `20` 秒 | 输入框内容在最近这段时间内有变化（你正在输入）则跳过发送；`0` 表示不检查 |
| 检测窗口 | `20` 行 | 画面底部多少行算"当前" |

## 命令行模式

把运行 Codex 的 tmux 会话加入白名单（会话名作为参数）：

```sh
capacity-tmuxer 43 44 my-agent
```

或者通过环境变量指定，并在后台运行以持续监控：

```sh
WATCH_SESSIONS="43 44" nohup capacity-tmuxer > ~/capacity-tmuxer.log 2>&1 &
tail -f ~/capacity-tmuxer.log
```

`--help` 会打印完整的选项列表。命令行模式只在检测到容量错误时发送，并使用指数退避。

### 实时状态面板（可选）

Codex 是内联渲染的，它自己的状态栏不会固定在底部。`--status-pane` 提供了一个
合成的状态栏：实时刷新每个被监控 pane 的状态（`WORKING` 工作中 / `IDLE` 空闲 /
`CAPACITY` 容量不足）。可以把它放在底部的一个小分屏里：

```sh
# 分出一个较矮的 pane 来显示状态
tmux split-window -v -l 8 'capacity-tmuxer --status-pane 43 44'
```

```
capacity-tmuxer  13:01:06   sessions: 43 44 40   (refresh 2s)

PANE                STATE      DETAIL
------              -----      ------
43:0.0              CAPACITY   at capacity — waiting to resubmit
44:0.0              WORKING    • Working (25s • esc to interrupt)
40:0.0              IDLE
```

该模式是只读的——从不发送按键。可以和监控进程同时运行（它们是相互独立的进程）。

## 如何决定发送（只在消息"新鲜"时）

容量错误的文本本身没有"新鲜度"标记，所以工具从不仅凭文本存在就发送。只有当
三个与滚动无关的事实同时成立时才发送——因此你已经滚过去的旧消息、或已在重试中的
消息都会被忽略：

1. **位置**——只有 pane 实时画面的底部一段才算数（即使你在 copy-mode 中向上
   滚动，`capture-pane` 读取的也是实时网格——已验证），所以折叠线以上的消息不会匹配。
2. **空闲**——Codex 的忙碌标识（`esc to interrupt`）必须 **不存在**，证明它确实
   停下了，而不是仍在工作。
3. **边沿而非电平**——进入停止状态时才发送，之后按退避（命令行模式）或随机等待
   （Web 模式）重试；一旦看到 Codex 重新工作，计时就会重置。

## 安全性

- **输入框静默检查（Web 界面，默认 20 秒）**——工具每次扫描都会记录输入框的内容；
  如果输入框内容在最近 20 秒内有变化（说明你正在输入），就跳过这次发送，并在静默期
  结束后再检查。输入框里有内容但已超过 20 秒没动，则不再跳过。"立即发送"和
  "全部立即发送"同样遵守这条规则。可在页面上调整秒数，`0` 为关闭检查。
- **输入框保护（命令行模式，默认开启）**——命令行版只有当输入框是空白的暗色占位符时
  才发送。如果输入框里有你打了一半的提示词，工具会检测到并跳过，绝不覆盖你的文字。
  失败即安全：无法确认输入框为空时就跳过。
- **只读检测**——唯一的写操作是 `send-keys "continue"` + `Enter`，并且只会发往
  通过上述所有检查的 pane。
- **退避 / 随机等待**——命令行模式下，反复回到容量错误的 pane 按
  `30s → ×2 → 900s` 的节奏重试；Web 模式下每次随机等待 1–5 分钟，不会狂刷。

## 配置（命令行模式）

所有可调参数都是环境变量：

| 变量 | 默认值 | 含义 |
|---|---|---|
| `POLL` | `15` | 扫描间隔秒数（监控模式） |
| `STATUS_POLL` | `2` | 刷新间隔秒数（`--status-pane` 模式） |
| `WINDOW` | `20` | 底部多少行算"当前/最后" |
| `CAP_RE` | `Selected model is at capacity` | 要匹配的容量错误消息（`grep -i`） |
| `BUSY_RE` | `esc to interrupt` | 出现即表示 Codex 正在工作 |
| `BACKOFF_START` | `30` | 发送后的首次等待（秒） |
| `BACKOFF_MAX` | `900` | 退避上限（秒） |
| `SEND_TEXT` | `continue` | 用于让智能体继续的文本 |
| `GUARD_COMPOSER` | `1` | 发送前要求输入框为空 |
| `WATCH_SESSIONS` | — | 未提供参数时使用的白名单 |

## 注意事项

- **同一个模型。** 它向 *同一个* 模型（即容量不足的那个）重新提交，对应"直接重试"
  的工作流程。如果容量问题持续，退避/随机等待会拉开重试间隔。切换模型不在本工具范围内。
- **Codex 文案。** `CAP_RE` 匹配目前观察到的字符串 `Selected model is at capacity`。
  如果将来的 Codex 版本修改了这条消息，请更新 `CAP_RE`。
- **"任何停止"模式。** Web 界面默认在 Codex 任何形式的停止（包括任务完成后空闲）
  后都会发送 `continue`，适合长时间目标任务。如果只想处理容量错误，请把触发条件
  改为"仅模型容量不足错误"。
- **画面持续变化。** Web 模式下，画面内容变化（例如你正在输入）会重置停止计时；
  如果 pane 中有持续变化的内容，则不会触发发送。
- **输入框内容的识别。** Web 模式取画面中最后一个以 `›` 或 `»` 开头的行（及其后连续的
  非空行）作为输入框内容；找不到提示符行时视为"无输入框"，不影响发送。
- **输入框提示符。** 命令行模式的输入框保护依据 Codex 的 `›` 与 `»` 提示符变体及其暗色占位符
  样式。未知的提示符或终端格式会按"失败即关闭"处理。如果 Codex 的渲染方式变了，
  可以设置 `GUARD_COMPOSER=0`（代价是失去半截提示词保护），
  或者新增提示符策略和抓取的画面样例。

## 测试

输入框分类器使用抓取的 ANSI 画面独立于 tmux 进行测试（bash 版与 Python 版共用
同一套样例）；Web 监控逻辑与 Python 版命令行使用模拟的 tmux 与时钟进行测试：

```sh
bash test/composer-guard-test.bash      # bash 版输入框保护
python3 test/composer-guard-test.py     # Python 版输入框保护（Windows 可用）
python3 test/codex-monitor-test.py      # Web 监控逻辑
python3 test/capacity-tmuxer-test.py    # Python 版命令行与 tmux 识别
```

Windows 下把 `python3` 换成 `python` 或 `py -3` 即可。

## 许可证

[MIT](LICENSE)

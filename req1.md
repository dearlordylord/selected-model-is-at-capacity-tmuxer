## 监控codex /goal中止状态并继续
1. 将readme翻译成中文， 提供web界面方便操作
2. 自动寻找tmux session，列表供用户选择
3. 用于监控tmux中codex使用/goal 启动的任务
   如果发现"Goal stalled (/goal resume)", 时间超过30s，在1-3分钟内发送continue， 进入等待continue状态， 如果continue了5分钟后还是Goal stalled状态， 则在random(1-5)分钟内发送"/goal resume"
4. 显示每个tmux codex任务当前状态，如 Pursuing goal (4m)

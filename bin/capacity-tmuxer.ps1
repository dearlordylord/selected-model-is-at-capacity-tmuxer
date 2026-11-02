<#
.SYNOPSIS
  capacity-tmuxer 的 PowerShell 启动脚本（调用 Python 版，无需 bash）。

.EXAMPLE
  .\bin\capacity-tmuxer.ps1 43 44              # 命令行监控
  .\bin\capacity-tmuxer.ps1 --status-pane 43   # 状态面板
  .\bin\capacity-tmuxer.ps1 web --auto         # 中文 Web 界面
  $env:TMUX_CMD = "wsl -e tmux"; .\bin\capacity-tmuxer.ps1 web --auto
#>
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'capacity-tmuxer.py'

# 依次尝试 py -3、python3、python（跳过 Windows 应用商店的占位 python.exe）
$exe = $null
$pyArgs = @()
foreach ($name in 'py', 'python3', 'python') {
    $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike '*\WindowsApps\*' } |
        Select-Object -First 1
    if ($cmd) {
        $exe = $cmd.Source
        if ($name -eq 'py') { $pyArgs = @('-3') }
        break
    }
}
if (-not $exe) {
    Write-Error '找不到 Python 3（需要 3.8 或更高版本）。请从 https://www.python.org/downloads/ 安装，或运行: winget install Python.Python.3.12'
    exit 127
}

$env:PYTHONUTF8 = '1'
& $exe @pyArgs $script @args
exit $LASTEXITCODE

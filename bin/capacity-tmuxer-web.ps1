<#
.SYNOPSIS
  启动 Codex 自动续跑监控的中文 Web 界面（PowerShell）。

.EXAMPLE
  .\bin\capacity-tmuxer-web.ps1 --auto
  .\bin\capacity-tmuxer-web.ps1 --port 9000 my-session
#>
& (Join-Path $PSScriptRoot 'capacity-tmuxer.ps1') web @args
exit $LASTEXITCODE

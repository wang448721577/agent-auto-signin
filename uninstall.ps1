# 卸载：删除计划任务（不删除任何签到脚本与日志）
param([string]$TaskName = "agent-auto-signin(手动)")

$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($t) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[OK] 已删除计划任务：$TaskName" -ForegroundColor Green
} else {
    Write-Host "[!] 未找到计划任务：$TaskName" -ForegroundColor Yellow
}

Write-Host "如需彻底清理，可再手动删除 config.json、.cache/、shots/、*.log" -ForegroundColor Gray

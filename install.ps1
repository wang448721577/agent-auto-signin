# agent-auto-signin 安装脚本（Windows PowerShell 5.1+）
# 作用：检测环境 → 生成 config.json → 注册「仅手动触发、无控制台窗口」的计划任务
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Run            # 装完立刻跑一次
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Daily 09:00    # 每天 09:00 自动跑
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Python "C:\Python311\python.exe"
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall

param(
    [string]$Python = "",
    [switch]$Run,
    [string]$Daily = "",
    [switch]$SkipDeps,
    [switch]$Uninstall,
    [string]$TaskName = "agent-auto-signin(手动)"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dailyAll = Join-Path $root "daily_all.py"

function Write-Step($msg) { Write-Host "[*] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "[!] $msg" -ForegroundColor Yellow }

# ---------- 卸载 ----------
if ($Uninstall) {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Ok "已删除计划任务：$TaskName"
    } else {
        Write-Warn2 "未找到计划任务：$TaskName"
    }
    return
}

Write-Step "项目目录：$root"

# ---------- 1. 找 Python ----------
if (-not $Python) {
    $cands = @()
    $cands += (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    $cands += (Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    foreach ($p in @("C:\Python313\python.exe", "C:\Python312\python.exe", "C:\Python311\python.exe")) {
        if (Test-Path $p) { $cands += $p }
    }
    foreach ($c in $cands) { if ($c -and (Test-Path $c)) { $Python = $c; break } }
}
if (-not $Python -or -not (Test-Path $Python)) {
    throw "未找到 python.exe，请用 -Python 指定，例如 -Python `"C:\Python311\python.exe`""
}
Write-Ok "Python：$Python"
$pyw = Join-Path (Split-Path $Python -Parent) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $Python }
Write-Ok "静默解释器：$pyw"

# ---------- 2. 依赖 ----------
if (-not $SkipDeps) {
    Write-Step "安装依赖（pywinauto psutil pillow pywin32 cryptography）"
    & $Python -m pip install --disable-pip-version-check -q -r (Join-Path $root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "依赖安装返回非 0，可稍后手动执行 pip install -r requirements.txt" }
    else { Write-Ok "依赖就绪" }
}

# ---------- 3. 探测路径并写 config.json ----------
Write-Step "探测客户端安装路径"
Push-Location $root
$probe = & $Python -c "import json,client_daily as c;print(json.dumps({k:c.CLIENTS[k]['exe'] for k in c.ORDER},ensure_ascii=False))" 2>$null
$wb = & $Python -c "import run_daily_win as r;print(r.WB88 or '')" 2>$null
Pop-Location

$clients = @{}
$missing = @()
if ($probe) {
    $obj = $probe | ConvertFrom-Json
    foreach ($p in $obj.PSObject.Properties) {
        $clients[$p.Name] = @{ exe = $p.Value }
        if (Test-Path $p.Value) { Write-Ok ("  {0}: {1}" -f $p.Name, $p.Value) }
        else { $missing += $p.Name; Write-Warn2 ("  {0}: 未找到（{1}）" -f $p.Name, $p.Value) }
    }
} else {
    Write-Warn2 "路径探测失败，可手动编写 config.json"
}

$cfg = [ordered]@{}
$cfg["python"] = $Python
if ($wb) { $cfg["workbuddy_signin"] = $wb }
if ($clients.Count -gt 0) { $cfg["clients"] = $clients }
$cfgJson = $cfg | ConvertTo-Json -Depth 5
$cfgPath = Join-Path $root "config.json"
[System.IO.File]::WriteAllText($cfgPath, $cfgJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "已写入 $cfgPath"

if ($missing.Count -gt 0) {
    Write-Warn2 ("以下客户端未安装或路径未探测到，对应端会报路径不存在：{0}" -f ($missing -join ", "))
}

# ---------- 4. 注册计划任务 ----------
Write-Step "注册计划任务：$TaskName"
$action = New-ScheduledTaskAction -Execute $pyw -Argument ('"' + $dailyAll + '"') -WorkingDirectory $root
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

if ($Daily) {
    $triggerTime = [datetime]::ParseExact($Daily, "HH:mm", $null)
    $trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime
    Register-ScheduledTask -TaskName $TaskName -TaskPath "\" -Action $action -Trigger $trigger -Settings $settings `
        -Description "AI 桌面端每日签到（接口 + 客户端），每天 $Daily 自动运行" -Force | Out-Null
    Write-Ok "已注册（每日 $Daily 触发）"
} else {
    Register-ScheduledTask -TaskName $TaskName -TaskPath "\" -Action $action -Settings $settings `
        -Description "AI 桌面端每日签到（接口 + 客户端），无自动触发器，只能手动启动" -Force | Out-Null
    Write-Ok "已注册（仅手动触发，0 个自动触发器）"
}

$t = Get-ScheduledTask -TaskName $TaskName
Write-Host ""
Write-Host ("任务：{0} | 状态：{1} | 触发器：{2}" -f $t.TaskName, $t.State, $t.Triggers.Count) -ForegroundColor Gray
Write-Host ("启动命令：Start-ScheduledTask -TaskName `"{0}`"" -f $TaskName) -ForegroundColor Gray
Write-Host ("日志：{0}" -f (Join-Path $root "daily_all.log")) -ForegroundColor Gray

if ($Run) {
    Write-Step "立即运行一次"
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 8
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Ok ("已启动，状态：{0}" -f (Get-ScheduledTask -TaskName $TaskName).State)
}

Write-Host ""
Write-Host "完成。建议先跑 python scripts/doctor.py 自检。" -ForegroundColor Green

# agent-auto-signin

> 一键完成九款 AI 桌面客户端的每日签到与积分领取，逐端输出人话结果。Windows 专用，纯本地凭据，零内置密钥。

覆盖 **9 个平台 / 11 个签到端点**（Trae 与 MiniMax 同时具备接口与客户端两条通道）：

| 类别 | 端点 | 说明 |
| --- | --- | --- |
| 接口类（4 个） | WorkBuddy、Trae、MiniMax Code、百度搭子 | 纯 HTTP，读取本机登录态直调官方接口，可后台无人值守 |
| 客户端类（7 个） | MiniMax、Trae CN、豆包、扣子、智谱清言、AS Studio、ima | Windows UI Automation 点击，需桌面会话 |

## 特性

- **幂等**：先查状态，未签才领；重复运行不会多领。
- **两类解耦**：`--api-only` / `--gui-only` 可分别跑，接口类挂了不影响客户端类，反之亦然。
- **可移植**：客户端 exe 路径自动探测（`%LOCALAPPDATA%\Programs`、`%ProgramFiles%`、其它盘的用户目录…），也支持 `config.json` 显式覆盖；不依赖任何桌面快捷方式。
- **自动收尾**：客户端类跑完自动关闭除 ima 外的所有客户端进程，WorkBuddy 不受影响。
- **留痕可查**：每端一行 JSON + 末行汇总；失败自动截图到 `shots/`，日志落 `daily_all.log` / `client_daily.log`。
- **不碰凭据**：只判断凭据文件是否可读，从不打印 token / cookie。

## 快速开始

```bash
pip install -r requirements.txt
python scripts/doctor.py        # 自检：依赖 / 客户端路径 / 凭据文件
python daily_all.py --api-only  # 先跑接口类（最稳）
python daily_all.py             # 全量：接口 + 客户端
```

单端调试：

```bash
python client_daily.py coze doubao
python run_daily_win.py trae dumate
```

## 做成定时任务（仅手动触发，无控制台窗口）

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1          # 注册任务
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Run     # 注册后立即跑一次
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Daily 09:00   # 需要每天自动跑
```

任务名 `agent-auto-signin(手动)`，动作 `pythonw.exe daily_all.py`，默认 **0 个触发器**（只手动启动），
可在任务计划程序里右键「运行」，或：

```powershell
Start-ScheduledTask -TaskName "agent-auto-signin(手动)"
```

卸载：`powershell -ExecutionPolicy Bypass -File .\uninstall.ps1`

## 结果码

`CLAIMED` 领取成功 · `ALREADY` 今日已签 · `GROWTH`/`DONE`/`LOGGED_IN` 完成 · `SKIP` 未配置/不可用 ·
`INACTIVE` 活动未开 · `PENDING` 待领 · `NO_SESSION` 登录过期（重开客户端一次） · `NO_AUTH` 未登录 ·
`LAUNCH_FAILED` 无桌面会话 · `ERROR`/`TIMEOUT` 见 report 与 `shots/`

## 配置（可选）

根目录放 `config.json`（已在 `.gitignore` 中）：

```json
{
  "python": "C:/Python311/python.exe",
  "workbuddy_signin": "D:/tools/workbuddy-auto-signin/signin.py",
  "clients": { "coze": { "exe": "D:/Program Files/Coze/Coze.exe" } }
}
```

## 作为 WorkBuddy 技能使用

本仓库根目录自带 `SKILL.md`，把整个目录放进下列任一位置即可被识别：

- 用户级：`~/.workbuddy/skills/agent-auto-signin/`
- 项目级：`{项目}/.workbuddy/skills/agent-auto-signin/`

之后直接说「帮我签到」「领今天的 AI 积分」即可触发。

## 已知限制

- WorkBuddy 端依赖 [88lin/workbuddy-auto-signin](https://github.com/88lin/workbuddy-auto-signin) 的 `signin.py`（支持加密凭据）。未安装时该端记 `SKIP`，其余端不受影响。
- Trae 接口领取自 2026-10-18 起可能返回 `code 9004`（服务端策略，非脚本问题）；脚本会将「订单重复」判定为已签，长期失败请改用 Trae 桌面端 GUI 签到。
- 豆包不暴露 UIA 控件树，签到按钮用颜色定位（实心蓝 `RGB(79,139,247)`）；卡片当天只弹一次，未弹出时记 `ALREADY` 并保存截图。
- 客户端 UI 改版会导致点击失效，此时看 `shots/` 截图更新选择器即可。

## 免责声明

本项目仅自动化「你自己账号」在本机客户端上的日常签到操作，不包含任何绕过、破解或批量行为。
接口由桌面端逆向而来，官方改版后可能失效。请遵守各平台用户协议，风险自负。

## License

MIT

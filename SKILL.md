---
name: agent-auto-signin
description: 一键完成 AI 桌面端每日签到与积分领取（WorkBuddy / Trae / MiniMax Code / 百度搭子 / 扣子 / 豆包 / 智谱清言 / AS Studio / ima）。当用户说「帮我签到」「领一下今天的 AI 积分」「跑一下自动签到」「看看今天签到结果」或需要把签到做成定期任务时使用。包含接口类（纯 HTTP，无人值守）与客户端类（Windows UI Automation 点击）两套实现，可只跑接口、只跑客户端或全量。
agent_created: true
---

# AI 桌面端每日签到（agent-auto-signin）

## 用途

一次性完成多款 AI 桌面客户端的每日签到 / 积分领取，并给出逐端结果 JSON。
分成两类实现，互不依赖：

| 类别 | 覆盖 | 依赖 | 可靠性 |
| --- | --- | --- | --- |
| 接口类（`run_daily_win.py`） | WorkBuddy、Trae、MiniMax Code、百度搭子（4 个端点） | 只需本地登录态，纯 HTTP | 高，可在后台跑 |
| 客户端类（`client_daily.py`） | MiniMax、Trae、豆包、扣子、智谱清言、AS Studio、ima（7 个端点） | 需要桌面会话 + UI Automation | 中，UI 改版可能失效 |

## 使用前提

1. Windows 10/11，且这些客户端**已安装并登录过**（脚本只读本机凭据，不含任何密钥）。
2. Python 3.9+，并安装依赖：`pip install -r requirements.txt`
   （`pywinauto`、`psutil`、`pillow`、`pywin32`、`cryptography`）。
3. 客户端类必须在**有桌面会话的环境**运行；后台/无桌面会话里 Electron 客户端会启动即退出，脚本会报 `LAUNCH_FAILED`。
4. WorkBuddy 端的接口签到依赖 [88lin/workbuddy-auto-signin](https://github.com/88lin/workbuddy-auto-signin) 的 `signin.py`，
   默认在以下位置自动查找，找不到时该端记 `SKIP`（不影响其他端）：
   `../workbuddy-auto-signin/signin.py`、`./vendor/workbuddy-auto-signin/signin.py`、`~/workbuddy-auto-signin/signin.py`，
   或在 `config.json` 里写 `"workbuddy_signin": "绝对路径"`。

## 执行方式

在技能目录下执行（`PY` 指装了依赖的 Python 解释器）：

```bash
# 全量（接口 + 客户端）
python daily_all.py

# 只跑接口类（快、稳，适合后台/无人值守）
python daily_all.py --api-only

# 只跑客户端类
python daily_all.py --gui-only

# 单端调试（客户端名见 client_daily.py 的 CLIENTS）
python client_daily.py coze doubao

# 自检：Python/依赖/客户端路径/凭据文件是否就绪
python scripts/doctor.py
```

输出约定：每个子任务一行 JSON，**最后一行一定是汇总**（`summary: true`），
含 `all_ok`、`failed`、`results[{agent,result,report}]`。

## 结果码含义

| result | 含义 | 需要处理 |
| --- | --- | --- |
| `CLAIMED` | 本次成功领取 | 否 |
| `ALREADY` | 今日已签过（幂等重跑的正常结果） | 否 |
| `GROWTH` / `DONE` / `LOGGED_IN` | 成长中心/客户端动作完成/仅保持登录 | 否 |
| `SKIP` | 该端未配置或 UI 暂不可用（如 Trae GUI 失效） | 否 |
| `INACTIVE` | 活动未开启 | 否 |
| `PENDING` | 今日待领（`status` 模式才会出现） | 否 |
| `NO_SESSION` | 登录态过期 → 打开对应客户端重新登录一次 | 是 |
| `NO_AUTH` | 未登录 / 找不到凭据文件 | 是 |
| `LAUNCH_FAILED` | 当前环境无桌面会话，客户端启动即退出 | 换到桌面会话运行 |
| `ERROR` / `TIMEOUT` | 看 `report`；客户端类会自动存截图到 `shots/` | 是 |

## 配置（可选）

需要覆盖自动探测时，在技能根目录放 `config.json`（已被 `.gitignore` 忽略）：

```json
{
  "python": "C:/Python311/python.exe",
  "workbuddy_signin": "D:/tools/workbuddy-auto-signin/signin.py",
  "clients": {
    "coze":    { "exe": "D:/Program Files/Coze/Coze.exe" },
    "doubao":  { "exe": "D:/Program Files/DoubaoWork/DoubaoWork.exe" }
  }
}
```

未配置时 `client_daily.py` 会自动在 `%LOCALAPPDATA%\Programs`、`%ProgramFiles%`、
`D:\Program Files`、`<任意盘>:\Users\* \AppData\Local\Programs` 等位置按 exe 名搜索。

## 做成定时任务

```powershell
# 注册一个「仅手动触发、不弹终端窗口」的计划任务
powershell -ExecutionPolicy Bypass -File .\install.ps1

# 注册后立即跑一次
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Run

# 需要每天自动跑时，再加每日触发器（任务计划程序里改，或 -Daily 09:00）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Daily 09:00
```

任务默认动作是 `pythonw.exe daily_all.py`，无控制台窗口，日志写入 `daily_all.log`。

## 关键注意事项

- **不要依赖桌面快捷方式启动客户端**：桌面会被整理，快捷方式会消失；一律用安装目录的 exe 绝对路径。
- 客户端类跑完会**关闭除 ima 以外的所有客户端进程**（`cleanup_clients()`），WorkBuddy 不在清单内不受影响。
- `daily_all.py` 对客户端类有「每天只跑一次」保护（标记 `.cache/gui_done_YYYY-MM-DD.txt`），
  重复触发只跑接口；需要强制重跑设环境变量 `FORCE_GUI=1`。
- 豆包不暴露 UIA 控件树，签到按钮靠**颜色定位**（实心蓝 `RGB(79,139,247)` 连通域）；找不到时记 `ALREADY` 并保存 `shots/doubao_*.png` 供核对。
- 扣子按**消耗倍率最小**选模型（菜单文本形如 `GLM-5.3-Flash … 0.1x`），再发「你好」，收到回复即完成签到。
- Trae 接口领取自 2026-10-18 起可能返回 `code 9004`（服务端策略，非脚本问题）；
  脚本会把「订单重复」判定为已签，反复失败时改用 Trae 桌面端 GUI 签到。
- 任何情况下脚本都不会打印 token/cookie，只输出人话结论。

详细端点说明与排障见 `references/troubleshooting.md` 与 `docs/endpoints.md`。

## 分发

本技能与 GitHub 仓库同构：把整个目录放进 `~/.workbuddy/skills/agent-auto-signin/`（用户级）
或 `{项目}/.workbuddy/skills/agent-auto-signin/`（项目级）即可被 WorkBuddy 识别。

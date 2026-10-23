# 排障手册

## 一、先跑自检

```bash
python scripts/doctor.py
```

逐项看 `[OK]/[FAIL]`：依赖、7 个客户端 exe 路径、WorkBuddy signin.py、各端凭据文件。
最后一行是汇总 JSON，`all_ok: false` 时按失败项处理。

## 二、按结果码排障

| 结果码 | 常见原因 | 处理 |
| --- | --- | --- |
| `NO_AUTH` | 没登录过该客户端 / 凭据文件位置变了 | 打开客户端登录一次；用 doctor 看探测到的路径 |
| `NO_SESSION` | token 过期 | 打开该客户端，等它刷新登录态（MiniMax 重启即可刷新） |
| `LAUNCH_FAILED` | 当前环境无桌面会话（如在后台服务/远程非交互会话里跑） | 改用登录会话中的计划任务，或在桌面双击运行 |
| `ERROR` + `未找到…按钮/入口` | 客户端 UI 改版 | 看 `shots/` 下对应截图，更新 `client_daily.py` 里的关键词 |
| `TIMEOUT` | 单端超过 620 秒 | 检查是否卡在启动/登录，必要时先手动打开一次 |
| `SKIP`（Trae GUI） | Trae 新版无障碍树失效 | 正常，接口端会兜底 |
| `code 9004`（Trae 接口） | 服务端策略变化 | 用 Trae 桌面端 GUI 签到；脚本已把「订单重复」判为已签 |

## 三、客户端类常见坑

1. **必须在交互式桌面会话运行**。在 WorkBuddy 的后台命令里直接启动 Electron 客户端，会因会话/网络隔离出现「启动即退出」或「界面空白」。正确做法：注册计划任务后在桌面会话里启动任务。
2. **窗口被别的窗口挡住**。豆包靠截图找按钮，脚本会先用 `SetForegroundWindow` 把窗口置前；如果仍失败，看 `shots/doubao_*.png` 是否是被遮挡的画面。
3. **豆包打卡卡片每天只弹一次**。当天已领或已弹过，脚本记 `ALREADY` 并存截图，属正常。
4. **扣子发不出消息**。旧实现按窗口比例点坐标会点空；现在是 UIA 找 `Edit` 控件 + 点「发送消息」，若仍失败看截图里输入框是否有文字。
5. **收尾没关干净**。`cleanup_clients()` 会按 exe 名杀进程；若某客户端改了进程名，把它加进 `CLIENTS` 的 exe 路径即可（进程名由 exe 文件名推导）。

## 四、路径探测不生效

自动探测顺序：`config.json` → `<LOCALAPPDATA>\Programs`、`%ProgramFiles%`、`%ProgramFiles(x86)%`、
`D:\Program Files`、`C:\`、`D:\`、`<任意盘>:\Users\*\AppData\Local\Programs` → 逐层找 exe 名（最多两层）。

装在非常规位置时，直接在 `config.json` 写死：

```json
{ "clients": { "coze": { "exe": "E:/Apps/Coze/Coze.exe" } } }
```

## 五、日志与证据

- `daily_all.log`：总入口逐端 JSON（pythonw 无窗口时也会写）
- `client_daily.log`：每个客户端的每一步，含重试记录
- `shots/`：失败截图（`<端>_<时间>.png`）、成功留档（`<端>_done_<时间>.png`）、豆包抓屏

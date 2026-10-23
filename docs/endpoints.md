# 端点对照表

## 接口类（`run_daily_win.py`）

| 端 | 脚本 | 凭据来源 | 接口 | 备注 |
| --- | --- | --- | --- | --- |
| WorkBuddy | 外部 `workbuddy-auto-signin/signin.py` | `%APPDATA%`/客户端运行时解密（sym-v1 加密信封） | 签到 + 成长中心 | 未安装该脚本时记 `SKIP` |
| Trae | `scripts/trae_signin.py` | `%APPDATA%\Trae CN\User\globalStorage\storage.json`（AES-128-CBC + openssl 解密） | `checkin_credits/status`、`/claim` | 依赖 openssl（Git 自带即可） |
| MiniMax Code | `scripts/minimax_signin_win.py` | `~/.minimax/auth/prod/cn/mcode-public/auth.json` | 官方签到 | token 由客户端启动时刷新 |
| 百度搭子 | `scripts/dumate_signin.py` | `%APPDATA%\qianfan-desktop-app\auth.json` + `.cookie-key`（AES-256-GCM） | `points/loginBonusInfo`、`points/loginBonus` | 需要 `cryptography` |

## 客户端类（`client_daily.py`）

| 端 | 进程/窗口 | 动作链 | 收尾 |
| --- | --- | --- | --- |
| MiniMax Code | `MiniMax Code.exe` | 重启 → 等自动登录（刷新 token） | 退出 |
| Trae CN | `Trae CN.exe` | 左下角头像 → 「每日领 100 积分」右侧「签到」 | 退出 |
| 豆包 | `DoubaoWork.exe` | 左下角「今日签到领 200 额度」→「立即签到」（UIA 优先，否则蓝色按钮颜色定位） | 退出 |
| 扣子 | `Coze.exe` | 新任务 → 选消耗倍率最低的模型 → 发「你好」→ 等回复 | 退出 |
| 智谱清言 | `智谱清言.exe` | 打开并保持登录态 | 退出 |
| AS Studio | `AStudio.exe` | 「限时每日福利」弹窗 → 「领取」 | 退出 |
| ima | `ima.copilot.exe` | 我的 Copilot → 设置 → 用量统计 → 领取算力 → 50 算力签到 | 关窗口，**进程保留** |

> 全部跑完后 `cleanup_clients()` 统一关闭除 ima 外的客户端；WorkBuddy 不在清单内，不会被关闭。

## 单端命令速查

```bash
python run_daily_win.py workbuddy trae minimax dumate     # 接口四端
python client_daily.py doubao coze                        # 指定客户端
python daily_all.py --api-only                            # 仅接口
FORCE_GUI=1 python daily_all.py                           # 强制重跑客户端（绕过每日一次保护）
```

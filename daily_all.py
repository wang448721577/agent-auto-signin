#!/usr/bin/env python3
"""每日任务总入口：接口类签到 + 网页/桌面端 GUI 任务，统一汇总。

组成：
  1) run_daily_win.py  —— WorkBuddy / Trae / MiniMax / 百度搭子（纯接口，无人值守可靠）
  2) client_daily.py   —— 扣子 / 智谱清言 / AStudio / ima 四个桌面客户端
                          （全部使用安装目录 exe，不依赖桌面快捷方式；
                            启动后等自动登录，再执行发送/领取动作）

用法：  python daily_all.py                # 全跑
        python daily_all.py --api-only    # 只跑接口类
        python daily_all.py --gui-only    # 只跑客户端类
输出：  各子任务 JSON + 最后一行总汇总（summary=true）
"""

import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 客户端（GUI）任务每天只跑一次：该组脚本会强制杀掉并重拉扣子/智谱清言/AStudio/ima，
# 一天内被重复触发（登录 + 定时任务）时既打扰用户又会打断已登录会话。
# 标记文件按天生成，跑过就不再重试；需手动重跑设 FORCE_GUI=1。
CACHE_DIR = os.path.join(HERE, ".cache")
GUI_MARK = os.path.join(CACHE_DIR, "gui_done_%s.txt" % datetime.now().strftime("%Y-%m-%d"))


def run_script(name, args=None):
    """跑一个子脚本，返回解析出的 JSON 行列表。"""
    cmd = [PY, os.path.join(HERE, name)] + (args or [])
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900,
                              encoding="utf-8", errors="replace", env=env)
    except subprocess.TimeoutExpired:
        return [{"result": "TIMEOUT", "report": "%s 超过 900 秒被终止" % name}]
    except Exception as e:
        return [{"result": "ERROR", "report": "无法执行 %s（%s）" % (name, e)}]

    parsed = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not parsed:
        parsed = [{"result": "ERROR",
                   "report": "%s 无 JSON 输出（stderr: %s）"
                             % (name, (proc.stderr or "")[:150].replace("\n", " "))}]
    return parsed


def main():
    args = sys.argv[1:]
    run_api = "--gui-only" not in args
    run_gui = "--api-only" not in args

    all_results = []

    # 先重启客户端（MiniMax Code 重启后 token 会刷新，接口签到才能成功）
    if run_gui:
        if os.path.exists(GUI_MARK) and os.environ.get("FORCE_GUI") != "1":
            print(json.dumps({
                "note": "客户端任务今日已执行过，跳过（标记 %s）；如需强制运行请设 FORCE_GUI=1"
                        % os.path.basename(GUI_MARK),
            }, ensure_ascii=False))
        else:
            gui_rows = run_script("client_daily.py")
            if gui_rows:
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    with open(GUI_MARK, "w", encoding="utf-8") as f:
                        f.write(datetime.now().isoformat(timespec="seconds"))
                except Exception:
                    pass  # 写标记失败不影响本次结果
            for row in gui_rows:
                if row.get("summary"):
                    for r in row.get("results", []):
                        all_results.append({"source": "client", **r})

    if run_api:
        for row in run_script("run_daily_win.py"):
            if row.get("summary"):
                for r in row.get("results", []):
                    all_results.append({"source": "api", **r})

    OK = {"CLAIMED", "ALREADY", "INACTIVE", "PENDING", "GROWTH", "DONE", "LOGGED_IN", "SKIP"}
    failed = [r["agent"] for r in all_results if r.get("result") not in OK]
    print(json.dumps({
        "summary": True,
        "all_ok": not failed,
        "failed": failed,
        "count": len(all_results),
        "results": all_results,
    }, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    # pythonw.exe 下没有控制台，sys.stdout 为 None；重定向到日志，保证后台无窗口也能留痕
    if sys.stdout is None or sys.stderr is None:
        try:
            _log = open(os.path.join(HERE, "daily_all.log"), "a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stdout or _log
            sys.stderr = sys.stderr or _log
        except Exception:
            pass
    sys.exit(main())

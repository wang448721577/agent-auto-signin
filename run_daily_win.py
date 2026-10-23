#!/usr/bin/env python3
"""Windows 每日签到调度器（四端合一的「接口类」签到）。

覆盖：WorkBuddy / Trae / MiniMax Code / 百度搭子。
  - WorkBuddy 端 → 复用 88lin/workbuddy-auto-signin 的 signin.py（支持加密凭据 + 成长中心）。
    找不到该脚本时记 SKIP，不影响其它三端。
  - Trae / MiniMax / 百度搭子 → 本仓库 scripts/ 下的脚本，凭据路径可用环境变量注入。

用法：
  python run_daily_win.py                # 跑全部四端
  python run_daily_win.py trae dumate    # 只跑指定端
输出：逐端一行 JSON + 最后一行汇总 JSON（summary=true）
退出码：0 全部成功/幂等，1 有端失败，2 参数错误
"""

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")

# 可移植配置：config.json 里可以显式指定 workbuddy_signin 与 python
CONFIG_PATH = os.path.join(HERE, "config.json")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except Exception:
    CONFIG = {}

# 默认用当前解释器（需已装 cryptography，百度搭子端解密依赖）
PY = CONFIG.get("python") or sys.executable

APPDATA = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
APPDATA_LOCAL = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))


def _first_existing(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


# WorkBuddy 端脚本：config.json 指定 / 同目录兄弟项目 / vendor 目录 / 用户主目录
WB88 = _first_existing([
    CONFIG.get("workbuddy_signin") or "",
    os.path.join(os.path.dirname(HERE), "workbuddy-auto-signin", "signin.py"),
    os.path.join(HERE, "vendor", "workbuddy-auto-signin", "signin.py"),
    os.path.join(os.path.expanduser("~"), "workbuddy-auto-signin", "signin.py"),
])

# Trae 登录态文件（不同版本目录名不同，按顺序探测）
TRAE_STORAGE = _first_existing([
    os.path.join(APPDATA, "Trae CN", "User", "globalStorage", "storage.json"),
    os.path.join(APPDATA, "TRAE SOLO CN", "User", "globalStorage", "storage.json"),
]) or os.path.join(APPDATA, "Trae CN", "User", "globalStorage", "storage.json")

# 百度搭子（千帆桌面端）数据目录
DUMATE_AUTH = _first_existing([os.path.join(APPDATA, "qianfan-desktop-app", "auth.json")])
DUMATE_DIR = os.path.dirname(DUMATE_AUTH) if DUMATE_AUTH else os.path.join(APPDATA, "qianfan-desktop-app")

TARGETS = {
    "workbuddy": {"script": WB88, "env": {}},
    "trae": {"script": os.path.join(SCRIPTS, "trae_signin.py"),
             "env": {"TRAE_STORAGE_FILE": TRAE_STORAGE}},
    "minimax": {"script": os.path.join(SCRIPTS, "minimax_signin_win.py"), "env": {}},
    "dumate": {"script": os.path.join(SCRIPTS, "dumate_signin.py"),
               "env": {"DUMATE_AUTH_DIR": DUMATE_DIR}},
}

LABEL = {"workbuddy": "WorkBuddy", "trae": "Trae",
         "minimax": "MiniMax Code", "dumate": "百度搭子"}

# 视为「非失败」的 result
OK_RESULTS = {"CLAIMED", "ALREADY", "INACTIVE", "PENDING", "GROWTH", "SKIP"}

# Trae 端依赖 openssl 命令行解密登录态；计划任务/非交互环境下 PATH 常不含它
OPENSSL_CANDIDATES = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Git", "usr", "bin"),
    os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Git", "usr", "bin"),
    os.path.join(APPDATA_LOCAL, "Programs", "Git", "usr", "bin"),
    r"D:\Program Files\Git\usr\bin",
]


def ensure_openssl(env):
    """若 PATH 中找不到 openssl，自动把已知目录补进去。"""
    if shutil.which("openssl", path=env.get("PATH", "")):
        return env
    for cand in OPENSSL_CANDIDATES:
        if cand and os.path.exists(os.path.join(cand, "openssl.exe")):
            env["PATH"] = cand + os.pathsep + env.get("PATH", "")
            break
    return env


def run_one(name):
    cfg = TARGETS[name]
    if not cfg["script"] or not os.path.isfile(cfg["script"]):
        return {"agent": name, "result": "SKIP",
                "report": "未找到该端脚本（%s），已跳过" % (cfg["script"] or name)}
    env = dict(os.environ)
    env.update(cfg["env"])
    env["PYTHONIOENCODING"] = "utf-8"
    env = ensure_openssl(env)
    try:
        proc = subprocess.run(
            [PY, cfg["script"], "auto"],
            capture_output=True, text=True, timeout=620, env=env,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"agent": name, "result": "TIMEOUT", "report": "单端超过 620 秒被终止"}
    except Exception as e:
        return {"agent": name, "result": "ERROR", "report": "无法执行脚本（%s）" % e}

    out = (proc.stdout or "").strip()
    parsed = None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if parsed is None:
        parsed = {"result": "ERROR", "report": "脚本无 JSON 输出（stderr: %s）"
                  % (proc.stderr or "")[:200].replace("\n", " ")}
    parsed["agent"] = name
    parsed["exit"] = proc.returncode
    # Trae 已由 GUI 签到完成时，接口会报订单重复——视为今日已签
    if name == "trae" and "order parameters are incorrect" in (parsed.get("report") or ""):
        parsed["result"] = "ALREADY"
        parsed["report"] = "今日已由 GUI 签到（接口返回订单重复，视为已签）"
    return parsed


def main():
    names = sys.argv[1:] or list(TARGETS)
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        print(json.dumps({"summary": True, "error": "未知端: %s" % unknown},
                         ensure_ascii=False))
        return 2

    results = []
    for n in names:
        r = run_one(n)
        results.append(r)
        print(json.dumps(r, ensure_ascii=False))

    failed = [r["agent"] for r in results if r.get("result") not in OK_RESULTS]
    print(json.dumps({
        "summary": True,
        "all_ok": not failed,
        "failed": failed,
        "results": [{"agent": LABEL.get(r["agent"], r["agent"]),
                     "result": r.get("result"),
                     "report": r.get("report")} for r in results],
    }, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

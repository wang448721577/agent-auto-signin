#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境自检：依赖、客户端安装路径、凭据文件是否就绪。

用法：python scripts/doctor.py
输出：逐项检查结果 + 最后一行汇总 JSON（summary=true）
不读取、不打印任何 token / cookie 内容，只判断文件是否可读。
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

CHECK_IMPORTS = ["psutil", "pywinauto", "PIL", "win32clipboard", "cryptography"]

CRED_FILES = {
    "Trae": os.path.join(os.environ.get("APPDATA", ""), "Trae CN", "User", "globalStorage", "storage.json"),
    "百度搭子": os.path.join(os.environ.get("APPDATA", ""), "qianfan-desktop-app", "auth.json"),
    "MiniMax Code": os.path.join(os.path.expanduser("~"), ".minimax", "auth", "prod", "cn",
                                 "mcode-public", "auth.json"),
}
# 可选路径：存在更好，不存在不算失败（不同版本目录名不同）
OPTIONAL_CREDS = {
    "Trae(SOLO)": os.path.join(os.environ.get("APPDATA", ""), "TRAE SOLO CN", "User", "globalStorage", "storage.json"),
}


def readable(path):
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except Exception:
        return False


def main():
    out = {"python": sys.version.split()[0], "ok": True, "checks": []}

    for mod in CHECK_IMPORTS:
        try:
            __import__(mod)
            out["checks"].append({"item": "import:" + mod, "ok": True})
        except Exception as e:
            out["ok"] = False
            out["checks"].append({"item": "import:" + mod, "ok": False, "hint": str(e)})

    try:
        import client_daily as c
        for k in c.ORDER:
            exe = c.CLIENTS[k]["exe"]
            ok = os.path.isfile(exe)
            if not ok:
                out["ok"] = False
            out["checks"].append({"item": "client:" + k, "ok": ok, "path": exe})
    except Exception as e:
        out["ok"] = False
        out["checks"].append({"item": "client_daily", "ok": False, "hint": str(e)})

    try:
        import run_daily_win as r
        wb = r.WB88
        out["checks"].append({"item": "workbuddy_signin", "ok": bool(wb), "path": wb,
                              "hint": "" if wb else "未找到 signin.py，WorkBuddy 端将 SKIP"})
    except Exception as e:
        out["checks"].append({"item": "run_daily_win", "ok": False, "hint": str(e)})

    for name, path in CRED_FILES.items():
        out["checks"].append({"item": "cred:" + name, "ok": readable(path), "path": path})
    for name, path in OPTIONAL_CREDS.items():
        out["checks"].append({"item": "cred:" + name + "(可选)", "ok": readable(path),
                              "path": path, "optional": True})

    print("agent-auto-signin 环境自检（只判断文件可读，不读取内容）\n")
    for c in out["checks"]:
        if c.get("ok"):
            flag = "OK  "
        elif c.get("optional"):
            flag = "SKIP"          # 可选项缺失不影响运行，不算失败
        else:
            flag = "FAIL"
        print("[%s] %-24s %s" % (flag, c["item"], c.get("path") or c.get("hint") or ""))
    print("\n[OK] 通过  [SKIP] 可选缺失（不影响）  [FAIL] 必须修复")
    print(json.dumps({"summary": True, "all_ok": out["ok"], "python": out["python"],
                      "checks": out["checks"]}, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

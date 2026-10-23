"""MiniMax Code 每日签到（Windows 适配版，每日 400 积分，连签第 4/7 天 1000）。

为什么需要这个版本：
原版 minimax_signin.py 假设登录 JWT 明文躺在 Electron 的 leveldb 里（macOS 行为），
Windows 版 MiniMax Code 桌面端把登录态换成 OAuth 不透明 token（mmoat_ 前缀），
写在 ~/.minimax/auth/prod/cn/mcode-public/auth.json，leveldb 里根本没有 JWT，
因此原脚本在 Windows 上必然报 NO_AUTH。

本脚本：
  1. 从 ~/.minimax 的 auth.json 读 accessToken（并检查 auth-state.json 的 expiresAtMs）；
  2. 复用原脚本逆向出的签名协议，直调官方接口：
       GET  https://agent.minimaxi.com/minimax-cloud/api/v1/signin/status
       POST https://agent.minimaxi.com/minimax-cloud/api/v1/signin/claim

用法：  python minimax_signin_win.py auto     # 查状态→可领才领（幂等）
        python minimax_signin_win.py status   # 只查状态
输出：  一行 JSON，人话在 report 字段。任何情况下不打印 token。
"""

import glob
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://agent.minimaxi.com"
REQUEST_TIMEOUT = 20

AUTH_REL = os.path.join(".minimax", "auth", "prod", "cn", "mcode-public")
CONFIG_NAME = "minimax-agent-cn-config.json"


def emit(out):
    print(json.dumps(out, ensure_ascii=False, default=str))


def _readable(path):
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except Exception:
        return False


def find_token():
    """从 ~/.minimax 读取当前登录 token，返回 (token, err_code, err_msg)。"""
    home = os.path.expanduser("~")
    base = os.environ.get("MINIMAX_AUTH_DIR") or os.path.join(home, AUTH_REL)
    auth_json = os.path.join(base, "auth.json")
    state_json = os.path.join(base, "auth-state.json")

    if not _readable(auth_json):
        return None, "NO_AUTH", ("未找到 MiniMax 登录态文件（%s），"
                                 "请先登录 MiniMax Code 桌面端" % auth_json)
    try:
        with open(auth_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records") or {}
        if not records:
            return None, "NO_AUTH", "登录态文件为空，请先登录 MiniMax Code 桌面端"
        # 优先选桌面端 mcode-public 记录；按 expiresAtMs 取最新的有效记录兜底
        rec = None
        for key, val in records.items():
            if "mcode-public" in key:
                rec = val
                break
        if rec is None:
            rec = max(records.values(), key=lambda v: float((v or {}).get("expiresAtMs") or 0))
        token = (rec or {}).get("accessToken")
    except Exception as e:
        return None, "ERROR", "登录态文件解析失败（%s: %s）" % (type(e).__name__, e)

    if not token:
        return None, "NO_AUTH", "登录态文件中没有 accessToken，请重新登录 MiniMax Code 桌面端"

    # 过期检查：以 auth-state.json 为准（它反映当前会话总体过期时间）
    exp = None
    try:
        if _readable(state_json):
            with open(state_json, "r", encoding="utf-8") as f:
                exp = json.load(f).get("expiresAtMs")
    except Exception:
        exp = None
    if exp and float(exp) / 1000.0 < time.time():
        return None, "NO_SESSION", ("登录态已于 %s 过期，"
                                    "请打开 MiniMax Code 客户端重新登录"
                                    % time.strftime("%Y-%m-%d %H:%M",
                                                    time.localtime(float(exp) / 1000.0)))
    return token, None, None


def real_user_id():
    """桌面端配置里的 realUserID；取不到返回 0（服务端不严格校验）。"""
    home = os.path.expanduser("~")
    for cand in (os.path.join(os.environ.get("APPDATA", ""), "MiniMax", CONFIG_NAME),
                 os.path.join(home, "Library", "Application Support", "MiniMax", CONFIG_NAME)):
        try:
            with open(cand, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return str(cfg.get("user", {}).get("realUserID") or 0)
        except Exception:
            continue
    return "0"


def signed_request(path, token, uid, method="GET", body=""):
    """复刻桌面端签名协议发请求；返回 (http_code, dict)。"""
    ms = int(time.time() * 1000)
    sec = ms // 1000
    params = [
        ("device_platform", "web"), ("biz_id", "3"), ("app_id", "3001"),
        ("version_code", "22201"), ("unix", str(ms)), ("timezone_offset", "480"),
        ("timezone_id", "Asia/Shanghai"), ("sys_language", "zh"), ("lang", "zh"),
        ("uuid", "null"), ("device_id", "48372915"), ("os_name", "macOS"),
        ("browser_name", "Chrome"), ("browser_language", "zh-CN"),
        ("browser_platform", "MacIntel"), ("user_id", uid),
        ("op_ticket", "undefined"), ("screen_width", "1512"), ("screen_height", "982"),
        ("unix", str(ms)), ("token", token),
    ]
    full = "%s?%s" % (path, urllib.parse.urlencode(params))
    yy = hashlib.md5(("%s_%s%s%s" % (urllib.parse.quote(full), body,
                                     hashlib.md5(str(ms).encode()).hexdigest(),
                                     "ooui")).encode()).hexdigest()
    xsig = hashlib.md5(("%sI*7Cf%%WZ#S&%%1RlZJ&C2%s" % (sec, body)).encode()).hexdigest()
    # 实测：Windows 桌面端的 mmoat_ token 必须用 Authorization: Bearer 送，
    # 沿用原脚本的 "token" 头会被服务端 401 拒绝（签名协议本身不变）。
    headers = {
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
        "x-timestamp": str(sec), "x-signature": xsig, "yy": yy,
        "Origin": API_BASE, "Referer": API_BASE + "/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }
    data = body.encode() if method == "POST" else None
    req = urllib.request.Request(API_BASE + full, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"error": str(e)}


def checkin(claim=False):
    token, err_code, err_msg = find_token()
    if err_code:
        return 2 if err_code == "NO_AUTH" else 1, {"result": err_code, "report": err_msg}
    uid = real_user_id()

    scode, sbody = signed_request("/minimax-cloud/api/v1/signin/status", token, uid)
    if scode == -1:
        return 1, {"result": "NETWORK",
                   "report": "网络不可达，签到跳过（%s）" % (sbody.get("error") or "")}
    base = sbody.get("base_resp") or {} if isinstance(sbody, dict) else {}
    if base.get("status_code") == 1022100011 or scode in (401, 403):
        return 1, {"result": "NO_SESSION",
                   "report": "登录态已失效，请打开 MiniMax Code 客户端重新登录"}
    if base.get("status_code") not in (0, None) or not isinstance(sbody.get("data"), dict):
        return 1, {"result": "ERROR",
                   "report": "状态接口异常：%s（HTTP %s）"
                             % (base.get("status_msg") or base.get("status_code"), scode)}

    days = sbody["data"].get("days") or []
    today = next((d for d in days if d.get("is_today")), None)
    streak = today.get("day_no") if today else None
    streak_txt = "连签第 %s 天" % streak if streak else "7 天周期"

    if today is None:
        return 0, {"result": "INACTIVE", "report": "签到面板无今日项（可能活动未开启）"}
    if today.get("status") == 3:
        return 0, {"result": "ALREADY", "report": "今日已签过（%s）" % streak_txt,
                   "day_no": streak, "points": today.get("points")}
    if today.get("status") != 2:
        return 0, {"result": "INACTIVE", "report": "今日不可领取（%s）" % streak_txt}

    if not claim:
        return 0, {"result": "PENDING",
                   "report": "今日可领 %s 积分（%s）" % (today.get("points"), streak_txt)}

    ccode, cbody = signed_request("/minimax-cloud/api/v1/signin/claim", token, uid,
                                  method="POST", body="{}")
    if ccode == -1:
        return 1, {"result": "NETWORK", "report": "领取请求未能送达，下次自动重试"}
    cdata = (cbody.get("data") or {}) if isinstance(cbody, dict) else {}
    cbase = (cbody.get("base_resp") or {}) if isinstance(cbody, dict) else {}
    if cbase.get("status_code") == 1022100011 or ccode in (401, 403):
        return 1, {"result": "NO_SESSION",
                   "report": "登录态已失效，请打开 MiniMax Code 客户端重新登录"}
    if cdata.get("claim_result") in (1, 2):
        result = "CLAIMED" if cdata.get("claim_result") == 1 else "ALREADY"
        verb = "成功领取" if result == "CLAIMED" else "今日已领过"
        return 0, {"result": result,
                   "report": "%s %s 积分（%s）" % (verb, cdata.get("points"), streak_txt),
                   "day_no": cdata.get("day_no"), "points": cdata.get("points")}
    return 1, {"result": "ERROR",
               "report": "领取失败：%s（HTTP %s）"
                         % (cbase.get("status_msg")
                            or json.dumps(cbody, ensure_ascii=False)[:120], ccode)}


def main():
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "auto"
    try:
        if action == "auto":
            code, out = checkin(claim=True)
        elif action == "status":
            code, out = checkin(claim=False)
        else:
            code, out = 2, {"result": "ERROR", "report": "未知命令：%s（可用：auto / status）" % action}
    except Exception as e:
        code, out = 2, {"result": "ERROR",
                        "report": "脚本运行异常（%s: %s）" % (type(e).__name__, e)}
    emit(out)
    return code


if __name__ == "__main__":
    import sys
    sys.exit(main())

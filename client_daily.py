#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桌面客户端每日任务（全部使用安装目录中的 exe，不依赖桌面快捷方式）。

启动参数带 --force-renderer-accessibility，让 Electron 客户端把页面 DOM 暴露给
Windows UI Automation，这样可以用控件名精确点击，不靠坐标、不靠截图。

各站点精确流程（按用户指定顺序执行，每个客户端独立进程、失败自动重试一次）：
  minimax  MiniMax Code —— 仅重启刷新 token（接口签到由 run_daily_win.py 负责）
  trae     Trae CN     —— 打开 → 点左下角用户头像 → 点「每日领 100 积分」
  doubao   豆包(工作)   —— 打开 → 左下角「今日签到领 200 额度」卡片点「立即签到」→ 退出
  coze     扣子         —— 打开 → 新任务 → 选消耗倍率最低的模型 → 发「你好」
                        → 等回复（自动完成签到给积分）→ 退出
  chatglm  智谱清言     —— 打开 → 登录 → 退出
  astudio  AS Studio   —— 打开 → 左下角「限时每日福利」弹窗 → 点「领取」→ 退出
  ima      ima         —— 打开 → 我的 Copilot → 右上角 Copilot 设置 → 用量统计
                        → 「每日登录福利」后「领取算力」→ 弹窗底部「50 算力签到」
                        → 完成后最小化（不退出）

用法：  python client_daily.py                 # 全部按序执行
        python client_daily.py coze ima        # 指定执行
退出码：0 全部成功，1 有失败
注意：必须在有桌面会话的环境运行（Windows 计划任务 / 手动双击）；
      在无 GUI 的后台会话里 Electron 客户端会启动即退出，脚本会报 LAUNCH_FAILED。
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(HERE, "shots")


# ---------------- 可移植的路径解析 ----------------
# 每个人的安装位置不同：优先读 config.json 的显式配置，其次在常见目录下按 exe 名字自动搜索。
CONFIG_PATH = os.path.join(HERE, "config.json")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
        CONFIG = json.load(_f)
except Exception:
    CONFIG = {}

_LOCALAPPDATA = os.environ.get("LOCALAPPDATA", "")
_PROGRAMFILES = os.environ.get("ProgramFiles", r"C:\Program Files")
_PROGRAMFILES86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

# 每个端：exe 文件名 + 优先尝试的目录（其后还会搜索通用目录）
EXE_CANDIDATES = {
    "minimax": ("MiniMax Code.exe", [r"MiniMax Code"]),
    "trae": ("Trae CN.exe", [r"Trae CN"]),
    "doubao": ("DoubaoWork.exe", [r"DoubaoWork"]),
    "coze": ("Coze.exe", [r"Coze"]),
    "chatglm": ("智谱清言.exe", [r"chatglm"]),
    "astudio": ("AStudio.exe", [r"AStudio"]),
    "ima": ("ima.copilot.exe", [r"ima.copilot"]),
}


def _search_roots(extra):
    roots = []
    for base in (os.path.join(_LOCALAPPDATA, "Programs"), _PROGRAMFILES, _PROGRAMFILES86,
                 r"D:\Program Files", r"C:\Program Files", "D:\\", "C:\\"):
        if base and os.path.isdir(base):
            roots.append(base)
    # 有些人把用户目录或程序目录放在别的盘（如 D:\Users\<用户>\AppData\Local\Programs）
    try:
        import glob
        for drive in ("C", "D", "E", "F", "G"):
            for p in glob.glob("%s:\\Users\\*\\AppData\\Local\\Programs" % drive):
                if p not in roots:
                    roots.append(p)
    except Exception:
        pass
    for e in extra:
        for base in (os.path.join(_LOCALAPPDATA, "Programs"), _PROGRAMFILES,
                     r"D:\Program Files", "D:\\"):
            p = os.path.join(base, e)
            if os.path.isdir(p):
                roots.insert(0, p)
    return roots


def resolve_exe(key):
    """返回该端的 exe 绝对路径：config.json > 自动探测 > 常见默认位置。"""
    override = (CONFIG.get("clients", {}).get(key, {}) or {}).get("exe")
    if override and os.path.isfile(override):
        return override
    exe_name, extra = EXE_CANDIDATES[key]
    for root in _search_roots(extra):
        direct = os.path.join(root, exe_name)
        if os.path.isfile(direct):
            return direct
        # 再往下搜两层（如 <root>\<AppName>\<exe>）
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth >= 2:
                dirnames[:] = []
                continue
            if exe_name in filenames:
                return os.path.join(dirpath, exe_name)
    return os.path.join(_PROGRAMFILES, exe_name)   # 找不到时给个可读的默认路径


CLIENTS = {
    "minimax": {
        "exe": resolve_exe("minimax"),
        "name": "MiniMax Code",
        "wait": 20,
        # 用户要求：签到完成后退出 MiniMax（token 已在启动时写入，退出不影响接口签到）
        "exit": True,
        "action": "restart_only",
    },
    "trae": {
        "exe": resolve_exe("trae"),
        "name": "Trae CN",
        "wait": 40,
        "exit": True,
        "action": "trae_signin",
        # 左下角头像按钮名为「用户xxx 用户xxx 免费」→ 弹出菜单中「每日领 100 积分」右侧「签到」按钮
        "avatar_keys": ["用户", "个人中心", "头像"],
        "signin_keys": ["签到", "每日领 100 积分", "每日领"],
        # Trae 更新为 SOLO 界面后无障碍树失效，GUI 签到降级为尽力而为：
        # 失败时记 SKIP（不计失败），接口签到（run_daily_win.py）兜底
        "optional": True,
    },
    "doubao": {
        "exe": resolve_exe("doubao"),
        "name": "豆包",
        "wait": 30,
        "exit": True,           # 用户要求：点完「立即签到」后退出豆包
        "action": "doubao_signin",
        # 左下角打卡卡片：「今日签到领 200 额度」+ 蓝色「立即签到」按钮
        "claim_keys": ["立即签到", "签到", "立即领取"],
    },
    "coze": {
        "exe": resolve_exe("coze"),
        "name": "扣子",
        "wait": 25,
        "exit": True,
        "action": "coze_dialog",
        # 左侧边栏实际按钮名为「新任务」，必须优先于「新建 Agent」匹配
        "new_keys": ["新任务", "新建任务", "新建对话", "新对话"],
        # 模型菜单项里带消耗倍率（如 0.81x / 1.38x），取倍率最小的模型
        "model_keys": ["Flash", "Pro", "GLM", "Doubao", "DeepSeek", "Kimi", "Qwen",
                       "Minimax", "Seed", "Auto"],
        "shot_on_done": True,  # 成功后也截图，便于核对当轮对话
    },
    "chatglm": {
        "exe": resolve_exe("chatglm"),
        "name": "智谱清言",
        "wait": 20,
        "exit": True,
        "action": "login_only",
    },
    "astudio": {
        "exe": resolve_exe("astudio"),
        "name": "AS Studio",
        "wait": 25,
        "exit": True,
        "action": "astudio_welfare",
        "popup_keys": ["限时每日福利", "每日福利", "福利"],
        "claim_keys": ["领取", "签到", "领积分"],
    },
    "ima": {
        "exe": resolve_exe("ima"),
        "name": "ima",
        "wait": 25,
        "exit": False,           # 不退出进程（保持托盘常驻）
        "close_window": True,    # 用户要求：签完后关闭 ima 窗口，但不退出程序
        "action": "ima_signin",
        "copilot_keys": ["我的copilot", "我的 Copilot", "我的Copilot"],
        # Copilot 设置按钮是无名图标，实测位于窗口右上角：right-96, top+100
        "settings_offset": (-96, 100),
        "usage_keys": ["用量统计"],
        "claim_keys": ["领取算力"],
        "welfare_title": "每日登录福利",  # 「领取算力」打开的独立窗口
        "final_keys": ["签到"],           # 福利窗口里「今日 50算力」后的按钮
    },
}

# 执行顺序：先重启 MiniMax 刷新 token，再按用户指定顺序走各站点
ORDER = ["minimax", "trae", "doubao", "coze", "chatglm", "astudio", "ima"]

SEND_TEXT = "你好"
MAX_RETRY = 1  # 失败自动重试一次


def emit(out):
    print(json.dumps(out, ensure_ascii=False, default=str))


def log_line(msg):
    """追加运行日志，便于定时任务事后排查。"""
    try:
        with open(os.path.join(HERE, "client_daily.log"), "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def process_running(key):
    import psutil
    low = key.lower()
    for p in psutil.process_iter(["name"]):
        try:
            n = p.info.get("name") or ""
            if low in n.lower():
                return True
        except Exception:
            continue
    return False


def kill_process(key):
    """强制结束进程：客户端重启后才会重新登录并弹出新的签到入口/按钮。"""
    import psutil
    low = key.lower()
    for p in psutil.process_iter(["name"]):
        try:
            if low in (p.info.get("name") or "").lower():
                p.kill()
        except Exception:
            continue
    time.sleep(3)  # 等进程彻底退出、释放凭据文件锁


def save_shot(window, tag):
    """找不到控件时留一张窗口截图，方便事后定位 UI 变化。"""
    try:
        os.makedirs(SHOT_DIR, exist_ok=True)
        path = os.path.join(SHOT_DIR, "%s_%s.png" % (tag, time.strftime("%Y%m%d_%H%M%S")))
        img = window.capture_as_image()
        img.save(path)
        return path
    except Exception:
        return ""


def find_window(proc_name_key):
    """按进程名找到客户端主窗口。"""
    from pywinauto import Desktop
    import psutil
    d = Desktop(backend="uia")
    best, best_area = None, 0
    for w in d.windows():
        try:
            if w.element_info.class_name in ("Chrome_WidgetWin_1", "Qt51514QWindowIcon", "Window"):
                pid = w.element_info.process_id
                pname = psutil.Process(pid).name().lower()
                if proc_name_key not in pname:
                    continue
                # 取面积最大的顶层窗口，避开 Trae 悬浮球这类小窗
                r = w.rectangle()
                area = (r.right - r.left) * (r.bottom - r.top)
                if area > best_area:
                    best, best_area = w, area
        except Exception:
            continue
    return best


def _match(text, keywords):
    """大小写不敏感的包含匹配（兼容「我的copilot」这类大小写差异）。"""
    low = text.lower()
    for k in keywords:
        if k.lower() in low:
            return True
    return False


def find_control(window, keywords, types=None, visible_only=True):
    """在窗口里按名称关键词找控件（默认只要可见的；关键词按顺序优先，
    避免「新建」抢在「新建任务」前面误中「新建 Agent」）。"""
    controls = []
    for c in window.descendants():
        try:
            ct = c.element_info.control_type
            if types and ct not in types:
                continue
            text = (c.window_text() or "").strip()
            if not text:
                continue
            if visible_only and not c.is_visible():
                continue
            controls.append((c, text))
        except Exception:
            continue
    for k in keywords:
        for c, text in controls:
            if k.lower() in text.lower():
                return c
    return None


def click_named(window, keywords, wait_after=3, types=None):
    """按名称关键词点一个可见控件，返回 (是否点到, 点到的文本)。"""
    c = find_control(window, keywords, types=types)
    if c is None:
        return False, ""
    text = (c.window_text() or "").strip()
    try:
        c.click_input()
        time.sleep(wait_after)
        return True, text
    except Exception:
        return False, text


def try_click_in_proc(proc_key, keywords, wait_after=3, main_window=None):
    """只在目标客户端进程的窗口（含其弹窗）里找控件点击——
    用于「限时每日福利」这类独立弹窗；限定进程避免误点任务栏等系统窗口。"""
    from pywinauto import Desktop
    import psutil
    windows = [w for w in Desktop(backend="uia").windows()
               if _belongs_to_proc(w, proc_key, psutil)]
    if main_window is not None:
        windows.append(main_window)
    for w in windows:
        try:
            c = find_control(w, keywords, types=["Button", "Hyperlink", "Text", "Custom", "Pane"])
            if c is not None:
                text = (c.window_text() or "").strip()
                c.click_input()
                time.sleep(wait_after)
                return True, text
        except Exception:
            continue
    return False, ""


def _belongs_to_proc(w, proc_key, psutil):
    try:
        pid = w.element_info.process_id
        return proc_key in psutil.Process(pid).name().lower()
    except Exception:
        return False


# ---------------- 各站点动作 ----------------

def do_login_only(window, cfg):
    return "LOGGED_IN", "%s 已启动并保持登录态" % cfg["name"]


def do_trae_signin(window, cfg, proc_key=None):
    """Trae：点左下角用户头像 → 弹出菜单中点「每日领 100 积分」右侧的「签到」按钮。
    Trae 可能同时有 IDE 窗口和 Agent 窗口，两个动作都在全部进程窗口中搜索。"""
    wins = []
    if window is not None:
        wins.append(window)
    if proc_key:
        for w in iter_proc_windows(proc_key):
            if all(w is not x for x in wins):
                wins.append(w)

    target = None
    for w in wins:
        c = find_control(w, cfg["avatar_keys"])
        if c is not None:
            target = (w, c)
            break
    if target is None:
        return "ERROR", "未找到 Trae 左下角用户头像入口（尝试了：%s）" % "/".join(cfg["avatar_keys"])
    w0, avatar = target
    name = (avatar.window_text() or "").strip()
    try:
        avatar.click_input()
        time.sleep(3)
    except Exception as e:
        return "ERROR", "Trae 头像点击失败（%s: %s）" % (type(e).__name__, e)
    report = "已点头像（%s）" % name

    # 弹出菜单可能挂在主窗口或独立窗口（点击后重新枚举）；优先点 Button 类型的「签到」
    search_wins = [w0]
    if proc_key:
        for w in iter_proc_windows(proc_key):
            if all(w is not x for x in search_wins):
                search_wins.append(w)
    for w in search_wins:
        btn = find_control(w, cfg["signin_keys"], types=["Button"])
        if btn is not None:
            text = (btn.window_text() or "").strip()
            try:
                btn.click_input()
                time.sleep(3)
                return "DONE", report + "；已点击「%s」完成签到" % text
            except Exception as e:
                return "ERROR", report + "；「签到」按钮点击失败（%s: %s）" % (type(e).__name__, e)
    return "ERROR", report + "；弹出菜单中未找到「签到」按钮（可能今日已签或 UI 变化）"


def iter_proc_windows(proc_key):
    """枚举目标进程的全部顶层窗口。"""
    from pywinauto import Desktop
    import psutil
    out = []
    for w in Desktop(backend="uia").windows():
        try:
            if _belongs_to_proc(w, proc_key, psutil):
                out.append(w)
        except Exception:
            continue
    return out


def set_clipboard(text):
    """把文本放进剪贴板（中文用剪贴板粘贴比逐键输入可靠得多）。"""
    import win32clipboard
    import win32con
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def do_coze_dialog_legacy(window, cfg):
    """（旧版坐标点击实现，已被下方 UIA 版取代，保留备查）"""
    import pywinauto.mouse as mouse
    report = ""
    ok, text = click_named(window, cfg["new_keys"], wait_after=4)
    if ok:
        report = "已点击「%s」；" % text
    try:
        r = window.rectangle()
        w = r.right - r.left
        h = r.bottom - r.top
        # 点输入框中央
        mouse.click(button="left", coords=(int(r.left + 0.49 * w), int(r.top + 0.48 * h)))
        time.sleep(1)
        set_clipboard(SEND_TEXT)
        window.type_keys("^v", with_spaces=True)
        time.sleep(1)
        # 点输入框右下角的发送箭头（↑）
        mouse.click(button="left", coords=(int(r.left + 0.879 * w), int(r.top + 0.575 * h)))
        time.sleep(8)  # 等一轮回复
        if find_control(window, [SEND_TEXT], visible_only=True) is not None:
            return "DONE", report + "已发送「%s」并完成一轮对话（已验证消息上屏）" % SEND_TEXT
        return "ERROR", report + "已执行发送但窗口中未看到「%s」消息，可能未发出" % SEND_TEXT
    except Exception as e:
        return "ERROR", report + "扣子发送失败（%s: %s）" % (type(e).__name__, e)


def _find_blue_button(img, dx=0.42, dy=0.50):
    """在图片左下区域找「实心蓝色主按钮」，返回 (中心X, 中心Y, 像素数) 或 None。
    做法：按蓝色阈值取点 → 4px 网格连通域 → 取填充率最高的矩形块（排除渐变插画）。
    豆包 Electron 未暴露 UIA 控件树，只能靠这个兜底。"""
    img = img.convert("RGB")
    W, H = img.size
    px = img.load()
    cell = 4
    grid = {}
    for y in range(int(H * dy), H, 2):
        for x in range(0, int(W * dx), 2):
            r, g, b = px[x, y]
            if abs(r - 79) < 22 and abs(g - 139) < 22 and abs(b - 247) < 16:
                grid.setdefault((x // cell, y // cell), 0)
                grid[(x // cell, y // cell)] += 1

    seen = set()
    best = None
    for start in list(grid):
        if start in seen:
            continue
        # BFS 连通域
        stack = [start]
        seen.add(start)
        comp = []
        while stack:
            cx, cy = stack.pop()
            comp.append((cx, cy))
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if (nx, ny) in grid and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    stack.append((nx, ny))
        xs = [c[0] for c in comp]
        ys = [c[1] for c in comp]
        w = max(xs) - min(xs) + 1
        h = max(ys) - min(ys) + 1
        if w < 25 or h < 5:
            continue
        fill = len(comp) / float(w * h)
        if fill < 0.55:          # 实心按钮填充率高，渐变插画很低
            continue
        area = w * h
        if best is None or area > best[0]:
            best = (area, min(xs) * cell, min(ys) * cell, max(xs) * cell, max(ys) * cell, len(comp))

    if best is None:
        return None
    _, x1, y1, x2, y2, n = best
    return (x1 + x2) // 2, (y1 + y2) // 2, n


def _bring_front(window):
    """把窗口强行拉到前台（set_focus 偶尔会被其他置顶窗口挡住，影响后续抓屏/点击）。"""
    try:
        import win32gui
        hwnd = window.handle
        win32gui.ShowWindow(hwnd, 9)      # SW_RESTORE
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(2)
        return True
    except Exception:
        try:
            window.set_focus()
            time.sleep(1)
        except Exception:
            pass
        return False


def do_doubao_signin(window, cfg):
    """豆包：打开后左下角出现「今日签到领 200 额度」卡片 → 点「立即签到」。
    优先用 UIA 精确点击；豆包不暴露控件树时退化为「实心蓝色按钮」颜色定位。"""
    import pywinauto.mouse as mouse
    from PIL import ImageGrab

    btn = find_control(window, cfg["claim_keys"], types=["Button"])
    if btn is not None:
        text = (btn.window_text() or "").strip()
        try:
            btn.click_input()
            time.sleep(3)
            return "DONE", "已点击「%s」完成豆包签到" % text
        except Exception as e:
            return "ERROR", "「%s」点击失败（%s: %s）" % (text, type(e).__name__, e)

    # 让窗口到前台再抓屏，避免被其他窗口遮挡
    _bring_front(window)
    rect = window.rectangle()

    # 打卡卡片是异步弹出的，最多轮询 40 秒等它出现
    found, img = None, None
    for _ in range(5):
        try:
            img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
        except Exception as e:
            return "ERROR", "豆包窗口截图失败（%s）" % type(e).__name__
        found = _find_blue_button(img)
        if found:
            break
        time.sleep(8)

    if not found:
        # 留一张抓屏，便于确认是「今天已签」还是「卡片没弹出」
        shot = ""
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            shot = os.path.join(SHOT_DIR, "doubao_%s.png" % time.strftime("%Y%m%d_%H%M%S"))
            img.save(shot)
        except Exception:
            shot = ""
        report = "未检测到「立即签到」按钮（可能今日已签，或打卡卡片今天不再弹出）"
        if shot:
            report += "；抓屏：%s" % shot
        return "ALREADY", report
    cx, cy, cnt = found
    try:
        mouse.click(button="left", coords=(rect.left + cx, rect.top + cy))
        time.sleep(4)
    except Exception as e:
        return "ERROR", "豆包签到按钮点击失败（%s: %s）" % (type(e).__name__, e)

    try:
        img2 = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
        after = _find_blue_button(img2)
    except Exception:
        after = None
    if after is None:
        return "DONE", "已点击左下角「立即签到」（按钮已消失，签到成功）"
    if after[2] < cnt * 0.6:
        return "DONE", "已点击左下角「立即签到」（按钮状态已变化）"
    return "ERROR", "已点击「立即签到」但按钮仍在，可能未生效（请人工确认）"


def _pick_cheapest_model(window, cfg):
    """打开模型菜单，读取每项消耗倍率（如 0.81x），选倍率最小的那个。"""
    import re

    btn, best_top = None, -1
    for c in window.descendants():
        try:
            if c.element_info.control_type != "Button":
                continue
            t = (c.window_text() or "").strip()
            if not t or len(t) > 32:
                continue
            if not any(k.lower() in t.lower() for k in cfg["model_keys"]):
                continue
            top = c.rectangle().top
            if top > best_top:          # 取最靠下（输入框工具栏）的那个
                btn, best_top = c, top
        except Exception:
            continue
    if btn is None:
        return "未找到模型选择器"
    current = (btn.window_text() or "").strip()
    try:
        btn.click_input()
        time.sleep(3)
    except Exception as e:
        return "模型选择器点击失败（%s）" % type(e).__name__

    items = []
    for c in window.descendants():
        try:
            if c.element_info.control_type != "MenuItem":
                continue
            t = (c.window_text() or "").strip()
            m = re.search(r"(\d+(?:\.\d+)?)\s*x", t)
            if not m:
                continue
            name = t.split(" 模型当前负载")[0].strip() or t.split()[0]
            items.append((float(m.group(1)), name, c))
        except Exception:
            continue
    if not items:
        try:
            window.type_keys("{ESC}")
        except Exception:
            pass
        return "模型菜单未读到消耗倍率（保持 %s）" % current
    items.sort(key=lambda x: x[0])
    mult, name, ctrl = items[0]
    try:
        ctrl.click_input()
        time.sleep(2)
    except Exception as e:
        return "最省积分模型「%s」点击失败（%s）" % (name, type(e).__name__)
    return "模型已切换为 %s（消耗 %sx，全场最低）" % (name, ("%g" % mult))


def _wait_reply(window, before_texts, timeout=120):
    """等扣子回复：出现新的大段文本即视为本轮回答完成。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            now = set()
            for c in window.descendants():
                try:
                    t = (c.window_text() or "").strip()
                    if len(t) >= 12:
                        now.add(t)
                except Exception:
                    continue
            fresh = [t for t in now - before_texts if SEND_TEXT not in t]
            if fresh:
                return fresh[0][:40]
        except Exception:
            pass
        time.sleep(5)
    return None


def do_coze_dialog(window, cfg):
    """扣子：新任务 → 选消耗积分最少的模型 → 输入「你好」→ 发送 → 等回复 → 退出。
    输入框用 UIA 的 Edit 控件定位（比坐标可靠），发送优先点「发送消息」按钮。"""
    import pywinauto.mouse as mouse
    report = []
    ok, text = click_named(window, cfg["new_keys"], wait_after=4)
    report.append("已点击「%s」" % text if ok else "未找到「新任务」，沿用当前会话")

    report.append(_pick_cheapest_model(window, cfg))

    edit = None
    for c in window.descendants():
        try:
            if c.element_info.control_type == "Edit":
                r = c.rectangle()
                if (r.right - r.left) > 200:
                    edit = c
        except Exception:
            continue
    if edit is None:
        return "ERROR", "；".join(report) + "；未找到输入框"

    before = set()
    for c in window.descendants():
        try:
            t = (c.window_text() or "").strip()
            if len(t) >= 12:
                before.add(t)
        except Exception:
            continue

    try:
        edit.click_input()
        time.sleep(1)
        set_clipboard(SEND_TEXT)
        window.type_keys("^v", with_spaces=True)
        time.sleep(1)
    except Exception as e:
        return "ERROR", "；".join(report) + "；输入失败（%s）" % type(e).__name__

    sent = False
    btn = find_control(window, ["发送消息"], types=["Button"])
    if btn is not None:
        try:
            btn.click_input()
            sent = True
        except Exception:
            sent = False
    if not sent:
        try:
            window.type_keys("{ENTER}")
            sent = True
        except Exception:
            pass
    if not sent:
        return "ERROR", "；".join(report) + "；未找到发送按钮"

    report.append("已发送「%s」" % SEND_TEXT)
    time.sleep(6)
    reply = _wait_reply(window, before)
    if reply is None:
        return "ERROR", "；".join(report) + "；等待回复超时（120 秒）"
    report.append("已收到回复（%s…）" % reply)
    return "DONE", "；".join(report) + "；签到完成"


def do_astudio_welfare(window, cfg, proc_key=None):
    """AS Studio：检测左下角「限时每日福利」弹窗 → 点「领取」。"""
    # 弹窗可能是独立窗口，也可能在主窗口内：只在本进程窗口里找，避免误点系统窗口
    found_popup, _ = try_click_in_proc(proc_key, cfg["popup_keys"], wait_after=2,
                                       main_window=window)
    ok, text = try_click_in_proc(proc_key, cfg["claim_keys"], wait_after=3,
                                 main_window=window)
    if ok:
        return "DONE", "已点击「%s」领取每日福利" % text
    if found_popup:
        return "ERROR", "已找到「限时每日福利」弹窗，但未找到「领取」按钮"
    # 弹窗未弹出绝大多数情况是当天已领取（福利一天只弹一次），记 ALREADY 不再误报失败
    return "ALREADY", "未检测到「限时每日福利」弹窗（当天已领取则不再弹出，视为已完成；若多日如此请检查客户端）"


def click_at_offset(window, dx, dy, wait_after=3):
    """点窗口右上区域的无名图标按钮（以窗口右上角为基准的偏移）。"""
    try:
        import pywinauto.mouse as m
        r = window.rectangle()
        m.click(button="left", coords=(r.right + dx, r.top + dy))
        time.sleep(wait_after)
        return True
    except Exception:
        return False


def find_titled_window(proc_key, title_key):
    """在目标进程的窗口里找标题包含关键词的窗口（如 ima 的「每日登录福利」独立窗口）。"""
    from pywinauto import Desktop
    import psutil
    for w in Desktop(backend="uia").windows():
        try:
            if not _belongs_to_proc(w, proc_key, psutil):
                continue
            if title_key in (w.window_text() or ""):
                return w
        except Exception:
            continue
    return None


def do_ima_signin(window, cfg, proc_key=None):
    """ima：我的 Copilot → 右上角设置图标 → 用量统计 → 领取算力 → 每日登录福利窗口「签到」。"""
    steps = []
    ok, text = click_named(window, cfg["copilot_keys"], wait_after=3)
    if not ok:
        return "ERROR", "未找到「我的 Copilot」入口（登录态可能缺失）"
    steps.append(text)

    dx, dy = cfg.get("settings_offset", (-96, 100))
    if not click_at_offset(window, dx, dy, wait_after=3):
        return "ERROR", "已进入「%s」，但右上角 Copilot 设置按钮点击失败" % "→".join(steps)
    steps.append("设置图标")
    time.sleep(1)

    ok, text = click_named(window, cfg["usage_keys"], wait_after=4)
    if not ok:
        return "ERROR", "路径 %s，未找到「用量统计」（设置菜单可能未打开）" % "→".join(steps)
    steps.append(text)

    time.sleep(2)  # 等右侧积分面板加载
    ok, text = click_named(window, cfg["claim_keys"], wait_after=4)
    if not ok:
        return "ERROR", "路径 %s，未找到「每日登录福利」后的「领取算力」（可能今日已领）" % "→".join(steps)
    steps.append(text)

    # 「领取算力」会打开独立的「每日登录福利」窗口，在其中点「今日 50算力」后的「签到」
    win2 = find_titled_window(proc_key, cfg["welfare_title"]) if proc_key else None
    if win2 is None:
        return "ERROR", "路径 %s，未找到「%s」窗口" % ("→".join(steps), cfg["welfare_title"])
    try:
        win2.set_focus()
        time.sleep(2)
    except Exception:
        pass
    btn = find_control(win2, cfg["final_keys"], types=["Button"])
    if btn is not None:
        try:
            btn.click_input()
            time.sleep(3)
            steps.append("签到")
            report = "ima 签到完成：%s" % "→".join(steps)
        except Exception as e:
            return "ERROR", "福利窗口「签到」点击失败（%s: %s）" % (type(e).__name__, e)
    elif find_control(win2, ["已领取"]) is not None:
        report = "ima 今日已领取（%s 窗口显示已领取）" % cfg["welfare_title"]
    else:
        return "ERROR", "福利窗口中既未找到「签到」按钮也未找到「已领取」标记"
    # 关掉福利窗口，避免堆积；主窗口按要求保持运行
    try:
        win2.close()
    except Exception:
        pass
    return "DONE", report


ACTIONS = {
    "login_only": do_login_only,
    "trae_signin": do_trae_signin,
    "coze_dialog": do_coze_dialog,
    "doubao_signin": do_doubao_signin,
    "astudio_welfare": do_astudio_welfare,
    "ima_signin": do_ima_signin,
}


def wait_window(proc_key, cfg_wait, min_controls=0, exe=None):
    """等客户端主窗口出现；min_controls>0 时继续轮询直到控件树丰富（Trae 的无障碍树加载慢且不稳定）。
    进程在运行但窗口未出现（最小化到托盘等）时，中途再次启动 exe 触发单实例机制把窗口唤出。"""
    deadline = time.time() + cfg_wait
    window = None
    relaunched = False
    while time.time() < deadline:
        window = find_window(proc_key)
        if window is not None:
            if min_controls <= 0:
                return window
            try:
                if len(window.descendants()) >= min_controls:
                    return window
            except Exception:
                pass
        elif exe and not relaunched and time.time() > deadline - cfg_wait + 30:
            relaunched = True
            try:
                subprocess.Popen([exe, "--force-renderer-accessibility"],
                                 cwd=os.path.dirname(exe),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL)
            except Exception:
                pass
        time.sleep(5)
    return window


def run_client_once(key):
    """执行单个客户端一次。返回结果 dict。"""
    cfg = CLIENTS[key]
    exe = cfg["exe"]
    name = cfg["name"]
    if not os.path.exists(exe):
        return {"agent": key, "result": "ERROR", "report": "%s 安装路径不存在：%s" % (name, exe)}

    proc_key = os.path.splitext(os.path.basename(exe))[0].lower()
    # 用户要求：每天定时任务首次执行时强制重启客户端，重启后才会弹出新的签到入口/按钮
    if process_running(proc_key):
        kill_process(proc_key)
    try:
        subprocess.Popen([exe, "--force-renderer-accessibility"],
                         cwd=os.path.dirname(exe),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL)
    except Exception as e:
        return {"agent": key, "result": "ERROR",
                "report": "%s 启动异常（%s: %s）" % (name, type(e).__name__, e)}
    time.sleep(cfg["wait"])
    if not process_running(proc_key):
        return {"agent": key, "result": "LAUNCH_FAILED",
                "report": "%s 启动后进程未留存（当前环境可能无桌面会话，"
                          "需由计划任务在登录会话中运行）" % name}

    if cfg.get("action") == "restart_only":
        time.sleep(8)  # 等客户端完成自动登录、写出新 token
        if cfg.get("exit"):
            kill_process(proc_key)
            return {"agent": key, "result": "DONE",
                    "report": "%s 已重启并自动登录（token 已刷新，供接口签到使用）；已退出" % name}
        return {"agent": key, "result": "DONE",
                "report": "%s 已重启并自动登录（token 已刷新，供接口签到使用）；保持运行" % name}

    # Trae 等无障碍树加载慢的客户端：继续轮询到控件足够丰富（最多再等 90 秒）
    window = wait_window(proc_key, 90 if key == "trae" else 45,
                         min_controls=50 if key == "trae" else 0, exe=exe)
    if window is None:
        return {"agent": key, "result": "NO_AUTH",
                "report": "%s 已运行但未找到主窗口（可能在托盘），无法自动操作" % name}

    try:
        window.set_focus()
        time.sleep(1)
    except Exception:
        pass

    if cfg["action"] == "astudio_welfare":
        result, report = do_astudio_welfare(window, cfg, proc_key)
    elif cfg["action"] == "trae_signin":
        result, report = do_trae_signin(window, cfg, proc_key)
    elif cfg["action"] == "ima_signin":
        result, report = do_ima_signin(window, cfg, proc_key)
    else:
        result, report = ACTIONS[cfg["action"]](window, cfg)

    shot = ""
    if result == "ERROR":
        shot = save_shot(window, key)
    elif result in ("DONE", "LOGGED_IN") and cfg.get("shot_on_done"):
        shot = save_shot(window, key + "_done")

    # 收尾：退出或最小化
    try:
        if cfg["exit"]:
            kill_process(proc_key)
            report += "；已退出"
        elif cfg.get("close_window"):
            # 关闭窗口但不结束进程（ima 保持在托盘）/ 关不掉就退化为最小化
            try:
                window.close()
                time.sleep(2)
            except Exception:
                try:
                    window.minimize()
                except Exception:
                    pass
            report += "；已关闭窗口（程序保持运行）"
        else:
            window.minimize()
            report += "；已最小化（保持运行）"
    except Exception as e:
        report += "；收尾异常（%s）" % type(e).__name__

    out = {"agent": key, "result": result, "report": report}
    # optional 客户端（Trae GUI）：失败降级为 SKIP，由接口签到兜底，不影响整体成败
    if result == "ERROR" and cfg.get("optional"):
        out["result"] = "SKIP"
        out["report"] = report + "（GUI 签到暂不可用，已由接口签到兜底）"
    if shot:
        out["screenshot"] = shot
    return out


def run_client(key):
    """失败自动重试一次，两次都失败才报 ERROR。"""
    r = run_client_once(key)
    log_line("%s 第一次：%s %s" % (key, r["result"], r["report"]))
    # 仅对 ERROR / NO_AUTH 重试；LAUNCH_FAILED 是环境问题，重试无意义
    if r["result"] in ("ERROR", "NO_AUTH") and MAX_RETRY > 0:
        time.sleep(5)
        r2 = run_client_once(key)
        log_line("%s 重试：%s %s" % (key, r2["result"], r2["report"]))
        if r2["result"] not in ("ERROR", "NO_AUTH"):
            r2["report"] = "（重试后成功）" + r2["report"]
            return r2
        r2["report"] = "（已重试一次仍失败）" + r2["report"]
        return r2
    return r


def cleanup_clients(keep=("ima",)):
    """签到收尾：关掉所有客户端进程，只保留 ima（以及 WorkBuddy 本身，它不在清单里）。
    用户要求：签完把软件和终端窗口都收干净，ima 保持托盘常驻。"""
    closed = []
    for key, cfg in CLIENTS.items():
        if key in keep:
            continue
        proc_key = os.path.splitext(os.path.basename(cfg["exe"]))[0].lower()
        try:
            if process_running(proc_key):
                kill_process(proc_key)
                closed.append(cfg["name"])
        except Exception:
            continue
    return closed


def main():
    keys = sys.argv[1:] or ORDER
    unknown = [k for k in keys if k not in CLIENTS]
    if unknown:
        emit({"summary": True, "error": "未知客户端: %s" % unknown})
        return 2

    results = [run_client(k) for k in keys]
    for r in results:
        emit(r)

    # 全部跑完后统一收尾（指定单端调试时不收尾，方便排查）
    closed = []
    if not sys.argv[1:]:
        try:
            closed = cleanup_clients()
            log_line("收尾：已关闭 %s" % ("、".join(closed) if closed else "（无残留进程）"))
        except Exception as e:
            log_line("收尾异常：%s" % type(e).__name__)

    OK = {"DONE", "LOGGED_IN", "SKIP", "ALREADY"}
    failed = [r["agent"] for r in results if r.get("result") not in OK]
    emit({"summary": True, "all_ok": not failed, "failed": failed, "closed": closed,
          "results": [{"agent": CLIENTS[r["agent"]]["name"], "result": r.get("result"),
                       "report": r.get("report")} for r in results]})
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

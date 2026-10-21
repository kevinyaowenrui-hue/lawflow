# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 原生无黑框桌面守护启动器 (Desktop Native Smart Supervisor)
功能：
1. 智能检测 127.0.0.1:5221 网关服务是否在线；
2. 若在线，直接唤起默认浏览器打开工作台，实现秒开且杜绝端口冲突；
3. 若不在线，自动检查并释放僵死端口，检测并拉起 Ollama 本地引擎；
4. 静默拉起 LawFlow 核心网关服务，将标准输出日志持久化至 storage/gateway.log；
5. 轮询等待健康探针（/health）确认 100% 就绪后，再自动唤起浏览器，彻底杜绝 ERR_CONNECTION_REFUSED；
6. 作为后台守护进程静默驻留，保障全系统稳定运行。
"""
import os
import sys
import time
import shutil
import urllib.request
import webbrowser
import subprocess
import ctypes
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
PORT = 5221
COMPAT_PORT = 8000
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
UI_URL = f"http://127.0.0.1:{PORT}/"
LOG_DIR = PROJECT_DIR / "storage"
LOG_FILE = LOG_DIR / "gateway.log"
CREATE_NO_WINDOW = 0x08000000
try:
    ctypes.windll.kernel32.FreeConsole()
except Exception:
    pass

def is_server_ready(port: int = PORT, path: str = "/health", timeout: float = 0.8) -> bool:
    try:
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "LawFlowLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status == 200
    except Exception:
        return False

def free_port_if_stale(port: int) -> None:
    """若端口被僵尸无响应进程占用，自动释放以防端口冲突"""
    if is_server_ready(port):
        return
    try:
        output = subprocess.check_output(
            f"netstat -ano -p tcp | findstr :{port}",
            shell=True,
            text=True,
            errors="ignore"
        )
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pid = int(parts[-1])
                if pid > 0 and pid != os.getpid():
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    time.sleep(0.3)
    except Exception:
        pass

def get_python_executable() -> str:
    # 优先定位已就绪的 hermes-agent 专用虚拟环境 Python 解释器
    user_profile = os.environ.get("USERPROFILE", "")
    venv_py = os.path.join(user_profile, r"AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe")
    if os.path.exists(venv_py):
        return venv_py
    
    # 查找 PATH 中的 python.exe
    py_in_path = shutil.which("python")
    if py_in_path and os.path.exists(py_in_path):
        return py_in_path
        
    return sys.executable or "python.exe"

def ensure_ollama_running():
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", headers={"User-Agent": "LawFlowLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=0.6) as res:
            if res.status == 200:
                return
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(0.5)
    except Exception:
        pass

def start_backend():
    free_port_if_stale(PORT)
    free_port_if_stale(COMPAT_PORT)
    ensure_ollama_running()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("a", encoding="utf-8")
    log_handle.write(f"\n--- [LawFlow Launcher 启动于 {time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
    log_handle.flush()

    py_exe = get_python_executable()
    main_py = str(PROJECT_DIR / "gateway" / "main.py")
    
    env = os.environ.copy()
    env["GATEWAY_HOST"] = "127.0.0.1"
    env["GATEWAY_PORT"] = str(PORT)
    env["PYTHONUNBUFFERED"] = "1"

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [py_exe, main_py],
        cwd=str(PROJECT_DIR),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=flags,
        close_fds=True
    )
    return proc

def open_native_app_window(url: str):
    """优先使用系统原生 Edge 或 Chrome 的独立 Profile --app 窗口模式启动"""
    local_app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    profile_dir = os.path.join(local_app_data, "DesktopAppProfiles", "LawFlow")
    os.makedirs(profile_dir, exist_ok=True)
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    ]
    si = subprocess.STARTUPINFO()
    si.lpDesktop = "WinSta0\\Default"
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 1
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([
                    exe,
                    f"--user-data-dir={profile_dir}",
                    f"--app={url}",
                    "--window-size=1440,900",
                    "--new-window",
                    "--no-first-run"
                ], startupinfo=si)
                return True
            except Exception:
                pass
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False

def main():
    already_running = is_server_ready(PORT)
    if not already_running:
        start_backend()
        ready = False
        for _ in range(60):
            time.sleep(0.25)
            if is_server_ready(PORT):
                ready = True
                break
        if not ready:
            ctypes.windll.user32.MessageBoxW(
                0,
                "LawFlow 智律工作台后端启动超时。\n请查看 storage/gateway.log 日志文件。",
                "LawFlow 启动提示",
                0x30
            )
            return
    open_native_app_window(UI_URL)

if __name__ == "__main__":
    main()

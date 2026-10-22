# -*- coding: utf-8 -*-
"""
LawFlow 智律工作台 - 原生无黑框桌面守护启动器 (Desktop Native Smart Supervisor)
功能：
1. 智能检测 127.0.0.1:5221 网关服务是否在线；
2. 若在线，直接唤起默认浏览器打开工作台；
3. 若不在线，仅在确认占用进程为 LawFlow 自身后才释放端口，再拉起网关；
4. 静默拉起 LawFlow 核心网关服务，将标准输出日志持久化至 storage/gateway.log；
5. 轮询等待健康探针（/health）确认就绪后，再自动唤起浏览器；
6. 作为后台守护进程静默驻留。
"""
import os
import sys
import time
import json
import shutil
import urllib.request
import webbrowser
import subprocess
import ctypes
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
PORT = 5221
HEALTH_URL = f"http://127.0.0.1:{PORT}/health"
UI_URL = f"http://127.0.0.1:{PORT}/"
LOG_DIR = PROJECT_DIR / "storage"
LOG_FILE = LOG_DIR / "gateway.log"
CREATE_NO_WINDOW = 0x08000000
try:
    ctypes.windll.kernel32.FreeConsole()
except Exception:
    pass


def is_lawflow_health_payload(payload) -> bool:
    """判断 /health JSON 是否标识为 LawFlow 应用。"""
    if not isinstance(payload, dict):
        return False
    return payload.get("app") == "LawFlow"


def _fetch_health_json(port: int = PORT, timeout: float = 0.8):
    url = f"http://127.0.0.1:{port}/health"
    req = urllib.request.Request(url, headers={"User-Agent": "LawFlowLauncher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        raw = res.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def is_lawflow_process_on_port(port: int = PORT) -> bool:
    """请求 /health：含 app=LawFlow → True；其他响应或连接失败 → False。"""
    try:
        return is_lawflow_health_payload(_fetch_health_json(port))
    except Exception:
        return False


def is_server_ready(port: int = PORT, path: str = "/health", timeout: float = 0.8) -> bool:
    try:
        url = f"http://127.0.0.1:{port}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "LawFlowLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status == 200
    except Exception:
        return False


def free_port_if_stale(port: int) -> bool:
    """
    仅当确认是 LawFlow 自己的健康进程（僵死需重启场景由调用方决定）或
    端口无响应时：若 /health 返回 LawFlow 标识才允许 taskkill；
    若端口被占用但不是 LawFlow，提示并返回 False（不杀进程）。
    """
    if is_server_ready(port):
        if is_lawflow_process_on_port(port):
            return True
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                f"端口 {port} 被其他程序占用，无法启动 LawFlow 智律工作台。\n请关闭占用该端口的程序后重试。",
                "LawFlow 启动提示",
                0x30,
            )
        except Exception:
            pass
        return False

    # 端口无健康响应：可能是僵死的 LawFlow，也可能是其他程序。
    # 再试一次 health；若连不上，不盲目 taskkill。
    if not is_lawflow_process_on_port(port):
        # 检查是否有进程在监听
        try:
            output = subprocess.check_output(
                f"netstat -ano -p tcp | findstr :{port}",
                shell=True,
                text=True,
                errors="ignore",
            )
        except Exception:
            return True
        listening = False
        for line in output.strip().splitlines():
            if "LISTENING" in line:
                listening = True
                break
        if listening:
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"端口 {port} 被其他程序占用，无法启动 LawFlow 智律工作台。\n请关闭占用该端口的程序后重试。",
                    "LawFlow 启动提示",
                    0x30,
                )
            except Exception:
                pass
            return False
        return True

    # 确认是 LawFlow 但后续逻辑需要重启时才杀——当前启动路径若已 ready 会直接打开 UI。
    # 此处仅在「曾是 LawFlow 且现需释放」时结束自身相关 PID。
    try:
        output = subprocess.check_output(
            f"netstat -ano -p tcp | findstr :{port}",
            shell=True,
            text=True,
            errors="ignore",
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
    return True


def get_python_executable() -> str:
    """查找顺序：项目内 .venv → LAWFLOW_PYTHON → PATH 中的 python。"""
    venv_py = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)

    env_py = (os.environ.get("LAWFLOW_PYTHON") or "").strip()
    if env_py and os.path.exists(env_py):
        return env_py

    py_in_path = shutil.which("python")
    if py_in_path and os.path.exists(py_in_path):
        # 避开 Windows Store 占位符
        if "WindowsApps" not in py_in_path:
            return py_in_path

    return sys.executable or "python.exe"


def ensure_ollama_running():
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            headers={"User-Agent": "LawFlowLauncher/1.0"},
        )
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
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)
    except Exception:
        pass


def start_backend():
    if not free_port_if_stale(PORT):
        return None
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
        close_fds=True,
    )
    return proc


def open_native_app_window(url: str):
    """优先使用系统原生 Edge 或 Chrome 的独立 Profile --app 窗口模式启动。"""
    local_app_data = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.environ.get("USERPROFILE") or str(Path.home()), "AppData", "Local"
    )
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
                subprocess.Popen(
                    [
                        exe,
                        f"--user-data-dir={profile_dir}",
                        f"--app={url}",
                        "--window-size=1440,900",
                        "--new-window",
                        "--no-first-run",
                    ],
                    startupinfo=si,
                )
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
    if already_running:
        if not is_lawflow_process_on_port(PORT):
            try:
                ctypes.windll.user32.MessageBoxW(
                    0,
                    f"端口 {PORT} 被其他程序占用，无法打开 LawFlow 智律工作台。",
                    "LawFlow 启动提示",
                    0x30,
                )
            except Exception:
                pass
            return
        open_native_app_window(UI_URL)
        return

    proc = start_backend()
    if proc is None:
        return
    ready = False
    for _ in range(60):
        time.sleep(0.25)
        if is_server_ready(PORT) and is_lawflow_process_on_port(PORT):
            ready = True
            break
    if not ready:
        ctypes.windll.user32.MessageBoxW(
            0,
            "LawFlow 智律工作台后端启动超时。\n请查看 storage/gateway.log 日志文件。",
            "LawFlow 启动提示",
            0x30,
        )
        return
    open_native_app_window(UI_URL)


if __name__ == "__main__":
    main()

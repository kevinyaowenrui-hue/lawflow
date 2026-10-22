# -*- coding: utf-8 -*-
"""基于脚本所在目录更新桌面快捷方式（相对路径，无个人盘符）。"""
import os
from pathlib import Path

try:
    import win32com.client
except ImportError as e:
    raise SystemExit(
        "需要 pywin32 才能更新 .lnk：pip install pywin32\n" + str(e)
    )

desktop = Path.home() / "Desktop"
if not desktop.is_dir():
    userprofile = os.environ.get("USERPROFILE") or str(Path.home())
    desktop = Path(userprofile) / "Desktop"

shortcut_path = desktop / "LawFlow 智律工作台.lnk"
project_dir = Path(__file__).resolve().parent.parent
venv_pythonw = project_dir / ".venv" / "Scripts" / "pythonw.exe"
launcher_pyw = project_dir / "launcher.pyw"
launcher_vbs = project_dir / "launcher.vbs"
icon_path = project_dir / "resources" / "lawflow.ico"

shell = win32com.client.Dispatch("WScript.Shell")
shortcut = shell.CreateShortCut(str(shortcut_path))

if venv_pythonw.is_file():
    shortcut.TargetPath = str(venv_pythonw)
    shortcut.Arguments = f'"{launcher_pyw}"'
else:
    shortcut.TargetPath = "wscript.exe"
    shortcut.Arguments = f'"{launcher_vbs}"'

shortcut.WorkingDirectory = str(project_dir)
shortcut.IconLocation = f"{icon_path},0"
shortcut.Description = "LawFlow 智律工作台 - 面向中国执业律师的本地私有化办案提效系统"
shortcut.Save()

print("Shortcut updated successfully!")
print("Target:", shortcut.TargetPath)
print("Arguments:", shortcut.Arguments)
print("WorkingDirectory:", shortcut.WorkingDirectory)
print("IconLocation:", shortcut.IconLocation)

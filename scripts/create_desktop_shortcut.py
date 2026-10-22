# -*- coding: utf-8 -*-
"""基于脚本所在目录创建桌面快捷方式（相对路径，无个人盘符）。"""
import os
import subprocess
from pathlib import Path


def make_shortcut():
    home = Path.home()
    desktop = home / "Desktop"
    if not desktop.is_dir():
        userprofile = os.environ.get("USERPROFILE") or str(home)
        desktop = Path(userprofile) / "Desktop"

    workspace_dir = Path(__file__).resolve().parent.parent
    shortcut_path = desktop / "LawFlow 智律工作台.lnk"
    icon_path = workspace_dir / "resources" / "lawflow.ico"
    vbs_path = workspace_dir / "launcher.vbs"

    ps_script = f"""
$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut('{shortcut_path}')
$sc.TargetPath = 'wscript.exe'
$sc.Arguments = '"{vbs_path}"'
$sc.WorkingDirectory = '{workspace_dir}'
$sc.IconLocation = '{icon_path},0'
$sc.Description = 'LawFlow 智律工作台 - 面向中国执业律师的私有化办案提效系统'
$sc.Save()
"""
    tmp_ps1 = workspace_dir / "scripts" / "temp_create_shortcut.ps1"
    tmp_ps1.write_text(ps_script, encoding="utf-8-sig")

    res = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(tmp_ps1)],
        capture_output=True,
        text=True,
    )
    if tmp_ps1.exists():
        tmp_ps1.unlink()

    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
    exists = shortcut_path.exists()
    print(f"桌面快捷方式生成状态: {exists} -> {shortcut_path}")
    return exists


if __name__ == "__main__":
    make_shortcut()

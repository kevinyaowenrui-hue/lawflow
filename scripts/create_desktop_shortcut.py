import os
import subprocess

def make_shortcut():
    desktop = os.path.expanduser(r"~\Desktop")
    if not os.path.exists(desktop):
        # Alternative Windows desktop lookup
        desktop = os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\kevin"), "Desktop")
    
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shortcut_path = os.path.join(desktop, "LawFlow 智律工作台.lnk")
    icon_path = os.path.join(workspace_dir, "resources", "lawflow.ico")
    vbs_path = os.path.join(workspace_dir, "launcher.vbs")

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
    tmp_ps1 = os.path.join(workspace_dir, "scripts", "temp_create_shortcut.ps1")
    with open(tmp_ps1, "w", encoding="utf-8-sig") as f:
        f.write(ps_script)

    res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", tmp_ps1], capture_output=True, text=True)
    if os.path.exists(tmp_ps1):
        os.remove(tmp_ps1)

    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
    exists = os.path.exists(shortcut_path)
    print(f"桌面快捷方式生成状态: {exists} -> {shortcut_path}")
    return exists

if __name__ == "__main__":
    make_shortcut()

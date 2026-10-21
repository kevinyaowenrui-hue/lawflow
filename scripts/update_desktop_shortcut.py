import os
import win32com.client

desktop = os.path.expanduser('~/Desktop')
shortcut_path = os.path.join(desktop, 'LawFlow 智律工作台.lnk')

pythonw_exe = os.path.expandvars(r'%USERPROFILE%\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe')
project_dir = r'F:\antigravity exports\LawFlow 智律工作台'
launcher_pyw = os.path.join(project_dir, 'launcher.pyw')
icon_path = os.path.join(project_dir, 'resources', 'lawflow.ico')

shell = win32com.client.Dispatch('WScript.Shell')
shortcut = shell.CreateShortCut(shortcut_path)
shortcut.TargetPath = pythonw_exe
shortcut.Arguments = f'"{launcher_pyw}"'
shortcut.WorkingDirectory = project_dir
shortcut.IconLocation = f'{icon_path},0'
shortcut.Description = 'LawFlow 智律工作台 - 面向中国执业律师的本地私有化办案提效系统'
shortcut.Save()

print('Shortcut updated successfully!')
print('Target:', shortcut.TargetPath)
print('Arguments:', shortcut.Arguments)
print('WorkingDirectory:', shortcut.WorkingDirectory)
print('IconLocation:', shortcut.IconLocation)

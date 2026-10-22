Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strAppDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strLauncherPyw = objFSO.BuildPath(strAppDir, "launcher.pyw")
objShell.CurrentDirectory = strAppDir

' 优先使用项目内 .venv\Scripts\pythonw.exe，其次 PATH 中的 pythonw
strVenvPyw = objFSO.BuildPath(strAppDir, ".venv\Scripts\pythonw.exe")

If objFSO.FileExists(strVenvPyw) Then
    strCmd = """" & strVenvPyw & """ """ & strLauncherPyw & """"
Else
    strCmd = "pythonw.exe """ & strLauncherPyw & """"
End If

objShell.Run strCmd, 0, False

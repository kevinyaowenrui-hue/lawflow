Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strAppDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strLauncherPyw = objFSO.BuildPath(strAppDir, "launcher.pyw")
objShell.CurrentDirectory = strAppDir

strHermesPyw = objShell.ExpandEnvironmentStrings("%USERPROFILE%\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe")

If objFSO.FileExists(strHermesPyw) Then
    strCmd = """" & strHermesPyw & """ """ & strLauncherPyw & """"
Else
    strCmd = "pythonw.exe """ & strLauncherPyw & """"
End If

objShell.Run strCmd, 0, False

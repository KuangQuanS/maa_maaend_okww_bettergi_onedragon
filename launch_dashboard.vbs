Option Explicit

Dim fso, shell, root, pythonw, scriptPath, command, extraArgs, arg, i

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    pythonw = "D:\python\pythonw.exe"
End If

scriptPath = root & "\scripts\launch_dashboard.py"

If Not fso.FileExists(pythonw) Then
    MsgBox "Pythonw was not found. Check .venv or D:\python.", vbCritical, "Dashboard"
    WScript.Quit 1
End If

If Not fso.FileExists(scriptPath) Then
    MsgBox "Launch script was not found:" & vbCrLf & scriptPath, vbCritical, "Dashboard"
    WScript.Quit 1
End If

extraArgs = ""
For i = 0 To WScript.Arguments.Count - 1
    arg = WScript.Arguments.Item(i)
    extraArgs = extraArgs & " " & Chr(34) & arg & Chr(34)
Next

command = """" & pythonw & """ """ & scriptPath & """" & extraArgs
shell.Run command, 1, False

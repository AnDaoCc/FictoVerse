Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

' === Fallback 1: standalone exe ===
distDir = scriptDir & "\dist"
If fso.FolderExists(distDir) Then
  For Each subFolder In fso.GetFolder(distDir).SubFolders
    If fso.FolderExists(subFolder.Path & "\_internal") Then
      For Each exeFile In subFolder.Files
        If LCase(fso.GetExtensionName(exeFile.Name)) = "exe" Then
          shell.CurrentDirectory = subFolder.Path
          shell.Run """" & exeFile.Path & """", 1, False
          WScript.Quit 0
        End If
      Next
    End If
  Next
End If

' === Fallback 2: .venv pythonw ===
pythonw = scriptDir & "\.venv\Scripts\pythonw.exe"
pyvenvCfg = scriptDir & "\.venv\pyvenv.cfg"
If fso.FileExists(pyvenvCfg) And fso.FileExists(pythonw) Then
  shell.CurrentDirectory = scriptDir
  shell.Run """" & pythonw & """ -m novel_world.web.run", 0, False
  WScript.Quit 0
End If

' === Fallback 3: batch launcher ===
batPath = scriptDir & "\GUI启动器.bat"
If fso.FileExists(batPath) Then
  shell.CurrentDirectory = scriptDir
  shell.Run """" & batPath & """", 1, False
  WScript.Quit 0
End If

' === Fallback 4: error ===
MsgBox "Launcher not found." & vbCrLf & vbCrLf & _
  "Please download the full installer package.", _
  vbExclamation, "FictoVerse"
WScript.Quit 1
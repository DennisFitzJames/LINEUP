Option Explicit

Dim SapGuiAuto, application, connection, session
Dim fso, scriptFolder, projectRoot, exportPath, archivePath
Dim latestFileName, timestampFileName, latestFilePath, timestampText
Dim grid

Set fso = CreateObject("Scripting.FileSystemObject")
scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptFolder)
exportPath = projectRoot & "\data\raw"
archivePath = projectRoot & "\data\archive"

EnsureFolder projectRoot & "\data"
EnsureFolder exportPath
EnsureFolder archivePath

latestFileName = "LRF2_Latest.txt"
latestFilePath = exportPath & "\" & latestFileName
timestampText = TimestampForFile()
timestampFileName = "LRF2_" & timestampText & ".txt"

DeleteFileIfExists latestFilePath

On Error Resume Next
Set SapGuiAuto = GetObject("SAPGUI")
CheckError "connecting to SAP GUI"

Set application = SapGuiAuto.GetScriptingEngine
Set connection = application.Children(0)
Set session = connection.Children(0)
CheckError "finding an active SAP session"
On Error GoTo 0

session.findById("wnd[0]").maximize
session.findById("wnd[0]/tbar[0]/okcd").Text = "/nLRF2"
session.findById("wnd[0]").sendVKey 0
WaitForSAPReady session, 30

On Error Resume Next
Set grid = session.findById("wnd[0]/usr/cntlD100_CCTR/shellcont/shell/shellcont[1]/shell")
CheckError "opening the LRF2 results grid"
On Error GoTo 0

grid.contextMenu
grid.pressToolbarContextButton "&MB_EXPORT"
grid.selectContextMenuItem "&PC"

WaitForWindow session, "wnd[1]", 15
session.findById("wnd[1]").sendVKey 0

WaitForWindow session, "wnd[1]/usr/ctxtDY_PATH", 15
session.findById("wnd[1]/usr/ctxtDY_PATH").Text = exportPath
session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = latestFileName
session.findById("wnd[1]").sendVKey 0

If Not WaitForExport(latestFilePath, 60) Then
    Fail "LRF2 text export did not become ready within 60 seconds: " & latestFilePath
End If

ArchiveFile latestFilePath, archivePath & "\" & timestampFileName

WScript.Echo "LRF2 text export complete:"
WScript.Echo latestFilePath
WScript.Quit 0

Sub CheckError(stepName)
    If Err.Number <> 0 Then
        Dim message
        message = Err.Description
        Err.Clear
        Fail "LRF2 failed while " & stepName & ": " & message
    End If
End Sub

Sub Fail(message)
    WScript.Echo "ERROR: " & message
    WScript.Quit 1
End Sub

Sub EnsureFolder(folderPath)
    Dim parentPath
    If fso.FolderExists(folderPath) Then Exit Sub

    parentPath = fso.GetParentFolderName(folderPath)
    If parentPath <> "" And Not fso.FolderExists(parentPath) Then
        EnsureFolder parentPath
    End If

    On Error Resume Next
    fso.CreateFolder folderPath
    If Err.Number <> 0 Then
        Dim message
        message = Err.Description
        Err.Clear
        On Error GoTo 0
        Fail "Could not create folder " & folderPath & ": " & message
    End If
    On Error GoTo 0
End Sub

Sub DeleteFileIfExists(filePath)
    If Not fso.FileExists(filePath) Then Exit Sub

    On Error Resume Next
    fso.DeleteFile filePath, True
    If Err.Number <> 0 Then
        Dim message
        message = Err.Description
        Err.Clear
        On Error GoTo 0
        Fail "Could not replace existing export " & filePath & ": " & message
    End If
    On Error GoTo 0
End Sub

Sub WaitForSAPReady(sessionObject, timeoutSeconds)
    Dim deadline
    deadline = DateAdd("s", timeoutSeconds, Now)

    Do While Now < deadline
        On Error Resume Next
        If Not sessionObject.Busy Then
            On Error GoTo 0
            Exit Sub
        End If
        Err.Clear
        On Error GoTo 0
        WScript.Sleep 250
    Loop

    Fail "SAP remained busy for more than " & timeoutSeconds & " seconds."
End Sub

Sub WaitForWindow(sessionObject, objectId, timeoutSeconds)
    Dim deadline, testObject
    deadline = DateAdd("s", timeoutSeconds, Now)

    Do While Now < deadline
        Set testObject = Nothing
        On Error Resume Next
        Set testObject = sessionObject.findById(objectId)
        On Error GoTo 0

        If Not testObject Is Nothing Then Exit Sub
        WScript.Sleep 250
    Loop

    Fail "SAP window or control did not appear: " & objectId
End Sub

Function WaitForExport(filePath, timeoutSeconds)
    Dim deadline, previousSize, stableChecks, currentSize
    deadline = DateAdd("s", timeoutSeconds, Now)
    previousSize = -1
    stableChecks = 0

    Do While Now < deadline
        If fso.FileExists(filePath) Then
            On Error Resume Next
            currentSize = fso.GetFile(filePath).Size
            If Err.Number = 0 And currentSize > 0 Then
                If currentSize = previousSize Then
                    stableChecks = stableChecks + 1
                Else
                    stableChecks = 0
                    previousSize = currentSize
                End If

                If stableChecks >= 3 Then
                    On Error GoTo 0
                    WaitForExport = True
                    Exit Function
                End If
            Else
                Err.Clear
            End If
            On Error GoTo 0
        End If

        WScript.Sleep 500
    Loop

    WaitForExport = False
End Function

Sub ArchiveFile(sourcePath, destinationPath)
    If Not fso.FileExists(sourcePath) Then Exit Sub

    On Error Resume Next
    fso.CopyFile sourcePath, destinationPath, True
    If Err.Number <> 0 Then
        WScript.Echo "WARNING: Could not archive LRF2 export: " & Err.Description
        Err.Clear
    End If
    On Error GoTo 0
End Sub

Function TimestampForFile()
    TimestampForFile = Year(Now) _
        & Right("0" & Month(Now), 2) _
        & Right("0" & Day(Now), 2) _
        & "_" _
        & Right("0" & Hour(Now), 2) _
        & Right("0" & Minute(Now), 2) _
        & Right("0" & Second(Now), 2)
End Function

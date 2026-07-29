Option Explicit
 
Dim SapGuiAuto, application, connection, session
Dim shell, fso
Dim scriptFolder, projectRoot, exportPath, archivePath
Dim latestFileName, timestampFileName, timestampText
 
Set shell = CreateObject("WScript.Shell")
    Set fso = CreateObject("Scripting.FileSystemObject")
 
' This script is expected to live in:
' C:\LINEUP\sap_scripts
'
' Therefore:
' scriptFolder = C:\LINEUP\sap_scripts
' projectRoot  = C:\LINEUP
scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectRoot = fso.GetParentFolderName(scriptFolder)
 
exportPath = projectRoot & "\data\raw"
archivePath = projectRoot & "\data\archive"
 
EnsureFolder projectRoot
EnsureFolder projectRoot & "\data"
EnsureFolder exportPath
EnsureFolder archivePath
 
latestFileName = "COOIS_ProductionList_Latest.txt"
 
timestampText = Year(Now) _
    & Right("0" & Month(Now), 2) _
    & Right("0" & Day(Now), 2) _
    & "_" _
    & Right("0" & Hour(Now), 2) _
    & Right("0" & Minute(Now), 2) _
    & Right("0" & Second(Now), 2)
 
timestampFileName = "COOIS_ProductionList_" & timestampText & ".txt"
 
On Error Resume Next
 
Set SapGuiAuto = GetObject("SAPGUI")
If Err.Number <> 0 Then
    MsgBox "SAP GUI is not open. Please open SAP and log in first.", vbCritical
    WScript.Quit 1
End If
 
Set application = SapGuiAuto.GetScriptingEngine
Set connection = application.Children(0)
Set session = connection.Children(0)
 
If Err.Number <> 0 Or session Is Nothing Then
    MsgBox "Could not connect to an active SAP session.", vbCritical
    WScript.Quit 1
End If
 
On Error GoTo 0
 
session.findById("wnd[0]").maximize
 
session.findById("wnd[0]/tbar[0]/okcd").Text = "/ncoois"
session.findById("wnd[0]").sendVKey 0
 
' Select list type: Production List
session.findById("wnd[0]/usr/ssub%_SUBSCREEN_TOPBLOCK:PPIO_ENTRY:1100/cmbPPIO_ENTRY_SC1100-PPIO_LISTTYP").Key = "PPIOP000"
 
' Layout
session.findById("wnd[0]/usr/ssub%_SUBSCREEN_TOPBLOCK:PPIO_ENTRY:1100/ctxtPPIO_ENTRY_SC1100-ALV_VARIANT").Text = "PROJECTPLN2"
 
' Plant
session.findById("wnd[0]/usr/tabsTABSTRIP_SELBLOCK/tabpSEL_00/ssub%_SUBSCREEN_SELBLOCK:PPIO_ENTRY:1200/ctxtS_WERKS-LOW").Text = "0787"
 
' Selection profile
session.findById("wnd[0]/usr/tabsTABSTRIP_SELBLOCK/tabpSEL_00/ssub%_SUBSCREEN_SELBLOCK:PPIO_ENTRY:1200/ctxtP_SELID").Text = "Z000019"
 
session.findById("wnd[0]").sendVKey 0
 
' Execute
session.findById("wnd[0]").sendVKey 8
 
' Export to local file
session.findById("wnd[0]/usr/cntlCUSTOM/shellcont/shell/shellcont/shell").pressToolbarContextButton "&MB_EXPORT"
session.findById("wnd[0]/usr/cntlCUSTOM/shellcont/shell/shellcont/shell").selectContextMenuItem "&PC"
 
' Confirm export format dialog
session.findById("wnd[1]").sendVKey 0
 
' Save latest file
session.findById("wnd[1]/usr/ctxtDY_PATH").Text = exportPath 

session.findById("wnd[1]/usr/ctxtDY_FILENAME").Text = latestFileName 

session.findById("wnd[1]/tbar[0]/btn[11]").press
 
' Also archive a timestamped copy
If fso.FileExists(exportPath & "\" & latestFileName) Then
    fso.CopyFile exportPath & "\" & latestFileName, archivePath & "\" & timestampFileName, True
End If
 
WScript.Echo "COOIS production list export complete:"
WScript.Echo exportPath & "\" & latestFileName
 
Sub EnsureFolder(folderPath)
    If Not fso.FolderExists(folderPath) Then
        On Error Resume Next
        fso.CreateFolder folderPath
 
        If Err.Number <> 0 Then
            MsgBox "Failed to create folder: " & folderPath & vbCrLf & Err.Description, vbCritical
            WScript.Quit 1
        End If
 
        On Error GoTo 0
    End If
End Sub
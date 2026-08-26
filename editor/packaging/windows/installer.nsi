Unicode True
Name "JSON API Forge Editor 0.5.0"
OutFile "${OUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\JSON API Forge Editor"
InstallDirRegKey HKCU "Software\JSON API Forge Editor" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "${ICON_FILE}"
UninstallIcon "${ICON_FILE}"

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "JSON API Forge Editor" SecMain
  SetOutPath "$INSTDIR"
  File /r "${STAGE_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\JSON API Forge Editor" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JSON API Forge Editor" "DisplayName" "JSON API Forge Editor"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JSON API Forge Editor" "DisplayVersion" "0.5.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JSON API Forge Editor" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  CreateDirectory "$SMPROGRAMS\JSON API Forge Editor"
  CreateShortcut "$SMPROGRAMS\JSON API Forge Editor\JSON API Forge Editor.lnk" "$INSTDIR\bin\JSON-API-Forge-Editor.exe"
  CreateShortcut "$DESKTOP\JSON API Forge Editor.lnk" "$INSTDIR\bin\JSON-API-Forge-Editor.exe"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\JSON API Forge Editor.lnk"
  Delete "$SMPROGRAMS\JSON API Forge Editor\JSON API Forge Editor.lnk"
  RMDir "$SMPROGRAMS\JSON API Forge Editor"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\JSON API Forge Editor"
  DeleteRegKey HKCU "Software\JSON API Forge Editor"
  RMDir /r "$INSTDIR"
SectionEnd

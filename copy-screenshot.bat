@echo off
mkdir "%~dp0docs" 2>nul
copy /Y "%USERPROFILE%\.cursor\projects\c-Users-yu-lapova-Documents-GitHub-TimeTrack\assets\c__Users_yu.lapova_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images_image-e7fca27a-92c1-4945-91a0-57260e24bc96.png" "%~dp0docs\stats-window.png"
if exist "%~dp0docs\stats-window.png" (
  echo OK: docs\stats-window.png
) else (
  echo FAIL: source image not found
)
pause

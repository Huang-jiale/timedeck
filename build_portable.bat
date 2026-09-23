@echo off
chcp 65001 >nul
rem 重新打包便携版：改完源码后双击这个文件即可。
rem 产物在 ..\发布\TimeDeck\ ，整个文件夹可以拷给别人，不需要对方装 Python。
cd /d "%~dp0"
set DIST=%~dp0..\发布
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name TimeDeck ^
  --icon "%~dp0app.ico" --distpath "%DIST%" --workpath "%~dp0.build" --specpath "%~dp0.build" ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebEngine --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuickWidgets --exclude-module PySide6.Qt3DCore --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtDataVisualization --exclude-module PySide6.QtTest --exclude-module PySide6.QtPdf ^
  --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtMultimediaWidgets ^
  --exclude-module PySide6.QtDesigner --exclude-module PySide6.QtUiTools --exclude-module PySide6.QtBluetooth ^
  --exclude-module PySide6.QtSerialPort --exclude-module PySide6.QtSql --exclude-module PySide6.QtPositioning ^
  --exclude-module PySide6.QtLocation --exclude-module PySide6.QtRemoteObjects --exclude-module PySide6.QtSensors ^
  --exclude-module PySide6.QtTextToSpeech --exclude-module PySide6.QtHelp --exclude-module PySide6.QtNetwork ^
  --exclude-module PySide6.QtSvg --exclude-module PySide6.QtSvgWidgets ^
  main.py
echo.
if exist "%DIST%\TimeDeck\TimeDeck.exe" (
  echo [OK] 打包完成：%DIST%\TimeDeck\TimeDeck.exe
) else (
  echo [X] 打包失败，看看上面的报错
)
pause

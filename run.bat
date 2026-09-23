@echo off
cd /d "%~dp0"
".venv\Scripts\pythonw.exe" main.py
if errorlevel 1 (
  echo 启动失败，下面是错误信息：
  ".venv\Scripts\python.exe" main.py
  pause
)

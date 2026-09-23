@echo off
rem rebuild portable build
cd /d "%~dp0"
.venv\Scripts\python.exe build_portable.py
pause

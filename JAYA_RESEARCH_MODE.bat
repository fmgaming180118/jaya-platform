@echo off
title JAYA - RESEARCH MODE
cls
echo ==================================================
echo           J A Y A   R E S E A R C H
echo           Initializing UI and API...
echo ==================================================
REM Pastikan berpindah ke direktori script (termasuk pergantian drive)
pushd "%~dp0JAYA_RESEARCH"
call start_jaya.bat
popd
pause

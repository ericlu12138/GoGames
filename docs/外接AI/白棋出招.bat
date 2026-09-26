@echo off
chcp 65001 >nul
title 白方(GPT)出招
:loop
echo.
echo ==========================================
echo   输入 GPT 回的坐标(例如 C3 / pass)
echo   直接回车 = 退出
echo ==========================================
set /p mv="白棋下: "
if "%mv%"=="" goto end
echo %mv%>"F:\围棋\外接AI\white_move.txt"
echo 已写入 white_move.txt: %mv%
timeout /t 2 >nul
goto loop
:end
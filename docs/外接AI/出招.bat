@echo off
chcp 65001 >nul
title 写一着给外接AI
:loop
echo.
echo ============================================
echo   把外接AI回的坐标写进来(例如 E5 / pass)
echo   直接回车 = 退出
echo ============================================
set /p mv="坐标: "
if "%mv%"=="" goto end
echo %mv%>"F:\围棋\外接AI\ai_move.txt"
echo 已写入 ai_move.txt: %mv%
timeout /t 2 >nul
goto loop
:end
@echo off
chcp 65001 > nul
title ARGOS WORKS Server
echo ========================================================
echo   ARGOS WORKS 백엔드 서버를 시작합니다...
echo   접속 주소: http://localhost:8080
echo ========================================================
python server\main.py
pause

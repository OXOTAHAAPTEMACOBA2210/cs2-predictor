@echo off
chcp 65001 > nul
title FACEIT AI Predictor & Dodge Scout (CS2)
echo ============================================================
echo   ЗАПУСК ВЕБ-ПРИЛОЖЕНИЯ: FACEIT AI PREDICTOR & DODGE SCOUT
echo ============================================================
echo.
echo Открытие приложения в браузере...
cd /d "%~dp0"
C:\ProgramData\anaconda3\python.exe -m streamlit run app.py
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".env" (
    echo .env fayli yo'q! .env.example ni nusxalab .env deb nomlang va BOT_TOKEN ni yozing.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Birinchi ishga tushirish: kutubxonalar o'rnatilmoqda...
    where py >nul 2>nul && (py -m venv .venv) || (python -m venv .venv)
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

:loop
echo Bot ishga tushdi. To'xtatish uchun bu oynani yoping.
".venv\Scripts\python.exe" bot.py
echo Bot to'xtadi. 10 soniyadan keyin qayta ishga tushadi...
timeout /t 10 >nul
goto loop

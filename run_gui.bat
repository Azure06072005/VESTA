@echo off
title VESTA Quantitative Lakehouse — Desktop Crawler Controller
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m src.crawlers.vesta_crawler_gui
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m src.crawlers.vesta_crawler_gui
) else (
    python -m src.crawlers.vesta_crawler_gui
)

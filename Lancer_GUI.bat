@echo off
REM Lanceur pour l'application BambuLab Timelapse YouTube
REM Active l'environnement virtuel et lance le script Python

REM Activer l'environnement virtuel
call .\.venv\Scripts\activate.bat

REM Lancer le script Python
python bambu_export_yt_gui.py

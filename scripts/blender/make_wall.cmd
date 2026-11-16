@echo off
rem Erzeugt test_wall.blend / .glb / Vorschau neu (Blender im Hintergrund)
"%LOCALAPPDATA%\Microsoft\WindowsApps\blender-launcher.exe" --background --factory-startup --python "%~dp0make_wall.py"

@echo off
rem Erzeugt test_rock.blend / .glb / Vorschau neu (Blender im Hintergrund)
"%LOCALAPPDATA%\Microsoft\WindowsApps\blender-launcher.exe" --background --factory-startup --python "%~dp0make_rock.py"

@echo off
echo Building watcher.exe ...
pyinstaller watcher.py ^
  --onefile ^
  --console ^
  --name watcher ^
  --hidden-import mss.windows ^
  --hidden-import cv2 ^
  --hidden-import numpy
echo.
echo Done. Find watcher.exe in dist\
pause

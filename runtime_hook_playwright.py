"""
PyInstaller runtime hook — set PLAYWRIGHT_BROWSERS_PATH so that
playwright can find the bundled Chromium browser inside the exe.

When running from a PyInstaller bundle:
  - OneFile mode:  browsers are extracted to  sys._MEIPASS / ms-playwright
  - Folder mode:   browsers sit next to the exe in  <exe_dir> / ms-playwright
"""

import os
import sys

if getattr(sys, 'frozen', False):
    # Determine base directory
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    browsers_dir = os.path.join(base, 'ms-playwright')
    if os.path.isdir(browsers_dir):
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir

import tempfile, os
from pathlib import Path
from mss import mss
from mss.tools import to_png

p = Path(tempfile.gettempdir()) / "test_mss_screenshot.png"
with mss() as sct:
    monitor = sct.monitors[0]
    image = sct.grab(monitor)
    result = to_png(image.rgb, image.size, output=str(p))
    rtype = type(result)
    rval = result[:20] if result else "None"
    exists = p.exists()
    print("Result type:", rtype)
    print("Result value (first 20):", rval)
    print("File exists:", exists)
    if exists:
        fsize = p.stat().st_size
        print("File size:", fsize)

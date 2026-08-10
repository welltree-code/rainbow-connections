"""Web build entry point.

pygbag's browser runtime hardcodes its entry point lookup to a file
literally named main.py (see the generated index.html's
`main = appdir / "assets" / "main.py"`), regardless of what script name
was passed to the build CLI. This thin shim exists only so the web build
can find something at that fixed path; the actual game lives in
RainbowConnections.py, which is still the file to run directly for
desktop play (`python3 RainbowConnections.py`).
"""

import asyncio

from RainbowConnections import main

asyncio.run(main())

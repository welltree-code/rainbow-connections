"""Web build entry point.

pygbag's browser runtime hardcodes its entry point lookup to a file
literally named main.py (see the generated index.html's
`main = appdir / "assets" / "main.py"`), regardless of what script name
was passed to the build CLI. This file exists so the web build can find
something at that fixed path; the actual game lives in
RainbowConnections.py, which is still the file to run directly for
desktop play (`python3 RainbowConnections.py`).

pygame.init()/set_mode() are called here directly, as genuine top-level
statements in the file pygbag actually runs, rather than as a side effect
of importing RainbowConnections - when they instead ran at module scope
inside RainbowConnections.py (only reached via this file's `from
RainbowConnections import main`), pygame came back partially initialized
under pygbag's web runtime specifically (pygame.init was simply missing
as an attribute afterward), even though desktop Python never cared about
the distinction.
"""

import asyncio

import pygame

from RainbowConnections import WINDOW_SIZE, main

pygame.init()
screen = pygame.display.set_mode(WINDOW_SIZE)
pygame.display.set_caption("Rainbow Connections")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 20)
big_font = pygame.font.Font(None, 48)

asyncio.run(main(screen, clock, font, big_font))

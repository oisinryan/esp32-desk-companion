#!/usr/bin/env python3
"""Create geometric test pixels for Codey compile checks; no third-party artwork."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
target = ROOT/'artifacts/ci-sheet.webp'
target.parent.mkdir(exist_ok=True)
image = Image.new('RGBA', (1536, 2288), (246, 245, 240, 255))
draw = ImageDraw.Draw(image)
for row in range(11):
    for col in range(8):
        x, y = col*192, row*208
        draw.rectangle((x+30,y+30,x+140,y+170), fill=(60+col*20,60+row*12,180,255))
image.save(target, lossless=True)
print(target)

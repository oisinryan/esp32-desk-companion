#!/usr/bin/env python3
"""Encode the installed Codey sprite sheet for personal ESP32 use.

Artwork remains OpenAI's; generated assets are excluded from source archives.
"""
import argparse, json, struct
from itertools import groupby
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sheet', type=Path, help='A compatible sprite sheet you have permission to use')
parser.add_argument('--app', type=Path, default=Path('/Applications/ChatGPT.app'), help='Installed macOS app bundle')
args = parser.parse_args()
(ROOT/'artifacts').mkdir(exist_ok=True)
if args.sheet:
    sheet = Image.open(args.sheet).convert('RGBA')
    import io
    output = io.BytesIO(); sheet.save(output, format='WEBP', lossless=True)
    encoded = output.getvalue()
else:
    with (args.app/'Contents/Resources/app.asar').open('rb') as f:
        h = struct.unpack('<4I', f.read(16))
        tree = json.loads(f.read(h[3]))
        assets = tree['files']['webview']['files']['assets']['files']
        names = [n for n in assets if n.startswith('codex-spritesheet-') and n.endswith('.webp')]
        if len(names) != 1: raise SystemExit('Expected one installed Codey sprite sheet; supply --sheet instead')
        entry = assets[names[0]]
        f.seek(8 + h[1] + int(entry['offset']))
        import io
        encoded = f.read(entry['size'])
        sheet = Image.open(io.BytesIO(encoded)).convert('RGBA')
if sheet.size[0] != 1536 or sheet.size[1] < 1872:
    raise SystemExit('Unsupported sprite grid; inspect new app assets before exporting')

(ROOT/'bridge/public/codey-sheet.webp').write_bytes(encoded)

BG = (246,245,240)
base = Image.new('RGBA', sheet.size, BG+(255,)); base.alpha_composite(sheet)
palette = base.convert('RGB').quantize(colors=64, method=Image.Quantize.MEDIANCUT)
rgb = palette.getpalette()[:192]
colors = [0xf6f5f0,0xffffff,0x243146,0x658bed,0x707787,0xa6dfe8]
colors += [(rgb[i]<<16)|(rgb[i+1]<<8)|rgb[i+2] for i in range(0,len(rgb),3)]
# idle, running, needs input, ready, failed, waving. Same rows as desktop Codey.
rows = [(0,6),(7,6),(6,6),(8,6),(5,8),(3,4)]
blob=bytearray(); offsets=[]; starts=[]; counts=[]
for row,count in rows:
    starts.append(len(offsets)); counts.append(count)
    for col in range(count):
        cell=base.crop((col*192,row*208,(col+1)*192,(row+1)*208))
        cell=cell.resize((144,156),Image.Resampling.NEAREST).convert('RGB')
        indices=cell.quantize(palette=palette,dither=Image.Dither.NONE).tobytes()
        offsets.append(len(blob))
        for value,group in groupby(indices):
            remaining=sum(1 for _ in group)
            while remaining:
                size=min(remaining,255); blob.extend((size,value+6)); remaining-=size
offsets.append(len(blob))
def array(name, kind, values):
    lines=[','.join(str(v) for v in values[i:i+32]) for i in range(0,len(values),32)]
    return f'const {kind} {name}[] PROGMEM = {{\n'+',\n'.join(lines)+'\n};\n'
out='#pragma once\n#include <Arduino.h>\n// Generated from installed OpenAI artwork; personal device use.\n'
out+=array('codeyColors','uint32_t',colors)
out+=array('codeyStarts','uint8_t',starts)+array('codeyCounts','uint8_t',counts)
out+=array('codeyOffsets','uint32_t',offsets)+array('codeyPixels','uint8_t',list(blob))
(ROOT/'firmware/include/codey_assets.h').write_text(out)
(ROOT/'artifacts/codey-palette.json').write_text(json.dumps(colors))
preview=base.crop((0,0,192,208)); preview.save(ROOT/'artifacts/codey-first-frame.png')
print(f'Encoded {len(offsets)-1} frames, {len(blob)} RLE bytes, {len(colors)} palette colors')

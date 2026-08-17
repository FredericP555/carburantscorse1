#!/usr/bin/env python3
from pathlib import Path

p=Path('index.html')
s=p.read_text(encoding='utf-8')
needle='<script src="app.js"></script>'
insert='<script src="app.js"></script>\n<script src="automation.js"></script>'
if insert in s:
    print('automation.js already loaded')
elif needle in s:
    p.write_text(s.replace(needle,insert,1),encoding='utf-8')
    print('index.html patched to load automation.js')
else:
    raise SystemExit('Could not find app.js script tag in index.html')

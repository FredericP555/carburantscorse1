import json
from pathlib import Path
p=json.loads(Path('data.json').read_text(encoding='utf-8'))
print(json.dumps((p.get('meta') or {}).get('bouclier') or {}, ensure_ascii=False, indent=2, sort_keys=True))

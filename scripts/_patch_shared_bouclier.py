from pathlib import Path

# Attach the authoritative c1 bouclier detector metadata to the shared manifest.
# The raw CSV remains unchanged.
p=Path('scripts/export_shared_c2_snapshot.py')
s=p.read_text(encoding='utf-8')
s=s.replace('import update_data_v2 as core\n','import update_data_v2 as core\nimport bouclier_detector\n',1)
needle='''        "producer": "FredericP555/carburantscorse1",\n        "method": "raw official declarations only; no c1 forward-fill or aggregation",\n'''
repl='''        "producer": "FredericP555/carburantscorse1",\n        "method": "raw official declarations only; no c1 forward-fill or aggregation",\n        "bouclier": bouclier_detector.metadata(max(years)),\n'''
if needle not in s:
    raise SystemExit('exporter metadata anchor not found')
s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8')

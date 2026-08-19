from pathlib import Path

# Patch shared exporter: attach the already-authoritative c1 bouclier detector metadata
# to the manifest while leaving the raw CSV untouched.
p=Path('scripts/export_shared_c2_snapshot.py')
s=p.read_text(encoding='utf-8')
s=s.replace('import update_data_v2 as core\n','import update_data_v2 as core\nimport bouclier_detector\n',1)
needle='''        "producer": "FredericP555/carburantscorse1",\n        "method": "raw official declarations only; no c1 forward-fill or aggregation",\n'''
repl='''        "producer": "FredericP555/carburantscorse1",\n        "method": "raw official declarations only; no c1 forward-fill or aggregation",\n        "bouclier": bouclier_detector.metadata(max(years)),\n'''
if needle not in s:
    raise SystemExit('exporter metadata anchor not found')
s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8')

# Strengthen the real-snapshot validation: the release manifest must carry both fuels.
p=Path('.github/workflows/validate-data.yml')
s=p.read_text(encoding='utf-8')
needle="""          assert meta['sha256']==hashlib.sha256(data.read_bytes()).hexdigest()\n"""
repl="""          assert meta['sha256']==hashlib.sha256(data.read_bytes()).hexdigest()\n          assert set(meta['bouclier'])=={'Gazole','SP95'}\n          assert 'ranges' in meta['bouclier']['Gazole'] and 'ranges' in meta['bouclier']['SP95']\n"""
if needle not in s:
    raise SystemExit('validation anchor not found')
s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8')

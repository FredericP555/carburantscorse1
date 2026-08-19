from pathlib import Path
p=Path('app.js')
s=p.read_text(encoding='utf-8')
anchor='const ZONES = [\n'
helper="""function getBouclierRanges(fuel) {\n  const b = DATA && DATA.meta && DATA.meta.bouclier && DATA.meta.bouclier[fuel];\n  return b && Array.isArray(b.ranges) ? b.ranges : [];\n}\n\n"""
if helper not in s:
    if anchor not in s:
        raise SystemExit('ZONES anchor not found')
    s=s.replace(anchor,helper+anchor,1)
old="(BOUCLIER[carbu]||[]).forEach(z=>{"
new="getBouclierRanges(carbu).forEach(z=>{"
if old not in s:
    raise SystemExit('shield rendering anchor not found')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')

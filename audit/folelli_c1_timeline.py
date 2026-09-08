#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

import update_data_v2 as core
import build_c1_v2_candidate as v2
import reliability_policy_v2
import bouclier_detector
import shield_phase_v2
import r2_guard_v2
from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap

IDS = ('20213003','20213007','20213008')
FUELS = ('Gazole','SP95')
SWITCH = date(2026,7,23)
END = date(2026,9,7)


def last_updates():
    merged = defaultdict(list)
    for year in (2025, 2026):
        parsed = core.parse_year(year)
        for key, vals in parsed.items():
            if key[0] in IDS and key[1] == 'corse' and key[2] in FUELS:
                merged[key].extend(vals)
    out = {}
    for sid in IDS:
        out[sid] = {}
        for fuel in FUELS:
            vals = sorted(merged.get((sid,'corse',fuel), []), key=lambda x:x[0])
            out[sid][fuel] = [{'ts':ts.isoformat(), 'value':value} for ts,value in vals]
    return merged, out


def legacy_windows(merged):
    result={}
    for sid in IDS:
        result[sid]={}
        for fuel in FUELS:
            vals=sorted(merged.get((sid,'corse',fuel), []), key=lambda x:x[0])
            prior=[x for x in vals if x[0].date() < SWITCH]
            if not prior:
                result[sid][fuel]=None; continue
            ts,val=prior[-1]
            if val is None:
                result[sid][fuel]={'last_ts':ts.isoformat(),'last_value':None,'legacy_last_eligible':None}
            else:
                result[sid][fuel]={'last_ts':ts.isoformat(),'last_value':val,'legacy_last_eligible':(ts.date()+timedelta(days=core.MAX_FFILL_DAYS)).isoformat()}
    return result


def v2_timeline(merged):
    # Rebuild declarations/events exactly as the V2 candidate does.
    declarations={}; events=[]; source_dates=[]
    for year in (2025, 2026):
        v2.parse_year(year, declarations, events, source_dates)
    declarations={k:v2._dedupe_updates(vals) for k,vals in declarations.items()}
    guard=v2.EventGuard(events,declarations)
    brands=json.loads((ROOT/'config/corse_station_brands.json').read_text(encoding='utf-8')).get('stations') or {}
    bouclier=shield_phase_v2.with_cap_phases(bouclier_detector.metadata(2026))
    rows={sid:{fuel:[] for fuel in FUELS} for sid in IDS}
    pointers={}
    phase_cache={}
    def phase(fuel,day):
        key=(fuel,day)
        if key not in phase_cache:
            phase_cache[key]=shield_phase_v2.phase_for_day(bouclier,fuel,day)
        return phase_cache[key]
    for sid in IDS:
        is_total=classify_registry_entry(brands.get(sid)) == TOTAL
        day=SWITCH
        while day<=END:
            state={}
            relevant=set(FUELS)
            for fuel in relevant:
                updates=declarations.get((sid,'corse',fuel),[])
                state[fuel]=v2._value_at(updates,pointers,(sid,'corse',fuel),day) if updates else (None,None)
            activity={fuel:ts for fuel,(ts,_v) in state.items() if ts is not None}
            gts,gprice=state.get('Gazole',(None,None)); sts,sprice=state.get('SP95',(None,None))
            gp=phase('Gazole',day); sp=phase('SP95',day)
            gcap=gp.cap if gp else None; scap=sp.cap if sp else None
            for fuel in FUELS:
                last_ts,last_price=state.get(fuel,(None,None)); tp=phase(fuel,day)
                r2=None
                age=reliability_policy_v2.age_days(last_ts,day)
                if age is not None and age >= reliability_policy_v2.NORMAL_MAX_AGE_DAYS and at_cap(gprice,gcap) and at_cap(sprice,scap):
                    try: r2=r2_guard_v2.stale_price_admissible(last_ts,day,bouclier_metadata=bouclier)
                    except Exception: r2=None
                d=reliability_policy_v2.evaluate(day=day,region_kind='corsica',target_fuel=fuel,last_declared_at=last_ts,last_price=last_price,latest_price_valid=last_price is not None,target_rupture_active=guard.rupture_active(sid,fuel,day),independently_inactive=guard.closed(sid,day),is_total=is_total,shield_effective=tp is not None,applicable_cap=tp.cap if tp else None,phase_started_on=tp.started_on if tp else None,activity_by_fuel=activity,gazole_price=gprice,gazole_cap=gcap,sp95_price=sprice,sp95_cap=scap,rotterdam_stale_price_admissible=r2)
                rows[sid][fuel].append({'date':day.isoformat(),'eligible':d.eligible,'reason':d.reason,'age_days':d.age_days,'last_ts':last_ts.isoformat() if last_ts else None,'price':last_price,'is_total':is_total,'shield_effective':tp is not None})
            day += timedelta(days=1)
    # Compress consecutive identical decision states.
    compressed={}
    for sid in IDS:
        compressed[sid]={}
        for fuel in FUELS:
            seq=rows[sid][fuel]; groups=[]
            for item in seq:
                sig=(item['eligible'],item['reason'],item['last_ts'],item['price'],item['is_total'],item['shield_effective'])
                if groups and groups[-1]['sig']==sig:
                    groups[-1]['end']=item['date']; groups[-1]['end_age_days']=item['age_days']
                else:
                    groups.append({'sig':sig,'start':item['date'],'end':item['date'],'start_age_days':item['age_days'],'end_age_days':item['age_days']})
            compressed[sid][fuel]=[{'start':g['start'],'end':g['end'],'eligible':g['sig'][0],'reason':g['sig'][1],'last_ts':g['sig'][2],'price':g['sig'][3],'is_total':g['sig'][4],'shield_effective':g['sig'][5],'age_days':[g['start_age_days'],g['end_age_days']]} for g in groups]
    return compressed


def main():
    merged, updates=last_updates()
    payload={'updates':updates,'legacy':legacy_windows(merged),'v2':v2_timeline(merged)}
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__': main()

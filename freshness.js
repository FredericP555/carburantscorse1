(function(){
  'use strict';

  const DAY_MS=86400000;

  function parseIso(s){
    if(!s||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(s)) return null;
    const [y,m,d]=s.split('-').map(Number);
    return new Date(Date.UTC(y,m-1,d));
  }
  function isoFromDate(d){
    return d?d.toISOString().slice(0,10):null;
  }
  function addDays(iso,n){
    const d=parseIso(iso); if(!d)return null;
    d.setUTCDate(d.getUTCDate()+n);
    return isoFromDate(d);
  }
  function frDate(iso){
    const d=parseIso(iso); if(!d)return '—';
    return new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(d);
  }
  function parisTodayIso(){
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const o={}; parts.forEach(p=>{if(p.type!=='literal')o[p.type]=p.value;});
    return `${o.year}-${o.month}-${o.day}`;
  }
  function ageDays(iso){
    const d=parseIso(iso),t=parseIso(parisTodayIso());
    return d&&t?Math.max(0,Math.floor((t-d)/DAY_MS)):null;
  }
  function lastValidC1(res){
    if(typeof DATA==='undefined'||!DATA||!DATA.G)return null;
    const ck=(typeof carbu!=='undefined'&&carbu==='SP95')?'S':'G';
    const rows=DATA[ck]&&DATA[ck].corse&&DATA[ck].corse[res];
    if(!Array.isArray(rows)||!rows.length)return null;
    for(let i=rows.length-1;i>=0;i--){
      if(rows[i]&&rows[i][1]!=null){
        if(typeof offsetToDate==='function')return offsetToDate(rows[i][0]);
        return addDays('2022-01-01',Number(rows[i][0]));
      }
    }
    return null;
  }
  function c2Rows(gran){
    if(typeof DATA==='undefined'||!DATA||!DATA.gazole)return [];
    if(typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&typeof currentVue!=='undefined'&&currentVue==='marge'){
      return (typeof MARGES_GZ!=='undefined'&&MARGES_GZ&&Array.isArray(MARGES_GZ.all))?MARGES_GZ.all:[];
    }
    const car=(typeof currentCarbu!=='undefined')?currentCarbu:'gazole';
    const ref=car==='sp95'&&typeof currentRef!=='undefined'?currentRef:'sp95';
    const node=DATA[car]&&DATA[car][ref]&&DATA[car][ref][gran];
    return node&&Array.isArray(node.all)?node.all:[];
  }
  function lastC2(gran){
    const rows=c2Rows(gran);
    for(let i=rows.length-1;i>=0;i--){if(rows[i]&&rows[i].date)return rows[i].date;}
    return null;
  }
  function sourceMaxDate(){
    if(typeof DATA!=='undefined'&&DATA&&DATA.gazole){
      const meta=(typeof window!=='undefined'&&window.A4C_DATA_META)||{};
      if(typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&typeof currentVue!=='undefined'&&currentVue==='marge'){
        return meta.ufip_last_observed_date||lastC2('weekly');
      }
      return meta.official_source_max_date||meta.daily_target_end||lastC2('daily');
    }
    return lastValidC1('d');
  }
  function weeklyStartDate(){
    if(typeof DATA!=='undefined'&&DATA&&DATA.gazole)return lastC2('weekly');
    return lastValidC1('w');
  }
  function isWeeklyView(){
    if(typeof DATA!=='undefined'&&DATA&&DATA.gazole){
      if(typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&typeof currentVue!=='undefined'&&currentVue==='marge')return true;
      return typeof currentGran!=='undefined'&&currentGran==='weekly';
    }
    return typeof resolution!=='undefined'&&resolution==='w';
  }

  function c1DisplayedSpanMonths(labels){
    if(!Array.isArray(labels)||labels.length<2)return 60;
    const toDate=s=>{
      if(!s)return null;
      const v=String(s);
      return new Date((v.length===7?v+'-01':v)+'T12:00:00');
    };
    const first=toDate(labels[0]),last=toDate(labels[labels.length-1]);
    if(!first||!last||Number.isNaN(first.getTime())||Number.isNaN(last.getTime()))return 60;
    return Math.max(1,(last.getFullYear()-first.getFullYear())*12+(last.getMonth()-first.getMonth())+1);
  }
  function c1AdaptiveTickLabel(val){
    const lbl=this.getLabelForValue(val);
    if(!lbl)return '';
    const labels=this.chart&&this.chart.data?this.chart.data.labels:[];
    const spanMonths=c1DisplayedSpanMonths(labels);
    const step=spanMonths<=15?2:spanMonths<=30?3:12;
    const parts=String(lbl).split('-');
    const month=Number(parts[1]||1),day=Number(parts[2]||1);
    const monthOk=step===12?month===1:((month-1)%step===0);
    if(typeof resolution!=='undefined'&&resolution==='d'&&(!monthOk||day!==1))return '';
    if(typeof resolution!=='undefined'&&resolution==='w'&&(!monthOk||day>7))return '';
    if(typeof resolution!=='undefined'&&resolution==='m'&&!monthOk)return '';
    return typeof formatLabel==='function'?formatLabel(lbl):String(lbl);
  }
  function installC1AdaptiveAxis(){
    if(typeof chartPrix==='undefined'||typeof chartEcart==='undefined'||!chartPrix||!chartEcart)return false;
    [chartPrix,chartEcart].forEach(chart=>{
      if(chart.options&&chart.options.scales&&chart.options.scales.x&&chart.options.scales.x.ticks){
        chart.options.scales.x.ticks.callback=c1AdaptiveTickLabel;
      }
    });
    chartPrix.update('none');
    chartEcart.update('none');
    return true;
  }

  // Classement C1 : dernière semaine complète, avec tendance vs semaine précédente.
  function c1RankingContext(){
    if(typeof DATA==='undefined'||!DATA||typeof getSeries!=='function'||typeof offsetToDate!=='function')return null;
    const ck=(typeof carbu!=='undefined'&&carbu==='SP95')?'S':'G';
    const weekly=getSeries(ck,'corse','w').filter(p=>p&&p[1]!=null);
    if(!weekly.length)return null;
    const daily=getSeries(ck,'corse','d').filter(p=>p&&p[1]!=null);
    const maxDate=(DATA.meta&&DATA.meta.last_date)||(daily.length?offsetToDate(daily[daily.length-1][0]):null);
    if(!maxDate)return null;
    let chosen=null;
    for(const row of weekly){
      const start=offsetToDate(row[0]);
      const end=addDays(start,6);
      if(end&&end<=maxDate)chosen=row;
    }
    if(!chosen)return null;
    const offset=Number(chosen[0]);
    return {ck,offset,prevOffset:offset-7,start:offsetToDate(offset),end:addDays(offsetToDate(offset),6)};
  }
  function c1WeeklyTtc(key,offset,ck){
    const rows=getSeries(ck,key,'w');
    const row=rows.find(p=>p&&Number(p[0])===Number(offset)&&p[1]!=null);
    return row?Number(row[1]):null;
  }
  function c1RankingWeekText(ctx){
    if(!ctx)return '';
    const start=parseIso(ctx.start),end=parseIso(ctx.end);
    if(!start||!end)return '';
    const months=['JANVIER','FÉVRIER','MARS','AVRIL','MAI','JUIN','JUILLET','AOÛT','SEPTEMBRE','OCTOBRE','NOVEMBRE','DÉCEMBRE'];
    if(start.getUTCFullYear()===end.getUTCFullYear()&&start.getUTCMonth()===end.getUTCMonth()){
      return `${start.getUTCDate()}–${end.getUTCDate()} ${months[end.getUTCMonth()]} ${end.getUTCFullYear()}`;
    }
    return `${start.getUTCDate()} ${months[start.getUTCMonth()]}–${end.getUTCDate()} ${months[end.getUTCMonth()]} ${end.getUTCFullYear()}`;
  }
  function c1UpdateRankingLabel(){
    const ctx=c1RankingContext();
    const rank=document.getElementById('rankLabel');
    if(!ctx||!rank)return;
    rank.textContent=`CLASSEMENT · SEMAINE ${c1RankingWeekText(ctx)} · ${String(carbu).toUpperCase()} TTC`;
  }
  function c1TrendMarkup(current,previous){
    if(previous==null||!Number.isFinite(previous)){
      return '<div class="rank-trend" title="Semaine précédente indisponible" style="width:30px;flex-shrink:0;text-align:center;color:#94a3b8;font-size:0.78rem;font-weight:800">→</div>';
    }
    const delta=current-previous;
    let arrow='→',color='#94a3b8',label='stable';
    if(delta>0.0005){arrow='↗';color='#dc2626';label='hausse';}
    else if(delta< -0.0005){arrow='↘';color='#16a34a';label='baisse';}
    const cents=delta*100;
    const signed=(cents>0?'+':'')+cents.toFixed(1).replace('.',',');
    return `<div class="rank-trend" title="${label} : ${signed} c/L vs semaine précédente" style="width:30px;flex-shrink:0;text-align:center;color:${color};font-size:0.86rem;font-weight:800;line-height:1">${arrow}</div>`;
  }
  function installC1WeeklyRanking(){
    if(typeof buildRanking!=='function'||typeof ALL_KEYS==='undefined')return false;
    if(window.__A4C_C1_WEEKLY_RANKING_INSTALLED__)return true;
    buildRanking=function(){
      const el=document.getElementById('rankRows');
      if(!el)return;
      el.innerHTML='';
      const ctx=c1RankingContext();
      if(!ctx)return;
      const ranked=ALL_KEYS.filter(k=>k!=='moy_regions').map(k=>({
        k,
        v:c1WeeklyTtc(k,ctx.offset,ctx.ck),
        prev:c1WeeklyTtc(k,ctx.prevOffset,ctx.ck),
      })).filter(d=>d.v!=null).sort((a,b)=>b.v-a.v);
      ranked.forEach((item,i)=>{
        const row=document.createElement('div');
        row.className='rank-row';
        const name=item.k==='corse'?'Corse':((typeof LABELS!=='undefined'&&LABELS[item.k])||item.k);
        row.innerHTML=`<div class="rank-num">${i+1}</div>
          <div class="rank-dot" style="background:${(typeof COLORS!=='undefined'&&COLORS[item.k])||'#888'}"></div>
          <div class="rank-name" style="color:${(typeof COLORS!=='undefined'&&COLORS[item.k])||'#888'}">${name}</div>
          ${c1TrendMarkup(item.v,item.prev)}
          <div class="rank-val">${item.v.toFixed(2)} €</div>`;
        el.appendChild(row);
      });
      c1UpdateRankingLabel();
    };
    if(typeof applyDynamicLabels==='function'){
      const baseApplyDynamicLabels=applyDynamicLabels;
      applyDynamicLabels=function(){
        baseApplyDynamicLabels();
        c1UpdateRankingLabel();
      };
    }
    window.__A4C_C1_WEEKLY_RANKING_INSTALLED__=true;
    return true;
  }

  function ensureBadge(){
    let badge=document.getElementById('a4c-freshness-badge');
    if(badge)return badge;
    const header=document.querySelector('header')||document.getElementById('header');
    if(!header)return null;
    const style=document.createElement('style');
    style.id='a4c-freshness-style';
    style.textContent=`
      header,#header{position:relative}
      #a4c-freshness-badge{position:absolute;right:18px;top:9px;z-index:5;display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border-radius:999px;border:1px solid #cbd5e1;background:#fff;font:600 11px/1.2 system-ui,sans-serif;white-space:nowrap;box-shadow:0 1px 2px rgba(15,23,42,.05)}
      #a4c-freshness-badge::before{content:'';width:8px;height:8px;border-radius:50%;background:#16a34a;flex:0 0 auto}
      #a4c-freshness-badge.fresh{color:#166534;border-color:#bbf7d0;background:#f0fdf4}
      #a4c-freshness-badge.warn{color:#9a3412;border-color:#fed7aa;background:#fff7ed}
      #a4c-freshness-badge.warn::before{background:#f59e0b}
      #a4c-freshness-badge.stale{color:#991b1b;border-color:#fecaca;background:#fef2f2}
      #a4c-freshness-badge.stale::before{background:#dc2626}
      @media(min-width:701px){header h1,#header h1{padding-right:330px}}
      @media(max-width:700px){#a4c-freshness-badge{position:static;margin:5px 0 1px;max-width:100%;white-space:normal;font-size:10px}header h1,#header h1{padding-right:0}}
    `;
    document.head.appendChild(style);
    badge=document.createElement('div');
    badge.id='a4c-freshness-badge';
    badge.className='fresh';
    badge.setAttribute('role','status');
    badge.setAttribute('aria-live','polite');
    badge.title='Fraîcheur des données : vert ≤ 3 jours, orange 4–7 jours, rouge > 7 jours.';
    const h1=header.querySelector('h1');
    if(h1)h1.insertAdjacentElement('afterend',badge); else header.appendChild(badge);
    return badge;
  }
  function updateFreshnessBadge(){
    const badge=ensureBadge(); if(!badge)return;
    const sourceMax=sourceMaxDate();
    if(!sourceMax){badge.textContent='Fraîcheur indisponible';badge.className='warn';return;}
    let freshnessDate=sourceMax;
    if(isWeeklyView()){
      const start=weeklyStartDate();
      if(start){
        const end=addDays(start,6);
        if(end&&sourceMax>=end){
          badge.textContent=`Hebdo · semaine complète au ${frDate(end)}`;
          freshnessDate=end;
        }else{
          badge.textContent=`Hebdo · semaine du ${frDate(start)} · partielle au ${frDate(sourceMax)}`;
          freshnessDate=sourceMax;
        }
      }else{
        badge.textContent=`Hebdo · données au ${frDate(sourceMax)}`;
      }
    }else{
      badge.textContent=`Données au ${frDate(sourceMax)}`;
    }
    const age=ageDays(freshnessDate);
    badge.className=age==null?'warn':age<=3?'fresh':age<=7?'warn':'stale';
  }

  installC1WeeklyRanking();
  window.A4C_updateFreshnessBadge=updateFreshnessBadge;
  document.addEventListener('click',function(e){
    const t=e.target&&e.target.closest&&e.target.closest('[data-res],[data-carbu],#btn-daily,#btn-weekly,#btn-prix,#btn-marge,#btn-gz,#btn-sp,#btn-sp95ref,#btn-e10ref');
    if(t)setTimeout(function(){updateFreshnessBadge();installC1AdaptiveAxis();installC1WeeklyRanking();},0);
  });
  window.addEventListener('load',function(){
    let tries=0;
    const timer=setInterval(function(){
      tries++;
      updateFreshnessBadge();
      const axisReady=installC1AdaptiveAxis();
      const rankingReady=installC1WeeklyRanking();
      if(typeof buildRanking==='function'&&typeof DATA!=='undefined'&&DATA){buildRanking();c1UpdateRankingLabel();}
      if((sourceMaxDate()&&axisReady&&rankingReady)||tries>30)clearInterval(timer);
    },100);
  });
})();
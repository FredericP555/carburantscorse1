let DATA = null;

async function loadData() {
  const resp = await fetch('data.json');
  DATA = await resp.json();
}


const REGIONS = ["Auvergne-Rhône-Alpes","Bourgogne-Franche-Comté","Bretagne",
  "Centre-Val de Loire","Grand Est","Hauts-de-France","Île-de-France",
  "Normandie","Nouvelle-Aquitaine","Occitanie","PACA","Pays de la Loire"];
const ALL_KEYS = ['corse','moy_regions',...REGIONS];
const LABELS = {corse:'Moy. Corse', moy_regions:'Moy. toutes régions'};
REGIONS.forEach(r=>LABELS[r]=r);
const REG_COLORS = ["#e07b39", "#c9a227", "#4a9e6b", "#3a9ebf", "#7b5ea7", "#c94a7b", "#2a9e9e", "#c94a4a", "#7ba63a", "#2a6fbf", "#bf4abf", "#e07b39"];
const COLORS = {corse:'#1a1a1a', moy_regions:'#e07b39'};
REGIONS.forEach((r,i)=>COLORS[r]=REG_COLORS[i%REG_COLORS.length]);

const BOUCLIER = {"Gazole": [{"d1": "2023-08-31", "d2": "2023-10-13"}, {"d1": "2023-10-24", "d2": "2023-10-30"}, {"d1": "2026-03-20", "d2": "2026-04-06"}, {"d1": "2026-04-08", "d2": "2026-05-27"}], "Gazole_promo": [{"d1": "2026-04-30", "d2": "2026-05-03"}, {"d1": "2026-05-08", "d2": "2026-05-10"}, {"d1": "2026-05-14", "d2": "2026-05-17"}, {"d1": "2026-05-23", "d2": "2026-05-25"}], "SP95": [{"d1": "2023-02-20", "d2": "2023-03-19"}, {"d1": "2023-03-27", "d2": "2023-05-02"}, {"d1": "2023-06-09", "d2": "2023-06-21"}, {"d1": "2023-07-25", "d2": "2023-10-07"}, {"d1": "2024-02-20", "d2": "2024-03-01"}, {"d1": "2024-03-07", "d2": "2024-06-05"}, {"d1": "2024-07-01", "d2": "2024-07-16"}, {"d1": "2026-03-13", "d2": "2026-05-28"}]};
const ZONES = [
  {d1:'2022-09-01',d2:'2022-11-15',label:'Remise -20c',alpha_fill:0.18},
  {d1:'2022-11-16',d2:'2022-12-31',label:'Remise -10c',alpha_fill:0.12},
];
const EVENTS = [
  {date:'2022-02-24',label:'Invasion Ukraine',color:'rgba(220,38,38,0.8)'},
  {date:'2025-11-17',label:'Sanctions Autorité concurrence',color:'rgba(234,88,12,0.8)'},
  {date:'2026-02-28',label:"Guerre d'Iran",color:'rgba(220,38,38,0.8)'},
];
const ANALYSE = {
  Gazole:{
    // Tendance structurelle (hors interventions)
    tendance:{
      y2022:'15,3', y2023:'17,3', y2024:'18,1', y2025:'18,3',
      delta:'+3,0', note:"De +15,3 c\u20ac/L en 2022 \u00e0 +18,3 c\u20ac/L en 2025"
    },
    // Effet des actions Total
    effet:{
      avec2022:'12,2', sans2022:'15,3', gain2022:'3,1',
      avec2026:'12,8', sans2026:'15,3', gain2026:'2,5',
      creux:'\u22121,1', creux_ctx:"lors de la remise de 20 c/L \u00e0 l'automne 2022"
    },
    // Bilan hors toute action
    bilan:{
      hors:'17,2', pendant:'13,1',
      y2022:'15,3', y2023:'17,3', y2024:'18,1', y2025:'18,3'
    }
  },
  SP95:{
    tendance:{
      y2022:'14,2', y2023:'14,3', y2024:'17,2', y2025:'17,3',
      delta:'+3,1', note:"De +14,2 c\u20ac/L en 2022 \u00e0 +17,3 c\u20ac/L en 2025"
    },
    effet:{
      avec2022:'10,6', sans2022:'14,2', gain2022:'3,6',
      avec2026:'12,4', sans2026:'16,4', gain2026:'4,1',
      creux:'\u22126,8', creux_ctx:"lors du pic de la crise de 2023"
    },
    bilan:{
      hors:'16,0', pendant:'10,2',
      y2022:'14,2', y2023:'14,3', y2024:'17,2', y2025:'17,3'
    }
  }
};

let carbu = 'Gazole';
let selReg = 'moy_regions';
const hidden = new Set(REGIONS);
const legItems = new Map();

// Convertit le format optimisé [offset, ttc, ht] en {serie: [[date, val], ...]}
const ORIGIN = new Date('2022-01-01');
function offsetToDate(n) {
  const d = new Date(ORIGIN); d.setDate(d.getDate()+n);
  return d.toISOString().slice(0,10);
}
function _buildSeries(carbuKey, valIdx) {
  const src = DATA[carbuKey] || {};
  const result = {};
  for(const [name, points] of Object.entries(src)) {
    result[name] = points.filter(p=>p[valIdx]!=null).map(p=>[offsetToDate(p[0]),p[valIdx]]);
  }
  return result;
}
let _cacheKey=null, _cacheTTC=null, _cacheHT=null;
function _ensureCache() {
  const key = carbu==='Gazole'?'G':'S';
  if(_cacheKey!==key) {
    _cacheTTC=_buildSeries(key,1); _cacheHT=_buildSeries(key,2); _cacheKey=key;
  }
}
function cats()   { _ensureCache(); return _cacheTTC; }
function catsHT() { _ensureCache(); return _cacheHT; }
function dict(arr){ return Object.fromEntries(arr||[]); }

function allDates(){
  const s=new Set();
  Object.values(cats()||{}).forEach(v=>v.forEach(([d])=>s.add(d)));
  return Array.from(s).sort();
}

function getMoyRegions(dates){
  const c=cats()||{};
  return dates.map(d=>{
    const vals=REGIONS.map(r=>dict(c[r])[d]).filter(v=>v!=null);
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  });
}
function getMoyRegionsHT(dates){
  const c=catsHT()||{};
  return dates.map(d=>{
    const vals=REGIONS.map(r=>dict(c[r])[d]).filter(v=>v!=null);
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  });
}

function buildPrixDs(dates){
  const c=cats()||{};
  const moy=getMoyRegions(dates);
  return ALL_KEYS.map(key=>{
    const data=key==='moy_regions'?moy:dates.map(d=>dict(c[key])[d]??null);
    return {label:LABELS[key]||key,_key:key,data,
      borderColor:COLORS[key]||'#888',
      backgroundColor:(COLORS[key]||'#888')+'18',
      borderWidth:key==='corse'?2.5:1.8,
      borderDash:key==='corse'?[6,3]:[],
      pointRadius:0,tension:0.3,spanGaps:true};
  });
}

function buildEcartDs(dates){
  const c=catsHT()||{};
  const corseMap=dict(c['corse']||[]);
  const moy=getMoyRegionsHT(dates);
  return ['moy_regions',...REGIONS].map(key=>{
    const data=dates.map((d,i)=>{
      const vc=corseMap[d];
      const vr=key==='moy_regions'?moy[i]:dict(c[key])[d];
      return (vc!=null&&vr!=null)?Math.round((vc-vr)*10000)/100:null;
    });
    return {label:LABELS[key]||key,_key:key,data,
      borderColor:COLORS[key]||'#888',
      backgroundColor:(COLORS[key]||'#888')+'18',
      borderWidth:key==='moy_regions'?2:1.2,
      pointRadius:0,tension:0.3,spanGaps:true};
  });
}

function getDateX(chart,dateStr){
  const labels=chart.data.labels;
  let i=labels.indexOf(dateStr);
  if(i<0) i=labels.findIndex(d=>d>=dateStr);
  return i<0?null:chart.scales.x.getPixelForValue(i);
}

const zonesPlugin={
  id:'zonesPlugin',
  afterDraw(chart){
    const {ctx,chartArea:{left,right,top,bottom},scales:{x,y}}=chart;
    if(!x||!y) return;
    ctx.save(); ctx.beginPath(); ctx.rect(left,top,right-left,bottom-top); ctx.clip();
    // Remises vertes
    ZONES.forEach(z=>{
      const x1=getDateX(chart,z.d1),x2=getDateX(chart,z.d2);
      if(x1==null||x2==null) return;
      ctx.fillStyle=`rgba(34,197,94,${z.alpha_fill})`;
      ctx.fillRect(x1,top,x2-x1,bottom-top);
    });
    // Bouclier jaune
    (BOUCLIER[carbu]||[]).forEach(z=>{
      const x1=getDateX(chart,z.d1),x2=getDateX(chart,z.d2);
      if(x1==null||x2==null) return;
      ctx.fillStyle='rgba(251,191,36,0.12)';
      ctx.fillRect(x1,top,x2-x1,bottom-top);
    });
    // Promos orange (Gazole)
    if(carbu==='Gazole') (BOUCLIER['Gazole_promo']||[]).forEach(z=>{
      const x1=getDateX(chart,z.d1),x2=getDateX(chart,z.d2);
      if(x1==null||x2==null) return;
      ctx.fillStyle='rgba(234,88,12,0.09)';
      ctx.fillRect(x1,top,x2-x1,bottom-top);
    });
    // Lignes événements
    EVENTS.forEach(ev=>{
      const px=getDateX(chart,ev.date);
      if(px==null) return;
      ctx.save();
      ctx.beginPath(); ctx.rect(left,top,right-left,bottom-top); ctx.clip();
      ctx.beginPath(); ctx.strokeStyle=ev.color; ctx.lineWidth=1.5;
      ctx.setLineDash([5,4]); ctx.moveTo(px,top); ctx.lineTo(px,bottom); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle=ev.color; ctx.font='bold 9px DM Mono,monospace';
      ctx.textAlign='left'; ctx.textBaseline='top';
      ctx.translate(px+3,top+6); ctx.rotate(Math.PI/2);
      ctx.fillText(ev.label,0,0);
      ctx.restore();
    });
    ctx.restore();
  }
};

Chart.register(zonesPlugin);

const TICK_CB = function(val,idx){
  const d=this.getLabelForValue(val); if(!d) return '';
  const p=d.split('-');
  const m=['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc'];
  return m[parseInt(p[1])-1]+' '+p[0].slice(2);
};
const GRID_OPTS = {color:'#e5e1d8'};
const BORDER_OPTS = {color:'#dedad2'};
const TOOLTIP_BASE = {
  backgroundColor:'#ffffff',borderColor:'#ddd9d0',borderWidth:1,
  titleColor:'#777',bodyColor:'#1a1a1a',
  titleFont:{family:'DM Mono',size:10},bodyFont:{family:'DM Mono',size:11}
};

let chartPrix, chartEcart;

function initCharts(){
  const dates=allDates();
  const pds=buildPrixDs(dates);
  const eds=buildEcartDs(dates);

  chartPrix=new Chart(document.getElementById('chartPrix').getContext('2d'),{
    type:'line',data:{labels:dates,datasets:pds},
    options:{
      responsive:true,interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{...TOOLTIP_BASE,
          filter:item=>!hidden.has(item.dataset._key)&&item.dataset._key!=='corse'?true:(item.dataset._key==='corse'||item.dataset._key===selReg),
          callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(2)} € TTC`}
        }
      },
      scales:{
        x:{ticks:{color:'#999',font:{family:'DM Mono',size:10},maxTicksLimit:18,maxRotation:0,autoSkip:true,callback:TICK_CB},grid:GRID_OPTS,border:BORDER_OPTS},
        y:{min:1.1,afterFit(s){s.width=62;},
          ticks:{color:'#999',font:{family:'DM Mono',size:11},padding:4,callback:v=>v.toFixed(2)+' €'},
          grid:{color:ctx=>ctx.tick?.value===0?'#aaa49a':'#e5e1d8'},border:BORDER_OPTS}
      }
    }
  });

  chartEcart=new Chart(document.getElementById('chartEcart').getContext('2d'),{
    type:'line',data:{labels:dates,datasets:eds},
    options:{
      responsive:true,interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{...TOOLTIP_BASE,
          filter:item=>item.dataset._key===selReg||item.dataset._key==='moy_regions'?true:false,
          callbacks:{label:ctx=>{
            const v=ctx.parsed.y; if(v==null) return null;
            return `${ctx.dataset.label}: ${v>=0?'+':''}${v.toFixed(2)} c€/L`;
          }}
        }
      },
      scales:{
        x:{ticks:{color:'#999',font:{family:'DM Mono',size:10},maxTicksLimit:18,maxRotation:0,autoSkip:true,callback:TICK_CB},grid:GRID_OPTS,border:BORDER_OPTS},
        y:{beginAtZero:false,
          ticks:{color:'#999',font:{family:'DM Mono',size:11},callback:v=>(v>=0?'+':'')+v.toFixed(1)+' c€'},
          grid:{color:ctx=>ctx.tick?.value===0?'#aaa49a':'#e5e1d8',lineWidth:ctx=>ctx.tick?.value===0?1.5:1},
          border:BORDER_OPTS}
      }
    }
  });

  // Visibilité initiale
  ALL_KEYS.forEach((k,i)=>{
    const meta=chartPrix.getDatasetMeta(i);
    if(meta) meta.hidden=(k!=='corse'&&k!==selReg);
  });
  ['moy_regions',...REGIONS].forEach((k,i)=>{
    const meta=chartEcart.getDatasetMeta(i);
    if(meta) meta.hidden=(k!==selReg);
  });
  chartPrix.update(); chartEcart.update();
}

function setVisible(key,visible){
  const i1=chartPrix.data.datasets.findIndex(d=>d._key===key);
  if(i1>=0) chartPrix.getDatasetMeta(i1).hidden=!visible;
  const i2=chartEcart.data.datasets.findIndex(d=>d._key===key);
  if(i2>=0) chartEcart.getDatasetMeta(i2).hidden=!visible;
}

function lastVal(key){
  if(key==='moy_regions'){
    const vals=REGIONS.map(r=>lastVal(r)).filter(v=>v!=null);
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  }
  const m=dict((cats()||{})[key]);
  return Object.values(m).filter(v=>v!=null).at(-1)??null;
}

function buildLegend(){
  const el=document.getElementById('legendItems');
  el.innerHTML=''; legItems.clear();
  ALL_KEYS.filter(k=>k!=='corse').forEach(key=>{
    const v=lastVal(key);
    const isActive=(key===selReg);
    const color=COLORS[key]||'#888';
    const item=document.createElement('div');
    item.className='leg-item'+(isActive?' active':'');
    item.style.color=color;
    item.dataset.key=key;
    item.innerHTML=`<div class="leg-check"><svg width="8" height="8" viewBox="0 0 8 8"><polyline points="1,4 3,6 7,2" stroke="#fff" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg></div>
      <div class="leg-color" style="background:${color};width:10px;height:10px;border-radius:50%;flex-shrink:0"></div>
      <div class="leg-name">${LABELS[key]||key}</div>
      <div class="leg-val">${v!=null?v.toFixed(2)+' €':'—'}</div>`;
    item.addEventListener('click',()=>{
      if(key===selReg) return;
      const prev=legItems.get(selReg);
      if(prev) prev.classList.remove('active');
      setVisible(selReg,false);
      selReg=key;
      item.classList.add('active');
      setVisible(key,true);
      chartPrix.update(); chartEcart.update();
    });
    legItems.set(key,item);
    el.appendChild(item);
  });
}

function buildRanking(){
  const el=document.getElementById('rankRows'); el.innerHTML='';
  const ranked=ALL_KEYS.filter(k=>k!=='moy_regions').map(k=>{
    const v=lastVal(k); return {k,v};
  }).filter(d=>d.v!=null).sort((a,b)=>b.v-a.v);
  const maxV=ranked[0]?.v, minV=ranked.at(-1)?.v;
  ranked.forEach((item,i)=>{
    const pct=maxV===minV?50:((item.v-minV)/(maxV-minV)*90+10).toFixed(1);
    const row=document.createElement('div'); row.className='rank-row';
    row.innerHTML=`<div class="rank-num">${i+1}</div>
      <div class="rank-dot" style="background:${COLORS[item.k]||'#888'}"></div>
      <div class="rank-name" style="color:${COLORS[item.k]||'#888'}">${LABELS[item.k]||item.k}</div>
      <div class="rank-bar-wrap"><div class="rank-bar" style="width:${pct}%;background:${COLORS[item.k]||'#888'}"></div></div>
      <div class="rank-val">${item.v.toFixed(2)} €</div>`;
    el.appendChild(row);
  });
}

function buildAnalyse(){
  const el=document.getElementById('analyse-content'); if(!el) return;
  const d=ANALYSE[carbu]; if(!d) return;
  const c=carbu.toLowerCase();
  const col=(titre,texte,note)=>`<div class="analyse-col">
    <div class="analyse-titre">${titre}</div>
    <p class="analyse-texte">${texte}</p>
    <p class="analyse-note">${note}</p></div>`;

  const t1 = col(
    '1 — UN ÉCART QUI SE CREUSE, HORS TOUTE ACTION TOTALENERGIES',
    `Sans aucune intervention de TotalEnergies, l'écart de prix ${c} entre la Corse et le continent s'aggrave chaque année. +${d.tendance.y2022}&nbsp;c€/L&nbsp;HT en 2022, +${d.tendance.y2023}&nbsp;c€/L en 2023, +${d.tendance.y2024}&nbsp;c€/L en 2024, +${d.tendance.y2025}&nbsp;c€/L en 2025 — soit <strong>${d.tendance.delta}&nbsp;c€/L de plus en trois ans</strong>. Cette progression exclut toute explication par les seuls coûts d’insularité : ceux-ci sont stables d’une année sur l’autre. La Corse ne devient pas plus île — c’est donc autre chose qui fait grimper l’écart.`,
    'Source : moyenne journalière HT, données data.gouv.fr · carburantscorse.fr'
  );

  const t2 = col(
    '2 — EFFETS DES ACTIONS TOTALENERGIES',
    `Les remises carburant (sept.–déc.&nbsp;2022, −20&nbsp;c/L puis −10&nbsp;c/L) et les périodes d'activation du bouclier tarifaire ont atténué l'écart. En 2022, grâce aux remises, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022}&nbsp;c€/L</strong> au lieu de +${d.effet.sans2022}&nbsp;c€/L sans intervention — un gain de <strong>${d.effet.gain2022}&nbsp;c€/L</strong>. L'effet a même été spectaculaire ponctuellement : l'écart est brièvement devenu <strong>négatif (${d.effet.creux}&nbsp;c€/L)</strong> ${d.effet.creux_ctx}. En 2026, avec le bouclier actif depuis mars, l'écart annuel redescend à <strong>+${d.effet.avec2026}&nbsp;c€/L</strong> contre +${d.effet.sans2026}&nbsp;c€/L sans bouclier.`,
    'En 2024 et 2025, le bouclier a été activé par épisodes trop courts pour peser sur la moyenne annuelle.'
  );

  el.innerHTML = t1 + t2;
}

function updateBouclierInfo(){
  const bi=document.getElementById('bouclier-info'); if(!bi) return;
  const lp=document.getElementById('legende-promo');
  if(carbu==='Gazole'){
    bi.innerHTML='&#9632; Bouclier tarifaire TotalEnergies&nbsp;: <b>1,99&nbsp;€/L TTC</b> de août&nbsp;2023 au 19&nbsp;mars&nbsp;2026 · <b>2,09&nbsp;€/L TTC</b> du 20&nbsp;mars au 7&nbsp;avr.&nbsp;2026 · <b>2,25&nbsp;€/L TTC</b> depuis le 8&nbsp;avr.&nbsp;2026 <span style="color:rgba(234,88,12,0.8)">· Promo 2,09&nbsp;€/L les ponts de mai&nbsp;2026</span>';
    if(lp) lp.style.display='flex';
  } else {
    bi.innerHTML='&#9632; Bouclier tarifaire TotalEnergies&nbsp;: <b>1,99&nbsp;€/L TTC</b> depuis mars&nbsp;2023';
    if(lp) lp.style.display='none';
  }
}

function refresh(){
  if(!DATA||!chartPrix||!chartEcart) return;
  const dates=allDates();
  const npds=buildPrixDs(dates);
  const neds=buildEcartDs(dates);
  chartPrix.data.labels=dates;
  chartPrix.data.datasets.forEach((ds,i)=>{ if(npds[i]) ds.data=npds[i].data; });
  ALL_KEYS.forEach((k,i)=>{
    const meta=chartPrix.getDatasetMeta(i);
    if(meta) meta.hidden=(k!=='corse'&&k!==selReg);
  });
  chartPrix.update();
  chartEcart.data.labels=dates;
  chartEcart.data.datasets.forEach((ds,i)=>{ if(neds[i]) ds.data=neds[i].data; });
  ['moy_regions',...REGIONS].forEach((k,i)=>{
    const meta=chartEcart.getDatasetMeta(i);
    if(meta) meta.hidden=(k!==selReg);
  });
  chartEcart.update();
  document.getElementById('chartLabel').textContent=`${carbu.toUpperCase()} TTC — PRIX MOYEN JOURNALIER`;
  document.getElementById('chartEcartLabel').textContent=`${carbu.toUpperCase()} HT — ÉCART CORSE VS RÉGIONS (C€/L)`;
  document.getElementById('rankLabel').textContent=`CLASSEMENT AU 28 MAI 2026 — ${carbu.toUpperCase()} TTC`;
  document.getElementById('subtitleLine').textContent=`Prix moyen journalier (€/L TTC) · Janvier 2022 – Mai 2026 · Stations autoroute exclues`;
  updateBouclierInfo();
  buildLegend(); buildRanking(); buildAnalyse();
}

document.querySelectorAll('[data-carbu]').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('[data-carbu]').forEach(x=>x.classList.remove('active'));
  carbu=b.dataset.carbu; b.classList.add('active');
  selReg='moy_regions'; refresh();
}));

async function init(){
  await loadData();
  initCharts();
  updateBouclierInfo(); buildLegend(); buildRanking(); buildAnalyse();
  document.getElementById('loading').style.display='none';
}

init();


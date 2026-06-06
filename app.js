let DATA = null;
let resolution = 'd'; // m=mensuel w=hebdo d=journalier (défaut: journalier)

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
const REG_COLORS = ['#e07b39','#c9a227','#4a9e6b','#3a9ebf','#7b5ea7','#c94a7b',
  '#2a9e9e','#c94a4a','#7ba63a','#2a6fbf','#bf4abf','#e07b39'];
const COLORS = {corse:'#1a1a1a', moy_regions:'#e07b39'};
REGIONS.forEach((r,i)=>COLORS[r]=REG_COLORS[i%REG_COLORS.length]);

const BOUCLIER = {
  Gazole:[
    {d1:'2023-08-31',d2:'2023-10-13'},{d1:'2023-10-24',d2:'2023-10-30'},
    {d1:'2026-03-20',d2:'2026-04-06'},{d1:'2026-04-08',d2:'2026-05-27'},
  ],
  Gazole_promo:[
    {d1:'2026-04-30',d2:'2026-05-03'},{d1:'2026-05-08',d2:'2026-05-10'},
    {d1:'2026-05-14',d2:'2026-05-17'},{d1:'2026-05-23',d2:'2026-05-25'},
  ],
  SP95:[
    {d1:'2023-02-20',d2:'2023-03-19'},{d1:'2023-03-27',d2:'2023-05-02'},
    {d1:'2023-06-09',d2:'2023-06-21'},{d1:'2023-07-25',d2:'2023-10-07'},
    {d1:'2024-02-20',d2:'2024-03-01'},{d1:'2024-03-07',d2:'2024-06-05'},
    {d1:'2024-07-01',d2:'2024-07-16'},{d1:'2026-03-13',d2:'2026-05-28'},
  ],
};
const ZONES = [
  {d1:'2022-09-01',d2:'2022-11-15',alpha_fill:0.18},
  {d1:'2022-11-16',d2:'2022-12-31',alpha_fill:0.12},
];
const EVENTS = [
  {date:'2022-02-24',label:'Invasion Ukraine',color:'rgba(220,38,38,0.8)'},
  {date:'2025-11-17',label:'Sanctions Autorité',color:'rgba(234,88,12,0.8)'},
  {date:'2026-02-28',label:"Guerre d'Iran",color:'rgba(220,38,38,0.8)'},
];
const ANALYSE = {
  Gazole:{
    tendance:{y2022:'15,3',y2023:'17,3',y2024:'18,1',y2025:'18,3',delta:'+3,0'},
    effet:{avec2022:'12,2',sans2022:'15,3',gain2022:'3,1',avec2026:'12,8',sans2026:'15,3',gain2026:'2,5',creux:'−1,1',creux_ctx:"lors de la remise de 20 c/L à l'automne 2022"}
  },
  SP95:{
    tendance:{y2022:'14,2',y2023:'14,3',y2024:'17,2',y2025:'17,3',delta:'+3,1'},
    effet:{avec2022:'10,6',sans2022:'14,2',gain2022:'3,6',avec2026:'12,4',sans2026:'16,4',gain2026:'4,1',creux:'−6,8',creux_ctx:"lors du pic de la crise de 2023"}
  }
};

let carbu = 'Gazole';
let selReg = 'moy_regions';
const hidden = new Set(REGIONS);
const legItems = new Map();

// ── Accès aux données pré-calculées ─────────────────────────────────────────
const ORIGIN = new Date('2022-01-01');

function offsetToDate(n) {
  const d = new Date(ORIGIN); d.setDate(d.getDate()+n);
  return d.toISOString().slice(0,10);
}

function dateToOffset(str) {
  return Math.round((new Date(str) - ORIGIN) / 86400000);
}

function getSeries(carbuKey, serieName, res) {
  // Retourne [[label, ttc, ht], ...]
  return (DATA[carbuKey]?.[serieName]?.[res]) || [];
}

function getLabels(carbuKey, res) {
  // Labels des axes X depuis la série corse
  const pts = getSeries(carbuKey, 'corse', res);
  if(res === 'm') return pts.map(p=>p[0]); // "2022-01"
  return pts.map(p=>offsetToDate(p[0]));    // "2022-01-01"
}

function getTTC(carbuKey, serieName, res) {
  return getSeries(carbuKey, serieName, res).map(p=>p[1]);
}
function getHT(carbuKey, serieName, res) {
  return getSeries(carbuKey, serieName, res).map(p=>p[2]);
}

// ── Datasets Chart.js ────────────────────────────────────────────────────────
function buildPrixDs() {
  const ck = carbu==='Gazole'?'G':'S';
  const labels = getLabels(ck, resolution);
  return {labels, datasets: ALL_KEYS.map(key=>({
    label:LABELS[key]||key, _key:key,
    data: getTTC(ck, key, resolution),
    borderColor:COLORS[key]||'#888',
    backgroundColor:(COLORS[key]||'#888')+'18',
    borderWidth:key==='corse'?2.5:1.8,
    borderDash:key==='corse'?[6,3]:[],
    pointRadius:0, tension:0.3, spanGaps:true,
  }))};
}

function smooth7(arr) {
  return arr.map((v,i)=>{
    if(v==null) return null;
    const w=3;
    const sl=arr.slice(Math.max(0,i-w),i+w+1).filter(x=>x!=null);
    return sl.length?Math.round(sl.reduce((a,b)=>a+b,0)/sl.length*100)/100:null;
  });
}

function buildEcartDs() {
  const ck = carbu==='Gazole'?'G':'S';
  const labels = getLabels(ck, resolution);
  const corseHT = getHT(ck, 'corse', resolution);
  return {labels, datasets: ['moy_regions',...REGIONS].map(key=>({
    label:LABELS[key]||key, _key:key,
    data: (()=>{
      const raw = corseHT.map((vc,i)=>{
        const vr = getHT(ck, key, resolution)[i];
        return (vc!=null&&vr!=null)?Math.round((vc-vr)*10000)/100:null;
      });
      return resolution==='d' ? smooth7(raw) : raw;
    })(),
    borderColor:COLORS[key]||'#888',
    backgroundColor:(COLORS[key]||'#888')+'18',
    borderWidth:key==='moy_regions'?2:1.2,
    pointRadius:0, tension:0.3, spanGaps:true,
  }))};
}

// ── Plugins zones/événements ─────────────────────────────────────────────────
function getDateX(chart, dateStr) {
  const labels = chart.data.labels;
  // Pour mensuel, dateStr peut être "2022-09" → chercher le mois
  const searchStr = resolution==='m' ? dateStr.slice(0,7) : dateStr;
  let i = labels.indexOf(searchStr);
  if(i<0) i = labels.findIndex(d=>d>=searchStr);
  return i<0?null:chart.scales.x.getPixelForValue(i);
}

const zonesPlugin = {
  id:'zonesPlugin',
  afterDraw(chart) {
    const {ctx,chartArea:{left,right,top,bottom},scales:{x,y}}=chart;
    if(!x||!y) return;
    ctx.save(); ctx.beginPath(); ctx.rect(left,top,right-left,bottom-top); ctx.clip();
    ZONES.forEach(z=>{
      const x1=getDateX(chart,z.d1),x2=getDateX(chart,z.d2);
      if(x1==null||x2==null) return;
      ctx.fillStyle=`rgba(34,197,94,${z.alpha_fill})`;
      ctx.fillRect(x1,top,x2-x1,bottom-top);
    });
    (BOUCLIER[carbu]||[]).forEach(z=>{
      const x1=getDateX(chart,z.d1),x2=getDateX(chart,z.d2);
      if(x1==null||x2==null) return;
      ctx.fillStyle='rgba(251,191,36,0.12)';
      ctx.fillRect(x1,top,x2-x1,bottom-top);
    });
    if(carbu==='Gazole')(BOUCLIER['Gazole_promo']||[]).forEach(z=>{
      const x1=getDateX(chart,z.d1),x2=getDateX(chart,z.d2);
      if(x1==null||x2==null) return;
      ctx.fillStyle='rgba(234,88,12,0.09)';
      ctx.fillRect(x1,top,x2-x1,bottom-top);
    });
    const isMobile = window.innerWidth < 700;
    // Calculer les positions X de tous les événements pour éviter chevauchements
    const evPositions = EVENTS.map(ev=>({ev, px:getDateX(chart,ev.date)}))
                              .filter(e=>e.px!=null);
    evPositions.forEach((item, idx)=>{
      const {ev, px} = item;
      ctx.save();
      ctx.beginPath(); ctx.rect(left,top,right-left,bottom-top); ctx.clip();
      // Ligne verticale
      ctx.beginPath(); ctx.strokeStyle=ev.color; ctx.lineWidth=1.5;
      ctx.setLineDash([5,4]); ctx.moveTo(px,top); ctx.lineTo(px,bottom); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle=ev.color; ctx.font='bold 9px DM Mono,monospace';
      if(isMobile) {
        // Sur mobile : pas de label texte, juste la ligne verticale
        // (trop étroit pour afficher du texte lisiblement)
      } else {
        // Desktop : label vertical ancré en bas du graphe, monte vers le haut
        ctx.textAlign='right'; ctx.textBaseline='middle';
        ctx.translate(px-3, bottom-10); ctx.rotate(-Math.PI/2);
        ctx.fillText(ev.label, 0, 0);
      }
      ctx.restore();
    });
    ctx.restore();
  }
};
Chart.register(zonesPlugin);

// ── Formatage des ticks X ────────────────────────────────────────────────────
const MONTHS = ['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc'];
function formatLabel(lbl) {
  if(!lbl) return '';
  if(resolution==='m') {
    const [y,m] = lbl.split('-');
    return MONTHS[parseInt(m)-1]+' '+y.slice(2);
  }
  const parts = lbl.split('-');
  const y=parts[0], m=parts[1];
  return MONTHS[parseInt(m)-1]+' '+y.slice(2);
}

const TICK_CB = function(val, idx, ticks) {
  const lbl = this.getLabelForValue(val);
  if(!lbl) return '';
  // En journalier/hebdo : n'afficher que le 1er janvier de chaque année
  if(resolution !== 'm') {
    const parts = lbl.split('-');
    if(!parts[1] || !parts[2]) return '';
    if(parts[1] !== '01') return '';
    if(resolution === 'd' && parts[2] !== '01') return '';
    if(resolution === 'w' && parseInt(parts[2]) > 7) return '';
  }
  return formatLabel(lbl);
};
const GRID_OPTS  = {color:'#e5e1d8'};
const BORDER_OPTS = {color:'#dedad2'};
const TOOLTIP_BASE = {
  backgroundColor:'#ffffff',borderColor:'#ddd9d0',borderWidth:1,
  titleColor:'#777',bodyColor:'#1a1a1a',
  titleFont:{family:'DM Mono',size:10},bodyFont:{family:'DM Mono',size:11}
};

let chartPrix, chartEcart;

function initCharts() {
  const pd = buildPrixDs();
  const ed = buildEcartDs();

  chartPrix = new Chart(document.getElementById('chartPrix').getContext('2d'),{
    type:'line', data:pd,
    options:{
      responsive:true, interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{...TOOLTIP_BASE,
          filter:item=>(item.dataset._key==='corse'||item.dataset._key===selReg),
          callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(2)} € TTC`}
        }
      },
      scales:{
        x:{ticks:{color:'#999',font:{family:'DM Mono',size:10},maxRotation:0,autoSkip:false,callback:TICK_CB},grid:GRID_OPTS,border:BORDER_OPTS},
        y:{afterFit(s){s.width=62;},
          ticks:{color:'#999',font:{family:'DM Mono',size:11},padding:4,callback:v=>v.toFixed(2)+' €'},
          grid:{color:ctx=>ctx.tick?.value===0?'#aaa49a':'#e5e1d8'},border:BORDER_OPTS}
      }
    }
  });

  chartEcart = new Chart(document.getElementById('chartEcart').getContext('2d'),{
    type:'line', data:ed,
    options:{
      responsive:true, interaction:{mode:'index',intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{...TOOLTIP_BASE,
          filter:item=>item.dataset._key===selReg,
          callbacks:{label:ctx=>{
            const v=ctx.parsed.y; if(v==null) return null;
            return `${ctx.dataset.label}: ${v>=0?'+':''}${v.toFixed(2)} c€/L`;
          }}
        }
      },
      scales:{
        x:{ticks:{color:'#999',font:{family:'DM Mono',size:10},maxRotation:0,autoSkip:false,callback:TICK_CB},grid:GRID_OPTS,border:BORDER_OPTS},
        y:{beginAtZero:false,
          ticks:{color:'#999',font:{family:'DM Mono',size:11},callback:v=>(v>=0?'+':'')+v.toFixed(1)+' c€'},
          grid:{color:ctx=>ctx.tick?.value===0?'#aaa49a':'#e5e1d8',lineWidth:ctx=>ctx.tick?.value===0?1.5:1},
          border:BORDER_OPTS}
      }
    }
  });
  applyVisibility();
  // Mettre à jour les titres dès le chargement
  document.getElementById('chartLabel').textContent=`${carbu.toUpperCase()} TTC — PRIX MOYEN ${resolution==='m'?'MENSUEL':resolution==='w'?'HEBDOMADAIRE':'JOURNALIER'}`;
  document.getElementById('chartEcartLabel').textContent=`${carbu.toUpperCase()} HT — ÉCART CORSE VS RÉGIONS (C€/L)`;
  document.getElementById('rankLabel').textContent=`CLASSEMENT AU 28 MAI 2026 — ${carbu.toUpperCase()} TTC`;
  // Mettre à jour le bouton résolution actif
  document.querySelectorAll('[data-res]').forEach(b=>{
    b.classList.toggle('active', b.dataset.res===resolution);
  });
}

function applyVisibility() {
  ALL_KEYS.forEach((k,i)=>{
    const m=chartPrix.getDatasetMeta(i);
    if(m) m.hidden=(k!=='corse'&&k!==selReg);
  });
  ['moy_regions',...REGIONS].forEach((k,i)=>{
    const m=chartEcart.getDatasetMeta(i);
    if(m) m.hidden=(k!==selReg);
  });
  chartPrix.update(); chartEcart.update();
}

function setVisible(key, visible) {
  const i1=chartPrix.data.datasets.findIndex(d=>d._key===key);
  if(i1>=0) chartPrix.getDatasetMeta(i1).hidden=!visible;
  const i2=chartEcart.data.datasets.findIndex(d=>d._key===key);
  if(i2>=0) chartEcart.getDatasetMeta(i2).hidden=!visible;
}

function lastVal(key) {
  // Toujours sur les données journalières pour le classement
  if(key==='moy_regions') {
    const vals=REGIONS.map(r=>lastVal(r)).filter(v=>v!=null);
    return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
  }
  const ck=carbu==='Gazole'?'G':'S';
  const pts=getSeries(ck,key,'d');
  const last=pts.filter(p=>p[1]!=null).at(-1);
  return last?last[1]:null;
}

function buildLegend() {
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
      selReg=key; item.classList.add('active');
      setVisible(key,true);
      chartPrix.update(); chartEcart.update();
    });
    legItems.set(key,item);
    el.appendChild(item);
  });
}

function buildRanking() {
  const el=document.getElementById('rankRows'); el.innerHTML='';
  const ranked=ALL_KEYS.filter(k=>k!=='moy_regions').map(k=>({k,v:lastVal(k)}))
    .filter(d=>d.v!=null).sort((a,b)=>b.v-a.v);
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

function buildAnalyse() {
  const el=document.getElementById('analyse-content'); if(!el) return;
  const d=ANALYSE[carbu]; if(!d) return;
  const c=carbu.toLowerCase();
  const col=(titre,texte,note)=>`<div class="analyse-col">
    <div class="analyse-titre">${titre}</div>
    <p class="analyse-texte">${texte}</p>
    <p class="analyse-note">${note}</p></div>`;
  el.innerHTML=
    col('1 — UN ÉCART QUI SE CREUSE, HORS TOUTE ACTION TOTALENERGIES',
      `Sans aucune intervention de TotalEnergies, l'écart de prix ${c} entre la Corse et le continent s'aggrave chaque année : <strong>+${d.tendance.y2022} c€/L HT en 2022</strong>, <strong>+${d.tendance.y2023} c€/L en 2023</strong>, <strong>+${d.tendance.y2024} c€/L en 2024</strong>, <strong>+${d.tendance.y2025} c€/L en 2025</strong> — soit <strong>${d.tendance.delta} c€/L de plus en trois ans</strong>. Cette progression exclut toute explication par les seuls coûts d’insularité : ceux-ci sont stables d’une année sur l’autre. La Corse ne devient pas plus île — c’est donc autre chose qui fait grimper l’écart.`,
      'Source : moyenne journalière HT, données data.gouv.fr · carburantscorse.fr')+
    col('2 — EFFETS DES ACTIONS TOTALENERGIES',
      `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) et les périodes d'activation du bouclier tarifaire ont atténué l'écart. En 2022, grâce aux remises, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L sans intervention — un gain de <strong>${d.effet.gain2022} c€/L</strong>. L'effet a même été spectaculaire ponctuellement : l'écart est brièvement devenu <strong>négatif (${d.effet.creux} c€/L)</strong> ${d.effet.creux_ctx}. En 2026, avec le bouclier actif depuis mars, l'écart annuel redescend à <strong>+${d.effet.avec2026} c€/L</strong> contre +${d.effet.sans2026} c€/L sans bouclier.`,
      'En 2024 et 2025, le bouclier a été activé par épisodes trop courts pour peser sur la moyenne annuelle.');
}

function updateBouclierInfo() {
  const bi=document.getElementById('bouclier-info'); if(!bi) return;
  const lp=document.getElementById('legende-promo');
  if(carbu==='Gazole') {
    bi.innerHTML='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> de août 2023 au 19 mars 2026 · <b>2,09 €/L TTC</b> du 20 mars au 7 avr. 2026 · <b>2,25 €/L TTC</b> depuis le 8 avr. 2026 <span style="color:rgba(234,88,12,0.8)">· Promo 2,09 €/L les ponts de mai 2026</span>';
    if(lp) lp.style.display='flex';
  } else {
    bi.innerHTML='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> depuis mars 2023';
    if(lp) lp.style.display='none';
  }
}

function refresh() {
  if(!DATA||!chartPrix||!chartEcart) return;
  const pd=buildPrixDs(); const ed=buildEcartDs();
  chartPrix.data.labels=pd.labels;
  chartPrix.data.datasets.forEach((ds,i)=>{if(pd.datasets[i]) ds.data=pd.datasets[i].data;});
  chartEcart.data.labels=ed.labels;
  chartEcart.data.datasets.forEach((ds,i)=>{if(ed.datasets[i]) ds.data=ed.datasets[i].data;});
  applyVisibility();
  document.getElementById('chartLabel').textContent=`${carbu.toUpperCase()} TTC — PRIX MOYEN ${resolution==='m'?'MENSUEL':resolution==='w'?'HEBDOMADAIRE':'JOURNALIER'}`;
  document.getElementById('chartEcartLabel').textContent=`${carbu.toUpperCase()} HT — ÉCART CORSE VS RÉGIONS (C€/L)`;
  document.getElementById('rankLabel').textContent=`CLASSEMENT AU 28 MAI 2026 — ${carbu.toUpperCase()} TTC`;
  updateBouclierInfo(); buildLegend(); buildRanking(); buildAnalyse();
  // Mettre à jour boutons résolution
  document.querySelectorAll('[data-res]').forEach(b=>{
    b.classList.toggle('active', b.dataset.res===resolution);
  });
}

// ── Listeners ────────────────────────────────────────────────────────────────
document.querySelectorAll('[data-carbu]').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('[data-carbu]').forEach(x=>x.classList.remove('active'));
  carbu=b.dataset.carbu; b.classList.add('active');
  selReg='moy_regions'; refresh();
}));

document.querySelectorAll('[data-res]').forEach(b=>b.addEventListener('click',()=>{
  resolution=b.dataset.res; refresh();
}));

async function init() {
  await loadData();
  initCharts();
  refresh(); // met à jour titres, légende, classement, analyse
  document.getElementById('loading').style.display='none';
}

init();

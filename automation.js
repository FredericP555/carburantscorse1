// Couche d'automatisation A4C — chargée après app.js.
// Elle conserve le design historique et ajoute : dates dynamiques, fenêtre étroite,
// zones de bouclier prospectives et analyse courante reproductible.

function autoDateFr(str, withYear=true) {
  if(!str) return '';
  const [y,m,d]=str.split('-').map(Number);
  const months=['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'];
  return `${d} ${months[m-1]}${withYear?' '+y:''}`;
}

function autoMonthYearFr(str) {
  if(!str) return '';
  const [y,m]=str.split('-').map(Number);
  const months=['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
  return `${months[m-1]} ${y}`;
}

function autoNumberFr(v, digits=1, sign=false) {
  if(v==null || Number.isNaN(Number(v))) return '—';
  const n=Number(v);
  return `${sign&&n>=0?'+':''}${n.toFixed(digits).replace('.',',')}`;
}

// ── Fenêtre temporelle ───────────────────────────────────────────────────────
// Le critère porte sur la largeur réellement disponible pour le graphe, et non sur
// l'orientation de window. C'est indispensable quand le dashboard est intégré dans un iframe.
let autoMobileMonthsWindow=12;
let autoMonthsWindow=12;
let autoMonthsMax=12;
let autoNarrow=false;
const AUTO_NARROW_WIDTH=950;

function autoEnsurePeriodControl(){
  if(document.getElementById('periodControl')) return;
  const header=document.querySelector('header');
  const firstControls=header?.querySelector('.controls');
  if(!header||!firstControls) return;
  const ctrl=document.createElement('div');
  ctrl.id='periodControl';
  ctrl.className='controls';
  ctrl.style.marginTop='0.4rem';
  ctrl.style.display='none';
  ctrl.innerHTML=`<span class="ctrl-label">PÉRIODE AFFICHÉE</span>
    <input type="range" id="periodSlider" min="12" max="12" value="12" step="1" style="flex:1;min-width:120px;max-width:300px">
    <span class="ctrl-label" id="periodLabel" style="color:var(--text);letter-spacing:0;font-size:0.65rem">12 derniers mois</span>`;
  firstControls.insertAdjacentElement('afterend',ctrl);
  document.getElementById('periodSlider')?.addEventListener('input',e=>{
    autoMobileMonthsWindow=parseInt(e.target.value,10)||12;
    autoMonthsWindow=Math.min(autoMobileMonthsWindow,autoMonthsMax);
    autoUpdatePeriodLabel();
    if(typeof chartPrix!=='undefined'&&chartPrix&&typeof chartEcart!=='undefined'&&chartEcart) refresh();
  });
}

autoEnsurePeriodControl();

function autoComputeMonthsMax(){
  const ck=carbu==='Gazole'?'G':'S';
  const pts=getSeries(ck,'corse','d');
  if(!pts.length) return 12;
  const first=new Date(offsetToDate(pts[0][0]));
  const last=new Date(offsetToDate(pts[pts.length-1][0]));
  return Math.max(12,(last.getFullYear()-first.getFullYear())*12+(last.getMonth()-first.getMonth())+1);
}

function autoFullPeriodYears(){
  const ck=carbu==='Gazole'?'G':'S';
  const pts=getSeries(ck,'corse','d');
  if(!pts.length) return '';
  const first=offsetToDate(pts[0][0]).slice(0,4);
  const last=offsetToDate(pts[pts.length-1][0]).slice(0,4);
  return first===last?first:`${first}–${last}`;
}

function autoUpdatePeriodLabel(){
  const lbl=document.getElementById('periodLabel');
  if(!lbl) return;
  if(autoMonthsWindow>=autoMonthsMax){
    lbl.textContent=`Toute la période (${autoFullPeriodYears()})`;
    return;
  }
  if(autoMonthsWindow===12){lbl.textContent='12 derniers mois';return;}
  const years=Math.floor(autoMonthsWindow/12), months=autoMonthsWindow%12;
  const parts=[];
  if(years) parts.push(`${years} ${years>1?'ans':'an'}`);
  if(months) parts.push(`${months} mois`);
  lbl.textContent=parts.join(' ');
}

function autoAvailableChartWidth(){
  const host=document.querySelector('.chart-wrap') || document.querySelector('.charts');
  const width=host?.getBoundingClientRect?.().width;
  return width&&Number.isFinite(width)?width:window.innerWidth;
}

function autoSyncPeriodMode(){
  autoMonthsMax=autoComputeMonthsMax();
  autoNarrow=autoAvailableChartWidth()<AUTO_NARROW_WIDTH;
  const ctrl=document.getElementById('periodControl');
  const slider=document.getElementById('periodSlider');
  if(ctrl) ctrl.style.display=autoNarrow?'flex':'none';
  if(autoNarrow){
    autoMobileMonthsWindow=Math.max(12,Math.min(autoMobileMonthsWindow,autoMonthsMax));
    autoMonthsWindow=autoMobileMonthsWindow;
  }else{
    autoMonthsWindow=autoMonthsMax;
  }
  if(slider){slider.min=12;slider.max=autoMonthsMax;slider.value=autoMonthsWindow;}
  autoUpdatePeriodLabel();
}

function autoWindowStartIndex(labels){
  if(!autoNarrow || autoMonthsWindow>=autoMonthsMax || !labels.length) return 0;
  const lastLbl=labels[labels.length-1];
  const lastDateStr=resolution==='m'?lastLbl+'-01':lastLbl;
  const cutoff=new Date(lastDateStr);
  cutoff.setMonth(cutoff.getMonth()-autoMonthsWindow);
  const cutoffStr=cutoff.toISOString().slice(0,10);
  const idx=labels.findIndex(l=>(resolution==='m'?l+'-01':l)>=cutoffStr);
  return idx<0?0:idx;
}

function autoSliceWindow(result){
  if(!result?.labels?.length) return result;
  const start=autoWindowStartIndex(result.labels);
  if(start<=0) return result;
  return {
    labels:result.labels.slice(start),
    datasets:result.datasets.map(ds=>({...ds,data:ds.data.slice(start)})),
  };
}

const _autoBaseBuildPrixDs=buildPrixDs;
buildPrixDs=function(){return autoSliceWindow(_autoBaseBuildPrixDs());};
const _autoBaseBuildEcartDs=buildEcartDs;
buildEcartDs=function(){return autoSliceWindow(_autoBaseBuildEcartDs());};

// ── Métadonnées automatiques ─────────────────────────────────────────────────
function applyAutomationMeta() {
  const meta=DATA?.meta;
  if(!meta) return;
  const b=meta.bouclier||{};
  if(b.Gazole?.ranges) BOUCLIER.Gazole=b.Gazole.ranges.map(x=>({...x}));
  if(b.SP95?.ranges) BOUCLIER.SP95=b.SP95.ranges.map(x=>({...x}));

  // Le projet méthodologique du 14/06/2026 documente également une promotion 2,09 €/L
  // les 29–31 mai. On la conserve avec les épisodes déjà présents dans app (2).js.
  if(Array.isArray(BOUCLIER.Gazole_promo) && !BOUCLIER.Gazole_promo.some(x=>x.d1==='2026-05-29')){
    BOUCLIER.Gazole_promo.push({d1:'2026-05-29',d2:'2026-05-31'});
  }
}

function applyDynamicLabels() {
  const last=DATA?.meta?.last_date;
  if(!last) return;
  const lastLong=autoDateFr(last).toUpperCase();
  const rank=document.getElementById('rankLabel');
  if(rank) rank.textContent=`CLASSEMENT AU ${lastLong} — ${carbu.toUpperCase()} TTC`;
  const subtitle=document.getElementById('subtitleLine');
  if(subtitle) subtitle.textContent=`Prix moyen journalier (€/L TTC) · Janvier 2022 – ${autoMonthYearFr(last)} · Stations autoroute exclues`;
  autoUpdatePeriodLabel();
}

const _autoBaseInitCharts=initCharts;
initCharts=function(){
  applyAutomationMeta();
  autoSyncPeriodMode();
  _autoBaseInitCharts();
  applyDynamicLabels();
};

const _autoBaseRefresh=refresh;
refresh=function(){
  applyAutomationMeta();
  autoSyncPeriodMode();
  _autoBaseRefresh();
  applyDynamicLabels();
};

let _autoResizeTimer;
function autoViewportChanged(){
  clearTimeout(_autoResizeTimer);
  _autoResizeTimer=setTimeout(()=>{
    const before=autoNarrow;
    autoSyncPeriodMode();
    if((before!==autoNarrow) && typeof chartPrix!=='undefined'&&chartPrix) refresh();
  },120);
}
window.addEventListener('resize',autoViewportChanged);
window.addEventListener('orientationchange',()=>setTimeout(autoViewportChanged,200));

// ── Analyse éditoriale ───────────────────────────────────────────────────────
// Méthode historique retrouvée : « hors toute action TotalEnergies » = moyenne des jours
// où AUCUNE intervention Total n'est active, ni sur le Gazole ni sur le SP95. L'indicateur
// utilise donc le calendrier commun (union des deux carburants), et non un contrefactuel.
buildAnalyse=function(){
  const el=document.getElementById('analyse-content'); if(!el) return;
  const d=ANALYSE[carbu]; if(!d) return;
  const e=DATA?.meta?.editorial?.[carbu];
  const b=DATA?.meta?.bouclier?.[carbu];
  const c=carbu.toLowerCase();
  const col=(titre,texte,note)=>`<div class="analyse-col">
    <div class="analyse-titre">${titre}</div>
    <p class="analyse-texte">${texte}</p>
    <p class="analyse-note">${note}</p></div>`;

  const historique=col('1 — UN ÉCART QUI SE CREUSE, HORS TOUTE ACTION TOTALENERGIES',
    `Sur les jours hors toute action TotalEnergies, l'écart moyen HT du ${c} entre la Corse et le continent passe de <strong>+${d.tendance.y2022} c€/L en 2022</strong> à <strong>+${d.tendance.y2023} c€/L en 2023</strong>, <strong>+${d.tendance.y2024} c€/L en 2024</strong> puis <strong>+${d.tendance.y2025} c€/L en 2025</strong> — soit <strong>${d.tendance.delta} c€/L de plus en trois ans</strong>. Cette progression ne peut pas s'expliquer par un seul surcoût d'insularité supposé stable : la Corse ne devient pas davantage une île d'une année sur l'autre.`,
    'Source : moyenne journalière HT, données data.gouv.fr · carburantscorse.fr');

  if(!e) {
    el.innerHTML=historique+col('2 — EFFETS DES ACTIONS TOTALENERGIES',
      `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) et les périodes d'activation du bouclier tarifaire ont atténué l'écart. En 2022, grâce aux remises, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L hors toute action TotalEnergies — un gain de <strong>${d.effet.gain2022} c€/L</strong>.`,
      'Données courantes non encore disponibles.');
    return;
  }

  const through=autoDateFr(e.through);
  const p75=b?.latest_non_total_p75;
  const outsideGap=e.outside_total_action_gap ?? e.outside_effective_gap;
  const duringGap=e.during_total_action_gap ?? e.during_effective_gap;
  const currentStatus=e.current_active
    ? `Le bouclier est <strong>actuellement détecté comme contraignant depuis le ${autoDateFr(e.current_active_since)}</strong> : au dernier relevé, <strong>${Math.round((e.latest_near_share||0)*100)} %</strong> des <strong>${e.latest_total_stations}</strong> stations TotalEnergies suivies sont à moins de 1,5 c€/L du plafond de <strong>${autoNumberFr(e.current_cap,2)} €/L</strong>${p75!=null?`, tandis que le 75e percentile des stations corses non‑Total atteint <strong>${autoNumberFr(p75,3)} €/L</strong>`:''}.`
    : `Au ${through}, le plafond TotalEnergies est en vigueur mais <strong>n'est pas détecté comme économiquement contraignant</strong> par la combinaison « prix Total au plafond + pression du reste du marché corse ».`;

  const splitText=outsideGap!=null
    ? `Hors toute période d'action TotalEnergies — c'est-à-dire les jours où aucune action n'est active ni sur le gazole ni sur le SP95 — l'écart moyen atteint <strong>${autoNumberFr(outsideGap,1,true)} c€/L</strong>${duringGap!=null?`; pendant les périodes d'action TotalEnergies, il est de <strong>${autoNumberFr(duringGap,1,true)} c€/L</strong>`:''}.`
    : '';

  const courant=col('2 — EFFETS DES ACTIONS TOTALENERGIES',
    `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) ont nettement réduit l'écart : en 2022, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L hors toute action TotalEnergies. En ${e.year}, jusqu'au ${through}, l'écart moyen observé s'établit à <strong>${autoNumberFr(e.observed_ytd_gap,1,true)} c€/L</strong>. ${splitText} ${currentStatus}`,
    '« Hors toute action TotalEnergies » : moyenne des écarts journaliers HT des jours où aucune intervention Total n’est active sur aucun des deux carburants. Le bouclier prospectif reste détecté selon la règle économique documentée ; les anciennes zones sont figées.');

  el.innerHTML=historique+courant;
};

updateBouclierInfo=function(){
  const bi=document.getElementById('bouclier-info'); if(!bi) return;
  const lp=document.getElementById('legende-promo');
  const b=DATA?.meta?.bouclier?.[carbu];
  if(!b) return;
  const statut=b.current_active
    ? `<strong>contraignant depuis le ${autoDateFr(b.current_active_since)}</strong>`
    : '<strong>actuellement non contraignant</strong>';
  bi.innerHTML=`■ Plafond TotalEnergies suivi : <b>${autoNumberFr(b.current_cap,2)} €/L TTC</b> · Bouclier ${statut}`+
    (carbu==='Gazole'?' <span style="color:rgba(234,88,12,0.8)">· Promotions 2,09 €/L observées par épisodes en mai 2026</span>':'');
  if(lp){
    lp.style.display=carbu==='Gazole'?'flex':'none';
    if(carbu==='Gazole'){
      const txt=lp.childNodes[lp.childNodes.length-1];
      if(txt&&txt.nodeType===Node.TEXT_NODE) txt.textContent=' Promotions Total 2,09 €/L — épisodes de mai 2026';
    }
  }
};

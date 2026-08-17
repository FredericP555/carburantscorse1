// Couche d'automatisation A4C — chargée après app.js.
// Elle ne change pas le design : elle remplace uniquement les dates, zones de bouclier
// et éléments éditoriaux qui doivent suivre data.json.

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

function applyAutomationMeta() {
  const meta=DATA?.meta;
  if(!meta) return;
  const b=meta.bouclier||{};
  if(b.Gazole?.ranges) BOUCLIER.Gazole=b.Gazole.ranges.map(x=>({...x}));
  if(b.SP95?.ranges) BOUCLIER.SP95=b.SP95.ranges.map(x=>({...x}));
}

function applyDynamicLabels() {
  const last=DATA?.meta?.last_date;
  if(!last) return;
  const lastLong=autoDateFr(last).toUpperCase();
  const rank=document.getElementById('rankLabel');
  if(rank) rank.textContent=`CLASSEMENT AU ${lastLong} — ${carbu.toUpperCase()} TTC`;
  const subtitle=document.getElementById('subtitleLine');
  if(subtitle) subtitle.textContent=`Prix moyen journalier (€/L TTC) · Janvier 2022 – ${autoMonthYearFr(last)} · Stations autoroute exclues`;
}

// Conserver les fonctions originales, puis injecter les métadonnées avant le premier dessin.
const _autoBaseInitCharts=initCharts;
initCharts=function(){
  applyAutomationMeta();
  _autoBaseInitCharts();
};

const _autoBaseRefresh=refresh;
refresh=function(){
  applyAutomationMeta();
  _autoBaseRefresh();
  applyDynamicLabels();
};

// Même mise en page éditoriale, mais la partie 2026+ repose uniquement sur des grandeurs
// reproductibles. Les valeurs historiques 2022–2025 restent celles déjà publiées.
buildAnalyse=function(){
  const el=document.getElementById('analyse-content'); if(!el) return;
  const d=ANALYSE[carbu]; if(!d) return;
  const e=DATA?.meta?.editorial?.[carbu];
  const c=carbu.toLowerCase();
  const col=(titre,texte,note)=>`<div class="analyse-col">
    <div class="analyse-titre">${titre}</div>
    <p class="analyse-texte">${texte}</p>
    <p class="analyse-note">${note}</p></div>`;

  const historique=col('1 — UN ÉCART QUI SE CREUSE, HORS TOUTE ACTION TOTALENERGIES',
    `Sans aucune intervention de TotalEnergies, l'écart de prix ${c} entre la Corse et le continent s'aggrave chaque année : <strong>+${d.tendance.y2022} c€/L HT en 2022</strong>, <strong>+${d.tendance.y2023} c€/L en 2023</strong>, <strong>+${d.tendance.y2024} c€/L en 2024</strong>, <strong>+${d.tendance.y2025} c€/L en 2025</strong> — soit <strong>${d.tendance.delta} c€/L de plus en trois ans</strong>. Cette progression exclut toute explication par les seuls coûts d’insularité : ceux-ci sont stables d’une année sur l’autre. La Corse ne devient pas plus île — c’est donc autre chose qui fait grimper l'écart.`,
    'Source : moyenne journalière HT, données data.gouv.fr · carburantscorse.fr');

  if(!e) {
    el.innerHTML=historique+col('2 — EFFETS DES ACTIONS TOTALENERGIES',
      `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) et les périodes d'activation du bouclier tarifaire ont atténué l'écart. En 2022, grâce aux remises, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L sans intervention — un gain de <strong>${d.effet.gain2022} c€/L</strong>.`,
      'Données courantes non encore disponibles.');
    return;
  }

  const through=autoDateFr(e.through);
  const currentStatus=e.current_active
    ? `Le bouclier est <strong>actuellement effectif depuis le ${autoDateFr(e.current_active_since)}</strong> : au dernier relevé, <strong>${Math.round((e.latest_near_share||0)*100)} %</strong> des <strong>${e.latest_total_stations}</strong> stations TotalEnergies suivies se situent à moins de 1,5 c€/L du plafond de <strong>${autoNumberFr(e.current_cap,2)} €/L</strong>.`
    : `Au ${through}, le plafond TotalEnergies est en vigueur mais <strong>n'est pas détecté comme économiquement contraignant</strong> selon la distribution des prix observée.`;

  const courant=col('2 — EFFETS DES ACTIONS TOTALENERGIES',
    `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) ont nettement réduit l'écart : en 2022, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L hors remise. En ${e.year}, jusqu'au ${through}, l'écart moyen observé s'établit à <strong>${autoNumberFr(e.observed_ytd_gap,1,true)} c€/L</strong>. Hors périodes où le bouclier est détecté comme effectivement contraignant, il atteint <strong>${autoNumberFr(e.outside_effective_gap,1,true)} c€/L</strong>. ${currentStatus}`,
    'Bouclier effectif : au moins 30 % des stations TotalEnergies à moins de 1,5 c€/L du plafond, avec stabilisation des épisodes courts.');

  el.innerHTML=historique+courant;
};

updateBouclierInfo=function(){
  const bi=document.getElementById('bouclier-info'); if(!bi) return;
  const lp=document.getElementById('legende-promo');
  const b=DATA?.meta?.bouclier?.[carbu];
  if(!b) return;
  const statut=b.current_active
    ? `<strong>effectif depuis le ${autoDateFr(b.current_active_since)}</strong>`
    : '<strong>actuellement non contraignant</strong>';
  bi.innerHTML=`■ Plafond TotalEnergies suivi : <b>${autoNumberFr(b.current_cap,2)} €/L TTC</b> · Bouclier ${statut}`+
    (carbu==='Gazole'?' <span style="color:rgba(234,88,12,0.8)">· Promo 2,09 €/L les ponts de mai 2026</span>':'');
  if(lp) lp.style.display=carbu==='Gazole'?'flex':'none';
};

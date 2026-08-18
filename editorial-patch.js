// Ajustements éditoriaux de présentation — chargés après automation.js.
// 1) historique disponible explicite dans le sous-titre ;
// 2) texte éditorial coulé et équilibré sur deux colonnes ;
// 3) statut du bouclier distinguant la période actuelle des épisodes antérieurs de 2026.

function editorialEnsureStyles(){
  if(document.getElementById('editorial-flow-style')) return;
  const style=document.createElement('style');
  style.id='editorial-flow-style';
  style.textContent=`
    #analyse-content{display:block}
    #analyse-content .analyse-flow{column-count:2;column-gap:1.2rem;column-fill:balance}
    #analyse-content .analyse-flow .analyse-titre{break-after:avoid-column}
    #analyse-content .analyse-flow .analyse-note{break-inside:avoid}
    @media(max-width:700px){#analyse-content .analyse-flow{column-count:1}}
  `;
  document.head.appendChild(style);
}

function editorialRangeFr(r){
  return `du ${autoDateFr(r.d1,false)} au ${autoDateFr(r.d2)}`;
}

function editorialRangeCompact(r){
  return `${autoDateFr(r.d1,false)}–${autoDateFr(r.d2)}`;
}

function editorialJoinRanges(ranges,compact=false){
  const labels=ranges.map(r=>compact?editorialRangeCompact(r):editorialRangeFr(r));
  if(labels.length<=1) return labels[0]||'';
  if(labels.length===2) return `${labels[0]} puis ${labels[1]}`;
  return `${labels.slice(0,-1).join(', ')} puis ${labels[labels.length-1]}`;
}

function editorialEarlierIranWarRanges(b,currentSince){
  return (b?.ranges||[]).filter(r=>
    r.d1>='2026-02-28' && (!currentSince || r.d2<currentSince)
  );
}

const _editorialBaseApplyDynamicLabels=applyDynamicLabels;
applyDynamicLabels=function(){
  _editorialBaseApplyDynamicLabels();
  const last=DATA?.meta?.last_date;
  const subtitle=document.getElementById('subtitleLine');
  if(last&&subtitle){
    subtitle.textContent=`Historique disponible : janvier 2022 – ${autoMonthYearFr(last).toLowerCase()} · Stations autoroute exclues`;
  }
};

editorialEnsureStyles();

buildAnalyse=function(){
  const el=document.getElementById('analyse-content'); if(!el) return;
  const d=ANALYSE[carbu]; if(!d) return;
  const e=DATA?.meta?.editorial?.[carbu];
  const b=DATA?.meta?.bouclier?.[carbu];
  const c=carbu.toLowerCase();
  const block=(titre,texte,note)=>`
    <div class="analyse-titre">${titre}</div>
    <p class="analyse-texte">${texte}</p>
    <p class="analyse-note">${note}</p>`;

  const historique=block('1 — UN ÉCART QUI SE CREUSE, HORS TOUTE ACTION TOTALENERGIES',
    `Sur les jours hors toute action TotalEnergies, l'écart moyen HT du ${c} entre la Corse et le continent passe de <strong>+${d.tendance.y2022} c€/L en 2022</strong> à <strong>+${d.tendance.y2023} c€/L en 2023</strong>, <strong>+${d.tendance.y2024} c€/L en 2024</strong> puis <strong>+${d.tendance.y2025} c€/L en 2025</strong> — soit <strong>${d.tendance.delta} c€/L de plus en trois ans</strong>. Cette progression ne peut pas s'expliquer par un seul surcoût d'insularité supposé stable : la Corse ne devient pas davantage une île d'une année sur l'autre.`,
    'Source : moyenne journalière HT, données data.gouv.fr · carburantscorse.fr');

  if(!e){
    const courant=block('2 — EFFETS DES ACTIONS TOTALENERGIES',
      `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) et les périodes d'activation du bouclier tarifaire ont atténué l'écart. En 2022, grâce aux remises, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L hors toute action TotalEnergies — un gain de <strong>${d.effet.gain2022} c€/L</strong>.`,
      'Données courantes non encore disponibles.');
    el.innerHTML=`<div class="analyse-flow">${historique}${courant}</div>`;
    return;
  }

  const through=autoDateFr(e.through);
  const p75=b?.latest_non_total_p75;
  const outsideGap=e.outside_total_action_gap ?? e.outside_effective_gap;
  const duringGap=e.during_total_action_gap ?? e.during_effective_gap;
  const priorRanges=editorialEarlierIranWarRanges(b,e.current_active_since);
  const priorStatus=priorRanges.length
    ? `Après le début de la guerre en Iran, le bouclier avait déjà été détecté comme contraignant ${editorialJoinRanges(priorRanges)}. `
    : '';
  const currentStatus=e.current_active
    ? `${priorStatus}Il est <strong>actuellement détecté comme contraignant depuis le ${autoDateFr(e.current_active_since)}</strong> : au dernier relevé, <strong>${Math.round((e.latest_near_share||0)*100)} %</strong> des <strong>${e.latest_total_stations}</strong> stations TotalEnergies suivies sont à moins de 1,5 c€/L du plafond de <strong>${autoNumberFr(e.current_cap,2)} €/L</strong>${p75!=null?`, tandis que le 75e percentile des stations corses non‑Total atteint <strong>${autoNumberFr(p75,3)} €/L</strong>`:''}.`
    : `${priorStatus}Au ${through}, le plafond TotalEnergies est en vigueur mais <strong>n'est pas détecté comme économiquement contraignant</strong> par la combinaison « prix Total au plafond + pression du reste du marché corse ».`;

  const splitText=outsideGap!=null
    ? `Hors toute période d'action TotalEnergies — c'est-à-dire les jours où aucune action n'est active ni sur le gazole ni sur le SP95 — l'écart moyen atteint <strong>${autoNumberFr(outsideGap,1,true)} c€/L</strong>${duringGap!=null?`; pendant les périodes d'action TotalEnergies, il est de <strong>${autoNumberFr(duringGap,1,true)} c€/L</strong>`:''}.`
    : '';

  const courant=block('2 — EFFETS DES ACTIONS TOTALENERGIES',
    `Les remises carburant (sept.–déc. 2022, −20 c/L puis −10 c/L) ont nettement réduit l'écart : en 2022, l'écart annuel moyen ${c} est tombé à <strong>+${d.effet.avec2022} c€/L</strong> au lieu de +${d.effet.sans2022} c€/L hors toute action TotalEnergies. En ${e.year}, jusqu'au ${through}, l'écart moyen observé s'établit à <strong>${autoNumberFr(e.observed_ytd_gap,1,true)} c€/L</strong>. ${splitText} ${currentStatus}`,
    '« Hors toute action TotalEnergies » : moyenne des écarts journaliers HT des jours où aucune intervention Total n’est active sur aucun des deux carburants. Le bouclier prospectif reste détecté selon la règle économique documentée ; les anciennes zones sont figées.');

  el.innerHTML=`<div class="analyse-flow">${historique}${courant}</div>`;
};

updateBouclierInfo=function(){
  const bi=document.getElementById('bouclier-info'); if(!bi) return;
  const lp=document.getElementById('legende-promo');
  const b=DATA?.meta?.bouclier?.[carbu];
  if(!b) return;
  const priorRanges=editorialEarlierIranWarRanges(b,b.current_active_since);
  const statut=b.current_active
    ? `<strong>actuellement détecté comme contraignant depuis le ${autoDateFr(b.current_active_since)}</strong>`
    : '<strong>actuellement non contraignant</strong>';
  const precedent=priorRanges.length
    ? ` · Déjà détecté comme contraignant après le début de la guerre en Iran : ${editorialJoinRanges(priorRanges,true)}`
    : '';
  bi.innerHTML=`■ Plafond TotalEnergies suivi : <b>${autoNumberFr(b.current_cap,2)} €/L TTC</b> · Bouclier ${statut}${precedent}`+
    (carbu==='Gazole'?' <span style="color:rgba(234,88,12,0.8)">· Promotions 2,09 €/L observées par épisodes en mai 2026</span>':'');
  if(lp){
    lp.style.display=carbu==='Gazole'?'flex':'none';
    if(carbu==='Gazole'){
      const txt=lp.childNodes[lp.childNodes.length-1];
      if(txt&&txt.nodeType===Node.TEXT_NODE) txt.textContent=' Promotions Total 2,09 €/L — épisodes de mai 2026';
    }
  }
};

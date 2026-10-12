// Ajustements éditoriaux et de lecture — chargés après automation.js.
// 1) historique disponible explicite dans le sous-titre ;
// 2) texte éditorial coulé et équilibré sur deux colonnes ;
// 3) statut du bouclier distinguant la période actuelle des épisodes antérieurs de 2026 ;
// 4) écart HT journalier apparié strictement par date, sans lissage caché ;
// 5) repères temporels plus denses quand une fenêtre courte est affichée.

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

function editorialHistoricRows(d, e){
  if(Array.isArray(e?.historical_annual) && e.historical_annual.length){
    return e.historical_annual.filter(v=>v.outside_total_action_gap!=null && Number.isFinite(Number(v.outside_total_action_gap)));
  }
  // Fallback during transition, until C1's next metadata publication.
  return [2022,2023,2024,2025].map(year=>({
    year,
    outside_total_action_gap:Number(String(d.tendance['y'+year]).replace(',','.')),
    observed_gap:year===2022?Number(String(d.effet.avec2022).replace(',','.')):null,
    outside_total_action_days:null,
  }));
}

function editorialHistoryText(d, e, fuel){
  const history=editorialHistoricRows(d,e);
  // At least 180 unprotected observations for post-2025 structural comparisons.
  // The 2022-2025 reference is validated independently by the historic regression test.
  const comparable=history.filter(v=>v.year<=2025 || v.outside_total_action_days>=180);
  const exceptional=history.filter(v=>v.year>2025 && v.outside_total_action_days<180);
  if(comparable.length<2) return 'L’historique disponible ne permet pas encore de comparer plusieurs années complètes hors intervention TotalEnergies.';
  const first=comparable[0], last=comparable[comparable.length-1];
  const detail=comparable.map(v=>`<strong>${autoNumberFr(v.outside_total_action_gap,1,true)} c€/L en ${v.year}</strong>`).join(', ');
  const delta=Math.round((last.outside_total_action_gap-first.outside_total_action_gap)*10)/10;
  const evolution=delta>0
    ? `Entre ${first.year} et ${last.year}, <strong>cet écart s'est aggravé de ${autoNumberFr(delta,1)} c€/L</strong>.`
    : delta<0
      ? `Entre ${first.year} et ${last.year}, l'écart s'est réduit de <strong>${autoNumberFr(-delta,1)} c€/L</strong>.`
      : `Entre ${first.year} et ${last.year}, l'écart est demeuré pratiquement stable.`;
  const exceptionalText=exceptional.slice(-2).map(v=>
    `En ${v.year}, l'écart hors action ressort à <strong>${autoNumberFr(v.outside_total_action_gap,1,true)} c€/L</strong>, mais sur seulement ${v.outside_total_action_days} journées : il n'est pas directement comparable aux années disposant d'une couverture plus large.`
  ).join(' ');
  return `Sur les journées sans action tarifaire de TotalEnergies, l'écart moyen HT du ${fuel} entre la Corse et le continent s'établit successivement à ${detail}. ${evolution} L'aggravation constatée entre 2022 et 2025 ne peut être expliquée par la seule insularité : il faut chiffrer l'évolution des coûts de transport, de stockage, de distribution et des marges pour comprendre celle de cet écart. ${exceptionalText}`;
}

function editorialWeeklyText(e){
  const w=e?.weekly_change;
  if(!w || !Number.isFinite(Number(w.latest_gap)) || !Number.isFinite(Number(w.previous_gap))) return '';
  const value=Number(w.change);
  const movement=value>0
    ? `une hausse de <strong>${autoNumberFr(value,1)} c€/L</strong>`
    : value<0
      ? `une baisse de <strong>${autoNumberFr(-value,1)} c€/L</strong>`
      : 'un écart pratiquement inchangé';
  return `Sur la dernière semaine complète (du ${autoDateFr(w.latest_start)} au ${autoDateFr(w.latest_end)}), l'écart moyen HT observé est de <strong>${autoNumberFr(w.latest_gap,1,true)} c€/L</strong>, contre <strong>${autoNumberFr(w.previous_gap,1,true)} c€/L</strong> la semaine précédente : ${movement}. Cette variation hebdomadaire ne suffit pas, à elle seule, à établir une nouvelle tendance de fond.`;
}

buildAnalyse=function(){
  const el=document.getElementById('analyse-content'); if(!el) return;
  const d=ANALYSE[carbu]; if(!d) return;
  const e=DATA?.meta?.editorial?.[carbu];
  const c=carbu.toLowerCase();
  const source='Source : moyennes journalières HT, données publiques prix-carburants.gouv.fr · calculs A4C.';
  const block=(titre,texte,note='')=>`
    <div class="analyse-titre">${titre}</div>
    <p class="analyse-texte">${texte}</p>
    ${note?`<p class="analyse-note">${note}</p>`:''}`;

  const historique=block('1 — UN ÉCART QUI S’EST CREUSÉ AU FIL DES ANNÉES',
    editorialHistoryText(d,e,c));

  if(!e){
    const courant=block('2 — LE BOUCLIER TOTALENERGIES ATTÉNUE L’ÉCART OBSERVÉ, SANS EN EFFACER LES CAUSES',
      `Les remises carburant de 2022 ont coïncidé avec un écart moyen annuel de <strong>${d.effet.avec2022} c€/L</strong>, contre <strong>${d.effet.sans2022} c€/L</strong> sur les seules journées hors action TotalEnergies. Les données de l'année en cours ne sont pas disponibles.`,
      source);
    el.innerHTML=`<div class="analyse-flow">${historique}${courant}</div>`;
    return;
  }

  const through=autoDateFr(e.through);
  const outsideGap=e.outside_total_action_gap ?? e.outside_effective_gap;
  const duringGap=e.during_total_action_gap ?? e.during_effective_gap;
  const ref2022=editorialHistoricRows(d,e).find(v=>v.year===2022);
  const refOutside=ref2022?.outside_total_action_gap ?? Number(String(d.effet.sans2022).replace(',','.'));
  const refObserved=ref2022?.observed_gap ?? Number(String(d.effet.avec2022).replace(',','.'));
  const remises=`En 2022, année des remises carburant de 20 puis 10 c€/L, l'écart moyen annuel observé était de <strong>${autoNumberFr(refObserved,1,true)} c€/L</strong>, contre <strong>${autoNumberFr(refOutside,1,true)} c€/L</strong> sur les seules journées hors action TotalEnergies.`;
  const splitText=outsideGap!=null && duringGap!=null
    ? `Sur les journées sans action TotalEnergies, l'écart moyen atteint <strong>${autoNumberFr(outsideGap,1,true)} c€/L</strong>, contre <strong>${autoNumberFr(duringGap,1,true)} c€/L</strong> pendant les périodes d'action. Ces deux moyennes portent sur des journées différentes : leur écart ne constitue pas une mesure directe de l'effet du bouclier.`
    : outsideGap!=null
      ? `Sur les journées sans action TotalEnergies, l'écart moyen atteint <strong>${autoNumberFr(outsideGap,1,true)} c€/L</strong>.`
      : duringGap!=null
        ? `Toutes les journées observées de l'année relèvent d'une période d'action TotalEnergies.`
        : '';
  const status=e.current_active && e.current_active_since
    ? `Le bouclier ${carbu==='SP95'?'sur le SP95':'sur le gazole'} est actuellement <strong>détecté comme économiquement contraignant depuis le ${autoDateFr(e.current_active_since)}</strong>.`
    : `Au ${through}, le bouclier ${carbu==='SP95'?'sur le SP95':'sur le gazole'} n'est pas détecté comme économiquement contraignant.`;
  const courant=block('2 — LE BOUCLIER TOTALENERGIES ATTÉNUE L’ÉCART OBSERVÉ, SANS EN EFFACER LES CAUSES',
    `${remises} En ${e.year}, jusqu'au ${through}, l'écart moyen HT observé s'établit à <strong>${autoNumberFr(e.observed_ytd_gap,1,true)} c€/L</strong>. ${splitText} ${editorialWeeklyText(e)} ${status} <strong>Une atténuation conjoncturelle de l'écart sous l'effet d'une intervention commerciale ne démontre pas que les mécanismes à l'origine de son aggravation ont disparu.</strong>`,
    `« Hors toute action TotalEnergies » : jours sans intervention active sur le gazole ni sur le SP95. Continent : moyenne à poids égal des douze régions métropolitaines ; stations autoroutières exclues. ${source}`);

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

// ── Écart HT : appariement strict par date/période, sans moyenne mobile cachée ──
// Le graphe supérieur affiche des prix TTC ; le graphe inférieur neutralise les TVA
// (Corse 13 %, continent 20 %). Les deux formes ne sont donc pas censées être identiques.
// En revanche, chaque point d'écart ci-dessous correspond désormais exactement à la même
// date/période dans les deux séries. Une date absente produit null au lieu de décaler la série.
function editorialBuildExactGapDs(){
  const ck=carbu==='Gazole'?'G':'S';
  const corsePts=getSeries(ck,'corse',resolution);
  const labels=resolution==='m'
    ? corsePts.map(p=>p[0])
    : corsePts.map(p=>offsetToDate(p[0]));

  return {labels,datasets:['moy_regions',...REGIONS].map(key=>{
    const regionByPeriod=new Map(getSeries(ck,key,resolution).map(p=>[p[0],p[2]]));
    return {
      label:LABELS[key]||key,
      _key:key,
      data:corsePts.map(p=>{
        const vc=p[2], vr=regionByPeriod.get(p[0]);
        return (vc!=null&&vr!=null)?Math.round((vc-vr)*10000)/100:null;
      }),
      borderColor:COLORS[key]||'#888',
      backgroundColor:(COLORS[key]||'#888')+'18',
      borderWidth:key==='moy_regions'?2:1.2,
      pointRadius:0,
      tension:0.3,
      spanGaps:true,
    };
  })};
}

buildEcartDs=function(){
  const result=editorialBuildExactGapDs();
  return (typeof autoSliceWindow==='function')?autoSliceWindow(result):result;
};

// ── Axe temporel ──────────────────────────────────────────────────────────────
// Sur 12 mois, afficher environ un repère tous les deux mois au lieu du seul 1er janvier.
function editorialTimeTick(val){
  const lbl=this.getLabelForValue(val);
  if(!lbl) return '';
  const narrow=(typeof autoNarrow==='boolean')?autoNarrow:false;
  const monthsWindow=(typeof autoMonthsWindow==='number')?autoMonthsWindow:999;

  if(resolution==='d'){
    const [y,m,d]=lbl.split('-').map(Number);
    if(narrow&&monthsWindow<=18){
      if(d!==1 || m%2===0) return '';
    }else if(narrow&&monthsWindow<=30){
      if(d!==1 || ![1,4,7,10].includes(m)) return '';
    }else if(m!==1 || d!==1){
      return '';
    }
    return MONTHS[m-1]+' '+String(y).slice(2);
  }

  if(resolution==='w'){
    const [y,m,d]=lbl.split('-').map(Number);
    if(narrow&&monthsWindow<=18){
      if(d>7 || m%2===0) return '';
    }else if(narrow&&monthsWindow<=30){
      if(d>7 || ![1,4,7,10].includes(m)) return '';
    }else if(m!==1 || d>7){
      return '';
    }
    return MONTHS[m-1]+' '+String(y).slice(2);
  }

  if(resolution==='m'){
    const [y,m]=lbl.split('-').map(Number);
    if(narrow&&monthsWindow<=18){
      if(m%2===0) return '';
    }else if(!narrow){
      if(![1,7].includes(m)) return '';
    }
    return MONTHS[m-1]+' '+String(y).slice(2);
  }

  return formatLabel(lbl);
}

function editorialApplyChartReadability(){
  [chartPrix,chartEcart].forEach(chart=>{
    const ticks=chart?.options?.scales?.x?.ticks;
    if(!ticks) return;
    ticks.autoSkip=false;
    ticks.callback=editorialTimeTick;
  });
  const gapLabel=document.getElementById('chartEcartLabel');
  if(gapLabel){
    const period=resolution==='d'?'JOURNALIER':resolution==='w'?'HEBDOMADAIRE':'MENSUEL';
    gapLabel.textContent=`${carbu.toUpperCase()} HT — ÉCART ${period} CORSE VS RÉGIONS (C€/L)`;
  }
  if(chartPrix) chartPrix.update('none');
  if(chartEcart) chartEcart.update('none');
}

const _editorialChartBaseInitCharts=initCharts;
initCharts=function(){
  _editorialChartBaseInitCharts();
  editorialApplyChartReadability();
};

const _editorialChartBaseRefresh=refresh;
refresh=function(){
  _editorialChartBaseRefresh();
  editorialApplyChartReadability();
};

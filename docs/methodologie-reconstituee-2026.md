# Méthodologie reconstituée — août 2026

Cette note documente les éléments retrouvés dans les fichiers de travail A4C et les arbitrages retenus pour automatiser `carburantscorse1` sans réécrire son histoire. Les sections ci-dessous distinguent explicitement ce qui relève de l'historique éditorial récupéré et ce qui relève de la règle de détection du bouclier effectif exécutée aujourd'hui.

## Sources de reconstitution

### 1. Dashboard Corse vs régions

Les fichiers `app (2).js` et `index (2).html` fournis en août 2026 confirment notamment :

- `data.json` comme source des séries ;
- Gazole et SP95 ;
- Corse + 12 régions métropolitaines ;
- séries journalières et hebdomadaires ;
- forward-fill historique documenté à 45 jours ;
- zones de remise et de bouclier qui avaient été écrites manuellement dans l'application historique ;
- texte historique 2022–2025 écrit manuellement ;
- prototype de curseur 12 mois → période complète.

Le prototype de curseur était présent mais pas réellement limité au mobile portrait malgré le comportement décrit dans l'échange qui l'accompagnait. L'automatisation corrige ce point.

### 2. Projet méthodologique Corse / Bouches-du-Rhône

Archive : `je-voudrais-te-faire-travailler-sur.zip`.

Le fichier `outputs/actualisation-series-journalieres/README_REPRISE_ACTUALISATION_2026.md`, sauvegardé le 14 juin 2026, documente un pipeline distinct :

1. extraction des ZIP annuels officiels ;
2. dernier relevé station + carburant + jour ;
3. forward-fill journalier ;
4. prix suspect si < 1,10 €/L ou > 3,00 €/L ;
5. aucune correction automatique ;
6. exclusion des prix suspects et des lignes trop anciennes dans les moyennes fiables ;
7. enrichissement des stations par enseigne.

Ce pipeline utilisait des seuils de fraîcheur différents :

- Bouches-du-Rhône Gazole/E10 : 30 jours ;
- Bouches-du-Rhône SP95 : 21 jours ;
- Corse : 90 jours ;
- station inactive : 60 jours en BdR, 180 jours en Corse.

Ces seuils appartiennent au projet Corse-vs-BdR. Ils ne remplacent pas le forward-fill 45 jours du dashboard Corse-vs-régions.

## Six relevés aberrants corses retrouvés

Le fichier `outputs/nettoyage-originaux/prix_aberrants_a_revoir.csv` permet d'identifier les six relevés historiques mentionnés dans le README de `carburantscorse1` :

| station | carburant | date | prix suspect | précédent | suivant |
|---|---|---|---:|---:|---:|
| 20137006 | SP95 | 2022-02-07 | 0,900 | 1,870 | 1,935 |
| 20137010 | SP95 | 2023-05-23 | 0,940 | 1,930 | 1,940 |
| 20137010 | SP95 | 2023-07-13 | 0,980 | 1,990 | 1,990 |
| 20145001 | Gazole | 2023-05-04 | 0,790 | 1,810 | 1,175 |
| 20169002 | Gazole | 2022-01-21 | 0,725 | 1,710 | 1,758 |
| 20600011 | Gazole | 2022-06-03 | 1,070 | 2,050 | 2,120 |

L'historique public reste figé. Prospectivement, le générateur applique la règle générale 1,10–3,00 €/L sans inventer de valeur corrigée.

## Enseignes et identité temporelle

Le registre des enseignes est alimenté par les pages officielles de station. Une enseigne associée à un ID ne doit pas être considérée comme éternelle : un même ID peut changer d'exploitation ou d'enseigne.

La politique retenue à partir de septembre 2026 est donc temporelle :

- les IDs nouveaux, non résolus ou qui réapparaissent sont revérifiés immédiatement ;
- les IDs actifs déjà résolus sont revérifiés progressivement, au plus tard selon une cible de 90 jours, avec un nombre de requêtes borné par passage ;
- un changement détecté prend effet à sa date de vérification ;
- l'identité antérieure est conservée dans l'historique du registre avec sa période de validité ;
- aucune série de prix déjà publiée n'est reclassée rétroactivement par cette maintenance.

Le référentiel TotalEnergies conserve en parallèle des alias historiques configurés pour la continuité des calculs. Ces alias sont des choix de configuration documentés ; ils ne doivent pas être interprétés comme une nouvelle preuve indépendante de l'identité physique de stations anciennes.

## Bouclier : deux calendriers à ne pas confondre

### 1. Calendrier éditorial historique

Les fenêtres historiques récupérées dans l'ancienne application sont conservées uniquement pour reproduire l'indicateur **« hors toute action TotalEnergies »**. Elles sont codées dans `LEGACY_RANGES` et servent au découpage éditorial des jours avec/sans action TotalEnergies.

Elles ne déterminent pas les zones jaunes du **bouclier effectif**.

### 2. Bouclier effectif : règle autoritative

`scripts/bouclier_detector.py` porte une seule règle autoritative pour C1 et C2. Un jour brut est actif si :

1. le plafond applicable est connu ;
2. au moins **une** station TotalEnergies active se situe entre **0,2 c€/L sous le plafond et 0,1 c€/L au-dessus** ;
3. le **75e percentile** des stations corses non-Total est au niveau ou au-dessus du plafond.

Stabilisation :

- une période n'est confirmée qu'après **2 jours bruts actifs consécutifs**, mais commence rétroactivement au premier de ces deux jours ;
- une fois les portions confirmées, **un seul jour inactif isolé** peut être comblé entre deux portions actives ;
- une journée active isolée ne suffit jamais à créer une période, et deux journées isolées séparées par un jour ne sont pas fusionnées artificiellement.

Les plages effectives **2023–2025** ont été recalculées une fois avec cette règle exacte à partir des stocks officiels puis gelées pour la reproductibilité (`HISTORICAL_RULE_RANGES`, gel au 31 décembre 2025). Elles sont :

**Gazole**

- 12 septembre 2023 → 2 novembre 2023.

**SP95**

- 8 mars 2023 → 17 mars 2023 ;
- 30 mars 2023 → 30 avril 2023 ;
- 26 juillet 2023 → 10 octobre 2023 ;
- 20 mars 2024 → 27 mai 2024.

À partir de **2026**, la même règle est recalculée dynamiquement depuis le stock officiel. Il n'existe donc plus de règle publique distincte de type « 20 % des stations à moins de 1,5 c€/L » : cette formulation était devenue obsolète par rapport au détecteur réellement exécuté.

Les paramètres de la règle — tolérances, population minimale, percentile, confirmation et comblement — sont publiés dans `data.json` et l'interface les lit pour produire ses libellés.

## Chronologie des plafonds

La chronologie formelle utilisée par `carburantscorse1` est :

- **SP95** : 1,99 €/L à partir du 1er mars 2023 ;
- **Gazole** : 1,99 €/L du 1er mars 2023 au 19 mars 2026 ; 2,09 €/L du 20 mars au 7 avril 2026 ; 2,25 €/L à partir du 8 avril 2026.

Le projet Corse-vs-BdR sauvegardé le 14 juin 2026 contenait des dates de transition légèrement différentes. Cette divergence reste documentée comme provenance historique mais n'est pas utilisée pour réécrire les courbes.

## Promotions gazole mai 2026

`app (2).js` contenait les épisodes :

- 30 avril–3 mai ;
- 8–10 mai ;
- 14–17 mai ;
- 23–25 mai.

Le projet méthodologique documente en plus 29–31 mai. Les prix station par station du ZIP montrent effectivement une concentration massive à 2,09 € les 30–31 mai. Cet épisode est conservé dans l'affichage promotionnel ; il est distinct du calendrier de détection du bouclier effectif.

## Référence Rotterdam UFIP

C1 possède le téléchargement unique de la série Rotterdam partagée avec C2. La source publique UFIP / Énergies et Mobilités décrit cette série comme des **cotations Rotterdam en EUR/litre, source Thomson-Reuters, moyennes mobiles sur 5 jours**.

Le contrat automatisé vérifie désormais ces trois propriétés avant d'accepter l'export. Les valeurs doivent aussi être finies et plausibles pour une série en EUR/litre. Le manifeste partagé publie explicitement :

- unité : `EUR/L` ;
- source de référence : `Thomson-Reuters` ;
- lissage : `5-day moving average` ;
- nom de la colonne : `rotterdam_eur_l` ;
- SHA-256 des actifs observés et journaliers.

Aucune conversion tonne/litre n'est effectuée. Le fichier journalier est obtenu en prolongeant la dernière cotation observée sur les jours sans observation (week-ends/jours fériés) ; cela ne transforme pas la cotation source en une autre moyenne.

Le retry UFIP compare le contenu date/valeur de la semaine précédente : il relance la chaîne aussi bien lorsqu'une semaine incomplète devient complète que lorsqu'une valeur d'une semaine déjà complète est corrigée à date inchangée.

## Politique d'automatisation retenue

- historique public des prix : immuable ;
- nouvelles données : append-only ;
- anomalies futures : exclusion, jamais correction inventée ;
- calendrier éditorial historique : conservé pour reproduire l'indicateur historique ;
- bouclier effectif : règle unique ci-dessus, historique 2023–2025 recalculé une fois puis gelé, 2026+ dynamique ;
- enseignes : validité temporelle, revérification ciblée et bornée ;
- référence UFIP : contrat explicite unité/source/lissage ;
- texte courant : uniquement grandeurs reproductibles et paramètres issus des métadonnées validées ;
- curseur : 12 mois par défaut seulement sur mobile portrait ; période complète sur ordinateur et paysage ;
- mise à jour principale : lundi 07:07 Europe/Paris, avec rattrapages et vérification métier jusqu'à Pages.

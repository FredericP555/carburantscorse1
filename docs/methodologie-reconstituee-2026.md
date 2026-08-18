# Méthodologie reconstituée — août 2026

Cette note documente les éléments retrouvés dans les fichiers de travail A4C et les arbitrages retenus pour automatiser `carburantscorse1` sans réécrire son histoire.

## Sources de reconstitution

### 1. Dashboard Corse vs régions

Les fichiers `app (2).js` et `index (2).html` fournis en août 2026 confirment notamment :

- `data.json` comme source des séries ;
- Gazole et SP95 ;
- Corse + 12 régions métropolitaines ;
- séries journalières et hebdomadaires ;
- forward-fill historique documenté à 45 jours dans le README du dépôt ;
- zones historiques de remise et de bouclier écrites manuellement dans `BOUCLIER` ;
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

## Référentiel TotalEnergies Corse

Le référentiel retrouvé contient 47 stations TotalEnergies actuelles.

Deux identifiants historiques sont rattachés à la station actuelle de Folelli :

- `20213003` → `20213007` ;
- `20213006` → `20213007`.

C'est pourquoi certaines séries historiques contiennent 49 identifiants Total alors que le parc actuel de référence en compte 47.

## Bouclier : ce qui est certain et ce qui ne l'est pas

### Zones historiques de `carburantscorse1`

Elles sont conservées telles qu'elles étaient publiées :

**Gazole**

- 2023-08-31 → 2023-10-13 ;
- 2023-10-24 → 2023-10-30 ;
- 2026-03-20 → 2026-04-06 ;
- 2026-04-08 → 2026-05-27.

**SP95**

- 2023-02-20 → 2023-03-19 ;
- 2023-03-27 → 2023-05-02 ;
- 2023-06-09 → 2023-06-21 ;
- 2023-07-25 → 2023-10-07 ;
- 2024-02-20 → 2024-03-01 ;
- 2024-03-07 → 2024-06-05 ;
- 2024-07-01 → 2024-07-16 ;
- 2026-03-13 → 2026-05-28.

L'étude du ZIP montre qu'un simple seuil de part de stations Total au plafond ne reproduit pas ces intervalles. Par exemple, en octobre 2023 plusieurs dizaines de pourcents des stations gazole restent à 1,99 € pendant un intervalle que le dashboard avait volontairement laissé sans zone jaune.

Conclusion : les zones historiques résultaient d'une appréciation du **caractère contraignant**, et non de la seule présence d'un prix de 1,99 €.

### Règle prospective

À compter du 29 mai 2026, l'automatisation utilise deux signaux :

1. au moins 20 % des Total actives sont à moins de 1,5 c€/L du plafond ;
2. le 75e percentile des stations corses non-Total est au niveau ou au-dessus du plafond.

La première condition mesure la concentration au plafond. La seconde fournit un signal indépendant de pression de marché. Un plafond n'est donc pas déclaré contraignant uniquement parce que des stations Total conservent un prix rond.

Stabilisation : trous <= 4 jours comblés lorsqu'ils sont encadrés ; épisodes < 5 jours ignorés.

## Chronologie des plafonds : divergence retrouvée

Les deux sources de travail ne donnent pas exactement les mêmes dates de transition pour le gazole 2026 :

- la dernière version fournie de `app (2).js` indique 1,99 € jusqu'au 19 mars, 2,09 € du 20 mars au 7 avril, 2,25 € à partir du 8 avril ;
- le projet Corse-vs-BdR sauvegardé le 14 juin utilise 2,09 € à partir du 13 mars et 2,25 € à partir du 7 avril.

L'automatisation de `carburantscorse1` suit la chronologie de sa dernière application fournie et **ne modifie pas les zones historiques**. La divergence est conservée ici pour éviter qu'elle ne soit oubliée.

## Promotions gazole mai 2026

`app (2).js` contenait les épisodes :

- 30 avril–3 mai ;
- 8–10 mai ;
- 14–17 mai ;
- 23–25 mai.

Le projet méthodologique documente en plus 29–31 mai. Les prix station par station du ZIP montrent effectivement une concentration massive à 2,09 € les 30–31 mai. Cet épisode est donc ajouté à l'affichage historique sans supprimer les épisodes déjà publiés.

## Politique d'automatisation retenue

- historique public : immuable ;
- nouvelles données : append-only ;
- anomalies futures : exclusion, jamais correction inventée ;
- bouclier historique : figé ;
- bouclier futur : règle économique à deux signaux ;
- texte courant : uniquement grandeurs reproductibles ;
- curseur : 12 mois par défaut seulement sur mobile portrait ; période complète sur ordinateur et paysage ;
- mise à jour : lundi 07:00 Europe/Paris, avec contrôles avant publication.

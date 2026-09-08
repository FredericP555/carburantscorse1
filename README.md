# Observatoire Prix Carburants Corse

Dashboard interactif comparant les prix des carburants en Corse aux régions métropolitaines françaises depuis janvier 2022.

**→ [carburantscorse.fr](https://carburantscorse.fr)**

## Structure

```text
index.html                          Structure HTML + CSS
app.js                              Application historique (Chart.js)
automation.js                       Dates, fenêtre mobile, bouclier et analyse courante
chart.min.js                        Bibliothèque Chart.js 4.4.1
data.json                           Séries pré-calculées + métadonnées dynamiques
config/total_corse_stations.json    Référentiel TotalEnergies Corse + alias historiques
scripts/                            Génération, détection et contrôles
.github/workflows/update-weekly.yml Mise à jour hebdomadaire
```

## Données et méthode

- **Source** : prix-carburants.gouv.fr, stock annuel officiel XML.
- **Périmètre** : Corse + 12 régions métropolitaines.
- **Carburants** : Gazole et SP95.
- **Prix affichés** : TTC pour le graphe de prix ; HT pour l'écart Corse–continent afin de neutraliser la différence de TVA (13 % en Corse, 20 % sur le continent).
- **Stations autoroutières** : exclues.
- **Prix journalier** : dernier prix déclaré par station pour la journée, puis forward-fill limité à **45 jours**. Ce seuil est celui du dashboard Corse-vs-régions publié ; le projet méthodologique Corse-vs-BdR retrouvé en juin 2026 utilisait des seuils territoriaux différents et n'est pas substitué silencieusement à cette série.
- **Prix suspects** : à partir de l'automatisation prospective, toute déclaration < **1,10 €/L** ou > **3,00 €/L** est considérée non fiable et exclut temporairement la station des moyennes jusqu'à une nouvelle déclaration valide. Aucun prix n'est corrigé automatiquement.
- **Agrégations** : les séries hebdomadaires et mensuelles sont calculées à partir du journalier.
- **Historique publié** : les valeurs déjà publiées jusqu'au 28 mai 2026 sont figées, y compris le traitement historique des **six relevés aberrants corses** documentés dans le projet A4C retrouvé. L'automatisation est ensuite **append-only** : elle ajoute de nouveaux jours sans réécrire rétroactivement les courbes publiques si le stock officiel est corrigé ultérieurement.

Des contrôles automatiques bloquent la publication en cas de rupture structurelle, incohérence TTC/HT, couverture anormale du référentiel TotalEnergies, population de stations anormale ou variation journalière régionale manifestement anormale.

## Audit hebdomadaire des stations corses

Avant toute publication, `scripts/station_audit.py` reconstruit l'état de chaque **série station-carburant** corse à la date du dernier jour disponible. Une même station physique peut donc apparaître dans l'audit Gazole et dans l'audit SP95.

Après exclusion en amont des stations `pop=A`, chaque série est classée dans une seule catégorie :

- **retenue** : dernier prix valide âgé d'au plus 45 jours ;
- **trop ancienne** : dernière déclaration âgée de plus de 45 jours ;
- **dernier prix invalide** : dernière déclaration récente mais hors de la plage 1,10–3,00 €/L ; la station reste exclue jusqu'à une déclaration valide ultérieure ;
- **sans état antérieur exploitable** : cas de sécurité prévu par le code, qui doit normalement rester à zéro.

Les comptes doivent se réconcilier exactement : `connues = retenues + trop anciennes + invalides + sans état`. Les identifiants des séries exclues, la date de leur dernière déclaration et son ancienneté sont conservés dans `data.json > meta > station_audit` et apparaissent dans le résumé GitHub Actions.

Premier audit vérifié au **17 août 2026** :

- Gazole : **125** séries connues dans les stocks N-1/N, **123** ayant déclaré en 2026, **121 retenues**, **4 trop anciennes**, **0 dernier prix invalide** ;
- SP95 : **125** séries connues, **123** ayant déclaré en 2026, **106 retenues**, **19 trop anciennes**, **0 dernier prix invalide**.

Une série « trop ancienne » n'est pas qualifiée automatiquement de station fermée : elle est simplement exclue de la moyenne tant qu'aucune nouvelle déclaration récente n'est disponible.

La publication est bloquée si :

- moins de **80** séries Gazole ou **60** séries SP95 restent retenues ;
- la population retenue chute de plus de **20 %** par rapport au dernier audit publié ;
- plus de **5 %** des séries ont comme dernier état un prix invalide ;
- le décompte ne se réconcilie pas ;
- le nombre retenu ne correspond pas au calcul indépendant du détecteur de bouclier (`stations Total + stations non-Total`).

Tant qu'aucun audit précédent n'est encore stocké dans `data.json`, la population vérifiée du 17 août 2026 (**121 Gazole / 106 SP95**) sert de référence de démarrage pour le garde-fou de baisse de 20 %.

## Référentiel des enseignes corses

Le stock prix-carburants.gouv.fr ne porte pas directement l'enseigne dans les déclarations de prix utilisées par le générateur. Le registre `config/corse_station_brands.json` est donc enrichi depuis la fiche officielle de chaque station.

Les IDs nouveaux, non résolus ou qui réapparaissent sont vérifiés immédiatement. Les IDs actifs déjà résolus sont ensuite **revérifiés progressivement**, par ancienneté de vérification, avec une politique bornée à **90 jours** et **12 revérifications par passage**. Un changement d'enseigne détecté ne réécrit pas l'histoire : l'ancienne identité est conservée avec sa période de validité et la nouvelle ne devient applicable qu'à la date de sa vérification.

Le fichier `config/total_corse_stations.json` conserve par ailleurs le référentiel TotalEnergies et ses alias historiques utilisés par le détecteur. Les alias sont une configuration historique explicite ; leur présence ne constitue pas à elle seule une nouvelle démonstration d'identité physique entre anciens et nouveaux IDs.

## Bouclier TotalEnergies effectif

Le graphique distingue le plafond commercial annoncé de son **effet économique observable**. Une seule règle de détection est désormais autoritative dans `scripts/bouclier_detector.py` et ses paramètres sont publiés dans `data.json > meta > bouclier > <carburant> > rule`.

Un jour brut est actif lorsque :

- au moins **une station TotalEnergies active** est dans la bande du plafond, soit de **0,2 c€/L sous le plafond à 0,1 c€/L au-dessus** ;
- le **75e percentile des stations corses non-Total** est au niveau ou au-dessus du plafond.

Une période est confirmée après **2 jours bruts actifs consécutifs**, avec effet rétroactif au premier de ces deux jours. Après confirmation, **un seul jour inactif isolé** peut être comblé entre deux portions confirmées. Deux journées actives isolées séparées par un jour ne suffisent donc pas à créer artificiellement une période.

Les plages **effectives** 2023–2025 ont été recalculées une fois avec cette règle unique et sont gelées pour la reproductibilité ; à partir de 2026, la même règle est recalculée dynamiquement sur le stock officiel. Cela est distinct du calendrier historique d'**actions TotalEnergies** utilisé uniquement pour reproduire l'indicateur éditorial « hors toute action TotalEnergies ».

Les montants des plafonds restent une configuration explicite dans `scripts/bouclier_detector.py`. Pour le Gazole : 1,99 €/L jusqu'au 19 mars 2026, 2,09 €/L du 20 mars au 7 avril, puis 2,25 €/L à partir du 8 avril ; pour le SP95, le plafond suivi est 1,99 €/L à partir du 1er mars 2023.

L'interface lit les tolérances, populations et règles directement dans les métadonnées validées au lieu de conserver un seuil éditorial codé séparément.

## Fenêtre temporelle

Le mécanisme de curseur récupéré dans les fichiers `app (2).js` / `index (2).html` a été corrigé pour correspondre au comportement attendu :

- **mobile portrait** : 12 derniers mois par défaut, curseur de 12 mois jusqu'à toute la période ;
- **mobile paysage et ordinateur** : toute la période, curseur masqué ;
- la borne maximale et le libellé `Toute la période (2022–…)` sont calculés automatiquement à partir de `data.json`.

## Analyse éditoriale automatisée

La méthode historique de l'indicateur **« hors toute action TotalEnergies »** a été reconstituée exactement.

Pour chaque jour, l'écart est calculé en HT entre la moyenne Corse et la **moyenne à poids égal des 12 moyennes régionales**. Puis les jours sont séparés en deux catégories :

- **pendant action TotalEnergies** : une intervention Total est active sur **au moins un des deux carburants**, Gazole ou SP95 ;
- **hors toute action TotalEnergies** : aucune intervention Total n'est active ce jour-là, ni sur le Gazole ni sur le SP95.

Le calendrier éditorial est donc l'**union des périodes d'action Gazole et SP95**, et il est identique pour l'analyse des deux carburants. Il est volontairement distinct du calendrier de détection du bouclier effectif décrit ci-dessus.

La règle retrouvée reproduit au dixième près tous les chiffres historiques codés dans le dashboard :

- Gazole hors toute action : **15,3 (2022), 17,3 (2023), 18,1 (2024), 18,3 (2025)** ;
- SP95 hors toute action : **14,2 (2022), 14,3 (2023), 17,2 (2024), 17,3 (2025)** ;
- bilan jusqu'au 28 mai 2026 : Gazole **17,2 hors / 13,1 pendant**, SP95 **16,0 hors / 10,2 pendant** ;
- début 2026 avant la première action commune (1er janvier–12 mars) : Gazole **15,3**, SP95 **16,4**.

Ces chiffres sont des **moyennes de jours observés**, pas un contrefactuel où l'on reconstruirait artificiellement ce qu'aurait été le prix sans TotalEnergies.

Pour l'année en cours, `data.json` stocke automatiquement :

- écart HT moyen observé depuis le 1er janvier ;
- écart HT moyen hors toute action TotalEnergies ;
- écart HT moyen pendant les actions TotalEnergies ;
- calendrier commun des périodes utilisé pour ce découpage ;
- statut courant du bouclier du carburant affiché, plafond, population Total/non-Total, part des Total dans la bande du plafond et 75e percentile des stations corses non-Total.

Un test de régression (`scripts/validate_editorial_history.py`) recalcule les chiffres historiques avant chaque validation de l'automatisation. Si la méthode dérive, le workflow échoue au lieu de publier silencieusement un autre indicateur sous le même nom.

## Référence Rotterdam UFIP partagée avec C2

C1 possède le téléchargement unique de la référence Rotterdam utilisée ensuite par C2. Le contrat accepté est explicite : **cotations Rotterdam Gazole en EUR/litre, source Thomson-Reuters, moyennes mobiles sur 5 jours**, telles qu'annoncées sur la page publique UFIP / Énergies et Mobilités. Aucune conversion tonne/litre n'est réalisée par A4C.

Le téléchargement est refusé si la page source n'annonce plus cette unité, cette source ou ce lissage, ou si les valeurs exportées sont non finies ou économiquement incompatibles avec une série en EUR/litre. Le manifeste C1→C2 publie l'unité, la source, le lissage et les SHA-256 des actifs.

Le retry UFIP compare désormais le **contenu date/valeur** de la semaine précédente avec la dernière source disponible : il relance C1 aussi bien lorsqu'une semaine incomplète devient complète que lorsqu'une cotation d'une semaine déjà complète est corrigée à date inchangée.

## Mise à jour hebdomadaire

Le workflow `update-weekly.yml` vise chaque **lundi à 07:07 heure de Paris**, été comme hiver. Des watchdogs indépendants assurent le rattrapage si le déclenchement planifié est retardé ou absent.

La chaîne sélectionnée :

1. télécharge les stocks annuels officiels ;
2. vérifie la source UFIP et récupère une fois la référence Rotterdam ;
3. met à jour de façon bornée le registre des enseignes ;
4. construit le candidat V2 sans réécrire le préfixe historique protégé ;
5. valide les séries, métadonnées, populations, bouclier et audit stations ;
6. construit et valide le bundle C1→C2 ;
7. ne promeut que le candidat conforme ;
8. commit les changements réels, publie la release partagée et demande la reconstruction Pages si nécessaire ;
9. un vérificateur métier indépendant exige ensuite la cohérence entre `main`, la release et le `data.json` réellement servi par Pages.

S'il n'y a aucun nouveau jour officiel, le prix peut rester un **no-op** ; une nouvelle release reste néanmoins pertinente si un actif partagé tel qu'UFIP ou le registre a changé. Le succès métier est vérifié séparément de la simple conclusion technique du workflow.

## Crédits

Calculs et analyse : [carburantscorse.fr](https://carburantscorse.fr) · Initiative A4C.

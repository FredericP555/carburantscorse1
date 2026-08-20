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
- **Prix journalier** : dernier prix déclaré par station pour la journée. Le seuil de **45 jours** porte désormais sur l'**activité de la station**, définie par une déclaration Gazole/SP95 ou un événement de rupture. Tant que la station reste active, le dernier prix valide de chaque carburant reste utilisable même si ce carburant lui-même n'a pas changé depuis plus de 45 jours. Une rupture active du carburant l'exclut jusqu'à sa fin.
- **Prix suspects** : à partir de l'automatisation prospective, toute déclaration < **1,10 €/L** ou > **3,00 €/L** est considérée non fiable et exclut temporairement le carburant de la station des moyennes jusqu'à une nouvelle déclaration valide. Aucun prix n'est corrigé automatiquement.
- **Agrégations** : les séries hebdomadaires et mensuelles sont calculées à partir du journalier.
- **Historique publié** : les valeurs déjà publiées jusqu'au 28 mai 2026 sont figées, y compris le traitement historique des **six relevés aberrants corses** documentés dans le projet A4C retrouvé. L'automatisation est ensuite **append-only** : elle ajoute de nouveaux jours sans réécrire rétroactivement les courbes publiques si le stock officiel est corrigé ultérieurement.

Des contrôles automatiques bloquent la publication en cas de rupture structurelle, incohérence TTC/HT, couverture anormale du référentiel TotalEnergies, population de stations anormale ou variation journalière régionale manifestement anormale.

## Audit hebdomadaire des stations corses

Avant toute publication, `scripts/station_audit.py` reconstruit l'état de chaque **série station-carburant** corse à la date du dernier jour disponible et distingue l'ancienneté du prix de l'activité de la station.

Après exclusion en amont des stations `pop=A`, chaque série est classée dans une seule catégorie :

- **retenue** : dernier prix valide, station encore active et aucune rupture active du carburant ;
- **station inactive** : aucune déclaration Gazole/SP95 ni événement de rupture depuis plus de 45 jours ;
- **rupture active** : le carburant est déclaré en rupture à la fin du jour considéré ;
- **dernier prix invalide** : dernière déclaration hors de la plage 1,10–3,00 €/L ; le carburant reste exclu jusqu'à une déclaration valide ultérieure ;
- **sans état antérieur exploitable** : cas de sécurité prévu par le code, qui doit normalement rester à zéro.

L'audit conserve en plus la liste des cas **« prix ancien / station active »** : le prix du carburant a plus de 45 jours mais reste retenu parce que la station continue à déclarer un autre état récent. Cette catégorie permet notamment de surveiller les SP95 durablement inchangés au plafond commercial.

Les comptes doivent se réconcilier exactement : `connues = retenues + stations inactives + ruptures actives + invalides + sans état`. Les identifiants, dates de dernier prix et dates de dernière activité sont conservés dans `data.json > meta > station_audit` et apparaissent dans le résumé GitHub Actions.

Premier audit vérifié avec l'ancienne règle au **17 août 2026** :

- Gazole : **125** séries connues dans les stocks N-1/N, **123** ayant déclaré en 2026, **121 retenues**, **4 trop anciennes**, **0 dernier prix invalide** ;
- SP95 : **125** séries connues, **123** ayant déclaré en 2026, **106 retenues**, **19 trop anciennes**, **0 dernier prix invalide**.

Le contrôle effectué le **20 août 2026** sur le stock officiel arrêté au 19 août a montré que la règle par ancienneté propre au carburant écartait **15 SP95 de stations pourtant actives**, dont **12 TotalEnergies**. Avec la règle d'activité de station, **121 SP95** sont retenus au 19 août, contre 106 avec l'ancienne règle.

La publication est bloquée si :

- moins de **80** séries Gazole ou **60** séries SP95 restent retenues ;
- la population retenue chute de plus de **20 %** par rapport au dernier audit publié ;
- plus de **5 %** des séries ont comme dernier état un prix invalide ;
- le décompte ne se réconcilie pas ;
- le nombre retenu ne correspond pas au calcul indépendant du détecteur de bouclier (`stations Total + stations non-Total`).

Tant qu'aucun audit précédent compatible n'est encore stocké dans `data.json`, la population vérifiée du 17 août 2026 (**121 Gazole / 106 SP95**) reste un garde-fou historique de baisse ; une hausse liée au changement de méthode n'est pas bloquée.

## Référentiel TotalEnergies

Le fichier Open Data ne fournit pas l'enseigne. Le référentiel récupéré dans le projet méthodologique A4C contient **47 stations TotalEnergies actuelles** en Corse. Deux anciens identifiants de Folelli (`20213003` et `20213006`) sont conservés comme alias historiques de `20213007`.

## Bouclier TotalEnergies effectif

Le graphique distingue le plafond commercial annoncé de son **effet économique observable**.

Les périodes jusqu'au 31 décembre 2025 ont été recalculées puis figées pour assurer la reproductibilité historique. À partir de 2026, la même règle est recalculée dynamiquement depuis le stock annuel officiel.

Un jour est considéré comme brut « bouclier effectif » lorsque les deux conditions suivantes sont réunies :

- au moins **une station TotalEnergies active** est effectivement au plafond, avec une tolérance de **0,2 c€/L sous le plafond à 0,1 c€/L au-dessus** ;
- le **75e percentile des stations corses non-Total** est au niveau ou au-dessus du plafond, ce qui indique une pression de marché compatible avec un plafond réellement contraignant.

Les stations utilisées par ce détecteur suivent exactement la même règle d'activité que la moyenne du dashboard : activité de station sur 45 jours, maintien possible d'un prix inchangé plus ancien, exclusion d'un dernier prix invalide et exclusion pendant une rupture active.

Une période n'est confirmée qu'après **2 jours bruts consécutifs**, avec effet rétroactif au premier jour. Une seule journée inactive peut ensuite être comblée entre deux portions confirmées. Deux jours isolés séparés par une journée inactive ne peuvent donc pas créer artificiellement une période.

Les montants des plafonds restent une configuration explicite dans `scripts/bouclier_detector.py`. Le calendrier éditorial historique « pendant/hors action TotalEnergies » reste distinct du dessin des zones de bouclier effectif.

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

Le calendrier éditorial est donc l'**union des périodes d'action Gazole et SP95**, et il est identique pour l'analyse des deux carburants. Ce point explique notamment le chiffre Gazole 2023 : retirer uniquement les périodes Gazole donne environ **17,0 c€/L**, alors que retirer l'union Gazole + SP95 redonne le chiffre historique **17,3 c€/L**.

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
- statut courant du bouclier du carburant affiché, plafond, proportion de Total proches du plafond et 75e percentile des stations corses non-Total.

Un test de régression (`scripts/validate_editorial_history.py`) recalcule les chiffres historiques avant chaque validation de l'automatisation. Si la méthode dérive, le workflow échoue au lieu de publier silencieusement un autre indicateur sous le même nom.

## Mise à jour hebdomadaire

Le workflow `update-weekly.yml` s'exécute chaque **lundi à 07:00 heure de Paris**, été comme hiver :

1. téléchargement du stock annuel officiel ;
2. ajout des seuls jours nouveaux à `data.json` ;
3. audit des séries station-carburant corses et application des garde-fous de population ;
4. contrôles de cohérence des séries candidates ;
5. détection prospective du bouclier effectif ;
6. recalcul des indicateurs éditoriaux selon le calendrier commun d'actions TotalEnergies ;
7. validation croisée des métadonnées et populations de stations ;
8. production du résumé hebdomadaire par le même script que celui testé dans la PR ;
9. commit automatique de `data.json` si les données ont réellement avancé ;
10. demande explicite de reconstruction de GitHub Pages.

S'il n'y a aucun nouveau jour officiel, l'exécution est un **no-op** : aucun commit inutile et aucune fausse date de mise à jour.

## Crédits

Calculs et analyse : [carburantscorse.fr](https://carburantscorse.fr) · Initiative A4C.

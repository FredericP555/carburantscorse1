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

Des contrôles automatiques bloquent la publication en cas de rupture structurelle, incohérence TTC/HT, couverture anormale du référentiel TotalEnergies ou variation journalière régionale manifestement anormale.

## Référentiel TotalEnergies

Le fichier Open Data ne fournit pas l'enseigne. Le référentiel récupéré dans le projet méthodologique A4C contient **47 stations TotalEnergies actuelles** en Corse. Deux anciens identifiants de Folelli (`20213003` et `20213006`) sont conservés comme alias historiques de `20213007`.

## Bouclier TotalEnergies effectif

Le graphique distingue le plafond commercial annoncé de son **effet économique observable**.

Les anciennes zones jaunes déjà publiées restent figées. Les fichiers de travail retrouvés montrent qu'elles ne peuvent pas être reproduites fidèlement par un seul seuil mécanique ; elles ne sont donc pas réécrites a posteriori.

À partir du **29 mai 2026**, une nouvelle zone n'est ajoutée que si deux signaux indépendants sont réunis :

- au moins **20 %** des stations TotalEnergies actives sont à moins de **1,5 c€/L** du plafond ;
- le **75e percentile des stations corses non-Total** est au niveau ou au-dessus du plafond, ce qui indique que le reste du marché exerce effectivement une pression compatible avec un plafond contraignant.

Pour éviter le clignotement quotidien, les interruptions de 4 jours ou moins peuvent être comblées et les épisodes isolés de moins de 5 jours sont écartés.

Cette règle prospective évite de confondre deux situations : « beaucoup de Total affichent encore 1,99 € » et « 1,99 € limite réellement leurs prix alors que le marché autour pousserait plus haut ».

Les montants des plafonds restent une configuration explicite dans `scripts/bouclier_detector.py`. La chronologie formelle retenue est celle de la dernière version de `app.js` fournie pour `carburantscorse1`. Le projet Corse-vs-BdR sauvegardé le 14 juin 2026 comporte des dates de transition légèrement différentes ; cette divergence est documentée et n'est pas utilisée pour modifier rétroactivement les zones historiques.

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
3. contrôles de cohérence et de couverture ;
4. détection prospective du bouclier effectif ;
5. recalcul des indicateurs éditoriaux selon le calendrier commun d'actions TotalEnergies ;
6. production d'un résumé lisible dans GitHub Actions ;
7. commit automatique de `data.json` si les données ont réellement avancé ;
8. demande explicite de reconstruction de GitHub Pages.

S'il n'y a aucun nouveau jour officiel, l'exécution est un **no-op** : aucun commit inutile et aucune fausse date de mise à jour.

## Crédits

Calculs et analyse : [carburantscorse.fr](https://carburantscorse.fr) · Initiative A4C.

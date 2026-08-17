# Observatoire Prix Carburants Corse

Dashboard interactif comparant les prix des carburants en Corse aux régions métropolitaines françaises depuis janvier 2022.

**→ [carburantscorse.fr](https://carburantscorse.fr)**

## Structure

```text
index.html                          Structure HTML + CSS
app.js                              Application historique (Chart.js)
automation.js                       Couche dynamique : dates, bouclier, analyse courante
chart.min.js                        Bibliothèque Chart.js 4.4.1
data.json                           Séries pré-calculées + métadonnées dynamiques
config/total_corse_stations.json    Référentiel des stations TotalEnergies corses
scripts/                            Génération, détection et contrôles
.github/workflows/update-weekly.yml Mise à jour hebdomadaire
```

## Données et méthode

- **Source** : prix-carburants.gouv.fr, stock annuel officiel XML.
- **Périmètre** : Corse + 12 régions métropolitaines.
- **Carburants** : Gazole et SP95.
- **Prix affichés** : TTC pour le graphe de prix ; HT pour l'écart Corse–continent afin de neutraliser la différence de TVA (13 % en Corse, 20 % sur le continent).
- **Stations autoroutières** : exclues.
- **Prix journalier** : dernier prix déclaré par station pour la journée, puis forward-fill limité à 45 jours.
- **Agrégations** : les séries hebdomadaires et mensuelles sont calculées à partir du journalier.
- **Historique publié** : les valeurs déjà publiées jusqu'au 28 mai 2026 sont figées, y compris le traitement historique des six relevés aberrants neutralisés. L'automatisation est ensuite **append-only** : elle ajoute de nouveaux jours sans réécrire rétroactivement les courbes publiques si le stock officiel est corrigé ultérieurement.

Des contrôles automatiques bloquent la publication en cas de rupture structurelle, incohérence TTC/HT ou variation journalière régionale manifestement anormale. Le contrôle ne corrige pas silencieusement une donnée douteuse : il arrête la mise à jour pour permettre son examen.

## Bouclier TotalEnergies effectif

Le graphique distingue le plafond commercial annoncé de son **effet économique observable**. Une zone jaune n'est affichée que lorsque le plafond est détecté comme effectivement contraignant.

La règle a été calibrée sur les périodes historiques déjà classées manuellement dans l'observatoire :

- au moins **30 %** des stations TotalEnergies corses observées sont situées à moins de **1,5 c€/L** du plafond ;
- les interruptions de **4 jours ou moins** sont comblées pour éviter les clignotements liés aux promotions ou au bruit quotidien ;
- les épisodes isolés de moins de **7 jours** ne sont pas retenus.

Les anciennes zones jaunes restent figées ; la détection automatique ne sert qu'à prolonger l'historique à partir du 29 mai 2026. Le référentiel TotalEnergies est séparé car l'Open Data officiel ne fournit pas l'enseigne des stations.

Les **montants des plafonds commerciaux** restent une configuration explicite dans `scripts/bouclier_detector.py`. Si TotalEnergies change son plafond, c'est le seul paramètre commercial qui doit être mis à jour manuellement ; le caractère effectif ou non du bouclier est ensuite déterminé automatiquement par les données.

## Analyse éditoriale automatisée

L'analyse historique 2022–2025 reste celle déjà publiée. Pour l'année en cours, le texte est alimenté automatiquement par des indicateurs reproductibles :

- écart HT moyen observé depuis le 1er janvier ;
- écart HT moyen hors périodes où le bouclier est détecté comme effectivement contraignant ;
- statut courant du bouclier ;
- date de début de la période active ;
- plafond courant et proportion de stations TotalEnergies proches du plafond.

Le système n'invente pas de valeur contrefactuelle « sans bouclier » lorsqu'elle ne peut pas être reconstruite de manière vérifiable à partir des données.

## Mise à jour hebdomadaire

Le workflow `update-weekly.yml` s'exécute chaque **lundi matin** :

1. téléchargement du stock annuel officiel ;
2. ajout des seuls jours nouveaux à `data.json` ;
3. contrôles de cohérence ;
4. détection du bouclier effectif ;
5. recalcul des indicateurs éditoriaux ;
6. commit automatique de `data.json` si les données ont réellement avancé ;
7. demande explicite de reconstruction de GitHub Pages.

S'il n'y a aucun nouveau jour officiel, l'exécution est un **no-op** : aucun commit inutile et aucune fausse date de mise à jour.

## Crédits

Calculs et analyse : [carburantscorse.fr](https://carburantscorse.fr) · Initiative A4C.

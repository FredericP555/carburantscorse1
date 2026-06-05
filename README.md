# Observatoire Prix Carburants Corse

Dashboard interactif comparant les prix des carburants en Corse vs les régions métropolitaines françaises, de janvier 2022 à mai 2026.

**→ [carburantscorse.fr](https://carburantscorse.fr)**

## Structure

```
index.html      Structure HTML + CSS
app.js          Code applicatif (Chart.js, logique, calculs)
chart.min.js    Bibliothèque Chart.js 4.4.1
data.json       Données pré-calculées (3 résolutions : mensuel, hebdo, journalier)
```

## Données

- **Source** : [prix-carburants.gouv.fr](https://prix-carburants.gouv.fr) — fichiers annuels 2022–2026
- **Périmètre** : 12 régions métropolitaines + Corse
- **Carburants** : Gazole, SP95
- **Prix affichés** : TTC (graphe prix) · HT pour l'écart (neutralise la différence de TVA Corse 13% / Continent 20%)
- **Stations autoroute** : exclues
- **Méthode** : forward-fill 45j, 6 relevés aberrants neutralisés

## Mise à jour des données

1. Télécharger le nouveau fichier XML sur prix-carburants.gouv.fr
2. Relancer le script de génération `data.json`
3. Pousser uniquement `data.json` sur GitHub

## Analyse

Le dashboard met en évidence :
1. Un écart de prix structurel Corse–Continent qui s'aggrave chaque année (+3 c€/L entre 2022 et 2025)
2. L'effet des remises et du bouclier tarifaire TotalEnergies sur cet écart
3. Que cette progression exclut toute explication par les seuls coûts d'insularité

## Crédits

Calculs et analyse : [carburantscorse.fr](https://carburantscorse.fr) · Initiative [A4C](https://fpoletti.blog)

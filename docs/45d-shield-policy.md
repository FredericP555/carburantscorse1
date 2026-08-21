# Politique préparée — seuil 45 jours et bouclier

> **Statut : PRÉPARÉE, NON ACTIVÉE.** Toutes les modifications décrites ici restent sur `prep/45d-shield-policy`. `main` et la production du lundi restent inchangés jusqu'à décision explicite après la mise à jour du 24 août 2026.

## 1. Règle normale

- Seuil : **45 jours par station × carburant**.
- Une déclaration à J0 reste utilisable de J0 à J+44 inclus ; à J+45 elle sort de la règle normale.
- Une redéclaration au même prix remet le compteur à zéro.
- Prix non fini, date future, rupture/fermeture ou preuve indépendante d'inactivité : exclusion prioritaire.

## 2. Corse — période de bouclier TotalEnergies effectif

Le détecteur de bouclier préparé conserve la règle historique : plafond connu, au moins une TotalEnergies au plafond avec tolérance **-0,2 c/L à +0,1 c/L**, et P75 hors Total au moins égal au plafond ; confirmation sur deux jours consécutifs, avec au plus un jour isolé comblé.

Sur la branche de préparation, le détecteur dynamique est désormais aligné sur la nouvelle méthodologie :

- fraîcheur stricte `age < 45` : J+45 est exclu ;
- tri-état `TOTAL / NON_TOTAL_CONFIRMED / UNKNOWN` ;
- un ID `UNKNOWN` n'entre ni dans le groupe Total ni dans le P75 hors Total ;
- le registre canonique est `config/corse_station_brands.json`.

Les périodes historiques 2023-2025 restent figées et ne sont pas recalculées silencieusement.

Au-delà de 45 jours en Corse, l'exception préparée concerne uniquement **Gazole et SP95** dans une station TotalEnergies, après détection du bouclier avec des données normalement fraîches, si le dernier prix du carburant cible est au plafond applicable et s'il était encore admissible à l'entrée de la phase.

La vivacité est recherchée uniquement sur l'autre carburant principal (**Gazole ↔ SP95**). E10 ne peut pas bénéficier d'une exception de vieillissement.

### Double plafond et Rotterdam

Si Gazole et SP95 sont simultanément au plafond, Rotterdam Gazole peut servir dans le cas particulier du double plafond. Rotterdam n'est jamais utilisé comme indice du marché SP95.

Le calibrage Corse candidat 2026 reste : entrée 8 avril 2026 ; R1 = moyenne des trois dernières cotations réellement observées avant l'entrée ; sorties 29 mai, 1er juin et 2 juin ; `k_corse ≈ 0,733`, avec `R2 = k × R1`.

**La règle exacte de franchissement de R2 n'est pas définie dans cette préparation.** Le moteur ne fait que consommer un verdict `rotterdam_gazole_constraining`. Aucune convention supplémentaire n'est inventée avant décision méthodologique explicite.

## 3. Source Rotterdam et release commune C1 → C2

La chaîne préparée est **UFIP → C1 → C2**.

- C1 effectue l'unique téléchargement UFIP.
- C1 produit `rotterdam_gazole_observed.csv` et `rotterdam_gazole_daily.csv`.
- La fenêtre UFIP conserve les observations de calibration 2026 même après le changement d'année.
- C1 publie, dans une même release validée : snapshot 13/20, métadonnées, deux CSV Rotterdam et registre Corse canonique.
- Les SHA-256 du snapshot, des deux CSV Rotterdam et du registre Corse sont inscrits dans le manifeste.
- La release n'est créée qu'après les validations bloquantes de C1 et, lorsqu'il y a une mise à jour, après le commit validé des données et du registre.

## 4. Continent C1 — vivacité bornée après 45 jours

Cette règle est propre au continent dans C1 :

- J0 à J+44 : règle normale ;
- de **J+45 à J+89 inclus**, un vieux prix Gazole/SP95 peut rester admissible uniquement si la même station a déclaré un autre carburant depuis moins de 45 jours ;
- la déclaration de vivacité ne remet pas à zéro l'âge du prix cible ;
- à **J+90**, le prix cible est exclu quoi qu'il arrive.

Ce plafond de 90 jours est un garde-fou propre à cette règle C1 continentale. Il ne doit pas être transposé automatiquement à C2.

## 5. Garde-fous prioritaires

Même lorsqu'une exception serait autrement applicable :

- rupture active → exclusion ;
- fermeture / preuve indépendante d'inactivité → exclusion ;
- prix absent, non fini ou invalide → exclusion ;
- date de déclaration future → exclusion ;
- en Corse sous bouclier, prix déjà périmé à l'entrée de la phase → aucune résurrection ;
- changement de plafond → nouvelle phase et nouvelle vérification de l'admissibilité à l'entrée.

## Procédure après lundi

1. Laisser C1 puis C2 publier normalement avec la méthode actuelle.
2. Contrôler les deux publications et figer les résultats comme référence.
3. Tester la politique préparée uniquement en candidat.
4. Produire `ACTUEL`, `NOUVELLE_REGLE_PROSPECTIVE` et `NOUVELLE_REGLE_RETROACTIVE`.
5. Mesurer les différences avant toute activation.
6. Définir séparément, puis coder et tester, la règle exacte liée au franchissement de R2.
7. Décider ensuite explicitement de toute migration ou réécriture historique.

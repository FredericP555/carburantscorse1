# Politique préparée — seuil 45 jours et bouclier

> **Statut : PRÉPARÉE, NON ACTIVÉE.** Toutes les modifications décrites ici restent sur `prep/45d-shield-policy`. `main` et la production du lundi restent inchangés jusqu'à décision explicite après la mise à jour du 24 août 2026.

## 1. Règle normale

- Seuil : **45 jours par station × carburant**.
- Une déclaration à J0 reste utilisable de J0 à J+44 inclus ; à J+45 elle sort de la règle normale.
- Une redéclaration au même prix remet le compteur à zéro.
- Prix non fini, date future, rupture/fermeture ou preuve indépendante d'inactivité : exclusion prioritaire.

## 2. Bouclier effectif et fiabilité d'un vieux prix sont deux choses distinctes

Le statut **bouclier effectif** reste déterminé uniquement par le détecteur A4C : plafond connu, au moins une TotalEnergies au plafond avec tolérance **-0,2 c/L à +0,1 c/L**, et P75 hors Total au moins égal au plafond ; confirmation sur deux jours consécutifs, avec au plus un jour isolé comblé.

R2 ne démarre pas et ne termine pas le bouclier. Il intervient seulement ensuite pour décider si un vieux prix de station peut encore entrer dans une moyenne dans le cas du double plafond.

Sur la branche de préparation, le détecteur dynamique utilise `age < 45` et le tri-état `TOTAL / NON_TOTAL_CONFIRMED / UNKNOWN`. Un ID `UNKNOWN` n'entre ni dans le groupe Total ni dans le P75 hors Total.

## 3. Corse — un seul carburant principal au plafond

Au-delà des 45 jours normaux, l'exception concerne uniquement Gazole/SP95 d'une station TotalEnergies pendant un bouclier effectif, si le prix cible est au plafond de sa phase.

- Cible SP95 : une nouvelle déclaration Gazole datant de moins de 45 jours prouve la vivacité.
- Cible Gazole : une nouvelle déclaration SP95 datant de moins de 45 jours prouve la vivacité.
- Cette déclaration de l'autre carburant crée une **nouvelle fenêtre glissante de 45 jours** pour le vieux prix cible.
- À défaut de nouvelle déclaration admissible depuis 45 jours, le vieux prix cible sort de la moyenne.
- E10 ne peut pas servir de vivacité en Corse et ne bénéficie pas lui-même d'une exception de vieillissement.

## 4. Corse — Gazole et SP95 simultanément au plafond

Quand Gazole et SP95 sont tous deux au plafond, la vivacité croisée entre eux ne suffit plus. Le contrôle devient économique :

- Rotterdam Gazole **>= R2 Corse** : les vieux prix Gazole/SP95 peuvent rester admissibles, sous réserve des autres garde-fous ;
- Rotterdam Gazole **< R2 Corse** : les vieux prix Gazole/SP95 sont exclus de la moyenne ;
- après un premier passage sous R2 intervenu après l'expiration normale du carburant cible, ce vieux prix reste exclu même si Rotterdam remonte ensuite ; il ne redevient admissible qu'après une **nouvelle déclaration de ce carburant cible**, qui crée un nouveau J0 ;
- ce mécanisme ne change jamais le statut « bouclier effectif ».

Calibration candidate 2026 : `k_corse ≈ 0,733`, donc `R2 = k × R1`, avec R1 calculé sur les trois dernières cotations réellement observées avant le 8 avril 2026.

## 5. Phases de plafond et absence de résurrection

Une **phase de plafond** est simplement une portion continue de bouclier effectif pendant laquelle le montant du plafond ne change pas.

Exemple Gazole 2026 : le passage de 2,09 € à 2,25 € le 8 avril crée automatiquement une nouvelle phase.

C1 publie désormais ces phases explicitement dans les métadonnées partagées avec : date de début, date de fin, carburant, plafond et identifiant de phase.

Le garde-fou « aucune résurrection » est calculé automatiquement :

- si la dernière déclaration du carburant était encore âgée de moins de 45 jours au début de la phase, elle peut bénéficier ensuite des exceptions prévues ;
- si elle était déjà périmée au début de cette phase, le bouclier ne la ressuscite pas ;
- si le carburant cible est redéclaré pendant la phase, cette nouvelle déclaration est une preuve fraîche et repart normalement de J0.

Il n'existe donc plus de booléen manuel `eligible_at_cap_entry` à faire confiance : le moteur calcule cette admissibilité à partir des dates.

## 6. Source Rotterdam et release commune C1 → C2

La chaîne préparée est **UFIP → C1 → C2**.

- C1 effectue l'unique téléchargement UFIP.
- C1 produit `rotterdam_gazole_observed.csv` et `rotterdam_gazole_daily.csv`.
- La fenêtre UFIP conserve les observations de calibration 2026 même après le changement d'année.
- C1 publie, dans une même release validée : snapshot 13/20, métadonnées avec phases de plafond, deux CSV Rotterdam et registre Corse canonique.
- Les SHA-256 sont contrôlables par C2.

## 7. Continent C1 — règle distincte

La règle continentale de C1 reste distincte de la règle BdR de C2 : J+45 à J+89 par vivacité sur un autre carburant, puis arrêt absolu à J+90. Ce garde-fou C1 ne doit pas être transposé aux BdR de C2.

## 8. Garde-fous prioritaires

Dans tous les cas :

- rupture active → exclusion ;
- fermeture / preuve indépendante d'inactivité → exclusion ;
- prix absent, non fini ou invalide → exclusion ;
- date de déclaration future → exclusion ;
- prix déjà périmé lors de l'entrée dans la phase de plafond → aucune résurrection ;
- changement de plafond → nouvelle phase et nouvelle vérification automatique.

## Procédure après lundi

1. Laisser C1 puis C2 publier normalement avec la méthode actuelle.
2. Contrôler les deux publications et figer les résultats comme référence.
3. Tester la politique préparée uniquement en candidat.
4. Produire `ACTUEL`, `NOUVELLE_REGLE_PROSPECTIVE` et `NOUVELLE_REGLE_RETROACTIVE`.
5. Mesurer les différences avant toute activation.
6. Décider ensuite explicitement de toute migration ou réécriture historique.

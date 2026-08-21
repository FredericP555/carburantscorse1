# Politique préparée — seuil 45 jours et bouclier

> **Statut : PRÉPARÉE, NON ACTIVÉE.** Toutes les modifications décrites ici restent sur `prep/45d-shield-policy`. `main` et la production du lundi restent inchangés jusqu'à décision explicite après la mise à jour du 24 août 2026.

## 1. Règle normale

- Seuil : **45 jours par station × carburant**.
- Une déclaration à J0 reste utilisable de J0 à J+44 inclus ; à J+45 elle sort de la règle normale.
- Une redéclaration au même prix remet le compteur à zéro.
- Prix non fini, date future, rupture/fermeture ou preuve indépendante d'inactivité : exclusion prioritaire.

## 2. Portée territoriale dans C1

C1 ne distingue que deux ensembles méthodologiques :

- **Corse** ;
- **toutes les régions hors Corse**, traitées uniformément par la règle continentale C1.

Les **Bouches-du-Rhône n'ont aucun statut particulier dans C1**. Elles sont traitées exactement comme n'importe quelle autre région hors Corse. La logique spécifique BdR n'existe que dans C2, parce que C2 est précisément l'observatoire Corse ↔ BdR.

La **règle Corse est la même dans C1 et dans C2, sans différence méthodologique**. C1 produit en plus les métadonnées partagées (bouclier, phases, Rotterdam, registre), mais cela ne change pas la règle d'admissibilité appliquée aux stations corses.

## 3. Bouclier effectif et fiabilité d'un vieux prix sont deux choses distinctes

Le statut **bouclier effectif** reste déterminé uniquement par le détecteur A4C : plafond connu, au moins une TotalEnergies au plafond avec tolérance **-0,2 c/L à +0,1 c/L**, et P75 hors Total au moins égal au plafond ; confirmation sur deux jours consécutifs, avec au plus un jour isolé comblé.

R2 ne démarre pas et ne termine pas le bouclier. Il intervient seulement ensuite pour décider si un vieux prix de station peut encore entrer dans une moyenne dans le cas du double plafond.

Sur la branche de préparation, le détecteur dynamique utilise `age < 45` et le tri-état `TOTAL / NON_TOTAL_CONFIRMED / UNKNOWN`. Un ID `UNKNOWN` n'entre ni dans le groupe Total ni dans le P75 hors Total.

## 4. Corse — un seul carburant principal au plafond

Cette règle est **identique dans C1 et C2**.

Au-delà des 45 jours normaux, l'exception concerne uniquement Gazole/SP95 d'une station TotalEnergies pendant un bouclier effectif, si le prix cible est au plafond de sa phase.

- Cible SP95 : une nouvelle déclaration Gazole datant de moins de 45 jours prouve la vivacité.
- Cible Gazole : une nouvelle déclaration SP95 datant de moins de 45 jours prouve la vivacité.
- Cette déclaration de l'autre carburant crée une **nouvelle fenêtre glissante de 45 jours** pour le vieux prix cible.
- À défaut de nouvelle déclaration admissible depuis 45 jours, le vieux prix cible sort de la moyenne.
- E10 ne peut pas servir de vivacité en Corse et ne bénéficie pas lui-même d'une exception de vieillissement.

## 5. Corse — Gazole et SP95 simultanément au plafond

Cette règle est également **identique dans C1 et C2**.

Quand Gazole et SP95 sont tous deux au plafond, la vivacité croisée entre eux ne suffit plus. Le contrôle devient économique :

- Rotterdam Gazole **>= R2 de la phase courante** : les vieux prix Gazole/SP95 peuvent rester admissibles, sous réserve des autres garde-fous ;
- Rotterdam Gazole **< R2 de la phase courante** : les vieux prix Gazole/SP95 sont exclus de la moyenne ;
- après un premier passage sous R2 intervenu après l'expiration normale du carburant cible, ce vieux prix reste exclu même si Rotterdam remonte ensuite ; il ne redevient admissible qu'après une **nouvelle déclaration de ce carburant cible**, qui crée un nouveau J0 ;
- ce mécanisme ne change jamais le statut « bouclier effectif ».

### Calibration de R2 par période de bouclier effectif

Les dates des **3, 6 et 7 avril 2026 ne définissent pas R1 pour toujours**. Elles appartiennent uniquement à l'épisode de référence 2026 qui sert à calibrer le coefficient territorial `k_corse ≈ 0,733`.

À chaque **nouvelle phase de bouclier effectif**, R1 est recalculé comme la moyenne des **trois dernières cotations Rotterdam réellement observées avant le début de cette phase**. Le seuil applicable à cette phase est alors :

`R2_phase = k_corse × R1_phase`

Ainsi, si les prix repassent sous le plafond et que le bouclier cesse d'être effectif, puis qu'ils reviennent plus tard au plafond et qu'une nouvelle période de bouclier effectif est détectée, cette nouvelle période reçoit **un nouveau R1 et un nouveau R2**, même si le montant du plafond n'a pas changé.

Le coefficient `k` reste celui calibré sur l'épisode de référence ; ce sont R1 et R2 qui sont recalculés à chaque nouvelle phase.

## 6. Phases de plafond et absence de résurrection

Une **phase de plafond** est une portion continue de bouclier effectif pendant laquelle le montant du plafond ne change pas.

Une nouvelle phase commence donc dans deux cas :

- le plafond change ;
- le bouclier effectif s'interrompt puis recommence plus tard, même avec le même plafond.

Exemple Gazole 2026 : le passage de 2,09 € à 2,25 € le 8 avril crée automatiquement une nouvelle phase.

C1 publie ces phases explicitement dans les métadonnées partagées avec : date de début, date de fin, carburant, plafond et identifiant de phase. La date de début de phase sert aussi de point d'ancrage pour recalculer le R1/R2 Rotterdam de cette phase.

Le garde-fou « aucune résurrection » est calculé automatiquement :

- si la dernière déclaration du carburant était encore âgée de moins de 45 jours au début de la phase, elle peut bénéficier ensuite des exceptions prévues ;
- si elle était déjà périmée au début de cette phase, le bouclier ne la ressuscite pas ;
- si le carburant cible est redéclaré pendant la phase, cette nouvelle déclaration est une preuve fraîche et repart normalement de J0.

Il n'existe donc plus de booléen manuel `eligible_at_cap_entry` à faire confiance : le moteur calcule cette admissibilité à partir des dates.

## 7. Source Rotterdam et release commune C1 → C2

La chaîne préparée est **UFIP → C1 → C2**.

- C1 effectue l'unique téléchargement UFIP.
- C1 produit `rotterdam_gazole_observed.csv` et `rotterdam_gazole_daily.csv`.
- La fenêtre UFIP conserve les observations historiques nécessaires au calibrage de `k` et au calcul des trois cotations précédant chaque nouvelle phase.
- C1 publie, dans une même release validée : snapshot 13/20, métadonnées avec phases de plafond, deux CSV Rotterdam et registre Corse canonique.
- Les SHA-256 sont contrôlables par C2.

## 8. Toutes les régions hors Corse dans C1, BdR comprises

La règle continentale C1 s'applique **uniformément à toutes les régions hors Corse**, y compris les Bouches-du-Rhône :

- J0 à J+44 : règle normale ;
- J+45 à J+89 : le vieux prix Gazole/SP95 peut rester admissible si la station a déclaré un autre carburant depuis moins de 45 jours ;
- J+90 : exclusion absolue du vieux prix cible.

Il n'existe **aucun traitement spécial BdR dans C1** : pas de `k_bdr`, pas de `R2 BdR`, pas de branche Total classique spécifique. Ces éléments appartiennent uniquement à C2.

## 9. Garde-fous prioritaires

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

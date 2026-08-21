# Politique préparée — seuil 45 jours et bouclier

> **Statut : PRÉPARÉE, NON ACTIVÉE.** Cette branche ne modifie aucun calcul de production. `main`, les workflows, `scripts/update_data_v2.py` et le détecteur de bouclier actuellement en production restent inchangés jusqu'à décision explicite après la mise à jour du lundi 24 août 2026.

## Règle normale hors bouclier

- Seuil unique : **45 jours par station × carburant**, Corse et continent.
- Une déclaration à J0 reste utilisable de J0 à J+44 ; à J+45 elle devient périmée.
- Une redéclaration au même prix remet le compteur à zéro.
- La vivacité de la station est un test séparé : hors bouclier, une déclaration récente d'un autre carburant ne prolonge pas un vieux prix du carburant cible.
- Rupture/fermeture, prix invalide ou preuve indépendante d'inactivité : exclusion prioritaire.

## Détection du bouclier TotalEnergies effectif — règle conservée

Le détecteur actuellement en production dans C1 reste l'autorité pour décider si le bouclier est effectivement contraignant. Il n'est pas remplacé par cette préparation.

Un jour est considéré comme actif lorsque :

1. le plafond TotalEnergies applicable est connu ;
2. au moins une station TotalEnergies active est au plafond, avec la tolérance A4C **-0,2 c/L à +0,1 c/L** ;
3. le **75e percentile** des stations corses non-Total actives est au moins égal au plafond.

La période est confirmée après **2 jours consécutifs** remplissant ces conditions et commence au premier de ces deux jours. Un seul jour inactif peut être comblé entre deux séquences confirmées. Un jour actif isolé ne suffit pas.

Les périodes historiques déjà déterminées avec cette règle restent conservées. À partir de 2026, le détecteur continue à fonctionner dynamiquement à partir des données normalement fraîches.

## Exception uniquement pendant un bouclier effectif

L'exception au seuil normal de 45 jours ne peut être examinée que :

- pour une station **TotalEnergies** ;
- après que le bouclier a été détecté avec des données normalement fraîches, donc sans circularité ;
- si le dernier prix du carburant cible est bien situé au plafond applicable ;
- si cette valeur était encore admissible à l'entrée de la phase de plafond.

### Vivacité

- **Corse** : au-delà de 45 jours, vivacité recherchée uniquement sur l'autre carburant principal (**Gazole ↔ SP95**).
- **Continent** : au-delà de 45 jours, une déclaration récente de n'importe quel autre carburant effectivement déclaré par la station peut établir sa vivacité.

### Double plafond Gazole + SP95

Si Gazole et SP95 sont simultanément au plafond et que l'indice **Rotterdam Gazole** confirme que le plafond Gazole reste économiquement contraignant, le délai de 45 jours peut être suspendu pour les deux carburants.

Rotterdam n'est pas utilisé comme indice du marché SP95. Il sert uniquement à étayer l'hypothèse de silence déclaratif explicable dans la configuration précise de double plafond.

Le seuil Rotterdam reste volontairement non paramétré (`rotterdam_threshold: null`) tant qu'il n'a pas été calibré et validé. L'exception échoue donc fermée en son absence.

## Garde-fous

- Une rupture/fermeture ou une preuve indépendante d'inactivité prime sur toute exception.
- Le simple vieillissement d'un prix pendant un double plafond ne constitue pas, à lui seul, une preuve d'inactivité.
- Une valeur déjà périmée au début d'une phase de plafond ne peut jamais être « ressuscitée » par l'exception.
- Un changement de plafond ouvre une nouvelle phase et impose de réexaminer l'admissibilité à l'entrée.

## Procédure après lundi

1. Laisser C1 puis C2 publier normalement lundi avec leur méthode actuelle.
2. Contrôler les deux publications et figer ces résultats comme référence.
3. Brancher cette politique uniquement dans un calcul candidat, jamais directement en production.
4. Produire trois séries côte à côte :
   - `ACTUEL` ;
   - `NOUVELLE_REGLE_PROSPECTIVE` ;
   - `NOUVELLE_REGLE_RETROACTIVE`.
5. Mesurer pour C1 et C2 : nombre de jours modifiés, stations gagnées/perdues, variation maximale d'une moyenne journalière, moyennes annuelles, écarts Corse/continent ou Corse/BdR et périodes de bouclier modifiées.
6. Calibrer et valider séparément le critère `Rotterdam Gazole contraignant` sans utiliser des prix prolongés pour détecter le bouclier.
7. Décider ensuite explicitement de toute migration ou réécriture historique.

## Rétroactivité

- **C1** : la règle normale historique est déjà fondée sur un forward-fill de 45 jours. Une simulation rétroactive est surtout utile pour mesurer l'effet des exceptions pendant les périodes de bouclier. Toute correction éventuelle sera décidée après comparaison chiffrée.
- **C2** : l'historique a été construit avec 150 jours en Corse et 30 jours dans les BdR. Une simple bascule prospective vers 45/45 créerait une rupture méthodologique. Un recalcul rétroactif 45/45 est donc à privilégier sous réserve des contrôles.
- L'exception `double plafond + Rotterdam` ne doit pas être reconstruite artificiellement pour les périodes où aucune série Rotterdam fiable n'est disponible, notamment 2023-2024 à ce stade.
- Toute réécriture historique éventuelle doit être exceptionnelle, documentée et précédée d'un rapport de différences. Aucune modification silencieuse de l'historique append-only.

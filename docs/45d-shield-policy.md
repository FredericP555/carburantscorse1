# Politique préparée — seuil 45 jours et bouclier

> **Statut : PRÉPARÉE, NON ACTIVÉE.** Ce document et le module `scripts/reliability_policy_v2.py` ne sont pas utilisés par le pipeline de production avant décision explicite après la mise à jour du lundi.

## Règle normale

- Seuil unique : **45 jours par station × carburant**, Corse et continent.
- Une déclaration à J0 reste utilisable de J0 à J+44 ; à J+45 elle devient périmée.
- Une redéclaration au même prix remet le compteur à zéro.
- Rupture active, prix invalide ou preuve indépendante d'inactivité : exclusion prioritaire.

## Bouclier effectif TotalEnergies

L'exception ne peut être appliquée qu'après détermination du bouclier à partir de données normalement fraîches (pas de circularité), et seulement pour un prix situé au plafond avec la tolérance A4C (-0,2 c/+0,1 c).

- **Corse** : au-delà de 45 jours, vivacité recherchée sur l'autre carburant principal (Gazole ↔ SP95).
- **Continent** : au-delà de 45 jours, toute déclaration récente d'un autre carburant de la station peut prouver sa vivacité.
- **Double plafond Gazole + SP95** : si les deux prix sont au plafond et que l'indice Rotterdam Gazole indique que le plafond Gazole reste économiquement contraignant, le délai de 45 jours peut être suspendu pour les deux carburants. Rotterdam n'est pas présenté comme un indice SP95 : il fonde uniquement l'hypothèse de silence explicable dans la configuration de double plafond.
- Le simple vieillissement des prix ne peut pas, dans cette configuration, servir de preuve d'inactivité. L'inactivité doit reposer sur un signal indépendant.
- Aucune valeur déjà périmée au début d'une phase de plafond ne peut être ressuscitée par l'exception. Un changement de plafond ouvre une nouvelle phase.

## Activation après lundi

1. Laisser C1/C2 publier lundi avec la méthode actuelle.
2. Contrôler la publication et figer un point de comparaison.
3. Brancher le module préparé dans le calcul candidat uniquement.
4. Produire un diff ancien/nouveau : stations-jours, moyennes quotidiennes, moyennes annuelles, écarts Corse/continent, périodes de bouclier.
5. Calibrer/valider le test `Rotterdam Gazole contraignant` sans utiliser les prix prolongés pour détecter le bouclier.
6. Décider séparément du recalcul rétroactif C1 et C2.
7. Aucun merge ni activation sans validation explicite.

## Rétroactivité

- C1 : simulation rétroactive utile, surtout sur les périodes de bouclier.
- C2 : recalcul rétroactif 45/45 à privilégier pour éviter une rupture 150/30 → 45/45 dans l'historique.
- Toute réécriture historique éventuelle doit être exceptionnelle, documentée et précédée d'un rapport de différences.

# Politique préparée — seuil 45 jours et bouclier

> **Statut : PRÉPARÉE, NON ACTIVÉE.** Cette branche ne modifie aucun calcul de production. `main`, les workflows, `scripts/update_data_v2.py` et le détecteur de bouclier actuellement en production restent inchangés jusqu'à décision explicite après la mise à jour du lundi 24 août 2026.

## 1. Règle normale

- Seuil : **45 jours par station × carburant**.
- Une déclaration à J0 reste utilisable de J0 à J+44 inclus ; à J+45 elle sort de la règle normale.
- Une redéclaration au même prix remet le compteur à zéro.
- Rupture/fermeture, prix invalide ou preuve indépendante d'inactivité : exclusion prioritaire.

## 2. Corse — période de bouclier TotalEnergies effectif

Le détecteur actuellement en production dans C1 reste l'autorité pour décider si le bouclier est effectivement contraignant. Il n'est pas remplacé par cette préparation.

Un jour est considéré comme actif lorsque :

1. le plafond TotalEnergies applicable est connu ;
2. au moins une station TotalEnergies active est au plafond, avec la tolérance A4C **-0,2 c/L à +0,1 c/L** ;
3. le **75e percentile** des stations corses non-Total actives est au moins égal au plafond.

La période est confirmée après **2 jours consécutifs** remplissant ces conditions et commence au premier de ces deux jours. Un seul jour inactif peut être comblé entre deux séquences confirmées. Un jour actif isolé ne suffit pas.

Au-delà de 45 jours en Corse, l'exception préparée est examinée uniquement pour une station **TotalEnergies**, après détection du bouclier avec des données normalement fraîches, si le dernier prix du carburant cible est au plafond applicable et s'il était encore admissible à l'entrée de la phase.

La vivacité est recherchée uniquement sur l'autre carburant principal (**Gazole ↔ SP95**). Si Gazole et SP95 sont simultanément au plafond, le critère Rotterdam Gazole peut prendre le relais dans la configuration double-plafond, selon la même logique cible que dans C2. Rotterdam n'est jamais utilisé comme indice du marché SP95.

Le seuil Rotterdam de C1 reste volontairement non activé tant que son raccordement à la calibration Corse de C2 n'a pas été explicitement validé ; aucune récupération UFIP supplémentaire n'est ajoutée ici.

## 3. Continent — vivacité bornée après 45 jours

C1 ne dispose pas d'un rattachement d'enseigne suffisamment complet pour appliquer au continent une exception Total par marque. La règle préparée est donc indépendante de l'enseigne et du bouclier :

- J0 à J+44 : règle normale ;
- de **J+45 à J+89 inclus**, un vieux prix Gazole/SP95 peut rester admissible uniquement si la même station a déclaré **un autre carburant** depuis moins de 45 jours ;
- n'importe quel autre carburant effectivement déclaré par la station peut servir de preuve de vivacité ;
- la déclaration de vivacité ne remet pas à zéro l'âge du prix cible ;
- à **J+90**, le prix cible est exclu quoi qu'il arrive, même si un autre carburant a été déclaré le jour même.

Le plafond absolu de 90 jours empêche donc une prolongation indéfinie par déclarations successives d'autres carburants.

## 4. Garde-fous prioritaires

Même lorsqu'une exception serait autrement applicable :

- rupture active → exclusion ;
- fermeture / preuve indépendante d'inactivité → exclusion ;
- prix absent ou invalide → exclusion ;
- en Corse sous bouclier, prix déjà périmé à l'entrée de la phase → aucune résurrection ;
- changement de plafond → nouvelle phase et nouvelle vérification de l'admissibilité à l'entrée.

Le simple vieillissement d'un prix pendant un double plafond ne constitue pas, à lui seul, une preuve d'inactivité.

## Procédure après lundi

1. Laisser C1 puis C2 publier normalement lundi avec leur méthode actuelle.
2. Contrôler les deux publications et figer ces résultats comme référence.
3. Brancher cette politique uniquement dans un calcul candidat, jamais directement en production.
4. Produire trois séries côte à côte : `ACTUEL`, `NOUVELLE_REGLE_PROSPECTIVE`, `NOUVELLE_REGLE_RETROACTIVE`.
5. Mesurer pour C1 et C2 : nombre de jours modifiés, stations gagnées/perdues, variation maximale d'une moyenne journalière, moyennes annuelles, écarts Corse/continent ou Corse/BdR et périodes de bouclier modifiées.
6. Valider le raccordement du critère Rotterdam Corse sans utiliser de prix prolongés pour détecter le bouclier.
7. Décider ensuite explicitement de toute migration ou réécriture historique.

## Rétroactivité

- **C1** : la règle normale historique est déjà fondée sur un forward-fill de 45 jours. Une simulation rétroactive devra désormais mesurer séparément l'effet de la vivacité continentale bornée 45→89 jours et celui des exceptions de bouclier en Corse.
- **C2** : l'historique a été construit avec 150 jours en Corse et 30 jours dans les BdR. Une simple bascule prospective vers 45/45 créerait une rupture méthodologique. Un recalcul rétroactif 45/45 est donc à privilégier sous réserve des contrôles.
- L'exception `double plafond + Rotterdam` ne doit pas être reconstruite artificiellement pour les périodes où aucune série Rotterdam fiable n'est disponible, notamment 2023-2024 à ce stade.
- Toute réécriture historique éventuelle doit être exceptionnelle, documentée et précédée d'un rapport de différences. Aucune modification silencieuse de l'historique append-only.

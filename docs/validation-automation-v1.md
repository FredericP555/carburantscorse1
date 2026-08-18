# Validation automation-v1

## Contrôles fonctionnels

- Génération append-only : historique publié inchangé.
- Méthode éditoriale historique : chiffres 2022–2025 et bilans historiques reproduits exactement.
- Rendu navigateur : desktop, mobile portrait et mobile paysage.
- GitHub Pages : reconstruction explicite testée.

## Audit des stations corses — référence initiale

Audit indépendant effectué sur le stock officiel disponible au **17 août 2026** avec le même seuil de fraîcheur de **45 jours** que le dashboard.

| Carburant | Séries connues N-1/N | Déclarées en 2026 | Retenues au 17/08 | Trop anciennes | Dernier prix invalide |
|---|---:|---:|---:|---:|---:|
| Gazole | 125 | 123 | 121 | 4 | 0 |
| SP95 | 125 | 123 | 106 | 19 | 0 |

Les populations retenues ont été recoupées avec le détecteur TotalEnergies :

- Gazole : **121 = 47 TotalEnergies + 74 non-Total** ;
- SP95 : **106 = 35 TotalEnergies + 71 non-Total**.

Le workflow bloque si le comptage ne se réconcilie pas, si la population retenue chute de plus de 20 % par rapport au dernier audit, si elle passe sous un plancher absolu (80 Gazole / 60 SP95), si plus de 5 % des derniers états sont des prix invalides, ou si le total retenu diffère du calcul indépendant Total + non-Total.

La référence de démarrage avant le premier audit stocké dans `data.json` est celle du 17 août 2026 : **121 Gazole / 106 SP95**.

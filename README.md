# 🏀 NBA pour Home Assistant

Intégration personnalisée affichant scores, classements et matchs de vos équipes NBA favorites (données ESPN, sans clé API).

## Fonctionnalités
- Plusieurs équipes favorites
- Dernier match, prochain match, match en cours par équipe
- Matchs du jour, classements Est/Ouest
- Mise à jour rapide (30 s) pendant les matchs
- Événements `nba_game_start` et `nba_game_end` pour vos automatisations
- Cartes Lovelace et blueprint de notification fournis

## Installation via HACS
1. HACS > ⋮ > **Dépôts personnalisés**
2. Ajouter `https://github.com/cy-bertrand/ha-nba` (catégorie **Intégration**)
3. Installer **NBA**, puis redémarrer Home Assistant
4. Paramètres > Appareils et services > **Ajouter une intégration** > NBA

## Cartes Lovelace
Voir le dossier `lovelace/` : copiez le YAML dans une carte « Manuel ».

## Notifications
Importez le blueprint `blueprints/nba_game_notification.yaml` ou créez une automatisation sur les événements `nba_game_start` / `nba_game_end`.

## Avertissement
API ESPN non officielle, susceptible de changer. Projet non affilié à la NBA.

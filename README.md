# 🏀 NBA pour Home Assistant

Intégration personnalisée affichant scores, classements, statistiques et matchs de vos équipes NBA favorites (données ESPN, sans clé API).

## Fonctionnalités
- Plusieurs équipes favorites
- Dernier match, prochain match, match en cours par équipe
- Dates et heures affichées dans le fuseau horaire de votre Home Assistant
- Matchs du jour, classements Est/Ouest
- Meilleurs joueurs de la saison : marqueurs, rebondeurs, passeurs, intercepteurs, contreurs
- Mise à jour rapide (30 s) pendant les matchs
- Événements `nba_game_start` et `nba_game_end` pour vos automatisations
- Cartes Lovelace (logos, couleurs, équipes favorites en surbrillance)
- Blueprint de notification installé automatiquement

## Installation via HACS
1. HACS > ⋮ > **Dépôts personnalisés**
2. Ajouter `https://github.com/cy-bertrand/ha-nba` (catégorie **Intégration**)
3. Installer **NBA**, puis redémarrer Home Assistant
4. Paramètres > Appareils et services > **Ajouter une intégration** > NBA

## Capteurs créés
| Capteur | Contenu |
|---|---|
| `sensor.nba_matchs_du_jour` | Nombre de matchs, détail dans l'attribut `games` |
| `sensor.nba_classement_est` / `_ouest` | Premier de la conférence, classement complet dans `standings` |
| `sensor.nba_meilleurs_marqueurs` (et rebondeurs, passeurs, intercepteurs, contreurs) | Top 10 dans l'attribut `leaders` |
| `sensor.<equipe>_dernier_match` / `_prochain_match` / `_match_en_cours` | Une série par équipe favorite |

## Notifications (blueprint automatique)
Au démarrage, l'intégration copie elle-même le blueprint dans `config/blueprints/automation/nba/`. Il apparaît ensuite dans **Paramètres > Automatisations et scènes > Modèles** sous le nom « NBA - Notification de match » : cliquez dessus puis **Créer une automatisation**.

Le fichier installé n'est jamais écrasé s'il existe déjà. Pour récupérer une version plus récente du blueprint, supprimez `config/blueprints/automation/nba/nba_game_notification.yaml` puis redémarrez Home Assistant.

Vous pouvez aussi créer votre propre automatisation sur les événements `nba_game_start` / `nba_game_end`.

## Cartes Lovelace
Dossier `lovelace/` : ouvrez le fichier, copiez le YAML dans une carte **Manuelle**. Les cartes utilisent du HTML dans une carte Markdown, aucune dépendance externe n'est nécessaire.
- `today-games-card.yaml` : matchs du jour
- `standings-card.yaml` : classement (Est ou Ouest)
- `team-card.yaml` : résumé d'une équipe (adapter les noms de capteurs)
- `leaders-card.yaml` : top 10 des marqueurs avec podium
- `top3-passeurs-card.yaml`, `top3-rebondeurs-card.yaml`, `top3-contreurs-card.yaml`, `top3-intercepteurs-card.yaml` : podiums top 3

## Avertissement
API ESPN non officielle, susceptible de changer. Projet non affilié à la NBA.

# 🏀 NBA pour Home Assistant

Integration personnalisee affichant scores, classements, statistiques et matchs de vos equipes NBA favorites (donnees ESPN, sans cle API).

## Fonctionnalites
- Plusieurs equipes favorites
- Dernier match, prochain match, match en cours par equipe
- Dates et heures affichees dans le fuseau horaire de votre Home Assistant
- Matchs du jour, classements Est/Ouest
- Meilleurs joueurs de la saison : marqueurs, rebondeurs, passeurs, intercepteurs, contreurs
- Mise a jour rapide (30 s) pendant les matchs
- Evenements `nba_game_start` et `nba_game_end` pour vos automatisations
- Cartes Lovelace (logos, couleurs, podium, equipes favorites en surbrillance) et blueprint de notification

## Installation via HACS
1. HACS > ⋮ > **Depots personnalises**
2. Ajouter `https://github.com/cy-bertrand/ha-nba` (categorie **Integration**)
3. Installer **NBA**, puis redemarrer Home Assistant
4. Parametres > Appareils et services > **Ajouter une integration** > NBA

## Capteurs crees
| Capteur | Contenu |
|---|---|
| `sensor.nba_matchs_du_jour` | Nombre de matchs, detail dans l'attribut `games` |
| `sensor.nba_classement_est` / `_ouest` | Premier de la conference, classement complet dans `standings` |
| `sensor.nba_meilleurs_marqueurs` (et rebondeurs, passeurs, intercepteurs, contreurs) | Top 10 dans l'attribut `leaders` |
| `sensor.<equipe>_dernier_match` / `_prochain_match` / `_match_en_cours` | Une serie par equipe favorite |

## Cartes Lovelace
Dossier `lovelace/` : ouvrez le fichier, copiez le YAML dans une carte **Manuelle**. Les cartes utilisent du HTML dans une carte Markdown, aucune dependance externe n'est necessaire.
- `today-games-card.yaml` : matchs du jour
- `standings-card.yaml` : classement (Est ou Ouest)
- `team-card.yaml` : resume d'une equipe (adapter les noms de capteurs)
- `leaders-card.yaml` : top 10 des marqueurs avec podium
- `top3-passeurs-card.yaml`, `top3-rebondeurs-card.yaml`, `top3-contreurs-card.yaml`, `top3-intercepteurs-card.yaml` : podiums top 3

## Notifications
Importez le blueprint `blueprints/nba_game_notification.yaml` (choix du debut et/ou de la fin de match, filtre par equipe, vainqueur indique) ou creez une automatisation sur les evenements `nba_game_start` / `nba_game_end`.

## Avertissement
API ESPN non officielle, susceptible de changer. Projet non affilie a la NBA.

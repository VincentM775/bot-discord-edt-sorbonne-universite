# Bot Discord — Emploi du temps (UFR Info P6 / Jussieu)

Poste automatiquement l'emploi du temps dans un salon Discord **chaque soir, pour
le lendemain**, plus un **récapitulatif de la semaine à venir le dimanche soir**.
Configuré par défaut pour **M1_RES_ALT** (parcours Réseaux, alternance).

Les données sont lues directement depuis le serveur **CalDAV** de l'UFR (matière,
horaire, salle) — pas de screenshot, robuste aux changements du site. Le compte
invité (`student.master` / `guest`) est public : il figure en clair dans le
`config.js` du site `https://cal.ufr-info-p6.jussieu.fr/master/` et donne un accès
en lecture seule.

## 1. Créer le bot Discord

1. Va sur https://discord.com/developers/applications → **New Application**.
2. Onglet **Bot** → **Reset Token** → copie le token (c'est ton `DISCORD_TOKEN`).
3. Toujours dans **Bot**, active **Message Content Intent**.
4. Onglet **OAuth2 → URL Generator** : coche `bot`, puis les permissions
   `Send Messages` et `Embed Links`. Ouvre l'URL générée pour inviter le bot sur
   ton serveur.
5. Dans Discord (mode développeur activé : Paramètres → Avancés → Mode développeur),
   clic droit sur ton salon → **Copier l'identifiant** (c'est `DISCORD_CHANNEL_ID`).

## 2. Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # puis édite .env
```

Remplis `.env` : `DISCORD_TOKEN`, `DISCORD_CHANNEL_ID`, et éventuellement
`SEND_TIME` (heure d'envoi, ex. `18:00`).

## 3. Tester

```bash
# Test de la récupération CalDAV seule (sans Discord) :
python edt.py

# Lancer le bot, puis dans le salon :
#   !edt              -> emploi du temps d'aujourd'hui
#   !edt hier         -> aussi : aujourd'hui, demain
#                        (ou en anglais : yesterday, today, tomorrow)
#   !semaine          -> aperçu de la semaine en cours
python bot.py
```

## 4. Déploiement systemd (serveur Linux)

Édite `bot-edt.service` (utilisateur + chemins), puis :

```bash
sudo cp bot-edt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bot-edt
journalctl -u bot-edt -f
```

## Changer de parcours

Modifie `CALDAV_URL` dans `.env`. Exemples (remplace la fin) :

| Parcours | URL |
|---|---|
| M1_RES_ALT (défaut) | `.../caldav.php/RES/M1_RES-ITESCIA/` |
| M1_RES | `.../caldav.php/RES/M1_RES/` |
| M2_RES | `.../caldav.php/RES/M2_RES/` |
| M2_RES-SEC | `.../caldav.php/RES/M2_RES-ITESCIA/` |
| M2_RES-DEV | `.../caldav.php/RES/M2_RES-INSTA/` |

Autres masters : remplace `RES` par `ANDROIDE`, `BIM`, `DAC`, `IMA`, `IQ`, `SAR`,
`SESI`, `SFPN`, `STL` (préfixe complet :
`https://cal.ufr-info-p6.jussieu.fr:443/caldav.php/`).

## Réglages (.env)

| Variable | Rôle |
|---|---|
| `SEND_TIME` | Heure de l'envoi quotidien (Europe/Paris), `HH:MM` |
| `SEND_FOR` | `tomorrow` (défaut) ou `today` |
| `POST_WHEN_EMPTY` | `true` = poster "Pas de cours 🎉" même les jours vides |
| `WEEKLY_ENABLED` | `true` = activer le récap hebdomadaire |
| `WEEKLY_TIME` | Heure de l'envoi hebdo (Europe/Paris), `HH:MM` |
| `WEEKLY_DAY` | Jour d'envoi : `0` = lundi … `6` = dimanche (défaut `6` = dimanche soir) |
| `WEEKLY_DAYS` | Jours affichés : `5` = lun→ven, `7` = semaine complète |

> Le récap hebdo affiche toujours la **semaine à venir** (prochain lundi). Avec les
> réglages par défaut, il part le **dimanche soir** — comme l'envoi quotidien, mais
> pour toute la semaine suivante.

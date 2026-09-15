"""Bot Discord qui poste l'emploi du temps (M1_RES_ALT / UFR Info P6) dans un
salon, chaque soir, pour le lendemain. Voir README.md."""

from __future__ import annotations

import datetime as dt
import logging
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import edt

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot-edt")

PARIS = ZoneInfo("Europe/Paris")
AUCUN_COURS = "Pas de cours 🎉"

# --- Configuration (.env) ---------------------------------------------------
TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
CALDAV_URL = os.environ.get(
    "CALDAV_URL",
    "https://cal.ufr-info-p6.jussieu.fr:443/caldav.php/RES/M1_RES-ITESCIA/",
)
CALDAV_USER = os.environ.get("CALDAV_USER", "student.master")
CALDAV_PASSWORD = os.environ.get("CALDAV_PASSWORD", "guest")
SEND_FOR = os.environ.get("SEND_FOR", "tomorrow").strip().lower()
POST_WHEN_EMPTY = os.environ.get("POST_WHEN_EMPTY", "true").strip().lower() == "true"


def _parse_time(value: str) -> dt.time:
    h, m = value.split(":")
    return dt.time(hour=int(h), minute=int(m), tzinfo=PARIS)


SEND_AT = _parse_time(os.environ.get("SEND_TIME", "18:00"))

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _date_fr(d: dt.date) -> str:
    return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]} {d.year}"


def _jour_cible() -> dt.date:
    today = dt.datetime.now(PARIS).date()
    return today + dt.timedelta(days=1) if SEND_FOR == "tomorrow" else today


def construire_embed(jour: dt.date) -> discord.Embed:
    cours = edt.fetch_cours(CALDAV_URL, CALDAV_USER, CALDAV_PASSWORD, jour)
    titre = f"📅 Emploi du temps — {_date_fr(jour)}"

    if not cours:
        return discord.Embed(title=titre, description=AUCUN_COURS, color=0x2ECC71)

    lignes = []
    for c in cours:
        lieu = f" 📍 {c.lieu}" if c.lieu else ""
        lignes.append(f"🕐 {c.horaire} • {c.titre}{lieu}")
    embed = discord.Embed(title=titre, description="\n".join(lignes), color=0x3498DB)
    embed.set_footer(text=f"{len(cours)} cours")
    return embed


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


async def envoyer(jour: dt.date | None = None) -> None:
    jour = jour or _jour_cible()
    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    try:
        embed = construire_embed(jour)
    except Exception:
        log.exception("Échec de récupération de l'emploi du temps")
        await channel.send("⚠️ Impossible de récupérer l'emploi du temps (erreur réseau/CalDAV).")
        return

    if embed.description == AUCUN_COURS and not POST_WHEN_EMPTY:
        log.info("Aucun cours le %s, envoi ignoré (POST_WHEN_EMPTY=false)", jour)
        return
    await channel.send(embed=embed)
    log.info("Emploi du temps envoyé pour le %s", jour)


@tasks.loop(time=SEND_AT)
async def envoi_quotidien() -> None:
    await envoyer()


@bot.command(name="edt")
async def cmd_edt(ctx: commands.Context) -> None:
    """Force l'envoi de l'emploi du temps (jour cible) dans le salon courant."""
    embed = construire_embed(_jour_cible())
    await ctx.send(embed=embed)


@bot.event
async def on_ready() -> None:
    log.info("Connecté en tant que %s", bot.user)
    if not envoi_quotidien.is_running():
        envoi_quotidien.start()
    log.info("Envoi quotidien programmé à %s (Europe/Paris)", SEND_AT.strftime("%H:%M"))


if __name__ == "__main__":
    bot.run(TOKEN)

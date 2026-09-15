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

# --- Récapitulatif hebdomadaire --------------------------------------------
WEEKLY_ENABLED = os.environ.get("WEEKLY_ENABLED", "true").strip().lower() == "true"
WEEKLY_AT = _parse_time(os.environ.get("WEEKLY_TIME", "18:00"))
# Jour d'envoi de l'aperçu : 0 = lundi ... 6 = dimanche.
# Défaut 6 (dimanche soir) : la veille de la semaine, comme l'envoi quotidien.
WEEKLY_DAY = int(os.environ.get("WEEKLY_DAY", "6"))
# Nombre de jours affichés dans l'aperçu (5 = lundi->vendredi).
WEEKLY_DAYS = int(os.environ.get("WEEKLY_DAYS", "5"))

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _date_fr(d: dt.date) -> str:
    return f"{_JOURS[d.weekday()]} {d.day} {_MOIS[d.month - 1]} {d.year}"


# Arguments acceptés par !edt (français et anglais), en décalage de jours par
# rapport à aujourd'hui.
_DECALAGES = {
    "hier": -1,
    "yesterday": -1,
    "aujourdhui": 0,
    "ajd": 0,
    "today": 0,
    "demain": 1,
    "tomorrow": 1,
}


def _jour_demande(quand: str) -> dt.date | None:
    """Convertit l'argument de !edt en date : sans argument, c'est aujourd'hui.
    None si l'argument est inconnu. (L'envoi automatique du soir, lui, suit
    SEND_FOR et vise donc le lendemain.)"""
    cle = quand.strip().lower().replace("'", "").replace("\u2019", "") or "aujourdhui"
    if cle not in _DECALAGES:
        return None
    return dt.datetime.now(PARIS).date() + dt.timedelta(days=_DECALAGES[cle])


def _jour_cible() -> dt.date:
    today = dt.datetime.now(PARIS).date()
    return today + dt.timedelta(days=1) if SEND_FOR == "tomorrow" else today


def _lundi_courant() -> dt.date:
    today = dt.datetime.now(PARIS).date()
    return today - dt.timedelta(days=today.weekday())


def _lundi_prochain() -> dt.date:
    """Le lundi de la semaine à venir (strictement après aujourd'hui)."""
    today = dt.datetime.now(PARIS).date()
    jours = (0 - today.weekday()) % 7 or 7
    return today + dt.timedelta(days=jours)


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


def construire_embed_semaine(lundi: dt.date) -> discord.Embed:
    semaine = edt.fetch_semaine(
        CALDAV_URL, CALDAV_USER, CALDAV_PASSWORD, lundi, nb_jours=WEEKLY_DAYS
    )
    dernier = lundi + dt.timedelta(days=WEEKLY_DAYS - 1)
    embed = discord.Embed(
        title=f"🗓️ Semaine du {lundi.day} au {_date_fr(dernier)}",
        color=0x9B59B6,
    )
    for jour, cours in semaine.items():
        entete = f"{_JOURS[jour.weekday()].capitalize()} {jour.day:02d}/{jour.month:02d}"
        if not cours:
            embed.add_field(name=entete, value="— pas de cours", inline=False)
            continue
        lignes = []
        for c in cours:
            lieu = f" 📍 {c.lieu}" if c.lieu else ""
            lignes.append(f"🕐 {c.horaire} • {c.titre}{lieu}")
        embed.add_field(name=entete, value="\n".join(lignes), inline=False)
    return embed


# Easter egg : réponse à tout message privé qui n'est pas une commande.
REPONSE_MP = """Salut 👋

Si tu veux l'emploi du temps, écris-moi :
• `!edt` — les cours d'**aujourd'hui** (chaque soir je poste aussi ceux du lendemain, tout seul)
• `!edt hier`, `!edt aujourd'hui`, `!edt demain` — la journée de ton choix (l'anglais marche aussi : `yesterday`, `today`, `tomorrow`)
• `!semaine` — toute la **semaine en cours**, jour par jour, du lundi au vendredi

Et sinon… pourquoi tu viens me déranger ? 🤨
Si tu veux de l'aide pour tes exos de transformée de Fourier, envoie-les moi : je me ferai un plaisir de **ne pas** te répondre. 
(Je préfère les additions moi : 1+2=3, 3+4=5, ouais je sais ta vu comment je suis trop fort ?? 😎)

Allez, va réviser, et bon courage pour ton exam ^^"""


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


async def envoyer_semaine(lundi: dt.date | None = None) -> None:
    lundi = lundi or _lundi_prochain()
    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    try:
        embed = construire_embed_semaine(lundi)
    except Exception:
        log.exception("Échec de récupération de l'emploi du temps hebdomadaire")
        await channel.send("⚠️ Impossible de récupérer l'emploi du temps de la semaine.")
        return
    await channel.send(embed=embed)
    log.info("Aperçu hebdomadaire envoyé pour la semaine du %s", lundi)


@tasks.loop(time=SEND_AT)
async def envoi_quotidien() -> None:
    await envoyer()


@tasks.loop(time=WEEKLY_AT)
async def envoi_hebdomadaire() -> None:
    # Le loop se déclenche chaque jour à WEEKLY_AT ; on n'agit que le bon jour.
    if dt.datetime.now(PARIS).weekday() == WEEKLY_DAY:
        await envoyer_semaine()


@bot.command(name="edt")
async def cmd_edt(ctx: commands.Context, quand: str = "") -> None:
    """Emploi du temps d'un jour : `!edt`, `!edt hier|aujourd'hui|demain`
    (ou `yesterday|today|tomorrow`)."""
    jour = _jour_demande(quand)
    if jour is None:
        await ctx.send(
            f"Je ne connais pas `{quand}` 🤔 — essaie `!edt`, `!edt hier`, "
            "`!edt aujourd'hui` ou `!edt demain` (ou en anglais : `yesterday`, "
            "`today`, `tomorrow`)."
        )
        return
    embed = construire_embed(jour)
    await ctx.send(embed=embed)


@bot.command(name="semaine")
async def cmd_semaine(ctx: commands.Context) -> None:
    """Force l'envoi de l'aperçu de la semaine en cours."""
    embed = construire_embed_semaine(_lundi_courant())
    await ctx.send(embed=embed)


@bot.event
async def on_message(message: discord.Message) -> None:
    # En privé, tout ce qui n'est pas une commande valide déclenche l'easter egg.
    # En salon, comportement inchangé.
    if message.author.bot:
        return
    if message.guild is None:
        ctx = await bot.get_context(message)
        if not ctx.valid:
            log.info("Easter egg envoyé à %s", message.author)
            await message.channel.send(REPONSE_MP)
            return
    await bot.process_commands(message)


@bot.event
async def on_ready() -> None:
    log.info("Connecté en tant que %s", bot.user)
    if not envoi_quotidien.is_running():
        envoi_quotidien.start()
    log.info("Envoi quotidien programmé à %s (Europe/Paris)", SEND_AT.strftime("%H:%M"))
    if WEEKLY_ENABLED and not envoi_hebdomadaire.is_running():
        envoi_hebdomadaire.start()
        log.info(
            "Aperçu hebdomadaire programmé le %s à %s (Europe/Paris)",
            _JOURS[WEEKLY_DAY],
            WEEKLY_AT.strftime("%H:%M"),
        )


if __name__ == "__main__":
    bot.run(TOKEN)

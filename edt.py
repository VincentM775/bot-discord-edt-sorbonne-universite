"""Récupération et formatage de l'emploi du temps depuis le serveur CalDAV
de l'UFR Info P6 (Jussieu). Aucune dépendance à Discord ici : ce module est
testable seul (voir `python edt.py`)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import requests
import recurring_ical_events
from icalendar import Calendar

PARIS = ZoneInfo("Europe/Paris")

# Requête REPORT CalDAV : on demande les VEVENT chevauchant une plage de temps.
# On expanse les récurrences côté client (recurring_ical_events) pour ne pas
# dépendre du support serveur de <expand>.
_REPORT_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><c:calendar-data/></d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="{start}" end="{end}"/>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""


@dataclass
class Cours:
    debut: dt.datetime
    fin: dt.datetime
    titre: str
    lieu: str

    @property
    def horaire(self) -> str:
        return f"{self.debut.strftime('%H:%M')} – {self.fin.strftime('%H:%M')}"


def _iter_calendar_data(xml_bytes: bytes):
    """Extrait chaque bloc VCALENDAR de la réponse multistatus CalDAV."""
    import xml.etree.ElementTree as ET

    ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
    root = ET.fromstring(xml_bytes)
    for cal_data in root.iter("{urn:ietf:params:xml:ns:caldav}calendar-data"):
        if cal_data.text:
            yield cal_data.text


def _report(
    url: str,
    user: str,
    password: str,
    debut: dt.datetime,
    fin: dt.datetime,
    timeout: int,
) -> list[str]:
    """Envoie le REPORT CalDAV et retourne les blocs VCALENDAR bruts (ICS)."""
    body = _REPORT_TEMPLATE.format(
        start=debut.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        end=fin.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    resp = requests.request(
        "REPORT",
        url,
        auth=(user, password),
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        data=body.encode("utf-8"),
        timeout=timeout,
    )
    resp.raise_for_status()
    return list(_iter_calendar_data(resp.content))


def _cours_du_jour(ics_texts: list[str], jour: dt.date) -> list[Cours]:
    """Extrait, depuis des blocs ICS, les cours d'un jour donné (récurrences
    expansées), triés par heure de début."""
    cours: list[Cours] = []
    for ics_text in ics_texts:
        cal = Calendar.from_ical(ics_text)
        events = recurring_ical_events.of(cal).between(
            dt.datetime.combine(jour, dt.time.min, PARIS),
            dt.datetime.combine(jour, dt.time.max, PARIS),
        )
        for ev in events:
            debut = ev.get("DTSTART").dt
            fin_prop = ev.get("DTEND")
            fin = fin_prop.dt if fin_prop else debut

            # Ignore les événements "journée entière" (date sans heure).
            if not isinstance(debut, dt.datetime):
                continue

            debut = debut.astimezone(PARIS)
            fin = fin.astimezone(PARIS) if isinstance(fin, dt.datetime) else debut

            titre = str(ev.get("SUMMARY", "(sans titre)")).replace("\\n", " ").strip()
            lieu = str(ev.get("LOCATION", "")).replace("\\n", " ").strip()
            cours.append(Cours(debut=debut, fin=fin, titre=titre, lieu=lieu))

    cours.sort(key=lambda c: c.debut)
    return cours


def fetch_cours(
    url: str,
    user: str,
    password: str,
    jour: dt.date,
    timeout: int = 60,
) -> list[Cours]:
    """Retourne les cours d'un jour donné, triés par heure de début."""
    # Fenêtre large (marge d'un jour) pour capter les événements récurrents,
    # on filtrera précisément ensuite.
    debut = dt.datetime.combine(jour - dt.timedelta(days=1), dt.time.min, PARIS)
    fin = dt.datetime.combine(jour + dt.timedelta(days=2), dt.time.min, PARIS)
    ics_texts = _report(url, user, password, debut, fin, timeout)
    return _cours_du_jour(ics_texts, jour)


def fetch_semaine(
    url: str,
    user: str,
    password: str,
    lundi: dt.date,
    nb_jours: int = 7,
    timeout: int = 90,
) -> dict[dt.date, list[Cours]]:
    """Retourne les cours de la semaine sous forme {date: [Cours]}, en une seule
    requête. `lundi` est le premier jour ; `nb_jours` le nombre de jours couverts."""
    debut = dt.datetime.combine(lundi - dt.timedelta(days=1), dt.time.min, PARIS)
    fin = dt.datetime.combine(lundi + dt.timedelta(days=nb_jours + 1), dt.time.min, PARIS)
    ics_texts = _report(url, user, password, debut, fin, timeout)
    return {
        (jour := lundi + dt.timedelta(days=i)): _cours_du_jour(ics_texts, jour)
        for i in range(nb_jours)
    }


if __name__ == "__main__":
    # Petit test manuel : affiche les cours de demain.
    import os

    from dotenv import load_dotenv

    load_dotenv()
    demain = dt.datetime.now(PARIS).date() + dt.timedelta(days=1)
    liste = fetch_cours(
        os.environ.get(
            "CALDAV_URL",
            "https://cal.ufr-info-p6.jussieu.fr:443/caldav.php/RES/M1_RES-ITESCIA/",
        ),
        os.environ.get("CALDAV_USER", "student.master"),
        os.environ.get("CALDAV_PASSWORD", "guest"),
        demain,
    )
    print(f"{len(liste)} cours le {demain:%A %d/%m/%Y}")
    for c in liste:
        print(f"  {c.horaire}  {c.titre}  @ {c.lieu}")

    # Aperçu de la semaine en cours (lundi -> dimanche).
    url = os.environ.get(
        "CALDAV_URL",
        "https://cal.ufr-info-p6.jussieu.fr:443/caldav.php/RES/M1_RES-ITESCIA/",
    )
    aujourdhui = dt.datetime.now(PARIS).date()
    lundi = aujourdhui - dt.timedelta(days=aujourdhui.weekday())
    print(f"\n--- Semaine du {lundi:%d/%m/%Y} ---")
    for jour, cs in fetch_semaine(
        url,
        os.environ.get("CALDAV_USER", "student.master"),
        os.environ.get("CALDAV_PASSWORD", "guest"),
        lundi,
    ).items():
        print(f"{jour:%A %d/%m} : {len(cs)} cours")
        for c in cs:
            print(f"  {c.horaire}  {c.titre}  @ {c.lieu}")

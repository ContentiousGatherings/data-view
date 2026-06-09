"""
Database queries for pilot dataset extraction.

Finds AuthoritativeEvents linked to matching MeetingTypes via the
Event → EventMatch chain, then resolves all related entities.
"""

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, create_engine, select
from tqdm import tqdm

# Add parent directory to path to import db_model
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db_model import (
    Article,
    AuthoritativeActor,
    AuthoritativeEvent,
    AuthoritativeEventActor,
    AuthoritativeLocation,
    AuthoritativeMeetingType,
    Event,
    EventMatch,
    MeetingType,
    MeetingTypeMatch,
)

# Search term definitions: (label, SQL LIKE patterns)
SEARCH_TERMS = [
    ("folkmöte", ["%folkmöte%"]),
    ("första maj", ["%majdemonstration%", "%1majdemonstration%", "%majfest%", "%majfirande%", "%demonstration%"]),
]


@dataclass
class PilotRow:
    """One row in the pilot dataset, representing an AuthoritativeEvent."""

    auth_event_id: int
    site_url: str | None = None
    datum: str | None = None
    kategori: str | None = None
    ort: str | None = None
    ort_id: int | None = None
    lan: str | None = None
    aktorer: str | None = None
    aktor_idn: str | None = None
    textutdrag: str | None = None
    lankar: str | None = None
    publiceringsdatum: str | None = None
    tidning: str | None = None
    kall_event_idn: str | None = None
    artikel_idn: str | None = None
    meetingtype_idn: str | None = None
    sokord: str | None = None
    kallor: int = 0


def extract_pilot_data(
    db_path: str,
    usable_only: bool = False,
    terms: list[str] | None = None,
) -> list[PilotRow]:
    """Extract pilot dataset rows from the database.

    Args:
        terms: If provided, only use search terms whose labels are in this list.

    Returns a list of PilotRow sorted by date.
    """
    engine = create_engine(f"sqlite:///{db_path}")

    active_terms = SEARCH_TERMS
    if terms:
        active_terms = [(l, p) for l, p in SEARCH_TERMS if l in terms]

    with Session(engine) as session:
        # Step 1: Find AuthoritativeEvent IDs per search term via JOINs
        # Maps auth_event_id → set of search term labels
        auth_event_terms: dict[int, set[str]] = defaultdict(set)
        # Maps auth_event_id → set of source event IDs that matched
        auth_event_sources: dict[int, set[int]] = defaultdict(set)
        # Maps auth_event_id → set of matching AuthoritativeMeetingType IDs
        auth_event_amt_ids: dict[int, set[int]] = defaultdict(set)

        for label, patterns in active_terms:
            for pattern in patterns:
                # JOIN: AuthoritativeMeetingType → MeetingTypeMatch → MeetingType → Event → EventMatch
                stmt = (
                    select(
                        EventMatch.authoritative_event_id,
                        EventMatch.event_id,
                        AuthoritativeMeetingType.id,
                    )
                    .join(Event, EventMatch.event_id == Event.id)
                    .join(MeetingType, Event.type_id == MeetingType.id)
                    .join(
                        MeetingTypeMatch,
                        MeetingTypeMatch.meetingtype_id == MeetingType.id,
                    )
                    .join(
                        AuthoritativeMeetingType,
                        MeetingTypeMatch.authoritative_meetingtype_id
                        == AuthoritativeMeetingType.id,
                    )
                    .where(AuthoritativeMeetingType.name.ilike(pattern))
                    .where(MeetingTypeMatch.accepted == True)
                    .where(EventMatch.authoritative_event_id.isnot(None))
                )
                results = session.exec(stmt).all()
                for ae_id, event_id, amt_id in results:
                    auth_event_terms[ae_id].add(label)
                    auth_event_sources[ae_id].add(event_id)
                    auth_event_amt_ids[ae_id].add(amt_id)

            matched = sum(1 for ae, terms in auth_event_terms.items() if label in terms)
            print(f"  '{label}': {matched} AuthoritativeEvents")

        print(
            f"\n  Total unique AuthoritativeEvents found: {len(auth_event_terms)}"
        )

        # Step 2: Batch-fetch AuthoritativeEvents
        auth_event_ids = sorted(auth_event_terms.keys())
        ae_map: dict[int, AuthoritativeEvent] = {}
        for ae in session.exec(
            select(AuthoritativeEvent).where(
                AuthoritativeEvent.id.in_(auth_event_ids)
            )
        ).all():
            if usable_only and ae.use is False:
                continue
            ae_map[ae.id] = ae

        # Batch-fetch AuthoritativeMeetingTypes
        all_amt_ids = {amid for ids in auth_event_amt_ids.values() for amid in ids}
        amt_map: dict[int, AuthoritativeMeetingType] = {}
        if all_amt_ids:
            for amt in session.exec(
                select(AuthoritativeMeetingType).where(
                    AuthoritativeMeetingType.id.in_(all_amt_ids)
                )
            ).all():
                amt_map[amt.id] = amt

        # Batch-fetch locations
        loc_ids = {
            ae.authoritative_location_id
            for ae in ae_map.values()
            if ae.authoritative_location_id
        }
        loc_map: dict[int, AuthoritativeLocation] = {}
        if loc_ids:
            for loc in session.exec(
                select(AuthoritativeLocation).where(
                    AuthoritativeLocation.id.in_(loc_ids)
                )
            ).all():
                loc_map[loc.id] = loc

        # Batch-fetch actors per AuthoritativeEvent
        ae_actor_links = session.exec(
            select(AuthoritativeEventActor).where(
                AuthoritativeEventActor.authoritative_event_id.in_(ae_map.keys())
            )
        ).all()
        actor_ids = {link.authoritative_actor_id for link in ae_actor_links}
        actor_map: dict[int, AuthoritativeActor] = {}
        if actor_ids:
            for actor in session.exec(
                select(AuthoritativeActor).where(
                    AuthoritativeActor.id.in_(actor_ids)
                )
            ).all():
                actor_map[actor.id] = actor
        # Group by auth_event_id
        ae_actors_grouped: dict[int, list[AuthoritativeActor]] = defaultdict(list)
        for link in ae_actor_links:
            actor = actor_map.get(link.authoritative_actor_id)
            if actor:
                ae_actors_grouped[link.authoritative_event_id].append(actor)

        # Batch-fetch all source events via EventMatch
        all_em = session.exec(
            select(EventMatch.authoritative_event_id, EventMatch.event_id).where(
                EventMatch.authoritative_event_id.in_(ae_map.keys())
            )
        ).all()
        ae_all_sources: dict[int, set[int]] = defaultdict(set)
        all_event_ids: set[int] = set()
        for ae_id, event_id in all_em:
            ae_all_sources[ae_id].add(event_id)
            all_event_ids.add(event_id)

        # Batch-fetch Events
        event_map: dict[int, Event] = {}
        if all_event_ids:
            for ev in session.exec(
                select(Event).where(Event.id.in_(all_event_ids))
            ).all():
                event_map[ev.id] = ev

        # Batch-fetch Articles
        article_uuids = {
            ev.article_id for ev in event_map.values() if ev.article_id
        }
        article_map: dict[str, Article] = {}
        if article_uuids:
            for art in session.exec(
                select(Article).where(Article.id.in_(article_uuids))
            ).all():
                article_map[str(art.id)] = art

        # Step 3: Build rows
        rows: list[PilotRow] = []
        for ae_id in tqdm(sorted(ae_map.keys()), desc="Building rows"):
            auth_event = ae_map[ae_id]
            row = PilotRow(auth_event_id=ae_id)
            row.site_url = f"https://contentiousgatherings.github.io/data-view/authoritativeevent/{ae_id}/"

            # Datum
            if auth_event.event_date_start:
                row.datum = auth_event.event_date_start.strftime("%Y-%m-%d")

            # Kategori — from matched AuthoritativeMeetingTypes
            amt_ids = auth_event_amt_ids.get(ae_id, set())
            amt_names = sorted({amt_map[a].name for a in amt_ids if a in amt_map})
            if amt_names:
                row.kategori = "; ".join(amt_names)

            # Location
            if auth_event.authoritative_location_id:
                auth_loc = loc_map.get(auth_event.authoritative_location_id)
                if auth_loc:
                    row.ort = auth_loc.name
                    row.ort_id = auth_loc.id
                    row.lan = auth_loc.county

            # Aktörer
            actors = ae_actors_grouped.get(ae_id, [])
            if actors:
                row.aktorer = "; ".join(a.name for a in actors)
                row.aktor_idn = "; ".join(str(a.id) for a in actors)

            # Source event data
            source_ids = ae_all_sources.get(ae_id, set())
            matched_source_ids = auth_event_sources.get(ae_id, set())

            excerpts = []
            urls = []
            journals = []
            article_ids_list = []
            pub_dates = []

            for src_id in sorted(source_ids):
                event = event_map.get(src_id)
                if event is None:
                    continue
                if event.excerpt:
                    excerpts.append(event.excerpt)
                if event.article_id:
                    article = article_map.get(str(event.article_id))
                    if article:
                        article_ids_list.append(str(article.id))
                        if article.url:
                            url = article.url.replace("_alto.xml", ".jp2")
                            urls.append(url)
                        if article.journal:
                            journals.append(article.journal)
                        if article.date_published:
                            pub_dates.append(
                                article.date_published.strftime("%Y-%m-%d")
                            )

            if excerpts:
                seen = set()
                unique = []
                for e in excerpts:
                    if e not in seen:
                        seen.add(e)
                        unique.append(e)
                row.textutdrag = "\n-------------\n".join(unique)
            if urls:
                row.lankar = "; ".join(dict.fromkeys(urls))
            if pub_dates:
                row.publiceringsdatum = "; ".join(dict.fromkeys(pub_dates))
            if journals:
                row.tidning = "; ".join(dict.fromkeys(journals))
            if article_ids_list:
                row.artikel_idn = "; ".join(dict.fromkeys(article_ids_list))

            # Source event and MeetingType IDs
            row.kall_event_idn = "; ".join(
                str(i) for i in sorted(matched_source_ids)
            )
            amt_ids = auth_event_amt_ids.get(ae_id, set())
            if amt_ids:
                row.meetingtype_idn = "; ".join(str(i) for i in sorted(amt_ids))

            # Sökord
            terms = auth_event_terms.get(ae_id, set())
            row.sokord = "; ".join(sorted(terms))

            # Källor
            row.kallor = auth_event.source_event_count

            rows.append(row)

        # Sort by date
        rows.sort(key=lambda r: r.datum or "")

    return rows

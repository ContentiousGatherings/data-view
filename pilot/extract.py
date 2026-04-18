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
    Actor,
    Article,
    AuthoritativeActor,
    AuthoritativeEvent,
    AuthoritativeEventActor,
    AuthoritativeLocation,
    Event,
    EventMatch,
    MeetingType,
)

# Search term definitions: (label, SQL LIKE patterns)
SEARCH_TERMS = [
    ("folkmöte", ["%folkmöte%"]),
    ("förstamaj-tåg", ["%förstamaj%tåg%", "%första maj%tåg%"]),
]


@dataclass
class PilotRow:
    """One row in the pilot dataset, representing an AuthoritativeEvent."""

    auth_event_id: int
    datum: str | None = None
    kategori: str | None = None
    ort: str | None = None
    ort_id: int | None = None
    lan: str | None = None
    aktorer: str | None = None
    aktor_idn: str | None = None
    textutdrag: str | None = None
    lankar: str | None = None
    tidning: str | None = None
    kall_event_idn: str | None = None
    artikel_idn: str | None = None
    meetingtype_idn: str | None = None
    sokord: str | None = None
    kallor: int = 0


def extract_pilot_data(
    db_path: str, usable_only: bool = False
) -> list[PilotRow]:
    """Extract pilot dataset rows from the database.

    Returns a list of PilotRow sorted by date.
    """
    engine = create_engine(f"sqlite:///{db_path}")

    with Session(engine) as session:
        # Step 1: Find AuthoritativeEvent IDs per search term
        # Maps auth_event_id → set of search term labels
        auth_event_terms: dict[int, set[str]] = defaultdict(set)
        # Maps auth_event_id → set of source event IDs that matched
        auth_event_sources: dict[int, set[int]] = defaultdict(set)
        # Maps auth_event_id → set of matching MeetingType IDs
        auth_event_mt_ids: dict[int, set[int]] = defaultdict(set)

        for label, patterns in SEARCH_TERMS:
            # Find matching MeetingTypes
            matching_mt_ids = set()
            for pattern in patterns:
                stmt = select(MeetingType.id).where(
                    MeetingType.name.ilike(pattern)
                )
                matching_mt_ids.update(session.exec(stmt).all())

            if not matching_mt_ids:
                print(f"  No MeetingTypes found for '{label}'")
                continue

            print(f"  Found {len(matching_mt_ids)} MeetingTypes for '{label}'")

            # Find Events with those MeetingTypes
            event_ids = set()
            for mt_id in matching_mt_ids:
                stmt = select(Event.id).where(Event.type_id == mt_id)
                event_ids.update(session.exec(stmt).all())

            if not event_ids:
                print(f"  No Events found for '{label}'")
                continue

            print(f"  Found {len(event_ids)} Events for '{label}'")

            # Trace Events → EventMatch → AuthoritativeEvent
            for event_id in event_ids:
                stmt = select(EventMatch).where(EventMatch.event_id == event_id)
                matches = session.exec(stmt).all()
                for match in matches:
                    if match.authoritative_event_id is not None:
                        auth_event_terms[match.authoritative_event_id].add(label)
                        auth_event_sources[match.authoritative_event_id].add(event_id)
                        # Find which MT IDs this event used
                        event = session.get(Event, event_id)
                        if event and event.type_id in matching_mt_ids:
                            auth_event_mt_ids[match.authoritative_event_id].add(
                                event.type_id
                            )

        print(
            f"\n  Total unique AuthoritativeEvents found: {len(auth_event_terms)}"
        )

        # Step 2: Build rows
        rows: list[PilotRow] = []
        auth_event_ids = sorted(auth_event_terms.keys())

        for ae_id in tqdm(auth_event_ids, desc="Resolving AuthoritativeEvents"):
            auth_event = session.get(AuthoritativeEvent, ae_id)
            if auth_event is None:
                continue

            if usable_only and auth_event.use is False:
                continue

            row = PilotRow(auth_event_id=ae_id)

            # Datum
            if auth_event.event_date_start:
                row.datum = auth_event.event_date_start.strftime("%Y-%m-%d")

            # Kategori
            row.kategori = auth_event.category

            # Location (Ort, Län)
            if auth_event.authoritative_location_id:
                auth_loc = session.get(
                    AuthoritativeLocation, auth_event.authoritative_location_id
                )
                if auth_loc:
                    row.ort = auth_loc.name
                    row.ort_id = auth_loc.id
                    row.lan = auth_loc.county

            # Aktörer (via AuthoritativeEventActor → AuthoritativeActor)
            stmt = select(AuthoritativeEventActor).where(
                AuthoritativeEventActor.authoritative_event_id == ae_id
            )
            ae_actors = session.exec(stmt).all()
            actor_names = []
            actor_ids = []
            for ae_actor in ae_actors:
                auth_actor = session.get(
                    AuthoritativeActor, ae_actor.authoritative_actor_id
                )
                if auth_actor:
                    actor_names.append(auth_actor.name)
                    actor_ids.append(str(auth_actor.id))
            if actor_names:
                row.aktorer = "; ".join(actor_names)
                row.aktor_idn = "; ".join(actor_ids)

            # Source event data (excerpts, URLs, journals)
            source_event_ids = auth_event_sources.get(ae_id, set())
            # Also include all source events from EventMatch, not just the
            # ones that matched the search term
            stmt = select(EventMatch.event_id).where(
                EventMatch.authoritative_event_id == ae_id
            )
            all_source_ids = set(session.exec(stmt).all())
            # Use the matched ones for traceability
            matched_source_ids = source_event_ids

            excerpts = []
            urls = []
            journals = []
            article_ids = []

            for src_id in sorted(all_source_ids):
                event = session.get(Event, src_id)
                if event is None:
                    continue
                if event.excerpt:
                    excerpts.append(event.excerpt)
                if event.article_id:
                    article = session.get(Article, event.article_id)
                    if article:
                        article_ids.append(str(article.id))
                        if article.url:
                            urls.append(article.url)
                        if article.journal:
                            journals.append(article.journal)

            if excerpts:
                # Deduplicate while preserving order
                seen = set()
                unique = []
                for e in excerpts:
                    if e not in seen:
                        seen.add(e)
                        unique.append(e)
                row.textutdrag = " ||| ".join(unique)
            if urls:
                row.lankar = "; ".join(dict.fromkeys(urls))
            if journals:
                row.tidning = "; ".join(dict.fromkeys(journals))
            if article_ids:
                row.artikel_idn = "; ".join(dict.fromkeys(article_ids))

            # Source event and MeetingType IDs
            row.kall_event_idn = "; ".join(
                str(i) for i in sorted(matched_source_ids)
            )
            mt_ids = auth_event_mt_ids.get(ae_id, set())
            if mt_ids:
                row.meetingtype_idn = "; ".join(str(i) for i in sorted(mt_ids))

            # Sökord
            terms = auth_event_terms.get(ae_id, set())
            row.sokord = "; ".join(sorted(terms))

            # Källor
            row.kallor = auth_event.source_event_count

            rows.append(row)

        # Sort by date
        rows.sort(key=lambda r: r.datum or "")

    return rows

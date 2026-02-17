#!/usr/bin/env python3
"""
Static site generator for pipeline validation review.

Generates browsable HTML pages for Events and Entities, with pre-filled
GitHub issue links for colleagues to suggest corrections.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader
from sqlmodel import Session, create_engine, select
from tqdm import tqdm

# Add parent directory to path to import db_model
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db_model import (
    Actor,
    ActorAlias,
    Article,
    AuthoritativeActor,
    AuthoritativeEvent,
    AuthoritativeEventActor,
    AuthoritativeLocation,
    AuthoritativeMeetingType,
    Event,
    EventMatch,
    Location,
    MeetingType,
    MeetingTypeMatch,
    SplitActor,
    SplitActorMatch,
    SplitLocation,
    SplitLocationMatch,
    TimeStamp,
)


def get_status(record: Any) -> str:
    """Determine the validation status of a record."""
    if hasattr(record, "blocked") and record.blocked:
        return "blocked"
    if hasattr(record, "use"):
        if record.use is True:
            return "valid"
        elif record.use is False:
            return "invalid"
    if hasattr(record, "accepted"):
        if record.accepted is True:
            return "valid"
        elif record.accepted is False:
            return "invalid"
    if hasattr(record, "needs_review"):
        if record.needs_review is False:
            return "valid"
        else:
            return "unknown"
    if hasattr(record, "matching_datetime"):
        if record.matching_datetime is not None:
            return "valid"
    if hasattr(record, "reviewed_date"):
        if record.reviewed_date is not None:
            return "valid"
        else:
            return "unknown"
    return "unknown"


def get_status_reason(record: Any) -> str | None:
    """Get the reason for the status."""
    if hasattr(record, "blocked") and record.blocked:
        return getattr(record, "block_reason", None)
    if hasattr(record, "use") and record.use is False:
        return getattr(record, "unuse_reason", None)
    if hasattr(record, "accepted") and record.accepted is not None:
        return getattr(record, "accepted_reason", None)
    return None


def make_issue_url(
    repo: str,
    table: str,
    record_id: int,
    context: dict,
    generated_at: str,
    action: str = "report",
) -> str:
    """Generate a GitHub issue URL with pre-filled content.

    Actions: mark_valid, mark_unusable, mark_blocked, report.
    """
    ACTION_CONFIG = {
        "mark_valid": {
            "prefix": "[Valid]",
            "json": {"table": table, "id": record_id, "action": "mark_valid", "reviewer": ""},
        },
        "mark_unusable": {
            "prefix": "[Invalid]",
            "json": {
                "table": table,
                "id": record_id,
                "action": "mark_unusable",
                "reason": "EDIT THIS: Describe why this should be removed",
                "reviewer": "",
            },
        },
        "mark_blocked": {
            "prefix": "[Block]",
            "json": {
                "table": table,
                "id": record_id,
                "action": "mark_blocked",
                "reason": "EDIT THIS: Describe why this is blocked",
                "reviewer": "",
            },
        },
        "report": {
            "prefix": "[Report]",
            "json": {
                "table": table,
                "id": record_id,
                "action": "report",
                "description": "EDIT THIS: Describe the problem",
                "reviewer": "",
            },
        },
    }

    cfg = ACTION_CONFIG.get(action, ACTION_CONFIG["report"])
    title = f"{cfg['prefix']} {table}/{record_id}"
    json_block = json.dumps(cfg["json"], indent=2)

    if action == "report":
        # Shorter body for general reports — no detailed context section
        body = f"""<!-- EDIT JSON BELOW - Keep the code fence markers -->
```json
{json_block}
```

---
*Page: /{table}/{record_id}/*
*Site generated: {generated_at}*
*Submit this issue to log your correction.*
"""
    else:
        # Full body with reference context
        context_lines = []
        for key, value in context.items():
            if value is not None:
                str_value = str(value)
                if len(str_value) > 200:
                    str_value = str_value[:200] + "..."
                context_lines.append(f"- **{key}:** {str_value}")
        context_md = "\n".join(context_lines)

        body = f"""<!-- EDIT JSON BELOW - Keep the code fence markers -->
```json
{json_block}
```

### Reference (do not edit below this line)
{context_md}

---
*Page: /{table}/{record_id}/*
*Site generated: {generated_at}*
*Submit this issue to log your correction.*
"""

    # GitHub has URL length limits (~8000 chars), truncate body if needed
    if len(body) > 1800:
        body = body[:1800] + "\n\n(truncated)"

    return (
        f"https://github.com/{repo}/issues/new?title={quote(title)}&body={quote(body)}"
    )


class SiteGenerator:
    def __init__(
        self,
        db_path: str,
        repo: str,
        output_dir: str,
        base_url: str = "",
    ):
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.repo = repo
        self.base_url = base_url.rstrip("/")

        # Generation timestamp
        self.generated_at = datetime.now(timezone.utc)
        self.generated_at_str = self.generated_at.strftime("%Y-%m-%d %H:%M UTC")

        # Set up Jinja2
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True,
        )

        # Add custom filters and globals
        self.env.filters["get_status"] = get_status
        self.env.filters["get_status_reason"] = get_status_reason
        self.env.globals["make_issue_url"] = lambda table, id, ctx, action="report": make_issue_url(
            self.repo, table, id, ctx, self.generated_at_str, action=action
        )
        self.env.globals["generated_at"] = self.generated_at_str
        self.env.globals["base_url"] = self.base_url

        # Database engine
        self.engine = create_engine(f"sqlite:///{db_path}")

    def generate(self):
        """Generate the entire static site."""
        print(f"Generating site from {self.db_path}")
        print(f"Output directory: {self.output_dir}")

        # Create output directories
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Copy static files
        self._copy_static_files()

        # Generate pages
        with Session(self.engine) as session:
            stats = self._generate_all_pages(session)

        # Generate index
        self._generate_index(stats)

        print(f"Site generated successfully at {self.output_dir}")

    def _copy_static_files(self):
        """Copy CSS and other static files."""
        static_src = Path(__file__).parent / "static"
        static_dst = self.output_dir / "static"
        if static_src.exists():
            if static_dst.exists():
                shutil.rmtree(static_dst)
            shutil.copytree(static_src, static_dst)

    def _generate_all_pages(self, session: Session) -> dict:
        """Generate all entity pages and return statistics."""
        stats = {}
        all_entities = {}  # Store for list page generation

        # Entity type configurations
        entity_configs = [
            ("event", Event, "event.html", "Events", "excerpt", None),
            ("location", Location, "location.html", "Locations", "name", "country"),
            (
                "splitlocation",
                SplitLocation,
                "splitlocation.html",
                "Split Locations",
                "name",
                "country",
            ),
            ("actor", Actor, "actor.html", "Actors", "name", "description"),
            (
                "splitactor",
                SplitActor,
                "splitactor.html",
                "Split Actors",
                "name",
                "actor_type",
            ),
            ("timestamp", TimeStamp, "timestamp.html", "Timestamps", "when", None),
            (
                "meetingtype",
                MeetingType,
                "meetingtype.html",
                "Meeting Types",
                "name",
                "category",
            ),
            (
                "authoritativeevent",
                AuthoritativeEvent,
                "authoritativeevent.html",
                "Authoritative Events",
                "canonical_name",
                "category",
            ),
            (
                "eventmatch",
                EventMatch,
                "eventmatch.html",
                "Event Matches",
                "composite_score",
                "algorithm",
            ),
            (
                "authoritativelocation",
                AuthoritativeLocation,
                "authoritativelocation.html",
                "Authoritative Locations",
                "name",
                "county",
            ),
            (
                "splitlocationmatch",
                SplitLocationMatch,
                "splitlocationmatch.html",
                "Split Location Matches",
                "confidence_score",
                "algorithm",
            ),
            (
                "authoritativeactor",
                AuthoritativeActor,
                "authoritativeactor.html",
                "Authoritative Actors",
                "name",
                "actor_type",
            ),
            (
                "actoralias",
                ActorAlias,
                "actoralias.html",
                "Actor Aliases",
                "alias",
                "alias_normalized",
            ),
            (
                "splitactormatch",
                SplitActorMatch,
                "splitactormatch.html",
                "Split Actor Matches",
                "confidence_score",
                "algorithm",
            ),
            (
                "authoritativemeetingtype",
                AuthoritativeMeetingType,
                "authoritativemeetingtype.html",
                "Authoritative Meeting Types",
                "name",
                "category",
            ),
            (
                "meetingtypematch",
                MeetingTypeMatch,
                "meetingtypematch.html",
                "Meeting Type Matches",
                "confidence_score",
                "algorithm",
            ),
            (
                "authoritativeeventactor",
                AuthoritativeEventActor,
                "authoritativeeventactor.html",
                "Authoritative Event Actors",
                "role",
                "source_event_count",
            ),
        ]

        # Custom queries: filter entity types that are too large unfiltered
        custom_queries = {
            "authoritativelocation": select(AuthoritativeLocation).where(
                AuthoritativeLocation.id.in_(
                    select(SplitLocationMatch.authoritative_location_id).distinct()
                )
            ),
        }

        for (
            entity_type,
            model,
            template,
            display_name,
            primary_field,
            secondary_field,
        ) in entity_configs:

            query = custom_queries.get(entity_type, select(model))
            entities = session.exec(query).all()
            all_entities[entity_type] = {
                "entities": entities,
                "display_name": display_name,
                "primary_field": primary_field,
                "secondary_field": secondary_field,
            }
            stats[entity_type] = self._generate_entity_pages(
                session, entities, entity_type, template
            )

        # Generate list pages
        self._generate_list_pages(all_entities, stats)

        return stats

    def _generate_list_pages(self, all_entities: dict, stats: dict):
        """Generate paginated list/browse pages for each entity type."""
        list_template = self.env.get_template("list.html")
        page_size = 200

        # Field labels for display
        field_labels = {
            "excerpt": "Excerpt",
            "name": "Name",
            "when": "When",
            "country": "Country",
            "description": "Description",
            "category": "Category",
            "actor_type": "Type",
            "canonical_name": "Canonical Name",
            "composite_score": "Composite Score",
            "algorithm": "Algorithm",
            "county": "County",
            "alias": "Alias",
            "alias_normalized": "Normalized",
            "confidence_score": "Confidence Score",
            "role": "Role",
            "source_event_count": "Source Events",
        }

        # Extra grouping column for match tables
        group_fields = {
            "splitlocationmatch": ("split_location_id", "Split Location"),
        }

        for entity_type, data in all_entities.items():
            entities = data["entities"]
            group_field, group_field_label = group_fields.get(entity_type, (None, None))

            # Chunk entities into pages
            chunks = [
                entities[i : i + page_size]
                for i in range(0, max(len(entities), 1), page_size)
            ]
            if not chunks:
                chunks = [[]]

            # Build page descriptors
            pages = []
            for page_idx, chunk in enumerate(chunks):
                start = page_idx * page_size + 1
                end = start + len(chunk) - 1
                label = f"{start}-{end}" if len(chunk) > 0 else "0"
                if page_idx == 0:
                    path = f"/{entity_type}/"
                else:
                    path = f"/{entity_type}/{start}-{end}/"
                pages.append(
                    {"label": label, "path": path, "is_current": False}
                )

            # Render each page
            for page_idx, chunk in enumerate(chunks):
                pages_for_render = [
                    {**p, "is_current": i == page_idx} for i, p in enumerate(pages)
                ]

                html = list_template.render(
                    entity_type=entity_type,
                    entity_type_display=data["display_name"],
                    entities=chunk,
                    counts=stats[entity_type],
                    primary_field=data["primary_field"],
                    primary_field_label=field_labels.get(
                        data["primary_field"], data["primary_field"]
                    ),
                    secondary_field=data["secondary_field"],
                    secondary_field_label=(
                        field_labels.get(data["secondary_field"])
                        if data["secondary_field"]
                        else None
                    ),
                    group_field=group_field,
                    group_field_label=group_field_label,
                    pages=pages_for_render,
                )

                # First page → entity_type/index.html
                # Subsequent → entity_type/{start}-{end}/index.html
                if page_idx == 0:
                    list_dir = self.output_dir / entity_type
                else:
                    start = page_idx * page_size + 1
                    end = start + len(chunk) - 1
                    list_dir = self.output_dir / entity_type / f"{start}-{end}"
                list_dir.mkdir(parents=True, exist_ok=True)
                (list_dir / "index.html").write_text(html)

    def _generate_entity_pages(
        self,
        session: Session,
        entities: list,
        entity_type: str,
        template_name: str,
    ) -> dict:
        """Generate pages for a list of entities."""
        template = self.env.get_template(template_name)
        entity_dir = self.output_dir / entity_type
        entity_dir.mkdir(parents=True, exist_ok=True)

        counts = {"total": 0, "valid": 0, "invalid": 0, "blocked": 0, "unknown": 0}

        # Build ordered ID list for record navigation
        entity_ids = [e.id for e in entities]

        for i, entity in enumerate(
            tqdm(entities, desc=f"Generating {entity_type} pages")
        ):
            counts["total"] += 1
            status = get_status(entity)
            counts[status] += 1

            # Get related data based on entity type
            context = self._get_entity_context(session, entity, entity_type)

            # Build record navigation
            record_nav = {
                "first_id": entity_ids[0],
                "last_id": entity_ids[-1],
                "prev_id": entity_ids[i - 1] if i > 0 else None,
                "next_id": entity_ids[i + 1] if i < len(entity_ids) - 1 else None,
                "entity_type": entity_type,
            }

            # Render the page
            html = template.render(
                entity=entity,
                entity_type=entity_type,
                status=status,
                status_reason=get_status_reason(entity),
                record_nav=record_nav,
                **context,
            )

            # Write to file
            page_dir = entity_dir / str(entity.id)
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(html)

        # For match tables, recompute counts grouped by parent entity so that
        # e.g. 5 suggestions for one split location count as a single entry.
        if entity_type == "splitlocationmatch":
            counts = self._grouped_match_counts(
                entities, key=lambda e: e.split_location_id
            )

        return counts

    @staticmethod
    def _grouped_match_counts(entities: list, key) -> dict:
        """Count stats grouped by a parent key.

        Groups match records by key (e.g. split_location_id) and assigns each
        group a single status: "valid" if any match is accepted, "invalid" if
        all are explicitly rejected, "unknown" otherwise.
        """
        from collections import defaultdict

        groups: dict[int, list] = defaultdict(list)
        for entity in entities:
            groups[key(entity)].append(entity)

        counts = {"total": 0, "valid": 0, "invalid": 0, "blocked": 0, "unknown": 0}
        for members in groups.values():
            counts["total"] += 1
            statuses = [get_status(m) for m in members]
            if "valid" in statuses:
                counts["valid"] += 1
            elif all(s == "invalid" for s in statuses):
                counts["invalid"] += 1
            elif "blocked" in statuses:
                counts["blocked"] += 1
            else:
                counts["unknown"] += 1
        return counts

    def _get_entity_context(
        self, session: Session, entity: Any, entity_type: str
    ) -> dict:
        """Get related data for an entity."""
        context = {}

        if entity_type == "event":
            # Load related entities
            if entity.article_id:
                context["article"] = session.get(Article, entity.article_id)
            if entity.location_id:
                context["location"] = session.get(Location, entity.location_id)
            if entity.date_id:
                context["timestamp"] = session.get(TimeStamp, entity.date_id)
            if entity.type_id:
                context["meetingtype"] = session.get(MeetingType, entity.type_id)
            # Get actors for this event
            context["actors"] = session.exec(
                select(Actor).where(Actor.event_id == entity.id)
            ).all()
            # Get consolidation matches
            try:
                context["event_matches"] = session.exec(
                    select(EventMatch).where(EventMatch.event_id == entity.id)
                ).all()
            except Exception:
                context["event_matches"] = []

        elif entity_type == "location":
            # Get split locations
            context["split_locations"] = session.exec(
                select(SplitLocation).where(SplitLocation.location_id == entity.id)
            ).all()
            # Get events using this location
            context["events"] = session.exec(
                select(Event).where(Event.location_id == entity.id)
            ).all()

        elif entity_type == "splitlocation":
            # Get parent location
            if entity.location_id:
                context["parent_location"] = session.get(Location, entity.location_id)
            # Get matches (table might not exist)
            try:
                context["matches"] = session.exec(
                    select(SplitLocationMatch).where(
                        SplitLocationMatch.split_location_id == entity.id
                    )
                ).all()
                # Load authoritative locations for matches
                for match in tqdm(
                    context["matches"],
                    desc="Loading authoritative locations",
                    leave=False,
                ):
                    match.authoritative_location = session.get(
                        AuthoritativeLocation, match.authoritative_location_id
                    )
            except Exception:
                context["matches"] = []

        elif entity_type == "actor":
            # Get split actors
            context["split_actors"] = session.exec(
                select(SplitActor).where(SplitActor.actor_id == entity.id)
            ).all()
            # Get the event
            if entity.event_id:
                context["event"] = session.get(Event, entity.event_id)

        elif entity_type == "splitactor":
            # Get parent actor
            if entity.actor_id:
                context["parent_actor"] = session.get(Actor, entity.actor_id)
            # Get matches (table might not exist)
            try:
                context["matches"] = session.exec(
                    select(SplitActorMatch).where(
                        SplitActorMatch.split_actor_id == entity.id
                    )
                ).all()
                # Load authoritative actors for matches
                for match in tqdm(
                    context["matches"], desc="Loading authoritative actors", leave=False
                ):
                    match.authoritative_actor = session.get(
                        AuthoritativeActor, match.authoritative_actor_id
                    )
            except Exception:
                context["matches"] = []

        elif entity_type == "timestamp":
            # Get events using this timestamp
            context["events"] = session.exec(
                select(Event).where(Event.date_id == entity.id)
            ).all()

        elif entity_type == "meetingtype":
            # Get events using this meeting type
            context["events"] = session.exec(
                select(Event).where(Event.type_id == entity.id)
            ).all()
            # Get matches (table might not exist)
            try:
                context["matches"] = session.exec(
                    select(MeetingTypeMatch).where(
                        MeetingTypeMatch.meetingtype_id == entity.id
                    )
                ).all()
                # Load authoritative meeting types for matches
                for match in tqdm(
                    context["matches"],
                    desc="Loading authoritative meeting types",
                    leave=False,
                ):
                    match.authoritative_meetingtype = session.get(
                        AuthoritativeMeetingType, match.authoritative_meetingtype_id
                    )
            except Exception:
                context["matches"] = []

        elif entity_type == "authoritativeevent":
            # Get authoritative location
            if entity.authoritative_location_id:
                context["auth_location"] = session.get(
                    AuthoritativeLocation, entity.authoritative_location_id
                )
            # Get event matches with full source event details
            try:
                matches = session.exec(
                    select(EventMatch).where(
                        EventMatch.authoritative_event_id == entity.id
                    )
                ).all()
                source_events = []
                for match in matches:
                    event = session.get(Event, match.event_id)
                    se = {
                        "match": match,
                        "event": event,
                        "article": None,
                        "location": None,
                        "timestamp": None,
                        "meetingtype": None,
                        "actors": [],
                    }
                    if event:
                        if event.article_id:
                            se["article"] = session.get(Article, event.article_id)
                        if event.location_id:
                            se["location"] = session.get(Location, event.location_id)
                        if event.date_id:
                            se["timestamp"] = session.get(TimeStamp, event.date_id)
                        if event.type_id:
                            se["meetingtype"] = session.get(MeetingType, event.type_id)
                        se["actors"] = session.exec(
                            select(Actor).where(Actor.event_id == event.id)
                        ).all()
                    source_events.append(se)
                context["source_events"] = source_events
            except Exception:
                context["source_events"] = []
            # Get actors
            try:
                context["auth_actors"] = session.exec(
                    select(AuthoritativeEventActor).where(
                        AuthoritativeEventActor.authoritative_event_id == entity.id
                    )
                ).all()
                for aa in context["auth_actors"]:
                    aa.authoritative_actor = session.get(
                        AuthoritativeActor, aa.authoritative_actor_id
                    )
            except Exception:
                context["auth_actors"] = []

        elif entity_type == "eventmatch":
            # Get linked event and authoritative event
            if entity.event_id:
                context["event"] = session.get(Event, entity.event_id)
            if entity.authoritative_event_id:
                context["auth_event"] = session.get(
                    AuthoritativeEvent, entity.authoritative_event_id
                )

        elif entity_type == "authoritativelocation":
            # Get split location matches pointing to this auth location
            try:
                matches = session.exec(
                    select(SplitLocationMatch).where(
                        SplitLocationMatch.authoritative_location_id == entity.id
                    )
                ).all()
                for match in matches:
                    match.split_location = session.get(
                        SplitLocation, match.split_location_id
                    )
                context["matches"] = matches
            except Exception:
                context["matches"] = []

        elif entity_type == "splitlocationmatch":
            # Get linked split location and authoritative location
            if entity.split_location_id:
                context["split_location"] = session.get(
                    SplitLocation, entity.split_location_id
                )
            if entity.authoritative_location_id:
                context["auth_location"] = session.get(
                    AuthoritativeLocation, entity.authoritative_location_id
                )

        elif entity_type == "authoritativeactor":
            # Get aliases
            try:
                context["aliases"] = session.exec(
                    select(ActorAlias).where(
                        ActorAlias.authoritative_actor_id == entity.id
                    )
                ).all()
            except Exception:
                context["aliases"] = []
            # Get split actor matches
            try:
                matches = session.exec(
                    select(SplitActorMatch).where(
                        SplitActorMatch.authoritative_actor_id == entity.id
                    )
                ).all()
                for match in matches:
                    match.split_actor = session.get(SplitActor, match.split_actor_id)
                context["matches"] = matches
            except Exception:
                context["matches"] = []

        elif entity_type == "actoralias":
            # Get the authoritative actor
            if entity.authoritative_actor_id:
                context["auth_actor"] = session.get(
                    AuthoritativeActor, entity.authoritative_actor_id
                )

        elif entity_type == "splitactormatch":
            # Get linked split actor and authoritative actor
            if entity.split_actor_id:
                context["split_actor"] = session.get(SplitActor, entity.split_actor_id)
            if entity.authoritative_actor_id:
                context["auth_actor"] = session.get(
                    AuthoritativeActor, entity.authoritative_actor_id
                )

        elif entity_type == "authoritativemeetingtype":
            # Get meeting type matches
            try:
                matches = session.exec(
                    select(MeetingTypeMatch).where(
                        MeetingTypeMatch.authoritative_meetingtype_id == entity.id
                    )
                ).all()
                for match in matches:
                    match.meetingtype = session.get(MeetingType, match.meetingtype_id)
                context["matches"] = matches
            except Exception:
                context["matches"] = []

        elif entity_type == "meetingtypematch":
            # Get linked meeting type and authoritative meeting type
            if entity.meetingtype_id:
                context["meetingtype"] = session.get(MeetingType, entity.meetingtype_id)
            if entity.authoritative_meetingtype_id:
                context["auth_meetingtype"] = session.get(
                    AuthoritativeMeetingType, entity.authoritative_meetingtype_id
                )

        elif entity_type == "authoritativeeventactor":
            # Get linked authoritative event and actor
            if entity.authoritative_event_id:
                context["auth_event"] = session.get(
                    AuthoritativeEvent, entity.authoritative_event_id
                )
            if entity.authoritative_actor_id:
                context["auth_actor"] = session.get(
                    AuthoritativeActor, entity.authoritative_actor_id
                )

        return context

    def _generate_index(self, stats: dict):
        """Generate the index page with statistics."""
        template = self.env.get_template("index.html")

        html = template.render(
            stats=stats,
            # Rows for the index page layout
            entity_rows=[
                # Row 1: Event centered alone
                [("event", "Events")],
                # Row 2: placeholder for pipeline columns (handled separately)
                "pipeline",
                # Row 3: consolidation
                [
                    ("eventmatch", "Event Matches"),
                    ("authoritativeeventactor", "Auth. Event Actors"),
                ],
                # Row 4: AuthoritativeEvent centered alone
                [("authoritativeevent", "Authoritative Events")],
            ],
            # Pipeline columns: each data type as a vertical column
            pipeline_columns=[
                [
                    ("location", "Locations"),
                    ("splitlocation", "Split Locations"),
                    ("splitlocationmatch", "Location Matches"),
                    ("authoritativelocation", "Auth. Locations"),
                ],
                [
                    ("timestamp", "Timestamps"),
                ],
                [
                    ("actor", "Actors"),
                    ("splitactor", "Split Actors"),
                    ("splitactormatch", "Actor Matches"),
                    ("authoritativeactor", "Auth. Actors"),
                    ("actoralias", "Actor Aliases"),
                ],
                [
                    ("meetingtype", "Meeting Types"),
                    ("meetingtypematch", "Type Matches"),
                    ("authoritativemeetingtype", "Auth. Types"),
                ],
            ],
        )

        (self.output_dir / "index.html").write_text(html)


def main():
    parser = argparse.ArgumentParser(
        description="Generate static review site from pipeline database"
    )
    parser.add_argument(
        "--db",
        default="../alpha.db",
        help="Path to the SQLite database (default: ../alpha.db)",
    )
    parser.add_argument(
        "--output",
        default="./docs",
        help="Output directory for generated site (default: ./docs)",
    )
    parser.add_argument(
        "--repo",
        default="ContentiousGatherings/data-view",
        help="GitHub repository for issues (default: ContentiousGatherings/data-view)",
    )
    parser.add_argument(
        "--base-url",
        default="/data-view",
        help="Base URL path prefix for GitHub Pages (default: /data-view)",
    )

    args = parser.parse_args()

    # Resolve paths
    db_path = os.path.abspath(args.db)
    output_dir = os.path.abspath(args.output)

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    generator = SiteGenerator(
        db_path=db_path,
        output_dir=output_dir,
        repo=args.repo,
        base_url=args.base_url,
    )

    generator.generate()


if __name__ == "__main__":
    main()

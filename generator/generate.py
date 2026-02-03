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
    Article,
    AuthoritativeActor,
    AuthoritativeLocation,
    AuthoritativeMeetingType,
    Event,
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
    return "unknown"


def get_status_reason(record: Any) -> str | None:
    """Get the reason for the status."""
    if hasattr(record, "blocked") and record.blocked:
        return getattr(record, "block_reason", None)
    if hasattr(record, "use") and record.use is False:
        return getattr(record, "unuse_reason", None)
    return None


def make_issue_url(
    repo: str, table: str, record_id: int, context: dict, generated_at: str
) -> str:
    """Generate a GitHub issue URL with pre-filled content."""
    title = f"[Review] {table}/{record_id}"

    json_block = json.dumps(
        {
            "table": table,
            "id": record_id,
            "action": "mark_unusable",
            "reason": "EDIT THIS: Describe why this should be removed",
            "reviewer": "",
        },
        indent=2,
    )

    # Format context as markdown
    context_lines = []
    for key, value in context.items():
        if value is not None:
            # Truncate long values
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

    return f"https://github.com/{repo}/issues/new?title={quote(title)}&body={quote(body)}"


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
        self.env.globals["make_issue_url"] = lambda table, id, ctx: make_issue_url(
            self.repo, table, id, ctx, self.generated_at_str
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
        ]

        for (
            entity_type,
            model,
            template,
            display_name,
            primary_field,
            secondary_field,
        ) in entity_configs:
            print(f"Generating {entity_type} pages...")
            entities = session.exec(select(model)).all()
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
        print("Generating list pages...")
        self._generate_list_pages(all_entities, stats)

        return stats

    def _generate_list_pages(self, all_entities: dict, stats: dict):
        """Generate list/browse pages for each entity type."""
        list_template = self.env.get_template("list.html")

        # Field labels for display
        field_labels = {
            "excerpt": "Excerpt",
            "name": "Name",
            "when": "When",
            "country": "Country",
            "description": "Description",
            "category": "Category",
            "actor_type": "Type",
        }

        for entity_type, data in all_entities.items():
            # Limit to first 500 entities for performance
            entities = data["entities"][:500]

            html = list_template.render(
                entity_type=entity_type,
                entity_type_display=data["display_name"],
                entities=entities,
                counts=stats[entity_type],
                primary_field=data["primary_field"],
                primary_field_label=field_labels.get(
                    data["primary_field"], data["primary_field"]
                ),
                secondary_field=data["secondary_field"],
                secondary_field_label=field_labels.get(data["secondary_field"])
                if data["secondary_field"]
                else None,
            )

            # Write to entity_type/index.html
            list_dir = self.output_dir / entity_type
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

        for entity in tqdm(entities, desc=f"Generating {entity_type} pages"):
            counts["total"] += 1
            status = get_status(entity)
            counts[status] += 1

            # Get related data based on entity type
            context = self._get_entity_context(session, entity, entity_type)

            # Render the page
            html = template.render(
                entity=entity,
                entity_type=entity_type,
                status=status,
                status_reason=get_status_reason(entity),
                **context,
            )

            # Write to file
            page_dir = entity_dir / str(entity.id)
            page_dir.mkdir(parents=True, exist_ok=True)
            (page_dir / "index.html").write_text(html)

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
                for match in tqdm(context["matches"], desc="Loading authoritative locations"):
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
                for match in tqdm(context["matches"], desc="Loading authoritative actors"):
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
                for match in tqdm(context["matches"], desc="Loading authoritative meeting types"):
                    match.authoritative_meetingtype = session.get(
                        AuthoritativeMeetingType, match.authoritative_meetingtype_id
                    )
            except Exception:
                context["matches"] = []

        return context

    def _generate_index(self, stats: dict):
        """Generate the index page with statistics."""
        template = self.env.get_template("index.html")

        html = template.render(
            stats=stats,
            entity_types=[
                ("event", "Events"),
                ("location", "Locations"),
                ("splitlocation", "Split Locations"),
                ("actor", "Actors"),
                ("splitactor", "Split Actors"),
                ("timestamp", "Timestamps"),
                ("meetingtype", "Meeting Types"),
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
        default="",
        help="Base URL path prefix for GitHub Pages (e.g. /data-view)",
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

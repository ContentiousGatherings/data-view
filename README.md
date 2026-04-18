# CG Data View

Tools for validating and analyzing the Contentious Gatherings pipeline output.

## Overview

This repository contains two tools:

1. **Review Site Generator** (`generator/`) — Generates a browsable HTML site from the pipeline database, allowing colleagues to review extracted entities and submit corrections via GitHub Issues.
2. **Pilot Dataset Export** (`pilot/`) — Extracts AuthoritativeEvents matching specific meeting type search terms and exports them to `.xlsx` with embedded charts for initial analysis.

## Quick Start

```bash
# Install dependencies
pip install jinja2 sqlmodel tqdm

# Generate the site
cd cg-review-site
python -m generator --db ../alpha.db

# Serve locally for testing
cd docs
python -m http.server 8000
# Open http://localhost:8000
```

## Full CLI Options

```bash
python -m generator \
  --db ../alpha.db \
  --output ./docs \
  --repo "ContentiousGatherings/data-view" \
  --base-url "/data-view"
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `../alpha.db` | Path to SQLite database |
| `--output` | `./docs` | Output directory for generated HTML |
| `--repo` | `ContentiousGatherings/data-view` | GitHub repo for issue links |
| `--base-url` | `/data-view` | Base URL path prefix for GitHub Pages |

## Site Structure

```
docs/
├── index.html                        # Dashboard with entity counts
├── static/style.css                  # Styles
├── event/{id}/index.html             # Event detail pages
├── location/{id}/                    # Location pages
├── splitlocation/{id}/               # Split location pages
├── actor/{id}/                       # Actor pages
├── splitactor/{id}/                  # Split actor pages
├── timestamp/{id}/                   # Timestamp pages
├── meetingtype/{id}/                 # Meeting type pages
├── authoritativeevent/{id}/          # Authoritative event pages
├── eventmatch/{id}/                  # Event match pages
├── authoritativelocation/{id}/       # Authoritative location pages
├── splitlocationmatch/{id}/          # Split location match pages
├── authoritativeactor/{id}/          # Authoritative actor pages
├── actoralias/{id}/                  # Actor alias pages
├── splitactormatch/{id}/             # Split actor match pages
├── authoritativemeetingtype/{id}/    # Authoritative meeting type pages
├── meetingtypematch/{id}/            # Meeting type match pages
└── authoritativeeventactor/{id}/     # Authoritative event actor pages
```

## How to Review

Each entity detail page has four action buttons:

| Button | Action | Description |
|--------|--------|-------------|
| **Valid** | `mark_valid` | Confirm the entity is correct |
| **Invalid** | `mark_unusable` | Flag as unusable (edit the reason) |
| **Block** | `mark_blocked` | Flag as blocked / needs manual review (edit the reason) |
| **Report** | `report` | Report a general problem (edit the description) |

Click a button, edit the pre-filled JSON if needed, then submit the GitHub issue.

### Example Issue JSON

**Mark as valid:**
```json
{
  "table": "event",
  "id": 123,
  "action": "mark_valid"
}
```

**Mark as unusable:**
```json
{
  "table": "event",
  "id": 123,
  "action": "mark_unusable",
  "reason": "This is not a public gathering, it's a private dinner party"
}
```

**Mark as blocked (needs expert review):**
```json
{
  "table": "location",
  "id": 456,
  "action": "mark_blocked",
  "reason": "Ambiguous location name - could be multiple places"
}
```

**Report a problem:**
```json
{
  "table": "timestamp",
  "id": 789,
  "action": "report",
  "description": "The normalized date seems off by one day"
}
```

## GitHub Action

The `process-review.yml` workflow:
1. Triggers when an issue with `[Valid]`, `[Invalid]`, `[Block]`, or `[Report]` prefix is opened/edited
2. Extracts and validates the JSON from the issue body
3. If valid: appends to `edits.jsonl`, adds "validated" label, comments confirmation
4. If invalid: adds "needs-fix" label, comments with what to fix

## Applying Edits

The `edits.jsonl` file accumulates all validated corrections. To apply them to the database:

```bash
# TODO: Create apply_edits.py script
python apply_edits.py --edits edits.jsonl --db ../alpha.db
```

## Status Indicators

| Status | Visual | Meaning |
|--------|--------|---------|
| Valid | Green checkmark | `use=True, blocked=False` |
| Invalid | Red X | `use=False` with reason |
| Blocked | Yellow warning | `blocked=True` (needs review) |
| Unknown | Grey question mark | `use=None` (not yet validated) |

## Development

### Regenerating the Site

After database changes:

```bash
python -m generator --db ../alpha.db
```

### Deploying to GitHub Pages

GitHub Pages is configured to serve from the `docs/` folder on `main`.

### Adding New Entity Types

1. Add template in `generator/templates/{entity}.html`
2. Update `_generate_all_pages()` in `generator/generate.py`
3. Add to `entity_types` list in index template

## Pilot Dataset Export

Extracts deduplicated AuthoritativeEvents that match specific meeting type keywords and exports structured data to `.xlsx` for downstream analysis.

### What it does

1. Searches `MeetingType.name` for two search terms:
   - **folkmöte** — public meetings
   - **förstamaj-tåg** — May Day marches (matches spelling variants)
2. Traces matched MeetingTypes through `Event` → `EventMatch` → `AuthoritativeEvent` to get deduplicated canonical events
3. Resolves related entities: location, county (län), actors, source article excerpts and URLs
4. Exports to a single `.xlsx` file with:
   - **Data** sheet — one row per AuthoritativeEvent with all variables and IDs for traceability
   - **Möten per år** sheet — line chart of events over time, per search term
   - **Möten per län** sheet — bar chart of events by county, per search term

### Output columns

| Column | Source |
|--------|--------|
| AuthEvent ID | `AuthoritativeEvent.id` |
| Datum | `AuthoritativeEvent.event_date_start` |
| Kategori | `AuthoritativeEvent.category` |
| Ort | `AuthoritativeLocation.name` |
| Ort ID | `AuthoritativeLocation.id` |
| Län | `AuthoritativeLocation.county` |
| Aktörer | `AuthoritativeActor.name` (via `AuthoritativeEventActor`) |
| Aktör-IDn | `AuthoritativeActor.id` values |
| Textutdrag | Source `Event.excerpt` values (via `EventMatch`) |
| Länkar | Source `Article.url` values |
| Tidning | Source `Article.journal` values |
| Käll-event-IDn | Source `Event.id` values |
| Artikel-IDn | Source `Article.id` values |
| MeetingType-IDn | Matched `MeetingType.id` values |
| Sökord | Which search term matched |
| Källor | `AuthoritativeEvent.source_event_count` |

### Usage

```bash
pip install openpyxl sqlmodel tqdm

python -m pilot --db ../alpha.db --xlsx
```

Produces a timestamped file, e.g. `2026-04-18T143022_pilot_dataset.xlsx`.

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `../alpha.db` | Path to SQLite database |
| `--xlsx` | (flag) | Produce the .xlsx output file |
| `--usable-only` | (flag) | Exclude blocked/invalid AuthoritativeEvents |

## Dependencies

- Python 3.10+
- jinja2
- sqlmodel
- tqdm
- openpyxl (pilot export)

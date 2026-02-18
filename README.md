# CG Review Site

Static site generator for validating the Contentious Gatherings pipeline output.

## Overview

This tool generates a browsable HTML site from the pipeline database (`alpha.db`), allowing colleagues to review extracted entities and submit corrections via GitHub Issues.

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

## Dependencies

- Python 3.10+
- jinja2
- sqlmodel
- tqdm

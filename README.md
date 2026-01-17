# CG Review Site

Static site generator for validating the Contentious Gatherings pipeline output.

## Overview

This tool generates a browsable HTML site from the pipeline database (`alpha.db`), allowing colleagues to review extracted entities and submit corrections via GitHub Issues.

## Quick Start

```bash
# Install dependencies
pip install jinja2 sqlmodel

# Generate the site
cd cg-review-site
python -m generator.generate --db ../alpha.db --output ./site

# Serve locally for testing
cd site
python -m http.server 8000
# Open http://localhost:8000
```

## Full CLI Options

```bash
python -m generator.generate \
  --db ../alpha.db \
  --output ./site \
  --repo "username/cg-review-site" \
  --base-url "https://username.github.io/cg-review-site"
```

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `../alpha.db` | Path to SQLite database |
| `--output` | `./site` | Output directory for generated HTML |
| `--repo` | `username/cg-review-site` | GitHub repo for issue links |
| `--base-url` | `https://username.github.io/cg-review-site` | Base URL for the deployed site |

## Site Structure

```
site/
├── index.html              # Dashboard with entity counts
├── event/{id}/index.html   # Event detail pages
├── location/{id}/          # Location pages
├── splitlocation/{id}/     # Split location pages
├── actor/{id}/             # Actor pages
├── splitactor/{id}/        # Split actor pages
├── timestamp/{id}/         # Timestamp pages
├── meetingtype/{id}/       # Meeting type pages
└── static/style.css        # Styles
```

## How to Report Problems

1. Navigate to any entity page
2. Click the **Report Problem** button
3. Edit the JSON in the pre-filled issue:
   - Change `action` to one of: `mark_unusable`, `mark_blocked`, `correct_field`
   - Replace the `reason` placeholder with your explanation
   - For `correct_field`, add `field` and `new_value` parameters
4. Submit the issue

### Example Issue JSON

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

**Correct a field:**
```json
{
  "table": "timestamp",
  "id": 789,
  "action": "correct_field",
  "field": "normalized_datetime",
  "new_value": "1895-03-15T14:00:00",
  "reason": "The original parsing was off by one day"
}
```

## GitHub Action

The `process-review.yml` workflow:
1. Triggers when an issue with `[Review]` prefix is opened/edited
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
python -m generator.generate --db ../alpha.db --output ./site
```

### Deploying to GitHub Pages

1. Push the `site/` directory to the `gh-pages` branch, or
2. Configure GitHub Pages to serve from the `site/` folder on `main`

### Adding New Entity Types

1. Add template in `generator/templates/{entity}.html`
2. Update `_generate_all_pages()` in `generator/generate.py`
3. Add to `entity_types` list in index template

## Dependencies

- Python 3.10+
- jinja2
- sqlmodel
- (inherited from main project) SQLAlchemy

"""
Pilot dataset generator.

Extracts AuthoritativeEvents matching specific meeting type search terms
and exports them to an .xlsx file with embedded charts.

Usage:
    python -m pilot --db ../alpha.db --xlsx
"""

import argparse
import os
import sys
from datetime import datetime, timezone

from pilot.extract import SEARCH_TERMS, extract_pilot_data
from pilot.export import export_xlsx


def main():
    available_terms = [label for label, _ in SEARCH_TERMS]

    parser = argparse.ArgumentParser(
        description="Generate pilot dataset (.xlsx) from pipeline database"
    )
    parser.add_argument(
        "--db",
        default="../alpha.db",
        help="Path to the SQLite database (default: ../alpha.db)",
    )
    parser.add_argument(
        "--xlsx",
        action="store_true",
        default=False,
        help="Produce the .xlsx output file",
    )
    parser.add_argument(
        "--usable-only",
        action="store_true",
        default=False,
        help="Exclude blocked/invalid AuthoritativeEvents",
    )
    parser.add_argument(
        "--terms",
        nargs="+",
        choices=available_terms,
        default=None,
        help=f"Search terms to include (default: all). Choices: {', '.join(available_terms)}",
    )

    args = parser.parse_args()

    if not args.xlsx:
        parser.print_help()
        print("\nSpecify --xlsx to generate the output file.")
        sys.exit(0)

    # Resolve database path
    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    # Generate output filename with ISO datetime prefix
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    if args.terms:
        suffix = "_".join(t.replace(" ", "-") for t in args.terms)
        output_path = f"{timestamp}_pilot_{suffix}.xlsx"
    else:
        output_path = f"{timestamp}_pilot_dataset.xlsx"

    print(f"Extracting pilot data from {db_path}")
    rows = extract_pilot_data(db_path, usable_only=args.usable_only, terms=args.terms)

    if not rows:
        print("No matching AuthoritativeEvents found.")
        sys.exit(0)

    export_xlsx(rows, output_path)
    print("Done.")


main()

#!/usr/bin/env python3
"""Convert LibreOffice Calc (.ods) spreadsheets to Tab-Separated Values (.tsv) files.

Excludes openapptnz*.ods and site-translations*.ods by default.
Preserves UTF-8 encoding and keeps empty cells blank rather than converting to NaN.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd

DEFAULT_EXCLUDE_PATTERNS = [
    "openapptnz*.ods",
    "site-translations*.ods",
]


def matches_any_pattern(filename: str, patterns: Sequence[str]) -> bool:
    """Check if filename matches any glob pattern (case-insensitive)."""
    filename_lower = filename.lower()
    return any(fnmatch.fnmatch(filename_lower, pattern.lower()) for pattern in patterns)


def convert_ods_file(
    ods_path: Path,
    output_dir: Path,
    skip_empty_col_b: bool = True,
    strip_brackets: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """Convert an ODS file into one or more TSV files.

    If the file has one sheet, the output filename is <stem>.tsv.
    If the file has multiple sheets, output filenames are <stem>_<sheet>.tsv.
    Rows with an empty translation in Column B are skipped by default.
    Outer brackets '( ... )' in Column A values are removed by default.
    """
    excel_file = pd.ExcelFile(ods_path, engine="odf")
    sheet_names = excel_file.sheet_names
    output_files: list[Path] = []

    for sheet in sheet_names:
        if len(sheet_names) == 1:
            tsv_filename = f"{ods_path.stem}.tsv"
        else:
            safe_sheet_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in sheet)
            tsv_filename = f"{ods_path.stem}_{safe_sheet_name}.tsv"

        output_path = output_dir / tsv_filename

        if dry_run:
            print(f"[DRY-RUN] Would convert: {ods_path.name} (sheet: '{sheet}') -> {output_path.name}")
            output_files.append(output_path)
            continue

        df = pd.read_excel(
            ods_path,
            sheet_name=sheet,
            engine="odf",
            keep_default_na=False,
        )

        skipped_count = 0
        if skip_empty_col_b and len(df.columns) >= 2:
            col_b = df.columns[1]
            non_empty_mask = df[col_b].astype(str).str.strip() != ""
            skipped_count = int(len(df) - non_empty_mask.sum())
            df = df[non_empty_mask]

        if strip_brackets and len(df.columns) >= 1:
            col_a = df.columns[0]
            df[col_a] = df[col_a].map(
                lambda val: str(val)[1:-1] if str(val).startswith("(") and str(val).endswith(")") else val
            )

        df.to_csv(
            output_path,
            sep="\t",
            index=False,
            na_rep="",
            encoding="utf-8",
            lineterminator="\n",
        )

        skip_info = f", skipped {skipped_count} empty rows" if skipped_count else ""
        if verbose:
            print(f"Converted: {ods_path.name} -> {output_path.name} ({len(df)} rows, {len(df.columns)} columns{skip_info})")
        else:
            print(f"Converted: {ods_path.name} -> {output_path.name}")

        output_files.append(output_path)

    return output_files


def find_ods_files(
    input_dir: Path,
    exclude_patterns: Sequence[str],
) -> tuple[list[Path], list[Path]]:
    """Find all .ods files in directory and categorize into included and excluded."""
    included: list[Path] = []
    excluded: list[Path] = []

    for path in sorted(input_dir.glob("*.ods")):
        if matches_any_pattern(path.name, exclude_patterns):
            excluded.append(path)
        else:
            included.append(path)

    return included, excluded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert LibreOffice Calc (.ods) files to Tab-Separated Values (.tsv) files."
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing .ods files (default: current working directory).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where .tsv files will be saved (default: same as input directory).",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=DEFAULT_EXCLUDE_PATTERNS,
        help=f"Patterns of files to exclude (default: {DEFAULT_EXCLUDE_PATTERNS}).",
    )
    parser.add_argument(
        "--keep-empty",
        action="store_true",
        help="Keep rows missing a language translation in Column B instead of skipping them.",
    )
    parser.add_argument(
        "--keep-brackets",
        action="store_true",
        help="Do not remove outer parentheses '( ... )' from Column A values.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="List files that would be converted without creating any output files.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed row and column statistics during conversion.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_dir = args.input_dir.resolve()
    if not input_dir.is_dir():
        print(f"Error: Input directory does not exist: {input_dir}", file=sys.stderr)
        return 1

    output_dir = args.output_dir.resolve() if args.output_dir else input_dir
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    included_files, excluded_files = find_ods_files(input_dir, args.exclude)

    if args.verbose or args.dry_run:
        print(f"Found {len(included_files)} file(s) to convert, {len(excluded_files)} file(s) excluded.")
        if excluded_files:
            print("Excluded files:")
            for ef in excluded_files:
                print(f"  - {ef.name}")

    if not included_files:
        print(f"No matching .ods files found in {input_dir}.")
        return 0

    converted_count = 0
    for ods_file in included_files:
        try:
            convert_ods_file(
                ods_path=ods_file,
                output_dir=output_dir,
                skip_empty_col_b=not args.keep_empty,
                strip_brackets=not args.keep_brackets,
                verbose=args.verbose,
                dry_run=args.dry_run,
            )
            converted_count += 1
        except Exception as err:
            print(f"Error converting {ods_file.name}: {err}", file=sys.stderr)
            return 1

    action = "Would convert" if args.dry_run else "Successfully converted"
    print(f"{action} {converted_count} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

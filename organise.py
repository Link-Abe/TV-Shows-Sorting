"""
TV Shows Organiser
==================
A single-file command-line script that recursively walks a TV Shows root
directory, extracts structured metadata (show name, season, episode) from
messy download-style filenames and folder names, and reorganises every media
file into a clean, readable folder hierarchy:

    <TV Shows Root>/
      <Show Name>/
        <Show Name - Season X>/
          <Show Name - Season X - Episode Y>.ext

Supports a --test mode that operates on a temporary copy of a reference
folder so results can be verified without touching real files.

Usage:
    python organise.py <root>
    python organise.py --test <path> [--overwrite]
"""

import argparse
import dataclasses
import enum
import pathlib
import shutil
import datetime
import typing
import re
import os
import sys
import unicodedata

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Literal


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

MEDIA_EXTS: frozenset[str] = frozenset(
    {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts"}
)

JUNK_EXTS: frozenset[str] = frozenset(
    {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".srt", ".sub"}
)

QUALITY_TOKENS: frozenset[str] = frozenset(
    {
        "1080p", "720p", "480p", "2160p", "4K",
        "WEB", "WEBRip", "WEB-DL", "HDTV", "HEVC",
        "x264", "x265", "h264", "h265", "H.264", "H.265",
        "BluRay", "BDRip", "AMZN", "ATVP", "HULU", "NF",
        "COMPLETE", "MULTI",
        "DDP", "DDP2.0", "DDP5.1", "AAC", "AAC2.0",
        "Atmos", "HDR", "SDR", "REMUX", "REPACK", "PROPER",
    }
)

# Show name alias map — keys are normalised lowercase, value is the canonical
# display name.  Add entries here whenever source filenames use inconsistent
# abbreviations or short names for the same show.
# Keys are matched against the parsed show_name_raw after lowercasing and
# stripping punctuation/spaces.
SHOW_NAME_ALIASES: dict[str, str] = {
    # House M.D. variants
    "house md":                             "House M.D.",
    "house, md":                            "House M.D.",
    "house m d":                            "House M.D.",
    "house, m d":                           "House M.D.",
    # Star Trek abbreviations and hyphen/typo variants
    "ds9":                                  "Star Trek Deep Space Nine",
    "star trek ds9":                        "Star Trek Deep Space Nine",
    "start trek deep space nine":           "Star Trek Deep Space Nine",  # typo: "Start"
    "star trek  deep space nine":           "Star Trek Deep Space Nine",  # double space
    "voyager":                              "Star Trek Voyager",
    "star trek  voyager":                   "Star Trek Voyager",           # double space
    "star trek voy":                        "Star Trek Voyager",
    # Stargate
    "stargate sg 1":                        "Stargate SG-1",
    # Karl Pilkington / Moaning of Life duplicates
    "karl pilkington the moaning of life":  "The Moaning of Life",
    # The Servant / Servant duplicate — canonical is without "The"
    "the servant":                          "Servant",
    # Strictly Come Dancing typo
    "stricktly come dancing":               "Strictly Come Dancing",
    # Add more as needed, e.g.:
    # "tng":  "Star Trek The Next Generation",
    # "tos":  "Star Trek The Original Series",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShowMetadata:
    """Parsed metadata extracted from a filename or folder name."""
    show_name_raw: str          # space-separated words, pre-title-case
    season: int                 # 1-based season integer, no leading zeros
    episode: Optional[int]      # 1-based episode integer, or None for season packs
    name_is_canonical: bool = False  # True when show_name_raw came from alias map (skip title_case)


@dataclass
class OrgAction:
    """A single logged action produced by the Organiser."""
    kind: Literal["MOVED", "CREATED", "DELETED", "WARN", "CONFLICT", "SKIPPED"]
    source: str                 # absolute path string
    dest: Optional[str] = None  # absolute path string (None for DELETED / WARN)
    detail: Optional[str] = None  # human-readable detail string


class FileClass(Enum):
    """Classification of a file based on its extension and name."""
    MEDIA = "media"
    JUNK = "junk"
    SAMPLE = "sample"
    UNKNOWN = "unknown"


@dataclass
class PlannedOperation:
    """A filesystem operation to be executed during the execution pass."""
    kind: Literal["MOVE", "DELETE", "CREATE_DIR"]
    source: Path
    dest: Optional[Path] = None


# ---------------------------------------------------------------------------
# File classifier
# ---------------------------------------------------------------------------


def classify_file(path: Path) -> FileClass:
    """
    Classify a file based on its extension and name.

    Returns:
        FileClass.SAMPLE  — extension is in MEDIA_EXTS and filename contains
                            the word "sample" (case-insensitive).
        FileClass.MEDIA   — extension is in MEDIA_EXTS.
        FileClass.JUNK    — extension is in JUNK_EXTS.
        FileClass.UNKNOWN — anything else.
    """
    suffix = path.suffix.lower()
    if suffix in MEDIA_EXTS:
        if "sample" in path.stem.lower():
            return FileClass.SAMPLE
        return FileClass.MEDIA
    if suffix in JUNK_EXTS:
        return FileClass.JUNK
    return FileClass.UNKNOWN


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Regex for SxxEyy (e.g. S02E04, S20E01) — case-insensitive
# Also handles multi-episode ranges like S02E05-09 or S02E05-E09 (captures first episode)
_RE_SXXEYY = re.compile(r'S(\d+)E(\d+)(?:-E?\d+)?', re.IGNORECASE)

# Regex for standalone Sxx NOT immediately followed by Eyy — case-insensitive
_RE_SXX = re.compile(r'S(\d+)(?!E\d)', re.IGNORECASE)

# Regex for the Plex output format — used for idempotency on already-organised files:
#   "<Show Name> - SxxEyy"
_RE_CLEAN_FORMAT = re.compile(r'^(.+?)\s+-\s+S(\d+)E(\d+)$', re.IGNORECASE)

# Regex for bracket-enclosed release-group tokens, e.g. [EZTVx.to], [TGx]
_RE_BRACKET_TOKEN = re.compile(r'\[[^\]]*\]')

# Quality tokens set as lowercase for case-insensitive comparison
_QUALITY_TOKENS_LOWER: frozenset[str] = frozenset(t.lower() for t in QUALITY_TOKENS)


def parse(name: str) -> Optional[ShowMetadata]:
    """
    Extract show metadata from a filename (with or without extension)
    or a folder name.

    Returns None if no SxxEyy or Sxx token can be found.
    Strips the file extension before parsing if present.
    """
    # Step 1: Strip file extension if present
    stem = name
    for ext in MEDIA_EXTS:
        if name.lower().endswith(ext):
            stem = name[: len(name) - len(ext)]
            break

    # Step 1a: Strip leading site-name prefixes like "www.SiteName.org - "
    stem = re.sub(r'^www\.[^\s].*?\s+-+\s+', '', stem, flags=re.IGNORECASE).strip()

    # Step 1b: Fast-path for already-organised Plex-format filenames (idempotency):
    #   e.g. "Silo - S02E05" — parse directly without going through the full algorithm
    clean_match = _RE_CLEAN_FORMAT.match(stem)
    if clean_match:
        show_name_raw = clean_match.group(1).strip()
        season = int(clean_match.group(2))
        episode: Optional[int] = int(clean_match.group(3))
        if show_name_raw:
            return ShowMetadata(show_name_raw=show_name_raw, season=season, episode=episode)

    sxxeyy_match = _RE_SXXEYY.search(stem)
    sxx_match = _RE_SXX.search(stem)

    # Prefer SxxEyy; only use Sxx if no SxxEyy found.
    if sxxeyy_match:
        token_match = sxxeyy_match
        season = int(sxxeyy_match.group(1))
        episode = int(sxxeyy_match.group(2))
    elif sxx_match:
        token_match = sxx_match
        season = int(sxx_match.group(1))
        episode = None
    else:
        return None

    # Step 3: Detect separator style using the pre-season portion of the stem
    pre_season = stem[: token_match.start()]
    dot_count = pre_season.count('.')
    space_count = pre_season.count(' ')
    separator = '.' if dot_count > space_count else ' '

    # Step 4: Split the FULL stem on the detected separator to get all tokens,
    # then find which token index contains the season/episode marker.
    # We need to locate the season token within the split list.
    parts = stem.split(separator)

    # Find the index of the part that contains our token match.
    # Reconstruct character offsets to find the matching part index.
    token_start = token_match.start()
    char_pos = 0
    token_part_idx = None
    sep_len = len(separator)
    for i, part in enumerate(parts):
        part_start = char_pos
        part_end = char_pos + len(part)
        # The token overlaps with this part if the token starts within it
        if part_start <= token_start < part_end:
            token_part_idx = i
            break
        char_pos += len(part) + sep_len

    if token_part_idx is None:
        return None

    # Step 5: Everything to the LEFT of the token part is the raw show-name word list.
    # We need to re-examine the parts before the token, but the parts themselves may
    # include bracket-enclosed tokens that should be stripped.
    raw_name_parts = parts[:token_part_idx]

    # Step 6: Strip quality tokens and release-group tokens from the raw name parts.
    # Release-group tokens:
    #   a) Tokens enclosed in [...] — always stripped (at any position)
    #   b) Hyphen-prefixed suffix tokens that appear AFTER the SxxEyy token AND after
    #      at least one quality token. Since we're only looking at parts BEFORE the
    #      season token here, (b) cannot apply to the show-name portion.
    #
    # However, bracket tokens can appear in the pre-season portion (unlikely but possible).
    # We need to strip them.

    cleaned_parts: list[str] = []
    for part in raw_name_parts:
        # Remove any [...] substrings from the part
        part_no_brackets = _RE_BRACKET_TOKEN.sub('', part).strip()
        if not part_no_brackets:
            continue
        # Check if the remaining text is a quality token (whole-token, case-insensitive)
        if part_no_brackets.lower() in _QUALITY_TOKENS_LOWER:
            continue
        cleaned_parts.append(part_no_brackets)

    # Step 7: Join remaining words with a single space, then strip any
    # trailing/leading hyphens or whitespace that can appear when the last
    # show-name word was itself a hyphen-only token (e.g. from a badly split
    # name like "Star Trek -").
    show_name_raw = ' '.join(cleaned_parts).strip(' -')

    # Step 8: Strip trailing punctuation characters (commas, dots) from the
    # assembled show name — e.g. "House, M.D." parsed with space separator
    # can produce "House, M.D." with a trailing dot that confuses folder naming.
    show_name_raw = show_name_raw.strip('., ')

    if not show_name_raw:
        return None

    # Step 9: Apply alias map — normalise known variant names to their
    # canonical form.  The lookup key is the show name lowercased with
    # punctuation/spaces collapsed.
    alias_key = re.sub(r'[^a-z0-9 ]', '', show_name_raw.lower()).strip()
    alias_key = re.sub(r'\s+', ' ', alias_key)
    if alias_key in SHOW_NAME_ALIASES:
        return ShowMetadata(
            show_name_raw=SHOW_NAME_ALIASES[alias_key],
            season=season,
            episode=episode,
            name_is_canonical=True,
        )

    return ShowMetadata(
        show_name_raw=show_name_raw,
        season=season,
        episode=episode,
    )


# ---------------------------------------------------------------------------
# Pretty_Printer component
# ---------------------------------------------------------------------------

# Words rendered in lowercase when they appear as non-first, non-last words
_LOWERCASE_WORDS: frozenset[str] = frozenset({
    # articles
    "a", "an", "the",
    # coordinating conjunctions
    "and", "but", "or", "nor",
    # short prepositions
    "at", "by", "for", "in", "of", "on", "to", "up",
    # short subordinating conjunctions used adverbially
    "as", "if", "so",
})


def title_case(s: str) -> str:
    """
    Apply TV-library title case rules to a show name string.

    - Capitalises the first letter of every word not in the lowercase exception
      list.
    - Renders exception-list words in lowercase when they are not the first or
      last word of the string.
    - Always capitalises the first word and the last word regardless of word
      class.
    - Idempotent: title_case(title_case(s)) == title_case(s).
    """
    words = s.split()
    if not words:
        return s

    result = []
    last_idx = len(words) - 1
    for i, word in enumerate(words):
        lower = word.lower()
        if i == 0 or i == last_idx:
            # First and last word always capitalised
            result.append(unicodedata.normalize("NFC", lower.capitalize()))
        elif lower in _LOWERCASE_WORDS:
            result.append(lower)
        else:
            result.append(unicodedata.normalize("NFC", lower.capitalize()))

    return " ".join(result)


def _format_name(meta: ShowMetadata) -> str:
    """Return the display show name, skipping title_case for canonical alias names."""
    if meta.name_is_canonical:
        return meta.show_name_raw
    return title_case(meta.show_name_raw)


def format_show_folder(meta: ShowMetadata) -> str:
    """Returns e.g. 'Ancient Aliens'"""
    return _format_name(meta)


def format_season_folder(meta: ShowMetadata) -> str:
    """Returns e.g. 'Season 20'  (Plex preferred format)"""
    return f"Season {meta.season}"


def format_season_only_folder(meta: ShowMetadata) -> str:
    """Returns e.g. 'Season 1'  (episode is None, Plex preferred format)"""
    return f"Season {meta.season}"


def format_episode_filename(meta: ShowMetadata, ext: str) -> str:
    """Returns e.g. 'Ancient Aliens - S20E01.mkv'  (Plex preferred format)
    ext should include the leading dot; it is lowercased in the output."""
    return (
        f"{_format_name(meta)}"
        f" - S{meta.season:02d}E{meta.episode:02d}"
        f"{ext.lower()}"
    )


# ---------------------------------------------------------------------------
# Organiser component
# ---------------------------------------------------------------------------


def organise(root: Path, overwrite: bool = False) -> list[OrgAction]:
    """
    Walk root recursively. For each file encountered:
    - If Junk_File extension or Sample_File → schedule deletion.
    - If Media_File → parse filename:
        - If parseable → compute target path, schedule move (or skip if already correct).
        - If unparseable → log WARN, leave in place.
    - If unknown extension → log WARN, leave in place.

    Execute scheduled operations in order:
    1. Create destination folders as needed.
    2. Move media files.
    3. Delete junk files.
    4. Delete now-empty (or junk-only) source folders bottom-up.

    Returns a list of all OrgAction records.
    """
    root = root.resolve()
    actions: list[OrgAction] = []
    planned: list[PlannedOperation] = []

    # ------------------------------------------------------------------
    # Discovery pass: walk the entire tree and classify every file.
    # No filesystem modifications are made here.
    # ------------------------------------------------------------------
    file_count = 0
    print("Scanning files...", flush=True)
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            file_count += 1
            if file_count % 100 == 0:
                print(f"  Scanned {file_count} files...", flush=True)
            file_path = Path(dirpath) / filename
            file_class = classify_file(file_path)

            if file_class in (FileClass.JUNK, FileClass.SAMPLE):
                # Schedule for deletion — emit no action yet (actions emitted during
                # execution pass).
                planned.append(PlannedOperation(kind="DELETE", source=file_path))

            elif file_class == FileClass.MEDIA:
                meta = parse(file_path.stem)
                if meta is None:
                    # Unparseable media file — warn and leave in place.
                    actions.append(OrgAction(
                        kind="WARN",
                        source=str(file_path),
                        detail=f"unparseable – {file_path}",
                    ))
                else:
                    # Compute the target path from the file's own name (Req 2.8, 4.2).
                    show_folder = format_show_folder(meta)
                    season_folder = format_season_folder(meta)
                    episode_filename = format_episode_filename(meta, file_path.suffix)
                    dest = root / show_folder / season_folder / episode_filename

                    if file_path.resolve() == dest.resolve():
                        # Already at the correct location (Req 2.7).
                        actions.append(OrgAction(
                            kind="SKIPPED",
                            source=str(file_path),
                            dest=str(dest),
                        ))
                    elif dest.exists():
                        # Destination already occupied by a different file (Req 6.5).
                        if overwrite:
                            # With --overwrite: schedule a MOVE that will replace it.
                            planned.append(PlannedOperation(
                                kind="MOVE", source=file_path, dest=dest
                            ))
                        else:
                            actions.append(OrgAction(
                                kind="CONFLICT",
                                source=str(file_path),
                                dest=str(dest),
                                detail="skipped; use --overwrite to replace",
                            ))
                    else:
                        # Normal move: schedule CREATE_DIR for the season folder then MOVE.
                        planned.append(PlannedOperation(
                            kind="CREATE_DIR", source=dest.parent
                        ))
                        planned.append(PlannedOperation(
                            kind="MOVE", source=file_path, dest=dest
                        ))

            else:
                # FileClass.UNKNOWN — warn and leave in place (Req 3.6).
                actions.append(OrgAction(
                    kind="WARN",
                    source=str(file_path),
                    detail=f"unrecognised extension {file_path.suffix} – {file_path}",
                ))

    # ------------------------------------------------------------------
    # Collect source directories for bottom-up pruning (task 5.4).
    # We track every directory that contained a file we touched (moved,
    # deleted, or simply visited as a potential container).
    # ------------------------------------------------------------------
    print(f"Scan complete: {file_count} files found. Planning {len(planned)} operations...", flush=True)
    source_dirs: set[Path] = set()
    for op in planned:
        source_dirs.add(op.source.parent)

    # ------------------------------------------------------------------
    # Execution pass (task 5.3)
    # Process operations in dependency order: CREATE_DIR → MOVE → DELETE
    # ------------------------------------------------------------------

    # --- CREATE_DIR pass ---
    print("Creating folders...", flush=True)
    created_dirs: set[Path] = set()
    for op in planned:
        if op.kind != "CREATE_DIR":
            continue
        dest_dir = op.source  # source field holds the directory path for CREATE_DIR ops
        if dest_dir in created_dirs:
            # Avoid emitting duplicate CREATED actions for the same directory
            continue
        try:
            os.makedirs(dest_dir, exist_ok=True)
            created_dirs.add(dest_dir)
            actions.append(OrgAction(
                kind="CREATED",
                source=str(dest_dir),
            ))
        except OSError as exc:
            actions.append(OrgAction(
                kind="WARN",
                source=str(dest_dir),
                detail=f"filesystem error – {dest_dir}: {exc}",
            ))

    # --- MOVE pass ---
    print("Moving files...", flush=True)
    for op in planned:
        if op.kind != "MOVE":
            continue
        src = op.source
        dest = op.dest
        # Re-check whether dest exists at execution time (another move may have
        # landed something there, or --overwrite was requested).
        if dest.exists():
            if not overwrite:
                actions.append(OrgAction(
                    kind="CONFLICT",
                    source=str(src),
                    dest=str(dest),
                    detail="skipped; use --overwrite to replace",
                ))
                continue
        try:
            if dest.exists():
                os.remove(dest)
            shutil.move(str(src), str(dest))
            actions.append(OrgAction(
                kind="MOVED",
                source=str(src),
                dest=str(dest),
            ))
        except OSError as exc:
            actions.append(OrgAction(
                kind="WARN",
                source=str(src),
                detail=f"filesystem error – {src}: {exc}",
            ))

    # --- DELETE pass (junk / sample files scheduled during discovery) ---
    print("Deleting junk files...", flush=True)
    for op in planned:
        if op.kind != "DELETE":
            continue
        src = op.source
        if not src.exists():
            # Already gone (e.g. inside a folder that was removed earlier)
            continue
        try:
            if src.is_dir():
                shutil.rmtree(src)
            else:
                os.remove(src)
            actions.append(OrgAction(
                kind="DELETED",
                source=str(src),
            ))
        except OSError as exc:
            actions.append(OrgAction(
                kind="WARN",
                source=str(src),
                detail=f"filesystem error – {src}: {exc}",
            ))

    # ------------------------------------------------------------------
    # Folder pruning — bottom-up (task 5.4)
    # Req 3.3, 3.4, 3.5
    # ------------------------------------------------------------------

    # Sort deepest-first by the number of path components (most nested first).
    candidate_dirs = sorted(
        source_dirs,
        key=lambda p: len(p.parts),
        reverse=True,
    )

    for directory in candidate_dirs:
        # Req 3.5: never delete TV_Shows_Root
        if directory == root:
            continue
        if not directory.exists():
            continue

        # Scan what remains in the directory after moves/deletes above.
        remaining = list(directory.iterdir())

        # If any file has an UNKNOWN extension, leave the whole directory alone
        # and emit a warning (Req 3.6 / design spec).
        has_unknown = False
        for item in remaining:
            if item.is_file():
                suffix = item.suffix.lower()
                if suffix not in MEDIA_EXTS and suffix not in JUNK_EXTS:
                    has_unknown = True
                    actions.append(OrgAction(
                        kind="WARN",
                        source=str(item),
                        detail=f"unrecognised extension {item.suffix} – {item}",
                    ))
        if has_unknown:
            continue

        # Delete any remaining junk files in the directory.
        for item in remaining:
            if item.is_file() and item.suffix.lower() in JUNK_EXTS:
                try:
                    os.remove(item)
                    actions.append(OrgAction(
                        kind="DELETED",
                        source=str(item),
                    ))
                except OSError as exc:
                    actions.append(OrgAction(
                        kind="WARN",
                        source=str(item),
                        detail=f"filesystem error – {item}: {exc}",
                    ))

        # After junk removal, delete the directory if it is now empty.
        try:
            remaining_after_cleanup = list(directory.iterdir())
            if not remaining_after_cleanup:
                directory.rmdir()
                actions.append(OrgAction(
                    kind="DELETED",
                    source=str(directory),
                ))
        except OSError as exc:
            actions.append(OrgAction(
                kind="WARN",
                source=str(directory),
                detail=f"filesystem error – {directory}: {exc}",
            ))

    return actions


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def _print_actions(actions: list[OrgAction]) -> None:
    """Print all action log lines to stdout."""
    for action in actions:
        if action.kind == "MOVED":
            print(f"MOVED: {action.source} → {action.dest}")
        elif action.kind == "CREATED":
            print(f"CREATED: {action.source}")
        elif action.kind == "DELETED":
            print(f"DELETED: {action.source}")
        elif action.kind == "WARN":
            print(f"WARN: {action.detail}")
        elif action.kind == "CONFLICT":
            print(f"CONFLICT: {action.source} → {action.dest} ({action.detail})")
        elif action.kind == "SKIPPED":
            print(f"SKIPPED: {action.source} → {action.dest}")


def _print_summary(actions: list[OrgAction]) -> None:
    """Print the final summary block."""
    moved = sum(1 for a in actions if a.kind == "MOVED")
    created = sum(1 for a in actions if a.kind == "CREATED")
    deleted = sum(1 for a in actions if a.kind == "DELETED")
    warnings = sum(1 for a in actions if a.kind == "WARN")
    conflicts = sum(1 for a in actions if a.kind == "CONFLICT")

    print("--- Summary ---")
    print(f"Files moved:     {moved}")
    print(f"Folders created: {created}")
    print(f"Files deleted:   {deleted}")
    print(f"Warnings:        {warnings}")
    print(f"Conflicts:       {conflicts}")


def main() -> None:
    """CLI entry point for the TV Shows Organiser."""
    # Ensure stdout is UTF-8 on all platforms (including Windows cp1252 consoles)
    # so that the → arrow character in log lines encodes correctly.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Organise TV show files")
    parser.add_argument("root", nargs="?", help="TV shows root directory")
    parser.add_argument(
        "--test", metavar="PATH", help="Run in test mode on a copy of PATH"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite conflicts"
    )
    args = parser.parse_args()

    if args.test is not None:
        # --- Test mode ---
        test_path = pathlib.Path(args.test)
        if not test_path.exists() or not test_path.is_dir():
            print(f"ERROR: {args.test} does not exist or is not a directory")
            raise SystemExit(1)

        # Compute temp copy path: <parent>/<basename>_<timestamp>
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        temp_copy = test_path.parent / f"{test_path.name}_{timestamp}"

        # Copy the reference folder
        shutil.copytree(str(test_path), str(temp_copy))

        abs_temp = temp_copy.resolve()
        print(f"TESTMODE: working copy at {abs_temp}")

        # Run organiser on the temp copy
        actions = organise(temp_copy, overwrite=args.overwrite)

        _print_actions(actions)
        _print_summary(actions)

        print(f"TESTMODE: result at {abs_temp}")

    elif args.root is not None:
        # --- Normal mode ---
        root_path = pathlib.Path(args.root)
        if not root_path.exists() or not root_path.is_dir():
            print(f"ERROR: {args.root} does not exist or is not a directory")
            raise SystemExit(1)

        actions = organise(root_path, overwrite=args.overwrite)

        _print_actions(actions)
        _print_summary(actions)

    else:
        # Neither root nor --test provided
        parser.print_usage()
        raise SystemExit(1)


if __name__ == "__main__":
    main()

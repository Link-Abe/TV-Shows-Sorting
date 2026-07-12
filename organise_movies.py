"""
Movie Organiser
===============
Flattens a Movies root folder into:

    Movies/
      <Movie Title>.<ext>

Rules:
- Recursively finds all media files (.mkv, .mp4, .avi, .mov, .wmv, .m4v, .ts)
- Strips year, quality tokens, release group suffixes from the filename
- Renames/moves the file to Movies/<Clean Title>.<ext>
- Deletes junk files (.nfo, .txt, .jpg, .jpeg, .png, .srt, .sub)
- Removes empty folders after organising
- Never deletes the Movies root folder
- Supports --test mode (works on a timestamped copy)
- Supports --overwrite flag

Usage:
    python organise_movies.py <path/to/Movies>
    python organise_movies.py --test <path/to/Movies> [--overwrite]
"""

import argparse
import datetime
import os
import pathlib
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Literal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEDIA_EXTS: frozenset[str] = frozenset(
    {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts"}
)

JUNK_EXTS: frozenset[str] = frozenset(
    {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".srt", ".sub"}
)

# Quality/encoding tokens to strip from movie filenames (case-insensitive)
QUALITY_TOKENS: frozenset[str] = frozenset({
    "1080p", "720p", "480p", "2160p", "4K",
    "WEB", "WEBRip", "WEB-DL", "HDTV", "HEVC",
    "x264", "x265", "h264", "h265", "H264", "H265",
    "BluRay", "BLURAY", "BDRip", "BRRip",
    "AMZN", "ATVP", "HULU", "NF",
    "COMPLETE", "MULTI", "EXTENDED", "REMASTERED", "THEATRICAL",
    "DDP", "DDP2.0", "DDP5.1", "AAC", "AAC2.0", "AAC5.1",
    "Atmos", "HDR", "SDR", "REMUX", "REPACK", "PROPER",
    "DVDRip", "DVDScr", "CAM", "TS", "R5",
})

_QUALITY_TOKENS_LOWER = frozenset(t.lower() for t in QUALITY_TOKENS)

# Words kept lowercase in title case (unless first/last)
_LOWERCASE_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "but", "or", "nor",
    "at", "by", "for", "in", "of", "on", "to", "up",
    "as", "if", "so",
})

# Regex to detect a standalone 4-digit year like 2022, (2022)
_RE_YEAR = re.compile(r'\(?\b(19\d{2}|20\d{2})\b\)?')

# Regex for bracket-enclosed tokens e.g. [EZTVx.to]
_RE_BRACKET = re.compile(r'\[[^\]]*\]')

# Regex for site prefixes like "www.YTS.MX - "
_RE_SITE_PREFIX = re.compile(r'^www\.[^\s].*?\s+-+\s+', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MovieAction:
    kind: Literal["MOVED", "DELETED", "WARN", "CONFLICT", "SKIPPED"]
    source: str
    dest: Optional[str] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Title case
# ---------------------------------------------------------------------------

def title_case(s: str) -> str:
    words = s.split()
    if not words:
        return s
    result = []
    last = len(words) - 1
    for i, word in enumerate(words):
        low = word.lower()
        if i == 0 or i == last or low not in _LOWERCASE_WORDS:
            result.append(unicodedata.normalize("NFC", low.capitalize()))
        else:
            result.append(low)
    return " ".join(result)


# ---------------------------------------------------------------------------
# Movie title parser
# ---------------------------------------------------------------------------

def parse_movie_title(name: str) -> Optional[str]:
    """
    Extract a clean movie title from a filename or folder name.

    Returns the title in title case, or None if nothing useful can be extracted.

    Examples:
      "Avatar.The.Way.Of.Water.2022.BLURAY.1080p.x264.mkv" -> "Avatar the Way of Water"
      "Avatar The Way Of Water (2022) BLURAY 1080p BluRay 5.1-LAMA.mkv" -> "Avatar the Way of Water"
    """
    stem = name
    # Strip extension
    for ext in MEDIA_EXTS:
        if name.lower().endswith(ext):
            stem = name[: len(name) - len(ext)]
            break

    # Strip site prefix
    stem = _RE_SITE_PREFIX.sub('', stem).strip()

    # Strip bracket tokens
    stem = _RE_BRACKET.sub('', stem).strip()

    # Detect separator: dots or spaces
    dot_count = stem.count('.')
    space_count = stem.count(' ')
    separator = '.' if dot_count > space_count else ' '

    # Split into parts
    parts = stem.replace('_', ' ').split(separator)

    # Find where the year or first quality token appears — everything before is the title
    title_parts = []
    for part in parts:
        clean = part.strip(' -_.,')
        if not clean:
            continue
        # Stop at year
        if _RE_YEAR.fullmatch(clean.strip('()')):
            break
        # Stop at quality token
        if clean.lower() in _QUALITY_TOKENS_LOWER:
            break
        # Stop at resolution pattern like 1080p even if not in set
        if re.fullmatch(r'\d{3,4}p', clean, re.IGNORECASE):
            break
        title_parts.append(clean)

    title = ' '.join(title_parts).strip(' -_.,')
    if not title:
        return None

    return title_case(title)


# ---------------------------------------------------------------------------
# Organiser
# ---------------------------------------------------------------------------

def organise_movies(root: Path, overwrite: bool = False) -> list[MovieAction]:
    root = root.resolve()
    actions: list[MovieAction] = []

    # Discovery pass
    file_count = 0
    print("Scanning files...", flush=True)
    moves: list[tuple[Path, Path]] = []   # (src, dest)
    deletes: list[Path] = []
    source_dirs: set[Path] = set()

    for dirpath, _dirs, filenames in os.walk(root):
        for filename in filenames:
            file_count += 1
            if file_count % 100 == 0:
                print(f"  Scanned {file_count} files...", flush=True)

            src = Path(dirpath) / filename
            ext = src.suffix.lower()

            if ext in JUNK_EXTS:
                deletes.append(src)
                source_dirs.add(src.parent)
                continue

            if ext not in MEDIA_EXTS:
                actions.append(MovieAction(
                    kind="WARN", source=str(src),
                    detail=f"unrecognised extension {ext} – {src}"
                ))
                continue

            # It's a media file — parse title from filename first, fall back to folder name
            title = parse_movie_title(src.name)
            if title is None:
                title = parse_movie_title(src.parent.name)
            if title is None:
                actions.append(MovieAction(
                    kind="WARN", source=str(src),
                    detail=f"unparseable – {src}"
                ))
                continue

            dest = root / f"{title}{ext}"

            if src.resolve() == dest.resolve():
                actions.append(MovieAction(kind="SKIPPED", source=str(src), dest=str(dest)))
                continue

            moves.append((src, dest))
            source_dirs.add(src.parent)

    print(f"Scan complete: {file_count} files found. Planning {len(moves)} moves, {len(deletes)} deletes...", flush=True)

    # Execution pass — moves
    print("Moving files...", flush=True)
    for src, dest in moves:
        if dest.exists():
            if not overwrite:
                actions.append(MovieAction(
                    kind="CONFLICT", source=str(src), dest=str(dest),
                    detail="skipped; use --overwrite to replace"
                ))
                continue
            try:
                # Clear read-only flag before removing (Windows WinError 5)
                dest.chmod(0o666)
                os.remove(dest)
            except OSError as exc:
                actions.append(MovieAction(
                    kind="WARN", source=str(src),
                    detail=f"filesystem error removing existing file – {dest}: {exc}"
                ))
                continue
        try:
            shutil.move(str(src), str(dest))
            actions.append(MovieAction(kind="MOVED", source=str(src), dest=str(dest)))
        except OSError as exc:
            actions.append(MovieAction(
                kind="WARN", source=str(src),
                detail=f"filesystem error – {src}: {exc}"
            ))

    # Execution pass — deletes
    print("Deleting junk files...", flush=True)
    for src in deletes:
        if not src.exists():
            continue
        try:
            os.remove(src)
            actions.append(MovieAction(kind="DELETED", source=str(src)))
        except OSError as exc:
            actions.append(MovieAction(
                kind="WARN", source=str(src),
                detail=f"filesystem error – {src}: {exc}"
            ))

    # Folder pruning — bottom-up, never delete root
    candidate_dirs = sorted(source_dirs, key=lambda p: len(p.parts), reverse=True)
    for directory in candidate_dirs:
        if directory == root:
            continue
        if not directory.exists():
            continue
        remaining = list(directory.iterdir())
        # Skip if any unknown-extension files remain
        has_unknown = any(
            f.is_file() and f.suffix.lower() not in MEDIA_EXTS and f.suffix.lower() not in JUNK_EXTS
            for f in remaining
        )
        if has_unknown:
            continue
        # Delete remaining junk
        for item in remaining:
            if item.is_file() and item.suffix.lower() in JUNK_EXTS:
                try:
                    os.remove(item)
                    actions.append(MovieAction(kind="DELETED", source=str(item)))
                except OSError:
                    pass
        # Remove if now empty
        try:
            if not list(directory.iterdir()):
                directory.rmdir()
                actions.append(MovieAction(kind="DELETED", source=str(directory)))
        except OSError:
            pass

    return actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_actions(actions: list[MovieAction]) -> None:
    for a in actions:
        if a.kind == "MOVED":
            print(f"MOVED: {a.source} → {a.dest}")
        elif a.kind == "DELETED":
            print(f"DELETED: {a.source}")
        elif a.kind == "WARN":
            print(f"WARN: {a.detail}")
        elif a.kind == "CONFLICT":
            print(f"CONFLICT: {a.source} → {a.dest} ({a.detail})")
        elif a.kind == "SKIPPED":
            pass  # already correct, no noise


def _print_summary(actions: list[MovieAction]) -> None:
    moved    = sum(1 for a in actions if a.kind == "MOVED")
    deleted  = sum(1 for a in actions if a.kind == "DELETED")
    warnings = sum(1 for a in actions if a.kind == "WARN")
    conflicts= sum(1 for a in actions if a.kind == "CONFLICT")
    print("--- Summary ---")
    print(f"Files moved:  {moved}")
    print(f"Files deleted:{deleted}")
    print(f"Warnings:     {warnings}")
    print(f"Conflicts:    {conflicts}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Organise movie files")
    parser.add_argument("root", nargs="?", help="Movies root directory")
    parser.add_argument("--test", metavar="PATH", help="Run on a timestamped copy of PATH")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite conflicts")
    args = parser.parse_args()

    if args.test is not None:
        test_path = pathlib.Path(args.test)
        if not test_path.exists() or not test_path.is_dir():
            print(f"ERROR: {args.test} does not exist or is not a directory")
            raise SystemExit(1)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        temp_copy = test_path.parent / f"{test_path.name}_{timestamp}"
        shutil.copytree(str(test_path), str(temp_copy))
        abs_temp = temp_copy.resolve()
        print(f"TESTMODE: working copy at {abs_temp}")
        actions = organise_movies(temp_copy, overwrite=args.overwrite)
        _print_actions(actions)
        _print_summary(actions)
        print(f"TESTMODE: result at {abs_temp}")

    elif args.root is not None:
        root_path = pathlib.Path(args.root)
        if not root_path.exists() or not root_path.is_dir():
            print(f"ERROR: {args.root} does not exist or is not a directory")
            raise SystemExit(1)
        actions = organise_movies(root_path, overwrite=args.overwrite)
        _print_actions(actions)
        _print_summary(actions)

    else:
        parser.print_usage()
        raise SystemExit(1)


if __name__ == "__main__":
    main()

# TV-Shows-Sorting

A single-file Python script that reorganises messy TV show downloads into a clean, browsable folder hierarchy.

## Output structure

```
<TV Shows Root>/
  <Show Name>/
    <Show Name - Season X>/
      <Show Name - Season X - Episode Y>.ext
```

For example:

```
Ancient.Aliens.S20E01.1080p.WEB.h264-EDITH[EZTVx.to].mkv
  →  Ancient Aliens/Ancient Aliens - Season 20/Ancient Aliens - Season 20 - Episode 1.mkv
```

## Requirements

- Python 3.10+
- No third-party runtime dependencies (stdlib only)

To run the tests:

```bash
pip install hypothesis pytest
```

## Usage

### Organise a folder

```bash
python organise.py <path/to/TV Shows Root>
```

Recursively walks the folder, moves every parseable media file to its correct location, deletes junk files (`.nfo`, `.txt`, `.jpg`, etc.), and removes empty folders.

### Dry run (test mode)

```bash
python organise.py --test <path/to/TV Shows Root>
```

Creates a timestamped copy of the folder (e.g. `TV-Shows-Root_20240611T120000Z`) in the same parent directory, runs the organiser on the copy, and leaves the original completely untouched. The copy remains on disk so you can inspect the result.

### Overwrite conflicts

```bash
python organise.py --overwrite <path/to/TV Shows Root>
python organise.py --test <path/to/TV Shows Root> --overwrite
```

If a destination file already exists, `--overwrite` replaces it. Without this flag, conflicts are logged and the source file is left in place.

## Output

Every action is logged to stdout:

```
TESTMODE: working copy at C:\...\TV-Shows-Root_20240611T120000Z
CREATED: C:\...\Ancient Aliens\Ancient Aliens - Season 20
MOVED:   C:\...\Ancient.Aliens.S20E01.mkv → C:\...\Ancient Aliens - Season 20 - Episode 1.mkv
DELETED: C:\...\show.nfo
WARN:    unparseable – C:\...\some_unrecognised_file.mkv
CONFLICT: C:\...\src.mkv → C:\...\dest.mkv (skipped; use --overwrite to replace)

--- Summary ---
Files moved:     12
Folders created: 6
Files deleted:   4
Warnings:        1
Conflicts:       0
```

## What it handles

| Source pattern | Result |
|---|---|
| `Ancient.Aliens.S20E01.1080p.WEB.h264-EDITH[EZTVx.to].mkv` | `Ancient Aliens/Ancient Aliens - Season 20/Ancient Aliens - Season 20 - Episode 1.mkv` |
| `Resident Alien S03E07 Here Comes My Baby 1080p AMZN WEB-DL.mkv` | `Resident Alien/Resident Alien - Season 3/Resident Alien - Season 3 - Episode 7.mkv` |
| `silo.s02e04.multi.1080p.web.h264.mkv` (lowercase) | `Silo/Silo - Season 2/Silo - Season 2 - Episode 4.mkv` |
| Season pack folder (`Criminal.Record.S01.COMPLETE.720p...`) | All episodes unpacked into `Criminal Record/Criminal Record - Season 1/` |
| Junk files (`.nfo`, `.txt`, `.jpg`, `.srt`, etc.) | Deleted |
| Sample files (`...sample.mkv`) | Deleted |
| Unknown extension files | Left in place with a `WARN` log entry |

## Running tests

```bash
python -m pytest tests/ -v
```

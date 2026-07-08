# TV-Shows-Sorting

Two single-file Python scripts that organise messy TV show and movie downloads into clean, Plex-ready folder structures.

## Requirements

- Python 3.10+
- No third-party runtime dependencies (stdlib only)

---

## TV Shows — `organise.py`

### Output structure

```
<TV Shows Root>/
  <Show Name>/
    Season X/
      <Show Name> - SxxEyy.ext
```

Example:

```
Ancient.Aliens.S20E01.1080p.WEB.h264-EDITH[EZTVx.to].mkv
  →  Ancient Aliens/Season 20/Ancient Aliens - S20E01.mkv
```

### Usage

```bash
# Organise your TV shows folder
python organise.py "E:\TV Shows"

# Dry run on a timestamped copy (original untouched)
python organise.py --test "E:\TV Shows"

# Overwrite conflicts
python organise.py --overwrite "E:\TV Shows"
```

### What it handles

| Source pattern | Result |
|---|---|
| `Ancient.Aliens.S20E01.1080p.WEB.h264-EDITH[EZTVx.to].mkv` | `Ancient Aliens/Season 20/Ancient Aliens - S20E01.mkv` |
| `Resident Alien S03E07 Here Comes My Baby 1080p AMZN WEB-DL.mkv` | `Resident Alien/Season 3/Resident Alien - S03E07.mkv` |
| `silo.s02e04.multi.1080p.web.h264.mkv` (lowercase) | `Silo/Season 2/Silo - S02E04.mkv` |
| `Silo.S02E05-09.mkv` (multi-episode range) | `Silo/Season 2/Silo - S02E05.mkv` |
| Season pack folder (`Criminal.Record.S01.COMPLETE...`) | All episodes unpacked into `Criminal Record/Season 1/` |
| `www.UIndex.org - Alien Earth S01E05...mkv` (site prefix) | `Alien Earth/Season 1/Alien Earth - S01E05.mkv` |
| Junk files (`.nfo`, `.txt`, `.jpg`, `.srt`, etc.) | Deleted |
| Sample files (`...sample.mkv`) | Deleted |
| Already correctly placed files | Skipped (idempotent) |
| Unknown extension files | Left in place with a `WARN` log entry |

### Show name aliases

The script normalises known variant names automatically. Edit `SHOW_NAME_ALIASES` in `organise.py` to add more:

```python
SHOW_NAME_ALIASES: dict[str, str] = {
    "ds9":                 "Star Trek Deep Space Nine",
    "voyager":             "Star Trek Voyager",
    "house md":            "House M.D.",
    "stargate sg 1":       "Stargate SG-1",
    # add your own here...
}
```

---

## Movies — `organise_movies.py`

### Output structure

```
<Movies Root>/
  <Movie Title>.ext
```

Example:

```
Avatar.The.Way.Of.Water.2022.BLURAY.1080p.BluRay.x264.AAC5.1-LAMA.mkv
  →  Movies/Avatar the Way of Water.mkv
```

### Usage

```bash
# Organise your Movies folder
python organise_movies.py "E:\Movies"

# Dry run on a timestamped copy (original untouched)
python organise_movies.py --test "E:\Movies"

# Overwrite conflicts
python organise_movies.py --overwrite "E:\Movies"
```

### What it handles

| Source | Result |
|---|---|
| `Avatar.The.Way.Of.Water.2022.BLURAY.1080p.x264-LAMA.mkv` | `Avatar the Way of Water.mkv` |
| `No Time To Die (2021) [1080p] [WEBRip] [YTS.MX].mkv` | `No Time to Die.mkv` |
| `oppenheimer.2023.1080p.web.h264.mkv` | `Oppenheimer.mkv` |
| Junk files (`.nfo`, `.txt`, `.jpg`, etc.) | Deleted |
| Empty folders after organising | Removed |
| Already correctly named files | Skipped (idempotent) |

---

## Output log format

Both scripts log every action to stdout:

```
Scanning files...
  Scanned 100 files...
Scan complete: 243 files found. Planning 18 moves...
Moving files...
MOVED: E:\...\source.mkv → E:\...\Clean Name.mkv
DELETED: E:\...\junk.nfo
WARN: unparseable – E:\...\unrecognised_file.mkv
CONFLICT: E:\...\src.mkv → E:\...\dest.mkv (skipped; use --overwrite to replace)

--- Summary ---
Files moved:   18
Files deleted: 7
Warnings:      2
Conflicts:     0
```

## Windows permissions

If you see `[WinError 5] Access is denied` errors, run this in an admin PowerShell to strip read-only flags:

```powershell
Get-ChildItem -Path "E:\TV Shows" -Recurse | ForEach-Object { $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly) }
```

## Running tests

```bash
pip install hypothesis pytest
python -m pytest tests/ -v
```

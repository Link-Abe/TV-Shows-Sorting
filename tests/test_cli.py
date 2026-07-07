"""
CLI example-based tests for the TV Shows Organiser.

Covers:
- test_cli.py: Task 7.2
  - --test with valid reference folder: working copy created, printed path correct,
    original folder unchanged.
  - --test with nonexistent path: exit code 1 and error message.
  - --overwrite flag: conflicting file is overwritten and logged as MOVED.
  - Summary block output format.
  - Normal mode with valid root.
  - Normal mode with invalid root: exit code 1 and error message.
  - No args: exit code 1.

Requirements: 5.1–5.8, 6.5, 6.6
"""

import subprocess
import sys
import tempfile
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_organiser(*args: str) -> subprocess.CompletedProcess:
    """Run organise.py as a subprocess and return the CompletedProcess."""
    script = Path(__file__).parent.parent / "organise.py"
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def make_media_file(path: Path) -> None:
    """Create a zero-byte .mkv file at path (creating parent dirs as needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


# ---------------------------------------------------------------------------
# Test-mode tests (Req 5.1–5.8)
# ---------------------------------------------------------------------------


def test_test_mode_creates_working_copy():
    """
    --test PATH creates a timestamped copy in the same parent directory.
    The original folder must be unchanged. (Req 5.1, 5.2, 5.4)
    """
    with tempfile.TemporaryDirectory() as parent:
        ref = Path(parent) / "TV-Shows-Ref"
        ref.mkdir()
        make_media_file(ref / "silo.s02e04.multi.1080p.web.h264-higgsboson.mkv")

        result = run_organiser("--test", str(ref))

        assert result.returncode == 0

        # Original folder must still exist and be unchanged
        assert ref.is_dir()
        original_files = list(ref.rglob("*"))
        assert any(f.name == "silo.s02e04.multi.1080p.web.h264-higgsboson.mkv" for f in original_files)

        # A new sibling folder must have been created
        siblings = [d for d in Path(parent).iterdir() if d != ref and d.is_dir()]
        assert len(siblings) == 1, "Expected exactly one working-copy folder"
        copy_dir = siblings[0]
        assert copy_dir.name.startswith("TV-Shows-Ref_")


def test_test_mode_prints_working_copy_path_before_operations():
    """
    TESTMODE: working copy at <path> is printed before any action output. (Req 5.6)
    """
    with tempfile.TemporaryDirectory() as parent:
        ref = Path(parent) / "TV-Shows-Ref"
        ref.mkdir()
        make_media_file(ref / "silo.s02e04.multi.1080p.web.h264-higgsboson.mkv")

        result = run_organiser("--test", str(ref))

        lines = result.stdout.splitlines()
        assert lines[0].startswith("TESTMODE: working copy at "), (
            f"First line should be TESTMODE: working copy at ..., got: {lines[0]!r}"
        )


def test_test_mode_prints_result_path_as_last_line():
    """
    TESTMODE: result at <path> is the last line of output. (Req 5.7)
    """
    with tempfile.TemporaryDirectory() as parent:
        ref = Path(parent) / "TV-Shows-Ref"
        ref.mkdir()
        make_media_file(ref / "silo.s02e04.multi.1080p.web.h264-higgsboson.mkv")

        result = run_organiser("--test", str(ref))

        lines = [l for l in result.stdout.splitlines() if l.strip()]
        assert lines[-1].startswith("TESTMODE: result at "), (
            f"Last line should be TESTMODE: result at ..., got: {lines[-1]!r}"
        )


def test_test_mode_both_paths_are_same():
    """
    The path printed at start and end of test mode must be the same absolute path.
    (Req 5.6, 5.7)
    """
    with tempfile.TemporaryDirectory() as parent:
        ref = Path(parent) / "TV-Shows-Ref"
        ref.mkdir()
        make_media_file(ref / "silo.s02e04.1080p.web.h264.mkv")

        result = run_organiser("--test", str(ref))
        assert result.returncode == 0

        lines = result.stdout.splitlines()
        first_path = lines[0].replace("TESTMODE: working copy at ", "").strip()
        non_empty = [l for l in lines if l.strip()]
        last_path = non_empty[-1].replace("TESTMODE: result at ", "").strip()

        assert first_path == last_path


def test_test_mode_leaves_temp_copy_in_place():
    """
    The temporary working copy is NOT deleted after test mode completes. (Req 5.5)
    """
    with tempfile.TemporaryDirectory() as parent:
        ref = Path(parent) / "TV-Shows-Ref"
        ref.mkdir()
        make_media_file(ref / "silo.s02e04.1080p.web.h264.mkv")

        result = run_organiser("--test", str(ref))
        assert result.returncode == 0

        lines = result.stdout.splitlines()
        temp_path = lines[0].replace("TESTMODE: working copy at ", "").strip()
        assert Path(temp_path).is_dir(), "Temp copy must remain on disk after test mode"


def test_test_mode_invalid_path_exits_1():
    """
    --test with a nonexistent path prints an error and exits with code 1. (Req 5.8)
    """
    result = run_organiser("--test", "/this/path/does/not/exist/at/all")
    assert result.returncode == 1
    assert "ERROR" in result.stdout or "ERROR" in result.stderr
    assert "does not exist or is not a directory" in result.stdout or \
           "does not exist or is not a directory" in result.stderr


def test_test_mode_file_path_not_dir_exits_1(tmp_path):
    """
    --test with a file (not a directory) prints an error and exits 1. (Req 5.8)
    """
    f = tmp_path / "not_a_dir.txt"
    f.write_text("hello")

    result = run_organiser("--test", str(f))
    assert result.returncode == 1
    assert "does not exist or is not a directory" in result.stdout or \
           "does not exist or is not a directory" in result.stderr


def test_test_mode_no_temp_copy_created_on_invalid_path():
    """
    No files are created when --test path is invalid. (Req 5.8)
    """
    with tempfile.TemporaryDirectory() as parent:
        nonexistent = str(Path(parent) / "does_not_exist")
        result = run_organiser("--test", nonexistent)
        assert result.returncode == 1
        # No sibling copy should have been created
        remaining = list(Path(parent).iterdir())
        assert remaining == [], f"No files should be created, but found: {remaining}"


def test_test_mode_original_unchanged_after_run():
    """
    Organiser must not touch the original reference folder in test mode. (Req 5.2)
    """
    with tempfile.TemporaryDirectory() as parent:
        ref = Path(parent) / "TV-Shows-Ref"
        ref.mkdir()
        original_file = ref / "silo.s02e04.multi.1080p.web.h264-higgsboson.mkv"
        original_file.touch()

        result = run_organiser("--test", str(ref))
        assert result.returncode == 0

        # Original file must still be at the exact original path
        assert original_file.exists(), "Original file must be unchanged by test mode"


# ---------------------------------------------------------------------------
# Normal mode tests (Req 6.1–6.6)
# ---------------------------------------------------------------------------


def test_normal_mode_organises_files(tmp_path):
    """
    Normal mode: files are moved to the correct target path and logged. (Req 2.1, 6.1)
    """
    make_media_file(tmp_path / "silo.s02e04.multi.1080p.web.h264-higgsboson.mkv")

    result = run_organiser(str(tmp_path))

    assert result.returncode == 0
    expected = tmp_path / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
    assert expected.exists()
    assert "MOVED:" in result.stdout


def test_normal_mode_invalid_root_exits_1():
    """
    Normal mode with a nonexistent root exits with code 1 and prints an error.
    """
    result = run_organiser("/this/path/does/not/exist")
    assert result.returncode == 1
    assert "does not exist or is not a directory" in result.stdout or \
           "does not exist or is not a directory" in result.stderr


def test_normal_mode_root_is_file_exits_1(tmp_path):
    """
    Normal mode with a file as root exits with code 1.
    """
    f = tmp_path / "notadir.mkv"
    f.touch()
    result = run_organiser(str(f))
    assert result.returncode == 1


def test_no_args_exits_1():
    """
    Calling with no arguments exits with code 1.
    """
    result = run_organiser()
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Summary block format (Req 6.6)
# ---------------------------------------------------------------------------


def test_summary_block_format(tmp_path):
    """
    The summary block must appear with the correct headings and numeric values.
    """
    make_media_file(tmp_path / "silo.s02e04.multi.1080p.web.h264.mkv")
    make_media_file(tmp_path / "show.info.txt")  # junk file

    result = run_organiser(str(tmp_path))
    assert result.returncode == 0

    stdout = result.stdout
    assert "--- Summary ---" in stdout
    assert "Files moved:" in stdout
    assert "Folders created:" in stdout
    assert "Files deleted:" in stdout
    assert "Warnings:" in stdout
    assert "Conflicts:" in stdout


def test_summary_counts_are_correct(tmp_path):
    """
    Summary counts accurately reflect what happened. (Req 6.6)
    """
    make_media_file(tmp_path / "silo.s02e04.multi.1080p.web.h264.mkv")
    (tmp_path / "junk.nfo").write_text("junk")

    result = run_organiser(str(tmp_path))
    assert result.returncode == 0

    lines = result.stdout.splitlines()
    # Parse summary lines
    summary = {l.split(":")[0].strip(): l.split(":")[-1].strip()
               for l in lines if ":" in l and l.startswith(("Files", "Folders", "Warnings", "Conflicts"))}

    assert int(summary.get("Files moved", -1)) == 1
    assert int(summary.get("Files deleted", -1)) == 1  # junk.nfo deleted
    assert int(summary.get("Folders created", -1)) >= 1  # at least one season folder


# ---------------------------------------------------------------------------
# --overwrite flag tests (Req 6.5)
# ---------------------------------------------------------------------------


def test_overwrite_flag_replaces_conflict(tmp_path):
    """
    With --overwrite, a conflicting destination file is replaced and logged as MOVED.
    """
    # Create source file
    src = tmp_path / "silo.s02e04.multi.1080p.web.h264.mkv"
    src.write_bytes(b"source content")

    # Pre-create the destination file (simulating a conflict)
    dest = tmp_path / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old content")

    result = run_organiser("--overwrite", str(tmp_path))

    assert result.returncode == 0
    assert "MOVED:" in result.stdout
    assert "CONFLICT:" not in result.stdout
    # Destination should now contain the source content
    assert dest.read_bytes() == b"source content"


def test_without_overwrite_conflict_is_logged(tmp_path):
    """
    Without --overwrite, a conflicting destination file logs CONFLICT and leaves
    the source in place.
    """
    src = tmp_path / "silo.s02e04.multi.1080p.web.h264.mkv"
    src.write_bytes(b"source content")

    dest = tmp_path / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"old content")

    result = run_organiser(str(tmp_path))

    assert result.returncode == 0
    assert "CONFLICT:" in result.stdout
    # Source must remain in place
    assert src.exists()
    # Destination must be untouched
    assert dest.read_bytes() == b"old content"


# ---------------------------------------------------------------------------
# Log format tests (Req 6.1–6.4)
# ---------------------------------------------------------------------------


def test_moved_log_format(tmp_path):
    """MOVED log entries use the format: MOVED: <src> → <dest>  (Req 6.1)"""
    make_media_file(tmp_path / "silo.s02e04.1080p.web.h264.mkv")
    result = run_organiser(str(tmp_path))
    assert result.returncode == 0
    moved_lines = [l for l in result.stdout.splitlines() if l.startswith("MOVED:")]
    assert len(moved_lines) >= 1
    assert "→" in moved_lines[0]


def test_created_log_format(tmp_path):
    """CREATED log entries use the format: CREATED: <folder_path>  (Req 6.2)"""
    make_media_file(tmp_path / "silo.s02e04.1080p.web.h264.mkv")
    result = run_organiser(str(tmp_path))
    assert result.returncode == 0
    created_lines = [l for l in result.stdout.splitlines() if l.startswith("CREATED:")]
    assert len(created_lines) >= 1


def test_deleted_log_format(tmp_path):
    """DELETED log entries use the format: DELETED: <path>  (Req 6.3)"""
    (tmp_path / "garbage.nfo").write_text("nfo junk")
    result = run_organiser(str(tmp_path))
    assert result.returncode == 0
    deleted_lines = [l for l in result.stdout.splitlines() if l.startswith("DELETED:")]
    assert len(deleted_lines) >= 1


def test_warn_log_format_unparseable(tmp_path):
    """WARN log entries for unparseable filenames use: WARN: unparseable – <path>  (Req 6.4)"""
    make_media_file(tmp_path / "movie_no_season.mkv")
    result = run_organiser(str(tmp_path))
    assert result.returncode == 0
    warn_lines = [l for l in result.stdout.splitlines() if l.startswith("WARN:")]
    assert any("unparseable" in l for l in warn_lines)


def test_conflict_log_format(tmp_path):
    """CONFLICT entries use: CONFLICT: <src> → <dest> (skipped; use --overwrite to replace)  (Req 6.5)"""
    src = tmp_path / "silo.s02e04.1080p.web.h264.mkv"
    src.touch()

    dest = tmp_path / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
    dest.parent.mkdir(parents=True)
    dest.touch()

    result = run_organiser(str(tmp_path))
    assert result.returncode == 0
    conflict_lines = [l for l in result.stdout.splitlines() if l.startswith("CONFLICT:")]
    assert len(conflict_lines) >= 1
    assert "→" in conflict_lines[0]
    assert "skipped; use --overwrite to replace" in conflict_lines[0]

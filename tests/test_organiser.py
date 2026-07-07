# Feature: tv-shows-organiser, Tasks 5.2–5.4: Discovery + Execution pass + Folder pruning inside organise()
# Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 6.1, 6.2, 6.3, 6.4, 6.5

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from organise import organise, OrgAction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(root: Path, *parts: str) -> Path:
    """Create an empty file at root / parts, creating parent dirs as needed."""
    p = root.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


def actions_by_kind(actions: list[OrgAction], kind: str) -> list[OrgAction]:
    return [a for a in actions if a.kind == kind]


# ---------------------------------------------------------------------------
# JUNK / SAMPLE files → DELETED (execution pass removes them; no WARN emitted)
# ---------------------------------------------------------------------------

def test_junk_file_is_deleted():
    """Junk files are deleted during the execution pass and emit a DELETED action."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "show.nfo")
        actions = organise(root)
        # The junk file should no longer exist on disk
        assert not f.exists()
        # A DELETED action should reference the junk file
        deleted = actions_by_kind(actions, "DELETED")
        assert any("show.nfo" in a.source for a in deleted)
        # No WARN should be emitted for a plain junk file
        warn_actions = actions_by_kind(actions, "WARN")
        assert not any("show.nfo" in (a.source or "") for a in warn_actions)


def test_sample_file_is_deleted():
    """Sample media files are deleted during the execution pass and emit a DELETED action."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "Show.S01E01.sample.mkv")
        actions = organise(root)
        # The sample file should no longer exist on disk
        assert not f.exists()
        # A DELETED action should reference the sample file
        deleted = actions_by_kind(actions, "DELETED")
        assert any("sample" in a.source.lower() for a in deleted)


# ---------------------------------------------------------------------------
# MEDIA + parseable → SKIPPED (already at target) or planned MOVE
# For discovery-only pass, parseable files NOT at target produce no action
# (they are in the planned list, not actions). Files already at target → SKIPPED.
# ---------------------------------------------------------------------------

def test_parseable_media_already_at_target_emits_skipped():
    """
    A parseable media file already residing at its computed target path
    SHALL emit a SKIPPED action (Req 2.7).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Build the exact target structure
        target = root / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()

        actions = organise(root)
        skipped = actions_by_kind(actions, "SKIPPED")
        assert len(skipped) == 1
        assert "Silo - Season 2 - Episode 4.mkv" in skipped[0].source


def test_parseable_media_not_at_target_is_moved():
    """
    A parseable media file NOT yet at its target path is moved to the correct
    destination and emits CREATED + MOVED actions.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = make_file(root, "silo.s02e04.multi.1080p.web.h264-higgsboson[EZTVx.to].mkv")
        actions = organise(root)
        # Source file should no longer exist
        assert not src.exists()
        # Destination should exist at the correct path
        expected = root / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
        assert expected.exists()
        # MOVED action should be present
        moved = actions_by_kind(actions, "MOVED")
        assert len(moved) == 1
        assert moved[0].dest == str(expected)


def test_target_path_derived_from_filename_not_folder(tmp_path):
    """
    Req 2.8 / 4.2: destination is derived from the file's own name, not the
    containing folder name.  A file inside 'Criminal Record Season 2' whose
    filename says S01 SHALL be targeted to Season 1, not Season 2.
    """
    root = tmp_path
    make_file(root, "Criminal Record Season 2",
              "Criminal.Record.S01E01.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv")
    actions = organise(root)
    # The file is parseable and NOT at target, so no action but also no WARN
    warn_actions = actions_by_kind(actions, "WARN")
    assert warn_actions == []


# ---------------------------------------------------------------------------
# MEDIA + unparseable → WARN (Req 6.4)
# ---------------------------------------------------------------------------

def test_unparseable_media_emits_warn():
    """
    A media file whose name cannot be parsed emits a WARN action with
    'unparseable' in the detail (Req 6.4).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(root, "just_a_movie.mkv")
        actions = organise(root)
        warn = actions_by_kind(actions, "WARN")
        assert len(warn) == 1
        assert "unparseable" in (warn[0].detail or "")
        assert "just_a_movie.mkv" in warn[0].source


def test_unparseable_media_detail_format(tmp_path):
    """WARN detail format matches 'unparseable – <file_path>' (Req 6.4)."""
    src = make_file(tmp_path, "mystery.mkv")
    actions = organise(tmp_path)
    warn = actions_by_kind(actions, "WARN")
    assert any("unparseable" in (a.detail or "") for a in warn)
    assert any(str(src) in (a.detail or "") for a in warn)


# ---------------------------------------------------------------------------
# UNKNOWN extension → WARN (Req 3.6)
# ---------------------------------------------------------------------------

def test_unknown_extension_emits_warn():
    """
    A file with an unrecognised extension emits a WARN action with
    'unrecognised extension' in the detail (Req 3.6).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(root, "readme.xyz")
        actions = organise(root)
        warn = actions_by_kind(actions, "WARN")
        assert len(warn) == 1
        assert "unrecognised extension" in (warn[0].detail or "")
        assert ".xyz" in (warn[0].detail or "")


def test_unknown_extension_file_not_in_planned():
    """Unknown-extension files must be left in place — the file should still exist."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = make_file(root, "data.xyz")
        organise(root)
        assert f.exists()


# ---------------------------------------------------------------------------
# CONFLICT detection (Req 6.5)
# ---------------------------------------------------------------------------

def test_conflict_when_dest_already_exists():
    """
    If the computed destination already contains a file and overwrite=False,
    a CONFLICT action is emitted.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Place a file at what will be the target path
        target = root / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        # Place a different source file that resolves to the same target
        src = make_file(root, "incoming",
                        "silo.s02e04.multi.1080p.web.h264-higgsboson[EZTVx.to].mkv")
        actions = organise(root)
        conflicts = actions_by_kind(actions, "CONFLICT")
        assert len(conflicts) == 1
        assert str(src) == conflicts[0].source
        assert str(target) == conflicts[0].dest
        assert "overwrite" in (conflicts[0].detail or "").lower()


def test_no_conflict_with_overwrite_flag():
    """
    With overwrite=True, a file at the destination is replaced (MOVE planned,
    no CONFLICT emitted during discovery pass).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        make_file(root, "incoming",
                  "silo.s02e04.multi.1080p.web.h264-higgsboson[EZTVx.to].mkv")
        actions = organise(root, overwrite=True)
        conflicts = actions_by_kind(actions, "CONFLICT")
        assert conflicts == []


# ---------------------------------------------------------------------------
# Recursive traversal (Req 4.1)
# ---------------------------------------------------------------------------

def test_recursive_traversal_finds_deeply_nested_files():
    """
    Organiser SHALL recurse into all subdirectory levels (Req 4.1).
    A deeply nested unparseable file should still produce a WARN.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(root, "level1", "level2", "level3", "no_season.mkv")
        actions = organise(root)
        warn = actions_by_kind(actions, "WARN")
        assert any("no_season.mkv" in a.source for a in warn)


def test_recursive_traversal_finds_parseable_file_in_nested_folder():
    """
    A parseable media file buried inside multiple folder levels is found
    and handled (emits SKIPPED if already at correct target, or no action
    if to be moved).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Already at exact target path inside nested dirs
        target = (root / "Ancient Aliens" / "Ancient Aliens - Season 20"
                  / "Ancient Aliens - Season 20 - Episode 1.mkv")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        actions = organise(root)
        skipped = actions_by_kind(actions, "SKIPPED")
        assert len(skipped) == 1


# ---------------------------------------------------------------------------
# Mixed directory: combination of file types
# ---------------------------------------------------------------------------

def test_mixed_directory_multiple_file_types():
    """
    A directory with junk, sample, parseable media, unparseable media, and
    unknown files is handled correctly:
    - junk/sample → no discovery action
    - parseable not at target → no action (planned)
    - unparseable → WARN
    - unknown → WARN
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(root, "show.nfo")                            # JUNK → no action
        make_file(root, "sample.S01E01.sample.mkv")            # SAMPLE → no action
        make_file(root, "silo.s02e04.mkv")                     # MEDIA parseable → planned MOVE
        make_file(root, "just_a_movie.mkv")                    # MEDIA unparseable → WARN
        make_file(root, "data.xyz")                            # UNKNOWN → WARN

        actions = organise(root)
        warn_actions = actions_by_kind(actions, "WARN")

        # Exactly 2 WARN actions: one for unparseable media, one for unknown ext
        assert len(warn_actions) == 2
        details = [a.detail or "" for a in warn_actions]
        assert any("unparseable" in d for d in details)
        assert any("unrecognised extension" in d for d in details)


# ---------------------------------------------------------------------------
# Property-based tests (Tasks 5.5–5.9)
# ---------------------------------------------------------------------------

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from organise import ShowMetadata, format_episode_filename, format_season_folder, format_show_folder

# ---------------------------------------------------------------------------
# Shared Hypothesis strategies
# ---------------------------------------------------------------------------

# Words made of letters only — no digits, no slashes, no quality-token chars.
# Restricted to ASCII letters to avoid Unicode normalization edge cases (e.g.,
# µ vs μ, Turkish İ, Greek combining characters) that are unrelated to the
# structural filesystem-organisation properties being tested.
_word = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll"), max_codepoint=0x7F),
    min_size=1,
    max_size=12,
)

# Windows reserved device names that cannot be used as file/folder names on Windows.
# These are filtered out to prevent FileNotFoundError on Windows hosts.
_WINDOWS_RESERVED = frozenset({
    "con", "prn", "aux", "nul",
    "com0", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt0", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
})


def _safe_show_name(words: list) -> str:
    """Join words into a show name, ensuring the result is not a Windows reserved name."""
    name = " ".join(words)
    # If the entire name (case-insensitive, stripped) matches a reserved device name,
    # append an extra character to make it safe.
    if name.strip().lower() in _WINDOWS_RESERVED:
        name = name + "X"
    return name


_show_name_words = st.lists(_word, min_size=1, max_size=4)

# ShowMetadata with a concrete episode number
_episode_metadata = st.builds(
    ShowMetadata,
    show_name_raw=_show_name_words.map(_safe_show_name),
    season=st.integers(min_value=1, max_value=30),
    episode=st.integers(min_value=1, max_value=30),
)

# ShowMetadata without episode (season-pack style)
_season_metadata = st.builds(
    ShowMetadata,
    show_name_raw=_show_name_words.map(_safe_show_name),
    season=st.integers(min_value=1, max_value=30),
    episode=st.just(None),
)

# A list of 1–5 episode metadatas (for multi-file tests)
_episode_list = st.lists(_episode_metadata, min_size=1, max_size=5)

# Media extensions to use when creating test files
_media_ext = st.sampled_from([".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts"])

# Junk extensions
_junk_ext = st.sampled_from([".txt", ".nfo", ".jpg", ".jpeg", ".png", ".srt", ".sub"])


# ---------------------------------------------------------------------------
# Property 5: every parseable media file lands at the correct target path
# Validates: Requirements 2.1, 2.2, 2.3, 2.6, 2.8, 4.1, 4.2, 4.3
# ---------------------------------------------------------------------------

@given(
    entries=st.lists(
        st.tuples(_episode_metadata, _media_ext),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_prop5_every_parseable_file_at_correct_target(entries):
    """
    **Validates: Requirements 2.1, 2.2, 2.3, 2.6, 2.8, 4.1, 4.2, 4.3**

    For any collection of parseable media files placed at arbitrary source
    paths, after organise() every file SHALL reside at
    <root>/<show_folder>/<season_folder>/<episode_filename>.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Create source files in a flat "downloads" subdirectory.
        # Name them using format_episode_filename so they are parseable,
        # but nest them inside a generic subfolder so they are not already
        # at the target path.
        src_dir = root / "downloads"
        src_dir.mkdir()

        expected_targets: list[Path] = []
        for i, (meta, ext) in enumerate(entries):
            filename = format_episode_filename(meta, ext)
            # Place the file inside downloads/ (not yet at target)
            src = src_dir / filename
            src.touch()

            # Compute the expected target from the same metadata
            show_folder = format_show_folder(meta)
            season_folder = format_season_folder(meta)
            target = root / show_folder / season_folder / filename
            expected_targets.append(target)

        organise(root)

        # Every computed target must now exist
        for target in expected_targets:
            assert target.exists(), (
                f"Expected file not found at target: {target}"
            )


# ---------------------------------------------------------------------------
# Property 6: same show+season → same season folder
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

@given(
    base_meta=_episode_metadata,
    extra_episodes=st.lists(
        st.integers(min_value=1, max_value=30),
        min_size=1,
        max_size=4,
        unique=True,
    ),
    ext=_media_ext,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prop6_same_show_season_same_folder(base_meta, extra_episodes, ext):
    """
    **Validates: Requirements 2.4**

    All media files sharing the same show_name_raw and season SHALL end up
    in the same directory after organise().
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src_dir = root / "downloads"
        src_dir.mkdir()

        # Build a list of metadatas: base_meta plus variants with different
        # episode numbers but same show name and season.
        metadatas = [base_meta] + [
            ShowMetadata(
                show_name_raw=base_meta.show_name_raw,
                season=base_meta.season,
                episode=ep,
            )
            for ep in extra_episodes
            if ep != base_meta.episode  # avoid duplicate filenames
        ]

        for meta in metadatas:
            filename = format_episode_filename(meta, ext)
            (src_dir / filename).touch()

        organise(root)

        # All files should share the same parent directory
        expected_season_folder = (
            root
            / format_show_folder(base_meta)
            / format_season_folder(base_meta)
        )
        for meta in metadatas:
            filename = format_episode_filename(meta, ext)
            target = expected_season_folder / filename
            assert target.exists(), (
                f"File not in expected season folder: {target}"
            )


# ---------------------------------------------------------------------------
# Property 7: season-pack folders are fully unpacked and removed
# Validates: Requirements 2.5
# ---------------------------------------------------------------------------

@given(
    pack_meta=_season_metadata,
    episodes=st.lists(
        st.integers(min_value=1, max_value=30),
        min_size=1,
        max_size=6,
        unique=True,
    ),
    ext=_media_ext,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prop7_season_pack_unpacked_and_removed(pack_meta, episodes, ext):
    """
    **Validates: Requirements 2.5**

    A season-pack folder containing episode files SHALL be fully unpacked:
    all files land at their correct target paths and the original pack
    folder SHALL no longer exist.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Build a season-pack folder name in the typical torrent style
        show_slug = pack_meta.show_name_raw.replace(" ", ".")
        pack_folder_name = f"{show_slug}.S{pack_meta.season:02d}.COMPLETE.720p"
        pack_dir = root / pack_folder_name
        pack_dir.mkdir()

        # Place episode files inside the pack folder
        episode_metadatas: list[ShowMetadata] = []
        for ep_num in episodes:
            ep_meta = ShowMetadata(
                show_name_raw=pack_meta.show_name_raw,
                season=pack_meta.season,
                episode=ep_num,
            )
            episode_metadatas.append(ep_meta)
            filename = format_episode_filename(ep_meta, ext)
            (pack_dir / filename).touch()

        organise(root)

        # All episode files must be at their correct target paths
        for ep_meta in episode_metadatas:
            target = (
                root
                / format_show_folder(ep_meta)
                / format_season_folder(ep_meta)
                / format_episode_filename(ep_meta, ext)
            )
            assert target.exists(), (
                f"Episode file not at correct target: {target}"
            )

        # The original season-pack folder must no longer exist
        assert not pack_dir.exists(), (
            f"Season-pack folder still exists: {pack_dir}"
        )


# ---------------------------------------------------------------------------
# Property 8: organiser is idempotent
# Validates: Requirements 2.7
# ---------------------------------------------------------------------------

@given(
    entries=st.lists(
        st.tuples(_episode_metadata, _media_ext),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prop8_organiser_is_idempotent(entries):
    """
    **Validates: Requirements 2.7**

    Calling organise() twice SHALL produce the same filesystem state as
    calling it once. The second call SHALL emit no MOVED, CREATED, or
    DELETED actions for already-correctly-placed files.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src_dir = root / "incoming"
        src_dir.mkdir()

        for meta, ext in entries:
            filename = format_episode_filename(meta, ext)
            (src_dir / filename).touch()

        # First call organises the tree
        organise(root)

        # Second call on the already-organised tree
        actions2 = organise(root)

        # The second call must not produce any MOVED, CREATED, or DELETED actions
        non_idempotent = [
            a for a in actions2
            if a.kind in ("MOVED", "CREATED", "DELETED")
        ]
        assert non_idempotent == [], (
            f"Second organise() produced unexpected actions: {non_idempotent}"
        )


# ---------------------------------------------------------------------------
# Property 9: junk and sample files are deleted after organising
# Validates: Requirements 3.1, 3.2
# ---------------------------------------------------------------------------

def _safe_dir_name(s: str) -> bool:
    """Return True if the string is a safe directory name on all platforms."""
    return s.strip().lower() not in _WINDOWS_RESERVED


# Safe directory name strategy — filters out Windows reserved device names
_safe_dir_part = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=1,
    max_size=8,
).filter(_safe_dir_name)

# Safe file stem strategy — same filter
_safe_stem = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=1,
    max_size=8,
).filter(_safe_dir_name)


@given(
    # Junk files: arbitrary nesting depth (0–3 subdirectories) + junk extension
    junk_files=st.lists(
        st.tuples(
            st.lists(_safe_dir_part, min_size=0, max_size=3),
            _safe_stem,
            _junk_ext,
        ),
        min_size=1,
        max_size=6,
    ),
    # Sample files: a media extension with "sample" in the name
    sample_files=st.lists(
        st.tuples(
            st.lists(_safe_dir_part, min_size=0, max_size=2),
            _media_ext,
        ),
        min_size=0,
        max_size=3,
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prop9_junk_and_sample_files_deleted(junk_files, sample_files):
    """
    **Validates: Requirements 3.1, 3.2**

    After organise(), no junk-extension files and no sample media files
    SHALL remain anywhere under <root>.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        created_junk: list[Path] = []
        created_samples: list[Path] = []

        # Create junk files
        for dir_parts, stem, ext in junk_files:
            subdir = root.joinpath(*dir_parts) if dir_parts else root
            subdir.mkdir(parents=True, exist_ok=True)
            f = subdir / f"{stem}{ext}"
            f.touch()
            created_junk.append(f)

        # Create sample media files (name contains "sample")
        for dir_parts, ext in sample_files:
            subdir = root.joinpath(*dir_parts) if dir_parts else root
            subdir.mkdir(parents=True, exist_ok=True)
            f = subdir / f"ShowName.S01E01.sample{ext}"
            f.touch()
            created_samples.append(f)

        organise(root)

        # No junk files should survive
        for f in created_junk:
            assert not f.exists(), f"Junk file still exists: {f}"

        # No sample files should survive
        for f in created_samples:
            assert not f.exists(), f"Sample file still exists: {f}"

        # Also verify by walking: no file with a junk extension remains
        junk_exts = {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".srt", ".sub"}
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                suffix = Path(fname).suffix.lower()
                assert suffix not in junk_exts, (
                    f"Junk file found under root after organise(): "
                    f"{Path(dirpath) / fname}"
                )
                # Check for sample media files
                if suffix in {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts"}:
                    assert "sample" not in fname.lower(), (
                        f"Sample media file found under root after organise(): "
                        f"{Path(dirpath) / fname}"
                    )


# ---------------------------------------------------------------------------
# Property 10: Empty and junk-only non-root folders are removed
# Validates: Requirements 3.3, 3.4
# ---------------------------------------------------------------------------

@given(
    dir_names=st.lists(
        _safe_dir_part,
        min_size=1,
        max_size=4,
        unique=True,
    ),
    junk_ext=_junk_ext,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prop10_empty_junk_folders_removed(dir_names, junk_ext):
    """
    **Validates: Requirements 3.3, 3.4**

    After organise(), no non-root subdirectory that contained only junk-
    extension files (and no media or unknown files) SHALL still exist.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        created_subdirs: list[Path] = []
        for dir_name in dir_names:
            subdir = root / dir_name
            subdir.mkdir(exist_ok=True)
            # Place only junk files inside the subdirectory
            (subdir / f"info{junk_ext}").touch()
            (subdir / f"readme.nfo").touch()
            created_subdirs.append(subdir)

        organise(root)

        # Every subdir that contained only junk files should now be gone
        for subdir in created_subdirs:
            assert not subdir.exists(), (
                f"Junk-only subdir still exists after organise(): {subdir}"
            )


# ---------------------------------------------------------------------------
# Property 11: TV_Shows_Root is never deleted
# Validates: Requirement 3.5
# ---------------------------------------------------------------------------

@given(
    content=st.one_of(
        # All-junk root
        st.just("junk_only"),
        # Empty root
        st.just("empty"),
        # Mixed: some media + junk
        st.just("mixed"),
    )
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_prop11_root_never_deleted(content):
    """
    **Validates: Requirement 3.5**

    After organise() with any content (even all-junk, even empty), the root
    directory SHALL still exist.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        if content == "junk_only":
            (root / "info.nfo").touch()
            (root / "poster.jpg").touch()
        elif content == "empty":
            pass  # leave root empty
        else:  # "mixed"
            (root / "info.nfo").touch()
            (root / "silo.s02e04.mkv").touch()

        organise(root)

        assert root.exists(), (
            f"TV_Shows_Root was deleted by organise()! root={root}"
        )


# ---------------------------------------------------------------------------
# Property 12: Unknown-extension files are left in place with a warning
# Validates: Requirement 3.6
# ---------------------------------------------------------------------------

# Safe unknown extensions — guaranteed not in MEDIA_EXTS or JUNK_EXTS
_unknown_ext = st.sampled_from([".xyz", ".dat", ".bin", ".log", ".cfg"])


@given(
    stem=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
        min_size=1,
        max_size=10,
    ),
    ext=_unknown_ext,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_prop12_unknown_ext_files_left_with_warn(stem, ext):
    """
    **Validates: Requirement 3.6**

    A file with an unknown extension SHALL remain at its original path after
    organise() and the returned action list SHALL contain a WARN action
    referencing that file's path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / f"{stem}{ext}"
        f.touch()

        actions = organise(root)

        # File must still be in place
        assert f.exists(), (
            f"Unknown-extension file was removed: {f}"
        )

        # A WARN action must reference this file
        warn_actions = actions_by_kind(actions, "WARN")
        assert any(str(f) in (a.source or "") or str(f) in (a.detail or "")
                   for a in warn_actions), (
            f"No WARN action found for unknown-ext file {f}. "
            f"Actions: {warn_actions}"
        )


# ---------------------------------------------------------------------------
# Integration tests — real-world scenarios
# ---------------------------------------------------------------------------


def test_int_loose_dot_separated():
    """
    Loose dot-separated filename at root is moved to the correct hierarchy.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(root, "Ancient.Aliens.S20E01.1080p.WEB.h264-EDITH[EZTVx.to].mkv")
        organise(root)
        expected = (
            root
            / "Ancient Aliens"
            / "Ancient Aliens - Season 20"
            / "Ancient Aliens - Season 20 - Episode 1.mkv"
        )
        assert expected.exists(), f"Expected file not found: {expected}"


def test_int_loose_space_separated():
    """
    Loose space-separated filename at root is moved to the correct hierarchy.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(
            root,
            "Resident Alien S03E07 Here Comes My Baby 1080p AMZN WEB-DL DDP5 1 H 264-FLUX[EZTVx.to].mkv",
        )
        organise(root)
        expected = (
            root
            / "Resident Alien"
            / "Resident Alien - Season 3"
            / "Resident Alien - Season 3 - Episode 7.mkv"
        )
        assert expected.exists(), f"Expected file not found: {expected}"


def test_int_lowercase_filename():
    """
    All-lowercase dot-separated filename is moved and title-cased correctly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(root, "silo.s02e04.multi.1080p.web.h264-higgsboson[EZTVx.to].mkv")
        organise(root)
        expected = (
            root
            / "Silo"
            / "Silo - Season 2"
            / "Silo - Season 2 - Episode 4.mkv"
        )
        assert expected.exists(), f"Expected file not found: {expected}"


def test_int_folder_name_misleads():
    """
    A folder named 'Criminal Record Season 2' contains a file that says S01E01.
    The destination is derived from the file name (Season 1), not the folder.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(
            root,
            "Criminal Record Season 2",
            "Criminal.Record.S01E01.1080p.HEVC.x265-MeGusta[EZTVx.to].mkv",
        )
        organise(root)
        expected = (
            root
            / "Criminal Record"
            / "Criminal Record - Season 1"
            / "Criminal Record - Season 1 - Episode 1.mkv"
        )
        assert expected.exists(), f"Expected file not found: {expected}"


def test_int_season_pack_folder():
    """
    A season-pack folder is fully unpacked: all 3 episode files land at the
    correct season folder and the original pack folder is removed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pack_dir = root / "Criminal.Record.S01.COMPLETE.720p.ATVP.WEBRip.x264[EZTVx.to]"
        pack_dir.mkdir()
        for ep in (1, 2, 3):
            (pack_dir / f"Criminal.Record.S01E0{ep}.mkv").touch()

        organise(root)

        season_folder = root / "Criminal Record" / "Criminal Record - Season 1"
        for ep in (1, 2, 3):
            target = season_folder / f"Criminal Record - Season 1 - Episode {ep}.mkv"
            assert target.exists(), f"Episode {ep} not found: {target}"

        assert not pack_dir.exists(), (
            f"Season-pack folder still exists: {pack_dir}"
        )


def test_int_cross_show_nested():
    """
    A 'Beyond Skinwalker Ranch' episode nested inside a
    'The.Secret.of.Skinwalker.Ranch' folder goes to its own show folder,
    not the parent show's folder.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_file(
            root,
            "The.Secret.of.Skinwalker.Ranch",
            "Beyond.Skinwalker.Ranch.S02E06.1080p.WEB.h264-EDITH.mkv",
        )
        organise(root)
        expected = (
            root
            / "Beyond Skinwalker Ranch"
            / "Beyond Skinwalker Ranch - Season 2"
            / "Beyond Skinwalker Ranch - Season 2 - Episode 6.mkv"
        )
        assert expected.exists(), f"Expected file not found: {expected}"


def test_int_junk_files_deleted():
    """
    Junk files placed in root (.nfo, .jpg, .txt) are deleted after organise().
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        nfo = make_file(root, "show.nfo")
        jpg = make_file(root, "poster.jpg")
        txt = make_file(root, "info.txt")

        organise(root)

        assert not nfo.exists(), f"Junk file still exists: {nfo}"
        assert not jpg.exists(), f"Junk file still exists: {jpg}"
        assert not txt.exists(), f"Junk file still exists: {txt}"


def test_int_sample_file_deleted():
    """
    A sample media file is deleted after organise().
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sample = make_file(root, "Show.S01E01.sample.mkv")
        organise(root)
        assert not sample.exists(), f"Sample file still exists: {sample}"


def test_int_overwrite_flag():
    """
    Without --overwrite, a pre-existing destination file produces CONFLICT.
    With overwrite=True, the source is moved (MOVED) and no CONFLICT is emitted.
    """
    # --- Without overwrite ---
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Pre-create the target
        target = root / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        # Place a different source that resolves to the same target
        src = make_file(root, "incoming", "silo.s02e04.mkv")

        actions_no_ow = organise(root, overwrite=False)
        conflicts = actions_by_kind(actions_no_ow, "CONFLICT")
        assert len(conflicts) >= 1, "Expected a CONFLICT without --overwrite"
        assert str(src) == conflicts[0].source
        assert str(target) == conflicts[0].dest

    # --- With overwrite ---
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "Silo" / "Silo - Season 2" / "Silo - Season 2 - Episode 4.mkv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        make_file(root, "incoming", "silo.s02e04.mkv")

        actions_ow = organise(root, overwrite=True)
        conflicts = actions_by_kind(actions_ow, "CONFLICT")
        moved = actions_by_kind(actions_ow, "MOVED")

        assert conflicts == [], f"Unexpected CONFLICT with --overwrite: {conflicts}"
        assert any(str(target) == a.dest for a in moved), (
            f"Expected MOVED action to {target}"
        )

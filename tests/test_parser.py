# Feature: tv-shows-organiser, Property 1: Parser round-trip (SxxEyy, dot and space separators)

import sys
import os

# Ensure the workspace root is on sys.path so organise.py can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hypothesis import given, settings
from hypothesis import strategies as st

from organise import parse, format_episode_filename, ShowMetadata, QUALITY_TOKENS

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Quality tokens as a lowercase set for filtering
_QUALITY_TOKENS_LOWER = frozenset(t.lower() for t in QUALITY_TOKENS)

# Strategy for valid show name words (no digits, no quality-token words)
# Restricted to ASCII letters to avoid Unicode normalization edge cases
# (e.g., µ vs μ, combining characters) that are not relevant to the
# structural parsing properties being tested.
# Also filters out any word that matches a quality token (case-insensitively),
# since quality tokens in the pre-season position are intentionally stripped by
# the parser (Req 1.7) and would cause round-trip mismatches.
show_name_words = st.lists(
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll"), max_codepoint=0x7F),
        min_size=1,
    ).filter(lambda w: w.lower() not in _QUALITY_TOKENS_LOWER),
    min_size=1, max_size=5
)

# Strategy for ShowMetadata with episode
episode_metadata = st.builds(
    ShowMetadata,
    show_name_raw=show_name_words.map(lambda ws: " ".join(ws)),
    season=st.integers(min_value=1, max_value=30),
    episode=st.integers(min_value=1, max_value=30)
)

# ---------------------------------------------------------------------------
# Property 1: Parser round-trip (SxxEyy, dot and space separators)
# Validates: Requirements 1.1, 1.3, 1.4, 1.12
# ---------------------------------------------------------------------------

@given(meta=episode_metadata)
@settings(max_examples=200)
def test_parser_round_trip_episode(meta):
    """
    **Validates: Requirements 1.1, 1.3, 1.4, 1.12**

    For any ShowMetadata with a non-None episode, formatting it into an episode
    filename (using format_episode_filename) then parsing that filename with parse
    SHALL yield a result with identical season, identical episode, and show_name_raw
    tokens that are equal when compared case-insensitively after splitting on
    whitespace.
    """
    filename = format_episode_filename(meta, ".mkv")
    result = parse(filename)
    assert result is not None, (
        f"parse() returned None for formatted filename: {filename!r} "
        f"(generated from meta={meta!r})"
    )
    assert result.season == meta.season, (
        f"Season mismatch: expected {meta.season}, got {result.season} "
        f"for filename {filename!r}"
    )
    assert result.episode == meta.episode, (
        f"Episode mismatch: expected {meta.episode}, got {result.episode} "
        f"for filename {filename!r}"
    )
    # Compare the show names case-insensitively — with ASCII-only input the
    # simple .lower() comparison is unambiguous.
    assert result.show_name_raw.lower().split() == meta.show_name_raw.lower().split(), (
        f"Show name mismatch: expected tokens {meta.show_name_raw.lower().split()!r}, "
        f"got {result.show_name_raw.lower().split()!r} "
        f"for filename {filename!r}"
    )

# ---------------------------------------------------------------------------
# Property 2: Parser round-trip (season-pack, Sxx only)
# Validates: Requirements 1.2, 1.12
# ---------------------------------------------------------------------------

# Strategy for ShowMetadata without episode (season pack)
season_metadata = st.builds(
    ShowMetadata,
    show_name_raw=show_name_words.map(lambda ws: " ".join(ws)),
    season=st.integers(min_value=1, max_value=30),
    episode=st.just(None)
)


@given(
    show_words=show_name_words,
    season=st.integers(min_value=1, max_value=30)
)
@settings(max_examples=200)
def test_parser_round_trip_season_pack(show_words, season):
    """
    **Validates: Requirements 1.2, 1.12**

    For any ShowMetadata with episode=None, constructing a dot-separated
    season-pack style folder name (with an Sxx token) and parsing it with parse
    SHALL yield a result with identical season and episode=None, and
    show_name_raw tokens equal case-insensitively.
    """
    # Construct a dot-separated season-pack style folder name with Sxx token
    # e.g. "Criminal.Record.S01.COMPLETE.720p"
    show_part = ".".join(show_words)
    folder_name = f"{show_part}.S{season:02d}.COMPLETE.720p"
    result = parse(folder_name)
    assert result is not None, (
        f"parse() returned None for season-pack folder name: {folder_name!r} "
        f"(show_words={show_words!r}, season={season!r})"
    )
    assert result.season == season, (
        f"Season mismatch: expected {season}, got {result.season} "
        f"for folder name {folder_name!r}"
    )
    assert result.episode is None, (
        f"Episode should be None for season-pack, got {result.episode} "
        f"for folder name {folder_name!r}"
    )
    assert result.show_name_raw.lower().split() == [w.lower() for w in show_words], (
        f"Show name mismatch: expected tokens {[w.lower() for w in show_words]!r}, "
        f"got {result.show_name_raw.lower().split()!r} "
        f"for folder name {folder_name!r}"
    )

# ---------------------------------------------------------------------------
# Feature: tv-shows-organiser, Property 3: Quality and release-group tokens stripped
# Validates: Requirements 1.7, 1.8
# ---------------------------------------------------------------------------


@given(
    show_words=show_name_words,
    season=st.integers(min_value=1, max_value=30),
    episode=st.integers(min_value=1, max_value=30),
    quality_subset=st.lists(st.sampled_from(sorted(QUALITY_TOKENS)), min_size=1, max_size=3)
)
@settings(max_examples=200)
def test_quality_tokens_stripped(show_words, season, episode, quality_subset):
    """
    **Validates: Requirements 1.7, 1.8**

    For any valid raw show name (a non-empty list of words), arbitrary subset of
    quality tokens, constructing a dot-separated filename containing those extra
    tokens and then parsing it SHALL yield show_name_raw that contains none of the
    quality or release-group tokens.
    """
    # Build dot-separated filename: ShowName.SxxEyy.Quality1.Quality2.mkv
    show_part = ".".join(show_words)
    quality_part = ".".join(quality_subset)
    filename = f"{show_part}.S{season:02d}E{episode:02d}.{quality_part}.mkv"
    result = parse(filename)
    assert result is not None, (
        f"parse() returned None for filename: {filename!r}"
    )
    # The show name should not contain any quality tokens
    result_words_lower = set(result.show_name_raw.lower().split())
    quality_tokens_lower = {t.lower() for t in QUALITY_TOKENS}
    assert result_words_lower.isdisjoint(quality_tokens_lower), \
        f"Quality token found in show name: {result.show_name_raw!r} (filename={filename!r})"


@given(
    show_words=show_name_words,
    season=st.integers(min_value=1, max_value=30),
    episode=st.integers(min_value=1, max_value=30),
    release_group=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1, max_size=10
    )
)
@settings(max_examples=200)
def test_bracket_release_group_stripped(show_words, season, episode, release_group):
    """
    **Validates: Requirements 1.7, 1.8**

    For any valid raw show name and an arbitrary release-group suffix in [bracket]
    form, constructing a dot-separated filename with that release group appended
    and then parsing it SHALL yield show_name_raw that does not contain the
    release-group token.
    """
    show_part = ".".join(show_words)
    filename = f"{show_part}.S{season:02d}E{episode:02d}.1080p.WEB[{release_group}].mkv"
    result = parse(filename)
    assert result is not None, (
        f"parse() returned None for filename: {filename!r}"
    )
    # The bracketed form [release_group] must not appear in show name
    assert f"[{release_group}]" not in result.show_name_raw, (
        f"Bracketed release group [{release_group}] found in show name: "
        f"{result.show_name_raw!r} (filename={filename!r})"
    )
    # The show name must equal only the words from show_words (case-insensitive)
    # — i.e. the parsed show name tokens must match the input show words exactly,
    # confirming that nothing from the post-SxxEyy portion leaked into it.
    assert result.show_name_raw.lower().split() == [w.lower() for w in show_words], (
        f"Parsed show name tokens {result.show_name_raw.lower().split()!r} do not match "
        f"expected show words {[w.lower() for w in show_words]!r} "
        f"(filename={filename!r})"
    )

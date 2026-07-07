# Feature: tv-shows-organiser, Property 13: Title case rules are correctly applied
# Validates: Requirements 7.1, 7.2, 7.3

from organise import title_case, _LOWERCASE_WORDS
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate single words made only of ASCII letters (to keep test cases simple
# and deterministic with respect to case transforms).
_word = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll"), max_codepoint=0x7F),
    min_size=1,
    max_size=12,
)

# A word that is in the lowercase-exception list
_exception_word = st.sampled_from(sorted(_LOWERCASE_WORDS))

# A word that is NOT in the lowercase-exception list (and not empty)
_regular_word = _word.filter(lambda w: w.lower() not in _LOWERCASE_WORDS)

# A word drawn from either pool
_any_word = st.one_of(_regular_word, _exception_word)


def _make_sentence(words):
    """Join a list of words into a single string."""
    return " ".join(words)


# ---------------------------------------------------------------------------
# Property 13: Title case rules are correctly applied
# Validates: Requirements 7.1, 7.2, 7.3
# ---------------------------------------------------------------------------

@given(
    words=st.lists(_any_word, min_size=1, max_size=10)
)
@settings(max_examples=500)
def test_title_case_correctness_rules(words):
    """
    **Validates: Requirements 7.1, 7.2, 7.3**

    For any list of words:
    - title_case capitalises the first letter of every word not in the
      lowercase-exception list (Req 7.1).
    - Words in the lowercase-exception list are rendered lowercase when they
      are NOT the first or last word (Req 7.2).
    - The first word and last word are ALWAYS capitalised regardless of word
      class (Req 7.3).
    """
    s = _make_sentence(words)
    result = title_case(s)
    result_words = result.split()

    # Guard: title_case must return a string with the same word count
    assert len(result_words) == len(words), (
        f"Word count changed: input={words!r}, result={result!r}"
    )

    last_idx = len(words) - 1

    for i, (original_word, result_word) in enumerate(zip(words, result_words)):
        lower = original_word.lower()

        if i == 0 or i == last_idx:
            # Req 7.3: first and last word must always be capitalised
            assert result_word == lower.capitalize(), (
                f"Word at position {i} (first/last) should be capitalised. "
                f"original={original_word!r}, got={result_word!r}, "
                f"full input={s!r}, full result={result!r}"
            )
        elif lower in _LOWERCASE_WORDS:
            # Req 7.2: exception-list words in non-first, non-last position → lowercase
            assert result_word == lower, (
                f"Exception-list word at position {i} should be lowercase. "
                f"original={original_word!r}, got={result_word!r}, "
                f"full input={s!r}, full result={result!r}"
            )
        else:
            # Req 7.1: regular words must be capitalised
            assert result_word == lower.capitalize(), (
                f"Regular word at position {i} should be capitalised. "
                f"original={original_word!r}, got={result_word!r}, "
                f"full input={s!r}, full result={result!r}"
            )


@given(
    first=_exception_word,
    last=_exception_word,
    middle=st.lists(_any_word, min_size=0, max_size=8),
)
@settings(max_examples=200)
def test_first_and_last_always_capitalised_even_if_exception_words(first, last, middle):
    """
    **Validates: Requirements 7.3**

    Even when the first and last words are in the lowercase-exception list,
    they must still be capitalised.
    """
    words = [first] + middle + [last]
    s = _make_sentence(words)
    result = title_case(s)
    result_words = result.split()

    # First word capitalised
    assert result_words[0] == first.lower().capitalize(), (
        f"First word should be capitalised even though it is an exception word. "
        f"first={first!r}, result[0]={result_words[0]!r}, full result={result!r}"
    )
    # Last word capitalised (only relevant when there are 2+ words)
    if len(result_words) > 1:
        assert result_words[-1] == last.lower().capitalize(), (
            f"Last word should be capitalised even though it is an exception word. "
            f"last={last!r}, result[-1]={result_words[-1]!r}, full result={result!r}"
        )


@given(
    prefix=st.lists(_regular_word, min_size=1, max_size=4),
    exception_middle=st.lists(_exception_word, min_size=1, max_size=4),
    suffix=st.lists(_regular_word, min_size=1, max_size=4),
)
@settings(max_examples=200)
def test_exception_words_in_middle_are_lowercase(prefix, exception_middle, suffix):
    """
    **Validates: Requirements 7.2**

    Exception-list words that appear strictly between the first and last words
    must be rendered in lowercase.
    """
    words = prefix + exception_middle + suffix
    s = _make_sentence(words)
    result = title_case(s)
    result_words = result.split()

    last_idx = len(words) - 1
    # The exception words land at positions len(prefix) .. len(prefix)+len(exception_middle)-1
    for i in range(len(prefix), len(prefix) + len(exception_middle)):
        if i == 0 or i == last_idx:
            continue  # first/last override applies
        assert result_words[i] == exception_middle[i - len(prefix)].lower(), (
            f"Exception word at position {i} should be lowercase. "
            f"got={result_words[i]!r}, full input={s!r}, full result={result!r}"
        )


# ---------------------------------------------------------------------------
# Task 3.6: Unit tests for Pretty_Printer with concrete examples
# Validates: Requirements 1.9–1.11, 7.1–7.5
# ---------------------------------------------------------------------------

import pytest
from organise import (
    ShowMetadata,
    format_show_folder,
    format_season_folder,
    format_season_only_folder,
    format_episode_filename,
    title_case,
)

# ---------------------------------------------------------------------------
# 3.6.1–3: format_show_folder, format_season_folder, format_episode_filename
# ---------------------------------------------------------------------------

def test_format_show_folder_ancient_aliens():
    """format_show_folder returns the title-cased show name only."""
    meta = ShowMetadata(show_name_raw="Ancient Aliens", season=20, episode=1)
    assert format_show_folder(meta) == "Ancient Aliens"


def test_format_season_folder_ancient_aliens():
    """format_season_folder returns '<Show Name> - Season <N>'."""
    meta = ShowMetadata(show_name_raw="Ancient Aliens", season=20, episode=1)
    assert format_season_folder(meta) == "Ancient Aliens - Season 20"


def test_format_episode_filename_ancient_aliens():
    """format_episode_filename returns '<Show Name> - Season <N> - Episode <M><ext>'."""
    meta = ShowMetadata(show_name_raw="Ancient Aliens", season=20, episode=1)
    assert format_episode_filename(meta, ".mkv") == "Ancient Aliens - Season 20 - Episode 1.mkv"


# ---------------------------------------------------------------------------
# 3.6.4: format_season_only_folder with episode=None
# ---------------------------------------------------------------------------

def test_format_season_only_folder_criminal_record():
    """format_season_only_folder returns '<Show Name> - Season <N>' when episode is None."""
    meta = ShowMetadata(show_name_raw="Criminal Record", season=1, episode=None)
    assert format_season_only_folder(meta) == "Criminal Record - Season 1"


# ---------------------------------------------------------------------------
# 3.6.5–8: title_case rules
# ---------------------------------------------------------------------------

def test_title_case_lowercase_exception_words_in_middle():
    """Lowercase-exception words in middle positions are rendered lowercase."""
    assert title_case("the secret of skinwalker ranch") == "The Secret of Skinwalker Ranch"


def test_title_case_always_capitalises_first_word():
    """The first word is always capitalised, even if it is an exception word."""
    assert title_case("a show") == "A Show"


def test_title_case_always_capitalises_last_word():
    """The last word is always capitalised, even if it is an exception word."""
    assert title_case("show of the") == "Show of The"


def test_title_case_idempotent_concrete():
    """Applying title_case to already-correct input produces identical output."""
    already_correct = "The Secret of Skinwalker Ranch"
    assert title_case(already_correct) == already_correct


# ---------------------------------------------------------------------------
# 3.6.9: Parametrised tests for all format functions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("show_name_raw, season, episode, expected", [
    ("Ancient Aliens", 20, 1, "Ancient Aliens"),
    ("Silo", 2, 4, "Silo"),
    ("Criminal Record", 1, None, "Criminal Record"),
    ("Resident Alien", 3, 7, "Resident Alien"),
    ("The Secret of Skinwalker Ranch", 1, 5, "The Secret of Skinwalker Ranch"),
])
def test_format_show_folder_parametrised(show_name_raw, season, episode, expected):
    """format_show_folder returns title-cased name across various shows."""
    meta = ShowMetadata(show_name_raw=show_name_raw, season=season, episode=episode)
    assert format_show_folder(meta) == expected


@pytest.mark.parametrize("show_name_raw, season, episode, expected", [
    ("Ancient Aliens", 20, 1, "Ancient Aliens - Season 20"),
    ("Silo", 2, 4, "Silo - Season 2"),
    ("Resident Alien", 3, 7, "Resident Alien - Season 3"),
    ("Criminal Record", 1, 1, "Criminal Record - Season 1"),
    ("The Secret of Skinwalker Ranch", 1, 5, "The Secret of Skinwalker Ranch - Season 1"),
])
def test_format_season_folder_parametrised(show_name_raw, season, episode, expected):
    """format_season_folder returns '<Show> - Season <N>' across various shows."""
    meta = ShowMetadata(show_name_raw=show_name_raw, season=season, episode=episode)
    assert format_season_folder(meta) == expected


@pytest.mark.parametrize("show_name_raw, season, expected", [
    ("Criminal Record", 1, "Criminal Record - Season 1"),
    ("Silo", 2, "Silo - Season 2"),
    ("Ancient Aliens", 20, "Ancient Aliens - Season 20"),
])
def test_format_season_only_folder_parametrised(show_name_raw, season, expected):
    """format_season_only_folder returns '<Show> - Season <N>' when episode is None."""
    meta = ShowMetadata(show_name_raw=show_name_raw, season=season, episode=None)
    assert format_season_only_folder(meta) == expected


@pytest.mark.parametrize("show_name_raw, season, episode, ext, expected", [
    ("Ancient Aliens", 20, 1, ".mkv", "Ancient Aliens - Season 20 - Episode 1.mkv"),
    ("Silo", 2, 4, ".mkv", "Silo - Season 2 - Episode 4.mkv"),
    ("Resident Alien", 3, 7, ".mp4", "Resident Alien - Season 3 - Episode 7.mp4"),
    ("Criminal Record", 1, 1, ".mkv", "Criminal Record - Season 1 - Episode 1.mkv"),
    # Extension is lowercased in output
    ("Silo", 2, 4, ".MKV", "Silo - Season 2 - Episode 4.mkv"),
    # No leading zeros on season or episode
    ("Ancient Aliens", 20, 1, ".mkv", "Ancient Aliens - Season 20 - Episode 1.mkv"),
])
def test_format_episode_filename_parametrised(show_name_raw, season, episode, ext, expected):
    """format_episode_filename returns correct full filename across various inputs."""
    meta = ShowMetadata(show_name_raw=show_name_raw, season=season, episode=episode)
    assert format_episode_filename(meta, ext) == expected


# ---------------------------------------------------------------------------
# Property 14: Title case formatter is idempotent
# Validates: Requirements 7.5
# ---------------------------------------------------------------------------

@given(s=st.text(min_size=1))
def test_title_case_idempotent(s):
    """
    For any show name string s, title_case(title_case(s)) == title_case(s).

    **Validates: Requirements 7.5**
    """
    assert title_case(title_case(s)) == title_case(s)

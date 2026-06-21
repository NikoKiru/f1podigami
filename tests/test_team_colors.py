"""Unit tests for the constructor colour map and on-colour ink helper."""

from build.team_colors import FALLBACK, TEAM_COLORS, team_color, text_on


def test_known_team_returns_its_colour():
    assert team_color("ferrari") == TEAM_COLORS["ferrari"]
    assert team_color("mercedes").startswith("#")


def test_unknown_or_empty_team_falls_back():
    assert team_color("nonsense_team") == FALLBACK
    assert team_color("") == FALLBACK


def test_every_colour_is_a_hex_triplet():
    for cid, hex_color in TEAM_COLORS.items():
        assert hex_color.startswith("#") and len(hex_color) == 7, cid
        int(hex_color[1:], 16)  # parses as hex


def test_text_on_picks_dark_ink_for_light_colours():
    # Haas light grey -> dark ink is the legible choice
    assert text_on("#B6BABD") == "#0b0d12"
    assert text_on("#FFFFFF") == "#0b0d12"


def test_text_on_picks_white_ink_for_dark_colours():
    # Ferrari red / McLaren orange are dark enough to need white text
    assert text_on("#ED1131") == "#ffffff"
    assert text_on("#000000") == "#ffffff"


def test_text_on_is_always_one_of_two_inks():
    for hex_color in TEAM_COLORS.values():
        assert text_on(hex_color) in ("#0b0d12", "#ffffff")

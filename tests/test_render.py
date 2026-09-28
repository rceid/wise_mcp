import pytest

from wise_mcp import render


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (42126.06, "42,126"),
        (7.3454, "7.35"),
        (-0.3, "-0.30"),
        (0.858, "0.86"),
        (0.003123, "0.00312"),  # tiny changes keep their significant digits
        (0, "0.00"),
        (None, "–"),
        (float("nan"), "–"),
    ],
)
def test_number(value, text):
    assert render.number(value) == text


def test_signed_marks_increases():
    assert (render.signed(1.2), render.signed(-0.3), render.signed(None)) == ("+1.20", "-0.30", "–")


def test_table():
    assert render.table(["A", "B"], [[1, "x"]]) == "| A | B |\n|---|---|\n| 1 | x |"


@pytest.mark.parametrize(
    ("better", "target", "phrase"),
    [("higher", None, "higher is better"), ("target", 0, "closer to 0.00 is better")],
)
def test_heading_states_the_direction(better, target, phrase):
    measure = {"name": "Gap", "code": "2_2", "unit": "Percent", "better": better, "target": target}
    assert render.heading(measure) == f"**Gap** (2_2, Percent; {phrase})"


def test_caveats_include_the_measure_note():
    assert render.caveats(["Years differ."], "A ratio.") == (
        "Caveats:\n- Years differ.\n- About this measure: A ratio."
    )
    assert render.caveats([]) == ""

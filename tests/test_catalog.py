from collections import Counter

import pytest

from wise_mcp.catalog import OECD_MEMBERS, load_measures, parse_measures


@pytest.fixture(scope="module")
def measures():
    return load_measures()


class TestShippedFile:
    def test_covers_every_measure_in_the_database(self, measures):
        # 68 current + 35 future as of 2026-09. The live tests check this against the real data.
        assert len(measures) == 103

    def test_headlines_match_the_how_s_life_dashboard(self, measures):
        # How's Life? 2024 Reader's Guide, Tables 3 and 4.
        current = Counter(m.headline for m in measures.values() if m.headline and not m.is_future)
        future = Counter(m.headline for m in measures.values() if m.headline and m.is_future)
        assert current == {
            "average": 11,
            "vertical_inequality": 1,
            "horizontal_inequality": 3,
            "deprivation": 9,
        }
        assert future == {"stock": 5, "flow": 1, "risk_factor": 4, "resilience_factor": 2}

    def test_deprivations_and_vertical_inequalities_are_lower_is_better(self, measures):
        # A share of people falling below a threshold, or a top-to-bottom ratio, is never good.
        suffixed = [m for m in measures.values() if m.code.endswith(("_DEP", "_VER"))]
        assert suffixed
        assert all(m.better == "lower" for m in suffixed)

    def test_gaps_and_balances_aim_for_a_target(self, measures):
        targets = {m.code: m.target for m in measures.values() if m.better == "target"}
        assert targets == {"2_2": 0, "4_3": 0, "14_5": 50, "12_11": 0}

    @pytest.mark.parametrize(
        ("code", "better"),
        [
            ("3_2", "higher"),  # housing affordability is income left after housing costs
            ("14_6", "higher"),  # "corruption" is a perceptions index where 100 is very clean
            ("11_2", "lower"),  # negative affect balance
            ("12_7", "higher"),  # Red List Index: 1 means no species under threat
        ],
    )
    def test_measures_whose_names_mislead(self, measures, code, better):
        assert measures[code].better == better

    def test_thresholds_are_converted_to_the_data_units(self, measures):
        assert measures["4_1"].threshold == pytest.approx(20 / 60, abs=1e-3)  # 20 min, in hours
        assert measures["12_8"].threshold == 0.5  # "0.5 thousand kg", the data are in thousands

    def test_only_carbon_footprint_needs_a_default_unit(self, measures):
        assert {m.code: m.unit for m in measures.values() if m.unit} == {"12_9": "T_CO2E_PS"}


class TestValidation:
    def test_unquoted_code_is_rejected(self):
        # YAML 1.1 reads 1_1 as the integer 11.
        with pytest.raises(ValueError, match="must be quoted"):
            parse_measures("1_1:\n  better: higher\n")

    @pytest.mark.parametrize(
        ("entry", "message"),
        [
            ("beter: higher", "unknown field"),
            ("better: up", "better must be higher, lower or target"),
            ("better: target", "target value goes with"),
            ("better: higher\n  target: 0", "target value goes with"),
            ("better: target\n  target: zero", "target must be a number"),
            ("better: higher\n  headline: stock", "headline must be one of"),
            ("better: higher\n  threshold: -1", "threshold must be a number of at least 0"),
            ("better: higher\n  comparable: sometimes", "comparable must be true or false"),
            ("better: higher\n  unit_label: 3", "unit_label must be text"),
            ("better: higher\n  pooled: yearly", "pooled must be true or false"),
        ],
    )
    def test_invalid_entries_name_the_measure(self, entry, message):
        with pytest.raises(ValueError, match=message) as exc_info:
            parse_measures(f'"1_1":\n  {entry}\n')
        assert str(exc_info.value).startswith("1_1:")

    def test_future_measures_use_capital_headline_types(self):
        parsed = parse_measures('"12_8":\n  better: lower\n  headline: risk_factor\n')
        assert parsed["12_8"].is_future
        with pytest.raises(ValueError, match="headline must be one of"):
            parse_measures('"12_8":\n  better: lower\n  headline: average\n')

    def test_malformed_code_is_rejected(self):
        with pytest.raises(ValueError, match="not a How's Life\\? measure code"):
            parse_measures('"life_satisfaction":\n  better: higher\n')


def test_the_survey_measures_published_per_period_are_marked_pooled(measures):
    # Checked against the data: 2008-10, 2011-13, ..., 2023-25 hold one value for every country.
    pooled = {code for code, m in measures.items() if m.pooled}
    assert pooled == {"7_1", "7_1_DEP", "10_2", "10_2_DEP", "11_2", "11_3", "14_3", "14_7"}


def test_oecd_has_38_members():
    # As of September 2026. Update OECD_MEMBERS when Bulgaria (or anyone else) joins.
    assert len(OECD_MEMBERS) == 38
    assert all(len(code) == 3 and code.isupper() for code in OECD_MEMBERS)


def test_the_wrong_emissions_unit_label_is_corrected():
    # The OECD labels greenhouse gas emissions in kg per person; the values are tonnes.
    labelled = {m.code: m.unit_label for m in load_measures().values() if m.unit_label}
    assert labelled == {"12_8": "Tonnes of CO2-equivalent per person"}

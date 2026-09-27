"""What each How's Life? measure means, from measures.yaml: which direction is better, whether
it's a headline indicator, and how big a change counts as meaningful.

The file is hand-edited, so loading validates every entry and fails with the measure code in the
message rather than letting a typo quietly change a ranking.
"""

import re
from dataclasses import dataclass, fields
from functools import cache
from importlib.resources import files
from typing import Literal

import yaml

Better = Literal["higher", "lower", "target"]

# Measures 1-11 are current well-being dimensions, 12-15 are the capitals for future well-being.
FIRST_FUTURE_DIMENSION = 12
CURRENT_HEADLINE_TYPES = {"average", "vertical_inequality", "horizontal_inequality", "deprivation"}
FUTURE_HEADLINE_TYPES = {"stock", "flow", "risk_factor", "resilience_factor"}

_CODE = re.compile(r"^\d{1,2}_\d{1,2}(_VER|_DEP)?$")

# The 38 OECD members as of September 2026. OECD averages cover members only, so partner and
# accession countries in the data (Brazil, South Africa, Argentina...) are shown but not averaged.
# Bulgaria may become the 39th member around the end of 2026.
OECD_MEMBERS = frozenset(
    {
        "AUS", "AUT", "BEL", "CAN", "CHE", "CHL", "COL", "CRI", "CZE", "DEU",
        "DNK", "ESP", "EST", "FIN", "FRA", "GBR", "GRC", "HUN", "IRL", "ISL",
        "ISR", "ITA", "JPN", "KOR", "LTU", "LUX", "LVA", "MEX", "NLD", "NOR",
        "NZL", "POL", "PRT", "SVK", "SVN", "SWE", "TUR", "USA",
    }
)  # fmt: skip


@dataclass(frozen=True)
class Measure:
    code: str
    better: Better
    target: float | None = None
    name: str | None = None
    headline: str | None = None
    threshold: float | None = None
    unit: str | None = None
    unit_label: str | None = None  # overrides a wrong OECD unit label
    comparable: bool = True
    note: str | None = None

    @property
    def dimension(self) -> int:
        return int(self.code.split("_")[0])

    @property
    def is_future(self) -> bool:
        return self.dimension >= FIRST_FUTURE_DIMENSION


@cache
def load_measures() -> dict[str, Measure]:
    """The measures shipped with the package, keyed by code (e.g. "11_1")."""
    return parse_measures(files("wise_mcp").joinpath("measures.yaml").read_text())


def parse_measures(text: str) -> dict[str, Measure]:
    raw = yaml.safe_load(text) or {}
    return {code: _parse_entry(code, entry) for code, entry in raw.items()}


def _parse_entry(code: object, entry: object) -> Measure:
    if not isinstance(code, str):
        raise ValueError(f'Measure code {code!r} must be quoted, e.g. "1_1", or YAML misreads it')
    if not _CODE.match(code):
        raise ValueError(f"{code}: not a How's Life? measure code like 1_1, 1_3_VER or 2_8_DEP")
    if not isinstance(entry, dict):
        raise ValueError(f"{code}: expected a mapping of fields")

    known = {f.name for f in fields(Measure)} - {"code"}
    unknown = set(entry) - known
    if unknown:
        raise ValueError(f"{code}: unknown field(s) {sorted(unknown)}, expected {sorted(known)}")

    measure = Measure(code=code, **entry)
    if measure.better not in ("higher", "lower", "target"):
        raise ValueError(f"{code}: better must be higher, lower or target, not {measure.better!r}")
    if (measure.better == "target") != (measure.target is not None):
        raise ValueError(f"{code}: a target value goes with, and only with, better: target")
    if measure.target is not None and not isinstance(measure.target, int | float):
        raise ValueError(f"{code}: target must be a number")

    allowed = FUTURE_HEADLINE_TYPES if measure.is_future else CURRENT_HEADLINE_TYPES
    if measure.headline is not None and measure.headline not in allowed:
        raise ValueError(f"{code}: headline must be one of {sorted(allowed)}")
    if measure.threshold is not None and (
        not isinstance(measure.threshold, int | float) or measure.threshold < 0
    ):
        raise ValueError(f"{code}: threshold must be a number of at least 0")
    if not isinstance(measure.comparable, bool):
        raise ValueError(f"{code}: comparable must be true or false")
    if measure.unit_label is not None and not isinstance(measure.unit_label, str):
        raise ValueError(f"{code}: unit_label must be text")
    return measure

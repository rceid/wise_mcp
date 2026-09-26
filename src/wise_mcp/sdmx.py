"""Minimal client for the OECD SDMX REST API.

It does one thing: download a whole dataflow as CSV and turn it into a tidy DataFrame plus a
code -> label lookup. Filtered queries aren't needed because the store keeps a full local copy.

The OECD allows roughly 60 data requests per hour per IP. This client never retries: a retry
spends more of that budget, and the store has a better fallback (serve the existing cache).
"""

import io
from dataclasses import dataclass

import httpx
import pandas as pd

from wise_mcp.config import SDMX_BASE_URL

# The dimensions of the How's Life? data structure (DSD_HSL), in key order, then the
# attributes attached to each observation.
DIMENSIONS = ["REF_AREA", "MEASURE", "UNIT_MEASURE", "AGE", "SEX", "EDUCATION_LEV", "DOMAIN"]
CODED_ATTRIBUTES = ["OBS_STATUS", "UNIT_MULT", "DECIMALS"]

# In the "csvfilewithlabels" format every coded column is immediately followed by a column
# holding its English label, e.g. REF_AREA ("FRA") then "Reference area" ("France").
LABELLED_COLUMNS = DIMENSIONS + CODED_ATTRIBUTES

# Values that mean "not applicable" rather than an actual base period.
_NO_BASE_PERIOD = {"", "_Z"}


class SdmxError(Exception):
    """The OECD API could not be reached or returned something unusable."""


class RateLimitError(SdmxError):
    """The OECD API refused the request because this IP made too many requests."""

    def __init__(self, retry_after: str | None):
        self.retry_after = retry_after
        wait = f" Retry after: {retry_after}." if retry_after else ""
        super().__init__(f"OECD API rate limit reached (about 60 requests/hour).{wait}")


class NoResultsError(SdmxError):
    """The query was valid but matched no data (the API answers these with HTTP 404)."""


@dataclass(frozen=True)
class DataflowDownload:
    structure_id: str  # e.g. "OECD.WISE.WDP:DSD_HSL@DF_HSL_CWB(1.1)", includes the version
    name: str  # e.g. "Current well-being"
    observations: pd.DataFrame  # one row per data point, codes only
    labels: dict[str, dict[str, str]]  # column -> code -> label, e.g. ["ref_area"]["FRA"]


class SdmxClient:
    def __init__(self, base_url: str = SDMX_BASE_URL, timeout: float = 120.0):
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": "wise-mcp/0.1"},
            follow_redirects=True,
        )

    def fetch_dataflow(self, agency_id: str, dataflow_id: str) -> DataflowDownload:
        return parse_labelled_csv(self.fetch_dataflow_csv(agency_id, dataflow_id))

    def fetch_dataflow_csv(self, agency_id: str, dataflow_id: str) -> str:
        """Download every observation in a dataflow as labelled CSV text.

        The path is /data/{agency},{dataflow},{version}/{key}. An empty version means the
        latest one, and the key "all" means no filtering on any dimension.
        """
        response = self._get(
            f"/data/{agency_id},{dataflow_id},/all",
            params={"dimensionAtObservation": "AllDimensions", "format": "csvfilewithlabels"},
        )
        return response.text

    def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        try:
            response = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise SdmxError(f"Could not reach the OECD API: {exc}") from exc

        if response.status_code == 429:
            raise RateLimitError(response.headers.get("Retry-After"))
        if response.status_code == 404:
            raise NoResultsError(f"No data found for {path}: {response.text[:200]}")
        if response.status_code == 403:
            raise SdmxError(
                "The OECD API refused the request (HTTP 403). It blocks some VPN and "
                "anonymised traffic, so try again without a VPN."
            )
        if response.is_error:
            raise SdmxError(f"OECD API returned HTTP {response.status_code}: {response.text[:200]}")
        return response

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SdmxClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def parse_labelled_csv(text: str) -> DataflowDownload:
    """Split a "csvfilewithlabels" response into typed observations and label lookups."""
    # Read everything as text first. keep_default_na=False stops pandas from turning codes
    # like "NA" (Namibia) into missing values; real types are applied column by column below.
    raw = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)

    required = [
        "STRUCTURE_ID",
        "STRUCTURE_NAME",
        *LABELLED_COLUMNS,
        "TIME_PERIOD",
        "OBS_VALUE",
        "BASE_PER",
    ]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise SdmxError(f"Unexpected CSV from the OECD API, missing columns: {missing}")
    if raw.empty:
        raise NoResultsError("The OECD API returned a CSV with no observations")

    header = list(raw.columns)
    labels = {}
    for column in LABELLED_COLUMNS:
        label_column = header[header.index(column) + 1]
        pairs = raw[[column, label_column]].drop_duplicates()
        labels[column.lower()] = dict(zip(pairs[column], pairs[label_column], strict=True))

    observations = pd.DataFrame({column.lower(): raw[column] for column in DIMENSIONS})
    observations["time_period"] = raw["TIME_PERIOD"].astype("int64")  # annual data: "2021"
    observations["obs_value"] = pd.to_numeric(raw["OBS_VALUE"]).astype("float64")
    observations["obs_status"] = raw["OBS_STATUS"]
    observations["unit_mult"] = raw["UNIT_MULT"].astype("int64")  # value is x 10^unit_mult
    observations["decimals"] = raw["DECIMALS"].astype("int64")
    observations["base_per"] = raw["BASE_PER"].where(~raw["BASE_PER"].isin(_NO_BASE_PERIOD))

    return DataflowDownload(
        structure_id=raw["STRUCTURE_ID"].iloc[0],
        name=raw["STRUCTURE_NAME"].iloc[0],
        observations=observations,
        labels=labels,
    )

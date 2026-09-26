import httpx
import pytest
import respx

from wise_mcp.sdmx import (
    NoResultsError,
    RateLimitError,
    SdmxClient,
    SdmxError,
    parse_labelled_csv,
)

DATA_URL = "https://sdmx.oecd.org/public/rest/data/OECD.WISE.WDP,DSD_HSL@DF_HSL_CWB,/all"


def fetch_current() -> None:
    with SdmxClient() as client:
        client.fetch_dataflow("OECD.WISE.WDP", "DSD_HSL@DF_HSL_CWB")


class TestParseLabelledCsv:
    def test_observations_have_lowercase_columns_and_real_types(self, current_csv):
        obs = parse_labelled_csv(current_csv).observations

        assert list(obs.columns) == [
            "ref_area",
            "measure",
            "unit_measure",
            "age",
            "sex",
            "education_lev",
            "domain",
            "time_period",
            "obs_value",
            "obs_status",
            "unit_mult",
            "decimals",
            "base_per",
        ]
        assert obs["time_period"].dtype == "int64"
        assert obs["obs_value"].dtype == "float64"
        assert len(obs) == 288

    def test_known_value(self, current_csv):
        obs = parse_labelled_csv(current_csv).observations
        france_2024 = obs.query(
            "ref_area == 'FRA' and measure == '11_1' and time_period == 2024"
            " and sex == '_T' and age == '_T' and education_lev == '_T'"
        )
        assert france_2024["obs_value"].item() == pytest.approx(7.1386, abs=1e-4)

    def test_labels_map_codes_to_english_names(self, current_csv):
        labels = parse_labelled_csv(current_csv).labels

        assert labels["ref_area"]["FRA"] == "France"
        assert labels["measure"]["11_1"] == "Life satisfaction"
        assert labels["sex"]["F"] == "Female"
        assert labels["obs_status"]["B"] == "Time series break"

    def test_labels_only_cover_codes_present_in_the_data(self, current_csv):
        # The OECD's full area codelist has 3,763 entries. Only the ones with data matter.
        labels = parse_labelled_csv(current_csv).labels
        assert set(labels["ref_area"]) == {"DEU", "FRA", "MEX"}

    def test_structure_id_and_name(self, current_csv):
        download = parse_labelled_csv(current_csv)
        assert download.structure_id.startswith("OECD.WISE.WDP:DSD_HSL@DF_HSL_CWB(")
        assert download.name == "Current well-being"

    def test_not_applicable_base_period_becomes_missing(self, current_csv, future_csv):
        # Current well-being marks "no base period" as "_Z", future well-being leaves it blank.
        assert parse_labelled_csv(current_csv).observations["base_per"].isna().all()
        future = parse_labelled_csv(future_csv).observations["base_per"]
        assert set(future.dropna()) == {"2020"}
        assert future.isna().any()

    def test_country_code_na_is_kept(self, current_csv):
        # Namibia's code is "NA", which pandas reads as a missing value unless told not to.
        header, first_row = current_csv.splitlines()[:2]
        namibia_row = first_row.replace(",DEU,Germany,", ",NA,Namibia,")
        obs = parse_labelled_csv(f"{header}\n{namibia_row}\n").observations
        assert obs["ref_area"].tolist() == ["NA"]

    def test_unexpected_columns_raise(self):
        with pytest.raises(SdmxError, match="missing columns"):
            parse_labelled_csv("STRUCTURE_ID,OBS_VALUE\nX,1\n")

    def test_header_without_rows_raises_no_results(self, current_csv):
        header = current_csv.splitlines()[0]
        with pytest.raises(NoResultsError):
            parse_labelled_csv(header + "\n")


class TestSdmxClient:
    @respx.mock
    def test_downloads_whole_dataflow_as_labelled_csv(self, current_csv):
        route = respx.get(DATA_URL).respond(200, text=current_csv)

        with SdmxClient() as client:
            download = client.fetch_dataflow("OECD.WISE.WDP", "DSD_HSL@DF_HSL_CWB")

        assert route.call_count == 1
        params = route.calls.last.request.url.params
        assert params["format"] == "csvfilewithlabels"
        assert params["dimensionAtObservation"] == "AllDimensions"
        assert len(download.observations) == 288

    @respx.mock
    def test_rate_limit_raises_without_retrying(self):
        route = respx.get(DATA_URL).respond(429, headers={"Retry-After": "3600"})

        with pytest.raises(RateLimitError) as exc_info:
            fetch_current()

        assert exc_info.value.retry_after == "3600"
        assert route.call_count == 1  # a retry would only spend more of the hourly budget

    @pytest.mark.parametrize(
        ("status", "error", "message"),
        [
            (404, NoResultsError, "No data found"),
            (403, SdmxError, "VPN"),
            (500, SdmxError, "HTTP 500"),
        ],
    )
    @respx.mock
    def test_http_errors(self, status, error, message):
        respx.get(DATA_URL).respond(status, text="NoResultsFound")
        with pytest.raises(error, match=message):
            fetch_current()

    @respx.mock
    def test_network_failure(self):
        respx.get(DATA_URL).mock(side_effect=httpx.ConnectError("no route to host"))
        with pytest.raises(SdmxError, match="Could not reach the OECD API"):
            fetch_current()

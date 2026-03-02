import pytest
from unittest.mock import patch, MagicMock

from app.okavango_app import OkavangoData, DataSource


def test_download(tmp_path):
    """
    Test that download_project_data:
    - calls requests.get
    - creates the file
    - writes correct content
    """

    source = DataSource(
        url="https://example.com/test.csv",
        filename="test.csv"
    )

    fake_response = MagicMock()
    fake_response.content = b"Code,Year,Value\nUSA,2023,10\n"
    fake_response.raise_for_status = MagicMock()

    with patch("app.okavango_app.requests.get", return_value=fake_response) as mock_get:

        OkavangoData(
            sources=[source],
            download_dir=str(tmp_path)
        )

        file_path = tmp_path / "test.csv"

        assert file_path.exists()

        assert mock_get.call_count == 1

        assert file_path.read_bytes() == fake_response.content


import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def test_merge(tmp_path):
    """
    Test that merge_geospatial_layers:
    - merges correctly on ISO code
    - keeps geometry
    - does not duplicate rows
    """

    geo_df = gpd.GeoDataFrame(
        {
            "ADM0_A3": ["USA", "FRA"],
            "geometry": [Point(0, 0), Point(1, 1)]
        },
        geometry="geometry",
        crs="EPSG:4326"
    )

    df = pd.DataFrame({
        "Code": ["USA", "FRA"],
        "TestMetric": [100, 200]
    })

    handler = OkavangoData(
        sources=[],
        download_dir=str(tmp_path)
    )

    handler.geo_dataframe = geo_df
    handler.dataframes = {"dummy.csv": df}

    handler.merge_geospatial_layers()
    merged = handler.merged_data

    assert isinstance(merged, gpd.GeoDataFrame)

    assert "geometry" in merged.columns
    assert merged.geometry.notna().all()

    assert merged.shape[0] == geo_df.shape[0]

    assert "TestMetric" in merged.columns

    assert merged.loc[merged["ADM0_A3"] == "USA", "TestMetric"].item() == 100
    assert merged.loc[merged["ADM0_A3"] == "FRA", "TestMetric"].item() == 200
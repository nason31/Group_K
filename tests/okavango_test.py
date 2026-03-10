"""
Unit Tests for Project Okavango Data Pipeline

This module contains pytest-based unit tests for the `OkavangoData` pipeline, focusing
on two core responsibilities:

1) Downloading project data (`download_project_data`) without making real network calls.
2) Merging cleaned metric tables into a geospatial layer (`merge_geospatial_layers`).

Reasoning
---------
These tests are designed to validate the most important behaviors of the pipeline while
keeping the test suite:
- **Fast** (no real downloads, small in-memory DataFrames)
- **Deterministic** (controlled inputs/outputs)
- **Isolated** (mock external systems like HTTP requests)

Dependencies
------------
pytest
unittest.mock (patch, MagicMock)
pandas, geopandas
shapely

Examples
--------
Run the full test suite from the project root:

>>> pytest -q
"""

import pytest
from unittest.mock import patch, MagicMock

from app.data_handler import OkavangoData, DataSource


def test_download(tmp_path):
    """
    Verify that `OkavangoData` downloads a CSV source and writes it to disk.

    Reasoning
    ---------
    The production code downloads data using `requests.get`. In tests, we patch the
    network call so the test does not depend on internet access and remains repeatable.

    This test checks that:
    - `requests.get` is called exactly once,
    - the expected file is created in the provided temporary directory,
    - the file content matches the mocked HTTP response content.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Built-in pytest fixture providing a temporary directory unique to this test.

    Returns
    -------
    None

    Raises
    ------
    AssertionError
        If the file is not created, the network call is not made as expected, or the
        written bytes do not match the mocked response.

    Examples
    --------
    Run this test only:

    >>> pytest -q -k test_download
    """

    source = DataSource(
        url="https://example.com/test.csv",
        filename="test.csv"
    )

    fake_response = MagicMock()
    fake_response.content = b"Code,Year,Value\nUSA,2023,10\n"
    fake_response.raise_for_status = MagicMock()

    with patch("app.data_handler.requests.get", return_value=fake_response) as mock_get:

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
    Verify that `merge_geospatial_layers` merges metrics into the GeoDataFrame correctly.

    Reasoning
    ---------
    The dashboard relies on geometry and metric columns living in a single GeoDataFrame.
    This test creates a minimal in-memory world layer and a matching metric table to
    confirm the merge:
    - joins on the expected ISO code column (`ADM0_A3`),
    - preserves geometry,
    - does not duplicate or drop rows unintentionally.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Built-in pytest fixture providing a temporary directory unique to this test.
        (Used here to construct the handler consistently with other tests.)

    Returns
    -------
    None

    Raises
    ------
    AssertionError
        If the merged output is not a GeoDataFrame, the geometry column is missing or
        contains nulls, the row count changes unexpectedly, or metric values do not
        match the expected country codes.

    Examples
    --------
    Run this test only:

    >>> pytest -q -k test_merge
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
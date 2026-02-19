"""okavango.py

Downloads, extracts, and merges environmental and geospatial datasets
for the Okavango project. Data sources include Our World in Data (CSV)
and Natural Earth (Shapefile).
"""

import io
import os
import zipfile
from typing import Optional

import geopandas as gpd
import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOWNLOAD_DIR: str = "downloads"
SHAPEFILE_DIR: str = os.path.join(DOWNLOAD_DIR, "ne_110m_admin_0_countries")
SHAPEFILE_PATH: str = os.path.join(SHAPEFILE_DIR, "ne_110m_admin_0_countries.shp")
SHAPEFILE_ZIP_PATH: str = os.path.join(DOWNLOAD_DIR, "ne_110m_admin_0_countries.zip")

# Each tuple contains (url, target_csv_filename).
# A None filename signals that the zip should be saved and extracted as a
# shapefile rather than treated as a single-CSV archive.
DATASET_SOURCES: list[tuple[str, Optional[str]]] = [
    (
        "https://ourworldindata.org/grapher/annual-change-forest-area.zip"
        "?v=1&csvType=full&useColumnShortNames=false",
        "annual-change-forest-area.csv",
    ),
    (
        "https://ourworldindata.org/grapher/annual-deforestation.zip"
        "?v=1&csvType=full&useColumnShortNames=false",
        "annual-deforestation.csv",
    ),
    (
        "https://ourworldindata.org/grapher/terrestrial-protected-areas.zip"
        "?v=1&csvType=full&useColumnShortNames=false",
        "terrestrial-protected-areas.csv",
    ),
    (
        "https://ourworldindata.org/grapher/share-degraded-land.zip"
        "?v=1&csvType=full&useColumnShortNames=false",
        "share-degraded-land.csv",
    ),
    (
        "https://ourworldindata.org/grapher/forest-area-as-share-of-land-area.zip"
        "?v=1&csvType=full&useColumnShortNames=false",
        "forest-area-as-share-of-land-area.csv",
    ),
    (
        "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip",
        None,  # Shapefile archive — extract all contents
    ),
]

CSV_PATHS: list[str] = [
    os.path.join(DOWNLOAD_DIR, "annual-change-forest-area.csv"),
    os.path.join(DOWNLOAD_DIR, "annual-deforestation.csv"),
    os.path.join(DOWNLOAD_DIR, "terrestrial-protected-areas.csv"),
    os.path.join(DOWNLOAD_DIR, "share-degraded-land.csv"),
    os.path.join(DOWNLOAD_DIR, "forest-area-as-share-of-land-area.csv"),
]


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------


def download_datasets() -> None:
    """Download and extract all project datasets into the downloads directory.

    Iterates over ``DATASET_SOURCES`` and skips any file that already exists
    on disk. CSV datasets are extracted directly from their zip archives.
    The Natural Earth shapefile archive is saved as a zip and then extracted
    into its own subdirectory.

    Downloads are streamed in 8 KB chunks to limit memory usage. A connection
    timeout of 10 s and a read timeout of 60 s are applied to every request.

    Returns:
        None

    Raises:
        requests.HTTPError: If the server returns a non-2xx status code.
        zipfile.BadZipFile: If a downloaded file cannot be opened as a zip.
    """
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for url, target_filename in DATASET_SOURCES:

        # --- Skip logic ---------------------------------------------------
        if target_filename is None:
            # Shapefile: skip if the zip already exists on disk.
            if os.path.exists(SHAPEFILE_ZIP_PATH):
                print("  Shapefile zip already exists, skipping...")
                continue
        else:
            # CSV dataset: skip if the extracted file already exists.
            local_csv_path = os.path.join(DOWNLOAD_DIR, target_filename)
            if os.path.exists(local_csv_path):
                print(f"  {target_filename} already exists, skipping download...")
                continue

        # --- Download -----------------------------------------------------
        print(f"Downloading {url}...")
        with requests.get(url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            # Collect streamed chunks into a single bytes object.
            raw_content: bytes = b"".join(
                chunk for chunk in response.iter_content(chunk_size=8192) if chunk
            )

        # --- Extract / save -----------------------------------------------
        if target_filename is None:
            # Save the shapefile zip to disk and extract all contained files.
            with open(SHAPEFILE_ZIP_PATH, "wb") as zip_file:
                zip_file.write(raw_content)
            print(f"  Saved shapefile zip to {SHAPEFILE_ZIP_PATH}")

            with zipfile.ZipFile(SHAPEFILE_ZIP_PATH, "r") as zf:
                zf.extractall(SHAPEFILE_DIR)
            print(f"  Extracted shapefile to {SHAPEFILE_DIR}")
        else:
            # Extract only the target CSV from the in-memory zip archive.
            with zipfile.ZipFile(io.BytesIO(raw_content), "r") as zf:
                zf.extract(target_filename, DOWNLOAD_DIR)
            print(f"  Extracted {target_filename}")


def load_and_merge_data() -> gpd.GeoDataFrame:
    """Load all CSV datasets and the shapefile, then merge them into one GeoDataFrame.

    Merging is performed in two stages:

    1. **CSV stage** — All CSV files are merged sequentially on the ``"Code"``
       (ISO country code) and ``"Year"`` columns using an outer join, so that
       every country-year combination present in any dataset is retained.
       Rows without a ``"Code"`` value (e.g. regional aggregates) are dropped
       before each merge. Duplicate columns introduced by the suffixing
       mechanism are removed after every merge step.

    2. **Geo stage** — The Natural Earth GeoDataFrame is left-joined onto the
       merged CSV DataFrame on ``GU_A3`` (geo side) and ``"Code"`` (CSV side),
       ensuring that all 177 countries in the shapefile are preserved even if
       they have no matching CSV data.

    Returns:
        gpd.GeoDataFrame: A GeoDataFrame containing country geometries and all
        environmental indicator columns from the CSV datasets.

    Raises:
        FileNotFoundError: If any of the expected CSV files or the shapefile
            are missing from the downloads directory.
    """
    merged_csv: Optional[pd.DataFrame] = None

    for csv_path in CSV_PATHS:
        df: pd.DataFrame = pd.read_csv(csv_path)

        # Remove rows that represent regional aggregates (no ISO country code).
        df = df.dropna(subset=["Code"])

        if merged_csv is None:
            # First CSV becomes the base of the merged table.
            merged_csv = df
        else:
            # Outer join preserves all country-year rows from both sides.
            # The "_drop" suffix marks duplicate shared columns for removal.
            merged_csv = merged_csv.merge(
                df,
                on=["Code", "Year"],
                how="outer",
                suffixes=("", "_drop"),
            )
            # Remove columns that are exact duplicates introduced by suffixing.
            merged_csv = merged_csv[
                [col for col in merged_csv.columns if not col.endswith("_drop")]
            ]

    # Load the Natural Earth country polygons as the base GeoDataFrame.
    gdf: gpd.GeoDataFrame = gpd.read_file(SHAPEFILE_PATH)

    # Left join keeps all 177 shapefile countries; unmatched rows get NaN.
    merged: gpd.GeoDataFrame = gdf.merge(
        merged_csv,
        left_on="GU_A3",
        right_on="Code",
        how="left",
    )

    return merged


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

download_datasets()
merged_data: gpd.GeoDataFrame = load_and_merge_data()
print(merged_data.shape)

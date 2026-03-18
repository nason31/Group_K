"""
Project Okavango: Data Handler Module

This module provides data models and data handling utilities for the Okavango project.
It downloads environmental indicators from Our World in Data (OWID) and merges them
with a Natural Earth world-countries shapefile.

The pipeline is organized into:
1) Data models (Pydantic)
2) Data downloading and processing (pandas/geopandas)

Why it works this way
---------------------
- **Idempotency:** downloads are skipped if files already exist locally. This makes
  reruns safe and fast (same inputs → same stored artifacts) and prevents unnecessary
  network calls.
- **"Most recent" snapshot:** when a dataset includes a "Year" column, the pipeline
  keeps the latest year per country. This aligns the dashboard with "current" values
  rather than historical time series.
- **Schema variability:** OWID exports can vary in naming for country identifiers
  ("Code", "ISO", "Entity", etc.). The loader uses heuristics to locate the identifier
  column and normalizes it to "Code" for consistent merging.

Notes
-----
- CSV sources are downloaded once into a local directory and reused on subsequent runs.
- OWID datasets are reduced to a single (most recent) record per country code when a
  "Year" column is present.
- Geospatial joins are performed using the Natural Earth 3-letter country code field
  (preferring "ADM0_A3", falling back to "ISO_A3") merged against the normalized "Code"
  column in each dataset.

Dependencies
------------
os, zipfile, requests
pandas, geopandas
pydantic

Examples
--------
Instantiate the data handler in Python:

>>> from app.data_handler import OkavangoData, project_sources
>>> handler = OkavangoData(sources=project_sources)
>>> handler.merged_data is not None
True
"""

import os
import zipfile
import requests
import pandas as pd
import geopandas as gpd
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict


class DataSource(BaseModel):
    """
    Defines a remote data input used by the Okavango data pipeline.

    A `DataSource` describes either:
    - A CSV file containing country-level metrics (typically from OWID), or
    - A zipped Natural Earth shapefile containing world country geometries.

    Args:
        url (pydantic.HttpUrl): Remote URL of the dataset. Must be a valid
            HTTP/HTTPS URL.
        filename (str, optional): Local filename used to persist a CSV download
            in `download_dir`. Only relevant when `is_shapefile=False`.
            Defaults to None.
        is_shapefile (bool): Whether the source points to a zipped shapefile
            download. Defaults to False.

    Note:
        - When `is_shapefile=True`, `filename` is ignored.
        - For CSV sources, `filename` should be unique to avoid collisions in
          the download directory.

    Example:
        >>> src = DataSource(
        ...     url="https://ourworldindata.org/grapher/annual-deforestation.csv",  # noqa: E501
        ...     filename="annual-deforestation.csv",
        ... )
        >>> src.is_shapefile
        False
    """

    url: HttpUrl
    filename: Optional[str] = Field(default=None)
    is_shapefile: bool = Field(default=False)


class OkavangoData:
    """
    Data handler for Project Okavango.

    This class:
    1) Downloads project sources (CSV metrics + world shapefile) into a
       local directory.
    2) Loads and cleans CSV datasets, normalizing a country code column to
       "Code".
    3) Loads the shapefile into a GeoDataFrame.
    4) Merges each metric dataset into the world map layer.

    Args:
        sources (list[DataSource]): List of sources to download and process.
            Should include one shapefile source and one or more CSV metric
            sources.
        download_dir (str): Directory where downloaded artifacts are stored
            (CSV files and shapefile zip). Defaults to "downloads".

    Attributes:
        sources (list[DataSource]): The configured list of sources.
        download_dir (str): Base directory for persisted downloads.
        shapefile_dir (str): Directory where the shapefile zip is extracted.
        dataframes (dict[str, pd.DataFrame]): Mapping from CSV filename to
            its cleaned DataFrame. Each includes "Code" (normalized country
            identifier) and metric columns (excludes "Year"/"Entity"/"Country"
            when present).
        geo_dataframe (gpd.GeoDataFrame or None): GeoDataFrame loaded from
            the Natural Earth shapefile.
        merged_data (gpd.GeoDataFrame or None): World GeoDataFrame with all
            metric columns merged in.

    Note:
        - Initialization performs the full pipeline (download → load/clean →
          merge).
        - CSV cleaning attempts to infer a geographic key column by searching
          for "code"/"iso", and if none, falling back to "entity"/"country"/
          "name".
        - When a "Year" column exists, only the latest entry per country is
          retained.

    Example:
        >>> handler = OkavangoData(sources=project_sources)
        >>> isinstance(handler.merged_data, gpd.GeoDataFrame)
        True
    """
    def __init__(self, sources: list[DataSource], download_dir: str = "downloads"):
        """
        Initialize the data handler and run the full data preparation pipeline.

        Args:
            sources (list[DataSource]): List of configured sources to download
                and process.
            download_dir (str): Output directory for downloaded and extracted
                data. Defaults to "downloads".

        Raises:
            OSError: If the download directory cannot be created.
            requests.RequestException: If downloads fail during initialization
                (propagated from download step).

        Example:
            >>> handler = OkavangoData(sources=project_sources,
            ...                        download_dir="downloads")
            >>> handler.dataframes is not None
            True
        """
        self.sources = sources
        self.download_dir = download_dir
        self.shapefile_dir = os.path.join(self.download_dir, "ne_110m_admin_0_countries")
        
        self.dataframes: Dict[str, pd.DataFrame] = {}
        self.geo_dataframe: Optional[gpd.GeoDataFrame] = None
        self.merged_data: Optional[gpd.GeoDataFrame] = None

        os.makedirs(self.download_dir, exist_ok=True)
        self.download_project_data()
        self._load_and_clean_dataframes()
        self.merge_geospatial_layers()

    def download_project_data(self) -> None:
        """
        Downloads all configured project sources to the local filesystem.

        This method iterates over `self.sources` and:
        - For shapefiles: downloads a zip to `download_dir`, then extracts it
          into `self.shapefile_dir` if not already present.
        - For CSV files: downloads each CSV to `download_dir` under
          `source.filename` if not already present.

        This method is intentionally **idempotent**: if the expected local
        files already exist, it skips downloading them again. This:
        - reduces runtime and bandwidth usage,
        - makes reruns safe and predictable,
        - aligns with the idempotency principle.

        Returns:
            None

        Raises:
            requests.HTTPError: If a download request returns a non-success
                status and `raise_for_status()` is triggered.
            requests.RequestException: For network issues, timeouts, or other
                request-layer failures.

        Note:
            - Downloads are skipped if the target file already exists locally.
            - Shapefile extraction is performed after download completes.

        Example:
            >>> handler = OkavangoData(sources=project_sources)
            >>> handler.download_project_data()  # skip existing files
        """

        for source in self.sources:
            url_str = str(source.url)
            
            if source.is_shapefile:
                shapefile_zip = os.path.join(self.download_dir, "ne_110m_admin_0_countries.zip")
                if not os.path.exists(shapefile_zip):
                    print(f"Downloading shapefile...")
                    response = requests.get(url_str, stream=True, timeout=(10, 60))
                    response.raise_for_status()
                    with open(shapefile_zip, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    with zipfile.ZipFile(shapefile_zip, "r") as zf:
                        zf.extractall(self.shapefile_dir)
            else:
                csv_path = os.path.join(self.download_dir, source.filename)
                if not os.path.exists(csv_path):
                    print(f"Downloading {source.filename}...")
                    response = requests.get(url_str, stream=True, timeout=(10, 60))
                    response.raise_for_status()
                    
                    with open(csv_path, "wb") as f:
                        f.write(response.content)

    def _load_and_clean_dataframes(self) -> None:
        """
        Load the shapefile and each CSV dataset, then perform basic cleaning.

        The dashboard needs a **single comparable value per country** per
        metric. OWID CSV exports may contain many years or varying schema
        conventions. This method normalizes all sources into a consistent
        shape:
        - a shared key column "Code",
        - the latest observation per country when "Year" is available,
        - only the metric columns required for visualization.

        For each source:
        - Shapefile sources are loaded into `self.geo_dataframe`.
        - CSV sources are read into pandas DataFrames and cleaned by:
          1) Identifying a likely geographic identifier column.
          2) Renaming that column to "Code" (dropping any pre-existing "Code"
             column when necessary to avoid ambiguity).
          3) Dropping rows with missing country codes.
          4) If present, sorting by "Year" descending and keeping the most
             recent row per country.
          5) Keeping only "Code" plus metric columns (dropping "Year",
             "Entity", and "Country" fields when present).

        Returns:
            None

        Raises:
            FileNotFoundError: If the expected shapefile (.shp) is missing when
                attempting to load it.
            UnicodeDecodeError: If a CSV file cannot be decoded using the
                specified encoding ('utf-8-sig').
            pandas.errors.ParserError: If a CSV file is malformed or cannot
                be parsed by pandas.
            OSError: If there are filesystem-related issues while reading
                input files.
            ValueError: If geopandas fails to correctly interpret the shapefile
                contents.

        Note:
            - If no suitable geographic identifier column is found, that CSV
              is skipped.
            - Cleaned DataFrames are stored in `self.dataframes` keyed by
              filename.

        Example:
            >>> handler = OkavangoData(sources=project_sources)
            >>> handler._load_and_clean_dataframes()
            >>> len(handler.dataframes) > 0
            True
        """
        for source in self.sources:
            if source.is_shapefile:
                shp_path = os.path.join(self.shapefile_dir, "ne_110m_admin_0_countries.shp")
                self.geo_dataframe = gpd.read_file(shp_path)
            else:
                csv_path = os.path.join(self.download_dir, source.filename)
                if not os.path.exists(csv_path):
                    continue
                
                df = pd.read_csv(csv_path, encoding='utf-8-sig')

                geo_col = None
                for col in df.columns:
                    clean_col = col.lower()
                    if "code" in clean_col or "iso" in clean_col:
                        geo_col = col
                        break
                
                if not geo_col:
                    for col in df.columns:
                        clean_col = col.lower()
                        if "entity" in clean_col or "country" in clean_col or "name" in clean_col:
                            geo_col = col
                            break

                if not geo_col:
                    continue

                if geo_col != "Code":
                    if "Code" in df.columns:
                        df.drop(columns=["Code"], inplace=True) 
                    df.rename(columns={geo_col: "Code"}, inplace=True)
                
                df = df.dropna(subset=["Code"])

                if "Year" in df.columns:
                    df = df.sort_values("Year", ascending=False).drop_duplicates(subset=["Code"])

                keep_cols = ["Code"]
                for col in df.columns:
                    if col not in ["Code", "Year", "Entity", "Country"]:
                        keep_cols.append(col)
                
                df = df[keep_cols]
                self.dataframes[source.filename] = df

    def merge_geospatial_layers(self) -> None:
        """
        Merge all cleaned metric tables into the world GeoDataFrame.

        Visualization requires geometry + attributes in a single table. This
        method left-joins each cleaned metric DataFrame onto the world
        countries GeoDataFrame so that every country shape is kept even if
        some metrics are missing.

        Process:
        - Creates a copy of `self.geo_dataframe`.
        - Determines which country code column to use for joining:
          - Uses "ADM0_A3" if present, otherwise uses "ISO_A3".
        - Iterates through each cleaned DataFrame in `self.dataframes` and
          left-joins it to the GeoDataFrame on the chosen map code column vs
          the metric "Code" column.
        - Drops any merge-produced duplicate columns with the suffix "_drop".

        Returns:
            None

        Raises:
            KeyError: If expected join columns are missing (e.g., neither
                "ADM0_A3" nor "ISO_A3").
            ValueError: If merge inputs are not mergeable due to incompatible
                dtypes or invalid frames.

        Note:
            - If `self.geo_dataframe` is not loaded, the function returns
              without merging.
            - The final merged result is stored in `self.merged_data`.

        Example:
            >>> handler = OkavangoData(sources=project_sources)
            >>> handler.merge_geospatial_layers()
            >>> "geometry" in handler.merged_data.columns
            True
        """
        if self.geo_dataframe is None:
            return

        merged_gdf = self.geo_dataframe.copy()
        map_code_col = "ADM0_A3" if "ADM0_A3" in merged_gdf.columns else "ISO_A3"

        for filename, df in self.dataframes.items():
            if df.empty:
                continue
                
            merged_gdf = merged_gdf.merge(
                df, left_on=map_code_col, right_on="Code", how="left",
                suffixes=("", "_drop")
            )
            merged_gdf = merged_gdf[[c for c in merged_gdf.columns if not c.endswith("_drop")]]

        self.merged_data = merged_gdf


# --- PROJECT SOURCES CONFIGURATION ---
project_sources = [
    DataSource(
        url="https://ourworldindata.org/grapher/annual-change-forest-area.csv",
        filename="annual-change-forest-area.csv"
    ),
    DataSource(
        url="https://ourworldindata.org/grapher/annual-deforestation.csv",
        filename="annual-deforestation.csv"
    ),
    DataSource(
        url="https://ourworldindata.org/grapher/terrestrial-protected-areas.csv",
        filename="terrestrial-protected-areas.csv"
    ),
    DataSource(
        url="https://ourworldindata.org/grapher/share-degraded-land.csv",
        filename="share-degraded-land.csv"
    ),
    DataSource(
        url="https://ourworldindata.org/grapher/forest-area-as-share-of-land-area.csv",
        filename="forest-area-as-share-of-land-area.csv"
    ),
    DataSource(
        url="https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip",
        is_shapefile=True
    )
]

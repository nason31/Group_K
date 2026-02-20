"""okavango.py

Downloads, extracts, and merges environmental and geospatial datasets
for the Okavango project into a cohesive Class structure.
"""

import io
import os
import zipfile
import requests
import pandas as pd
import geopandas as gpd
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict

# ---------------------------------------------------------------------------
# Pydantic Models for Static Type Checking
# ---------------------------------------------------------------------------

class DataSource(BaseModel):
    """Pydantic model to strictly validate our data source inputs."""
    url: HttpUrl
    filename: Optional[str] = Field(default=None, description="Target CSV filename. None if it is a shapefile.")
    is_shapefile: bool = Field(default=False, description="Flag to identify the shapefile archive.")

# ---------------------------------------------------------------------------
# Main Application Class
# ---------------------------------------------------------------------------

class OkavangoData:
    """Class to handle downloading, loading, and merging of environmental datasets."""

    def __init__(self, sources: list[DataSource], download_dir: str = "downloads"):
        """
        Phase 2 Requirement: __init__ executes both download and merge functions,
        and reads datasets into corresponding attributes.
        """
        self.sources = sources
        self.download_dir = download_dir
        self.shapefile_dir = os.path.join(self.download_dir, "ne_110m_admin_0_countries")
        
        # Attributes to hold our dataframes
        self.dataframes: Dict[str, pd.DataFrame] = {}
        self.geo_dataframe: Optional[gpd.GeoDataFrame] = None
        self.merged_data: Optional[gpd.GeoDataFrame] = None

        os.makedirs(self.download_dir, exist_ok=True)

        # Execute Function 1 & 2 equivalents
        self.download_project_data()
        self._load_and_clean_dataframes()
        self.merge_geospatial_layers()

    def download_project_data(self) -> None:
        """
        Function 1: Downloads and extracts datasets.
        """
        for source in self.sources:
            url_str = str(source.url)
            
            if source.is_shapefile:
                shapefile_zip = os.path.join(self.download_dir, "ne_110m_admin_0_countries.zip")
                if not os.path.exists(shapefile_zip):
                    print(f"Downloading shapefile from {url_str}...")
                    self._fetch_and_extract_zip(url_str, shapefile_zip, extract_dir=self.shapefile_dir)
                else:
                    print("Shapefile already exists, skipping...")
            else:
                csv_path = os.path.join(self.download_dir, source.filename)
                if not os.path.exists(csv_path):
                    print(f"Downloading {source.filename}...")
                    self._fetch_and_extract_csv(url_str, csv_path)
                else:
                    print(f"{source.filename} already exists, skipping...")

    def _fetch_and_extract_zip(self, url: str, save_path: str, extract_dir: str) -> None:
        """Helper method to download and extract a standard zip archive."""
        response = requests.get(url, stream=True, timeout=(10, 60))
        response.raise_for_status()
        
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        with zipfile.ZipFile(save_path, "r") as zf:
            zf.extractall(extract_dir)

    def _fetch_and_extract_csv(self, url: str, save_path: str) -> None:
        """Helper method to download OWID zips and extract the CSV dynamically."""
        response = requests.get(url, stream=True, timeout=(10, 60))
        response.raise_for_status()
        
        # OWID grapher zips usually contain a single CSV, but the name might vary.
        # We read the first CSV we find and save it as our target filename.
        with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
            csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
            if csv_files:
                # Read it into pandas directly from the zip to avoid extraction naming conflicts
                with zf.open(csv_files[0]) as f:
                    df = pd.read_csv(f)
                    df.to_csv(save_path, index=False)

    def _load_and_clean_dataframes(self) -> None:
        """
        Reads datasets into class attributes and filters for the MOST RECENT year.
        This handles the KeyError by dynamically searching for the country code column.
        """
        for source in self.sources:
            if source.is_shapefile:
                shp_path = os.path.join(self.shapefile_dir, "ne_110m_admin_0_countries.shp")
                self.geo_dataframe = gpd.read_file(shp_path)
            else:
                csv_path = os.path.join(self.download_dir, source.filename)
                df = pd.read_csv(csv_path)

                # 1. Dynamically find the ISO Code column to avoid KeyErrors
                code_col = next((col for col in df.columns if col.lower() in ["code", "iso code", "iso_code", "country code"]), None)
                
                if not code_col:
                    print(f"Warning: No country code column found in {source.filename}. Skipping dataset.")
                    continue

                # Standardize column name to "Code"
                df.rename(columns={code_col: "Code"}, inplace=True)
                df = df.dropna(subset=["Code"])

                # 2. Filter for the MOST RECENT data per country (Requirement)
                if "Year" in df.columns:
                    idx = df.groupby("Code")["Year"].idxmax()
                    df = df.loc[idx]

                self.dataframes[source.filename] = df

    def merge_geospatial_layers(self) -> None:
        """
        Function 2: Merges the map (GeoPandas) with the latest dataset statistics.
        Ensures the left dataframe is the GeoDataFrame as requested.
        """
        if self.geo_dataframe is None:
            raise ValueError("Shapefile data not loaded. Cannot merge.")

        # Start with the map as the base (left dataframe)
        merged_gdf = self.geo_dataframe.copy()

        for filename, df in self.dataframes.items():
            # Left join ensures we keep all 177 countries on the map, 
            # even if OWID is missing data for them.
            merged_gdf = merged_gdf.merge(
                df,
                left_on="GU_A3",  # Natural Earth's 3-letter ISO code column
                right_on="Code",  # Our standardized OWID code column
                how="left",
                suffixes=("", f"_{filename.split('.')[0]}") # Prevent overlapping column names
            )

        self.merged_data = merged_gdf


# ---------------------------------------------------------------------------
# Execution Block (Will run when you test the file directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    
    # Define sources using the Pydantic model for strict validation
    project_sources = [
        DataSource(
            url="https://ourworldindata.org/grapher/annual-change-forest-area.zip?v=1&csvType=full&useColumnShortNames=false",
            filename="annual-change-forest-area.csv"
        ),
        DataSource(
            url="https://ourworldindata.org/grapher/annual-deforestation.zip?v=1&csvType=full&useColumnShortNames=false",
            filename="annual-deforestation.csv"
        ),
        DataSource(
            url="https://ourworldindata.org/grapher/terrestrial-protected-areas.zip?v=1&csvType=full&useColumnShortNames=false",
            filename="terrestrial-protected-areas.csv"
        ),
        DataSource(
            url="https://ourworldindata.org/grapher/share-degraded-land.zip?v=1&csvType=full&useColumnShortNames=false",
            filename="share-degraded-land.csv"
        ),
        DataSource(
            url="https://ourworldindata.org/grapher/forest-area-as-share-of-land-area.zip?v=1&csvType=full&useColumnShortNames=false",
            filename="forest-area-as-share-of-land-area.csv"
        ),
        DataSource(
            url="https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip",
            is_shapefile=True
        )
    ]

    print("Initializing OkavangoData Class and processing pipelines...")
    okavango = OkavangoData(sources=project_sources)
    
    print("\nMerge Complete!")
    print(f"Final GeoDataFrame Shape: {okavango.merged_data.shape}")
    print(f"Columns ready for Streamlit: {list(okavango.merged_data.columns)}")
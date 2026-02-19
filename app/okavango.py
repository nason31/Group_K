"""okavango.py

Downloads, extracts, and merges environmental and geospatial datasets
for the Okavango project. Data sources include Our World in Data (CSV)
and Natural Earth (Shapefile).
"""

import io
import os
import zipfile
from typing import Optional, List, Dict

import geopandas as gpd
import pandas as pd
import requests
from pydantic import BaseModel, HttpUrl, Field

# ---------------------------------------------------------------------------
# Pydantic Schema (Replacing the old Tuple list)
# ---------------------------------------------------------------------------

class DatasetSource(BaseModel):
    """Validates the URL and target filename for each dataset."""
    url: HttpUrl
    target_filename: Optional[str] = Field(None, description="None signals a shapefile archive")

# ---------------------------------------------------------------------------
# The Main Class
# ---------------------------------------------------------------------------

class OkavangoDataHandler:
    """
    Manages the environmental and geospatial data lifecycle.
    """
    def __init__(
        self,
        download_dir: str = "downloads",
        sources: Optional[List[DatasetSource]] = None
    ) -> None:
        """
        Phase 2 Requirements:
        1. Initialize directory and path constants as attributes.
        2. Execute download and merge functions automatically.
        3. Store dataframes as class attributes.
        """
        # Converting constants to instance attributes
        self.download_dir = download_dir
        self.shapefile_dir = os.path.join(self.download_dir, "ne_110m_admin_0_countries")
        self.shapefile_path = os.path.join(self.shapefile_dir, "ne_110m_admin_0_countries.shp")
        
        # New attributes for storing loaded data
        self.dataframes: Dict[str, pd.DataFrame] = {}
        self.final_map: Optional[gpd.GeoDataFrame] = None

        # Automatic execution as per requirements
        if sources:
            self.download_project_data(sources)
            self.final_map = self.merge_geospatial_layers()
        
    def download_project_data(self, sources: List[DatasetSource]) -> None:
        """Function 1: Handles the downloading and extraction logic."""
        os.makedirs(self.download_dir, exist_ok=True)

        for source in sources:
            url_str = str(source.url)
            
            # Streaming download logic from original code
            with requests.get(url_str, stream=True, timeout=(10, 60)) as response:
                response.raise_for_status()
                raw_content = b"".join(chunk for chunk in response.iter_content(8192) if chunk)

            if source.target_filename:
                # Extract CSV and immediately read into the class attribute
                with zipfile.ZipFile(io.BytesIO(raw_content), "r") as zf:
                    zf.extract(source.target_filename, self.download_dir)
                
                # REQUIREMENT: Read datasets into attributes
                path = os.path.join(self.download_dir, source.target_filename)
                self.dataframes[source.target_filename] = pd.read_csv(path).dropna(subset=["Code"])
            else:
                # Handle Shapefile extraction
                zip_path = os.path.join(self.download_dir, "ne_countries.zip")
                with open(zip_path, "wb") as f:
                    f.write(raw_content)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(self.shapefile_dir)
    
    def merge_geospatial_layers(self) -> gpd.GeoDataFrame:
        """Function 2: Merges the shapefile (left) with the downloaded CSVs."""
        # Load the base map
        gdf = gpd.read_file(self.shapefile_path)
        
        merged_csv: Optional[pd.DataFrame] = None
        for df in self.dataframes.values():
            if merged_csv is None:
                merged_csv = df
            else:
                # Merge logic using Code and Year
                merged_csv = merged_csv.merge(df, on=["Code", "Year"], how="outer", suffixes=("", "_drop"))
                merged_csv = merged_csv[[col for col in merged_csv.columns if not col.endswith("_drop")]]

        # Final merge with GeoPandas on the LEFT
        if merged_csv is not None:
            return gdf.merge(merged_csv, left_on="GU_A3", right_on="Code", how="left")
        return gdf

if __name__ == "__main__":
    # You would define your sources here using the Pydantic model
    my_sources = [
        DatasetSource(url="https://ourworldindata.org/grapher/annual-deforestation.zip?v=1", target_filename="annual-deforestation.csv"),
        DatasetSource(url="https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip")
    ]
    
    # This single call now downloads, extracts, reads into attributes, and merges.
    handler = OkavangoDataHandler(sources=my_sources)
    
    # You can access the final result directly
    print(handler.final_map.head())

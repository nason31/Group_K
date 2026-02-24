import os
import zipfile
import requests
import pandas as pd
import geopandas as gpd
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict

# ==========================================
# 1. DATA MODELS & PIPELINE 
# ==========================================

class DataSource(BaseModel):
    url: HttpUrl
    filename: Optional[str] = Field(default=None)
    is_shapefile: bool = Field(default=False)

class OkavangoData:
    def __init__(self, sources: list[DataSource], download_dir: str = "downloads"):
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


# --- PROJECT SOURCES ---
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


# ==========================================
# 2. STREAMLIT DASHBOARD
# ==========================================

st.set_page_config(page_title="Project Okavango", layout="wide")
st.title("🌍 Project Okavango: Environmental Dashboard")
st.markdown("**Analyzing the most recent environmental data from Our World in Data.**")

@st.cache_resource
def get_data_handler():
    with st.spinner("Downloading and merging the latest data..."):
        return OkavangoData(sources=project_sources)

handler = get_data_handler()
gdf = handler.merged_data

PRETTY_LABELS = {
    "Annual deforestation": "Annual Deforestation",
    "Net forest conversion": "Annual Change in Forest Area",
    "Terrestrial protected area": "Share of Protected Land",
    "Proportion Of Land That Is Degraded Over Total Land Area (%)": "Share of Degraded Land",
    "Forest area as a proportion of total land area": "Forest Area as Share of Land",
}

def format_metric(raw_name):
    return PRETTY_LABELS.get(raw_name, raw_name.replace("_", " ").title())

st.subheader("Map Visualization")

owid_metrics = []
for df in handler.dataframes.values():
    for col in df.columns:
        if col != "Code":
            owid_metrics.append(col)

valid_metrics = [col for col in owid_metrics if col in gdf.columns]

if not valid_metrics:
    st.error("Merge failed! The OWID metrics didn't attach to the map.")
    st.stop()

selected_metric = st.selectbox("Select a metric to visualize:", valid_metrics, format_func=format_metric)

gdf[selected_metric] = pd.to_numeric(gdf[selected_metric], errors='coerce')
display_name = format_metric(selected_metric)

# --- PLOT 1: THE WORLD MAP ---
fig, ax = plt.subplots(1, 1, figsize=(15, 8))
gdf.plot(
    column=selected_metric,
    ax=ax,
    legend=True,
    cmap="YlGnBu",
    missing_kwds={"color": "lightgrey", "label": "No Data"}
)
ax.set_title(f"Global Distribution: {display_name}") 
ax.set_axis_off()
st.pyplot(fig)

st.divider()

# --- PLOT 2: TOP 5 & BOTTOM 5 GRAPH ---
st.subheader(f"Extremes: Top 5 and Bottom 5 Countries for {display_name}") 

chart_data = gdf.dropna(subset=[selected_metric])
top_5 = chart_data.nlargest(5, selected_metric)
bottom_5 = chart_data.nsmallest(5, selected_metric)
extremes_df = pd.concat([top_5, bottom_5])

fig2, ax2 = plt.subplots(figsize=(10, 5))
country_col = "NAME" if "NAME" in extremes_df.columns else "ADMIN" 

bars = ax2.bar(extremes_df[country_col], extremes_df[selected_metric], color=['#d9534f']*5 + ['#5cb85c']*5)
ax2.set_ylabel(display_name) 
ax2.set_title(f"Top 5 vs Bottom 5: {display_name}") 
plt.xticks(rotation=45, ha='right')
ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
fig2.tight_layout()

st.pyplot(fig2)
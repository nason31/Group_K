"""
Project Okavango: Streamlit Dashboard

This module implements the Streamlit web application for visualizing environmental
data from Our World in Data integrated with Natural Earth country geometries.

The dashboard provides:
1) Interactive map visualization of environmental metrics
2) Top 5 and Bottom 5 country comparisons for each metric

Dependencies
------------
streamlit, matplotlib, pandas, geopandas
app.data_handler (for OkavangoData and project_sources)

Usage
-----
Run this app from the terminal:

>>> streamlit run app/streamlit_app.py

Or use the main.py entry point:

>>> python main.py
"""

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from data_handler import OkavangoData, project_sources


# ==========================================
# STREAMLIT CONFIGURATION
# ==========================================

st.set_page_config(page_title="Project Okavango", layout="wide")
st.title("🌍 Project Okavango: Environmental Dashboard")
st.markdown("**Analyzing the most recent environmental data from Our World in Data.**")


# ==========================================
# DATA LOADING
# ==========================================

@st.cache_resource
def get_data_handler():
    """
    Create and cache an `OkavangoData` handler for the Streamlit app.

    This function is decorated with `st.cache_resource` so the expensive steps
    (download, preprocessing, and geospatial merging) are performed only once
    per app session unless the cache is invalidated.

    Returns
    -------
    OkavangoData
        A fully prepared data handler containing the merged geospatial dataset.

    Raises
    ------
    requests.RequestException
        If a download fails during handler creation.
    OSError
        If local filesystem operations fail (e.g., creating directories).    

    Notes
    -----
    - A Streamlit spinner is shown while the data is being downloaded and merged.
    - The handler uses the global `project_sources` configuration from data_handler.py.

    Examples
    --------
    In the Streamlit script:

    >>> handler = get_data_handler()
    >>> gdf = handler.merged_data
    """
    with st.spinner("Downloading and merging the latest data..."):
        return OkavangoData(sources=project_sources)


handler = get_data_handler()
gdf = handler.merged_data


# ==========================================
# HELPER FUNCTIONS & CONFIGURATION
# ==========================================

PRETTY_LABELS = {
    "Annual deforestation": "Annual Deforestation",
    "Net forest conversion": "Annual Change in Forest Area",
    "Terrestrial protected area": "Share of Protected Land",
    "Proportion Of Land That Is Degraded Over Total Land Area (%)": "Share of Degraded Land",
    "Forest area as a proportion of total land area": "Forest Area as Share of Land",
}


def format_metric(raw_name: str) -> str:
    """
    Convert a raw OWID column name into a user-friendly metric label.

    Reasoning
    ---------
    OWID column names can be quite long or inconsistent across different datasets.
    For the dashboard, we want the metric names to look clean and easy to understand
    for users. At the same time, we keep the original column names internally so the
    data processing and plotting logic continues to work correctly.

    Parameters
    ----------
    raw_name : str
        Raw column name as found in OWID CSV files and propagated into the merged
        GeoDataFrame.

    Returns
    -------
    str
        Human-readable label for display in the Streamlit UI. If `raw_name` is not
        present in `PRETTY_LABELS`, a best-effort title-cased formatting is applied.

    Examples
    --------
    >>> format_metric("Annual deforestation")
    'Annual Deforestation'
    >>> format_metric("some_new_metric_name")
    'Some New Metric Name'
    """        
    return PRETTY_LABELS.get(raw_name, raw_name.replace("_", " ").title())


# ==========================================
# METRIC SELECTION
# ==========================================

st.subheader("Map Visualization")

# Extract available metrics from loaded dataframes
owid_metrics = []
for df in handler.dataframes.values():
    for col in df.columns:
        if col != "Code":
            owid_metrics.append(col)

# Filter to only metrics that successfully merged into the geodataframe
valid_metrics = [col for col in owid_metrics if col in gdf.columns]

if not valid_metrics:
    st.error("Merge failed! The OWID metrics didn't attach to the map.")
    st.stop()

selected_metric = st.selectbox(
    "Select a metric to visualize:", 
    valid_metrics, 
    format_func=format_metric
)

# Ensure metric is numeric for visualization
gdf[selected_metric] = pd.to_numeric(gdf[selected_metric], errors='coerce')
display_name = format_metric(selected_metric)


# ==========================================
# PLOT 1: WORLD MAP VISUALIZATION
# ==========================================

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


# ==========================================
# PLOT 2: TOP 5 & BOTTOM 5 COMPARISON
# ==========================================

st.subheader(f"Extremes: Top 5 and Bottom 5 Countries for {display_name}") 

# Filter out rows with missing data for the selected metric
chart_data = gdf.dropna(subset=[selected_metric])
top_5 = chart_data.nlargest(5, selected_metric)
bottom_5 = chart_data.nsmallest(5, selected_metric)

# Concatenate bottom 5 first (left side), then top 5 (right side)
extremes_df = pd.concat([bottom_5, top_5])

# Create bar chart
fig2, ax2 = plt.subplots(figsize=(10, 5))
country_col = "NAME" if "NAME" in extremes_df.columns else "ADMIN" 

# Color scheme: Bottom 5 (red) on left, Top 5 (green) on right
bars = ax2.bar(
    extremes_df[country_col], 
    extremes_df[selected_metric], 
    color=['#d9534f']*5 + ['#5cb85c']*5
)

ax2.set_ylabel(display_name) 
ax2.set_title(f"Top 5 vs Bottom 5: {display_name}") 
plt.xticks(rotation=45, ha='right')
ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
fig2.tight_layout()

st.pyplot(fig2)

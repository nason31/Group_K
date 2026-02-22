import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from okavango import OkavangoData, project_sources

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
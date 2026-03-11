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

from typing import Any, Optional
import importlib

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, ScalarFormatter
from matplotlib.patches import Patch

from data_handler import OkavangoData, project_sources


# ==========================================
# STREAMLIT CONFIGURATION
# ==========================================

st.set_page_config(page_title="Project Okavango", layout="wide")


def apply_custom_styles() -> None:
    """Apply lightweight styling to give the app a cleaner website-like look."""
    st.markdown(
        """
        <style>
            .okv-header {
                background: linear-gradient(120deg, #d8f3dc 0%, #e7f5ff 100%);
                border: 1px solid #c7e9d0;
                border-radius: 14px;
                padding: 1rem 1.2rem;
                margin-bottom: 1rem;
            }
            .okv-title {
                margin: 0;
                color: #114b2b;
                font-size: 1.8rem;
            }
            .okv-subtitle {
                margin: 0.35rem 0 0 0;
                color: #2f5d50;
                font-size: 1rem;
            }
            .okv-nav {
                display: flex;
                gap: 0.6rem;
                margin: 0.2rem 0 1rem 0;
                flex-wrap: wrap;
            }
            .okv-nav-link {
                text-decoration: none;
                border-radius: 999px;
                padding: 0.45rem 0.9rem;
                border: 1px solid #cbd5e1;
                color: #1f2937;
                background: #f8fafc;
                font-weight: 600;
                font-size: 0.95rem;
            }
            .okv-nav-link.active {
                background: #0f766e;
                color: #ffffff;
                border-color: #0f766e;
            }
            .block-container {
                padding-top: 1.4rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_header() -> None:
    """Render the dashboard header card."""
    st.markdown(
        """
        <div class="okv-header">
            <h1 class="okv-title">Project Okavango: Environmental Dashboard</h1>
            <p class="okv-subtitle">Analyzing the most recent environmental data and AI-based risk insights.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def get_current_page() -> str:
    """Get active page from session state, seeded once from query params."""
    valid_pages = {"dashboard", "workflow"}

    if "active_page" not in st.session_state:
        page = st.query_params.get("page", "dashboard")
        if isinstance(page, list):
            page = page[0] if page else "dashboard"
        st.session_state.active_page = page if page in valid_pages else "dashboard"

    return st.session_state.active_page


def render_top_navigation(active_page: str) -> None:
    """Render top navigation buttons that switch pages in the same tab."""
    nav_col_1, nav_col_2 = st.columns(2)

    with nav_col_1:
        if st.button(
            "Data Dashboard",
            use_container_width=True,
            type="primary" if active_page == "dashboard" else "secondary",
            key="top_nav_dashboard",
        ):
            if st.session_state.active_page != "dashboard":
                st.session_state.active_page = "dashboard"
                st.rerun()

    with nav_col_2:
        if st.button(
            "AI Workflow",
            use_container_width=True,
            type="primary" if active_page == "workflow" else "secondary",
            key="top_nav_workflow",
        ):
            if st.session_state.active_page != "workflow":
                st.session_state.active_page = "workflow"
                st.rerun()


apply_custom_styles()
render_top_header()


def get_pipeline_runner() -> Optional[Any]:
    """Attempt to load the backend pipeline function from common module names."""
    module_candidates = [
        "ai_backend",
        "app.ai_backend",
        "ai_pipeline",
        "pipeline",
        "backend",
        "app.ai_pipeline",
        "app.pipeline",
        "app.backend",
    ]

    for module_name in module_candidates:
        try:
            module = importlib.import_module(module_name)
            runner = getattr(module, "run_pipeline", None)
            if callable(runner):
                return runner
        except Exception:
            continue

    return None


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
    "deforestation": "Annual Deforestation",
    "annual deforestation": "Annual Deforestation",
    "net forest conversion": "Annual Change in Forest Area",
    "annual change in forest area": "Annual Change in Forest Area",
    "terrestrial protected area": "Share of Protected Land",
    "terrestrial protected areas (% of total land area)": "Share of Protected Land",
    "proportion of land that is degraded over total land area (%)": "Share of Degraded Land",
    "forest area as a proportion of total land area": "Forest Area as Share of Land",
    "share of land covered by forest": "Forest Area as Share of Land",
}

METRIC_UNITS = {
    "deforestation": "km²/year",
    "annual deforestation": "km²/year",
    "net forest conversion": "km²/year",
    "annual change in forest area": "km²/year",
    "terrestrial protected area": "%",
    "terrestrial protected areas (% of total land area)": "%",
    "proportion of land that is degraded over total land area (%)": "%",
    "forest area as a proportion of total land area": "%",
    "share of land covered by forest": "%",
}


def normalize_metric_name(raw_name: str) -> str:
    """Normalize metric names for robust label/unit lookups."""
    return raw_name.strip().lower()


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
    normalized_name = normalize_metric_name(raw_name)
    return PRETTY_LABELS.get(normalized_name, raw_name.replace("_", " ").title())


def metric_label_with_unit(raw_name: str) -> str:
    """Build a display label that includes metric units when known."""
    pretty_name = format_metric(raw_name)
    unit = METRIC_UNITS.get(normalize_metric_name(raw_name))
    if not unit:
        return pretty_name
    return f"{pretty_name} ({unit})"


def _first_non_empty(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    """Return the first present and non-empty value for a list of possible keys."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return default


def render_page_1() -> None:
    """Render the original map-based metrics dashboard."""
    st.subheader("Map Visualization")
    st.sidebar.header("Dashboard Controls")
    st.sidebar.caption("Choose the environmental indicator to visualize on the global map.")

    # Extract available metrics from loaded dataframes (CSV files only, excludes shapefile)
    owid_metrics = []
    for _, df in handler.dataframes.items():
        for col in df.columns:
            if col != "Code":
                owid_metrics.append(col)

    # Filter to only metrics that successfully merged into the geodataframe
    # Exclude geometry, shapefile-only columns, and annotation columns
    excluded_columns = {
        "geometry", "ADMIN", "ISO_A3", "ADM0_A3", "NAME", "CONTINENT", "REGION_UN",
        "SUBREGION", "REGION_WB", "NAME_LONG", "FORMAL_EN", "SOVEREIGNT", "SOV_A3"
    }

    valid_metrics = [
        col for col in owid_metrics
        if col in gdf.columns
        and col not in excluded_columns
        and "annotation" not in col.lower()
    ]

    if not valid_metrics:
        st.error("Merge failed! The OWID metrics didn't attach to the map.")
        st.stop()

    selected_metric = st.sidebar.selectbox(
        "Environmental indicator",
        valid_metrics,
        format_func=format_metric,
    )

    # Ensure metric is numeric for visualization
    gdf[selected_metric] = pd.to_numeric(gdf[selected_metric], errors="coerce")
    display_name = metric_label_with_unit(selected_metric)
    selected_unit = METRIC_UNITS.get(normalize_metric_name(selected_metric), "")

    # Get data statistics for context
    data_with_values = gdf[selected_metric].dropna()
    countries_with_data = len(data_with_values)

    # Display metric context
    st.info(f"📊 **Data Summary:** {countries_with_data} countries with data")

    # ==========================================
    # PLOT 1: WORLD MAP VISUALIZATION
    # ==========================================

    fig, ax = plt.subplots(1, 1, figsize=(15, 8))
    gdf.plot(
        column=selected_metric,
        ax=ax,
        legend=True,
        cmap="YlGnBu",
        missing_kwds={"color": "lightgrey", "label": "No Data"},
        legend_kwds={
            "label": display_name,
            "orientation": "horizontal",
            "shrink": 0.8,
            "aspect": 30,
            "pad": 0.05,
        },
    )

    # Improve colorbar readability for large-value metrics.
    colorbar_ax = fig.axes[-1]
    if normalize_metric_name(selected_metric) in {"deforestation", "annual deforestation", "net forest conversion", "annual change in forest area"}:
        colorbar_ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x / 1_000_000:.2f}M"))
        colorbar_ax.xaxis.get_offset_text().set_visible(False)
    else:
        plain_formatter = ScalarFormatter(useOffset=False)
        plain_formatter.set_scientific(False)
        colorbar_ax.xaxis.set_major_formatter(plain_formatter)
        colorbar_ax.xaxis.get_offset_text().set_visible(False)

    # Add explicit unit label on the colorbar so users always see the measurement.
    if selected_unit:
        colorbar_ax.set_title(f"Unit: {selected_unit}", fontsize=10, pad=8)

    ax.set_title(f"Global Distribution: {display_name}", fontsize=16, fontweight="bold", pad=20)
    ax.set_axis_off()
    st.pyplot(fig)
    st.caption("Grey countries indicate no available source value for the selected metric.")

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
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    country_col = "NAME" if "NAME" in extremes_df.columns else "ADMIN"

    # Get country names and values
    countries = extremes_df[country_col].tolist()
    values = extremes_df[selected_metric].tolist()

    # Color scheme: Bottom 5 (red) on left, Top 5 (green) on right
    colors = ["#d9534f"] * 5 + ["#5cb85c"] * 5
    bars = ax2.bar(countries, values, color=colors, edgecolor="black", linewidth=0.5)

    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        ax2.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            f"{height:,.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    # Create custom legend
    legend_elements = [
        Patch(facecolor="#d9534f", edgecolor="black", label="Bottom 5 (Lowest)"),
        Patch(facecolor="#5cb85c", edgecolor="black", label="Top 5 (Highest)"),
    ]
    ax2.legend(handles=legend_elements, loc="upper left", fontsize=10, framealpha=0.9)

    ax2.set_ylabel(display_name, fontsize=12, fontweight="bold")
    ax2.set_xlabel("Country", fontsize=12, fontweight="bold")
    ax2.set_title(f"Top 5 vs Bottom 5 Countries: {display_name}", fontsize=14, fontweight="bold", pad=15)
    plt.xticks(rotation=45, ha="right", fontsize=10)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
    ax2.grid(axis="y", alpha=0.3, linestyle="--")
    fig2.tight_layout()

    st.pyplot(fig2)


def render_risk_badge(is_danger: bool) -> None:
    """Render a clear visual indicator for environmental risk."""
    if is_danger:
        badge_color = "#b42318"
        bg_color = "#fee4e2"
        label = "⚠️ High Environmental Risk"
    else:
        badge_color = "#027a48"
        bg_color = "#d1fadf"
        label = "✅ Low Environmental Risk"

    st.markdown(
        f"""
        <div style="padding: 0.8rem 1rem; border-radius: 0.6rem; background: {bg_color}; border: 1px solid {badge_color}; display: inline-block; margin-top: 0.5rem; margin-bottom: 0.8rem;">
            <span style="color: {badge_color}; font-weight: 700; font-size: 1rem;">{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_2() -> None:
    """Render the AI workflow page that calls run_pipeline(lat, lon, zoom)."""
    st.subheader("Page 2: AI Image Workflow")
    st.caption("Select coordinates and run the image analysis pipeline.")

    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None

    run_pipeline = get_pipeline_runner()
    if run_pipeline is None:
        st.error(
            "Could not find backend function run_pipeline(lat, lon, zoom). "
            "Expected it in ai_pipeline.py, pipeline.py, or backend.py."
        )
        st.stop()

    col_a, col_b = st.columns([1.2, 1])
    with col_a:
        lat = st.slider("Latitude", min_value=-85.0, max_value=85.0, value=-19.0, step=0.1)
        lon = st.slider("Longitude", min_value=-180.0, max_value=180.0, value=23.0, step=0.1)
        zoom = st.slider("Zoom", min_value=1, max_value=18, value=11, step=1)

    with col_b:
        preset = st.selectbox(
            "Quick region preset",
            [
                "Custom",
                "Okavango Delta",
                "Amazon Basin",
                "Borneo Rainforest",
                "Great Barrier Reef",
            ],
        )

        if preset != "Custom":
            presets = {
                "Okavango Delta": (-19.3, 22.9, 10),
                "Amazon Basin": (-3.4, -62.2, 8),
                "Borneo Rainforest": (0.9, 114.0, 8),
                "Great Barrier Reef": (-18.3, 147.7, 9),
            }
            lat, lon, zoom = presets[preset]
            st.info(
                "Preset applied. Coordinates used for this run: "
                f"lat={lat}, lon={lon}, zoom={zoom}"
            )

        st.text_input(
            "Run label (optional)",
            value="",
            help="Optional note for the operator; backend can store this if supported.",
        )

    run_clicked = st.button("Run AI Pipeline", type="primary", use_container_width=True)

    if run_clicked:
        with st.spinner("Running pipeline: image fetch + AI analysis..."):
            try:
                result = run_pipeline(float(lat), float(lon), int(zoom))
                st.session_state.pipeline_result = result
            except Exception as exc:
                st.error(f"Pipeline execution failed: {exc}")
                return
    else:
        result = st.session_state.pipeline_result

    if result is None:
        st.info("Choose parameters and click 'Run AI Pipeline' to analyze the area.")
        return

    if not isinstance(result, dict):
        st.error("Backend returned an invalid response. Expected dict[str, Any].")
        return

    from_cache = bool(_first_non_empty(result, ["from_cache", "cached", "cache_hit"], False))
    image_path = _first_non_empty(result, ["image_path", "image_file", "image", "image_filepath"])
    image_description = _first_non_empty(
        result,
        ["image_description", "description", "image_text", "image_caption"],
        "No image description returned.",
    )
    danger_value = _first_non_empty(result, ["danger", "is_danger", "risk", "danger_flag"], False)
    risk_text = _first_non_empty(
        result,
        ["text_description", "risk_text", "risk_assessment", "analysis"],
        "No risk assessment text returned.",
    )

    danger_str = str(danger_value).strip().lower()
    is_danger = danger_str in {"y", "yes", "true", "1", "danger", "high", "high_risk"} or bool(danger_value) is True

    if from_cache:
        st.success("Cached result found. Skipped compute and loaded existing analysis.")
    else:
        st.success("Pipeline completed with a fresh analysis run.")

    img_col, txt_col = st.columns(2)

    with img_col:
        st.markdown("### Satellite Image")
        if image_path:
            try:
                st.image(image_path, use_container_width=True)
            except Exception:
                st.warning(f"Could not render image at path: {image_path}")
        else:
            st.warning("No image path returned by backend.")

    with txt_col:
        st.markdown("### Image Description")
        st.write(image_description)

    st.markdown("### Environmental Risk Check")
    render_risk_badge(is_danger)
    st.write(risk_text)

    with st.expander("Pipeline response details"):
        st.json(result)


active_page = get_current_page()
render_top_navigation(active_page)

if active_page == "dashboard":
    render_page_1()
else:
    render_page_2()

"""
Project Okavango: Database Module

Handles all persistence for the AI pipeline on Page 2:
- Initializes the images.csv database
- Checks the cache before running the pipeline (keyed on lat + lon + zoom)
- Saves new pipeline results (CSV row metadata)
- Loads cached results for display

The database lives in the `database/` directory.
Images are stored in the `images/` directory with deterministic filenames.

Usage
-----
    from app.db import init_db, check_cache, save_run, load_cached_result

Notes
-----
- All functions are stateless and safe to call multiple times.
- The CSV is append-only: new rows are added, nothing is ever deleted.
- Image filenames are derived from lat/lon/zoom so they can be reconstructed
  from the CSV without storing absolute paths.
"""

import os
import yaml
import pandas as pd
from datetime import datetime
from typing import Any


# ==========================================
# CONSTANTS
# ==========================================

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_DIR     = os.path.join(ROOT_DIR, "database")
IMAGES_DIR = os.path.join(ROOT_DIR, "images")
CSV_PATH   = os.path.join(DB_DIR, "images.csv")

CSV_COLUMNS = [
    "timestamp",
    "latitude",
    "longitude",
    "zoom",
    "image_path",
    "image_prompt",
    "image_model",
    "image_description",
    "text_prompt",
    "text_model",
    "text_description",
    "danger",
]


# ==========================================
# CONFIG LOADER
# ==========================================

def load_models_config(config_path: str = None) -> dict[str, Any]:
    """
    Load the models.yaml configuration file.

    Parameters
    ----------
    config_path : str, optional
        Explicit path to models.yaml. Defaults to <project_root>/models.yaml.

    Returns
    -------
    dict
        Parsed YAML content with model names, prompts and settings.

    Raises
    ------
    FileNotFoundError
        If models.yaml is not found at the expected location.

    Examples
    --------
    >>> config = load_models_config()
    >>> config["image_model"]["name"]
    'llava:7b'
    """
    if config_path is None:
        config_path = os.path.join(ROOT_DIR, "models.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"models.yaml not found at {config_path}. "
            "Please ensure models.yaml is in the project root."
        )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    return config

# ==========================================
# HELPERS
# ==========================================

def _image_filename(lat: float, lon: float, zoom: int) -> str:
    """
    Build a deterministic image filename from coordinates and zoom level.

    Parameters
    ----------
    lat : float
        Latitude coordinate.
    lon : float
        Longitude coordinate.
    zoom : int
        Zoom level.

    Returns
    -------
    str
        Filename in format ``img_<lat>_<lon>_<zoom>.png`` with dots replaced by hyphens.

    Examples
    --------
    >>> _image_filename(-3.0, -3.0, 17)
    'img_-3-0_-3-0_17.png'
    """
    lat_str = str(lat).replace(".", "-")
    lon_str = str(lon).replace(".", "-")
    return f"img_{lat_str}_{lon_str}_{zoom}.png"


def _image_path(lat: float, lon: float, zoom: int) -> str:
    """
    Get the full filesystem path to the image file for given coordinates and zoom.

    Parameters
    ----------
    lat : float
        Latitude coordinate.
    lon : float
        Longitude coordinate.
    zoom : int
        Zoom level.

    Returns
    -------
    str
        Absolute path to the image file in the images directory.
    """
    return os.path.join(IMAGES_DIR, _image_filename(lat, lon, zoom))


# ==========================================
# INIT
# ==========================================

def init_db() -> None:
    """
    Initialize the database directory structure and CSV file.

    Creates the database and images directories if they don't exist.
    Initializes an empty images.csv with proper columns on first run.
    Safe to call multiple times (idempotent).

    Returns
    -------
    None
    """
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    if not os.path.exists(CSV_PATH):
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(CSV_PATH, index=False)
        print(f"[DB] Initialized new database at {CSV_PATH}")
    else:
        print(f"[DB] Database found at {CSV_PATH}")
# ==========================================
# CACHE
# ==========================================

def check_cache(lat: float, lon: float, zoom: int) -> bool:
    """
    Check if a pipeline result exists for the given coordinates and zoom level.

    Parameters
    ----------
    lat : float
        Latitude coordinate.
    lon : float
        Longitude coordinate.
    zoom : int
        Zoom level.

    Returns
    -------
    bool
        True if both the CSV entry and image file exist for the given parameters,
        False otherwise.
    """
    if not os.path.exists(CSV_PATH):
        return False

    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return False

    match = df[
        (df["latitude"]  == lat)  &
        (df["longitude"] == lon)  &
        (df["zoom"]      == zoom)
    ]

    if match.empty:
        return False

    return os.path.exists(_image_path(lat, lon, zoom))


def load_cached_result(lat: float, lon: float, zoom: int) -> dict[str, Any] | None:
    """
    Load a cached pipeline result by coordinates and zoom level.

    Parameters
    ----------
    lat : float
        Latitude coordinate.
    lon : float
        Longitude coordinate.
    zoom : int
        Zoom level.

    Returns
    -------
    dict[str, Any] | None
        Dictionary containing the cached pipeline result with keys:
        timestamp, latitude, longitude, zoom, image_path, image_prompt,
        image_model, image_description, text_prompt, text_model,
        text_description, and danger. Returns None if no result exists
        for the given coordinates and zoom level.
    """
    if not os.path.exists(CSV_PATH):
        return None

    df = pd.read_csv(CSV_PATH)
    match = df[
        (df["latitude"]  == lat)  &
        (df["longitude"] == lon)  &
        (df["zoom"]      == zoom)
    ]

    if match.empty:
        return None

    row = match.iloc[-1].to_dict()
    row["image_path"] = _image_path(lat, lon, zoom)
    return row


def save_run(
    lat: float,
    lon: float,
    zoom: int,
    source_image_path: str,
    image_prompt: str,
    image_model: str,
    image_description: str,
    text_prompt: str,
    text_model: str,
    text_description: str,
    danger: bool | str,
) -> dict[str, Any]:
    """
    Persist a completed pipeline run to the database.

    Appends a new row to the images.csv file with the pipeline results.
    The image file persistence is handled upstream by the caller.

    Parameters
    ----------
    lat : float
        Latitude coordinate.
    lon : float
        Longitude coordinate.
    zoom : int
        Zoom level.
    source_image_path : str
        Original image file path (for reference; actual image persistence
        is handled upstream).
    image_prompt : str
        Prompt used for image generation.
    image_model : str
        Name of the image generation model.
    image_description : str
        Generated image description from AI model.
    text_prompt : str
        Prompt used for text analysis.
    text_model : str
        Name of the text analysis model.
    text_description : str
        Generated text description from AI model.
    danger : bool | str
        Danger assessment. If bool, True→'DANGER', False→'SAFE'.
        If str, converted to uppercase.

    Returns
    -------
    dict[str, Any]
        The created database row as a dictionary with keys:
        timestamp, latitude, longitude, zoom, image_path, image_prompt,
        image_model, image_description, text_prompt, text_model,
        text_description, and danger.
    """
    init_db()

    dest_image_path = _image_path(lat, lon, zoom)

    if isinstance(danger, bool):
        danger_value = "DANGER" if danger else "SAFE"
    else:
        danger_value = danger.strip().upper()

    row = {
        "timestamp":         datetime.now().isoformat(timespec="seconds"),
        "latitude":          lat,
        "longitude":         lon,
        "zoom":              zoom,
        "image_path":        dest_image_path,
        "image_prompt":      image_prompt,
        "image_model":       image_model,
        "image_description": image_description,
        "text_prompt":       text_prompt,
        "text_model":        text_model,
        "text_description":  text_description,
        "danger":            danger_value,
    }

    pd.DataFrame([row]).to_csv(CSV_PATH, mode="a", header=False, index=False)
    print(f"[DB] Saved run → lat={lat}, lon={lon}, zoom={zoom}, danger={danger}")
    return row                
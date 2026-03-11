"""
Project Okavango: Database Module

Handles all persistence for the AI pipeline on Page 2:
- Initializes the images.csv database
- Checks the cache before running the pipeline (keyed on lat + lon + zoom)
- Saves new pipeline results (CSV row + image file)
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
import shutil
from datetime import datetime


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

def load_models_config(config_path: str = None) -> dict:
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
    """Build a deterministic image filename. e.g. img_-3.0_-3.0_17.png"""
    return f"img_{lat}_{lon}_{zoom}.png"


def _image_path(lat: float, lon: float, zoom: int) -> str:
    """Full path to the image file for the given settings."""
    return os.path.join(IMAGES_DIR, _image_filename(lat, lon, zoom))


# ==========================================
# INIT
# ==========================================

def init_db() -> None:
    """
    Ensure the database directory and images.csv exist.
    Safe to call on every app start (idempotent).
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
    Check whether a result for this lat/lon/zoom already exists in the database.
    Returns True only if both the CSV row AND the image file exist.
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


def load_cached_result(lat: float, lon: float, zoom: int) -> dict | None:
    """
    Load a cached pipeline result. Returns None if no cache hit.
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
    danger: str,
) -> dict:
    """
    Append a completed pipeline run to the CSV and store the image.
    """
    init_db()

    dest_image_path = _image_path(lat, lon, zoom)
    if source_image_path != dest_image_path:
        shutil.copy2(source_image_path, dest_image_path)

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
        "danger":            danger.strip().upper(),
    }

    pd.DataFrame([row]).to_csv(CSV_PATH, mode="a", header=False, index=False)
    print(f"[DB] Saved run → lat={lat}, lon={lon}, zoom={zoom}, danger={danger}")
    return row                
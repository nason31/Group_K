"""AI backend module for satellite image analysis and environmental risk assessment.

This module provides functions for:
- Downloading satellite images from ESRI World Imagery
- Describing images using vision models (via Ollama)
- Assessing environmental risk from image descriptions
- Orchestrating the full AI analysis pipeline
"""

import importlib
import math
import os
from pathlib import Path
from typing import Any

import base64
import requests
import yaml


# Module-level cache for models.yaml
_config_cache: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """
    Load and cache the models.yaml configuration file.

    Returns the parsed YAML configuration as a dictionary.
    Caches the result after the first read to avoid repeated file I/O.

    Raises:
        FileNotFoundError: If models.yaml cannot be found.
        yaml.YAMLError: If models.yaml is not valid YAML.
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    config_path = Path(__file__).parent.parent / "models.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}"
        )

    with open(config_path, "r") as f:
        try:
            _config_cache = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(
                f"Failed to parse models.yaml: {e}"
            ) from e

    return _config_cache


def get_image(
    lat: float, lon: float, zoom: int, output_dir: str = "images",
    high_res: bool = True
) -> str:
    """
    Download a satellite image tile from ESRI World Imagery.

    Converts the given latitude, longitude, and zoom level to a bounding box,
    then downloads the corresponding satellite imagery from ESRI's World
    Imagery service. High resolution mode (default) requests larger output
    sizes for better image quality.

    Args:
        lat: Latitude in degrees (-90 to 90).
        lon: Longitude in degrees (-180 to 180).
        zoom: Zoom level (0-28). Higher values are more detailed.
        output_dir: Directory to save the image. Defaults to "images".
        high_res: If True (default), request 1024×1024 px images for higher
            quality. If False, use 512×512 px images.

    Returns:
        The absolute file path of the saved image.

    Raises:
        FileNotFoundError: If models.yaml cannot be read.
        RuntimeError: If the HTTP request fails (non-200 status).
        ValueError: If coordinates or zoom are out of valid range.
    """
    # Load configuration
    config = _load_config()

    # Use ESRI export endpoint for better quality control
    esri_export_url = (
        "https://server.arcgisonline.com/ArcGIS/rest/services"
        "/World_Imagery/MapServer/export"
    )

    # Convert lat/lon/zoom to Web Mercator bounding box
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    # Calculate tile size in meters at the given zoom level
    # Earth circumference in Web Mercator
    earth_circumference = 40075016.686

    # Map width at zoom level (in meters)
    map_width = earth_circumference / (2**zoom)

    # Tile size is 256 pixels, so calculate the ground distance
    tile_ground_size = map_width

    # Create a bounding box around the center point
    # (approximately 256x256 meter area at zoom 15)
    half_size = tile_ground_size / 2

    # Convert to Web Mercator coordinates
    merc_x = (lon_rad * earth_circumference) / (2 * math.pi)
    merc_y = (
        (math.log(math.tan(math.pi / 4 + lat_rad / 2)) * earth_circumference) /
        (2 * math.pi)
    )

    # Create bounding box
    bbox_min_x = merc_x - half_size
    bbox_max_x = merc_x + half_size
    bbox_min_y = merc_y - half_size
    bbox_max_y = merc_y + half_size

    # Request size in pixels
    output_size = 1024 if high_res else 512

    # Build the export request parameters
    params = {
        "bbox": f"{bbox_min_x},{bbox_min_y},{bbox_max_x},{bbox_max_y}",
        "size": f"{output_size},{output_size}",
        "dpi": 96,
        "format": "png",
        "f": "image",
    }

    # Download with User-Agent header to avoid 403s
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36"
        )
    }

    response = requests.get(
        esri_export_url, params=params, headers=headers, timeout=10
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to download image from {esri_export_url}: "
            f"HTTP {response.status_code}"
        )

    # Build output filename: replace '.' with '-' in coordinates
    lat_str = str(lat).replace(".", "-")
    lon_str = str(lon).replace(".", "-")
    filename = f"{lat_str}_{lon_str}_{zoom}.png"

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Save the image
    file_path = output_path / filename
    file_path.write_bytes(response.content)

    # Return absolute path
    return str(file_path.resolve())

def ensure_model(model_name: str) -> None:
    """
    Ensure an Ollama model is available locally.

    Args:
        model_name: Name of the Ollama model to verify locally.

    Raises:
        Any exception raised by the Ollama client while listing or pulling
            models.
    """
    ollama_module = importlib.import_module("ollama")
    models_response = ollama_module.list()
    available_models = {
        model["name"]
        for model in models_response.get("models", [])
        if isinstance(model, dict) and "name" in model
    }

    if model_name not in available_models:
        ollama_module.pull(model_name)

def describe_image(image_path: str) -> tuple[str, str, str]:
    """Send a satellite image to the configured vision model via Ollama.

    Loads the image model configuration from models.yaml, ensures the model
    is available locally, then sends the image to the model for analysis.

    Args:
        image_path: Absolute or relative path to the image file to analyse.

    Returns:
        A tuple of ``(model_name, prompt_used, description)`` where
        ``model_name`` is the Ollama model identifier, ``prompt_used`` is
        the prompt sent to the model, and ``description`` is the model's
        textual description of the image.

    Raises:
        FileNotFoundError: If ``image_path`` does not exist.
        RuntimeError: If the model returns an empty or null response.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    config = _load_config()
    image_cfg = config["image_model"]
    model_name: str = image_cfg["name"]
    prompt: str = image_cfg["prompt"]
    max_tokens: int = image_cfg["max_tokens"]

    ensure_model(model_name)

    image_bytes = path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    ollama_module = importlib.import_module("ollama")
    response = ollama_module.chat(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        options={"num_predict": max_tokens},
    )

    description: str = (
        response.get("message", {}).get("content", "").strip()
        if isinstance(response, dict)
        else getattr(
            getattr(response, "message", None), "content", ""
        ).strip()
    )

    if not description:
        raise RuntimeError(
            f"Vision model '{model_name}' returned an empty response."
        )

    return model_name, prompt, description


if __name__ == "__main__":
    # Smoke test: download an image of the Eiffel Tower area
    try:
        image_path = get_image(lat=48.85, lon=2.35, zoom=15)
        print(f"Success! Image saved to: {image_path}")
    except Exception as e:
        print(f"Error: {e}")

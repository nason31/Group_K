"""AI backend module for satellite image analysis and environmental risk assessment.

This module provides functions for:
- Downloading satellite images from ESRI World Imagery
- Describing images using vision models (via Ollama)
- Assessing environmental risk from image descriptions
- Orchestrating the full AI analysis pipeline
"""

import base64
import argparse
import importlib
import math
import time
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

import requests
import yaml

try:
    from app.db import check_cache, load_cached_result, save_run
except ModuleNotFoundError:
    from db import check_cache, load_cached_result, save_run


# Module-level cache for models.yaml
_config_cache: dict[str, Any] | None = None
_verified_models: set[str] = set()


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
    _ = config

    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude out of range [-90, 90]: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude out of range [-180, 180]: {lon}")
    if not (0 <= zoom <= 28):
        raise ValueError(f"Zoom out of range [0, 28]: {zoom}")

    # Web Mercator practical latitude limit to keep projection math stable.
    max_merc_lat = 85.05112878
    lat_clamped = max(min(lat, max_merc_lat), -max_merc_lat)

    # Use two equivalent ArcGIS hosts; some transient failures only hit one.
    esri_export_urls = [
        (
            "https://server.arcgisonline.com/ArcGIS/rest/services"
            "/World_Imagery/MapServer/export"
        ),
        (
            "https://services.arcgisonline.com/ArcGIS/rest/services"
            "/World_Imagery/MapServer/export"
        ),
    ]

    # Convert lat/lon/zoom to Web Mercator bounding box
    lat_rad = math.radians(lat_clamped)
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

    # Clamp bbox to valid EPSG:3857 extent.
    max_merc_extent = 20037508.342789244
    bbox_min_x = max(-max_merc_extent, min(max_merc_extent, bbox_min_x))
    bbox_max_x = max(-max_merc_extent, min(max_merc_extent, bbox_max_x))
    bbox_min_y = max(-max_merc_extent, min(max_merc_extent, bbox_min_y))
    bbox_max_y = max(-max_merc_extent, min(max_merc_extent, bbox_max_y))

    # Request size in pixels
    output_size = 1024 if high_res else 512

    # Build the export request parameters
    params = {
        "bbox": f"{bbox_min_x},{bbox_min_y},{bbox_max_x},{bbox_max_y}",
        "size": f"{output_size},{output_size}",
        "bboxSR": 3857,
        "imageSR": 3857,
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

    errors: list[str] = []
    response: requests.Response | None = None

    # Retry transient failures per host before falling back to the next host.
    for esri_export_url in esri_export_urls:
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    esri_export_url, params=params, headers=headers, timeout=10
                )

                if response.status_code == 200 and response.content:
                    break

                errors.append(
                    f"{esri_export_url} attempt {attempt}: HTTP {response.status_code}"
                )
            except requests.RequestException as exc:
                errors.append(
                    f"{esri_export_url} attempt {attempt}: {type(exc).__name__}: {exc}"
                )

            # Simple exponential backoff for transient upstream issues.
            time.sleep(0.5 * (2 ** (attempt - 1)))

        if response is not None and response.status_code == 200 and response.content:
            break

    if response is None or response.status_code != 200 or not response.content:
        error_summary = " | ".join(errors[-6:]) if errors else "no response details"
        raise RuntimeError(
            "Failed to download image from ArcGIS World Imagery after retries. "
            f"Details: {error_summary}"
        )

    # Build output filename: replace '.' with '-' in coordinates
    lat_str = str(lat).replace(".", "-")
    lon_str = str(lon).replace(".", "-")
    filename = f"img_{lat_str}_{lon_str}_{zoom}.png"

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
        RuntimeError: If Ollama is not accessible or the model pull fails.
    """
    if model_name in _verified_models:
        print(f"[ensure_model] model '{model_name}' already verified in this session")
        return

    print(f"[ensure_model] checking model: {model_name}")
    ollama_module = importlib.import_module("ollama")
    try:
        # Use a short timeout for quick connectivity/list checks.
        print("[ensure_model] connecting to Ollama at localhost:11434")
        list_client = ollama_module.Client(timeout=10.0)
        models_response = list_client.list()
    except Exception as e:
        raise RuntimeError(
            f"Cannot connect to Ollama. Ensure Ollama is running on "
            f"localhost:11434. Error: {e}"
        ) from e

    # Extract model names from the response (handles both dict and object formats)
    raw_models = []
    if hasattr(models_response, "models"):
        raw_models = models_response.models
    elif isinstance(models_response, dict):
        raw_models = models_response.get("models", [])

    available_models: set[str] = set()
    for model in raw_models:
        if isinstance(model, dict):
            name = model.get("name") or model.get("model")
        else:
            name = getattr(model, "name", None) or getattr(model, "model", None)

        if isinstance(name, str) and name:
            available_models.add(name)

    print(
        f"[ensure_model] found {len(available_models)} local model(s): "
        f"{sorted(available_models)}"
    )

    if model_name not in available_models:
        try:
            print(f"[ensure_model] model '{model_name}' not found locally; pulling...")
            # Pull can take minutes depending on model size/network speed.
            pull_client = ollama_module.Client(timeout=1800.0)
            pull_client.pull(model_name)
            print(f"[ensure_model] pull complete for model '{model_name}'")
        except Exception as e:
            raise RuntimeError(
                f"Failed to pull model '{model_name}': {e}"
            ) from e
    else:
        print(f"[ensure_model] model '{model_name}' already available locally")

    _verified_models.add(model_name)

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
    try:
        # Create client with 120-second timeout for long-running inference
        client = ollama_module.Client(timeout=1200.0)
        response = client.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            options={"num_predict": max_tokens},
            stream=False,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to get image description from model '{model_name}'. "
            f"Ensure Ollama is running. Error: {e}"
        ) from e

    # Extract description from response (handle Pydantic models)
    description: str = ""
    if hasattr(response, "message"):
        # Pydantic model response
        if hasattr(response.message, "content"):
            description = response.message.content.strip()
        elif isinstance(response.message, dict):
            description = response.message.get("content", "").strip()
    elif isinstance(response, dict):
        # Dict response
        msg = response.get("message", {})
        if isinstance(msg, dict):
            description = msg.get("content", "").strip()
        else:
            description = getattr(msg, "content", "").strip()

    if not description:
        raise RuntimeError(
            f"Vision model '{model_name}' returned an empty response."
        )

    return model_name, prompt, description

def assess_risk(description: str) -> tuple[str, str, str, bool]:
    """
    Sends the image description to a second Ollama text model.
    The model generates environmental risk questions and answers them,
    then returns an overall verdict.

    Args:
        description: Textual description of a satellite image produced by
            ``describe_image()``.

    Returns:
        A tuple of ``(model_name, prompt_used, full_response, is_danger)``
        where ``is_danger`` is ``True`` if the model concluded DANGER,
        ``False`` for SAFE.

    Raises:
        RuntimeError: If the model returns an empty or null response.
    """
    config = _load_config()
    text_cfg = config["text_model"]
    model_name: str = text_cfg["name"]
    base_prompt: str = text_cfg["prompt"]
    max_tokens: int = text_cfg["max_tokens"]

    ensure_model(model_name)

    full_prompt = f"{base_prompt}\n\n{description}"

    ollama_module = importlib.import_module("ollama")
    try:
        client = ollama_module.Client(timeout=1200.0)
        response = client.chat(
            model=model_name,
            messages=[{"role": "user", "content": full_prompt}],
            # think=False disables Qwen3's extended thinking mode so that
            # the answer appears in message.content rather than being
            # silently routed to message.thinking.
            options={"num_predict": max_tokens},
            think=False,
            stream=False,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to get risk assessment from model '{model_name}'. "
            f"Ensure Ollama is running. Error: {e}"
        ) from e

    # Extract response text (handle both Pydantic models and plain dicts).
    # Qwen3 thinking models may return an empty content field while the
    # actual response sits in message.thinking; check both fields.
    def _extract_text(msg: Any) -> str:
        if isinstance(msg, dict):
            return (
                msg.get("content") or msg.get("thinking") or ""
            ).strip()
        return (
            getattr(msg, "content", None)
            or getattr(msg, "thinking", None)
            or ""
        ).strip()

    full_response: str = ""
    if hasattr(response, "message"):
        full_response = _extract_text(response.message)
    elif isinstance(response, dict):
        full_response = _extract_text(response.get("message", {}))

    if not full_response:
        raise RuntimeError(
            f"Text model '{model_name}' returned an empty response."
        )

    is_danger: bool = "danger" in full_response.lower()

    return model_name, full_prompt, full_response, is_danger

def run_pipeline(
    lat: float,
    lon: float,
    zoom: int,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the full AI workflow for a single map location.

    This orchestration function:
    1. Downloads a satellite image for the given coordinates.
    2. Generates an image description with the configured vision model.
    3. Assesses environmental risk using the configured text model.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        zoom: Web map zoom level.

    Returns:
        A dictionary containing all pipeline outputs, ready for logging
        and frontend display.
    """
    def _emit(message: str) -> None:
        if progress_callback is not None:
            try:
                progress_callback(message)
            except Exception:
                # UI callback errors should not break the core pipeline.
                pass

    started_at = time.perf_counter()
    timings: dict[str, float] = {}

    _emit("Checking cache...")
    cache_started = time.perf_counter()
    if check_cache(lat, lon, zoom):
        cached_result = load_cached_result(lat, lon, zoom)
        if cached_result is not None:
            timings["cache_seconds"] = round(time.perf_counter() - cache_started, 3)
            timings["total_seconds"] = round(time.perf_counter() - started_at, 3)
            _emit("Loaded cached result.")
            return {
                **cached_result,
                "from_cache": True,
                "timings": timings,
            }
    timings["cache_seconds"] = round(time.perf_counter() - cache_started, 3)

    _emit("Downloading satellite image...")
    image_started = time.perf_counter()
    image_path = get_image(lat, lon, zoom)

    timings["image_download_seconds"] = round(time.perf_counter() - image_started, 3)

    _emit("Running vision model...")
    vision_started = time.perf_counter()
    image_model, image_prompt, image_description = describe_image(image_path)

    timings["vision_inference_seconds"] = round(time.perf_counter() - vision_started, 3)

    _emit("Running risk assessment model...")
    risk_started = time.perf_counter()
    text_model, text_prompt, text_description, danger = assess_risk(
        image_description
    )

    timings["risk_inference_seconds"] = round(time.perf_counter() - risk_started, 3)

    _emit("Saving pipeline result...")
    save_started = time.perf_counter()
    saved_run = save_run(
        lat=lat,
        lon=lon,
        zoom=zoom,
        source_image_path=image_path,
        image_prompt=image_prompt,
        image_model=image_model,
        image_description=image_description,
        text_prompt=text_prompt,
        text_model=text_model,
        text_description=text_description,
        danger=danger,
    )

    timings["save_seconds"] = round(time.perf_counter() - save_started, 3)
    timings["total_seconds"] = round(time.perf_counter() - started_at, 3)
    _emit("Pipeline complete.")

    return {
        **saved_run,
        "from_cache": False,
        "timings": timings,
        "image_path": image_path,
        "image_model": image_model,
        "image_prompt": image_prompt,
        "image_description": image_description,
        "text_model": text_model,
        "text_prompt": text_prompt,
        "text_description": text_description,
        "danger": danger,
    }


def _self_test_run_pipeline() -> None:
    """Run lightweight cache and persistence checks for ``run_pipeline``."""
    cached_result = {
        "latitude": 1.0,
        "longitude": 2.0,
        "zoom": 3,
        "image_path": "/tmp/cached.png",
        "danger": "SAFE",
    }

    with (
        patch("ai_backend.check_cache", return_value=True) as mock_check,
        patch(
            "ai_backend.load_cached_result", return_value=cached_result
        ) as mock_load,
        patch("ai_backend.get_image") as mock_get_image,
        patch("ai_backend.describe_image") as mock_describe,
        patch("ai_backend.assess_risk") as mock_assess,
        patch("ai_backend.save_run") as mock_save,
    ):
        result = run_pipeline(1.0, 2.0, 3)

        assert result == cached_result
        mock_check.assert_called_once_with(1.0, 2.0, 3)
        mock_load.assert_called_once_with(1.0, 2.0, 3)
        mock_get_image.assert_not_called()
        mock_describe.assert_not_called()
        mock_assess.assert_not_called()
        mock_save.assert_not_called()

    saved_result = {
        "timestamp": "2026-03-13T12:00:00",
        "latitude": 1.0,
        "longitude": 2.0,
        "zoom": 3,
        "image_path": "/tmp/generated.png",
        "image_prompt": "image prompt",
        "image_model": "vision-model",
        "image_description": "forest near river",
        "text_prompt": "text prompt",
        "text_model": "risk-model",
        "text_description": "SAFE",
        "danger": "SAFE",
    }

    with (
        patch("ai_backend.check_cache", return_value=False) as mock_check,
        patch(
            "ai_backend.get_image", return_value="/tmp/generated.png"
        ) as mock_get_image,
        patch(
            "ai_backend.describe_image",
            return_value=(
                "vision-model",
                "image prompt",
                "forest near river",
            ),
        ) as mock_describe,
        patch(
            "ai_backend.assess_risk",
            return_value=(
                "risk-model",
                "text prompt",
                "SAFE",
                False,
            ),
        ) as mock_assess,
        patch("ai_backend.save_run", return_value=saved_result) as mock_save,
    ):
        result = run_pipeline(1.0, 2.0, 3)

        mock_check.assert_called_once_with(1.0, 2.0, 3)
        mock_get_image.assert_called_once_with(1.0, 2.0, 3)
        mock_describe.assert_called_once_with("/tmp/generated.png")
        mock_assess.assert_called_once_with("forest near river")
        mock_save.assert_called_once_with(
            lat=1.0,
            lon=2.0,
            zoom=3,
            source_image_path="/tmp/generated.png",
            image_prompt="image prompt",
            image_model="vision-model",
            image_description="forest near river",
            text_prompt="text prompt",
            text_model="risk-model",
            text_description="SAFE",
            danger=False,
        )
        assert result["timestamp"] == saved_result["timestamp"]
        assert result["image_path"] == "/tmp/generated.png"
        assert result["danger"] is False
        assert result["text_description"] == "SAFE"

    print("run_pipeline self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run ai_backend self-test or the full pipeline."
    )
    parser.add_argument("--lat", type=float, help="Latitude for pipeline run")
    parser.add_argument("--lon", type=float, help="Longitude for pipeline run")
    parser.add_argument("--zoom", type=int, help="Zoom level for pipeline run")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run lightweight run_pipeline tests without calling external services.",
    )
    args = parser.parse_args()

    if args.self_test:
        _self_test_run_pipeline()
    elif None not in (args.lat, args.lon, args.zoom):
        print(run_pipeline(args.lat, args.lon, args.zoom))
    else:
        parser.print_help()
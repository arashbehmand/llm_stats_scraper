import logging
from datetime import datetime, timedelta, timezone

import requests

# Models listed on OpenRouter within this window are flagged as new listings.
NEW_LISTING_LOOKBACK_HOURS = 48
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/frontend/models"


def _parse_openrouter_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fetch_openrouter_model_catalog():
    try:
        response = requests.get(
            OPENROUTER_MODELS_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        models = data.get("data", data) if isinstance(data, dict) else data
        return models if isinstance(models, list) else []
    except Exception as e:
        logging.warning(f"OpenRouter: Failed to fetch model catalog: {e}")
        return []


def _fetch_new_openrouter_models(models=None):
    try:
        models = models if models is not None else _fetch_openrouter_model_catalog()
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=NEW_LISTING_LOOKBACK_HOURS
        )
        new_models = []

        for model in models:
            if not isinstance(model, dict) or model.get("hidden"):
                continue

            created_at = _parse_openrouter_timestamp(
                model.get("created_at") or model.get("createdAt")
            )
            if created_at and created_at >= cutoff:
                new_models.append(model)

        logging.info(
            f"OpenRouter new listings: {len(new_models)} models created in last "
            f"{NEW_LISTING_LOOKBACK_HOURS}h."
        )
        return new_models
    except Exception as e:
        logging.warning(f"OpenRouter: Failed to fetch new model listings: {e}")
        return []


def _new_listing_rows(new_models):
    rows = []
    for model in new_models:
        if model.get("hidden"):
            continue
        rows.append(
            {
                "model": model.get("name")
                or model.get("permaslug")
                or model.get("slug"),
                "rank": None,
                "score": 0.0,
                "source": "openrouter_new",
                "details": {
                    "slug": model.get("permaslug") or model.get("slug"),
                    "base_slug": model.get("slug"),
                    "is_new_listing": True,
                    "created_at": model.get("created_at") or model.get("createdAt"),
                    "updated_at": model.get("updated_at") or model.get("updatedAt"),
                    "author": model.get("author"),
                    "context_length": model.get("context_length"),
                    "description": (model.get("description") or "")[:200],
                    "input_modalities": model.get("input_modalities"),
                    "output_modalities": model.get("output_modalities"),
                    "supports_reasoning": model.get("supports_reasoning"),
                    "usage_metric_key": "new_listing",
                },
            }
        )
    return rows


def scrape_openrouter():
    """Return recent OpenRouter model listings only."""
    try:
        model_catalog = _fetch_openrouter_model_catalog()
        new_models = _fetch_new_openrouter_models(model_catalog)
        rows = _new_listing_rows(new_models)
        logging.info(f"OpenRouter: Extracted {len(rows)} new listing rows.")
        return rows
    except Exception as e:
        logging.error(f'Error scraping OpenRouter: {e}"')
        return []

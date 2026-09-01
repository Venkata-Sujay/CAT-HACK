"""Model artifact registry.

Loaded once at application startup. If an artifact is missing the app still
boots -- it degrades to rules-only intelligence and says exactly which script to
run. A missing model must never be a 500 on the dashboard.

Artifacts are produced by the scripts under ``ml/`` and are NOT committed as
build outputs of the app; see PROJECT_STATE.md -> How to Run.
"""

import logging
from pathlib import Path
from typing import Any

import joblib

from app.config import settings

logger = logging.getLogger("rental.ml")


class ModelRegistry:
    """Holds the trained artifacts and their metadata."""

    def __init__(self) -> None:
        self.anomaly_bundle: dict[str, Any] | None = None
        self.demand_bundle: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    @property
    def anomaly_ready(self) -> bool:
        return self.anomaly_bundle is not None

    @property
    def demand_ready(self) -> bool:
        return self.demand_bundle is not None

    @property
    def anomaly_model(self):
        return self.anomaly_bundle.get("model") if self.anomaly_bundle else None

    @property
    def demand_model(self):
        return self.demand_bundle.get("model") if self.demand_bundle else None

    # ------------------------------------------------------------------
    def _load_one(self, filename: str, label: str) -> dict[str, Any] | None:
        path = Path(settings.ML_ARTIFACTS_DIR) / filename
        if not path.exists():
            logger.warning("%s artifact not found at %s", label, path)
            return None
        try:
            bundle = joblib.load(path)
        except Exception:  # noqa: BLE001 - a corrupt artifact must not stop boot
            logger.exception("Failed to load %s artifact from %s", label, path)
            return None

        meta = bundle.get("metadata", {}) if isinstance(bundle, dict) else {}
        logger.info(
            "Loaded %s model  version=%s  trained_at=%s  rows=%s",
            label,
            meta.get("model_version", "?"),
            meta.get("trained_at", "?"),
            meta.get("training_rows", "?"),
        )
        return bundle

    def load(self) -> None:
        self.anomaly_bundle = self._load_one(settings.ANOMALY_MODEL_FILE, "anomaly")
        self.demand_bundle = self._load_one(settings.DEMAND_MODEL_FILE, "demand")

    def reload(self) -> None:
        """Re-read artifacts from disk -- lets a retrain take effect without a restart."""
        self.load()

    def metadata(self) -> dict[str, Any]:
        return {
            "anomaly": (self.anomaly_bundle or {}).get("metadata"),
            "demand": (self.demand_bundle or {}).get("metadata"),
        }


model_registry = ModelRegistry()

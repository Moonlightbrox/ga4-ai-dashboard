"""BigQuery client + credential helpers.

Owns:
    * Lazy import of ``google.cloud.bigquery`` so the rest of the backend can
      run without it installed (CI, lint, fresh checkouts).
    * Loading the platform service-account key with the right BigQuery scopes.
    * Cached BigQuery ``Client`` per ``project:location``.
    * Resolving a GA4 property id to its export dataset reference.
"""

from __future__ import annotations

import json
import os
from typing import Any

from google.oauth2 import service_account


# Full ``bigquery`` scope: needed because every query (including SELECTs) is
# submitted as a Job, which the read-only scope cannot create. Real access is
# still constrained by the SA's IAM roles (jobUser + dataViewer).
_BQ_SCOPES = ("https://www.googleapis.com/auth/bigquery",)


def _import_bigquery():
    """Lazy import of ``google.cloud.bigquery`` with a friendly error.

    Raises ``ValueError`` (not ImportError) so callers' generic config-error
    catch already covers it.
    """
    try:
        from google.cloud import bigquery as _bigquery
    except ImportError as exc:  # pragma: no cover - exercised by operators
        raise ValueError(
            "google-cloud-bigquery is not installed. Run "
            "`pip install -r backend/requirements.txt`."
        ) from exc
    return _bigquery


def _load_bq_credentials() -> service_account.Credentials:
    """Load the platform service account with BigQuery scope.

    Re-uses the same env keys as the GA4 link setup
    (``GA4_LINK_SERVICE_ACCOUNT_JSON`` / ``GA4_LINK_SERVICE_ACCOUNT_FILE`` /
    ``GOOGLE_APPLICATION_CREDENTIALS``).
    """
    key_json = os.getenv("GA4_LINK_SERVICE_ACCOUNT_JSON", "").strip()
    if key_json:
        try:
            info = json.loads(key_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "GA4_LINK_SERVICE_ACCOUNT_JSON is not valid JSON."
            ) from exc
        return service_account.Credentials.from_service_account_info(
            info, scopes=_BQ_SCOPES
        )

    key_path = os.getenv("GA4_LINK_SERVICE_ACCOUNT_FILE") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if not key_path or not os.path.isfile(key_path):
        raise ValueError(
            "Set GA4_LINK_SERVICE_ACCOUNT_JSON, GA4_LINK_SERVICE_ACCOUNT_FILE, "
            "or GOOGLE_APPLICATION_CREDENTIALS to a service account key."
        )
    return service_account.Credentials.from_service_account_file(
        key_path, scopes=_BQ_SCOPES
    )


def get_project_id() -> str:
    project = os.getenv("GA4_EXPORT_GCP_PROJECT_ID", "").strip()
    if not project:
        raise ValueError("GA4_EXPORT_GCP_PROJECT_ID is not set.")
    return project


def get_dataset_location() -> str:
    return os.getenv("GA4_BQ_DATASET_LOCATION", "US").strip() or "US"


_CLIENT_CACHE: dict[str, Any] = {}


def get_bq_client() -> Any:
    """Return a cached BigQuery client for the configured project + location.

    Cache key includes project + location so an env change at runtime (e.g. in
    tests) yields a fresh client instead of silently reusing a stale one.
    """
    bq = _import_bigquery()
    project = get_project_id()
    location = get_dataset_location()
    cache_key = f"{project}:{location}"
    client = _CLIENT_CACHE.get(cache_key)
    if client is None:
        credentials = _load_bq_credentials()
        client = bq.Client(
            credentials=credentials,
            project=project,
            location=location,
        )
        _CLIENT_CACHE[cache_key] = client
    return client


def _normalize_property_id(property_id: str) -> str:
    """Strip a ``properties/`` prefix and surrounding whitespace.

    GA4's BigQuery export dataset is always ``analytics_<numericId>`` -- never
    ``analytics_properties/<id>`` -- so we have to peel the resource-name form
    if a session ever stored it accidentally.
    """
    if not property_id:
        raise ValueError("property_id is required.")
    normalized = property_id.strip().strip("/")
    if normalized.lower().startswith("properties/"):
        normalized = normalized.split("/", 1)[1].strip("/")
    if not normalized:
        raise ValueError("property_id is empty after normalization.")
    return normalized


def resolve_dataset_ref(property_id: str) -> str:
    """Return ``<gcp_project>.analytics_<property_id>`` for a GA4 property."""
    normalized = _normalize_property_id(property_id)
    return f"{get_project_id()}.analytics_{normalized}"

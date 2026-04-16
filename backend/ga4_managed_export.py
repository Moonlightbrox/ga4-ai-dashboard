# Managed GA4 → BigQuery export: grant platform service account on the property, then create the BigQuery link.
# Uses Analytics Admin API v1alpha (accessBindings, bigQueryLinks).

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient
from google.analytics.admin_v1alpha.types import (
    AccessBinding,
    BigQueryLink,
    CreateAccessBindingRequest,
    CreateBigQueryLinkRequest,
)
from google.api_core import exceptions as gexc
from google.auth.credentials import Credentials
from google.oauth2 import service_account

# Scopes required for the service account when calling create_big_query_link.
_SA_SCOPES = ("https://www.googleapis.com/auth/analytics.edit",)

GA4_PREDEFINED_EDITOR = "predefinedRoles/editor"

# Returned as API detail when GA4 rejects add-user (OAuth user lacks property admin).
PERMISSION_DENIED_GRANT_HELP = (
    "Your Google account does not have permission to add users to this GA4 property. "
    "In Google Analytics: Admin → Property access management — you need the Administrator role "
    "(or another role that includes managing users) on this property. "
    "Sign in with that account, or ask the property owner to grant it, then use Reconnect and try again."
)


def _load_service_account_credentials() -> service_account.Credentials:
    key_json = os.getenv("GA4_LINK_SERVICE_ACCOUNT_JSON", "").strip()
    if key_json:
        try:
            info = json.loads(key_json)
            email = info.get("client_email")
            logging.info(f"Loading service account credentials from JSON env var: {email}")
        except json.JSONDecodeError as exc:
            raise ValueError("GA4_LINK_SERVICE_ACCOUNT_JSON is not valid JSON.") from exc
        return service_account.Credentials.from_service_account_info(
            info, scopes=_SA_SCOPES
        )

    key_path = os.getenv("GA4_LINK_SERVICE_ACCOUNT_FILE") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if not key_path or not os.path.isfile(key_path):
        raise ValueError(
            "Set GA4_LINK_SERVICE_ACCOUNT_JSON, GA4_LINK_SERVICE_ACCOUNT_FILE, or GOOGLE_APPLICATION_CREDENTIALS."
        )
    logging.info(f"Loading service account credentials from file: {key_path}")
    return service_account.Credentials.from_service_account_file(
        key_path, scopes=_SA_SCOPES
    )


def get_link_config() -> dict[str, str]:
    """Read GCP project id, dataset location, and connector SA email from the environment."""
    gcp_project = os.getenv("GA4_EXPORT_GCP_PROJECT_ID", "").strip()
    dataset_location = os.getenv("GA4_BQ_DATASET_LOCATION", "US").strip()
    sa_email = os.getenv("GA4_LINK_SERVICE_ACCOUNT_EMAIL", "").strip()
    if not gcp_project:
        raise ValueError("GA4_EXPORT_GCP_PROJECT_ID is not set.")
    if not sa_email:
        raise ValueError("GA4_LINK_SERVICE_ACCOUNT_EMAIL is not set.")
    return {
        "gcp_project_id": gcp_project,
        "dataset_location": dataset_location,
        "service_account_email": sa_email,
    }


def grant_service_account_property_access(
    user_credentials: Credentials,
    property_id: str,
    service_account_email: str,
) -> dict[str, Any]:
    """
    Add the platform service account to the GA4 property with Editor (via OAuth user with manage.users).
    Idempotent: treats AlreadyExists as success.
    """
    client = AnalyticsAdminServiceClient(credentials=user_credentials)
    parent = f"properties/{property_id}"
    binding = AccessBinding(
        user=service_account_email,
        roles=[GA4_PREDEFINED_EDITOR],
    )
    try:
        created = client.create_access_binding(
            CreateAccessBindingRequest(parent=parent, access_binding=binding)
        )
        return {"status": "created", "name": created.name}
    except gexc.AlreadyExists:
        return {"status": "already_exists"}


def create_managed_bigquery_link(
    property_id: str,
    gcp_project_id: str,
    dataset_location: str,
    *,
    daily_export: bool = True,
    streaming_export: bool = False,
) -> dict[str, Any]:
    """
    Link the GA4 property to the given GCP project for BigQuery export (creates analytics_<property_id> dataset).
    Must be called with service account credentials that already have Editor on the property.
    """
    creds = _load_service_account_credentials()
    client = AnalyticsAdminServiceClient(credentials=creds)
    parent = f"properties/{property_id}"

    project_resource = (
        gcp_project_id
        if gcp_project_id.startswith("projects/")
        else f"projects/{gcp_project_id}"
    )

    link = BigQueryLink(
        project=project_resource,
        dataset_location=dataset_location,
        daily_export_enabled=daily_export,
        streaming_export_enabled=streaming_export,
    )

    logging.info(f"Attempting to create BigQuery link for property {property_id} to project {project_resource}")

    try:
        created = client.create_big_query_link(
            CreateBigQueryLinkRequest(parent=parent, bigquery_link=link)
        )
        logging.info(f"Successfully created BigQuery link: {created.name}")
        return {"status": "created", "name": created.name, "project": created.project}
    except gexc.AlreadyExists:
        logging.info(f"BigQuery link already exists for property {property_id}")
        return {"status": "already_exists"}
    except gexc.PermissionDenied as exc:
        # Log full details for debugging
        logging.error(f"PermissionDenied creating BigQuery link: {exc.message}. Details: {exc.details}")
        # Re-raise with message to be caught by main.py
        raise RuntimeError(f"GA4 Permission Denied: {exc.message}") from exc
    except Exception as exc:
        logging.error(f"Unexpected error creating BigQuery link: {exc}")
        raise


def list_bigquery_links_for_property(
    property_id: str,
) -> list[dict[str, Any]]:
    """List BigQuery links on the property (uses the same service account as create)."""
    creds = _load_service_account_credentials()
    client = AnalyticsAdminServiceClient(credentials=creds)
    parent = f"properties/{property_id}"
    out: list[dict[str, Any]] = []
    for bl in client.list_big_query_links(parent=parent):
        out.append(
            {
                "name": bl.name,
                "project": bl.project,
                "dataset_location": bl.dataset_location,
                "daily_export_enabled": bl.daily_export_enabled,
                "streaming_export_enabled": bl.streaming_export_enabled,
            }
        )
    return out

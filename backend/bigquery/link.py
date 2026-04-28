"""Managed GA4 -> BigQuery export link.

End-to-end flow:
    1. ``grant_service_account_property_access`` -- the OAuth user adds the
       platform service account as an Editor on the GA4 property.
    2. ``list_data_stream_names`` -- fetch every stream so the link actually
       exports event data.
    3. ``create_managed_bigquery_link`` -- the platform SA creates the GA4 ->
       BigQuery link (or heals an existing one's ``export_streams``).

Lives next to the rest of the BigQuery layer because what it produces (the
``analytics_<property_id>`` dataset and its ``events_*`` shards) is consumed by
:mod:`backend.bigquery.client` / :mod:`status` / :mod:`runner` and the
materializers.
"""

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
    UpdateBigQueryLinkRequest,
)
from google.api_core import exceptions as gexc
from google.auth.credentials import Credentials
from google.oauth2 import service_account
from google.protobuf import field_mask_pb2


# Service account scope for create_big_query_link.
_SA_SCOPES = ("https://www.googleapis.com/auth/analytics.edit",)

GA4_PREDEFINED_EDITOR = "predefinedRoles/editor"

# Surfaced as the API ``detail`` when the OAuth user is not a property admin.
PERMISSION_DENIED_GRANT_HELP = (
    "Your Google account does not have permission to add users to this GA4 property. "
    "In Google Analytics: Admin -> Property access management -- you need the Administrator role "
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
    """Read GCP project id, dataset location, and the connector SA email."""
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
    """Add the platform SA to the GA4 property with Editor.

    Idempotent: ``AlreadyExists`` is treated as success.
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


def list_data_stream_names(
    user_credentials: Credentials,
    property_id: str,
) -> list[str]:
    """Resource names of every data stream on the property.

    GA4 exports event data only for streams listed in ``export_streams``; we
    auto-select all of them so the ``events_*`` tables actually populate.
    """
    client = AnalyticsAdminServiceClient(credentials=user_credentials)
    parent = f"properties/{property_id}"
    names: list[str] = []
    for stream in client.list_data_streams(parent=parent):
        if stream.name:
            names.append(stream.name)
    return names


def create_managed_bigquery_link(
    property_id: str,
    gcp_project_id: str,
    dataset_location: str,
    *,
    daily_export: bool = True,
    streaming_export: bool = False,
    export_streams: list[str] | None = None,
) -> dict[str, Any]:
    """Create the GA4 -> BigQuery link, healing an existing one if present."""
    creds = _load_service_account_credentials()
    client = AnalyticsAdminServiceClient(credentials=creds)
    parent = f"properties/{property_id}"

    project_resource = (
        gcp_project_id
        if gcp_project_id.startswith("projects/")
        else f"projects/{gcp_project_id}"
    )

    streams = list(export_streams or [])

    link = BigQueryLink(
        project=project_resource,
        dataset_location=dataset_location,
        daily_export_enabled=daily_export,
        streaming_export_enabled=streaming_export,
        export_streams=streams,
    )

    logging.info(
        f"Attempting to create BigQuery link for property {property_id} to project "
        f"{project_resource} with {len(streams)} export stream(s)"
    )

    try:
        created = client.create_big_query_link(
            CreateBigQueryLinkRequest(parent=parent, bigquery_link=link)
        )
        logging.info(f"Successfully created BigQuery link: {created.name}")
        return {
            "status": "created",
            "name": created.name,
            "project": created.project,
            "export_streams": list(created.export_streams),
        }
    except gexc.AlreadyExists:
        logging.info(f"BigQuery link already exists for property {property_id}")
        repair = _ensure_export_streams_on_existing_link(
            client,
            property_id=property_id,
            project_resource=project_resource,
            desired_streams=streams,
        )
        return {"status": "already_exists", **repair}
    except gexc.InvalidArgument as exc:
        # GA4 sometimes returns INVALID_ARGUMENT instead of ALREADY_EXISTS for
        # the same condition. Treat the "already exists" variants as repair.
        message = (exc.message or "").lower()
        if "already exists" in message or "already linked" in message:
            logging.info(
                f"BigQuery link already exists for property {property_id} "
                f"(reported as InvalidArgument): {exc.message}"
            )
            repair = _ensure_export_streams_on_existing_link(
                client,
                property_id=property_id,
                project_resource=project_resource,
                desired_streams=streams,
            )
            return {"status": "already_exists", **repair}
        logging.error(f"InvalidArgument creating BigQuery link: {exc.message}")
        raise
    except gexc.PermissionDenied as exc:
        logging.error(f"PermissionDenied creating BigQuery link: {exc.message}. Details: {exc.details}")
        raise RuntimeError(f"GA4 Permission Denied: {exc.message}") from exc
    except Exception as exc:
        logging.error(f"Unexpected error creating BigQuery link: {exc}")
        raise


def _ensure_export_streams_on_existing_link(
    client: AnalyticsAdminServiceClient,
    *,
    property_id: str,
    project_resource: str,
    desired_streams: list[str],
) -> dict[str, Any]:
    """Patch an existing link so ``export_streams`` includes all desired streams.

    GA4 normalizes the returned ``project`` field to ``projects/<NUMBER>`` even
    when callers pass ``projects/<ID>``, so we don't filter by project equality
    -- a strict match would skip every existing link and the repair would no-op.
    """
    if not desired_streams:
        return {"export_streams": [], "export_streams_updated": False}

    parent = f"properties/{property_id}"
    try:
        existing = list(client.list_big_query_links(parent=parent))
    except Exception as exc:
        logging.warning(f"Could not list BigQuery links while repairing export_streams: {exc}")
        return {
            "export_streams": [],
            "export_streams_updated": False,
            "export_streams_update_error": f"list_big_query_links failed: {exc}",
        }

    if not existing:
        logging.warning(
            f"BigQuery link creation returned AlreadyExists for property {property_id} "
            f"but list_big_query_links returned no links -- cannot repair export_streams."
        )
        return {
            "export_streams": [],
            "export_streams_updated": False,
            "export_streams_update_error": (
                "No existing BigQuery links visible to the service account, so export_streams "
                "could not be updated."
            ),
        }

    def _project_matches(bl: BigQueryLink) -> bool:
        return (bl.project or "").endswith(project_resource.split("/")[-1])

    candidates = [bl for bl in existing if _project_matches(bl)] or existing

    patched_names: list[str] = []
    final_streams: list[str] = []
    errors: list[str] = []

    for link in candidates:
        current = list(link.export_streams or [])
        merged = sorted(set(current).union(desired_streams))

        if set(current) == set(merged):
            logging.info(
                f"BigQuery link {link.name} already has all desired export_streams "
                f"({len(current)}); nothing to patch."
            )
            final_streams = current
            continue

        link.export_streams.clear()
        link.export_streams.extend(merged)
        mask = field_mask_pb2.FieldMask(paths=["export_streams"])
        try:
            updated = client.update_big_query_link(
                UpdateBigQueryLinkRequest(bigquery_link=link, update_mask=mask)
            )
            logging.info(
                f"Patched existing BigQuery link {updated.name} with "
                f"{len(merged)} export stream(s) (was {len(current)})"
            )
            patched_names.append(updated.name)
            final_streams = list(updated.export_streams)
        except gexc.PermissionDenied as exc:
            msg = (
                f"PermissionDenied updating BigQuery link {link.name}: {exc.message}. "
                "The platform service account likely needs the GA4 property Administrator role "
                "(Editor is not sufficient for updating BigQuery links)."
            )
            logging.error(msg)
            errors.append(msg)
        except Exception as exc:
            msg = f"Could not update export_streams on BigQuery link {link.name}: {exc}"
            logging.error(msg)
            errors.append(msg)

    return {
        "name": patched_names[0] if patched_names else candidates[0].name,
        "export_streams": final_streams,
        "export_streams_updated": bool(patched_names),
        **({"export_streams_update_error": "; ".join(errors)} if errors else {}),
    }


def list_bigquery_links_for_property(property_id: str) -> list[dict[str, Any]]:
    """List BigQuery links on the property (uses the platform SA)."""
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
                "export_streams": list(bl.export_streams),
            }
        )
    return out

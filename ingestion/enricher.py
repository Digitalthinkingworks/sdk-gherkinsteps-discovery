# ingestion/enricher.py

import os
import logging
import requests
from config.settings import enrichment_config, is_enrichment_enabled

logger = logging.getLogger(__name__)


def enrich_sdk_metadata(sdk_name: str, sdk_version: str) -> dict:
    """
    Fetch additional metadata for an SDK from enabled external sources.
    Returns a dict merged into the StepDocument metadata.
    Only runs for sources where enabled=true in config.
    """
    extra = {}

    if is_enrichment_enabled("jfrog"):
        extra.update(_fetch_jfrog_metadata(sdk_name, sdk_version))

    if is_enrichment_enabled("confluence"):
        extra.update(_fetch_confluence_metadata(sdk_name))

    if is_enrichment_enabled("sharepoint"):
        extra.update(_fetch_sharepoint_metadata(sdk_name))

    return extra


def _fetch_jfrog_metadata(sdk_name: str, sdk_version: str) -> dict:
    """
    Fetch artifact metadata from JFrog Artifactory.
    Returns: latest_version, artifact_url, last_modified.
    """
    cfg      = enrichment_config("jfrog")
    base_url = cfg.get("base_url", "")
    repo_key = cfg.get("repo_key", "libs-release")
    token    = os.getenv("JFROG_TOKEN", "")
    timeout  = cfg.get("timeout_seconds", 10)

    if not base_url or not token:
        logger.warning("[JFrog] base_url or JFROG_TOKEN not set — skipping")
        return {}

    # JFrog AQL query to find latest version of the artifact
    aql = (
        f'items.find({{'
        f'"repo":"{repo_key}",'
        f'"name":"{sdk_name}*.jar"'
        f'}}).sort({{"$desc":["created"]}}).limit(1)'
    )
    try:
        resp = requests.post(
            f"{base_url}/api/search/aql",
            data=aql,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "text/plain",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            item = results[0]
            return {
                "jfrog_latest_version": item.get("version", sdk_version),
                "jfrog_artifact_url":   f"{base_url}/{repo_key}/{item.get('path', '')}",
                "jfrog_last_modified":  item.get("modified", ""),
            }
    except Exception as e:
        logger.warning(f"[JFrog] metadata fetch failed for {sdk_name}: {e}")
    return {}


def _fetch_confluence_metadata(sdk_name: str) -> dict:
    """
    Search Confluence for pages related to the SDK.
    Returns: doc_url, doc_title, doc_excerpt.
    """
    cfg      = enrichment_config("confluence")
    base_url = cfg.get("base_url", "")
    token    = os.getenv("CONFLUENCE_TOKEN", "")
    username = os.getenv("CONFLUENCE_USERNAME", "")
    spaces   = cfg.get("space_keys", [])
    timeout  = cfg.get("timeout_seconds", 15)

    if not base_url or not token:
        logger.warning("[Confluence] base_url or CONFLUENCE_TOKEN not set — skipping")
        return {}

    space_filter = " OR ".join(f'space="{s}"' for s in spaces) if spaces else "type=page"
    cql = f'text~"{sdk_name}" AND ({space_filter}) ORDER BY lastmodified DESC'

    try:
        resp = requests.get(
            f"{base_url}/rest/api/content/search",
            params={"cql": cql, "limit": 1, "expand": "excerpt"},
            auth=(username, token),
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            page = results[0]
            return {
                "confluence_doc_title":   page.get("title", ""),
                "confluence_doc_url":     f"{base_url}{page.get('_links', {}).get('webui', '')}",
                "confluence_doc_excerpt": page.get("excerpt", ""),
            }
    except Exception as e:
        logger.warning(f"[Confluence] metadata fetch failed for {sdk_name}: {e}")
    return {}


def _fetch_sharepoint_metadata(sdk_name: str) -> dict:
    """
    Search SharePoint for documents related to the SDK.
    Uses Microsoft Graph API with client credentials flow.
    Returns: doc_url, doc_title.
    """
    cfg           = enrichment_config("sharepoint")
    site_url      = cfg.get("site_url", "")
    client_id     = os.getenv("SHAREPOINT_CLIENT_ID", "")
    client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET", "")
    tenant_id     = os.getenv("SHAREPOINT_TENANT_ID", "")
    timeout       = cfg.get("timeout_seconds", 20)

    if not all([site_url, client_id, client_secret, tenant_id]):
        logger.warning("[SharePoint] credentials not fully set — skipping")
        return {}

    try:
        # Get access token
        token_resp = requests.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
                "scope":         "https://graph.microsoft.com/.default",
            },
            timeout=timeout,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        # Search for SDK-related documents
        search_resp = requests.post(
            "https://graph.microsoft.com/v1.0/search/query",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"requests": [{"entityTypes": ["driveItem"], "query": {"queryString": sdk_name}, "size": 1}]},
            timeout=timeout,
        )
        search_resp.raise_for_status()
        hits = (search_resp.json()
                .get("value", [{}])[0]
                .get("hitsContainers", [{}])[0]
                .get("hits", []))
        if hits:
            resource = hits[0].get("resource", {})
            return {
                "sharepoint_doc_title": resource.get("name", ""),
                "sharepoint_doc_url":   resource.get("webUrl", ""),
            }
    except Exception as e:
        logger.warning(f"[SharePoint] metadata fetch failed for {sdk_name}: {e}")
    return {}
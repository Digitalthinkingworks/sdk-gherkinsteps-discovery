# ingestion/pipeline.py

import logging

from ingestion.enricher import enrich_sdk_metadata
from ingestion.crawler import LocalCrawler, GitHubCrawler
from ingestion.parser  import JavaStepsParser, StepDocument

from config.vectordb_factory import get_collection
from config.model_factory import embed_texts
from config.settings import get as cfg_get, crawler_mode as config_crawler_mode


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    return embed_texts(texts)


def run_pipeline(
    crawler_mode: str = "local",
    sdk_config:   dict | None = None,
    batch_size:   int = 32,
) -> dict:
    """
    Full ingestion pipeline: crawl → parse → embed → upsert to Chroma.

    Returns a summary dict with counts for logging / testing.
    """
    # ── 1. Crawl ──────────────────────────────────────────────────────
    mode = config_crawler_mode() or crawler_mode
    if mode == "local":
        crawler = LocalCrawler(sdk_config=sdk_config)
    else:
        crawler = GitHubCrawler(sdk_config=sdk_config)

    feature_files = crawler.crawl()
    if not feature_files:
        logger.warning("No .java files found. Check your root_dir or repo list.")
        return {"files": 0, "step_documents": 0, "upserted": 0}

    # ── 2. Parse ──────────────────────────────────────────────────────
    parser    = JavaStepsParser()
    all_docs: list[StepDocument] = []

    for ff in feature_files:
        try:
            docs = parser.parse(
                java_source          = ff.content,
                sdk_name             = ff.sdk_name,
                sdk_version          = ff.sdk_version,
                step_definition_file = ff.relative_path,
                github_url           = ff.github_url,
            )
            # Enrich each doc's metadata with JFrog/Confluence data
            extra_meta = enrich_sdk_metadata(ff.sdk_name, ff.sdk_version)
            if extra_meta:
                for doc in docs:
                    doc.__dict__.update(extra_meta)  # attach enriched fields
            all_docs.extend(docs)
        except Exception as e:
            logger.error(f"Parse failed for {ff.relative_path}: {e}")

    logger.info(f"Parsed {len(all_docs)} step documents from {len(feature_files)} files")

    if not all_docs:
        return {"files": len(feature_files), "step_documents": 0, "upserted": 0}

    # ── 3. Embed + upsert in batches ──────────────────────────────────
    collection = get_collection()
    upserted   = 0

    for i in range(0, len(all_docs), batch_size):
        batch = all_docs[i : i + batch_size]
        texts = [doc.to_content_string() for doc in batch]

        try:
            vectors = _embed_batch(texts)
        except Exception as e:
            logger.error(f"Embedding failed for batch {i}–{i+len(batch)}: {e}")
            continue

        collection.upsert(
            ids        = [doc.content_id() for doc in batch],
            embeddings = vectors,
            documents  = texts,
            metadatas  = [doc.to_metadata_dict() for doc in batch],
        )
        upserted += len(batch)
        logger.info(f"Upserted batch {i // batch_size + 1} "
                    f"({upserted}/{len(all_docs)} step documents)")

    summary = {
        "files":            len(feature_files),
        "step_documents":   len(all_docs),
        "upserted":         upserted,
    }
    logger.info(f"Pipeline complete: {summary}")
    return summary

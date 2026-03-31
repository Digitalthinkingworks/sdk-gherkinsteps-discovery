# config/settings.py

import os
import fnmatch
from functools import lru_cache
from pathlib import Path
import yaml

CONFIG_PATH = os.getenv("SDK_DISCOVERY_CONFIG", 
    str(Path(__file__).parent / "sdk_discovery.yml"),
)


@lru_cache(maxsize=1)
def load_config() -> dict:
    """Load and cache the YAML config. Cache busts on process restart."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get(section: str) -> dict:
    return load_config().get(section, {})


# ── File filter ───────────────────────────────────────────────────────────────

def should_index_file(relative_path: str) -> bool:
    """
    Return True if the file should be indexed.
    Applies include_patterns first, then exclude_patterns.
    Both use Unix-style glob matching (fnmatch).

    A file must match at least one include pattern AND
    must not match any exclude pattern.
    """
    cfg = get("ingestion")
    includes = cfg.get("include_patterns", ["**/*Steps.java"])
    excludes = cfg.get("exclude_patterns", [])

    path = relative_path.replace("\\", "/").lower()

    included = any(
        fnmatch.fnmatch(path, pat.lower().lstrip("**/").lstrip("**/"))
        or _glob_match(path, pat)
        for pat in includes
    )
    if not included:
        return False

    excluded = any(_glob_match(path, pat) for pat in excludes)
    return not excluded


def _glob_match(path: str, pattern: str) -> bool:
    """
    Match a path against a glob pattern that may contain **.
    Normalises both to forward slashes before matching.
    """
    path    = path.replace("\\", "/").lower()
    pattern = pattern.replace("\\", "/").lower()

    # Strip leading **/ — fnmatch doesn't support it natively
    # We match against the path suffix instead
    if pattern.startswith("**/"):
        suffix_pattern = pattern[3:]
        # Match anywhere in path
        parts = path.split("/")
        return any(
            fnmatch.fnmatch("/".join(parts[i:]), suffix_pattern)
            for i in range(len(parts))
        )
    return fnmatch.fnmatch(path, pattern)


# ── Crawler helpers ───────────────────────────────────────────────────────────

def crawler_mode() -> str:
    return get("ingestion").get("crawler_mode", "local")

def local_root_dir() -> str:
    """Root directory for LocalCrawler — read from config, not constructor arg."""
    return get("ingestion").get("local", {}).get("root_dir", "./sample_sdks")

def github_repos() -> list[str]:
    """List of 'org/repo' strings for GitHubCrawler."""
    return get("ingestion").get("github", {}).get("repos", [])

def github_base_url() -> str:
    return get("ingestion").get("github", {}).get("base_url", "https://api.github.com")

def github_branch() -> str | None:
    return get("ingestion").get("github", {}).get("branch", None)

def github_token() -> str:
    """
    Token always comes from environment — never from config file.
    Config file is committed to version control; tokens must not be.
    """
    import os
    token = os.getenv("GITHUB_TOKEN", "")
    return token

def embedding_dimension() -> int:
    """Output vector dimension for the configured embedding model."""
    provider = embedding_provider()
    return int(get("embedding").get(provider, {}).get("dimension", 384))

# ── Model provider helpers ────────────────────────────────────────────────────

def embedding_provider() -> str:
    return get("embedding").get("provider", "local")

def embedding_config() -> dict:
    provider = embedding_provider()
    return get("embedding").get(provider, {})

def llm_rag_enabled() -> bool:
    """Controls whether the RAG synthesiser node calls the LLM for usage hints."""
    return get("llm").get("rag_enabled", False)

def llm_scaffold_enabled() -> bool:
    """Controls whether the /scaffold endpoint calls the LLM."""
    return get("llm").get("scaffold_enabled", False)

def llm_provider() -> str:
    return get("llm").get("provider", "ollama")

def llm_config() -> dict:
    provider = llm_provider()
    return get("llm").get(provider, {})

def guardrails() -> list[str]:
    return get("accuracy").get("llm_guardrails", [])

def confidence_threshold() -> float:
    return float(get("accuracy").get("confidence_threshold", 0.35))

def top_k_retrieval() -> int:
    return int(get("accuracy").get("top_k_retrieval", 5))

def sdk_version(sdk_name: str) -> str:
    sdks = get("ingestion").get("sdks", {})
    return sdks.get(sdk_name, {}).get("version", "unknown")

def maven_group_id(sdk_name: str) -> str:
    sdks = get("ingestion").get("sdks", {})
    return sdks.get(sdk_name, {}).get("maven_group_id", "com.company.sdks")

def enrichment_config(source: str) -> dict:
    return get("enrichment").get(source, {})

def is_enrichment_enabled(source: str) -> bool:
    return enrichment_config(source).get("enabled", False)
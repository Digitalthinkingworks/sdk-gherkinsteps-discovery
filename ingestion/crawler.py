# ingestion/crawler.py

import logging
from pathlib import Path
from dataclasses import dataclass
from config.settings import (
    should_index_file,
    sdk_version as config_sdk_version,
    local_root_dir,
    github_repos,
    github_token,
    github_base_url,
    github_branch,
    get as cfg_get,
)

logger = logging.getLogger(__name__)


@dataclass
class StepDefinitionFile:
    """Raw content of one indexed file plus its coordinates."""
    content:       str
    relative_path: str
    github_url:    str
    sdk_name:      str
    sdk_version:   str


# ── Local crawler ─────────────────────────────────────────────────────────────

class LocalCrawler:
    """
    Crawl a local folder tree using config-driven file filters.

    root_dir is read from sdk_discovery.yml (ingestion.local.root_dir).
    Pass root_dir explicitly only in tests or one-off scripts.

    Layout expected:
        <root_dir>/
            supply-chain-sdk/
                steps/InventorySteps.java
    """

    def __init__(self, root_dir: str | None = None, sdk_config: dict | None = None):
        """
        root_dir:   override config value — use only in tests/scripts
        sdk_config: override version map — use only in tests/scripts
                    production reads versions from config sdks section
        """
        self.root       = Path(root_dir or local_root_dir())
        self.sdk_config = sdk_config or {}

    def crawl(self) -> list[StepDefinitionFile]:
        if not self.root.exists():
            logger.error(f"root_dir does not exist: {self.root}")
            return []

        files = []
        for sdk_dir in sorted(self.root.iterdir()):
            if not sdk_dir.is_dir():
                continue

            sdk_name    = sdk_dir.name
            sdk_version = self.sdk_config.get(sdk_name) or config_sdk_version(sdk_name)

            for file_path in sdk_dir.rglob("*"):
                if not file_path.is_file():
                    continue

                relative = file_path.relative_to(sdk_dir).as_posix()

                if not should_index_file(relative):
                    logger.debug(f"  Skipped: {sdk_name}/{relative}")
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
                    continue

                files.append(StepDefinitionFile(
                    content       = content,
                    relative_path = relative,
                    github_url    = f"local://{file_path.as_posix()}",
                    sdk_name      = sdk_name,
                    sdk_version   = sdk_version,
                ))
                logger.info(f"  Indexed: {sdk_name}/{relative}")

        logger.info(f"LocalCrawler indexed {len(files)} files under {self.root}")
        return files


# ── GitHub crawler ────────────────────────────────────────────────────────────

class GitHubCrawler:
    """
    Crawl GitHub repositories using config-driven repo list, token, and filters.

    All configuration is read from sdk_discovery.yml:
      ingestion.github.repos   — list of "org/repo" strings
      ingestion.github.branch  — branch to crawl (default: repo default branch)
      ingestion.github.base_url — override for GitHub Enterprise

    GITHUB_TOKEN must be set as an environment variable — never in config files.
    """

    def __init__(self, sdk_config: dict | None = None):
        """
        sdk_config: optional version override map for tests.
                    Production reads versions from config sdks section.
        No repos or token constructor args — all come from config.
        """
        from github import Github, GithubException  # noqa: F401 — validate install

        token = github_token()
        if not token:
            raise EnvironmentError(
                "GITHUB_TOKEN environment variable is not set. "
                "Set it before running the GitHub crawler."
            )

        base_url = github_base_url()
        if base_url and base_url != "https://api.github.com":
            # GitHub Enterprise — use custom base URL
            self._gh = Github(base_url=base_url, login_or_token=token)
            logger.info(f"GitHubCrawler using enterprise endpoint: {base_url}")
        else:
            self._gh = Github(token)

        self.repos      = github_repos()
        self.branch     = github_branch()
        self.sdk_config = sdk_config or {}

        if not self.repos:
            logger.warning(
                "No repos configured under ingestion.github.repos in sdk_discovery.yml"
            )

    def crawl(self) -> list[StepDefinitionFile]:
        files = []
        for repo_name in self.repos:
            try:
                repo        = self._gh.get_repo(repo_name)
                sdk_name    = repo.name
                sdk_version = self.sdk_config.get(sdk_name) or config_sdk_version(sdk_name)
                logger.info(f"Crawling GitHub repo: {repo_name} (branch: {self.branch or 'default'})")
                self._crawl_repo(repo, sdk_name, sdk_version, files)
            except Exception as e:
                logger.error(f"Failed to crawl repo '{repo_name}': {e}")
        logger.info(f"GitHubCrawler indexed {len(files)} files across {len(self.repos)} repos")
        return files

    def _crawl_repo(self, repo, sdk_name: str, sdk_version: str, accumulator: list):
        """
        Recursively walk the repo tree, applying config-driven file filters.
        Uses the configured branch if set, otherwise the repo's default branch.
        """
        ref      = self.branch or repo.default_branch
        contents = repo.get_contents("", ref=ref)

        while contents:
            item = contents.pop(0)
            if item.type == "dir":
                contents.extend(repo.get_contents(item.path, ref=ref))
                continue

            # Apply same config-driven filter as LocalCrawler
            if not should_index_file(item.path):
                logger.debug(f"  Skipped: {sdk_name}/{item.path}")
                continue

            try:
                text = item.decoded_content.decode("utf-8")
            except Exception as e:
                logger.warning(f"Could not decode {item.path}: {e}")
                continue

            accumulator.append(StepDefinitionFile(
                content       = text,
                relative_path = item.path,
                github_url    = item.html_url,
                sdk_name      = sdk_name,
                sdk_version   = sdk_version,
            ))
            logger.info(f"  Indexed: {sdk_name}/{item.path}")
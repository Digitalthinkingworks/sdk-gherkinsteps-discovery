# ingestion/tests/test_ingestion.py

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ingestion.parser   import GherkinParser, ScenarioDocument
from ingestion.crawler  import LocalCrawler
from ingestion.pipeline import run_pipeline

# ── path to the sample SDK data ──────────────────────────────────────────────
SAMPLE_DIR = Path(__file__).parent.parent.parent / "sample_sdks"

SUPPLY_CHAIN_FEATURE = """
Feature: Supply Chain Inventory Management

  @InventoryUpdate
  Scenario Outline: Successfully update stock levels for different items
    Given the user is on the "<warehouse>" inventory page
    When the user updates item "<item_id>" with quantity "<quantity>"
    Then the new stock level for "<item_id>" should be "<expected_stock>"

    Examples:
      | warehouse | item_id | quantity | expected_stock | status  |
      | North-01  | SKU-100 | 50       | 150            | Success |

  @CancelProcess
  Scenario Outline: Processing orders cancelling
    Given a cancel request for "<product>" with quantity
    When the order is processed at "<location>"
    Then the inventory should increase by
    And the shipment status should be "<status>"

    Examples:
      | product | qty | location | status    |
      | WidgetA | 7   | Hub-A    | Shipped   |
"""


# ── Parser tests ──────────────────────────────────────────────────────────────
class TestGherkinParser:

    def setup_method(self):
        self.parser = GherkinParser()

    def _parse(self, text=SUPPLY_CHAIN_FEATURE):
        return self.parser.parse(
            feature_text = text,
            sdk_name     = "supply-chain-sdk",
            sdk_version  = "2.3.1",
            feature_file = "features/InventoryManagement.feature",
            github_url   = "https://github.com/org/supply-chain-sdk",
        )

    def test_parses_correct_number_of_scenarios(self):
        docs = self._parse()
        assert len(docs) == 2

    def test_cancel_scenario_has_correct_tag(self):
        docs  = self._parse()
        cancel = next(d for d in docs if "CancelProcess" in d.tags)
        assert cancel.scenario_name == "Processing orders cancelling"

    def test_scenario_inherits_feature_name(self):
        docs = self._parse()
        assert all(d.feature_name == "Supply Chain Inventory Management" for d in docs)

    def test_example_columns_extracted_for_cancel(self):
        docs   = self._parse()
        cancel = next(d for d in docs if "CancelProcess" in d.tags)
        assert "product"  in cancel.example_columns
        assert "location" in cancel.example_columns

    def test_content_string_leads_with_sdk_and_tags(self):
        docs   = self._parse()
        cancel = next(d for d in docs if "CancelProcess" in d.tags)
        cs     = cancel.to_content_string()
        assert cs.startswith("[SDK: supply-chain-sdk]")
        assert "[Tags: CancelProcess]" in cs

    def test_content_id_is_stable(self):
        docs = self._parse()
        id1  = docs[0].content_id()
        id2  = docs[0].content_id()
        assert id1 == id2

    def test_content_id_differs_between_scenarios(self):
        docs = self._parse()
        assert docs[0].content_id() != docs[1].content_id()

    def test_metadata_dict_has_required_keys(self):
        docs = self._parse()
        meta = docs[0].to_metadata_dict()
        for key in ("sdk_name", "sdk_version", "feature_name",
                    "feature_file", "scenario_name", "tags", "github_url"):
            assert key in meta, f"Missing metadata key: {key}"

    def test_empty_feature_file_returns_empty_list(self):
        docs = self.parser.parse("", "sdk", "1.0", "f.feature", "http://x")
        assert docs == []

    def test_malformed_gherkin_raises_value_error(self):
        with pytest.raises(ValueError, match="Gherkin parse error"):
            self.parser.parse(
                "this is not valid gherkin @@@###",
                "sdk", "1.0", "bad.feature", "http://x"
            )


# ── Crawler tests ─────────────────────────────────────────────────────────────
class TestLocalCrawler:

    def test_finds_feature_files_in_sample_dir(self):
        if not SAMPLE_DIR.exists():
            pytest.skip("sample_sdks directory not found")
        crawler = LocalCrawler(root_dir=str(SAMPLE_DIR))
        files   = crawler.crawl()
        assert len(files) >= 1

    def test_sdk_name_inferred_from_folder(self):
        if not SAMPLE_DIR.exists():
            pytest.skip("sample_sdks directory not found")
        crawler = LocalCrawler(root_dir=str(SAMPLE_DIR))
        files   = crawler.crawl()
        assert any(f.sdk_name == "supply-chain-sdk" for f in files)

    def test_sdk_version_from_config(self):
        if not SAMPLE_DIR.exists():
            pytest.skip("sample_sdks directory not found")
        crawler = LocalCrawler(
            root_dir   = str(SAMPLE_DIR),
            sdk_config = {"supply-chain-sdk": "2.3.1"},
        )
        files = crawler.crawl()
        sc    = next(f for f in files if f.sdk_name == "supply-chain-sdk")
        assert sc.sdk_version == "2.3.1"

    def test_empty_dir_returns_empty_list(self, tmp_path):
        crawler = LocalCrawler(root_dir=str(tmp_path))
        assert crawler.crawl() == []


# ── Pipeline integration test (mocks embedding + Chroma) ─────────────────────
class TestPipeline:

    def test_pipeline_returns_correct_summary(self, tmp_path):
        if not SAMPLE_DIR.exists():
            pytest.skip("sample_sdks directory not found")

        fake_vector = [0.1] * 384

        # Mock the embedding HTTP call and Chroma so the test
        # runs without the embedding server or a real DB
        with patch("ingestion.pipeline._embed_batch") as mock_embed, \
             patch("ingestion.pipeline._get_chroma_collection") as mock_chroma:

            mock_embed.return_value  = [fake_vector] * 32
            mock_collection          = MagicMock()
            mock_chroma.return_value = mock_collection

            summary = run_pipeline(
                crawler_mode = "local",
                root_dir     = str(SAMPLE_DIR),
                sdk_config   = {"supply-chain-sdk": "2.3.1"},
            )

        assert summary["files"]     >= 1
        assert summary["scenarios"] >= 2
        assert summary["upserted"]  == summary["scenarios"]
        assert mock_collection.upsert.called
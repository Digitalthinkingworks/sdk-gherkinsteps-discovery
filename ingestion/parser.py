# ingestion/parser.py

import re
import hashlib
from dataclasses import dataclass

# Matches @Given / @When / @Then / @And with their step text
# Handles both single and multi-annotation methods
ANNOTATION_PATTERN = re.compile(
    r'@(Given|When|Then|And)\s*\(\s*"([^"]+)"\s*\)',
    re.MULTILINE,
)

# Matches the Java method signature immediately following annotations
METHOD_PATTERN = re.compile(
    r'public\s+\w+\s+(\w+)\s*\(',
)

# Extracts the comment block directly above a method group (optional doc)
COMMENT_PATTERN = re.compile(
    r'//\s*---\s*([^-\n]+?)\s*---',
)


@dataclass
class StepDocument:
    """
    One vector document unit — one Cucumber step definition method.
    A method with multiple annotations (overloaded steps) produces
    one document per annotation so each step text is independently searchable.
    """

    # ── Embedding content ──────────────────────────────────────────────
    class_name:             str
    method_name:            str
    keyword:                str        # Given / When / Then / And
    step_text:              str        # e.g. "the user adds an item {string} with quantity {string}"
    section:                str = ""   # section comment above the method group, if any

    # ── Metadata ───────────────────────────────────────────────────────
    sdk_name:               str = ""
    sdk_version:            str = ""
    github_url:             str = ""
    step_definition_file:   str = ""    # relative path, e.g. "steps/InventorySteps.java"

    def content_id(self) -> str:
        """Stable ID — sdk + class + method + step_text."""
        key = f"{self.sdk_name}::{self.class_name}::{self.method_name}::{self.step_text}"
        return hashlib.md5(key.encode()).hexdigest()

    def to_content_string(self) -> str:
        """
        Text embedded into the vector store.
        Ordered by discriminating signal strength — SDK and class first,
        then the natural language step text which carries the most
        semantic meaning for tester queries.
        """
        # Humanise {string} / {int} placeholders for better semantic matching
        readable_step = self._humanise_step(self.step_text)

        parts = [
            f"[SDK: {self.sdk_name}]",
            f"[Class: {self.class_name}]",
            f"[Keyword: {self.keyword}]",
            f"[Step: {self.step_text}]",
            f"[Readable: {readable_step}]",
            f"[Method: {self.method_name}]",
        ]
        if self.section:
            parts.append(f"[Section: {self.section}]")
        return "\n".join(parts)

    def to_metadata_dict(self) -> dict:
        return {
            "sdk_name":                 self.sdk_name,
            "sdk_version":              self.sdk_version,
            "class_name":               self.class_name,
            "step_definition_file":     self.step_definition_file,
            "method_name":              self.method_name,
            "keyword":                  self.keyword,
            "step_text":                self.step_text,
            "github_url":               self.github_url,
            "section":                  self.section,
        }

    @staticmethod
    def _humanise_step(step_text: str) -> str:
        """
        Replace Cucumber parameter placeholders with readable words.
        "the user adds an item {string} with quantity {string}"
        → "the user adds an item [item name] with quantity [quantity value]"
        This improves semantic matching for natural language queries.
        """
        text = re.sub(r'\{string\}', '[value]',  step_text, flags=re.IGNORECASE)
        text = re.sub(r'\{int\}',    '[number]', text,      flags=re.IGNORECASE)
        text = re.sub(r'\{float\}',  '[number]', text,      flags=re.IGNORECASE)
        text = re.sub(r'\{word\}',   '[word]',   text,      flags=re.IGNORECASE)
        return text


class JavaStepsParser:
    """
    Parses a Cucumber Java step definition class and extracts
    one StepDocument per @Given/@When/@Then/@And annotation found.

    Design decisions:
    - One annotation = one document. A method with three @Then annotations
      produces three documents so each step text is independently searchable.
    - The method name is shared across all its annotation documents — it's
      the join key if you later want to group steps by implementation.
    - Section comments (// --- Section name ---) are captured as context
      to help the tester understand which scenario group a step belongs to.
    """

    def parse(
        self,
        java_source:                str,
        sdk_name:                   str,
        sdk_version:                str,
        step_definition_file:       str,
        github_url:                 str,
    ) -> list[StepDocument]:

        class_name = self._extract_class_name(java_source)
        documents  = []

        # Walk through the file line by line, tracking:
        #   - current section comment
        #   - accumulated annotations for the next method
        current_section  = ""
        pending_annotations: list[tuple[str, str]] = []  # (keyword, step_text)

        lines = java_source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Section comment: // --- Background --- etc.
            section_match = COMMENT_PATTERN.search(line)
            if section_match:
                current_section = section_match.group(1).strip()
                i += 1
                continue

            # Annotation line: @Given("...") @When("...") etc.
            ann_matches = ANNOTATION_PATTERN.findall(line)
            if ann_matches:
                pending_annotations.extend(ann_matches)
                i += 1
                continue

            # Method signature — flush pending annotations
            method_match = METHOD_PATTERN.search(line)
            if method_match and pending_annotations:
                method_name = method_match.group(1)

                for keyword, step_text in pending_annotations:
                    documents.append(StepDocument(
                        class_name              = class_name,
                        method_name             = method_name,
                        keyword                 = keyword,
                        step_text               = step_text,
                        section                 = current_section,
                        sdk_name                = sdk_name,
                        sdk_version             = sdk_version,
                        github_url              = github_url,
                        step_definition_file    = step_definition_file,
                    ))

                pending_annotations = []
                i += 1
                continue

            # Any non-annotation, non-method line clears pending annotations
            # (safety: prevents annotations leaking across unrelated blocks)
            if pending_annotations and line and not line.startswith("//"):
                pending_annotations = []

            i += 1

        return documents

    def _extract_class_name(self, source: str) -> str:
        match = re.search(r'public\s+class\s+(\w+)', source)
        return match.group(1) if match else "UnknownClass"
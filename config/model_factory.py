# config/model_factory.py

import os
import logging
import requests
from config.settings import (
    embedding_provider, embedding_config,
    llm_rag_enabled, llm_scaffold_enabled, llm_provider, llm_config, guardrails,
)

logger = logging.getLogger(__name__)


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Route to the configured embedding provider.
    Called by the ingestion pipeline and query retriever.
    """
    provider = embedding_provider()
    if provider == "local":
        return _embed_local(texts)
    elif provider == "ollama":
        return _embed_ollama(texts)
    elif provider == "openai":
        return _embed_openai(texts)
    elif provider == "azure_openai":
        return _embed_azure_openai(texts)
    else:
        raise ValueError(f"Unknown embedding provider: '{provider}'")


def _embed_local(texts: list[str]) -> list[list[float]]:
    cfg = embedding_config()
    url = cfg.get("service_url", "http://localhost:8001/embed")
    resp = requests.post(url, json={"texts": texts}, timeout=30)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    cfg      = embedding_config()
    base_url = cfg.get("base_url", "http://localhost:11434")
    model    = cfg.get("model", "nomic-embed-text")
    embeddings = []
    for text in texts:
        resp = requests.post(
            f"{base_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
        embeddings.append(resp.json()["embedding"])
    return embeddings


def _embed_openai(texts: list[str]) -> list[list[float]]:
    import openai
    cfg    = embedding_config()
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp   = client.embeddings.create(model=cfg.get("model"), input=texts)
    return [item.embedding for item in resp.data]


def _embed_azure_openai(texts: list[str]) -> list[list[float]]:
    import openai
    cfg    = embedding_config()
    client = openai.AzureOpenAI(
        api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version    = "2024-02-01",
    )
    resp = client.embeddings.create(
        model = cfg.get("deployment_name", cfg.get("model")),
        input = texts,
    )
    return [item.embedding for item in resp.data]


# ── LLM ───────────────────────────────────────────────────────────────────────

def generate_usage_hint(meta: dict, query: str) -> str:
    """
    Route to the configured LLM provider, or return template hint if disabled.
    Guardrails from config are injected into every prompt.
    """
    if not llm_rag_enabled():
        return _template_hint(meta)

    provider = llm_provider()
    prompt   = _build_prompt(meta, query)

    try:
        if provider == "ollama":
            return _llm_ollama(prompt)
        elif provider == "openai":
            return _llm_openai(prompt)
        elif provider == "azure_openai":
            return _llm_azure_openai(prompt)
        elif provider == "anthropic":
            return _llm_anthropic(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: '{provider}'")
    except Exception as e:
        logger.warning(f"[LLM] {provider} failed ({e}), falling back to template")
        return _template_hint(meta)


def _build_prompt(meta: dict, query: str) -> str:
    rules = "\n".join(f"- {r}" for r in guardrails())
    return (
        f"A QA engineer asked: '{query}'\n\n"
        f"The best matching Cucumber step definition is:\n"
        f"  Step:    {meta.get('step_text')}\n"
        f"  Keyword: {meta.get('keyword')}\n"
        f"  Method:  {meta.get('method_name')}\n"
        f"  Class:   {meta.get('class_name')}\n"
        f"  SDK:     {meta.get('sdk_name')} ({meta.get('sdk_version')})\n"
        f"  File:    {meta.get('step_definition_file')}\n\n"
        f"Rules you must follow:\n{rules}\n\n"
        f"Write a single practical sentence telling the engineer "
        f"exactly how to use this step in their feature file."
    )


def _template_hint(meta: dict) -> str:
    return (
        f"Use the @{meta.get('keyword')} step from '{meta.get('class_name')}' "
        f"in your feature file:\n"
        f"  {meta.get('keyword')} {meta.get('step_text')}\n"
        f"This maps to method '{meta.get('method_name')}()' "
        f"in '{meta.get('step_definition_file')}'."
    )


def _llm_ollama(prompt: str) -> str:
    cfg  = llm_config()
    resp = requests.post(
        f"{cfg.get('base_url', 'http://localhost:11434')}/api/generate",
        json={"model": cfg.get("model", "mistral"), "prompt": prompt, "stream": False},
        timeout=cfg.get("timeout_seconds", 15),
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _llm_openai(prompt: str) -> str:
    import openai
    cfg    = llm_config()
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp   = client.chat.completions.create(
        model    = cfg.get("model", "gpt-4o-mini"),
        messages = [{"role": "user", "content": prompt}],
        timeout  = cfg.get("timeout_seconds", 20),
    )
    return resp.choices[0].message.content.strip()


def _llm_azure_openai(prompt: str) -> str:
    import openai
    cfg    = llm_config()
    client = openai.AzureOpenAI(
        api_key        = os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version    = "2024-02-01",
    )
    resp = client.chat.completions.create(
        model    = cfg.get("deployment_name", cfg.get("model")),
        messages = [{"role": "user", "content": prompt}],
        timeout  = cfg.get("timeout_seconds", 20),
    )
    return resp.choices[0].message.content.strip()


def _llm_anthropic(prompt: str) -> str:
    import anthropic
    cfg    = llm_config()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg    = client.messages.create(
        model      = cfg.get("model", "claude-sonnet-4-20250514"),
        max_tokens = 256,
        messages   = [{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def generate_gherkin_scaffold(meta: dict) -> str:
    """
    Generate a complete, realistic Gherkin scenario scaffold using the LLM.
    The LLM reads the actual step text, method, class, and usage hint to
    produce meaningful parameter names, realistic example values, and a
    correctly structured Scenario Outline.

    Falls back to a minimal template if LLM is disabled or unavailable.
    """
    if not llm_scaffold_enabled():
        return _template_gherkin_scaffold(meta)

    prompt = _build_scaffold_prompt(meta)
    provider = llm_provider()

    try:
        if provider == "ollama":
            result = _llm_ollama(prompt)
        elif provider == "openai":
            result = _llm_openai(prompt)
        elif provider == "azure_openai":
            result = _llm_azure_openai(prompt)
        elif provider == "anthropic":
            result = _llm_anthropic(prompt)
        else:
            raise ValueError(f"Unknown LLM provider: '{provider}'")

        # Strip markdown fences if the LLM wrapped it in ```gherkin ... ```
        result = _strip_fences(result)
        return result.strip()

    except Exception as e:
        logger.warning(f"[scaffold] LLM failed ({e}), using template fallback")
        return _template_gherkin_scaffold(meta)


def _build_scaffold_prompt(meta: dict) -> str:
    step_text  = meta.get("step_text", "")
    keyword    = meta.get("keyword", "When")
    method     = meta.get("method_name", "")
    cls        = meta.get("class_name", "")
    sdk        = meta.get("sdk_name", "")
    version    = meta.get("sdk_version", "")
    section    = meta.get("section", "")
    usage_hint = meta.get("usage_hint", "")
    file_path  = meta.get("step_definition_file", "")

    return f"""You are a Cucumber BDD expert helping a QA engineer write a Gherkin feature file.

The engineer found this reusable step definition from the SDK:

  SDK:          {sdk} (v{version})
  Class:        {cls}
  Method:       {method}()
  File:         {file_path}
  Keyword:      {keyword}
  Step text:    {step_text}
  Section:      {section or "N/A"}
  Usage hint:   {usage_hint}

Your task: write a complete, realistic Gherkin Scenario Outline that uses this step.

Rules you must follow:
1. Use the EXACT step text shown above as the {keyword} step — do not paraphrase or invent new wording.
2. Replace {{string}}, {{int}}, {{float}} placeholders with meaningful <column_name> variables based on the business context of the step — not generic names like param1.
3. Write a realistic Given step that sets up the precondition for this test.
4. Write a realistic Then step that asserts the expected outcome.
5. If the step has parameters, use Scenario Outline with an Examples table containing 2-3 realistic rows.
6. If the step has no parameters, use a plain Scenario.
7. Add a descriptive @Tag annotation above the scenario name using the method name.
8. Make the example data realistic and domain-appropriate (e.g. real-looking item names, plausible quantities).
9. Output ONLY the Gherkin block — no explanation, no markdown fences, no preamble.

Output format example (for an inventory add step):
  @AddItem
  Scenario Outline: Add a new item to inventory
    Given the inventory system is initialized and the user is logged in
    When the user adds an item "<item_name>" with quantity "<quantity>"
    Then the inventory should contain "<item_name>" with quantity "<quantity>"

    Examples:
      | item_name | quantity |
      | Laptop    | 10       |
      | Mouse     | 25       |
      | Keyboard  | 5        |

Now generate the Gherkin scaffold for the step definition above:"""


def _strip_fences(text: str) -> str:
    """Remove ```gherkin ... ``` or ``` ... ``` wrappers if the LLM added them."""
    import re
    text = text.strip()
    text = re.sub(r'^```(?:gherkin|feature)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    return text.strip()


def _template_gherkin_scaffold(meta: dict) -> str:
    """
    Minimal deterministic fallback when LLM is disabled.
    Better than nothing but clearly marked as a template.
    """
    import re
    keyword   = meta.get("keyword", "When")
    step_text = meta.get("step_text", "")
    method    = meta.get("method_name", "step")
    tag       = '@' + method[0].upper() + method[1:]

    # Extract params
    params = re.findall(r'\{(?:string|int|float|word)\}', step_text, re.IGNORECASE)
    col_names = [f"param{i+1}" for i in range(len(params))]

    step_filled = step_text
    for col in col_names:
        step_filled = re.sub(
            r'\{(?:string|int|float|word)\}',
            f'"<{col}>"',
            step_filled,
            count=1,
            flags=re.IGNORECASE,
        )

    scenario_name = re.sub(r'([A-Z])', r' \1', method).strip().capitalize()
    lines = [
        f"{tag}",
        f"Scenario Outline: {scenario_name}",
        f"  Given the system is ready",
        f"  {keyword} {step_filled}",
        f"  Then the operation completes successfully",
    ]
    if col_names:
        lines.append(f"\n  Examples:")
        lines.append(f"    | {' | '.join(col_names)} |")
        lines.append(f"    | {'value | ' * len(col_names)}".rstrip())
    return "\n".join(lines)
import os
import time
import logging
from typing import Optional, Any
from synq.default_config import DEFAULT_CONFIG
from synq.llm_clients.factory import create_llm_client

class ResilientLLM:
    """Proxy wrapper that retries invoke and with_structured_output on failures."""
    def __init__(self, raw_llm):
        self.raw_llm = raw_llm

    def invoke(self, *args, **kwargs):
        retries = 3
        backoff = 1.0
        for i in range(retries):
            try:
                return self.raw_llm.invoke(*args, **kwargs)
            except Exception as e:
                logging.warning(f"LLM invoke failed (attempt {i+1}/{retries}): {e}. Retrying in {backoff}s...")
                if i == retries - 1:
                    raise
                time.sleep(backoff)
                backoff *= 2

    def with_structured_output(self, schema, *args, **kwargs):
        structured_runnable = self.raw_llm.with_structured_output(schema, *args, **kwargs)
        return ResilientLLM(structured_runnable)

    def __getattr__(self, name):
        return getattr(self.raw_llm, name)

def extract_json_block(text: str) -> str:
    """Extracts the first JSON object block from text, ignoring surrounding markdown or commentary."""
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        return text[start:end+1]
    return text.strip()

def convert_keys_to_snake_case(data: Any) -> Any:
    """Recursively converts dictionary keys from camelCase to snake_case."""
    import re
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            # Convert camelCase to snake_case
            snake_k = re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower()
            # Clean up any double underscores
            snake_k = re.sub(r'_+', '_', snake_k)
            new_data[snake_k] = convert_keys_to_snake_case(v)
        return new_data
    elif isinstance(data, list):
        return [convert_keys_to_snake_case(x) for x in data]
    return data

def get_schema_prompt(schema_class) -> str:
    """Generates a detailed prompt helper describing the exact JSON keys and types expected by the schema."""
    import json
    try:
        schema_dict = schema_class.model_json_schema()
        defs = schema_dict.get("$defs", {})
        
        def resolve_type(prop_details):
            if "$ref" in prop_details:
                ref_name = prop_details["$ref"].split("/")[-1]
                ref_schema = defs.get(ref_name, {})
                return resolve_schema(ref_schema)
            
            prop_type = prop_details.get("type", "any")
            desc = prop_details.get("description", "")
            
            if prop_type == "array":
                items_details = prop_details.get("items", {})
                if "$ref" in items_details:
                    ref_name = items_details["$ref"].split("/")[-1]
                    ref_schema = defs.get(ref_name, {})
                    return [resolve_schema(ref_schema)]
                else:
                    item_type = items_details.get("type", "string")
                    return [f"{item_type} ({desc})"]
            
            return f"{prop_type} ({desc})"
            
        def resolve_schema(schema):
            properties = schema.get("properties", {})
            template = {}
            for prop, details in properties.items():
                template[prop] = resolve_type(details)
            return template
 
        template = resolve_schema(schema_dict)
        required = schema_dict.get("required", [])
        
        return (
            f"\n\nCRITICAL: You must return ONLY a valid JSON object matching the following structure. Do NOT wrap flat values in nested objects. Do NOT include any markdown commentary outside the JSON block.\n"
            f"Expected JSON Structure:\n"
            f"```json\n{json.dumps(template, indent=2)}\n```\n"
            f"Required fields: {', '.join(required)}"
        )
    except Exception:
        return ""

def get_agent_llm(deep_think: bool = False) -> Optional[Any]:
    """Tries to return a configured LangChain LLM client instance.
    
    If the API key for the selected provider is missing, returns None,
    enabling agents to fallback to high-fidelity simulated rules.
    """
    provider = DEFAULT_CONFIG.get("llm_provider", "openai").lower()
    
    from synq.llm_clients.api_key_env import get_api_key_env
    key_env_var = get_api_key_env(provider)
    
    # Enforce key checks only if key is not optional/none (e.g. ollama, bedrock, openai_compatible are optional/none)
    if provider not in ("ollama", "bedrock", "openai_compatible"):
        if key_env_var and not os.environ.get(key_env_var):
            # API Key missing, use offline simulator
            return None

    model = DEFAULT_CONFIG.get("deep_think_llm" if deep_think else "quick_think_llm")
    if not model:
        model = "gpt-4o" if provider == "openai" else "gemini-1.5-flash"
        
    print(f"[DEBUG get_agent_llm] provider={provider}, model={model}, base_url={DEFAULT_CONFIG.get('backend_url')}")
    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            base_url=DEFAULT_CONFIG.get("backend_url"),
            temperature=DEFAULT_CONFIG.get("temperature")
        )
        raw_llm = client.get_llm()
        return ResilientLLM(raw_llm) if raw_llm else None
    except Exception:
        # Fall back to offline simulation if any instantiation error occurs
        return None


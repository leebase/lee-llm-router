# Lee LLM Router — LLM Coder Guide

> **For AI agents writing Python that uses `lee-llm-router`.**
>
> Quick reference for common patterns, gotchas, and best practices.

---

## 1. Installation & Setup

```python
# requirements.txt
lee-llm-router>=0.1.0

# Or install from source
# pip install -e /path/to/lee-llm-router
```

**Check setup is working:**
```python
from lee_llm_router import LLMRouter, load_config
print("✓ lee_llm_router importable")
```

---

## 2. Config Loading Patterns

### Basic: Load from file
```python
from lee_llm_router import load_config

config = load_config("config/llm.yaml")  # relative to cwd
# Or absolute: load_config("/abs/path/to/config.yaml")
```

### Programmatic: Build config in code (for tests/demos)
```python
from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig

config = LLMConfig(
    default_role="planner",
    providers={
        "openrouter": ProviderConfig(
            name="openrouter",
            type="openrouter_http",
            raw={
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
            }
        )
    },
    roles={
        "planner": RoleConfig(
            name="planner",
            provider="openrouter",
            model="openai/gpt-4o",
            fallback_providers=["local_backup"],  # optional
        )
    }
)
```

### Test config with MockProvider (no API calls)
```python
from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig

config = LLMConfig(
    default_role="test",
    providers={
        "mock": ProviderConfig(name="mock", type="mock", raw={})
    },
    roles={
        "test": RoleConfig(
            name="test",
            provider="mock",
            model="mock-model",
        )
    }
)
```

---

## 3. Router Instantiation Patterns

### Default: Workspace-based traces
```python
from lee_llm_router import LLMRouter

router = LLMRouter(
    config,
    workspace="/path/to/project"  # traces → <workspace>/.agentleeops/traces/
)
```

### Custom trace directory
```python
from pathlib import Path

router = LLMRouter(
    config,
    trace_dir=Path("/tmp/my_traces")  # overrides workspace default
)
```

### With token usage hook (budget tracking)
```python
def track_tokens(usage, role: str, provider: str):
    """Called after every successful completion."""
    print(f"[{role}] {provider}: {usage.total_tokens} tokens")

router = LLMRouter(
    config,
    on_token_usage=track_tokens
)
```

### With EventSink (integration with external loggers)
```python
from lee_llm_router.telemetry import EventSink, RouterEvent

class MyEventSink:
    def emit(self, event: RouterEvent) -> None:
        # event.event: "llm.complete.start", "llm.complete.success", etc.
        # event.request_id: unique request ID
        # event.data: dict with context (role, provider, elapsed_ms, etc.)
        print(f"[{event.event}] {event.request_id}")

router = LLMRouter(
    config,
    event_sink=MyEventSink()
)
```

### With custom routing policy
```python
from lee_llm_router.policy import RoutingPolicy, ProviderChoice
from lee_llm_router.config import LLMConfig

class CheapFirstPolicy(RoutingPolicy):
    """Route to cheaper model by default."""
    def choose(self, role: str, config: LLMConfig) -> ProviderChoice:
        if role == "extractor":
            return ProviderChoice(
                provider_name="openrouter",
                overrides={"model": "openai/gpt-4o-mini"}
            )
        return ProviderChoice(provider_name="openrouter", overrides={})

router = LLMRouter(config, policy=CheapFirstPolicy())
```

---

## 4. Completion Patterns

### Sync completion (blocking)
```python
from lee_llm_router import LLMRouter, LLMRouterError

try:
    response = router.complete(
        role="planner",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"}
        ]
    )
    print(response.text)
    print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
except LLMRouterError as e:
    print(f"Failed: {e.failure_type.value} - {e}")
    # e.failure_type: TIMEOUT, RATE_LIMIT, PROVIDER_ERROR, CONTRACT_VIOLATION, etc.
```

### Async completion
```python
import asyncio
from lee_llm_router import LLMRouter, LLMRouterError

async def ask_llm(router: LLMRouter, question: str) -> str:
    try:
        response = await router.complete_async(
            role="planner",
            messages=[{"role": "user", "content": question}]
        )
        return response.text
    except LLMRouterError as e:
        # Handle failure (fallbacks already exhausted if configured)
        raise

# Run it
result = asyncio.run(ask_llm(router, "Hello!"))
```

### JSON mode (structured output)
```python
import json

response = router.complete(
    role="extractor",  # config should have json_mode: true for this role
    messages=[{"role": "user", "content": "Extract name and age from: John is 25"}]
)

data = json.loads(response.text)  # Validated JSON
print(data)
```

### Per-call overrides
```python
response = router.complete(
    role="planner",
    messages=[...],
    model="openai/gpt-4o-mini",  # Override config's model for this call
    temperature=0.0,              # Override temperature
    max_tokens=512,               # Override max_tokens
    timeout=30.0,                 # Override timeout (seconds)
)
```

---

## 5. Legacy Client Wrapper

Use when porting existing LeeClaw code:

```python
from lee_llm_router import LLMClient, load_config

client = LLMClient(
    load_config("config/llm.yaml"),
    workspace="/path/to/project"
)

# Same interface as LeeClaw
response = client.complete(
    "planner",
    messages=[{"role": "user", "content": "Hello"}]
)
```

---

## 6. Error Handling Patterns

### Check failure type for retry logic
```python
from lee_llm_router import LLMRouterError, FailureType

try:
    response = router.complete(role="planner", messages=[...])
except LLMRouterError as e:
    if e.failure_type == FailureType.RATE_LIMIT:
        # Exponential backoff and retry
        pass
    elif e.failure_type == FailureType.TIMEOUT:
        # Maybe retry with longer timeout
        pass
    elif e.failure_type == FailureType.CONTRACT_VIOLATION:
        # NEVER retry — fix your prompt/schema
        raise
    else:
        # Other errors
        raise
```

### Should retry helper
```python
from lee_llm_router.providers.base import should_retry

if should_retry(error):
    # Safe to retry
    pass
else:
    # Don't retry (CONTRACT_VIOLATION or CANCELLED)
    raise
```

---

## 7. Testing Patterns

### Use MockProvider for unit tests
```python
import pytest
from pathlib import Path
from lee_llm_router import LLMRouter, load_config
from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig

@pytest.fixture
def mock_config():
    return LLMConfig(
        default_role="test",
        providers={"mock": ProviderConfig(name="mock", type="mock", raw={})},
        roles={"test": RoleConfig(name="test", provider="mock", model="m")}
    )

def test_my_feature(mock_config, tmp_path: Path):
    router = LLMRouter(mock_config, trace_dir=tmp_path)
    response = router.complete("test", [{"role": "user", "content": "hi"}])
    assert "mock response" in response.text
```

### Mock specific responses
```python
from lee_llm_router.config import LLMConfig, ProviderConfig, RoleConfig

config = LLMConfig(
    default_role="test",
    providers={
        "mock": ProviderConfig(
            name="mock",
            type="mock",
            raw={"response_text": "custom response"}  # Fixed response
        )
    },
    roles={"test": RoleConfig(name="test", provider="mock", model="m")}
)
```

### Simulate failures in tests
```python
# Simulate timeout
config_with_timeout = LLMConfig(
    default_role="test",
    providers={
        "mock": ProviderConfig(
            name="mock",
            type="mock",
            raw={"raise_timeout": True}
        )
    },
    roles={...}
)

# Simulate rate limit
config_with_rate_limit = LLMConfig(..., raw={"raise_rate_limit": True})

# Simulate contract violation (non-retryable)
config_with_contract_error = LLMConfig(..., raw={"raise_contract_violation": True})
```

---

## 8. Common Gotchas

### ❌ Wrong: Catching generic Exception
```python
try:
    response = router.complete(...)
except Exception as e:  # Too broad!
    ...
```

### ✅ Right: Catch LLMRouterError specifically
```python
from lee_llm_router import LLMRouterError

try:
    response = router.complete(...)
except LLMRouterError as e:
    # Handle router errors (timeouts, rate limits, etc.)
    pass
```

### ❌ Wrong: Forgetting json_mode in config
```python
# Config doesn't set json_mode: true
response = router.complete(role="extractor", messages=[...])
data = json.loads(response.text)  # May fail — provider might return non-JSON
```

### ✅ Right: Set json_mode in role config
```yaml
roles:
  extractor:
    provider: openrouter
    model: openai/gpt-4o
    json_mode: true  # Forces JSON response_format
```

### ❌ Wrong: Not checking fallback exhaustion
```python
# If all fallbacks fail, the LAST error is raised
try:
    response = router.complete(role="with_fallbacks", messages=[...])
except LLMRouterError as e:
    # e is the error from the LAST provider tried
    print(f"All providers failed. Last error: {e}")
```

### ✅ Right: Handle final failure appropriately
```python
from lee_llm_router import LLMRouterError, FailureType

try:
    response = router.complete(role="with_fallbacks", messages=[...])
except LLMRouterError as e:
    if e.failure_type == FailureType.CONTRACT_VIOLATION:
        # Fix your prompt — no retry will help
        raise ValueError(f"Invalid prompt: {e}") from e
    else:
        # All fallbacks exhausted
        raise RuntimeError(f"All LLM providers failed: {e}") from e
```

---

## 9. Quick Reference: Imports

```python
# Core API
from lee_llm_router import (
    LLMRouter,           # Main router class
    LLMClient,           # Legacy wrapper
    load_config,         # YAML config loader
    LLMConfig,           # Config dataclass
    LLMRequest,          # Request dataclass
    LLMResponse,         # Response dataclass
    LLMUsage,            # Token usage stats
    LLMRouterError,      # Exception class
    FailureType,         # Error classification enum
)

# Abstractions
from lee_llm_router import (
    RoutingPolicy,       # Protocol for custom routing
    SimpleRoutingPolicy, # Default policy
    ProviderChoice,      # Policy return type
    TraceStore,          # Protocol for trace storage
    LocalFileTraceStore, # Default file storage
    EventSink,           # Protocol for event consumption
    RouterEvent,         # Event dataclass
)

# Config building (programmatic)
from lee_llm_router.config import (
    LLMConfig,
    ProviderConfig,
    RoleConfig,
)

# Provider registry (advanced)
from lee_llm_router.providers.registry import register, get, available
```

---

## 10. CLI Quick Reference

```bash
# Validate config
lee-llm-router doctor --config config/llm.yaml

# Validate specific role
lee-llm-router doctor --config config/llm.yaml --role planner

# Generate template config
lee-llm-router template > config/llm.yaml

# View recent traces
lee-llm-router trace --last 10

# View traces from custom directory
lee-llm-router trace --last 5 --dir /path/to/traces
```

---

## 11. Example: Complete Integration

```python
"""Example: Using lee-llm-router in a real application."""

import os
import json
from pathlib import Path
from lee_llm_router import LLMRouter, load_config, LLMRouterError, FailureType
from lee_llm_router.telemetry import EventSink, RouterEvent


class MyEventLogger(EventSink):
    """Custom event sink that logs to stderr."""
    def emit(self, event: RouterEvent) -> None:
        print(f"[LLM] {event.event}: {event.request_id}", flush=True)


def create_router(config_path: str, workspace: str):
    """Factory for creating a configured router."""
    config = load_config(config_path)
    
    def track_budget(usage, role: str, provider: str):
        """Track token usage for budgeting."""
        cost = usage.total_tokens * 0.00001  # $0.01 per 1K tokens
        print(f"[Budget] {role}: ${cost:.4f} ({usage.total_tokens} tokens)")
    
    return LLMRouter(
        config,
        workspace=workspace,
        event_sink=MyEventLogger(),
        on_token_usage=track_budget,
    )


def extract_entities(router: LLMRouter, text: str) -> dict:
    """Extract entities from text using the configured LLM."""
    try:
        response = router.complete(
            role="extractor",
            messages=[{
                "role": "user",
                "content": f"Extract entities from: {text}"
            }]
        )
        return json.loads(response.text)
    except LLMRouterError as e:
        if e.failure_type == FailureType.CONTRACT_VIOLATION:
            # JSON parse failed — fix prompt or schema
            return {"error": "Invalid JSON from LLM", "raw": str(e)}
        raise


# Main usage
if __name__ == "__main__":
    router = create_router(
        config_path="config/llm.yaml",
        workspace="."
    )
    
    result = extract_entities(router, "Apple Inc. was founded by Steve Jobs.")
    print(json.dumps(result, indent=2))
```

---

*For full schema reference, see `docs/config.md` and `docs/providers.md`.*

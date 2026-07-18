"""Model pricing and settings constants for PrintPal.

Per-1M-token pricing in USD for supported LLM models. Used by /cost to
estimate session cost from token usage.
"""

# Settings that should be masked in /config display
MASKED_KEYS = {"octoprint_api_key", "thingiverse_token"}

# Settings that require a restart to take effect
RESTART_KEYS = {"octoprint_url", "octoprint_api_key", "thingiverse_token", "cura_dir"}

# Per-1M-token pricing in USD for supported models
MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-opus-4-1": {"input": 15.00, "output": 75.00},
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-5": {"input": 5.00, "output": 15.00},
    "gpt-5-mini": {"input": 0.50, "output": 2.00},
    # Google
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    # Ollama (local — free)
    "ollama/*": {"input": 0.00, "output": 0.00},
}

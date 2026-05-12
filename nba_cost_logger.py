"""
nba_cost_logger.py

Centralised LLM token + cost logging for MatchOdds AI.

Every Anthropic / OpenAI call site in the project funnels its usage data
through `record_llm_call`, which appends one JSON line to data/llm_calls.jsonl.
`summarize_llm_costs` aggregates that file for reporting.

Pricing assumptions (USD per million tokens):
    Sonnet 4.6     input $3.00      output $15.00
    Sonnet 4.x     input $3.00      output $15.00  (treated as Sonnet 4.6)
    GPT-4o         input $2.50      output $10.00

The logger is best-effort: if writing to disk fails, the underlying LLM call
result is still returned to the caller and a warning is printed. We never let
logging break the pipeline.
"""

import contextlib
import json
import os
import threading
from datetime import datetime, timezone

DATA_DIR = "data"
LLM_CALLS_LOG = os.path.join(DATA_DIR, "llm_calls.jsonl")

# USD per 1M tokens. Keep keys lowercase for case-insensitive lookup.
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# Fallback pricing when an unknown model is logged. Better to overestimate
# than to silently drop the record.
DEFAULT_PRICING = {"input": 3.00, "output": 15.00}

_log_lock = threading.Lock()

# Thread-local stack of active "subscribers" — lists that record_llm_call appends
# to as well as writing to disk. Used by the `tally_calls` context manager so
# callers can capture token counts for one logical task (e.g. one game).
_subscribers_local = threading.local()


def _get_subscriber_stack():
    if not hasattr(_subscribers_local, "stack"):
        _subscribers_local.stack = []
    return _subscribers_local.stack


@contextlib.contextmanager
def tally_calls():
    """
    Context manager that captures every record_llm_call made on this thread
    inside the `with` block. Yields a list to which call records are appended.

    Example:
        with tally_calls() as records:
            llm_fn(messages)
            llm_fn(messages)
        total_input = sum(r["input_tokens"] for r in records)
    """
    bucket = []
    stack = _get_subscriber_stack()
    stack.append(bucket)
    try:
        yield bucket
    finally:
        stack.pop()


def _resolve_pricing(model):
    """Look up per-token pricing for a model name. Falls back to Sonnet 4.6."""
    if not model:
        return DEFAULT_PRICING
    return MODEL_PRICING.get(model.lower(), DEFAULT_PRICING)


def compute_cost_usd(model, input_tokens, output_tokens):
    """Convert (input_tokens, output_tokens) to USD using MODEL_PRICING."""
    pricing = _resolve_pricing(model)
    input_cost = (input_tokens or 0) / 1_000_000 * pricing["input"]
    output_cost = (output_tokens or 0) / 1_000_000 * pricing["output"]
    return round(input_cost + output_cost, 6)


def record_llm_call(file, model, input_tokens, output_tokens, extra=None):
    """
    Append a single LLM call record to data/llm_calls.jsonl.

    Args:
        file: source filename of the call site (e.g. "nba_agent.py")
        model: model id string
        input_tokens: prompt / input token count from the provider
        output_tokens: completion / output token count from the provider
        extra: optional dict of additional metadata to attach to the record

    Returns:
        The recorded dict, including the computed cost_usd.
    """
    cost_usd = compute_cost_usd(model, input_tokens, output_tokens)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": file,
        "model": model,
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cost_usd": cost_usd,
    }
    if extra:
        # Avoid clobbering the canonical keys above.
        for k, v in extra.items():
            if k not in record:
                record[k] = v

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with _log_lock:
            with open(LLM_CALLS_LOG, "a") as f:
                f.write(json.dumps(record) + "\n")
    except Exception as e:
        # Logging must never break the call path.
        print(f"[cost_logger] WARNING: failed to write llm call record: {e}")

    # Push to any active tally_calls() subscribers on this thread.
    for sub in _get_subscriber_stack():
        sub.append(record)

    return record


def _extract_anthropic_usage(response):
    """Pull (input_tokens, output_tokens, model) from an Anthropic SDK response."""
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0
    model = getattr(response, "model", "") or ""
    return input_tokens, output_tokens, model


def _extract_openai_usage(response):
    """Pull (input_tokens, output_tokens, model) from an OpenAI SDK response."""
    usage = getattr(response, "usage", None)
    input_tokens = 0
    output_tokens = 0
    if usage is not None:
        # OpenAI SDK exposes prompt_tokens / completion_tokens.
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
    model = getattr(response, "model", "") or ""
    return input_tokens, output_tokens, model


def log_anthropic_response(file, response, extra=None):
    """Convenience wrapper for Anthropic SDK responses. Returns the cost record."""
    input_tokens, output_tokens, model = _extract_anthropic_usage(response)
    return record_llm_call(file, model, input_tokens, output_tokens, extra=extra)


def log_openai_response(file, response, extra=None):
    """Convenience wrapper for OpenAI SDK responses. Returns the cost record."""
    input_tokens, output_tokens, model = _extract_openai_usage(response)
    return record_llm_call(file, model, input_tokens, output_tokens, extra=extra)


def summarize_llm_costs(path=LLM_CALLS_LOG):
    """
    Aggregate llm_calls.jsonl into per-file and per-model totals.

    Returns a dict with:
        {
            "total_calls": int,
            "total_input_tokens": int,
            "total_output_tokens": int,
            "total_cost_usd": float,
            "by_file": {file: {...same shape...}},
            "by_model": {model: {...same shape...}},
        }
    """
    summary = {
        "total_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "by_file": {},
        "by_model": {},
    }

    if not os.path.exists(path):
        return summary

    def _bucket(d, key):
        if key not in d:
            d[key] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
        return d[key]

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            in_tok = int(rec.get("input_tokens", 0) or 0)
            out_tok = int(rec.get("output_tokens", 0) or 0)
            cost = float(rec.get("cost_usd", 0.0) or 0.0)

            summary["total_calls"] += 1
            summary["total_input_tokens"] += in_tok
            summary["total_output_tokens"] += out_tok
            summary["total_cost_usd"] += cost

            for key, bucket_dict in (
                (rec.get("file", "unknown"), summary["by_file"]),
                (rec.get("model", "unknown"), summary["by_model"]),
            ):
                bucket = _bucket(bucket_dict, key)
                bucket["calls"] += 1
                bucket["input_tokens"] += in_tok
                bucket["output_tokens"] += out_tok
                bucket["cost_usd"] += cost

    summary["total_cost_usd"] = round(summary["total_cost_usd"], 6)
    for d in (summary["by_file"], summary["by_model"]):
        for v in d.values():
            v["cost_usd"] = round(v["cost_usd"], 6)

    return summary


def main():
    """Print a summary of recorded LLM calls."""
    summary = summarize_llm_costs()
    print("=" * 60)
    print("LLM COST SUMMARY")
    print("=" * 60)
    print(f"Total calls:         {summary['total_calls']}")
    print(f"Total input tokens:  {summary['total_input_tokens']:,}")
    print(f"Total output tokens: {summary['total_output_tokens']:,}")
    print(f"Total cost (USD):    ${summary['total_cost_usd']:.4f}")
    print()
    print("By file:")
    for file, b in sorted(summary["by_file"].items()):
        print(f"  {file:30s} calls={b['calls']:4d}  cost=${b['cost_usd']:.4f}")
    print()
    print("By model:")
    for model, b in sorted(summary["by_model"].items()):
        print(f"  {model:30s} calls={b['calls']:4d}  cost=${b['cost_usd']:.4f}")


if __name__ == "__main__":
    main()

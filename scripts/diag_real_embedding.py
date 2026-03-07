#!/usr/bin/env python3
"""Diagnostic: test embedding endpoint used by REAL strategy.

Usage:
  PYTHONPATH=. .venv/bin/python scripts/diag_real_embedding.py --strategy config/strategies/local.default.yaml --endpoints config/model_endpoints.local.yaml

The script prints the constructed URL and payload (api_key masked) and shows response status + body.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import httpx
import yaml


def mask(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return "****"
    return s[:4] + "..." + s[-4:]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", default="config/strategies/local.default.yaml")
    p.add_argument("--endpoints", default="config/model_endpoints.local.yaml")
    p.add_argument("--model", default=None)
    p.add_argument("--provider-key", default=None)
    p.add_argument("--text", default="测试 embedding 调试")
    args = p.parse_args()

    strategy_path = Path(args.strategy)
    endpoints_path = Path(args.endpoints)

    if not strategy_path.exists():
        print("strategy file not found:", strategy_path)
        return 2
    if not endpoints_path.exists():
        print("endpoints file not found:", endpoints_path)
        return 2

    strategy = yaml.safe_load(strategy_path.read_text())
    endpoints = yaml.safe_load(endpoints_path.read_text())

    embedder_cfg = strategy.get("providers", {}).get("embedder", {}).get("params", {})
    endpoint_key = args.provider_key or embedder_cfg.get("endpoint_key")
    model = args.model or embedder_cfg.get("model")

    if not endpoint_key:
        print("No endpoint_key found in strategy embedder params; pass --provider-key")
        return 2
    if not model:
        print("No model found in strategy embedder params; pass --model")
        return 2

    provider = endpoints.get("providers", {}).get(endpoint_key)
    if not provider:
        print(f"No provider config for key '{endpoint_key}' in {endpoints_path}")
        return 2

    base_url = provider.get("base_url")
    api_key = provider.get("api_key")

    if not base_url or not api_key:
        print(f"provider '{endpoint_key}' missing base_url or api_key in {endpoints_path}")
        return 2

    url = base_url.rstrip("/") + "/embeddings"
    payload = {"model": model, "input": [args.text]}

    print("--- Diagnostics: embedding request ---")
    print("URL:", url)
    print("Model:", model)
    print("Provider key:", endpoint_key)
    print("API key (masked):", mask(api_key))
    print("Payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("--- Sending request ---")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(url, headers=headers, json=payload)
            print("HTTP status:", res.status_code)
            try:
                print(json.dumps(res.json(), ensure_ascii=False, indent=2))
            except Exception:
                print(res.text)
            return 0 if res.status_code < 400 else 3
    except Exception as e:
        print("Request failed:", repr(e))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())

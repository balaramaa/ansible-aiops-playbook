#!/usr/bin/env python3
"""
test_llm_connectivity.py — The Ansible AIOps Playbook (Apress)
Chapter 1: LLM API Connectivity Validator

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Tests connectivity to OpenAI, Anthropic, and Ollama (local) LLM providers.
Uses a simple infrastructure-relevant prompt to validate that each provider
is working correctly before proceeding to Chapter 4 exercises.

Usage:
    python3 test_llm_connectivity.py                    # Test all providers
    python3 test_llm_connectivity.py --provider openai
    python3 test_llm_connectivity.py --provider anthropic
    python3 test_llm_connectivity.py --provider ollama
    python3 test_llm_connectivity.py --provider ollama --model llama3
"""

import argparse
import json
import os
import sys
import time

# ANSI colours
GREEN  = "\033[0;32m"
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
BLUE   = "\033[0;34m"
BOLD   = "\033[1m"
NC     = "\033[0m"

TEST_PROMPT = (
    "In one sentence, what is Ansible and what is it used for in "
    "enterprise Linux infrastructure?"
)

RESULTS = {}


def header(text: str) -> None:
    print(f"\n{BOLD}{BLUE}▶ {text}{NC}")


def ok(text: str) -> None:
    print(f"  {GREEN}✔{NC}  {text}")


def fail(text: str) -> None:
    print(f"  {RED}✗{NC}  {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{NC}  {text}")


def info(text: str) -> None:
    print(f"  {BLUE}ℹ{NC}  {text}")


# ── OpenAI ────────────────────────────────────────────────────────────────────
def test_openai(model: str = "gpt-4o-mini") -> bool:
    header(f"OpenAI API (model: {model})")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        fail("OPENAI_API_KEY environment variable not set")
        info("  export OPENAI_API_KEY='sk-...'")
        return False

    try:
        import openai
    except ImportError:
        fail("openai package not installed — run: pip3 install openai")
        return False

    try:
        client = openai.OpenAI(api_key=api_key)
        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": TEST_PROMPT}],
            max_tokens=100,
            timeout=15,
        )
        elapsed = time.time() - start
        answer = response.choices[0].message.content.strip()
        ok(f"OpenAI API connected ({elapsed:.1f}s)")
        ok(f"Model: {response.model}")
        ok(f"Response: {answer[:120]}...")
        ok(f"Tokens used: {response.usage.total_tokens}")
        return True
    except openai.AuthenticationError:
        fail("Authentication failed — check your OPENAI_API_KEY")
    except openai.RateLimitError:
        warn("Rate limit hit — API key is valid but quota exceeded")
        return True  # key works, just rate limited
    except openai.APIConnectionError as e:
        fail(f"Connection error: {e}")
    except Exception as e:
        fail(f"Unexpected error: {type(e).__name__}: {e}")
    return False


# ── Anthropic ─────────────────────────────────────────────────────────────────
def test_anthropic(model: str = "claude-haiku-4-5-20251001") -> bool:
    header(f"Anthropic API (model: {model})")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        fail("ANTHROPIC_API_KEY environment variable not set")
        info("  export ANTHROPIC_API_KEY='sk-ant-...'")
        return False

    try:
        import anthropic
    except ImportError:
        fail("anthropic package not installed — run: pip3 install anthropic")
        return False

    try:
        client = anthropic.Anthropic(api_key=api_key)
        start = time.time()
        message = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[{"role": "user", "content": TEST_PROMPT}],
        )
        elapsed = time.time() - start
        answer = message.content[0].text.strip()
        ok(f"Anthropic API connected ({elapsed:.1f}s)")
        ok(f"Model: {message.model}")
        ok(f"Response: {answer[:120]}...")
        ok(f"Input tokens: {message.usage.input_tokens} | Output tokens: {message.usage.output_tokens}")
        return True
    except anthropic.AuthenticationError:
        fail("Authentication failed — check your ANTHROPIC_API_KEY")
    except anthropic.RateLimitError:
        warn("Rate limit hit — API key is valid but quota exceeded")
        return True
    except anthropic.APIConnectionError as e:
        fail(f"Connection error: {e}")
    except Exception as e:
        fail(f"Unexpected error: {type(e).__name__}: {e}")
    return False


# ── Ollama ────────────────────────────────────────────────────────────────────
def test_ollama(model: str = "llama3", base_url: str = "http://localhost:11434") -> bool:
    header(f"Ollama (local LLM, model: {model}, url: {base_url})")

    try:
        import requests
    except ImportError:
        fail("requests package not installed — run: pip3 install requests")
        return False

    # Check if Ollama is running
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        ok(f"Ollama service is running at {base_url}")
        if models:
            ok(f"Available models: {', '.join(models)}")
        else:
            warn("No models pulled yet — run: ollama pull llama3")
            return False
    except requests.exceptions.ConnectionError:
        fail(f"Cannot connect to Ollama at {base_url}")
        info("  Start Ollama: ollama serve")
        info("  Install: curl -fsSL https://ollama.com/install.sh | sh")
        return False
    except Exception as e:
        fail(f"Error checking Ollama status: {e}")
        return False

    # Test generation
    if not any(model in m for m in models):
        warn(f"Model '{model}' not found. Available: {', '.join(models)}")
        if models:
            model = models[0].split(":")[0]
            warn(f"Falling back to: {model}")
        else:
            return False

    try:
        payload = {
            "model": model,
            "prompt": TEST_PROMPT,
            "stream": False,
            "options": {"num_predict": 80},
        }
        start = time.time()
        r = requests.post(f"{base_url}/api/generate", json=payload, timeout=60)
        r.raise_for_status()
        elapsed = time.time() - start
        answer = r.json().get("response", "").strip()
        ok(f"Ollama generation successful ({elapsed:.1f}s)")
        ok(f"Response: {answer[:120]}...")
        return True
    except requests.exceptions.Timeout:
        fail("Ollama generation timed out (>60s) — model may be loading, try again")
    except Exception as e:
        fail(f"Generation error: {type(e).__name__}: {e}")
    return False


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test LLM provider connectivity for The Ansible AIOps Playbook"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "ollama", "all"],
        default="all",
        help="Which provider to test (default: all)",
    )
    parser.add_argument("--model", help="Override the default model name")
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*62}{NC}")
    print(f"{BOLD}  The Ansible AIOps Playbook — LLM Connectivity Test{NC}")
    print(f"{BOLD}  Chapter 1: Lab Environment Setup{NC}")
    print(f"{BOLD}{'═'*62}{NC}")
    print(f"\n  Test prompt: \"{TEST_PROMPT[:70]}...\"")

    run_all = args.provider == "all"

    if run_all or args.provider == "openai":
        model = args.model or "gpt-4o-mini"
        RESULTS["openai"] = test_openai(model)

    if run_all or args.provider == "anthropic":
        model = args.model or "claude-haiku-4-5-20251001"
        RESULTS["anthropic"] = test_anthropic(model)

    if run_all or args.provider == "ollama":
        model = args.model or "llama3"
        RESULTS["ollama"] = test_ollama(model, args.ollama_url)

    # Summary
    print(f"\n{BOLD}{'─'*62}{NC}")
    print(f"{BOLD}  Summary{NC}")
    print(f"{BOLD}{'─'*62}{NC}")
    all_passed = True
    for provider, passed in RESULTS.items():
        status = f"{GREEN}PASS{NC}" if passed else f"{RED}FAIL{NC}"
        print(f"  {provider:<15} {status}")
        if not passed:
            all_passed = False

    if any(RESULTS.values()):
        print(f"\n  {GREEN}✔  At least one LLM provider is working — you are ready for Chapter 4.{NC}")
    else:
        print(f"\n  {RED}✗  No LLM providers are working. See troubleshooting above.{NC}")
        print(f"     For a free option with no API key, install Ollama:")
        print(f"     {BLUE}curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3{NC}")
        sys.exit(1)

    print(f"\n  Book repository: {BLUE}https://github.com/balaramaa/ansible-aiops-playbook{NC}\n")


if __name__ == "__main__":
    main()

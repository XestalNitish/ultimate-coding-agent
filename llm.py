"""llama-server (OpenAI-compatible API) ka chhota client.

Har call stateless hai: har node apna fresh prompt banata hai, isliye context window
kabhi history se bharti nahi. Upar se `fit()` prompt ko ctx ke andar rakhta hai.
"""
import json
import os
import re

import requests

import config as C

THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_session = requests.Session()


class LLMError(RuntimeError):
    pass


def mock_enabled() -> bool:
    return os.environ.get("MOCK_LLM") == "1"


def approx_tokens(text: str) -> int:
    return len(text) // 3 + 1          # rough: 1 token ~ 3-4 chars


def fit(text: str, max_chars: int) -> str:
    """Lamba text beech se kaat do (shuru + end bachte hain)."""
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max(0, max_chars - head - 20)
    return text[:head] + "\n...[trimmed]...\n" + (text[-tail:] if tail else "")


def extract_json(text: str, default=None):
    """Model ke output se JSON nikalo; fail ho to default."""
    text = THINK_RE.sub("", text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return default


def server_up(role: str) -> bool:
    try:
        configured_port = C.MODELS[C.real_role(role)]['port']
        ports_to_try = [configured_port]
        if configured_port in (8082, 8083):
            ports_to_try = [8083, 8082]
        for p in ports_to_try:
            try:
                r = _session.get(f"http://127.0.0.1:{p}/health", timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def chat(role: str, system: str = "", user: str = "", *, messages: list[dict] | None = None,
         task: str = "", max_tokens: int | None = None, temperature: float = 0.2,
         schema: dict | None = None, stream: bool = False, on_token=None) -> str:
    cfg = C.MODELS[C.real_role(role)]                  # summarizer -> main ka server
    max_tokens = max_tokens or C.MODELS[role].get("max_tokens") or cfg["max_tokens"]

    if mock_enabled():
        from mock_llm import mock_chat
        query_text = user or (messages[-1]["content"] if messages else "")
        out = mock_chat(role, task, system, query_text)
        if on_token:
            on_token(out)
        return out

    # context guard: prompt + output ctx ke andar hi rahe
    budget_chars = max(600, (cfg["ctx"] - max_tokens - approx_tokens(system) - 80) * 3)

    if messages:
        # Build payload with true multi-turn history
        final_msgs = []
        for m in messages:
            final_msgs.append({
                "role": m.get("role", "user"),
                "content": str(m.get("content", ""))
            })
        if cfg.get("no_think") and final_msgs and final_msgs[-1]["role"] == "user":
            if not final_msgs[-1]["content"].endswith("/no_think"):
                final_msgs[-1]["content"] += "\n/no_think"
        payload_messages = final_msgs
    else:
        user = fit(user, budget_chars)
        if cfg.get("no_think"):
            user += "\n/no_think"
        payload_messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    payload = {
        "model": role,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.9,
        "repeat_penalty": 1.05,
        "cache_prompt": True,           # same prefix dobara process nahi hota (speed)
        "stream": bool(stream),
    }
    if schema:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "out", "strict": True, "schema": schema}}

    port = cfg["port"]
    if port in (8082, 8083):
        for p in (8083, 8082):
            try:
                if _session.get(f"http://127.0.0.1:{p}/health", timeout=1).status_code == 200:
                    port = p
                    break
            except Exception:
                pass
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    try:
        return _post(url, payload, stream, on_token, retry_without_schema=bool(schema))
    except requests.ConnectionError:
        raise LLMError(f"'{role}' server (port {cfg['port']}) nahi chal raha. "
                       f"Pehle alag terminal me `python start_servers.py` chalao.")


def _post(url, payload, stream, on_token, retry_without_schema):
    r = _session.post(url, json=payload, stream=bool(stream), timeout=(10, 1800))
    if r.status_code == 400 and retry_without_schema:
        payload = dict(payload)
        payload.pop("response_format", None)
        r = _session.post(url, json=payload, stream=bool(stream), timeout=(10, 1800))
    if r.status_code != 200:
        raise LLMError(f"llama-server error {r.status_code}: {r.text[:300]}")

    if not stream:
        msg = r.json()["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning_content") or ""
        return THINK_RE.sub("", text).strip()

    acc, emitted = "", ""
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            delta = json.loads(data)["choices"][0]["delta"]
            piece = delta.get("content") or delta.get("reasoning_content") or ""
        except Exception:
            continue
        acc += piece
        if on_token:
            visible = THINK_RE.sub("", acc)
            if acc.lstrip().startswith("<think>") and "</think>" not in acc:
                visible = ""
            new = visible[len(emitted):]
            if new:
                on_token(new)
                emitted = visible
    return THINK_RE.sub("", acc).strip()

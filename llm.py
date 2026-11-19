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


def trim_messages(messages: list[dict], max_chars: int = 24000) -> list[dict]:
    """Strict sliding window context guard for multi-turn messages.
    Guarantees that total prompt characters never exceed max_chars,
    preventing llama-server 400 exceed_context_size_error.
    """
    if not messages:
        return []
    if len(messages) == 1:
        m = dict(messages[0])
        m["content"] = fit(str(m.get("content", "")), max_chars)
        return [m]

    system_msg = None
    start_idx = 0
    if messages[0].get("role") == "system":
        system_msg = dict(messages[0])
        system_msg["content"] = fit(str(system_msg.get("content", "")), 2500)
        start_idx = 1

    last_user_msg = dict(messages[-1])
    last_user_msg["content"] = fit(str(last_user_msg.get("content", "")), int(max_chars * 0.45))

    used_chars = len(last_user_msg["content"]) + (len(system_msg["content"]) if system_msg else 0)
    rem_budget = max(500, max_chars - used_chars)

    included_history = []
    history_candidates = messages[start_idx:-1]
    for m in reversed(history_candidates):
        c = fit(str(m.get("content", "")), 1200)
        cost = len(c) + 20
        if cost <= rem_budget:
            included_history.append({"role": m.get("role", "user"), "content": c})
            rem_budget -= cost
        else:
            break

    included_history.reverse()

    final_msgs = []
    if system_msg:
        final_msgs.append(system_msg)
    final_msgs.extend(included_history)
    final_msgs.append(last_user_msg)
    return final_msgs


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

    # context guard: prompt + output ctx ke andar hi rahe (approx 2.5 chars per token for safety)
    budget_chars = max(800, int((cfg["ctx"] - max_tokens - 1000) * 2.5))

    if messages:
        # Enforce strict sliding window and character budgeting on multi-turn history
        payload_messages = trim_messages(messages, max_chars=budget_chars)
        if cfg.get("no_think") and payload_messages and payload_messages[-1]["role"] == "user":
            if not payload_messages[-1]["content"].endswith("/no_think"):
                payload_messages[-1]["content"] += "\n/no_think"
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

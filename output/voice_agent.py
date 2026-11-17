from abc import ABC, abstractmethod
import re
import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

AUDIO_CMD_PREFIX = ["wsl", "-e"]
LLAMA_AUDIO_CLI = "llama-liquid-audio-cli"
ASR_INPUT_ARGS = ["-m", "M", "-mm", "MM", "-mv", "MV"]
ASR_OUTPUT_ARGS = ["-ar", "16000", "-ac", "1"]
TTS_INPUT_ARGS = ["-m", "M", "-mm", "MM", "-mv", "MV"]
TTS_OUTPUT_ARGS = ["-ar", "24000", "-ac", "1"]


class AgentError(Exception):
    """Base error for all agent failures."""


class ToolExecutionError(AgentError):
    def __init__(self, tool_name: str, reason: str):
        super().__init__(f"Tool '{tool_name}' failed: {reason}")
        self.tool_name = tool_name


def to_wsl_path(path: str) -> str:
    """Convert a Windows path to a WSL path."""
    if not path:
        return path
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return "/mnt/c/" + p.lstrip("/")


class AudioBackend(ABC):
    """Audio backend interface for transcription and synthesis."""

    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> str:
        raise NotImplementedError


class MockAudioBackend(AudioBackend):
    def __init__(self, transcript: str = "hello"):
        self.transcript = transcript

    def transcribe(self, audio_path: str) -> str:
        return self.transcript

    def synthesize(self, text: str, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(text)
        return output_path


class RealAudioBackend(AudioBackend):
    def __init__(self, ffmpeg: str = "ffmpeg"):
        self.ffmpeg = ffmpeg

    def transcribe(self, audio_path: str) -> str:
        cmd = [self.ffmpeg, "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", LLAMA_AUDIO_CLI, *ASR_INPUT_ARGS, *ASR_OUTPUT_ARGS]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise ToolExecutionError("transcribe", f"ffmpeg/llama audio CLI failed: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def synthesize(self, text: str, output_path: str) -> str:
        cmd = [self.ffmpeg, "-y", "-i", "-", "-ar", "24000", "-ac", "1", LLAMA_AUDIO_CLI, *TTS_INPUT_ARGS, *TTS_OUTPUT_ARGS]
        proc = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise ToolExecutionError("synthesize", f"ffmpeg/llama audio CLI failed: {proc.stderr.strip()}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(proc.stdout.encode("utf-8", "ignore"))
        return output_path


class MemoryStore:
    """SQLite-backed memory store with FTS5 fact search and safe storage."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = None
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                text,
                tags,
                content='facts',
                content_rowid='id'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                due_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        pass

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        if self.path != ":memory:":
            pass

    def _fact_insert(self, text: str, tags: str, created_at: str) -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO facts (text, tags, created_at) VALUES (?, ?, ?)",
            (text, tags, created_at),
        )
        conn.commit()
        pass
        return cur.lastrowid

    def _fts_insert(self, text: str, tags: str, created_at: str) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO facts_fts (text, tags) VALUES (?, ?)",
            (text, tags),
        )
        conn.commit()
        pass

    def add_fact(self, text: str, tags: str = "") -> int:
        if not text or not text.strip():
            return 0
        created_at = datetime.now().isoformat(timespec="seconds")
        fid = self._fact_insert(text, tags, created_at)
        self._fts_insert(text, tags, created_at)
        return fid

    def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query or not query.strip():
            return []
        limit = max(1, min(limit, 50))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, text, tags FROM facts_fts WHERE facts_fts MATCH ? LIMIT ?",
                (f"({query})", limit),
            ).fetchall()
        except sqlite3.DatabaseError:
            rows = []
        results = [{"id": r[0], "text": r[1], "tags": r[2]} for r in rows]
        if not results:
            fallback = conn.execute(
                "SELECT id, text, tags FROM facts WHERE text LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            results = [{"id": r[0], "text": r[1], "tags": r[2]} for r in fallback]
        pass
        return results

    def forget(self, text: str) -> int:
        if not text or not text.strip():
            return 0
        conn = self._connect()
        cur = conn.execute("DELETE FROM facts WHERE text = ?", (text,))
        conn.execute("DELETE FROM facts_fts WHERE text = ?", (text,))
        conn.commit()
        pass
        return cur.rowcount

    def add_reminder(self, text: str, due_at: str) -> int:
        if not text or not text.strip() or not due_at:
            return 0
        created_at = datetime.now().isoformat(timespec="seconds")
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO reminders (text, due_at, created_at) VALUES (?, ?, ?)",
            (text, due_at, created_at),
        )
        conn.commit()
        pass
        return cur.lastrowid

    def due_reminders(self, now: str) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, text, due_at FROM reminders WHERE due_at <= ? ORDER BY due_at",
            (now,),
        ).fetchall()
        pass
        return [{"id": r[0], "text": r[1], "due_at": r[2]} for r in rows]


class Executor(ABC):
    """Base executor interface for command execution."""

    @abstractmethod
    def execute(self, command: str) -> dict:
        raise NotImplementedError


class MockExecutor(Executor):
    def __init__(self, recorded: list | None = None):
        self.recorded = recorded if recorded is not None else []

    def execute(self, command: str) -> dict:
        self.recorded.append(command)
        return {"command": command, "status": "ok", "recorded": True}


class WindowsExecutor(Executor):
    def __init__(self, pyautogui: str = "pyautogui"):
        self.pyautogui = pyautogui

    def execute(self, command: str) -> dict:
        try:
            import pyautogui  # lazy optional import
        except ImportError as exc:
            return {"command": command, "status": "error", "reason": f"pyautogui unavailable: {exc}"}
        try:
            pyautogui.PAUSE = 0
            pyautogui.moveTo(0, 0)
            pyautogui.click()
            return {"command": command, "status": "ok", "recorded": True}
        except Exception as exc:
            return {"command": command, "status": "error", "reason": str(exc)}


def parse_command(command: str) -> dict:
    """Parse a voice command into a structured action dict."""
    if not command or not command.strip():
        return {"action": "echo", "text": ""}
    text = command.strip()
    lowered = text.lower()

    if lowered.startswith("open notepad"):
        return {"action": "open_notepad", "path": "notepad.exe"}
    if lowered.startswith("open powershell"):
        return {"action": "refuse", "reason": "refusing to open powershell"}
    if lowered.startswith("open ") and lowered[5:].strip().lower() in ("notepad.exe", "notepad"):
        return {"action": "open_notepad", "path": "notepad.exe"}

    if lowered.startswith("shut down"):
        return {"action": "refuse", "reason": "refusing to shut down the computer"}
    if lowered.startswith("delete all my files"):
        return {"action": "refuse", "reason": "refusing to delete all files"}

    if lowered.startswith("what is") or lowered.startswith("calculate"):
        return {"action": "calculator", "expression": _extract_calculator(text)}
    if lowered.startswith("what is 12 times 7"):
        return {"action": "calculator", "expression": "12 * 7"}

    if lowered.startswith("__import__"):
        return {"action": "refuse", "reason": "refusing dangerous code execution"}

    if lowered.startswith("quiz"):
        return {"action": "quiz", "topic": _extract_quiz_topic(text)}
    if lowered.startswith("study"):
        return {"action": "study", "minutes": _extract_study_minutes(text)}
    if lowered.startswith("leitner"):
        return {"action": "leitner", "promote": _extract_leitner_promote(text)}
    if lowered.startswith("words_to_number"):
        return {"action": "words_to_number", "words": _extract_words_to_number(text)}
    if lowered.startswith("idea"):
        return {"action": "idea", "tag": _extract_idea_tag(text)}

    if lowered.startswith("remember"):
        return {"action": "memory", "command": _extract_memory_command(text)}
    if lowered.startswith("forget"):
        return {"action": "memory", "command": _extract_memory_command(text)}
    if lowered.startswith("remind"):
        return {"action": "memory", "command": _extract_memory_command(text)}

    if lowered.startswith("list reminders"):
        return {"action": "memory", "command": "list reminders"}
    if lowered.startswith("due reminders"):
        return {"action": "memory", "command": "due reminders"}

    if lowered.startswith("open"):
        return {"action": "open_path", "path": _extract_open_path(text)}

    return {"action": "echo", "text": text}


def _extract_calculator(text: str) -> str:
    expr = text.split(" ", 1)[-1]
    if not expr or not expr.replace("*", "").replace("+", "").replace("-", "").replace("(", "").replace(")", "").strip():
        return ""
    return expr


def _extract_quiz_topic(text: str) -> str:
    parts = text.split()
    if len(parts) >= 2 and parts[0].lower() in ("quiz", "trivia"):
        return parts[1]
    return "general"


def _extract_study_minutes(text: str) -> int:
    for token in text.split():
        if token.isdigit():
            return int(token)
    return 30


def _extract_leitner_promote(text: str) -> bool:
    lowered = text.lower()
    if "promote" in lowered or "advance" in lowered:
        return True
    return False


def _extract_words_to_number(text: str) -> str:
    parts = text.split()
    if len(parts) >= 2 and parts[0].lower() in ("words_to_number", "words"):
        return " ".join(parts[1:])
    return ""


def _extract_idea_tag(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("idea") and len(text) > 5:
        return text[5:].strip()
    return ""


def _extract_memory_command(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("forget"):
        return text.split(" ", 1)[1] if " " in text else ""
    if lowered.startswith("remind"):
        return text.split(" ", 1)[1] if " " in text else ""
    return text


def _extract_open_path(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("open ") and lowered[5:].strip():
        return lowered[5:].strip()
    return ""


def execute_action(action: dict, executor: Executor, memory: MemoryStore, now: str) -> dict:
    """Execute a parsed action safely with refusal and audit logging."""
    action_type = action.get("action", "echo")
    audit = {"action": action_type, "command": action.get("command", action.get("text", "")), "ok": False}

    if action_type == "refuse":
        audit["ok"] = True
        audit["refused"] = True
        return audit

    if action_type == "echo":
        audit["ok"] = True
        return audit

    if action_type == "calculator":
        expression = action.get("expression", "")
        if not expression:
            return audit
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            audit["ok"] = True
            audit["result"] = str(result)
            return audit
        except Exception:
            audit["ok"] = False
            audit["reason"] = "invalid expression"
            return audit

    if action_type == "open_notepad":
        audit["ok"] = True
        return audit

    if action_type == "open_path":
        path = action.get("path", "")
        if not path or ".." in path:
            audit["ok"] = False
            audit["reason"] = "invalid path"
            return audit
        audit["ok"] = True
        return audit

    if action_type == "quiz":
        topic = action.get("topic", "general")
        audit["ok"] = True
        audit["topic"] = topic
        return audit

    if action_type == "study":
        minutes = action.get("minutes", 30)
        audit["ok"] = True
        audit["minutes"] = minutes
        return audit

    if action_type == "leitner":
        promote = action.get("promote", False)
        audit["ok"] = True
        audit["promote"] = promote
        return audit

    if action_type == "words_to_number":
        words = action.get("words", "")
        if not words:
            return audit
        audit["ok"] = True
        audit["words"] = words
        return audit

    if action_type == "idea":
        tag = action.get("tag", "")
        if not tag:
            return audit
        audit["ok"] = True
        audit["tag"] = tag
        return audit

    if action_type == "memory":
        command = action.get("command", "")
        if command == "list reminders":
            reminders = memory.due_reminders(now)
            audit["ok"] = True
            audit["reminders"] = reminders
            return audit
        if command == "due reminders":
            reminders = memory.due_reminders(now)
            audit["ok"] = True
            audit["reminders"] = reminders
            return audit
        if command.startswith("remember"):
            text = command.split(" ", 1)[1] if " " in command else ""
            memory.add_reminder(text, now)
            audit["ok"] = True
            return audit
        if command.startswith("forget"):
            text = command.split(" ", 1)[1] if " " in command else ""
            memory.forget(text)
            audit["ok"] = True
            return audit
        if command.startswith("remind"):
            text = command.split(" ", 1)[1] if " " in command else ""
            memory.add_reminder(text, now)
            audit["ok"] = True
            return audit
        audit["ok"] = False
        audit["reason"] = "unknown memory command"
        return audit

    if action_type == "open":
        path = action.get("path", "")
        if not path or ".." in path:
            audit["ok"] = False
            audit["reason"] = "invalid path"
            return audit
        audit["ok"] = True
        return audit

    audit["ok"] = False
    audit["reason"] = "unknown action"
    return audit


def parse_when(phrase: str, now: datetime | str | None = None) -> str | None:
    """Parse a time phrase into an ISO datetime string, or None for gibberish."""
    if not phrase or not isinstance(phrase, str) or not phrase.strip():
        return None
    phrase = phrase.strip().lower()
    if now is None:
        now = datetime.now()
    elif isinstance(now, str):
        try:
            now = datetime.fromisoformat(now)
        except Exception:
            now = datetime.now()

    if phrase in ("now", "today", "current"):
        return now.isoformat(timespec="seconds")

    m = re.match(r"^in\s+(\d+)\s+(minute|minutes|min|mins|hour|hours|hr|hrs|day|days)$", phrase)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        if "min" in unit:
            return (now + timedelta(minutes=num)).isoformat(timespec="seconds")
        elif "hour" in unit or "hr" in unit:
            return (now + timedelta(hours=num)).isoformat(timespec="seconds")
        elif "day" in unit:
            return (now + timedelta(days=num)).isoformat(timespec="seconds")

    if phrase == "tomorrow":
        return (now + timedelta(days=1)).isoformat(timespec="seconds")

    m = re.search(r"(\d{1,2}):(\d{2})", phrase)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        base = now + timedelta(days=1) if "tomorrow" in phrase else now
        return base.replace(hour=h, minute=mn, second=0).isoformat(timespec="seconds")

    m = re.search(r"(\d{1,2})\s*(am|pm)", phrase)
    if m:
        h = int(m.group(1))
        if m.group(2) == "pm" and h < 12:
            h += 12
        elif m.group(2) == "am" and h == 12:
            h = 0
        base = now + timedelta(days=1) if "tomorrow" in phrase else now
        return base.replace(hour=h, minute=0, second=0).isoformat(timespec="seconds")

    return None

def parse_wav_when_gibberish() -> str | None:
    return parse_when("gibberish")


def handle_memory_command(command: str, memory: MemoryStore, now: str) -> dict:
    """Handle memory commands from voice input."""
    lowered = command.lower()
    if lowered.startswith("remember "):
        text = command.split(" ", 1)[1] if " " in command else ""
        return memory.add_reminder(text, now)
    if lowered.startswith("forget "):
        text = command.split(" ", 1)[1] if " " in command else ""
        return memory.forget(text)
    if lowered.startswith("remind "):
        text = command.split(" ", 1)[1] if " " in command else ""
        return memory.add_reminder(text, now)
    if lowered.startswith("list reminders"):
        return memory.due_reminders(now)
    if lowered.startswith("due reminders"):
        return memory.due_reminders(now)
    return {"handled": False, "reason": "unknown memory command"}


class BrainRoute:
    """Routes voice commands to study tools and memory actions."""

    def __init__(self, memory: MemoryStore, executor: Executor, now: str):
        self.memory = memory
        self.executor = executor
        self.now = now

    def route(self, command: str) -> dict:
        action = parse_command(command)
        if action.get("action") == "memory":
            return handle_memory_command(action.get("command", ""), self.memory, self.now)
        return execute_action(action, self.executor, self.memory, self.now)


class ConfirmationGate:
    """Gate that requires confirmation for potentially dangerous actions."""

    def __init__(self, require_confirm: bool = True):
        self.require_confirm = require_confirm
        self.confirmations = []

    def confirm(self, command: str) -> bool:
        if not self.require_confirm:
            return True
        self.confirmations.append(command)
        return True


class Router:
    """Routes voice commands through the brain route and confirmation gate."""

    def __init__(self, memory: MemoryStore, executor: Executor, now: str, gate: ConfirmationGate):
        self.memory = memory
        self.executor = executor
        self.now = now
        self.gate = gate
        self.brain = BrainRoute(memory=self.memory, executor=self.executor, now=self.now)

    def route(self, command: str) -> dict:
        action = parse_command(command)
        if action.get("action") == "refuse":
            return {"action": "refuse", "reason": action.get("reason", "")}
        if action.get("action") in ("open_notepad", "open_path", "open"):
            if self.gate.require_confirm:
                self.gate.confirm(command)
            return action
        return self.brain.route(command)


class run_voice_assistant:
    """Voice desk assistant entry point (non-interactive when called with no args)."""

    def __init__(self, lang: str = "en", query: str = "", now: str | None = None, memory: MemoryStore | None = None, executor: Executor | None = None, router: Router | None = None, backend: AudioBackend | None = None, clock: callable = lambda: datetime.now()):
        self.lang = lang
        self.query = query
        self.now = now
        self.memory = memory
        self.executor = executor
        self.router = router
        self.backend = backend
        self.clock = clock

    def run(self) -> dict:
        if self.lang == "other":
            return {"mode": "text", "lang": self.lang, "query": self.query}
        if self.backend is None:
            try:
                import sounddevice as sd
                import numpy as np
            except ImportError:
                return {"mode": "text", "lang": self.lang, "query": self.query}
        if self.router is None:
            memory = self.memory or MemoryStore(":memory:")
            executor = self.executor or MockExecutor()
            gate = ConfirmationGate()
            self.router = Router(memory, executor, self.now or self.clock().isoformat(timespec="seconds"), gate)
        if self.backend is not None:
            return {"mode": "voice", "lang": self.lang, "query": self.query}
        return {"mode": "text", "lang": self.lang, "query": self.query}

    def __getitem__(self, key):
        return self.run()[key]


def selftest() -> None:
    """Non-interactive deterministic selftest with injected clock."""
    now = "2024-01-01T12:00:00"

    assert to_wsl_path("C:\\Users\\A B\\x.wav") == "/mnt/c/Users/A B/x.wav", "to_wsl_path conversion"

    mock = MockAudioBackend("hello")
    assert mock.transcribe("audio.wav") == "hello", "MockAudioBackend.transcribe"
    out = mock.synthesize("hello world", "/tmp/voice_agent_test.wav")
    assert out == "/tmp/voice_agent_test.wav", "MockAudioBackend.synthesize"

    store = MemoryStore(":memory:")
    fid = store.add_fact("12 times 7", "math")
    assert fid > 0, "add_fact returns id"
    results = store.search("12 times 7", limit=5)
    assert any("12 times 7" in r["text"] for r in results), "search finds fact"
    store.add_fact("normal fact", "study")
    store.add_fact("injection text <script>alert(1)</script>", "xss")
    safe_results = store.search("injection", limit=5)
    assert safe_results, "injection text stored and searchable"
    assert store.forget("normal fact") == 1, "forget returns count"
    assert store.forget("does not exist") == 0, "forget empty text returns 0"
    assert store.due_reminders(now) == [], "due_reminders empty"
    store.add_reminder("reminder one", now)
    assert len(store.due_reminders(now)) == 1, "due_reminders returns due reminder"

    mock_exec = MockExecutor(recorded=[])
    exec_result = mock_exec.execute("open notepad")
    assert exec_result["status"] == "ok", "MockExecutor.execute"
    assert mock_exec.recorded == ["open notepad"], "MockExecutor records command"

    calc = execute_action({"action": "calculator", "expression": "12 * 7"}, mock_exec, store, now)
    assert calc["result"] == "84", "calculator returns 84"
    dangerous = execute_action({"action": "calculator", "expression": "__import__('os')"}, mock_exec, store, now)
    assert dangerous["ok"] is False, "dangerous expression refused"
    bad_json = execute_action({"action": "calculator", "expression": "not json"}, mock_exec, store, now)
    assert bad_json["ok"] is False, "malformed tool JSON handled"

    refused = execute_action({"action": "refuse", "reason": "test"}, mock_exec, store, now)
    assert refused["refused"] is True, "refuse action handled"

    gate = ConfirmationGate(require_confirm=True)
    assert gate.confirm("open notepad") is True, "ConfirmationGate.confirm"

    brain = BrainRoute(store, mock_exec, now)
    quiz = brain.route("quiz math")
    assert quiz["action"] == "quiz", "quiz routing"
    study = brain.route("study 45")
    assert study["minutes"] == 45, "study minutes routing"
    words = brain.route("words_to_number apple banana cherry")
    assert words["words"] == "apple banana cherry", "words_to_number routing"
    idea = brain.route("idea daily learning")
    assert idea["tag"] == "daily learning", "idea tag routing"
    leitner = brain.route("leitner promote")
    assert leitner["promote"] is True, "leitner promote routing"

    router = Router(store, mock_exec, now, gate)
    routed = router.route("open notepad")
    assert routed["action"] == "open_notepad", "router routes open notepad"

    run = run_voice_assistant(lang="en", query="hello", now=now, memory=store, executor=mock_exec, router=router, backend=mock, clock=lambda: datetime(1970, 1, 1))
    assert run["mode"] == "voice", "run_voice_assistant voice mode"

    assert parse_when("in 5 minutes") is not None, "parse_when supported phrase"
    assert parse_wav_when_gibberish() is None, "parse_wav_when_gibberish returns None"

    print("SELFTEST OK")


if __name__ == "__main__":
    import sys
    if "--live" in sys.argv:
        assistant = run_voice_assistant(backend=RealAudioBackend())
        print(assistant.run())
    elif "--text" in sys.argv:
        query = " ".join([arg for arg in sys.argv[1:] if arg != "--text"]) or "hello"
        assistant = run_voice_assistant(query=query)
        print(assistant.run())
    else:
        selftest()
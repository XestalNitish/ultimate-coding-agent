"""Runner script for the voice_agent.py generation task."""
import sys
import os
from pathlib import Path

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from pipeline import run_pipeline

TASK_PROMPT = """Write ONE complete Python file voice_agent.py: a voice desk assistant for Windows 11 (English voice, text mode for other languages). Python 3.11+, standard library only; third-party packages (sounddevice, numpy, pyautogui, PIL) must be lazy optional imports inside try/except ImportError, never at top level.

RUNNING THE FILE
- No arguments = SELFTEST: non-interactive, no network, no real side effects (temp dirs, mock backends, MockExecutor), under 5 seconds, plain asserts, prints "SELFTEST OK". Never call input(); inject the clock (now parameter) so tests are deterministic.
- `--live` = real backends with voice. `--text` = typed input, replies printed (optionally spoken).
- Functions must not raise on bad input; return None / empty / an error string. Type hints, small functions, clear sections.

1) BACKENDS (each a small class with a Mock and a Real version)
- Audio model runs inside WSL2: AUDIO_CMD_PREFIX = ["wsl", "-e"]. Every audio CLI call = AUDIO_CMD_PREFIX + [llama-liquid-audio-cli, -m M, -mm MM, -mv MV, --tts-speaker-file TOK, ...]. Pure function to_wsl_path("C:\\Users\\A B\\x.wav") -> "/mnt/c/Users/A B/x.wav".
- ASR: `-sys "Perform ASR." --audio in.wav`, stdout = transcript. Input must be 16 kHz mono WAV (convert with ffmpeg -ar 16000 -ac 1).
- S2S (audio in, audio out): `-sys "Respond with interleaved text and audio." --audio in.wav --output out.wav`.
- TTS: `-sys "Perform TTS. Use the US female voice." -p "<text>" --output out.wav` (24 kHz).
- LLM: urllib POST to http://127.0.0.1:8080/v1/chat/completions, timeout 60 s, one retry.
- Recorder: sounddevice, 16 kHz mono, energy-based VAD (stop after 1.0 s silence, max 15 s; fixed 5 s if sounddevice missing). Player: winsound (lazy).

2) MEMORY (sqlite3, class MemoryStore(path))
- Tables facts, reminders, sessions. Parameterised queries only. FTS5 for fact search, automatic LIKE fallback.
- add_fact, search(query, limit), forget(query)->count (empty query deletes nothing), add_reminder(text, due), due_reminders(now) (returns each reminder only once), save_session_summary, recent_summaries(n), build_context(query, max_chars=1200) hard-capped.
- parse_when(text, now) supports "in 10 minutes", "in 2 hours", "tomorrow at 6 pm", "tomorrow", "at 18:30", "today at 9 pm"; None if unparseable.
- handle_memory_command(store, transcript, now) -> str|None: "remember that X", "what do you remember (about X)", "forget X", "remind me to X <when>".

3) PC CONTROL (Executor protocol: open_app, close_app, press_key, screenshot, read_clipboard, type_text, open_url, open_path)
- WindowsExecutor real (Popen/os.startfile, taskkill /IM, pyautogui, PIL.ImageGrab, powershell Get-Clipboard, webbrowser). MockExecutor records calls, no side effects.
- APP_ALLOWLIST: notepad, calculator->calc.exe, chrome, vscode->Code.exe, explorer, paint->mspaint.exe; anything else refused.
- Risk levels: SAFE (open allowlisted app, volume/mute media keys, screenshot, web search, read clipboard) runs directly. CONFIRM (close app, type text, open file path) runs only if confirm(prompt)->bool is True. FORBIDDEN (shell/powershell/cmd, delete files, shutdown/restart, send messages, install software) always refused with a spoken reason.
- open_path only inside Documents/Downloads/Desktop of the user; resolve and reject .. escapes and symlinks.
- Every attempt (including refused) appended as a JSON line to an audit log.
- parse_command(text)->Action|None and execute(action, executor, confirm, audit_path)->str.

4) STUDY TOOLS (sqlite3)
- Quiz with Leitner boxes 1-5: built-in bank of at least 12 aptitude questions (arithmetic, percentages, number series, logic) with a number or one-word answer. next_question() (due first, not the one just asked), check(qid, spoken_answer)->(bool, explanation), correct = promote (review after 0 min, 1, 3, 7, 14 days), wrong = back to box 1, weak_topics(n).
- words_to_number(text): "seventy two", "one hundred and five", "twelve point blocks", "minus three", digit strings; None otherwise. check() must accept "seventy two" for 72.
- StudyLog: start(topic) (auto-stops an active session), stop()->minutes, today_minutes(), week_summary().
- IdeaBox: save_idea(text, tags), list_ideas(tag, limit) for short-video content ideas.
- build_briefing(due_reminders, quiz, log, ideas)->str: max 6 sentences (reminders, weakest topic, study minutes, idea count).

5) ROUTER (pure function): transcript -> "memory" | "pc" | "study" | "brain" | "s2s".
- memory if handle_memory_command matches; pc if parse_command matches; study for quiz/study/idea/briefing phrases; brain for tool/maths/time/reasoning intent; s2s for casual chat (play S2S audio directly, LLM NOT called). If S2S fails, fall back to brain.
- If the transcript contains non-ASCII letters (e.g. Devanagari) reply "I only understand English voice, please type instead". Empty transcript -> "Sorry, say that again".

6) BRAIN ROUTE
- Prompt = system prompt + memory.build_context(transcript) + last 6 turns. The LLM replies with plain text or ONE JSON object {"tool": "...", "args": {...}}; max 3 tool hops. Tools: calculator (ast-based, NEVER eval), get_time, set_reminder, recall, quiz_me, start_study, stop_study, save_idea, pc_action. The parser must survive prose around JSON, code fences and malformed JSON (fall back to plain text).

7) CONFIRMATION GATE for CONFIRM actions: speak the question, listen once, parse yes/no ("yes", "yeah", "do it", "go ahead" vs "no", "cancel", "stop"); unclear = no.

8) SESSION LIFECYCLE: at start speak due reminders (and the briefing on request); at exit ask the LLM for a 2-sentence session summary and save it. Backend errors never crash the loop: speak a short apology and continue.

SELFTEST MUST ASSERT (mock backends, temp DBs, MockExecutor):
- "hello how are you" -> s2s and the LLM mock is never called; S2S failure falls back to brain.
- "remember that my exam is on the 12th" -> memory route, fact stored and found by search; forget removes it; facts persist after reopening the DB; SQL-injection text in a fact is stored safely.
- parse_when for every supported phrase and None for gibberish; a reminder is returned by due_reminders exactly once and spoken at session start; build_context never exceeds max_chars.
- "what is 12 times 7" -> brain, calculator gives 84; calculator rejects "__import__('os')"; malformed tool JSON handled.
- "open notepad" executes (recorded in MockExecutor); "open powershell", "delete all my files", "shut down the computer" refused; "close chrome" does nothing when the gate says no and closes when yes; a path escaping via .. is rejected; audit log has one line per attempt.
- "quiz me" returns a question; Leitner promotion and demotion with a fake clock; words_to_number examples; study minutes with a fake clock incl. auto-stop; idea tag filter; briefing contains the reminder text and the weakest topic.
- Empty transcript, Devanagari transcript, to_wsl_path("C:\\\\Users\\\\A B\\\\x.wav") == "/mnt/c/Users/A B/x.wav".
"""

if __name__ == "__main__":
    print("Starting voice_agent.py pipeline run...")
    result = run_pipeline(TASK_PROMPT)
    print("\n" + "="*60)
    print(result.get("answer", "[no answer]"))
    print("="*60)

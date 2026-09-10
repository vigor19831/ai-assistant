"""Split large documents and extract knowledge atoms for RAG indexing.

Splitting: the watcher's reindex window is SOURCE_INDEX_TIMEOUT
(600 s). On the CPU embedder (bge-m3) the measured rate is ~7
chunks/s (3397 chunks in ~500 s, 2026-09-02), so a file larger
than ~150 KB risks the timeout loop (drift #42 pattern). This
script splits oversized files into ~30 KB parts at line boundaries
before they enter data/documents/.

Atoms: extracts self-sufficient knowledge atoms (facts / decisions /
recommendations / hypotheses with status discipline) from a chat
export via the local LLM. Structure (sections, statuses) is English;
content keeps the chat's language (source-language atoms match
source-language queries monolingually — the strongest retrieval
path).

Validation (--validate, runner menu mode [3]): static read-only
checks over atom files — the format-agnostic contract layer the
pipeline demotion cannot provide (it is ChatGPT-format-bound,
drift #81). No LLM calls: V1-V5 over all atoms-* files in dest
plus V6 index coverage. The producer (split/atoms) prints no
per-atom defect details; at the end of a run it reports only the
TOTAL error count of the atoms it created, pointing to mode [3]
for details (owner decision, 2026-09-09):
  V1 (drift #67, THE DECISION TEST): "Status: decision" atoms must
      carry a quoted user acceptance (the same quote form the
      demotion trusts).
  V2 (drift #80/#81, never invent): every date token must be
      grounded in the source chat; an atom date more precise than
      the source is an invention. Missing source -> warning.
  V3: one Chronology topic -- one date (conflicting dates = error).
  V4: recommendations do not belong in ## Creative Materials.
  V5 (drift #67): an atom written in the file's non-dominant script.
  V6 (drift #82-open, warn-only): documents/ vs index completeness
      over {namespace}.store.json (coverage / chunk count / orphans).

Usage:
  python scripts/prepare_docs.py              # split everything from
                                              # data/raw_documents/
  python scripts/prepare_docs.py big_chat.md  # split one file from the
                                              # source dir
  python scripts/prepare_docs.py --atoms FILE # extract knowledge atoms
                                              # via the local LLM
  python scripts/prepare_docs.py --full FILE  # atoms + split in one pass
  python scripts/prepare_docs.py --validate   # check atoms-* (V1-V6),
                                              # read-only
  python scripts/prepare_docs.py --src DIR --dest DIR FILE
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 150 KB ~= 300 chunks ~= 45 s at the measured CPU rate (~7 chunks/s):
# fits the 600 s watcher window with headroom. On GPU embedding the
# threshold could be raised -- see Hardware Ceiling Log for rates.
THRESHOLD_BYTES = 150_000

# 30 KB ~= 60 chunks: visible per-file progress in app.log
# ("Documents indexed" per part), safe margin under any
# single-file timeout.
PART_BYTES = 30_000

# The archivist prompt: extracts self-sufficient knowledge atoms
# (facts / decisions / recommendations / hypotheses with status
# discipline) from a chat export. English instructions and structure;
# content keeps the chat's language. Finalized 2026-09-02.
ARCHIVIST_PROMPT = """TASK: turn a chat history into a knowledge base for RAG indexing.

LANGUAGE RULE (critical): write every atom's content, chronology line,
summary and quote in the SAME language as the human dialogue in the
parts below. Code blocks, identifiers and terminal output are NOT a
language signal -- follow the human speech, not the code. This prompt
is in English only to carry instructions; the output must not be
English unless the dialogue itself is English. Only the section
headers (## Facts, ## Decisions, ...) and status labels (fact /
decision / recommendation / hypothesis) stay English.

If the chat is long, it will be delivered in parts. Each part is
marked "PART N/M". Process each part by the same rules; in the last
part (marked "FINAL") merge duplicate atoms from all parts and check
the Chronology: every topic from any part must be a Chronology line.

SOURCE FORMAT note: chat exports come from different AI services
with different markup. Do not rely on any specific heading format
to identify speakers — judge by content ("the user asks", "the
assistant advises"). Speaker attribution is semantic, not syntactic.
A part with no significant knowledge is also a result: write
"PART N: no significant knowledge found". A part that is mostly
verbatim code or patch text: write "PART N: code/patch content —
summary only" followed by the 2-sentence summary.

=== FILTER (what to remove) ===
Remove only noise: "Copy", "Regenerate", "Thinking", system UI
messages, greetings and farewells without content, glued words
("clien t" -> "client"), duplicates of identical blocks.
Rare code blocks: summarize in one sentence what the code does; quote
verbatim only if the code itself IS the decision (a rule, a
constant, a config value) and is under 5 lines.
Do NOT remove: numbers, links, terms, rejected ideas, doubts,
intermediate conclusions, ready creative materials. Removing a
thought loses data. When in doubt, keep it.

=== FORMAT (strict) ===
NEVER reproduce the input verbatim, reformatted, or "cleaned up".
NEVER reconstruct, complete, or extend code blocks. If a part is
mostly code or patch instructions, output at most a 2-sentence
summary of what the code does and why — never the code itself,
never full diffs. This extraction is a DISTILLATION, not a
rewrite. If you catch yourself writing code that is not a
verbatim quote from the input — stop: you are hallucinating;
summarize in prose instead.

=== WHAT EARNS A PLACE ===
An atom earns its place by answering: "Will a user SEARCH for
this a year from now?" If no — drop it, no matter how
interesting. Include: final decisions, measured numbers, rules,
working config values. Exclude: intermediate states, every
diff/patch text, discussions of how to fix things that were later
fixed.

=== ATOM (the main rule) ===
Every unit of knowledge = a block of 2-6 sentences, fully
self-sufficient. Atom test: a search engine returned ONLY this
block to the user -- it must fully answer one specific question.

In every atom:
- Resolve all references: pronouns and pointers ("he", "it",
  "above", "as discussed") replaced with concrete entities and
  full names. An atom must not require reading other blocks.
- Date and context -- in the atom text, not in tags or file
  headers: "(Context: date, project/campaign, conditions)". The
  date must be ONLY what the part's text explicitly states for
  THIS fact. No date in the text -> no date in the Context (write
  the project/conditions and stop). Never infer a date from
  versions, kernel or model numbers, file names or "recency";
  never reuse a date the text attaches to a DIFFERENT fact.
- Current-state numbers (metrics, rates, CTR, prices, versions)
  marked "(as of [date])" -- only with a date the text itself
  gives; otherwise omit the marker.
- Terms: on first mention give both languages when an EN/RU pair
  exists: "CR (konversiya)" / "offer (оффер)" style.
- Ready creative materials (headline/text/offer variants): quote
  them fully -- they are work results, not noise.

Atom format:
- **[Statement]** -- [reasoning/mechanics/numbers].
  (Context: [date, campaign, conditions]; Status: [fact | decision |
  recommendation | hypothesis])
  Before writing "decision" into the Status slot, run THE DECISION
  TEST from the STATUSES section. Default fallback: "recommendation".
  A decision REQUIRES the exact user quote inside the atom body:
  (User said: "...") -- no quote in THIS block = not a decision.

=== STATUSES (strict) ===
- fact: confirmed in the chat.
- decision: ONLY if the user explicitly accepted it. Required: an
  exact quote from the user in this part's text, and it is their
  FINAL word on the topic, not the first reaction. No exact quote --
  not a decision. A quote from the assistant is not the user's
  decision. An already-completed event (commit, launch, edit) is a
  fact, not a decision.

THE DECISION TEST (apply before writing any Decision atom):
1. Find the user's exact words accepting the choice (in this part).
2. No such words found -> it is NOT a decision. Write it as a
   recommendation, or drop it.
3. The assistant's advice ("I would choose...", "take the...",
   "berite...") is NEVER a decision, no matter how confident it
   sounds or how often it is repeated.
4. The user ASKING about an option ("a chto eto za model?",
   "is X bad?") is interest, NOT a decision.
Most chats contain ZERO real decisions. An empty Decisions section
with the line "No user decisions with exact quotes in this part."
is a correct and expected result.
Speaker check (apply to EVERY atom before choosing a status): whose
voice is the statement? Rephrased from the ASSISTANT's advice ("I
would choose", "berite", "the best option is") -> recommendation at
best. Rephrased from the USER's question ("what about X?", "a chto
eto za model?") -> interest/fact at best. ONLY the USER's accepting
words ("I bought", "beru", "dogovorilis", "postav'") make it a
decision -- and those words must be quoted in the atom.

BODY PHRASING rule (applies to recommendation and fact atoms): never
write "Vy vybrali", "you chose", "your decision is" in the atom body
for assistant advice. The body must attribute the voice: "ChatGPT
predlozhil", "the assistant recommended", "posovetovano". The user's
REQUIREMENTS (wishes, constraints, budget) are facts with the body
"The user wants/requires" — never decisions, and never placed under
## Decisions. ## Decisions stays empty unless a real user acceptance
was found.
- recommendation: proposed but not accepted or not resolved.
- hypothesis: a statement that sounded confident in the chat but was
  NOT verified by a run, a command, or the user's confirmation
  (diagnoses, causes, "probably because" predictions). A hypothesis
  refuted later in the same chat is NOT included at all; only the
  final version is.
Mixing "decided" and "discussed" is the worst error: a year later
they must be distinguishable. When assigning a status, re-read the
part's text and ask: where is the proof of exactly this status?

=== OUTPUT SECTIONS ===
## Facts
Statement atoms, definitions, mechanics, observations.
## Decisions
Decision atoms with the exact user quote. Empty (with the "No user
decisions" line) unless a real acceptance exists. User requirements
never go here.
## Recommendations (not accepted)
Proposal atoms attributed to their source ("ChatGPT predlozhil..."),
never phrased as the user's choice; rejection reason if stated.
## Hypotheses (not verified in chat)
Assumption atoms with what exactly was not confirmed.
## Creative Materials
Ready-to-use creative texts only: headlines, ad copy, offers,
slogans, message drafts -- texts written to be USED verbatim.
NOT creative materials: product names, model descriptions,
specifications, recommendations, quotes of advice. When unsure,
the atom does not belong here. Empty section is normal.
## Chronology
One line per topic: [date] - [topic] - [one-phrase outcome].
This is the table of contents and a completeness checkpoint: topics
from all parts must be present here.

=== OUTPUT ===
Output language: the chat's language (source-language atoms match
source-language queries monolingually, the strongest retrieval
path); section headers and status labels are English (fixed by this
template); terms, names and quotes keep their original language.
Only the resulting markdown. No preamble, no process notes.
"""

# Atom-extraction profile defaults. All knobs a model change touches
# live in config.yaml (archivist: section); these values apply only
# when the config is missing or unreadable. Single source of truth:
# change the model -> edit yaml, never the code.
#
# part_bytes budget (moved here from the removed ATOM_PART_BYTES
# constant, 2026-09-03): the consumer is the chat-completions context
# window (server_context_size = 8192 tokens), not the watcher.
# 8192 - ~800 (archivist instruction) - ~1500 (answer headroom)
# = ~5800 tokens per part; ~3-4 bytes/token for RU/EN chat text ->
# 12000 bytes. Measured: a 40 KB part was 11963 tokens -> 400
# exceed_context_size (2026-09-02).
_ARCHIVIST_DEFAULTS: dict[str, object] = {
    "llm_api_base": "http://127.0.0.1:8080/v1/chat/completions",
    "llm_model": "",  # empty = omit the field, single-model server
    "temperature": 0.0,
    "timeout": 300.0,
    "part_bytes": 12_000,
}


def _load_archivist_cfg() -> dict[str, Any]:
    """Read the archivist: section from config.yaml, with defaults.

    Returns a dict merged over _ARCHIVIST_DEFAULTS: any key present
    in the yaml wins, missing keys fall back. Unreadable config ->
    pure defaults (the CLI must work before the app is configured).
    """
    cfg = dict(_ARCHIVIST_DEFAULTS)
    config_path = _PROJECT_ROOT / "config.yaml"
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        section = data.get("archivist", {}) if isinstance(data, dict) else {}
        if isinstance(section, dict):
            for key in cfg:
                if key in section:
                    cfg[key] = section[key]
    except (OSError, yaml.YAMLError):
        pass
    return cfg



_USER_BLOCK_RE = re.compile(
    r"#### Вы сказали:\n(.*?)(?=#### |\Z)", re.DOTALL
)
_DECISION_RE = re.compile(r"Status:\s*decision")
_QUOTE_RE = re.compile(r'[Uu]ser (?:said|stated):\s*"([^"]+)"')


def _validate_decisions(atoms_text: str, src: Path) -> tuple[str, int]:
    """Demote fabricated decisions to recommendations.

    A decision atom is trusted ONLY if its quoted user words are
    found verbatim inside a user block ("#### Вы сказали:") of the
    source chat; on exports without user-block markers (drift
    #80/#81) the quote must at least exist verbatim somewhere in the
    source — speaker attribution then rests on the prompt's DECISION
    TEST (the format-agnostic fallback). The quote is searched across
    the WHOLE ATOM (the
    statement line plus its continuation lines), not just the line
    that carries the Status label: the archivist prompt puts the
    quote in the atom body, which spans lines (component B,
    2026-09-08: a genuine verbatim quote was demoted because Status
    and quote sat on different lines). Fabricated quotes (LLM
    hallucination) and quotes lifted from assistant replies still
    fail and are demoted — the safe direction: an under-counted
    decision is recoverable, a fabricated one poisons the memory.
    Returns (validated text, number of demoted lines).
    """
    source = src.read_text(encoding="utf-8", errors="replace")
    user_blocks = [m.group(1) for m in _USER_BLOCK_RE.finditer(source)]
    demoted = 0
    lines = atoms_text.splitlines()
    for idx, line in enumerate(lines):
        if not _DECISION_RE.search(line):
            continue
        start, end = _atom_bounds(lines, idx)
        quote_m = _QUOTE_RE.search("\n".join(lines[start : end + 1]))
        quote = quote_m.group(1) if quote_m else ""
        if quote and len(quote) <= 120:
            if user_blocks:
                # ChatGPT-format export: speaker attribution is
                # verified against the user blocks.
                if any(quote in block for block in user_blocks):
                    continue
            elif quote in source:
                # Export without user-block markers (drift #80/#81):
                # the quote exists verbatim; attribution rests on the
                # prompt's DECISION TEST. Recovers genuine decisions on
                # unknown formats; a misattributed assistant quote
                # passes only where no markers exist at all.
                continue
        lines[idx] = _DECISION_RE.sub("Status: recommendation", line)
        demoted += 1
    return "\n".join(lines), demoted


def _atom_bounds(lines: list[str], idx: int) -> tuple[int, int]:
    """Line range [start, end] of the atom containing lines[idx].

    An atom is a statement line (see _ATOM_START_RE) plus its
    continuation lines (labels, quotes). Scanning UP, a statement
    line is the atom's OWN start and belongs to the range; scanning
    DOWN, a statement line is the NEXT atom's start and bounds it.
    Blank lines, headers and part separators ("---") bound both
    directions. Used by the demotion to search a decision's quote
    in the whole atom body, mirroring the prompt contract ("the
    quote lives in the atom body") rather than the Status line
    alone.
    """
    start = idx
    if _ATOM_START_RE.match(lines[idx]) is None:
        while start > 0:
            prev = lines[start - 1]
            if _ATOM_START_RE.match(prev) is not None:
                start -= 1
                break
            if (
                not prev.strip()
                or prev.lstrip().startswith("#")
                or prev.strip().startswith("---")
            ):
                break
            start -= 1
    end = idx
    while end < len(lines) - 1:
        nxt = lines[end + 1]
        if (
            not nxt.strip()
            or nxt.lstrip().startswith("#")
            or nxt.strip().startswith("---")
            or _ATOM_START_RE.match(nxt) is not None
        ):
            break
        end += 1
    return start, end


def _dedup_atoms(atoms_text: str) -> tuple[str, int]:
    """Remove exact duplicate atoms across parts.

    Parts are independent LLM requests: the model never sees the other
    parts' answers, so the prompt's FINAL instruction to "merge
    duplicate atoms from all parts" is structurally unfulfillable and
    cross-part duplicates survive. An atom is identified by its
    normalized WHOLE block (statement plus continuation lines via
    _atom_bounds, whitespace collapsed, lowercased): the same statement
    with a different Context is a DIFFERENT atom and survives —
    dropping it would lose knowledge (dev-2024-03 vs prod-2024-08
    configurations). Only exact block duplicates are removed —
    semantic near-duplicates stay for the reranker to handle.
    Returns (deduped text, removed atom count).
    """
    seen: set[str] = set()
    lines = atoms_text.splitlines()
    out: list[str] = []
    removed = 0
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if _ATOM_START_RE.match(line) is not None:
            _start, end = _atom_bounds(lines, idx)
            key = re.sub(
                r"\s+", " ", "\n".join(lines[idx : end + 1]).strip().lower()
            )
            if key in seen:
                removed += 1
                idx = end + 1
                continue
            seen.add(key)
        out.append(line)
        idx += 1
    return "\n".join(out), removed


def _split_for_atoms(data: bytes, part_bytes: int) -> list[bytes]:
    """Split raw bytes into ~part_bytes parts at line boundaries.

    The atoms path feeds parts to the LLM, whose limit is the token
    context window -- not the watcher's byte/timeout budget that
    PART_BYTES serves. part_bytes comes from the archivist config.
    Seam logic mirrors split_file, but the tolerance is tighter
    (// 4, not // 2): the atoms part budget is a hard token-window
    constraint, and an overshoot spends the answer headroom (a
    17041-byte part on a 12000 budget was measured 2026-09-03).
    """
    if len(data) <= part_bytes:
        return [data]
    parts: list[bytes] = []
    start = 0
    total = len(data)
    while start < total:
        end = min(start + part_bytes, total)
        if end < total:
            newline = data.find(b"\n", end)
            if newline != -1 and newline - end < part_bytes // 4:
                end = newline + 1
            else:
                # Never cut inside a UTF-8 multi-byte character: the
                # part is decoded with errors="replace" in make_atoms,
                # and a mid-character cut corrupts one letter at each
                # seam side. Advance to the next character boundary.
                while end < total and (data[end] & 0xC0) == 0x80:
                    end += 1
        parts.append(data[start:end])
        start = end
    return parts


def make_atoms(src: Path, dest_dir: Path) -> Path:
    """Extract knowledge atoms from a chat export via the local LLM.

    Splits the source into parts, sends each to the LLM with the
    archivist prompt (the last one marked FINAL for dedup),
    concatenates the answers into a single atoms-{stem}.md file.
    Returns the created file path. The raw source is not modified.
    """
    data = src.read_bytes()
    cfg = _load_archivist_cfg()
    parts = _split_for_atoms(data, part_bytes=int(cfg["part_bytes"]))
    answers: list[str] = []
    total = len(parts)
    print(f"[ATOMS] {src.name}: {total} part(s), {len(data)} bytes")
    for idx, part in enumerate(parts, start=1):
        is_final = idx == total
        header = f"PART {idx}/{total}"
        if is_final:
            header += "\nFINAL"
        user_content = (
            f"{ARCHIVIST_PROMPT}\n\n{header}\n\n"
            f"{part.decode('utf-8', errors='replace')}"
        )
        payload = {
            "messages": [{"role": "user", "content": user_content}],
            "temperature": float(cfg["temperature"]),
        }
        model_name = cfg["llm_model"]
        model_name = str(model_name).strip() if model_name is not None else ""
        if model_name:
            payload["model"] = model_name
        print(f"[ATOM] part {idx}/{total} -> LLM ({len(part)} bytes)")
        resp = httpx.post(
            str(cfg["llm_api_base"]), json=payload, timeout=float(cfg["timeout"])
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"] or ""
        if answer.strip():
            answers.append(answer.strip())
    target = dest_dir / f"atoms-{src.stem}{src.suffix}"
    atoms_text = "\n\n---\n\n".join(answers)
    atoms_text, deduped = _dedup_atoms(atoms_text)
    atoms_text, demoted = _validate_decisions(atoms_text, src)
    atoms_text, ungrounded = _ground_dates(atoms_text, src)
    if deduped:
        print(f"[ATOMS] dedup: {deduped} duplicate atom(s) across parts removed")
    if demoted:
        print(
            f"[ATOMS] validator: {demoted} fabricated/assistant-voiced "
            "decision(s) demoted to recommendation"
        )
    if ungrounded:
        print(
            f"[ATOMS] date-guard: {ungrounded} ungrounded date(s) removed "
            "from Context/as-of/Chronology (drift #80/#81)"
        )
    target.write_text(atoms_text, encoding="utf-8")
    print(f"[ATOMS] {len(answers)} answer block(s) -> {target.name}")
    return target


# Markdown image noise from AI-service exports: the full ![alt](url)
# tag and the favicon-wrapped [![](favicon)](link) variant. Pure
# export artifacts — no retrieval value, half the bytes of a typical
# export. Code spans/blocks are NOT touched. Byte pattern: the image
# URL alphabet is ASCII, and splitting operates on bytes.
_MD_IMAGE_BYTES_RE = re.compile(
    rb"!?\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\([^)]*\)"
)


def _strip_markdown_noise(raw: bytes) -> bytes:
    """Remove markdown image noise from raw bytes.

    Idempotent: a second pass finds nothing. Returns the input object
    unchanged when no match exists (the fast-path guards).
    """
    if b"](" not in raw and b"![" not in raw:
        return raw
    return _MD_IMAGE_BYTES_RE.sub(b"", raw)


def split_file(src: Path, dest_dir: Path) -> list[Path]:
    """Split src into parts of ~PART_BYTES at line boundaries.

    Returns the list of created part files. Files under the
    threshold are copied as-is (single "part"). Markdown image noise
    (![...](url) and their favicon wrappers) is stripped BEFORE
    splitting, on every path (split-only included): image links are
    pure embedding-export noise, they burn the token budget and add
    nothing to retrieval.
    """
    raw = src.read_bytes()
    stem = src.stem
    data = _strip_markdown_noise(raw)

    # Reconcile FIRST: remove split outputs impossible for the current
    # source size — the stale as-is copy of a file that grew past the
    # threshold (the watcher would index BOTH versions). Runs inside
    # split_file so every caller (CLI, menu, tests) is covered, not
    # just the main() loop path.
    _reconcile_outputs(src, dest_dir)

    # Stale-output sweep: a previous run on a longer version of this
    # source may have left more parts than this run creates. Remove
    # them so a rerun after an edit never leaves old parts behind.
    for stale in dest_dir.glob(glob.escape(stem) + "_part*" + src.suffix):
        stale.unlink()

    if len(data) <= THRESHOLD_BYTES:
        target = dest_dir / f"{stem}{src.suffix}"
        target.write_bytes(data)
        print(f"[SKIP] {src.name}: {len(data)} bytes <= threshold, copied as-is")
        return [target]

    parts: list[Path] = []
    start = 0
    idx = 1
    total = len(data)
    while start < total:
        end = min(start + PART_BYTES, total)
        if end < total:
            # Extend to the next newline so sentences stay intact.
            newline = data.find(b"\n", end)
            if newline != -1 and newline - end < PART_BYTES // 2:
                end = newline + 1
        chunk = data[start:end]
        target = dest_dir / f"{stem}_part{idx:02d}{src.suffix}"
        target.write_bytes(chunk)
        parts.append(target)
        print(f"[PART] {target.name}: {len(chunk)} bytes")
        start = end
        idx += 1
    return parts


def _reconcile_outputs(src: Path, dest_dir: Path) -> None:
    """Remove split outputs impossible for the current source size.

    A source that grew past THRESHOLD_BYTES leaves its old as-is
    copy next to the new parts — the watcher would index BOTH
    versions (duplicate, contradictory retrieval). A source that
    shrank below the threshold is swept by split_file's rewrite
    path; this covers the copy-side drift on skip passes too.
    """
    asis = dest_dir / f"{src.stem}{src.suffix}"
    if src.stat().st_size <= THRESHOLD_BYTES:
        for stale in dest_dir.glob(glob.escape(src.stem) + "_part*" + src.suffix):
            stale.unlink()
    elif asis.exists():
        asis.unlink()


def _needs_processing(src: Path, dest_dir: Path, atoms: bool, split: bool) -> bool:
    """Return True if the source must be (re)processed.

    Freshness rule: the source is newer than its output layer, or an
    output layer is missing. Unchanged sources are skipped entirely
    (idempotent reruns cost nothing). Note: indices (data/indices)
    are NOT an output layer -- wiping them triggers a full reindex
    via the watcher without touching this script's outputs.
    """
    src_mtime = src.stat().st_mtime
    if split:
        # Mirror split_file's naming: small files are copied as-is
        # ({stem}{suffix}); big files become {stem}_part01... A
        # part01 marker never exists for a small file, so every
        # rerun re-copied it, re-ran atoms (--full) and re-triggered
        # the watcher reindex (2026-09-03).
        if src.stat().st_size <= THRESHOLD_BYTES:
            marker = dest_dir / f"{src.stem}{src.suffix}"
        else:
            marker = dest_dir / f"{src.stem}_part01{src.suffix}"
        if not marker.exists() or marker.stat().st_mtime < src_mtime:
            return True
    if atoms:
        atoms_file = dest_dir / f"atoms-{src.stem}{src.suffix}"
        if not atoms_file.exists() or atoms_file.stat().st_mtime < src_mtime:
            return True
    return False


# ============================================================================
# Static atom validation (--validate): the format-agnostic contract layer.
#
# The demotion above is ChatGPT-format-bound (_USER_BLOCK_RE); on
# ####-less exports it is silent, and drift #81 proved that silence
# leaves decisions unprotected. The checks below run over the atoms
# OUTPUT and do not care about the source export format. Read-only.
# Atom shapes (validated against live atoms files, 2026-09-08): the
# "(Context: ...; Status: ...)" fragment may sit on the statement
# line, inside the bracketed statement, or on a continuation line;
# statements may or may not carry "-"/"**" markers -- all accepted.
# ============================================================================

_RECOMMENDATION_STATUS_RE = re.compile(r"Status:\s*recommendation\b")

# An atom starts at a statement line in any of the observed shapes:
# bulleted or plain, bold-bracketed or plain-bracketed. Continuation
# lines (labels, quotes, fenced code) follow until a blank line, a
# section header, or the next statement line.
_ATOM_START_RE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*\s*)?\[")

# Template fragments removed before script counting (V5): the
# "(Context: ...)" / "(...; Status: ...)" parenthetical may sit on the
# statement line, inside the bracketed statement, or on its own
# continuation line. Quotes are NOT removed: they are chat content.
_LABEL_PAREN_RE = re.compile(r"\([^()]*\b(?:Context|Status)\b[^()]*\)")

# "(as of [date])" markers on current-state numbers (archivist prompt):
# the whole marker is dropped when its date is ungrounded — without the
# date the marker is meaningless (date guard, drift #80/#81).
_AS_OF_PAREN_RE = re.compile(r"\(\s*[Aa]s of\b[^()]*\)")

# Russian month names, nominative + genitive ("1 мая", "мая 2024").
# Domain constants: the LANGUAGE rule exempts them from the
# no-Cyrillic rule (_USER_BLOCK_RE above carries the same kind).
_RU_MONTHS: dict[str, int] = {
    "январь": 1, "января": 1,
    "февраль": 2, "февраля": 2,
    "март": 3, "марта": 3,
    "апрель": 4, "апреля": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7,
    "август": 8, "августа": 8,
    "сентябрь": 9, "сентября": 9,
    "октябрь": 10, "октября": 10,
    "ноябрь": 11, "ноября": 11,
    "декабрь": 12, "декабря": 12,
}
_EN_MONTHS: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3,
    "mar": 3, "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sep": 9, "sept": 9, "october": 10, "oct": 10, "november": 11,
    "nov": 11, "december": 12, "dec": 12,
}
_RU_MONTHS_ALT = "|".join(sorted(_RU_MONTHS, key=len, reverse=True))
# EN months must match CAPITALIZED forms only ("May 1", "Aug 22"):
# the lowercase "may 12 people" prose stays out. Built via
# .capitalize() because the dict keys are lowercase (the lookup side
# lowercases too); building from the raw keys matched nothing
# (2026-09-08, caught by test_extraction_forms).
_EN_MONTHS_CAPS = [name.capitalize() for name in _EN_MONTHS]
_EN_MONTHS_ALT = "|".join(sorted(_EN_MONTHS_CAPS, key=len, reverse=True))
_YEAR = r"(?:19|20)\d{2}"

# One alternation, most specific first: finditer is left-to-right,
# so "2026-08-07" matches iso (not the bare year), "May 1, 2024"
# matches en_md (not en_my). EN months are case-sensitive to keep
# prose "may 12 people" out; RU months are case-insensitive (a
# capital "Мая" at a sentence start is legal).
_DATE_RE = re.compile(
    rf"""
    (?P<iso>\b(?P<iso_y>{_YEAR})-(?P<iso_m>\d{{1,2}})-(?P<iso_d>\d{{1,2}})\b)
   |(?P<isoym>\b(?P<isoym_y>{_YEAR})-(?P<isoym_m>\d{{1,2}})\b)
   |(?P<dot>\b(?P<dot_d>\d{{1,2}})\.(?P<dot_m>\d{{1,2}})\.(?P<dot_y>{_YEAR})\b)
   |(?P<ru>(?i:\b(?:(?P<ru_d>\d{{1,2}})\s+)?(?P<ru_m>{_RU_MONTHS_ALT})
      (?:\s+(?P<ru_y>{_YEAR}))?\b))
   |(?P<unix>\b(?P<unix_m>{_EN_MONTHS_ALT})\s+(?P<unix_d>\d{{1,2}})\s+
      \d{{1,2}}:\d{{2}}(?::\d{{2}})?\s+(?P<unix_y>{_YEAR})\b)
   |(?P<en_md>\b(?P<en_md_m>{_EN_MONTHS_ALT})\s+(?P<en_md_d>\d{{1,2}})\b
      (?:[,\s]+(?P<en_md_y>{_YEAR})\b)?)
   |(?P<en_dm>\b(?P<en_dm_d>\d{{1,2}})\s+(?P<en_dm_m>{_EN_MONTHS_ALT})\b
      (?:[,\s]+(?P<en_dm_y>{_YEAR})\b)?)
   |(?P<en_my>\b(?P<en_my_m>{_EN_MONTHS_ALT}),?\s+(?P<en_my_y>{_YEAR})\b)
   |(?P<year>\b(?P<year_y>{_YEAR})\b)
    """,
    re.VERBOSE,
)

# V5 thresholds: below _MIN_FILE_LETTERS the dominant script is
# undecidable; short atoms are not language-checked (EN terms inside
# RU atoms are legal -- the archivist prompt asks for EN/RU pairs).
_MIN_FILE_LETTERS = 100
_MIN_ATOM_LETTERS = 20
_FOREIGN_SCRIPT_RATIO = 0.6

# The Cyrillic letters in this class are the very thing being
# detected: an intentional lookalike, not a homoglyph bug (RUF001).
_CYR_RE = re.compile(r"[а-яёА-ЯЁ]")  # noqa: RUF001
_LAT_RE = re.compile(r"[a-zA-Z]")
# All three dash variants are intentional separator forms seen in
# live Chronology lines (RUF001: the en dash looks like the hyphen
# next to it).
_CHRON_SEP_RE = re.compile(r"\s+[-—–]\s+")  # noqa: RUF001

# Mirrors rag.sources.include in config.yaml (["*.md", "*.txt"]).
# If the watcher contract changes, this constant follows it.
_INDEXED_SUFFIXES = (".md", ".txt")


@dataclass(frozen=True)
class DateToken:
    """A normalized date; None components mean "not stated"."""

    year: int | None
    month: int | None
    day: int | None


@dataclass(frozen=True)
class DateHit:
    """A date token found in text, with its 1-based line number."""

    line: int
    text: str
    date: DateToken


@dataclass(frozen=True)
class Violation:
    """One finding: file, check id, severity, line, message."""

    file: str
    check: str
    severity: str
    line: int | None
    message: str


def _violation_sort_key(v: Violation) -> tuple[str, str, int, str]:
    return (v.file, v.check, v.line or 0, v.message)


def _iter_atoms(text: str) -> Iterator[tuple[str, int, str]]:
    """Yield (section, 1-based start line, atom text) for every atom.

    An atom starts at a statement line (see _ATOM_START_RE) and
    continues through plain and indented continuation lines (labels,
    quotes, fenced code) until a blank line, a "#" header, or the
    next statement line. Section is the last seen "##" header,
    lowercased ("" before the first header). Non-atom lines between
    atoms (sentinels, "---" part separators) are skipped.
    """
    section = ""
    current: list[str] = []
    start = 0
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            if current:
                yield section, start, "\n".join(current)
                current = []
            section = stripped.lstrip("#").strip().lower()
            continue
        if _ATOM_START_RE.match(line) is not None:
            if current:
                yield section, start, "\n".join(current)
            current = [line]
            start = idx
            continue
        if not stripped:
            if current:
                yield section, start, "\n".join(current)
                current = []
            continue
        if current:
            current.append(line)
    if current:
        yield section, start, "\n".join(current)


def _match_to_token(match: re.Match[str]) -> DateToken | None:
    """Convert one regex match to a DateToken; None if out of range."""
    year: int | None
    month: int | None
    day: int | None
    if match.group("iso") is not None:
        year = int(match.group("iso_y"))
        month = int(match.group("iso_m"))
        day = int(match.group("iso_d"))
    elif match.group("isoym") is not None:
        year = int(match.group("isoym_y"))
        month = int(match.group("isoym_m"))
        day = None
    elif match.group("dot") is not None:
        year = int(match.group("dot_y"))
        month = int(match.group("dot_m"))
        day = int(match.group("dot_d"))
    elif match.group("ru") is not None:
        month = _RU_MONTHS[match.group("ru_m").lower()]
        day = int(match.group("ru_d")) if match.group("ru_d") else None
        year = int(match.group("ru_y")) if match.group("ru_y") else None
    elif match.group("unix") is not None:
        month = _EN_MONTHS[match.group("unix_m").lower()]
        day = int(match.group("unix_d"))
        year = int(match.group("unix_y"))
    elif match.group("en_md") is not None:
        month = _EN_MONTHS[match.group("en_md_m").lower()]
        day = int(match.group("en_md_d"))
        year = int(match.group("en_md_y")) if match.group("en_md_y") else None
    elif match.group("en_dm") is not None:
        month = _EN_MONTHS[match.group("en_dm_m").lower()]
        day = int(match.group("en_dm_d"))
        year = int(match.group("en_dm_y")) if match.group("en_dm_y") else None
    elif match.group("en_my") is not None:
        year = int(match.group("en_my_y"))
        month = _EN_MONTHS[match.group("en_my_m").lower()]
        day = None
    else:
        year = int(match.group("year_y"))
        month = None
        day = None
    if month is not None and not 1 <= month <= 12:
        return None
    if day is not None and not 1 <= day <= 31:
        return None
    return DateToken(year=year, month=month, day=day)


def _parse_date_tokens(text: str) -> tuple[tuple[str, DateToken], ...]:
    """Extract (matched text, normalized date) pairs from text."""
    tokens: list[tuple[str, DateToken]] = []
    for match in _DATE_RE.finditer(text):
        token = _match_to_token(match)
        if token is not None:
            tokens.append((match.group(0), token))
    return tuple(tokens)


def extract_dates(text: str) -> tuple[DateHit, ...]:
    """Extract date tokens with 1-based line numbers (for reports)."""
    hits: list[DateHit] = []
    for match in _DATE_RE.finditer(text):
        token = _match_to_token(match)
        if token is None:
            continue
        line = text.count("\n", 0, match.start()) + 1
        hits.append(DateHit(line=line, text=match.group(0), date=token))
    return tuple(hits)


def _covers(source: DateToken, atom: DateToken) -> bool:
    """True if the source date grounds the atom date (never invent).

    Every component the atom states must be present in the source
    and equal; components the atom omits are unconstrained. An atom
    date more precise than the source is an invention.
    """
    for atom_part, source_part in (
        (atom.year, source.year),
        (atom.month, source.month),
        (atom.day, source.day),
    ):
        if atom_part is not None and source_part != atom_part:
            return False
    return True


def _ground_dates(atoms_text: str, src: Path) -> tuple[str, int]:
    """Strip ungrounded date tokens from template structures at birth.

    Producer-side twin of V2 (the _validate_decisions pattern): the
    archivist's stable invented dates are parametric beliefs of the
    model class (#87) — re-atomization re-inserts them, and V2 only
    reports (repair is a manual owner action, drift #86). Scope is
    bounded to prompt-defined structures: the "(Context: ...; Status:
    ...)" parenthetical, "(as of ...)" markers, and Chronology lines.
    Dates in free prose are left for V2 — removing text from prose is
    not safe surgery. A token is grounded when it appears verbatim in
    the source OR is covered by a parsed source date (_covers: an atom
    date more precise than the source is an invention). Stripping
    loses precision, never truth: a "when" question gets an evasive
    answer (atoms-undated-1, known model limitation) instead of a
    false date. Returns (grounded text, removed token count).
    """
    source = src.read_text(encoding="utf-8", errors="replace")
    source_dates = frozenset(tok for _, tok in _parse_date_tokens(source))

    def _grounded(match: re.Match[str]) -> bool:
        if match.group(0) in source:
            return True
        token = _match_to_token(match)
        if token is None:
            return True
        return any(_covers(src_tok, token) for src_tok in source_dates)

    removed = 0

    def _strip(fragment: str) -> str:
        def _repl(match: re.Match[str]) -> str:
            nonlocal removed
            if _grounded(match):
                return match.group(0)
            removed += 1
            return ""

        return _DATE_RE.sub(_repl, fragment)

    def _fix_label_paren(match: re.Match[str]) -> str:
        fixed = _strip(match.group(0))
        # Tidy separators the removal leaves behind:
        # "(Context: , project; Status: fact)" -> "(Context: project; ...)"
        fixed = re.sub(r":\s*,\s*", ": ", fixed)
        fixed = re.sub(r",\s*,\s*", ", ", fixed)
        return re.sub(r"\s{2,}", " ", fixed)

    def _fix_as_of_paren(match: re.Match[str]) -> str:
        """Drop the whole "(as of ...)" marker when its date is ungrounded."""
        nonlocal removed
        keep = True
        for m in _DATE_RE.finditer(match.group(0)):
            if not _grounded(m):
                removed += 1
                keep = False
        return match.group(0) if keep else ""

    lines = atoms_text.splitlines()
    out: list[str] = []
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            if stripped.startswith("#"):
                section = stripped.lstrip("#").strip().lower()
            out.append(line)
            continue
        if section.startswith("chronology"):
            fixed = _strip(line)
            if fixed != line:
                # A Chronology line leads with its date; drop the
                # separator the removal leaves: " - topic - outcome".
                fixed = re.sub(r"^\s*[-—–]\s*", "", fixed)  # noqa: RUF001
                fixed = re.sub(r"\s{2,}", " ", fixed)
                fixed = re.sub(r"\s+([.,;])", r"\1", fixed)
            out.append(fixed)
            continue
        fixed = _LABEL_PAREN_RE.sub(_fix_label_paren, line)
        fixed = _AS_OF_PAREN_RE.sub(_fix_as_of_paren, fixed)
        if fixed != line:
            fixed = re.sub(r"\s{2,}", " ", fixed)
            fixed = re.sub(r"\s+([.,;])", r"\1", fixed)
        out.append(fixed)
    return "\n".join(out), removed


def _conflicts(first: DateToken, second: DateToken) -> bool:
    """True if two dates cannot describe the same day.

    Components both dates state must agree; a missing component on
    either side is compatible (different precision, same date).
    """
    for left, right in (
        (first.year, second.year),
        (first.month, second.month),
        (first.day, second.day),
    ):
        if left is not None and right is not None and left != right:
            return True
    return False


def _check_decisions(text: str, fname: str) -> tuple[Violation, ...]:
    """V1: THE DECISION TEST -- a decision atom needs a user quote.

    Uses the same _DECISION_RE/_QUOTE_RE as the pipeline demotion:
    one point of truth for the decision contract. Speaker
    attribution (the quote coming from a USER block) stays in the
    demotion -- verifying it requires the source export format.
    """
    out: list[Violation] = []
    for _section, start, atom in _iter_atoms(text):
        if _DECISION_RE.search(atom) is None:
            continue
        quote_match = _QUOTE_RE.search(atom)
        if quote_match is None or not quote_match.group(1).strip():
            out.append(Violation(
                file=fname,
                check="V1",
                severity="error",
                line=start,
                message=(
                    "decision atom without a quoted user acceptance "
                    '(User said/stated: "...")'
                ),
            ))
    return tuple(out)


def _check_creative(text: str, fname: str) -> tuple[Violation, ...]:
    """V4: recommendations do not belong in Creative Materials."""
    out: list[Violation] = []
    for section, start, atom in _iter_atoms(text):
        if not section.startswith("creative materials"):
            continue
        if _RECOMMENDATION_STATUS_RE.search(atom) is not None:
            out.append(Violation(
                file=fname,
                check="V4",
                severity="error",
                line=start,
                message=(
                    "recommendation atom inside ## Creative Materials "
                    "(misfiled: the section holds ready creative texts only)"
                ),
            ))
    return tuple(out)


def _strip_template(atom: str) -> str:
    """Remove the English template skeleton from an atom.

    Parenthesized label fragments ("(Context: ...)", "(...; Status:
    ...)") are cut from every line, whatever shape the atom takes
    (label on the statement line, inside the bracket, or on a
    continuation line); lines left empty are dropped. Fenced code
    blocks are dropped entirely (verbatim code is content, not
    language). Quotes stay: they are chat content.
    """
    kept: list[str] = []
    in_fence = False
    for line in atom.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        remainder = _LABEL_PAREN_RE.sub("", line)
        if remainder.strip():
            kept.append(remainder)
    return "\n".join(kept)


def _check_script(
    text: str,
    fname: str,
    source_text: str | None = None,
) -> tuple[Violation, ...]:
    """V5: atoms in the source's non-dominant script (drift #67).

    The reference script is the SOURCE chat's, not the atoms file's:
    a model can flip an entire file's language (proved 2026-09-10:
    chasov atoms cyr=0 in an RU chat), which the old file-relative
    check cannot see — and it flagged the surviving CORRECT atoms as
    foreign. Falls back to the file's own dominant script when no
    source is available (the chat's language is then unknowable).
    The dominant script is computed over template-stripped atom
    CONTENT, not raw text: label parens carry English values even in
    RU atoms ("project:", "conditions:") and raw counting flips the
    file's script (first live run, 2026-09-08: 11 false flags on a
    fully RU file). Chronology lines are skipped: they are index
    entries, not atoms.
    """
    contents: list[tuple[int, str]] = [
        (start, _strip_template(atom))
        for section, start, atom in _iter_atoms(text)
        if not section.startswith("chronology")
    ]
    cyrillic_total = sum(len(_CYR_RE.findall(c)) for _, c in contents)
    latin_total = sum(len(_LAT_RE.findall(c)) for _, c in contents)
    source_is_ru: bool | None = None
    if source_text is not None:
        # Strip URLs before counting: chat exports are full of image
        # links, and their latin hostnames would flip an RU source.
        # No thresholds on the source side: even a short chat states
        # its language unambiguously, and a quiet fallback to the
        # FILE's script would hide a whole-file flip (test-caught).
        plain = re.sub(r"https?://\S+", " ", source_text)
        source_is_ru = len(_CYR_RE.findall(plain)) > len(_LAT_RE.findall(plain))
    if (
        source_is_ru is None
        and cyrillic_total + latin_total < _MIN_FILE_LETTERS
    ):
        # No source AND the file itself is too short to have a
        # decidable dominant script — nothing to compare against.
        # With a source the file-size threshold does not apply: the
        # reference is external, only the per-atom minimum guards.
        return ()
    file_is_ru = source_is_ru if source_is_ru is not None else (
        cyrillic_total > latin_total
    )
    out: list[Violation] = []
    for start, content in contents:
        cyrillic = len(_CYR_RE.findall(content))
        latin = len(_LAT_RE.findall(content))
        total = cyrillic + latin
        if total < _MIN_ATOM_LETTERS:
            continue
        foreign = cyrillic if not file_is_ru else latin
        script = "Cyrillic" if not file_is_ru else "Latin"
        if foreign / total >= _FOREIGN_SCRIPT_RATIO:
            out.append(Violation(
                file=fname,
                check="V5",
                severity="error",
                line=start,
                message=(
                    f"{script} atom while the source chat is "
                    f"{'RU' if file_is_ru else 'EN'} "
                    f"({foreign}/{total} letters)"
                ),
            ))
    return tuple(out)


def _norm_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic.strip().lower())


def _check_chronology(text: str, fname: str) -> tuple[Violation, ...]:
    """V3: the same Chronology topic must not carry conflicting dates.

    Monotonicity is deliberately NOT checked: chats legitimately
    revisit old topics. Only a mutual contradiction on the same
    normalized topic is an error (drift #80 class).
    """
    entries: dict[str, list[tuple[DateToken, str, int]]] = {}
    section = ""
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            section = stripped.lstrip("#").strip().lower()
            continue
        if not stripped or not section.startswith("chronology"):
            continue
        tokens = _parse_date_tokens(stripped)
        if not tokens:
            continue
        parts = _CHRON_SEP_RE.split(stripped, maxsplit=2)
        if len(parts) < 2:
            continue
        topic = _norm_topic(parts[1])
        if not topic:
            continue
        date_text, date_token = tokens[0]
        entries.setdefault(topic, []).append((date_token, date_text, idx))
    out: list[Violation] = []
    for topic in sorted(entries):
        items = entries[topic]
        reported = False
        for i in range(len(items) - 1):
            for j in range(i + 1, len(items)):
                first, second = items[i], items[j]
                if _conflicts(first[0], second[0]):
                    out.append(Violation(
                        file=fname,
                        check="V3",
                        severity="error",
                        line=first[2],
                        message=(
                            f"topic '{topic}': conflicting dates "
                            f"'{first[1]}' (line {first[2]}) and "
                            f"'{second[1]}' (line {second[2]})"
                        ),
                    ))
                    reported = True
                    break
            if reported:
                break
    return tuple(out)


def _check_dates(
    text: str,
    fname: str,
    source_text: str | None,
    source_label: str,
) -> tuple[Violation, ...]:
    """V2: every date token in the atoms text must exist in the source.

    A missing source downgrades the check to a single warning:
    provenance unchecked, not proven absent.
    """
    if source_text is None:
        return (Violation(
            file=fname,
            check="V2",
            severity="warn",
            line=None,
            message=(
                f"source not found: {source_label}; "
                "date provenance unchecked"
            ),
        ),)
    source_dates = frozenset(
        token for _, token in _parse_date_tokens(source_text)
    )
    out: list[Violation] = []
    for hit in extract_dates(text):
        if not any(_covers(source, hit.date) for source in source_dates):
            out.append(Violation(
                file=fname,
                check="V2",
                severity="error",
                line=hit.line,
                message=(
                    f"date '{hit.text}' not grounded in source "
                    f"{source_label}"
                ),
            ))
    return tuple(out)


def validate_text(
    text: str,
    fname: str,
    source_text: str | None,
    source_label: str,
) -> tuple[Violation, ...]:
    """Run V1-V5 over one atoms file's text.

    source_text is the raw source chat (date provenance); None
    downgrades V2 to a single warning. source_label names the source
    in messages.
    """
    violations: list[Violation] = []
    violations.extend(_check_decisions(text, fname))
    violations.extend(_check_creative(text, fname))
    violations.extend(_check_script(text, fname, source_text=source_text))
    violations.extend(_check_chronology(text, fname))
    violations.extend(_check_dates(text, fname, source_text, source_label))
    return tuple(sorted(violations, key=_violation_sort_key))


def _relpath_label(path: Path) -> str:
    """Project-relative label for reports (portable output)."""
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def check_index_coverage(
    dest_dir: Path,
    index_dir: Path,
    namespace: str,
) -> tuple[Violation, ...]:
    """V6: documents/ vs index completeness (drift #82-open). Warn-only.

    Static check over {namespace}.store.json -- no faiss binary, no
    server. Chunk identity: the store's metadata.source holds the
    DOCUMENT ID, which indexing.read_sources sets to the file STEM
    (no extension, no directory; empirically confirmed on the live
    index 2026-09-08 -- every store entry is a stem). Expected ids
    therefore cover both the stem and the relative posix uri
    (future-proof if the identity ever carries the path). Sub-checks:
    (a) every indexed-type document in dest_dir has chunks; (b) per
    source, chunk count equals the stored total_chunks -- a partial
    restore is the drift #82 gap; (c) store sources without a file
    on disk are orphans. Blind spots (accepted, warn-only): empty
    and oversized files are skipped by the indexer; total_chunks is
    trusted as per-document.
    """
    if not dest_dir.is_dir():
        return (Violation(
            file="<v6>", check="V6", severity="warn", line=None,
            message=f"dest dir not found: {dest_dir}; V6 skipped",
        ),)
    if not index_dir.is_dir():
        return (Violation(
            file="<v6>", check="V6", severity="warn", line=None,
            message=f"index dir not found: {index_dir}; V6 skipped",
        ),)
    store_file = index_dir / f"{namespace}.store.json"
    if not store_file.is_file():
        return (Violation(
            file=store_file.name, check="V6", severity="warn", line=None,
            message=f"no store for namespace '{namespace}'; V6 skipped",
        ),)
    try:
        data: dict[str, Any] = json.loads(
            store_file.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return (Violation(
            file=store_file.name, check="V6", severity="warn", line=None,
            message=f"unreadable store: {exc}",
        ),)

    totals_by_uri: dict[str, list[int]] = {}
    for chunk in data.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        meta = chunk.get("metadata")
        if not isinstance(meta, dict):
            continue
        uri = meta.get("source")
        if not isinstance(uri, str) or not uri:
            continue
        total = meta.get("total_chunks")
        totals_by_uri.setdefault(uri, []).append(
            total if isinstance(total, int) else -1
        )

    expected_files = sorted(
        path for path in dest_dir.rglob("*")
        if path.is_file() and path.suffix in _INDEXED_SUFFIXES
    )
    store_ids = set(totals_by_uri)
    expected_ids: set[str] = set()
    missing_files: list[Path] = []
    for path in expected_files:
        ids = {path.stem, path.relative_to(dest_dir).as_posix()}
        expected_ids.update(ids)
        if not ids & store_ids:
            missing_files.append(path)

    out: list[Violation] = []
    for path in missing_files:
        out.append(Violation(
            file=path.relative_to(dest_dir).as_posix(),
            check="V6", severity="warn", line=None,
            message=(
                f"document has no chunks in namespace '{namespace}' "
                "(missing from index -- drift #82 class)"
            ),
        ))
    for uri in sorted(store_ids - expected_ids):
        out.append(Violation(
            file=uri, check="V6", severity="warn", line=None,
            message="orphan chunks: source not on disk (stale index entries)",
        ))
    for uri in sorted(totals_by_uri):
        totals = totals_by_uri[uri]
        distinct = sorted(set(totals))
        if len(distinct) > 1:
            out.append(Violation(
                file=uri, check="V6", severity="warn", line=None,
                message=f"inconsistent total_chunks across chunks: {distinct}",
            ))
            continue
        total = distinct[0]
        if total <= 0:
            continue
        if len(totals) != total:
            out.append(Violation(
                file=uri, check="V6", severity="warn", line=None,
                message=(
                    f"{len(totals)} of {total} chunks in index "
                    "(partial restore or duplicate upsert)"
                ),
            ))
    return tuple(out)


def _source_path(atoms_path: Path, src_dir: Path) -> Path:
    """Mirror make_atoms naming: atoms-<name> comes from <name>."""
    name = atoms_path.name
    if name.startswith("atoms-"):
        name = name[len("atoms-"):]
    return src_dir / name


def validate_file(path: Path, src_dir: Path) -> tuple[Violation, ...]:
    """Validate one atoms file against its source chat.

    Sources are read as utf-8-sig with errors replaced: chat exports
    may carry a BOM (drift #46) and be lossy.
    """
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    source = _source_path(path, src_dir)
    source_text: str | None = None
    if source.is_file():
        source_text = source.read_text(
            encoding="utf-8-sig", errors="replace"
        )
    return validate_text(text, path.name, source_text, _relpath_label(source))


def _run_validation(
    files: list[str],
    src_dir: Path,
    dest_dir: Path,
    index_dir: Path,
    namespace: str,
) -> int:
    """CLI body of --validate: check atoms-* files and index coverage."""
    if files:
        atoms_files = [Path(name) for name in files]
    else:
        if not dest_dir.is_dir():
            print(f"[ERROR] dest dir not found: {dest_dir}", file=sys.stderr)
            return 1
        atoms_files = sorted(dest_dir.glob("atoms-*"))
        if not atoms_files:
            print(f"[ERROR] no atoms-* files in {dest_dir}", file=sys.stderr)
            return 1

    violations: list[Violation] = []
    for path in atoms_files:
        if not path.is_file():
            print(f"[ERROR] not a file: {path}", file=sys.stderr)
            return 1
        violations.extend(validate_file(path, src_dir))
    violations.extend(check_index_coverage(dest_dir, index_dir, namespace))

    for violation in sorted(violations, key=_violation_sort_key):
        line_part = f":{violation.line}" if violation.line is not None else ""
        print(
            f"[{violation.check}] {violation.file}{line_part} "
            f"{violation.severity.upper()}: {violation.message}"
        )
    errors = sum(1 for v in violations if v.severity == "error")
    warnings = sum(1 for v in violations if v.severity == "warn")
    print(
        f"[DONE] {len(atoms_files)} file(s) checked: "
        f"{errors} error(s), {warnings} warning(s)"
    )
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to split (default: everything in the source dir; "
        "with --validate: atoms files to check)",
    )
    parser.add_argument(
        "--src",
        default=str(_PROJECT_ROOT / "data" / "raw_documents"),
        help="Source directory with original documents",
    )
    parser.add_argument(
        "--dest",
        default=str(_PROJECT_ROOT / "data" / "documents"),
        help="Destination directory (default: data/documents)",
    )
    parser.add_argument(
        "--atoms",
        action="store_true",
        help="Only extract knowledge atoms (e.g. after a prompt change)",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Split only (same as the default; kept for symmetry)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Atoms + split in one pass (explicit, mature chats)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Check atoms-* files in dest against the atom contract "
        "(V1-V5) and index coverage (V6); read-only",
    )
    parser.add_argument(
        "--index",
        default=str(_PROJECT_ROOT / "data" / "indices"),
        help="Vector store dir for the V6 completeness check",
    )
    parser.add_argument(
        "--namespace",
        default="default",
        help="Namespace checked against documents/ (V6)",
    )
    args = parser.parse_args()

    src_dir = Path(args.src)
    dest_dir = Path(args.dest)

    if args.validate:
        if args.atoms or args.full or args.split:
            print(
                "[ERROR] --validate is mutually exclusive with "
                "--atoms/--split/--full",
                file=sys.stderr,
            )
            return 1
        return _run_validation(
            args.files, src_dir, dest_dir, Path(args.index), args.namespace
        )

    dest_dir.mkdir(parents=True, exist_ok=True)

    targets: list[Path] = []
    if args.files:
        for name in args.files:
            path = Path(name)
            if not path.is_absolute():
                path = src_dir / name
            targets.append(path)
    else:
        if not src_dir.exists():
            print(f"[ERROR] source dir not found: {src_dir}", file=sys.stderr)
            return 1
        targets = sorted(p for p in src_dir.iterdir() if p.is_file())
        if not targets:
            print(f"[ERROR] no files in {src_dir}", file=sys.stderr)
            return 1

    if args.atoms and args.split:
        print("[ERROR] --atoms and --split are mutually exclusive", file=sys.stderr)
        return 1
    if args.atoms and args.full:
        print("[ERROR] --atoms and --full are mutually exclusive", file=sys.stderr)
        return 1

    total_parts = 0
    atoms_errors = 0
    atoms_warnings = 0
    for src in targets:
        if not src.is_file():
            print(f"[ERROR] not a file: {src}", file=sys.stderr)
            return 1
        _reconcile_outputs(src, dest_dir)
        # Default: split only (fast, safe). Atoms are an explicit,
        # just-in-time step (--atoms / --full) on mature chats:
        # extraction costs LLM time and is done once per chat.
        do_atoms = args.atoms or args.full
        do_split = not args.atoms
        if not _needs_processing(src, dest_dir, atoms=do_atoms, split=do_split):
            print(f"[SKIP] {src.name}: output is up to date")
            continue
        if do_atoms:
            make_atoms(src, dest_dir)
            violations = validate_file(
                dest_dir / f"atoms-{src.stem}{src.suffix}", src.parent
            )
            atoms_errors += sum(1 for v in violations if v.severity == "error")
            atoms_warnings += sum(1 for v in violations if v.severity == "warn")
            if not do_split:
                continue
        parts = split_file(src, dest_dir)
        total_parts += len(parts)

    print(f"[DONE] {total_parts} file(s) in {dest_dir}")
    print("[NEXT] watcher picks them up within 60 s; watch app.log for")
    print("       'Documents indexed' lines, one per part.")
    if do_atoms:
        print("       'index.progress' covers the atoms file too.")
    if atoms_errors:
        print(
            f"[ATOMS] {atoms_errors} error(s), {atoms_warnings} warning(s) "
            "in atoms created this run -- run mode [3] for details"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

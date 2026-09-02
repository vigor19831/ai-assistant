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

Usage:
  python scripts/prepare_docs.py              # split everything from
                                              # data/raw_documents/
  python scripts/prepare_docs.py big_chat.md  # split one file from the
                                              # source dir
  python scripts/prepare_docs.py --atoms FILE # extract knowledge atoms
                                              # via the local LLM
  python scripts/prepare_docs.py --full FILE  # atoms + split in one pass
  python scripts/prepare_docs.py --src DIR --dest DIR FILE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

# LLM part budget (atoms path): the consumer is the chat-completions
# context window (server_context_size = 8192 tokens), not the watcher.
# Budget: 8192 - ~800 (archivist instruction) - ~1500 (answer headroom)
# = ~5800 tokens per part; ~3-4 bytes/token for RU/EN chat text ->
# 12 KB fits with headroom for token-dense Cyrillic. Measured fix:
# a 40 KB part was 11963 tokens -> 400 exceed_context_size (2026-09-02).
ATOM_PART_BYTES = 12_000

# The archivist prompt: extracts self-sufficient knowledge atoms
# (facts / decisions / recommendations / hypotheses with status
# discipline) from a chat export. English instructions and structure;
# content keeps the chat's language. Finalized 2026-09-02.
ARCHIVIST_PROMPT = """TASK: turn a chat history into a knowledge base for RAG indexing.

If the chat is long, it will be delivered in parts. Each part is
marked "PART N/M". Process each part by the same rules; in the last
part (marked "FINAL") merge duplicate atoms from all parts and check
the Chronology: every topic from any part must be a Chronology line.
A part with no significant knowledge is also a result: write
"PART N: no significant knowledge found".

=== FILTER (what to remove) ===
Remove only noise: "Copy", "Regenerate", "Thinking", system UI
messages, greetings and farewells without content, glued words
("clien t" -> "client"), duplicates of identical blocks.
Rare code blocks: keep as-is, inside an atom, if the code is part
of a decision.
Do NOT remove: numbers, links, terms, rejected ideas, doubts,
intermediate conclusions, ready creative materials. Removing a
thought loses data. When in doubt, keep it.

=== ATOM (the main rule) ===
Every unit of knowledge = a block of 2-6 sentences, fully
self-sufficient. Atom test: a search engine returned ONLY this
block to the user -- it must fully answer one specific question.

In every atom:
- Resolve all references: pronouns and pointers ("he", "it",
  "above", "as discussed") replaced with concrete entities and
  full names. An atom must not require reading other blocks.
- Date and context -- in the atom text, not in tags or file
  headers: "(Context: date, project/campaign, conditions)".
- Current-state numbers (metrics, rates, CTR, prices, versions)
  marked "(as of [date])".
- Terms: on first mention give both languages when an EN/RU pair
  exists: "CR (konversiya)" / "offer (оффер)" style.
- Ready creative materials (headline/text/offer variants): quote
  them fully -- they are work results, not noise.

Atom format:
- **[Statement]** -- [reasoning/mechanics/numbers].
  (Context: [date, campaign, conditions]; Status: [fact | decision |
  recommendation | hypothesis])

=== STATUSES (strict) ===
- fact: confirmed in the chat.
- decision: ONLY if the user explicitly accepted it. Required: an
  exact quote from the user in this part's text, and it is their
  FINAL word on the topic, not the first reaction. No exact quote --
  not a decision. A quote from the assistant is not the user's
  decision. An already-completed event (commit, launch, edit) is a
  fact, not a decision.
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
Decision atoms with the exact user quote.
## Recommendations (not accepted)
Proposal atoms; rejection reason if stated.
## Hypotheses (not verified in chat)
Assumption atoms with what exactly was not confirmed.
## Creative Materials
Ready texts/headlines/offers from the chat, each with the context
"what it was created for" and a status (used / rejected / draft).
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
_ARCHIVIST_DEFAULTS: dict[str, object] = {
    "llm_api_base": "http://127.0.0.1:8080/v1/chat/completions",
    "llm_model": "",  # empty = omit the field, single-model server
    "temperature": 0.0,
    "timeout": 300.0,
    "part_bytes": 12_000,
}


def _load_archivist_cfg() -> dict[str, object]:
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



def _split_for_atoms(data: bytes, part_bytes: int) -> list[bytes]:
    """Split raw bytes into ~part_bytes parts at line boundaries.

    The atoms path feeds parts to the LLM, whose limit is the token
    context window -- not the watcher's byte/timeout budget that
    PART_BYTES serves. part_bytes comes from the archivist config.
    Seam logic is shared with split_file.
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
            if newline != -1 and newline - end < part_bytes // 2:
                end = newline + 1
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
    for idx, part in enumerate(parts, start=1):
        is_final = idx == total
        header = f"PART {idx}/{total}"
        if is_final:
            header += "\nFINAL"
        user_content = (
            f"{header}\n\n{part.decode('utf-8', errors='replace')}"
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
    target.write_text("\n\n---\n\n".join(answers), encoding="utf-8")
    print(f"[ATOMS] {len(answers)} answer block(s) -> {target.name}")
    return target


def split_file(src: Path, dest_dir: Path) -> list[Path]:
    """Split src into parts of ~PART_BYTES at line boundaries.

    Returns the list of created part files. Files under the
    threshold are copied as-is (single "part").
    """
    data = src.read_bytes()
    stem = src.stem
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
        first_part = dest_dir / f"{src.stem}_part01{src.suffix}"
        if not first_part.exists() or first_part.stat().st_mtime < src_mtime:
            return True
    if atoms:
        atoms_file = dest_dir / f"atoms-{src.stem}{src.suffix}"
        if not atoms_file.exists() or atoms_file.stat().st_mtime < src_mtime:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to split (default: everything in the source dir)",
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
        help="Only split into parts (default: atoms + split)",
    )
    args = parser.parse_args()

    src_dir = Path(args.src)
    dest_dir = Path(args.dest)
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

    total_parts = 0
    for src in targets:
        if not src.is_file():
            print(f"[ERROR] not a file: {src}", file=sys.stderr)
            return 1
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
            if not do_split:
                continue
        parts = split_file(src, dest_dir)
        total_parts += len(parts)

    print(f"[DONE] {total_parts} file(s) in {dest_dir}")
    print("[NEXT] watcher picks them up within 60 s; watch app.log for")
    print("       'Documents indexed' lines, one per part.")
    if do_atoms:
        print("       'index.progress' covers the atoms file too.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

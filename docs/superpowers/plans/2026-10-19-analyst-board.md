# The Analyst Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local app for one PE analyst's first screen of a deal. Haiku reads the teaser and CIM and quotes the
company's numbers; code checks every quote; Opus prices the five worries; and a board shows the call, flip sizes,
pairs and an ask-the-seller list, with live drags.

**Architecture:** A new package `acqlab/app/`. It holds focused modules (ingest, store, verify, prompts, claude,
steps, board, server) and one static HTML page, served by Python's built-in `http.server` on `127.0.0.1`. The engine
and the deal record (`acqlab.agents.record.Record`) are imported and subclassed, never edited. Claude runs through
`claude -p`, with no tools and the documents inline, and answers in JSON.

**Tech Stack:** Python 3.12, pydantic, numpy, `pypdf` (the one new dependency), pytest. The page uses plain
JavaScript and SVG.

**Spec:** `docs/superpowers/specs/2026-10-19-analyst-board-design.md`

## Changes from the spec (found while planning; the user is told before execution)

1. **No tool server and no room shape.** Each Claude step is one tool-less `claude -p` call, with the documents in the
   prompt and a JSON answer. The pricer must return quotes and a reason, which the benchmark's `note_issue` tool
   cannot carry. Everything else the spec names is still reused: the engine, `Record`, the Committer's `norm` and
   `numbers`, `MIN_QUOTE`, `TOL`, `GUIDE`, `DILIGENCE_MAP`, `typical_high`, `routers.score_regret`, `solver.claude_bin`,
   `solver.child_env` and `mix.PRICES`.
2. **One size handle per worry: the top of its range.** The engine prices an open worry as "real with chance p, and
   then anywhere from 0 to the top" (`routers.beliefs.draw`), so a low handle would change nothing.
3. **Opus-judged sizes keep the typical-size floor, as benchmarked.** Only a size the analyst sets ("you set")
   bypasses it.
4. **The second look is Opus running the reader and the pricer again.** The board marks where Opus's numbers differ
   from the board's, and shows the engine's call at the board's numbers with Opus's worries.

## Global Constraints

- Python 3.12. Dependencies are `pydantic`, `numpy`, and `pypdf` (added with `uv add pypdf`). Nothing else.
- Models: `claude-haiku-5-5` reads; `claude-opus-5-5` prices and gives the second look.
- The server binds `127.0.0.1` only.
- Deal folders live under the analyst's home folder, default `~/AcqLab`, and never inside the repo or `data/`.
- No existing `acqlab/` module is edited. S4 stays frozen (tag `s4-frozen-plan5`).
- No real Claude call without the user's OK. Tests use fakes.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never modify settings or permissions files. If a git operation is blocked, stop and report.
- The baseline is 525 tests passing (`.venv/bin/python -m pytest -q`, about 6 minutes). Each task states its new
  total.

## Review Focus

1. **Numbers in thousands or other units** ("$162,798k" with the value 162.8): the quote check leaves them blank and
   never fills in a wrong value. Pinned in Task 2.
2. **A quote citing a document id that doesn't exist:** it is dropped and counted, with no crash. Pinned in Task 2.
3. **Claude answering with prose around the JSON, or with no JSON at all:** the JSON is extracted, or the step fails
   with "failed, try again" and Claude's text. It never crashes the server. Pinned in Task 3.
4. **A tampered or odd request** (price 0, chance 1.5, a negative size, an unknown deal): a 400 or 404 with a message,
   never a 500. Pinned in Tasks 4 and 5.
5. **Two deals with the same name:** each gets its own folder, and neither overwrites the other. Pinned in Task 1.

---

### Task 1: Ingest and storage

**Files:**
- Modify: `pyproject.toml` and `uv.lock` (via `uv add pypdf`)
- Create: `acqlab/app/__init__.py` (empty), `acqlab/app/store.py`, `acqlab/app/ingest.py`
- Test: `tests/app/__init__.py` (empty), `tests/app/pdfs.py`, `tests/app/test_ingest.py`

**Interfaces:**
- Produces:
  - `store.HOME = Path.home() / "AcqLab"`
  - `store.write(path: Path, obj) -> None`: atomic JSON write (a temp file in the same folder, then `os.replace`)
  - `store.load(path: Path, default=None)`: the parsed JSON, or `default` if the file is missing
  - `store.new_deal(home: Path, name: str) -> Path`: creates `home/deals/<slug>` (lowercase letters, digits and
    dashes); if that exists, `<slug>-2`, `<slug>-3` and so on
  - `store.deals(home: Path) -> list[dict]`: each `deal.json` plus `"id"` (the folder name), newest first
  - `ingest.UNREADABLE_CHARS = 20`: a page with fewer stripped characters is unreadable
  - `ingest.class Unreadable(Exception)`
  - `ingest.pages(path: Path) -> list[str]`: page texts. For a `.pdf`, `pypdf.PdfReader(path).pages[i].extract_text()`
    (or `""`). For `.md` or `.txt`, the whole file as one page.
  - `ingest.ingest(home: Path, name: str, price: float, files: dict[str, Path]) -> Path`:
    - `files` has the keys `"teaser"` and `"cim"`
    - it writes `deal.json` `{"name", "price", "created"}` (ISO time), and, for each doc,
      `docs/<id>.json` `{"id", "title", "pages": [...], "unreadable": [page numbers, 1-based]}`
    - titles are `"Teaser"` and `"Confidential Information Memorandum"`
    - it raises `Unreadable` (and creates no folder) when more than half the CIM's pages are unreadable
    - it returns the deal folder
  - `ingest.texts(deal: Path) -> dict[str, str]`: doc id to its pages joined, each page preceded by
    `"[page N]\n"`
- `tests/app/pdfs.py`: `write_pdf(path: Path, pages: list[str | None]) -> Path`. It writes a minimal valid PDF by hand
  (Helvetica, one `BT /F1 12 Tf 72 720 Td (text) Tj ET` stream per page). `None` makes a page with an empty content
  stream, standing in for an image-only page.

- [ ] **Step 1:** Run `uv add pypdf` and confirm `uv.lock` changed and `.venv/bin/python -c "import pypdf"` works.
- [ ] **Step 2: Write the failing tests** in `tests/app/test_ingest.py`:

```python
def test_pdf_pages_reads_text_and_an_image_only_page_reads_empty(tmp_path):
    p = write_pdf(tmp_path / "t.pdf", ["Revenue was 162.8 million dollars", None])
    got = pages(p)
    assert len(got) == 2 and "162.8" in got[0] and got[1].strip() == ""

def test_ingest_writes_the_docs_and_the_deal(tmp_path):
    t = tmp_path / "teaser.md"; t.write_text("Teaser text with LTM revenue of $162.8M")
    c = write_pdf(tmp_path / "cim.pdf", ["CIM page one, long enough to read", None, "page three text here ok"])
    deal = ingest(tmp_path / "home", "Cedar Harbor", 221.5, {"teaser": t, "cim": c})
    assert load(deal / "deal.json")["price"] == 221.5
    cim = load(deal / "docs" / "cim.json")
    assert cim["unreadable"] == [2] and len(cim["pages"]) == 3
    assert texts(deal)["teaser"].startswith("[page 1]\n")

def test_ingest_stops_when_most_of_the_cim_is_unreadable(tmp_path):
    c = write_pdf(tmp_path / "cim.pdf", [None, None, "only this page has text on it"])
    t = tmp_path / "t.md"; t.write_text("teaser")
    with pytest.raises(Unreadable):
        ingest(tmp_path / "home", "X", 100.0, {"teaser": t, "cim": c})
    assert not (tmp_path / "home" / "deals").exists() or not any((tmp_path / "home" / "deals").iterdir())

def test_two_deals_with_the_same_name_get_their_own_folders(tmp_path):
    a, b = new_deal(tmp_path, "Cedar Harbor"), new_deal(tmp_path, "Cedar Harbor")
    assert a != b and a.name == "cedar-harbor" and b.name == "cedar-harbor-2"

def test_write_is_atomic_and_load_falls_back_to_the_default(tmp_path):
    write(tmp_path / "x.json", {"a": 1})
    assert load(tmp_path / "x.json") == {"a": 1} and load(tmp_path / "y.json", {}) == {}
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]
```

- [ ] **Step 3:** Run `.venv/bin/python -m pytest tests/app/test_ingest.py -q`. Expected: it fails on import errors.
- [ ] **Step 4:** Implement `tests/app/pdfs.py`, `store.py` and `ingest.py` to the interfaces above. `ingest` checks
  that the CIM is readable before calling `new_deal`.
- [ ] **Step 5:** Run the same command. Expected: 5 passed.
- [ ] **Step 6:** Commit: `feat: analyst board ingest and storage: PDFs and text into local deal folders`.
  The full suite now passes 530 tests.

### Task 2: The quote check

**Files:**
- Create: `acqlab/app/verify.py`
- Test: `tests/app/test_verify.py`

**Interfaces:**
- Consumes: `acqlab.agents.committer.norm`, `numbers`, `MIN_QUOTE`, `TOL`.
- Produces:
  - `verify.FIELDS = ("revenue_ltm", "reported_ebitda", "claimed_addbacks", "adj_ebitda", "growth", "capex_pct",
    "nwc_pct", "da_pct", "tax_rate")`
  - `verify.OPS = {"sum": a+b, "difference": a-b, "product": a*b, "divide": a/b}` (lambdas)
  - `verify.quote_ok(q: dict, texts: dict[str, str]) -> bool`: `q["doc_id"]` is in `texts`, and `norm(q["text"])` is
    at least `MIN_QUOTE` characters and a substring of `norm(texts[doc_id])`
  - `verify.has(x: float, q: dict) -> bool`: `x` is within `TOL` (or relative 1e-6) of some number in
    `numbers(q["text"])`
  - `verify.check_number(answer: dict | None, texts) -> dict`, returning
    `{"value": float | None, "status": "quoted" | "calculated" | "blank" | "conflict", "quotes": [...], "calc": str,
    "inputs": [...], "why": str}`, with `answer` in the reader's per-field shape (`acqlab/app/prompts.py`):
    - **quoted:** `calc == "none"`, a non-null value, at least one quote, and every quote `quote_ok` and `has(value)`
    - **calculated:** `calc` in `OPS`, two inputs and two quotes, each quote `quote_ok` and `has` its own input, and
      `OPS[calc](*inputs)` within relative 1e-3 of the value
    - **conflict:** the value checks out, but some `other_values` entry has a checked quote whose value differs from
      it by more than `TOL`. The value becomes None, and the quotes list holds all the checked quotes.
    - **blank** otherwise, with `why` one of `"not stated"`, `"quote not found"`, `"number not in quote"`,
      `"calculation doesn't check"`
  - `verify.check_quotes(quotes: list[dict], texts) -> tuple[list[dict], int]`: the quotes that pass `quote_ok`, and
    how many were dropped

- [ ] **Step 1: Write the failing tests**, with
  `TEXTS = {"cim": "[page 1]\nLTM revenue of $162.8M grew 7.7% a year. Capex was $7.8M last year.\nRevenue last year: $162,798 thousand.", "teaser": "[page 1]\nRevenue: $160.0M (LTM)"}`:

```python
def q(doc, text): return {"doc_id": doc, "text": text}
def ans(value, quotes, calc="none", inputs=(), other=()):
    return {"value": value, "quotes": list(quotes), "calc": calc, "inputs": list(inputs), "other_values": list(other)}

def test_a_quoted_number_is_filled_in():
    r = check_number(ans(162.8, [q("cim", "LTM revenue of $162.8M grew")]), TEXTS)
    assert (r["status"], r["value"]) == ("quoted", 162.8)

def test_a_percentage_is_checked_as_its_fraction():
    assert check_number(ans(0.077, [q("cim", "grew 7.7% a year")]), TEXTS)["status"] == "quoted"

def test_a_calculated_number_shows_its_inputs():
    r = check_number(ans(7.8 / 162.8, [q("cim", "Capex was $7.8M last year"), q("cim", "LTM revenue of $162.8M")],
                         calc="divide", inputs=[7.8, 162.8]), TEXTS)
    assert r["status"] == "calculated" and r["inputs"] == [7.8, 162.8]

def test_no_quote_or_null_value_is_blank():
    assert check_number(ans(None, []), TEXTS)["why"] == "not stated"
    assert check_number(None, TEXTS)["status"] == "blank"

def test_a_quote_not_in_the_text_is_blank():
    assert check_number(ans(162.8, [q("cim", "LTM revenue of $162.8 million")]), TEXTS)["why"] == "quote not found"

def test_a_quote_without_the_number_is_blank():
    assert check_number(ans(150.0, [q("cim", "LTM revenue of $162.8M grew")]), TEXTS)["why"] == "number not in quote"

def test_a_short_quote_proves_nothing():
    assert check_number(ans(7.8, [q("cim", "$7.8M")]), TEXTS)["status"] == "blank"

def test_numbers_in_thousands_stay_blank_rather_than_wrong():
    assert check_number(ans(162.8, [q("cim", "Revenue last year: $162,798 thousand")]), TEXTS)["status"] == "blank"

def test_documents_that_disagree_leave_it_blank_with_both_quotes():
    r = check_number(ans(162.8, [q("cim", "LTM revenue of $162.8M grew")],
                         other=[{"value": 160.0, "quote": q("teaser", "Revenue: $160.0M (LTM)")}]), TEXTS)
    assert r["status"] == "conflict" and r["value"] is None and len(r["quotes"]) == 2

def test_worry_quotes_from_unknown_documents_are_dropped_and_counted():
    kept, dropped = check_quotes([q("cim", "Capex was $7.8M last year"), q("qoe", "anything at all here ok")], TEXTS)
    assert len(kept) == 1 and dropped == 1
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/app/test_verify.py -q`. Expected: it fails on import errors.
- [ ] **Step 3:** Implement `verify.py` to the interface.
- [ ] **Step 4:** Run the same command. Expected: 10 passed.
- [ ] **Step 5:** Commit: `feat: analyst board quote check: quoted, calculated, conflict or blank`. The suite now
  passes 540 tests.

### Task 3: Prompts, the Claude call and the three steps

**Files:**
- Create: `acqlab/app/prompts.py`, `acqlab/app/claude.py`, `acqlab/app/steps.py`
- Test: `tests/app/fake_answer.py`, `tests/app/test_steps.py`

**Interfaces:**
- Consumes:
  - `solver.claude_bin`, `solver.child_env`, `solver.TIMEOUT`, `solver.RunTimeout`
  - `llm.LLMUnavailable`
  - `mix.PRICES`, `mix.price`, `mix.usage`
  - `knowledge.GUIDE`
  - `verify.*` and `ingest.texts`
  - `store.write` and `store.load`
- Produces:
  - `prompts.HAIKU = "claude-haiku-5-5"`, `prompts.OPUS = "claude-opus-5-5"`
  - `prompts.READER` and `prompts.PRICER`: system prompts (exact copy below)
  - `prompts.documents(deal: Path) -> str`: `"## <title> (<id>)\n\n<texts[id]>"` per doc, teaser first
  - `prompts.face_block(numbers: dict, settings: dict, price: float) -> str`: the checked numbers, financing, policy
    and price as `key: value` lines
  - `claude.ask(prompt: str, system: str, model: str, *, claude: str | None = None, timeout: float = TIMEOUT) ->
    tuple[dict, dict]`: the parsed JSON answer and the CLI result
    - the command is `[bin, "-p", prompt, "--output-format", "json", "--model", model, "--tools", "",
      "--setting-sources", "", "--disable-slash-commands", "--system-prompt", system, "--no-session-persistence"]`
    - it runs in an empty temporary folder, with `env=child_env()`
    - the answer is the CLI result's `result` text, from its first `{` to its last `}`, parsed with `json.loads`
    - a non-zero exit, `is_error`, or JSON that doesn't parse raises `LLMUnavailable` carrying Claude's text (the last
      500 characters)
  - `steps.read(deal: Path, *, model: str = HAIKU, claude=None, out: str = "numbers.json") -> dict`:
    - it asks with `READER` and the documents, runs `check_number` on each field and `check_quotes` on each worry's
      quotes, then writes `out`: `{"name", "industry", "numbers": {field: check_number result}, "hints": [...],
      "cost": float}`
    - on a re-read into `numbers.json`, any field whose saved status is `"you"` is kept as it was
  - `steps.complete(numbers: dict) -> list[str]`: the fields whose value is None (blanks and conflicts), taking
    `numbers.json`'s `"numbers"` mapping
  - `steps.values(numbers: dict) -> dict[str, float]`: the same mapping reduced to field → value, for the fields with
    a value
  - `steps.Incomplete(Exception)`
  - `steps.price(deal: Path, settings: dict, *, model: str = OPUS, claude=None, numbers: dict | None = None, out: str =
    "worries.json") -> dict`:
    - it raises `Incomplete` (naming the fields) if any number or setting is missing
    - it asks with `PRICER`, the `face_block` and the documents
    - each answered worry is validated: `type` in `TRAPS`, `0 <= chance <= 1`, `0 <= low <= high`, all finite.
      Quotes go through `check_quotes`.
    - it writes `{"worries": {type: {"chance", "low", "high", "reason", "quotes", "dropped_quotes"} |
      {"not_priced": why}}, "cost"}`, covering all five types (a missing type is `{"not_priced": "Opus gave none"}`)
  - `steps.second_look(deal, settings, *, claude=None) -> dict`: `read(model=OPUS, out="second_numbers.json")`, then
    `price(model=OPUS, numbers=<the board's numbers>, out="second_worries.json")`. It returns
    `{"numbers": ..., "worries": ...}`.
  - `steps.estimate(deal: Path, step: str) -> float`: list-price dollars. Input tokens are the characters of
    `documents(deal)` plus the system prompt, divided by 4. Output is 4,000 tokens. The models are `read` on Haiku,
    `price` on Opus, and `second` as an Opus read plus an Opus price.
  - The actual cost of each step is `mix.price(models, tokens)` from `mix.usage(step, cli)`, falling back to the CLI's
    `total_cost_usd` when that is None.
- `tests/app/fake_answer.py`: a stand-in `claude`. It writes its argv to `FAKE_ARGS` if set. With `FAKE_CLAUDE=limit`
  it prints a usage-limit error and exits 1. Otherwise it prints
  `{"type": "result", "is_error": false, "result": <text>, "usage": {"input_tokens": 1000, "output_tokens": 100}, "modelUsage": {<--model value>: {}}}`,
  where `<text>` is the file `$FAKE_ANSWERS/reader.txt` if the system prompt equals `prompts.READER`, else
  `$FAKE_ANSWERS/pricer.txt`. Tests widen `solver.ENV_KEEP` with `FAKE_CLAUDE`, `FAKE_ARGS` and `FAKE_ANSWERS`, as
  `tests/conftest.py`'s `fake_claude` does.

**Exact prompt copy** (`{guide}` is `knowledge.GUIDE`; `PRICER` is formatted once at import):

```python
READER = """You read the teaser and CIM of a company for sale and report its numbers for a private-equity first \
screen. Report only what the documents state. Every number needs a quote: the exact sentence or table line it comes \
from, copied character for character and at least a few words long, with the id of its document. Code checks each \
quote against the document text and throws away any number whose quote is not found or does not contain it, so \
never round, convert units or paraphrase.

Numbers ($M for money; rates as fractions, so 7.7% is 0.077):
- revenue_ltm, reported_ebitda, claimed_addbacks, adj_ebitda: the last twelve months
- growth: expected yearly revenue growth
- capex_pct, nwc_pct, da_pct: capital expenditure, normal net working capital, and depreciation and amortisation, \
each as a share of revenue
- tax_rate
When a number is not stated but follows from two stated ones (for example capex_pct from capex and revenue), give \
calc ("divide", "sum", "difference" or "product"), the two inputs in order, and one quote for each input. When the \
documents state different figures for the same number, give the main one as value and the others in other_values, \
each with its quote. When a number is not in the documents, give value null.

Worries: for each of the five kinds (addback: add-backs that may not really be one-time; debt_like: debt-like items \
payable at closing; concentration: revenue that may be lost from a customer; nwc: working capital below normal at \
closing; capex: extra capital expenditure needed), quote the lines that bear on it and say in one sentence what they \
suggest. These are the seller's own documents: report what they say, do not judge it.

Answer with one JSON object and nothing else:
{"name": str, "industry": str,
 "numbers": {<each number above>: {"value": number or null, "quotes": [{"doc_id": str, "text": str}],
   "calc": "none" | "divide" | "sum" | "difference" | "product", "inputs": [number, number] or [],
   "other_values": [{"value": number, "quote": {"doc_id": str, "text": str}}]}},
 "worries": [{"type": str, "note": str, "quotes": [{"doc_id": str, "text": str}]}]}"""

PRICER = """You are a private-equity analyst pricing the risks in a leveraged buyout at a first screen: is this \
company worth the sponsor's time at the analyst's price?

You get the company's numbers (checked by the analyst), the lender terms, the sponsor's policy, the price, and the \
full text of the teaser and CIM. These are the seller's own documents: their claims never settle a risk, they only \
hint at where it may be and how big. A document that checks an issue and finds no problem would settle it at zero, \
but none has been read yet, so give your honest prior for every kind.

For each of the five kinds of issue, give the chance it is real (0 to 1), its size range in $M if it is (low is \
usually 0), a one-sentence reason, and the quotes it rests on (exact text, with the document id). A valuation engine \
prices your beliefs and makes the call, so give all five.

All amounts are in $M: addback = claimed add-backs that are not really one-time (they reduce EBITDA); debt_like = \
debt-like items payable at closing; concentration = annual revenue that will be lost; nwc = how far closing net \
working capital falls short of normal; capex = extra capital expenditure needed per year.

{guide}

Answer with one JSON object and nothing else:
{{"worries": [{{"type": str, "chance": number, "low": number, "high": number, "reason": str,
  "quotes": [{{"doc_id": str, "text": str}}]}}]}}"""
```

- [ ] **Step 1: Write the failing tests** in `tests/app/test_steps.py`. Each one builds a deal with `ingest` from two
  `.md` files whose text contains the quoted lines, plus a settings dict built from `tests/conftest.make_full()`'s
  `financing` and `policy` (`.model_dump()`):

```python
def test_ask_runs_claude_without_tools_in_an_empty_folder_and_extracts_the_json(...):
    # reader.txt = 'Here you go: {"a": 1} hope that helps'
    answer, cli = ask("p", READER, HAIKU, claude=fake)
    assert answer == {"a": 1}
    argv = json.loads(args_file.read_text())["argv"]
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--model") + 1] == HAIKU

def test_ask_without_json_fails_with_claude_s_text(...):
    # reader.txt = "Sorry, I can't read that."
    with pytest.raises(LLMUnavailable, match="can't read"):
        ask("p", READER, HAIKU, claude=fake)

def test_a_usage_limit_surfaces_claude_s_message(...):
    # FAKE_CLAUDE=limit
    with pytest.raises(LLMUnavailable, match="usage limit"):
        steps.read(deal, claude=fake)

def test_read_fills_checked_numbers_and_keeps_what_the_analyst_set(...):
    # numbers.json first saved with {"tax_rate": {"value": 0.25, "status": "you", ...}}; the reader answer gives
    # revenue_ltm quoted correctly and tax_rate 0.3 quoted correctly
    out = steps.read(deal, claude=fake)
    assert out["numbers"]["revenue_ltm"]["status"] == "quoted"
    assert out["numbers"]["tax_rate"] == {**saved_tax_rate}  # "you" wins over a re-read

def test_price_refuses_while_a_number_or_setting_is_blank(...):
    with pytest.raises(Incomplete, match="da_pct"):
        steps.price(deal, settings, claude=fake)

def test_price_keeps_valid_worries_and_marks_the_rest_not_priced(...):
    # pricer.txt: addback valid; debt_like chance 1.5; "goodwill" unknown type; concentration with one bad quote
    w = steps.price(deal, settings, claude=fake)["worries"]
    assert w["addback"]["chance"] == 0.4 and "not_priced" in w["debt_like"] and "not_priced" in w["capex"]
    assert w["concentration"]["dropped_quotes"] == 1 and "goodwill" not in w

def test_second_look_writes_its_own_files_and_leaves_the_board_s_alone(...):
    before = (deal / "numbers.json").read_text()
    steps.second_look(deal, settings, claude=fake)
    assert (deal / "second_numbers.json").exists() and (deal / "second_worries.json").exists()
    assert (deal / "numbers.json").read_text() == before

def test_the_estimate_prices_opus_above_haiku_and_the_second_look_highest(tmp_path):
    r, p, s = (steps.estimate(deal, k) for k in ("read", "price", "second"))
    assert 0 < r < p < s

def test_each_step_records_its_cost(...):
    assert steps.read(deal, claude=fake)["cost"] > 0
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/app/test_steps.py -q`. Expected: it fails on import errors.
- [ ] **Step 3:** Implement `fake_answer.py`, `prompts.py`, `claude.py` and `steps.py` to the interfaces. Unexpected
  shapes in Claude's answer (a missing key, a wrong type) make that field blank or that worry not priced, never an
  exception.
- [ ] **Step 4:** Run the same command. Expected: 9 passed.
- [ ] **Step 5:** Commit: `feat: analyst board steps: Haiku reads and quotes, Opus prices, Opus second look`. The
  suite now passes 549 tests.

### Task 4: The board math

**Files:**
- Create: `acqlab/app/board.py`
- Test: `tests/app/test_board.py`

**Interfaces:**
- Consumes:
  - `record.Record`, `record.Face`, `record.N_WORLDS`
  - `routers.routers.score_regret`, `knowledge.DILIGENCE_MAP`
  - `acqlab.engine.Deal`, `Company`, `Financing`, `Policy`
  - `acqlab.generator.sample.Teaser`, `acqlab.generator.traps.TRAPS`
- Produces:
  - `board.DOC_NAMES = {"qoe": "Quality of earnings report", "audited": "Audited accounts and notes", "cim": "CIM",
    "legal": "Legal letter", "contract": "Customer contracts", "assets": "Fixed asset schedule"}`
  - `board.face(numbers: dict[str, float], settings: dict, price: float, name: str, industry: str) -> Face`, taking
    plain values (`steps.values`):
    - the `Teaser` comes from the numbers and the price
    - the `Deal`'s `Company` uses `reported_adj_ebitda = adj_ebitda`, with `Financing(**settings["financing"])`,
      `Policy(**settings["policy"])` and `asking_price = price`
    - pydantic errors propagate as `ValueError`
  - `board.class BoardRecord(Record)`: `__init__(self, face: Face, worries: dict[str, dict], yours: set[str])`. It
    plans the priced worries (`{"type", "name": reason, "chance", "low", "high", "docs": []}`, skipping
    `not_priced`). It overrides `issue(t)` to return `Issue(p_real=e.chance, hi=e.high)` for an open `t` in `yours`,
    and `size_limit(t)` to return `e.high` for `t` in `yours`; otherwise it defers to `super()`.
  - `board.apply(worries: dict, overrides: dict[str, dict]) -> tuple[dict, set[str]]`:
    - each override is `{"chance": float, "high": float}` for a type in `TRAPS`
    - it checks `0 <= chance <= 1` and `0 <= high`, both finite, and raises `ValueError` otherwise
    - an override sets the worry's chance and high (low 0), adds the type to `yours`, and turns a not-priced worry
      into a priced one
  - `board.compute(face: Face, worries: dict, yours: set[str]) -> dict`, returning
    `{"go": bool, "walk_away": float, "p10": float, "p90": float, "clears": float, "hist": {"edges": [...],
    "counts": [...]}, "flips": {t: float | None}, "pairs": [[a, b], ...], "ask": [{"type", "value", "docs": [names]}],
    "price": float}`:
    - `go` and `walk_away` come from `decide()`
    - `p10` and `p90` are percentiles of the walk-away worlds, and `clears` is the share of worlds above the price
    - `hist` is `numpy.histogram` with 20 bins
    - `flips` is `flip_amount` for each priced worry
    - `pairs` is `flagged_pairs()`
    - `ask` is `score_regret(values, w, price, {t: 1.0}, open_)` over the priced worries with chance > 0, sorted
      high to low, with the docs from `DILIGENCE_MAP` through `DOC_NAMES`

- [ ] **Step 1: Write the failing tests.** Use `make_full()` from `tests/conftest.py` for the financing and policy, a
  numbers dict consistent with its `Company`, and `price = make_full().asking_price`:

```python
def test_with_no_worries_the_call_is_the_engine_s_at_face_value():
    out = compute(f, {}, set())
    assert out["go"] == is_go(f.deal, Params()) and out["walk_away"] == pytest.approx(walk_away(f.deal, Params()), rel=1e-3)

def test_a_size_you_set_is_used_as_set_below_the_typical_floor():
    floor = typical_high("debt_like", f.teaser)
    r = BoardRecord(f, {"debt_like": worry(0.5, 0, floor / 10)}, {"debt_like"})
    assert r.issue("debt_like").hi == pytest.approx(floor / 10)

def test_an_opus_size_keeps_the_typical_floor():
    floor = typical_high("debt_like", f.teaser)
    assert BoardRecord(f, {"debt_like": worry(0.5, 0, floor / 10)}, set()).issue("debt_like").hi == pytest.approx(floor)

def test_flip_sizes_are_reported_or_none():
    out = compute(f, {"debt_like": worry(0.5, 0, 50.0), "capex": worry(0.1, 0, 0.01)}, {"capex"})
    assert out["flips"]["debt_like"] > 0 and out["flips"]["capex"] is None

def test_the_pairs_strip_is_the_record_s_flagged_pairs():
    r = BoardRecord(f, worries, set())
    assert compute(f, worries, set())["pairs"] == [list(p) for p in r.flagged_pairs()]

def test_the_worry_that_matters_most_tops_the_ask_list():
    out = compute(f, {"debt_like": worry(0.5, 0, big), "capex": worry(0.5, 0, tiny)}, {"debt_like", "capex"})
    assert out["ask"][0]["type"] == "debt_like" and out["ask"][0]["docs"][0] == "Audited accounts and notes"

def test_the_histogram_covers_every_world():
    assert sum(compute(f, worries, set())["hist"]["counts"]) == N_WORLDS

def test_a_recalculation_takes_under_a_second():
    t = time.perf_counter(); compute(f, all_five, set()); assert time.perf_counter() - t < 1.0

def test_impossible_overrides_are_refused():
    for bad in ({"chance": 1.5, "high": 1}, {"chance": 0.5, "high": -1}, {"chance": float("nan"), "high": 1}):
        with pytest.raises(ValueError):
            apply(worries, {"addback": bad})
```

  Set `big` above the deal's headroom and `tiny` far below it. Compute them from
  `walk_away(f.deal, Params()) - price`, so the test holds for `make_full()`.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/app/test_board.py -q`. Expected: it fails on import errors.
- [ ] **Step 3:** Implement `board.py` to the interface.
- [ ] **Step 4:** Run the same command. Expected: 9 passed.
- [ ] **Step 5:** Commit: `feat: analyst board math: the call, flip sizes, pairs and the ask-the-seller ranking`. The
  suite now passes 558 tests.

### Task 5: The server

**Files:**
- Create: `acqlab/app/server.py`, `acqlab/app/__main__.py`
- Test: `tests/app/test_server.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `server.make(home: Path, port: int = 0, claude: str | None = None) -> ThreadingHTTPServer`, bound to
    `("127.0.0.1", port)`
  - `python -m acqlab.app [--home ~/AcqLab] [--port 8765]`, which prints the URL and serves until Ctrl-C
- Endpoints (JSON in and out). A `ValueError`, `Incomplete`, `Unreadable` or bad JSON gives a 400 with
  `{"error": message}`; an unknown deal gives a 404; an `LLMUnavailable` gives a 502 with
  `{"error": "failed, try again: " + message}`.

| Method and path | Does |
|---|---|
| `GET /` | serves `acqlab/app/static/index.html` |
| `GET /api/settings`, `POST /api/settings` | reads or writes `home/settings.json` (`{"financing", "policy"}`), validated by `Financing` and `Policy` |
| `GET /api/deals` | `store.deals(home)` |
| `POST /api/deals` | `{"name", "price", "teaser": {"filename", "base64"}, "cim": {...}}`: saves the files to a temp folder, then `ingest`. Refuses a price that isn't a finite number above 0. |
| `GET /api/deals/<id>` | the deal, its docs, `numbers.json`, `worries.json`, `board.json` and any second-look files |
| `GET /api/deals/<id>/estimate/<step>` | `{"dollars": steps.estimate(...)}` |
| `POST /api/deals/<id>/run/<step>` | `step` is `read`, `price` or `second`: runs it synchronously and returns its output |
| `POST /api/deals/<id>/numbers` | `{field: value}`: each value must be a finite number; saved with `status: "you"` |
| `POST /api/deals/<id>/board` | `{"overrides": {...}}`: `apply`, then `compute`; saves the overrides to `board.json` and returns the board. If second-look worries exist, it adds `"second": compute(face, second_worries, set())` and the per-field number differences. |

- [ ] **Step 1: Write the failing tests.** Start the server with `make(tmp_path, claude=fake)` on a thread, and call
  it with `urllib.request`:
  - `test_it_listens_on_the_laptop_only`: `srv.server_address[0] == "127.0.0.1"`
  - `test_the_page_is_served`: `GET /` returns 200, `text/html`, and contains `<title>`
  - `test_settings_round_trip_and_bad_settings_are_refused`: a valid post then a get gives back the same values;
    `{"policy": {"exit_multiple": "x"}}` gives 400
  - `test_a_deal_is_created_from_uploaded_text_files`: a post with base64 `.md` files gives 200 and an `id`, and
    `GET /api/deals` lists it
  - `test_a_bad_price_or_unknown_deal_is_a_clear_error`: price 0 gives 400 with `"error"`; `GET /api/deals/nope` gives
    404
  - `test_numbers_you_type_are_saved_as_yours`: posting `{"tax_rate": 0.25}` saves `status == "you"`;
    `{"tax_rate": "abc"}` gives 400
  - `test_the_board_recalculates_from_overrides`: with numbers, settings and worries written directly to the deal
    folder, posting `{"overrides": {"addback": {"chance": 1, "high": 5}}}` returns `go` and `ask`, and `board.json`
    holds the override; `{"chance": 2}` gives 400
  - `test_a_step_runs_through_claude`: `POST /run/read` with the fake gives 200, and `numbers.json` exists
  - `test_a_failed_claude_call_says_try_again`: with `FAKE_CLAUDE=limit`, `POST /run/read` gives 502 and the error
    starts with `"failed, try again"`
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/app/test_server.py -q`. Expected: it fails on import errors.
- [ ] **Step 3:** Implement `server.py` (one `BaseHTTPRequestHandler` subclass, with routes matched by splitting the
  path) and `__main__.py`. Create a placeholder `acqlab/app/static/index.html` with a `<title>Acquisition Lab</title>`;
  Task 6 replaces its body.
- [ ] **Step 4:** Run the same command. Expected: 9 passed.
- [ ] **Step 5:** Commit: `feat: analyst board server: local JSON API on 127.0.0.1`. The suite now passes 567 tests.

### Task 6: The page, a free sample deal, and a look in the browser

**Files:**
- Modify: `acqlab/app/static/index.html`
- Create: `scripts/board_sample.py`
- Test: `tests/app/test_sample.py`

**Interfaces:**
- Consumes: the Task 5 endpoints.
- Produces:
  - `scripts/board_sample.py --room <benchmark room> --home <folder>`: a deal made with no Claude call
    - ingest the room's `index.json` teaser text and `cim.md`
    - numbers from `engine.json`'s `teaser` and `deal.company`, each saved with status `"you"`
    - settings from `engine.json`'s `deal.financing` and `deal.policy`, if the home has none
    - worries at starting guesses: the chance from `acqlab/bench/base_rates.json`'s `rates`, low 0, high
      `typical_high`, and the reason "starting guess, not read"
    - it prints the deal id

**The page** is one file with plain JavaScript and inline SVG, and no libraries. Sections, top to bottom, as the spec
§5 lists them:
1. a deal picker with a "New deal" form (name, price, two file inputs read as base64), and a settings form
2. the call (GO or NO-GO, the walk-away with p10–p90, "clears in N% of outcomes")
3. the fork chart (`hist` as bars, with the price as a vertical line)
4. the worry rows: the reason; a chance slider; one "size if real, up to $X" slider whose range runs to
   `max(2 × high, 2 × flip)`; the flip marker on the slider track; quote chips that open a panel showing the page text
   with the quote highlighted; a source tag; "a quote didn't check out" when `dropped_quotes > 0`; and "not priced,
   set it yourself" for a worry with `not_priced`
5. the "together they flip it" strip
6. the ask list, with "copy as text" (one line per worry: the worry, $ value, documents)
7. the company numbers panel (red blanks, editable inputs posting to `/numbers`)
8. the step buttons: Read, Price and Second look. Each shows `estimate` first and asks the analyst to confirm.
9. the second-look lane

On a slider's `input` event, the page waits 150 ms after the last change, then posts `/board` and redraws. While
numbers or settings are blank, the board sections are greyed out with "fill in the red fields first".

- [ ] **Step 1: Write the failing test** `test_the_sample_deal_prices_on_the_board`. It runs `board_sample.main([...])`
  on the session `data` fixture's `dev-000` room, into `tmp_path`, and then checks that `compute(face(...),
  worries, set())` returns a `go` boolean and five `flips` keys.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/app/test_sample.py -q`. Expected: it fails.
- [ ] **Step 3:** Implement `scripts/board_sample.py` and the page.
- [ ] **Step 4:** Run the same command. Expected: 1 passed. The suite now passes 568 tests.
- [ ] **Step 5: Look at it in the browser (free).**
  - Run `scripts/board_sample.py` on one generated room into the scratchpad. Use any `dev-*` room from a fresh
    `batch.run`, never `data/`.
  - Start `python -m acqlab.app --home <that folder> --port 8765`, open `http://127.0.0.1:8765` in the browser pane,
    and check:
    - the board draws
    - dragging a worry's size past its flip marker turns the call, within a second
    - a quote chip opens its page
    - "copy as text" fills the clipboard
    - a blank number greys out the board
  - Take one screenshot for the user.
- [ ] **Step 6:** Commit: `feat: analyst board page and a free sample deal`.

### Task 7: Paid check 1, built but not run

**Files:**
- Create: `scripts/board_reading_check.py`
- Test: `tests/app/test_reading_check.py`
- Modify: `docs/HANDOFF.md` ("Resume here": the board is built, and check 1 awaits the user's OK)

**Interfaces:**
- Produces: `scripts/board_reading_check.py --data <set folder> --n 10 --out <json>`:
  - it refuses any `--data` folder named `test-r2`, `pilot-r2u` or `mix-test-*`
  - it refuses an existing `--out`
  - for the first `n` deals in the set's `deals/` folder, it ingests the teaser and CIM text into a temporary home,
    runs `steps.read` (Haiku), and compares each field with `engine.json`'s teaser and company. A field counts as
    right when it is within relative 1%, wrong when it is filled in but off, and blank otherwise.
  - it then sets the true numbers and the deal's financing and policy, runs `steps.price` (Opus) and `compute`, and
    compares `go` with `truth/<deal>.json`'s `truth.go`. The truth folder is read by the script, never put in the deal
    folder Claude sees.
  - it writes `{"fields": {field: {"right", "wrong", "blank"}}, "calls": {"right", "wrong"}, "cost": float, "deals":
    [...]}` and prints a summary

- [ ] **Step 1: Write the failing tests:**
  - `test_the_check_refuses_held_out_sets`: `--data .../test-r2` raises `SystemExit`
  - `test_the_check_scores_fields_and_calls_with_fake_claude`: on the `data` fixture with the fake (a reader answer
    that quotes `revenue_ltm` correctly and gives a wrong `growth`), the output has `revenue_ltm` right 1, `growth`
    wrong 1, the others blank, and one call scored
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/app/test_reading_check.py -q`. Expected: it fails.
- [ ] **Step 3:** Implement the script.
- [ ] **Step 4:** Run the same command. Expected: 2 passed. Then run the full suite. Expected: 570 passed.
- [ ] **Step 5:** Update `docs/HANDOFF.md`'s "Resume here" section. Give the command for check 1 on
  `data/cal-r2` (about $2, in the plan-4b worktree, where the data lives), and state that it needs the user's OK.
- [ ] **Step 6:** Commit: `feat: analyst board reading check (paid; not run)`.

### After the tasks

- [ ] A whole-branch review on Opus. Check against the spec, the "Changes from the spec" and the Review Focus. It must
  confirm that no file under `acqlab/` outside `acqlab/app/` changed (`git diff --stat main -- acqlab ':!acqlab/app'`
  is empty) and that nothing writes under `data/`.
- [ ] Ask the user before running paid check 1.
- [ ] Paid check 2 (one real CIM end to end) runs only when the user supplies a CIM, or picks a public sample, and
  says go.

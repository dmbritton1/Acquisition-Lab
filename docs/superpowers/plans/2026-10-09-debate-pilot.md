# Debate Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the debate pilot: two new systems (`debate_x`, `debate_s`) in which single Claude reads, a bull argues for buying with a small reading budget, a bear argues for passing, and a referee who read nothing makes the call. Also build the one-shot analysis script.

**Architecture:**
- **New module `acqlab/bench/debate.py`.** Modelled on `acqlab/bench/recon.py`, and it reuses that module's step machinery: `step`, `combine`, `call_of`, `spent`, `draft`.
- **Steps:** each step is one sandboxed `claude -p` session through `solver.run_session`.
- **Referee helper:** `referee.documents` is extracted, so all prompts share one way of writing out the documents read.
- **Analysis script `scripts/debate_pilot.py`:** reuses the upside pilot script's helpers.

**Tech Stack:** Python 3.12, pytest, numpy. The fake `claude` lives in `tests/agents/fake_claude.py`.

**Spec:** `docs/superpowers/specs/2026-10-09-debate-pilot-design.md`

## Global Constraints

- **Frozen files:** `acqlab/agents/` and `acqlab/routers/` stay byte-identical to tag `s4-frozen-plan5`. No tool changes.
- **No paid runs:**
  - No task runs a real `claude`; tests use the fake (`fake_claude` fixture) or monkeypatched steps.
  - The smoke test and the pilot need the user's OK first (Task 5).
- **Model:** `claude-opus-5-5` (`solver.MODEL`), unchanged.
- **Budget shares:**
  - `debate_x`: the bull gets 0.2·B on top of the reused `s1b` reader. Most pages: 1.2·B.
  - `debate_s`: the reader gets 0.8·B, and the bull gets B minus what the reader spent. Most pages: B.
- **Earlier prompts:** the kill-test and recon-pilot prompts must not change. Task 1 pins their fingerprints.
- **Commits:** every commit message ends with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Style:**
  - lines at most 120 characters;
  - comments and docstrings in the surrounding modules' terse style;
  - no new dependencies.
- **Running tests:** use `.venv/bin/python -m pytest`, from the repository root. The suite has 422 tests before Task 1.

## Review Focus

The spec implies these inputs but its tests list does not name them; each one now has a test in the owning task:

1. **A deal whose reused `s1b` run timed out.** It must count as a timed-out step, not crash: `test_x_counts_a_timed_out_s1b_run_as_a_timed_out_step` (Task 3).
2. **A reader who opened nothing.** The bull's session must get no `--paid` argument, rather than an empty one: `test_a_bull_after_a_reader_who_read_nothing_has_no_paid_documents` (Task 2).
3. **A bull that re-opens a document the reader read.** It costs nothing, so the deal's pages stay within the limit: checked with the real tool server in `test_both_systems_run_end_to_end_with_the_fake_claude` (Task 3).
4. **A reader that gave no call.** There is nothing to overturn, so the deal is counted apart, not as overturned: `test_overturned_calls_are_split_four_ways_and_by_group` (Task 4).
5. **Debate rows made with prompts other than the frozen ones** (for example, an edit after the freeze). The analysis must refuse them: `test_the_analysis_refuses_another_model_or_unfrozen_prompts` (Task 4).

## File map

| File | Task | Responsibility |
|---|---|---|
| `acqlab/bench/referee.py` | 1 | `documents(room, read)`, extracted from `build` |
| `acqlab/bench/recon.py` | 1 | `second_prompts` uses `referee.documents` |
| `tests/bench/test_referee.py` | 1 | prompt fingerprints and the `documents` test |
| `acqlab/bench/debate.py` | 2, 3 | prompts and steps (Task 2); the systems, runner and CLI (Task 3) |
| `tests/bench/test_debate.py` | 2, 3 | fake-run tests |
| `scripts/debate_pilot.py` | 4 | the spec §3 analysis |
| `tests/bench/test_debate_pilot.py` | 4 | the analysis tests |
| `docs/HANDOFF.md`, `docs/results/debate-pilot-prereg.md` | 5 | the resume point, then the pre-registration after the smoke test |

---

### Task 1: Extract `referee.documents` and pin the earlier pilots' prompts

**Files:**
- Modify: `acqlab/bench/referee.py` (`build`, plus a new `documents` just above it)
- Modify: `acqlab/bench/recon.py` (`second_prompts`)
- Test: `tests/bench/test_referee.py`

**Interfaces:**
- Produces: `referee.documents(room: Path, read: list[str]) -> str`.
  - It returns the full text of the documents in `read`, in the room's index order.
  - Each document appears as `## <title> (<id>)` followed by a blank line and the text; documents are joined by blank lines.
  - Duplicate ids and ids that aren't in the room are ignored. An empty list gives `""`.
  - Tasks 2 and 3 use it.

- [ ] **Step 1: Write the tests**

  In `tests/bench/test_referee.py`:
  - change the imports at the top to:

  ```python
  import hashlib
  import json
  from pathlib import Path

  from acqlab.bench import recon, referee
  ```

  - append the following to the end of the file:

  ```python
  def _fingerprint(prompts: tuple[str, str]) -> str:
      return hashlib.sha256("\x00".join(prompts).encode()).hexdigest()


  def test_the_earlier_pilots_prompts_are_unchanged(s4_fake_run):
      """Fingerprints taken before referee.documents was extracted (the debate pilot's plan, Task 1): the kill test's
      referee, the recon pilot's reading referee and its second opinion."""
      room, team = s4_fake_run
      solo = [{"tool": "open_document", "args": {"doc_id": "board_minutes"}, "cost": 3.0, "refused": False},
              {"tool": "submit", "args": {"go": True, "walk_away": 101.5, "reason": "solo"}, "refused": False}]
      assert _fingerprint(referee.prompts(room, team, solo, "dev-000")) == \
          "6ffe421c464d6e831557a63067ee98e24f25035ca619ba256af24317fb07ab35"
      assert _fingerprint(referee.build(room, ["one", "two"], ["qoe", "legal"], "dev-000", 6.5)) == \
          "1d111d468dac2a8b4a033a8a85e1173860823ef7fde3b7c11ae1818228ee99ff"
      assert _fingerprint(recon.second_prompts(room, ["legal", "qoe"])) == \
          "e74dcf9c54194457eb9d8d83f9e6146aac391f756a3738fad4189c56f4746387"


  def test_documents_are_the_full_text_of_those_read_in_index_order(s4_fake_run):
      room, _ = s4_fake_run
      titles = {d["id"]: d["title"] for d in json.loads((room / "index.json").read_text())["documents"]}
      out = referee.documents(room, ["legal", "qoe", "legal", "no_such_doc"])
      assert out.index("(qoe)") < out.index("(legal)") and out.count(f"## {titles['legal']} (legal)") == 1
      assert (room / "legal.md").read_text() in out and "no_such_doc" not in out
      assert referee.documents(room, []) == ""
  ```

  The three digests were taken from the code as it is before this task. The first test must pass both before and after the refactor.

- [ ] **Step 2: Run the tests**

  Run: `.venv/bin/python -m pytest tests/bench/test_referee.py -q`

  Expected:
  - `test_the_earlier_pilots_prompts_are_unchanged` PASSES (it pins today's output);
  - `test_documents_are_the_full_text_of_those_read_in_index_order` FAILS with `AttributeError: module 'acqlab.bench.referee' has no attribute 'documents'`.

  If the fingerprint test fails here, stop and report: the shared fixtures differ from those the digests were taken on.

- [ ] **Step 3: Extract `documents` in `acqlab/bench/referee.py`**

  1. Insert this function directly above `def build(`:

     ```python
     def documents(room: Path, read: list[str]) -> str:
         """The full text of the documents read, in the room's index order, each under its title and id."""
         titles = {d["id"]: d["title"] for d in json.loads((room / "index.json").read_text())["documents"]}
         return "\n\n".join(f"## {titles[d]} ({d})\n\n{(room / f'{d}.md').read_text()}" for d in titles if d in set(read))
     ```

  2. In `build`, replace these four lines:

     ```python
         index = json.loads((room / "index.json").read_text())
         titles = {d["id"]: d["title"] for d in index["documents"]}
         read = [d for d in titles if d in set(read)]
         docs = "\n\n".join(f"## {titles[d]} ({d})\n\n{(room / f'{d}.md').read_text()}" for d in read)
     ```

     with:

     ```python
         index = json.loads((room / "index.json").read_text())
         docs = documents(room, read)
     ```

- [ ] **Step 4: Use it in `recon.second_prompts`**

  In `acqlab/bench/recon.py`, replace the body of `second_prompts` with:

  ```python
  def second_prompts(room: Path, read: list[str]) -> tuple[str, str]:
      teaser = json.loads((room / "index.json").read_text())["teaser"]
      user = f"{teaser}\n\n# Documents\n\n{referee.documents(room, read)}\n\nNote every kind of issue, then submit."
      return SECOND_SYSTEM.format(guide=GUIDE), user
  ```

- [ ] **Step 5: Run the tests**

  Run: `.venv/bin/python -m pytest tests/bench/test_referee.py tests/bench/test_recon.py -q`

  Expected: all pass (11 in `test_referee.py` and 18 in `test_recon.py`, so 29 passed).

  Then run: `.venv/bin/python -m pytest -q`

  Expected: 424 passed.

- [ ] **Step 6: Commit**

  ```bash
  git add acqlab/bench/referee.py acqlab/bench/recon.py tests/bench/test_referee.py
  git commit -m "refactor: referee.documents, shared by the referee and the second opinion; earlier prompts pinned unchanged

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 2: The debate's prompts and steps

**Files:**
- Create: `acqlab/bench/debate.py` (prompts and steps; Task 3 adds the systems and the runner)
- Test: `tests/bench/test_debate.py`

**Interfaces:**
- Consumes:
  - `referee.documents(room, read) -> str` (Task 1);
  - `solver.run_session(room, budget, trace, prompt, system, tools, server_args, *, claude=None, timeout=...) -> dict`.
- Produces (Task 3 relies on these exact names):
  - **Constants:** `READER_SHARE = 0.8`, `BULL_SHARE = 0.2`, `SYSTEMS = ("debate_x", "debate_s")`, `BULL_TOOLS`, `BEAR_TOOLS`, `JUDGE_TOOLS`.
  - **Prompt texts:** `SHARED`, `BULL`, `BEAR`, `REFEREE`.
  - **`PROMPT_SHA: dict[str, str]`:** keys `shared`, `bull`, `bear` and `referee`; each value is a sha256 hex digest of that template.
  - **`TITLES: dict[str, str]`:** keys `reader`, `bull` and `bear`.
  - **`system(template, **fields) -> str`.**
  - **Prompt builders:**
    - `bull_prompts(room, budget, read, reader) -> (system, user)`;
    - `bear_prompts(room, read, reader, bull) -> (system, user)`;
    - `judge_prompts(room, read, views: dict[str, str], deal) -> (system, user)`.
  - **Steps:** each takes a keyword `trace: Path`, passes `**kw` to `run_session`, and returns the CLI result dict.
    - `bull(room, budget, read, reader, *, trace, **kw)`;
    - `bear(room, read, reader, case, *, trace, **kw)`;
    - `judge(room, read, views, deal, *, trace, **kw)`.

- [ ] **Step 1: Write the failing tests**

  Create `tests/bench/test_debate.py`:

  ```python
  import json
  from pathlib import Path

  import pytest

  from acqlab.bench import debate


  def _row(tool, args=None, cost=0.0):
      return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


  def _session(go, reads=(), cost=4.0, reason="r"):
      rows = [_row("open_document", {"doc_id": d}, cost) for d in reads]
      return rows + ([_row("submit", {"go": go, "walk_away": 100.0, "reason": reason})] if go is not None else [])


  @pytest.fixture
  def room(data):
      return data / "deals" / "dev-000" / "room"


  @pytest.fixture
  def docs(room):
      return [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]]


  @pytest.fixture
  def seen(monkeypatch):
      """run_session replaced by one that records its arguments and returns a CLI result."""
      out = {}
      monkeypatch.setattr(debate, "run_session", lambda *a, **kw: out.update(a=a, kw=kw) or {"total_cost_usd": 0})
      return out


  def test_the_bull_reads_with_its_budget_and_the_reader_s_documents_are_paid(room, docs, seen, tmp_path):
      debate.bull(room, 4.5, [docs[1], docs[0], docs[1]], "VIEW", trace=tmp_path / "t.jsonl", claude="x")
      room_, budget, trace, user, system, tools, server_args = seen["a"]
      assert budget == 4.5 and tools == debate.BULL_TOOLS and server_args == ["--paid", f"{docs[1]},{docs[0]}"]
      assert "a budget of 4.5 units" in system and "VIEW" in user and seen["kw"] == {"claude": "x"}


  def test_a_bull_after_a_reader_who_read_nothing_has_no_paid_documents(room, seen, tmp_path):
      debate.bull(room, 4.0, [], "VIEW", trace=tmp_path / "t.jsonl")
      assert seen["a"][6] == []


  def test_the_bear_and_the_referee_have_no_budget_and_no_reading_tools(room, docs, seen, tmp_path):
      debate.bear(room, docs[:2], "READER", "CASE", trace=tmp_path / "t.jsonl")
      assert seen["a"][1] == 0 and seen["a"][5] == debate.BEAR_TOOLS and seen["a"][6] == []
      debate.judge(room, docs[:2], {"reader": "A", "bull": "B", "bear": "C"}, "dev-000", trace=tmp_path / "t.jsonl")
      assert seen["a"][1] == 0 and seen["a"][5] == debate.JUDGE_TOOLS and seen["a"][6] == []
      assert not {"list_documents", "search", "open_document"} & set(debate.BEAR_TOOLS + debate.JUDGE_TOOLS)


  def test_the_bull_sees_the_reader_s_documents_and_view_and_nothing_else(room, docs):
      titles = {d["id"]: d["title"] for d in json.loads((room / "index.json").read_text())["documents"]}
      system, user = debate.bull_prompts(room, 3.0, [docs[2]], "READER VIEW")
      assert f"## {titles[docs[2]]} ({docs[2]})" in user and f"({docs[0]})\n" not in user
      assert "READER VIEW" in user and "case for buying" in user and "already paid for" in system


  def test_the_bear_answers_the_case_for_buying_over_both_sides_documents(room, docs):
      system, user = debate.bear_prompts(room, [docs[0], docs[3]], "READER VIEW", "BULL CASE")
      assert f"({docs[0]})" in user and f"({docs[3]})" in user and f"({docs[1]})\n" not in user
      assert "READER VIEW" in user and "BULL CASE" in user and "cannot read anything else" in system


  def test_the_referee_sees_every_document_and_all_three_summaries(room, docs):
      views = {"reader": "READER VIEW", "bull": "BULL CASE", "bear": "BEAR CASE"}
      system, user = debate.judge_prompts(room, docs[:3], views, "dev-000")
      assert all(f"({d})" in user for d in docs[:3]) and all(v in user for v in views.values())
      assert all(f"# {t}" in user for t in debate.TITLES.values()) and "no case" in system


  def test_the_summaries_order_is_fixed_per_deal_and_varies_across_deals(room):
      views = {"reader": "READER VIEW", "bull": "BULL CASE", "bear": "BEAR CASE"}

      def first(deal):
          user = debate.judge_prompts(room, [], views, deal)[1]
          return min(views.values(), key=user.index)

      firsts = [first(f"test-{i:03d}") for i in range(30)]
      assert set(firsts) == set(views.values())  # each side is first on some deal
      assert first("test-007") == first("test-007")


  def test_every_prompt_carries_the_shared_rules():
      for template, fields in ((debate.BULL, {"budget": 2}), (debate.BEAR, {}), (debate.REFEREE, {})):
          text = debate.system(template, **fields)
          assert "seller's marketing" in text and "costs the difference" in text and debate.GUIDE in text
      assert set(debate.PROMPT_SHA) == {"shared", "bull", "bear", "referee"}
      assert all(len(h) == 64 for h in debate.PROMPT_SHA.values())


  def test_no_step_reads_the_answer_key():
      source = Path(debate.__file__).read_text().split("def run(")[0]
      assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))
  ```

- [ ] **Step 2: Run the tests to see them fail**

  Run: `.venv/bin/python -m pytest tests/bench/test_debate.py -q`

  Expected: a collection error, `ImportError: cannot import name 'debate' from 'acqlab.bench'`.

- [ ] **Step 3: Write `acqlab/bench/debate.py`**

  ```python
  """The debate pilot (spec docs/superpowers/specs/2026-10-09-debate-pilot-design.md): single Claude reads, a bull argues
  for buying (with a small reading budget of its own), a bear argues for passing, and a referee who read nothing makes
  the call. debate_x reuses the deal's s1b run as the reader and gives the bull 0.2 of the budget on top; debate_s runs a
  new reader at 0.8 of the budget and gives the bull what is left. Each step is a sandboxed `claude -p` session on our
  tool server, which enforces its budget. No step reads the answer key; scoring does, after the final call.

    uv run python -m acqlab.bench.debate --data data/pilot-r2u --systems debate_x,debate_s --confirm-claude

  Runs go to <data>/runs/<system>/<deal>.json, the combined trace beside it (each step's own trace too); finished runs
  are skipped. Exit codes: 0 done; 1 an unknown system; 2 Claude stopped (rerun later to resume); 3 refused (no
  --confirm-claude)."""
  import hashlib
  import json
  import random
  from pathlib import Path

  from acqlab.agents.knowledge import GUIDE
  from acqlab.agents.solver import run_session
  from acqlab.bench import referee

  READER_SHARE, BULL_SHARE = 0.8, 0.2  # spec §1
  SYSTEMS = ("debate_x", "debate_s")
  BULL_TOOLS = ["list_documents", "search", "open_document", "evaluate", "note_issue", "submit"]
  BEAR_TOOLS = ["evaluate", "note_issue", "submit"]
  JUDGE_TOOLS = ["evaluate", "submit"]

  SHARED = """The confidential information memorandum (CIM) is the seller's marketing: its claims are what diligence \
  checks, never evidence on their own.

  All amounts are in $M: addback = claimed add-backs that are not really one-time (they reduce EBITDA); debt_like = \
  debt-like items payable at closing; concentration = annual revenue that will be lost; nwc = how far closing net \
  working capital falls short of normal; capex = extra capital expenditure needed per year. Use evaluate to price \
  adjustments: it returns the walk-away price (the most the sponsor should pay) and whether the deal clears at the \
  asking price. The sponsor is judged on the decision: buying a deal worth less than its price, or passing on one worth \
  more, costs the difference.

  {guide}"""

  BULL = """You are a private-equity analyst arguing the case for a leveraged buyout: the sponsor should buy the company \
  at its asking price.

  Another analyst did diligence on this deal with a limited reading budget. You get the teaser, with the lender terms \
  and the sponsor's policy; the full text of every document that analyst read; and the analyst's findings. You can also \
  read more, with a budget of {budget:g} units: list_documents shows every document, opening one costs 1 unit per page \
  and search costs 1 unit. The documents above are already paid for.

  Make the strongest honest case that the sponsor should buy. Look for evidence that the feared problems are smaller \
  than feared or absent, especially in documents the analyst did not open. A referee who has not read the deal will \
  weigh your case against an advocate for passing, and will have the full text of every document you cite. Quote the \
  documents word for word, with their ids. Where the evidence is clearly against buying, say so rather than bluff.

  For each of the five kinds of issue, record your evidence-based view with note_issue: the chance it is real (0 to 1), \
  its size range in $M if it is, and the documents that bear on it. Price your view with evaluate. Then call submit \
  once, with go, walk_away in $M and a reason that states your case, with quotes and document ids.

  {shared}"""

  BEAR = """You are a private-equity analyst arguing the case against a leveraged buyout: the sponsor should not buy \
  the company at its asking price.

  Another analyst did diligence on this deal with a limited reading budget, and an advocate then argued for buying. You \
  get the teaser, with the lender terms and the sponsor's policy; the full text of every document either of them read; \
  the analyst's findings; and the case for buying. You cannot read anything else.

  Make the strongest honest case that the sponsor should pass. Answer the case for buying point by point: where its \
  quotes leave a problem open, overstate what a document settles, or lean on the seller's own claims, say so. A referee \
  who has not read the deal will weigh your case against the case for buying, and will have the full text of every \
  document you cite. Quote the documents word for word, with their ids. Where the evidence is clearly for buying, say \
  so rather than bluff.

  For each of the five kinds of issue, record your evidence-based view with note_issue: the chance it is real (0 to 1), \
  its size range in $M if it is, and the documents that bear on it. Price your view with evaluate. Then call submit \
  once, with go, walk_away in $M and a reason that states your case, with quotes and document ids.

  {shared}"""

  REFEREE = """You are a private-equity analyst refereeing a debate about a leveraged buyout: should the sponsor buy the \
  company at its asking price?

  An analyst did diligence on this deal with a limited reading budget; then one advocate argued for buying and another \
  for passing. You get the teaser, with the lender terms and the sponsor's policy; the full text of every document any \
  of them read; and their three summaries. You cannot read anything else. The advocates were told to argue one side, so \
  check their quotes against the documents, which you have in full. Where an advocate gave no case, its summary says so; \
  decide anyway.

  Find what the disagreement turns on, and settle it from the documents: a finding counts where a document supports it, \
  and an issue no document settles stays uncertain. Use evaluate to price your adjustments. Then call submit once, with \
  go (true to buy at the asking price), walk_away in $M and a one-line reason. Your call is the final decision.

  {shared}"""

  PROMPT_SHA = {name: hashlib.sha256(text.encode()).hexdigest()
                for name, text in (("shared", SHARED), ("bull", BULL), ("bear", BEAR), ("referee", REFEREE))}
  TITLES = {"reader": "The diligence analyst", "bull": "The advocate for buying", "bear": "The advocate for passing"}


  def system(template: str, **fields) -> str:
      return template.format(shared=SHARED.format(guide=GUIDE), **fields)


  def teaser(room: Path) -> str:
      return json.loads((room / "index.json").read_text())["teaser"]


  # --- the prompts ---------------------------------------------------------------------------------------------------

  def bull_prompts(room: Path, budget: float, read: list[str], reader: str) -> tuple[str, str]:
      user = (f"{teaser(room)}\n\n# Documents the analyst read\n\n{referee.documents(room, read)}\n\n"
              f"# {TITLES['reader']}\n\n{reader}\n\nRead what you need within your budget, note every kind of issue, "
              f"then submit your case for buying.")
      return system(BULL, budget=budget), user


  def bear_prompts(room: Path, read: list[str], reader: str, bull: str) -> tuple[str, str]:
      user = (f"{teaser(room)}\n\n# Documents either of them read\n\n{referee.documents(room, read)}\n\n"
              f"# {TITLES['reader']}\n\n{reader}\n\n# The case for buying\n\n{bull}\n\nAnswer the case for buying, "
              f"note every kind of issue, then submit your case for passing.")
      return system(BEAR), user


  def judge_prompts(room: Path, read: list[str], views: dict[str, str], deal: str) -> tuple[str, str]:
      """The three summaries in an order fixed per deal from its id, so no side is always first."""
      order = list(TITLES)
      random.Random(deal).shuffle(order)
      summaries = "\n\n".join(f"# {TITLES[k]}\n\n{views[k]}" for k in order)
      user = (f"{teaser(room)}\n\n# Documents any of them read\n\n{referee.documents(room, read)}\n\n{summaries}\n\n"
              f"Settle the debate and submit your decision.")
      return system(REFEREE), user


  # --- the steps (module functions, so tests can replace them) -------------------------------------------------------

  def bull(room: Path, budget: float, read: list[str], reader: str, *, trace: Path, **kw) -> dict:
      """The bull reads with its own budget; the reader's documents are already paid for."""
      sys_, user = bull_prompts(room, budget, read, reader)
      paid = list(dict.fromkeys(read))
      return run_session(room, budget, trace, user, sys_, BULL_TOOLS, ["--paid", ",".join(paid)] if paid else [], **kw)


  def bear(room: Path, read: list[str], reader: str, case: str, *, trace: Path, **kw) -> dict:
      sys_, user = bear_prompts(room, read, reader, case)
      return run_session(room, 0, trace, user, sys_, BEAR_TOOLS, [], **kw)


  def judge(room: Path, read: list[str], views: dict[str, str], deal: str, *, trace: Path, **kw) -> dict:
      sys_, user = judge_prompts(room, read, views, deal)
      return run_session(room, 0, trace, user, sys_, JUDGE_TOOLS, [], **kw)
  ```

  Each prompt names what the spec §2 says that step sees, and its task. All three carry `SHARED`: the CIM rule, the amounts, `evaluate`, the scoring sentence and `GUIDE`.

- [ ] **Step 4: Run the tests**

  Run: `.venv/bin/python -m pytest tests/bench/test_debate.py -q`

  Expected: 9 passed.

  Then run: `.venv/bin/python -m pytest -q`

  Expected: 433 passed.

- [ ] **Step 5: Commit**

  ```bash
  git add acqlab/bench/debate.py tests/bench/test_debate.py
  git commit -m "feat: debate pilot prompts and steps: a bull that reads, a bear and a referee that do not

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 3: The two debate systems, the runner and the CLI

**Files:**
- Modify: `acqlab/bench/debate.py` (the imports, then the systems and runner appended)
- Test: `tests/bench/test_debate.py` (the imports, then the system and runner tests appended)

**Interfaces:**
- **Consumes:**
  - Task 2's `bull`, `bear` and `judge`, `BULL_SHARE`, `READER_SHARE` and `PROMPT_SHA`.
  - From `acqlab.bench.recon`:
    - `step(name, path, fn, *args, **kw) -> (rows, cli | None)`, which tags rows with `step` and returns `None` on a timeout;
    - `combine(trace, clis, final) -> (trace, cli)`;
    - `call_of(trace) -> dict | None`;
    - `spent(trace) -> float`;
    - `draft(room, budget, *, trace, router=False, **kw)`, which is single Claude, unchanged.
- **Produces (Task 4 reads these):**
  - **Run row:** each row in `<data>/runs/<system>/<deal>.json` is `pilot.score(...)` plus:
    - `rep` (0) and `budget`;
    - `spent`, the units paid across all steps;
    - `calls`, `{reader, bull, bear, referee}`, each the step's submitted args or `None`;
    - `step_cost`, `{reader, bull, bear, referee}`, each in USD or `None` for a timed-out step;
    - `prompts`, which is `PROMPT_SHA`.
  - **Combined trace:** `<deal>.trace.jsonl` sits beside the row.
    - Every row carries `step`: one of `reader`, `bull`, `bear`, `referee` or `final`.
    - The steps' own submits are renamed `step_submit`.
  - **Functions:**
    - `debate(room, deal, out, reader, left, **kw)`;
    - `run_x(room, budget, deal, out, **kw)`;
    - `run_s(room, budget, deal, out, **kw)`;
    - `RUN`;
    - `run(data, systems, split="test", deals=None, **kw) -> list[dict]`;
    - `main(argv) -> int`, with exit codes 0 done, 1 unknown system, 2 Claude stopped and 3 refused.

- [ ] **Step 1: Write the failing tests**

  1. In `tests/bench/test_debate.py`, replace the import block at the top with:

     ```python
     import functools
     import json
     import shutil
     from pathlib import Path

     import pytest

     from acqlab.agents.solver import RunTimeout, solve
     from acqlab.bench import debate, pilot
     from acqlab.generator.batch import AnswerKey
     ```

  2. Append the following to the end of the file:

     ```python
     # --- the systems and the runner ------------------------------------------------------------------------------------

     @pytest.fixture
     def fakes(monkeypatch, room):
         """Every step replaced by one that writes a scripted trace (scripts[step]; none scripted = a timeout) and records
         its arguments (calls[step])."""
         f = {"scripts": {}, "calls": {}}

         def run(*args, trace, **kw):
             name = trace.name.split(".")[-2]
             f["calls"][name] = (args, kw)
             if name not in f["scripts"]:
                 raise RunTimeout("fake timeout")
             trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
             return {"total_cost_usd": 0.1, "usage": {"output_tokens": 5}, "modelUsage": {"claude-opus-5-5": {}},
                     "env_keys": ["HOME", "PATH"]}

         for fn in ("draft", "bull", "bear", "judge"):
             monkeypatch.setattr(debate, fn, run)
         return f


     def _s1b(runs: Path, deal: str, trace: list[dict], status="ok"):
         """A finished s1b run beside the debate's runs, as pilot.run writes one; the debate's runs directory too."""
         for s in ("s1b", "debate_x"):
             (runs / s).mkdir(parents=True, exist_ok=True)
         (runs / "s1b" / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
         (runs / "s1b" / f"{deal}.json").write_text(json.dumps({
             "status": status, "tokens": {"output_tokens": 7}, "cost_usd": 0.2, "num_turns": 3, "duration_ms": 10,
             "models": ["claude-opus-5-5"], "env_keys": ["HOME"]}))


     def test_x_reuses_the_s1b_run_and_gives_the_bull_a_fifth_on_top(fakes, room, docs, data, tmp_path):
         runs = tmp_path / "runs"
         _s1b(runs, "dev-000", _session(False, docs[:2], cost=9.0))
         fakes["scripts"] |= {"bull": _session(True, docs[2:3], cost=4.0), "bear": _session(False),
                              "referee": _session(True)}
         trace, cli = debate.run_x(room, 20.0, "dev-000", runs / "debate_x" / "dev-000.json")
         (_, left, read, view), _ = fakes["calls"]["bull"]
         assert left == pytest.approx(4.0) and read == docs[:2] and "NO-GO" in view
         assert "draft" not in fakes["calls"]  # no new reader
         key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
         row = pilot.score(key, "debate_x", trace, cli, "ok")
         assert row["pages"] == 22.0 and row["cost_usd"] == pytest.approx(0.5) and row["sessions"] == 4
         assert row["tokens"]["output_tokens"] == 7 + 3 * 5 and row["models"] == ["claude-opus-5-5"]
         assert {r["step"] for r in trace} == {"reader", "bull", "bear", "referee", "final"}
         assert cli["calls"]["reader"]["go"] is False and cli["calls"]["referee"]["go"] is True
         assert cli["step_cost"] == {"reader": 0.2, "bull": 0.1, "bear": 0.1, "referee": 0.1}


     def test_x_stops_without_a_finished_s1b_run(fakes, room, tmp_path):
         with pytest.raises(FileNotFoundError, match="s1b"):
             debate.run_x(room, 20.0, "dev-000", tmp_path / "runs" / "debate_x" / "dev-000.json")
         assert not fakes["calls"]


     def test_x_counts_a_timed_out_s1b_run_as_a_timed_out_step(fakes, room, docs, tmp_path):
         runs = tmp_path / "runs"
         _s1b(runs, "dev-000", _session(None, docs[:1]), status="timeout")
         fakes["scripts"] |= {"bull": _session(True), "bear": _session(False), "referee": _session(True)}
         _, cli = debate.run_x(room, 20.0, "dev-000", runs / "debate_x" / "dev-000.json")
         assert cli["timeouts"] == 1 and cli["calls"]["reader"] is None and cli["step_cost"]["reader"] is None


     def test_s_gives_the_reader_80_percent_and_the_bull_what_is_left(fakes, room, docs, tmp_path):
         fakes["scripts"] |= {"reader": _session(True, docs[:3], cost=4.0), "bull": _session(True, docs[3:4], cost=4.0),
                              "bear": _session(False), "referee": _session(False)}
         trace, _ = debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")
         assert fakes["calls"]["reader"][0][1] == pytest.approx(16.0)
         (_, left, read, _), _ = fakes["calls"]["bull"]
         assert left == pytest.approx(8.0) and read == docs[:3]
         assert debate.spent(trace) <= 20.0


     def test_the_bear_and_referee_get_every_document_read_so_far(fakes, room, docs, tmp_path):
         fakes["scripts"] |= {"reader": _session(True, docs[:2]), "bull": _session(True, [docs[1], docs[4]]),
                              "bear": _session(False), "referee": _session(False)}
         debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")
         assert fakes["calls"]["bear"][0][1] == [docs[0], docs[1], docs[4]]
         (_, read, views, deal), _ = fakes["calls"]["referee"]
         assert read == [docs[0], docs[1], docs[4]] and deal == "dev-000" and set(views) == {"reader", "bull", "bear"}


     def test_a_missing_case_is_stated_and_the_debate_goes_on(fakes, room, docs, tmp_path):
         fakes["scripts"] |= {"reader": _session(True, docs[:1]), "bear": _session(False), "referee": _session(False)}
         trace, cli = debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")  # the bull timed out
         assert "ended without submitting" in fakes["calls"]["bear"][0][3]
         assert "ended without submitting" in fakes["calls"]["referee"][0][2]["bull"]
         assert debate.call_of(trace)["go"] is False and cli["timeouts"] == 1 and cli["calls"]["bull"] is None


     def test_a_referee_without_a_call_leaves_the_deal_unanswered(fakes, room, data, tmp_path):
         fakes["scripts"] |= {"reader": _session(True), "bull": _session(True), "bear": _session(False),
                              "referee": [_row("evaluate", {"adjustments": {}})]}
         trace, cli = debate.run_s(room, 20.0, "dev-000", tmp_path / "x.json")
         key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
         row = pilot.score(key, "debate_s", trace, cli, "no_call")
         assert not row["answered"] and row["go"] == key.truth.face_go
         assert sum(r["tool"] == "submit" for r in trace) == 0 and sum(r["tool"] == "step_submit" for r in trace) == 3


     def test_the_runner_refuses_without_confirmation_and_rejects_unknown_systems(tmp_path):
         assert debate.main(["--data", str(tmp_path)]) == 3
         assert debate.main(["--data", str(tmp_path), "--systems", "debate_y", "--confirm-claude"]) == 1


     def test_claude_stopping_mid_deal_writes_no_row_and_exits_2(data, tmp_path, monkeypatch):
         d = tmp_path / "d"
         shutil.copytree(data, d)

         def stop(*a, **kw):
             raise debate.LLMUnavailable("usage limit")

         monkeypatch.setitem(debate.RUN, "debate_s", stop)
         assert debate.main(["--data", str(d), "--systems", "debate_s", "--split", "dev", "--confirm-claude"]) == 2
         assert not list((d / "runs" / "debate_s").glob("*.json"))  # a rerun redoes the whole deal


     def test_both_systems_run_end_to_end_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
         monkeypatch.setenv("FAKE_CLAUDE", "ok")
         d = tmp_path / "d"
         shutil.copytree(data, d)
         pilot.run(d, 2, ["s1b"], solver=functools.partial(solve, claude=fake_claude), split="dev")
         rows = debate.run(d, list(debate.SYSTEMS), split="dev", deals=["dev-001"], claude=fake_claude)
         assert [(r["system"], r["deal"]) for r in rows] == [("debate_x", "dev-001"), ("debate_s", "dev-001")]
         for r in rows:
             limit = r["budget"] * (1.2 if r["system"] == "debate_x" else 1.0)
             trace = debate.referee.rows(d / "runs" / r["system"] / "dev-001.trace.jsonl")
             assert r["answered"] and r["sessions"] == 4 and r["pages"] <= limit + 1e-9
             assert r["prompts"] == debate.PROMPT_SHA and set(r["calls"]) == {"reader", "bull", "bear", "referee"}
             assert [s for s in dict.fromkeys(x["step"] for x in trace)] == ["reader", "bull", "bear", "referee", "final"]
         assert not (d / "runs" / "debate_x" / "dev-000.json").exists()  # --deals limits the run
         assert debate.run(d, list(debate.SYSTEMS), split="dev", deals=["dev-001"], claude=fake_claude) == []
     ```

- [ ] **Step 2: Run the tests to see them fail**

  Run: `.venv/bin/python -m pytest tests/bench/test_debate.py -q`

  Expected: the 10 new tests fail with `AttributeError`s (for example, `module 'acqlab.bench.debate' has no attribute 'draft'` or `'run_x'`). The 9 tests from Task 2 still pass.

- [ ] **Step 3: Add the systems and the runner to `acqlab/bench/debate.py`**

  1. Replace the import block (from `import hashlib` to `from acqlab.bench import referee`) with:

     ```python
     import argparse
     import hashlib
     import json
     import random
     from pathlib import Path

     from acqlab.agents.knowledge import GUIDE
     from acqlab.agents.solver import run_session
     from acqlab.bench import referee
     from acqlab.bench.recon import call_of, combine, draft, spent, step
     from acqlab.llm import LLMUnavailable
     ```

  2. Append the following to the end of the file:

     ```python
     # --- the systems ---------------------------------------------------------------------------------------------------

     def debate(room: Path, deal: str, out: Path, reader: tuple[list[dict], dict | None], left: float,
                **kw) -> tuple[list[dict], dict]:
         """Spec §2 after the reader: the bull with `left` units, the bear, then the referee, whose call is final (none if
         it gave none, so scoring treats the deal as unanswered)."""
         read = referee.opened(reader[0])
         views = {"reader": referee.solo_view(reader[0])}
         pro = step("bull", out.with_suffix(".bull.jsonl"), bull, room, left, read, views["reader"], **kw)
         read = list(dict.fromkeys(read + referee.opened(pro[0])))
         views["bull"] = referee.solo_view(pro[0])
         con = step("bear", out.with_suffix(".bear.jsonl"), bear, room, read, views["reader"], views["bull"], **kw)
         views["bear"] = referee.solo_view(con[0])
         ref = step("referee", out.with_suffix(".referee.jsonl"), judge, room, read, views, deal, **kw)
         steps = {"reader": reader, "bull": pro, "bear": con, "referee": ref}
         trace, cli = combine([r for rows, _ in steps.values() for r in rows], [c for _, c in steps.values()],
                              call_of(ref[0]))
         return trace, cli | {"calls": {k: call_of(rows) for k, (rows, _) in steps.items()},
                              "step_cost": {k: c and c.get("total_cost_usd") for k, (_, c) in steps.items()}}


     def reused(row: dict) -> dict | None:
         """An s1b row as a CLI result, for combine; None if that run timed out."""
         if row["status"] == "timeout":
             return None
         return {"usage": row["tokens"], "total_cost_usd": row["cost_usd"], "num_turns": row["num_turns"],
                 "duration_ms": row["duration_ms"], "modelUsage": {m: {} for m in row["models"]},
                 "env_keys": row["env_keys"]}


     def run_x(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict]:
         """debate_x: the deal's finished s1b run is the reader, unchanged; the bull gets 0.2 of the budget on top."""
         path = out.parents[1] / "s1b" / f"{deal}.json"
         if not (path.exists() and path.with_suffix(".trace.jsonl").exists()):
             raise FileNotFoundError(f"debate_x/{deal}: no finished s1b run to reuse at {path}")
         row = json.loads(path.read_text())
         rows = [r | {"step": "reader"} for r in referee.rows(path.with_suffix(".trace.jsonl"))]
         return debate(room, deal, out, (rows, reused(row)), BULL_SHARE * budget, **kw)


     def run_s(room: Path, budget: float, deal: str, out: Path, **kw) -> tuple[list[dict], dict]:
         """debate_s: a new reader at 0.8 of the budget; the bull gets what it left, so the deal never exceeds its budget."""
         reader = step("reader", out.with_suffix(".reader.jsonl"), draft, room, READER_SHARE * budget, **kw)
         return debate(room, deal, out, reader, max(0.0, budget - spent(reader[0])), **kw)


     RUN = {"debate_x": run_x, "debate_s": run_s}


     # --- the runner ----------------------------------------------------------------------------------------------------

     def run(data: Path, systems: list[str], split: str = "test", deals: list[str] | None = None, **kw) -> list[dict]:
         """Every missing run of these systems on the split's deals (or just `deals`); raises LLMUnavailable to stop."""
         from acqlab.bench.pilot import score  # scoring reads the answer key, after the final call
         from acqlab.generator.batch import AnswerKey
         out = []
         for deal in deals or json.loads((data / "splits.json").read_text())[split]:
             room = data / "deals" / deal / "room"
             budget = float(json.loads((room / "index.json").read_text())["default_budget"])
             for name in systems:
                 path = data / "runs" / name / f"{deal}.json"
                 if path.exists():
                     continue
                 path.parent.mkdir(parents=True, exist_ok=True)
                 trace, cli = RUN[name](room, budget, deal, path, **kw)
                 path.with_suffix(".trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
                 key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
                 assert key.budget == budget, f"{deal}: the room's budget is not the answer key's"
                 row = score(key, name, trace, cli, "ok" if call_of(trace) else "no_call") | {
                     "rep": 0, "budget": budget, "spent": spent(trace), "calls": cli["calls"],
                     "step_cost": cli["step_cost"], "prompts": PROMPT_SHA}
                 path.write_text(json.dumps(row, indent=2))
                 out.append(row)
                 print(f"{name} {deal}: answered={row['answered']} correct={row['correct']} regret {row['regret']:.3f} "
                       f"pages {row['pages']:g}/{budget:g}")
         return out


     def main(argv: list[str] | None = None) -> int:
         ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
         ap.add_argument("--data", type=Path, required=True)
         ap.add_argument("--systems", default=",".join(SYSTEMS))
         ap.add_argument("--split", default="test")
         ap.add_argument("--deals", default="", help="comma-separated deal ids (default: the whole split)")
         ap.add_argument("--confirm-claude", action="store_true", help="required: this spends real Claude usage")
         args = ap.parse_args(argv)
         systems = [s for s in args.systems.split(",") if s]
         if bad := [s for s in systems if s not in RUN]:
             print(f"Unknown systems {bad}: choose from {list(RUN)}")
             return 1
         if not args.confirm_claude:
             print("Refusing: pass --confirm-claude to spend real Claude usage")
             return 3
         try:
             run(args.data, systems, args.split, [d for d in args.deals.split(",") if d] or None)
         except LLMUnavailable as e:
             print(f"Claude stopped: {e}. Rerun to resume.")
             return 2
         return 0


     if __name__ == "__main__":
         raise SystemExit(main())
     ```

- [ ] **Step 4: Run the tests**

  Run: `.venv/bin/python -m pytest tests/bench/test_debate.py -q`

  Expected: 19 passed.

  Then run: `.venv/bin/python -m pytest -q`

  Expected: 443 passed.

- [ ] **Step 5: Commit**

  ```bash
  git add acqlab/bench/debate.py tests/bench/test_debate.py
  git commit -m "feat: debate_x (s1b reused, bull reads 0.2 on top) and debate_s (reader 0.8, bull the rest), runner and CLI

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 4: The analysis script

**Files:**
- Create: `scripts/debate_pilot.py`
- Test: `tests/bench/test_debate_pilot.py`

**Interfaces:**
- **Consumes:**
  - Task 3's row fields: `calls`, `step_cost`, `prompts`, `budget`, `spent` and `timeouts`. Each trace row's `step` comes from the combined trace.
  - `debate.SYSTEMS`, `debate.BULL_SHARE` and `debate.PROMPT_SHA`.
  - From `scripts/upside_pilot.py`, imported as a module: `GROUPS`, `MODEL`, `group`, `keys`, `load`, `settling_doc` and `stats`.
  - `analysis.compare(a, b)`.
- **Produces:**
  - `analyse(data, split="test") -> dict`;
  - `main(argv) -> int`, which writes `--out` once and returns 1 on any refusal;
  - the helpers `mechanics`, `meets`, `reading`, `versus`, `overturned`, `by_step`, `bull_found` and `check`.

- [ ] **Step 1: Write the failing tests**

  Create `tests/bench/test_debate_pilot.py`:

  ```python
  import json
  import runpy
  import shutil
  from pathlib import Path

  import pytest

  from acqlab.bench import debate, pilot
  from acqlab.generator import batch
  from acqlab.generator.batch import AnswerKey

  SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "debate_pilot.py"))
  DEBATES = debate.SYSTEMS


  @pytest.fixture(scope="module")
  def r2u(tmp_path_factory):
      """Five r2u test deals: 2 relief, 1 confirmed, 2 ordinary."""
      d = tmp_path_factory.mktemp("r2u")
      assert batch.run(d, {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u") == []
      return d


  def keys(d: Path) -> dict[str, AnswerKey]:
      return {p.stem: AnswerKey.model_validate_json(p.read_text()) for p in sorted((d / "truth").glob("*.json"))}


  def submit(go: bool, step: str | None = None) -> dict:
      row = {"tool": "submit", "args": {"go": go, "walk_away": 1.0, "reason": ""}, "refused": False, "cost": 0.0}
      return row | {"step": step} if step else row


  def write(d: Path, system: str, deal: str, trace: list[dict], extra: dict | None = None,
            models=("claude-opus-5-5",)) -> None:
      key = AnswerKey.model_validate_json((d / "truth" / f"{deal}.json").read_text())
      out = d / "runs" / system
      out.mkdir(parents=True, exist_ok=True)
      (out / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
      cli = {"total_cost_usd": 0.1, "sessions": 1, "modelUsage": {m: {} for m in models}}
      (out / f"{deal}.json").write_text(json.dumps(pilot.score(key, system, trace, cli, "ok") | (extra or {})))


  @pytest.fixture
  def finished(r2u, tmp_path):
      """A finished fake pilot. s1b and s4 are always right. In each debate the reader passes on every deal, the bull
      opens the settling document on the relief deals, and the referee is always right."""
      d = tmp_path / "d"
      shutil.copytree(r2u, d)
      for deal, key in keys(d).items():
          t = key.truth
          for s in ("s1b", "s4"):
              write(d, s, deal, [submit(t.go)])
          doc = SCRIPT["settling_doc"](key) if t.case_type == "relief" else None
          pages = {x["id"]: x["pages"] for x in json.loads((d / "deals" / deal / "room" / "index.json").read_text())
                   ["documents"]}
          bull = [{"tool": "open_document", "args": {"doc_id": doc}, "refused": False, "cost": pages[doc],
                   "step": "bull"}] if doc else []
          trace = [submit(False, "reader") | {"tool": "step_submit"}, *bull, submit(t.go, "final")]
          for s in DEBATES:
              write(d, s, deal, trace, {"budget": 20.0, "spent": 1.0, "prompts": debate.PROMPT_SHA,
                                        "calls": {"reader": {"go": False}, "bull": None, "bear": None,
                                                  "referee": {"go": t.go}},
                                        "step_cost": {"reader": 0.1, "bull": None, "bear": 0.1, "referee": 0.1}})
      return d


  def test_the_reading_follows_the_fixed_rule():
      ok = {s: {"passes": True} for s in DEBATES}
      regret = {"s1b": 0.010, "s4": 0.013, "debate_x": 0.008, "debate_s": 0.009}
      fgo = {"s1b": 0, "s4": 0, "debate_x": 1, "debate_s": 1}
      assert SCRIPT["reading"](regret, fgo, ok) == "debate helps at the same budget"
      assert SCRIPT["reading"](regret | {"debate_s": 0.010}, fgo, ok) == "debate helps only with extra pages"
      assert SCRIPT["reading"](regret, fgo | {"debate_s": 2}, ok) == "debate helps only with extra pages"  # 2 > 0 + 1
      assert SCRIPT["reading"](regret, fgo, ok | {"debate_s": {"passes": False}}) == \
          "debate helps only with extra pages"
      assert SCRIPT["reading"](regret | {"debate_s": 0.011, "debate_x": 0.010}, fgo, ok) == "debate doesn't help"


  def test_the_mechanics_check_needs_38_of_40_answered_and_no_deal_past_its_limit():
      rows = [{"answered": i >= 2, "spent": 20.0, "budget": 20.0} for i in range(40)]
      assert SCRIPT["mechanics"](rows, 1.0) == {"n": 40, "answered": 38, "over_limit": 0, "passes": True}
      rows[2]["answered"] = False
      assert not SCRIPT["mechanics"](rows, 1.0)["passes"]
      rows = [{"answered": True, "spent": 23.0, "budget": 20.0} for _ in range(40)]
      assert SCRIPT["mechanics"](rows, 1.2)["passes"] and SCRIPT["mechanics"](rows, 1.0)["over_limit"] == 40


  def test_overturned_calls_are_split_four_ways_and_by_group():
      def row(before, go, correct):
          return {"calls": {"reader": None if before is None else {"go": before}}, "go": go, "correct": correct}

      rows = {"a": row(False, True, True), "b": row(False, True, False), "c": row(True, False, True),
              "d": row(True, False, False), "e": row(True, True, True), "f": row(None, True, True)}
      groups = {"a": "relief", "b": "relief", "c": "confirmed", "d": "ordinary", "e": "ordinary", "f": "relief"}
      out = SCRIPT["overturned"](rows, groups)
      assert out["all"] == {"nogo_to_go_right": 1, "nogo_to_go_wrong": 1, "go_to_nogo_right": 1, "go_to_nogo_wrong": 1}
      assert out["relief"]["nogo_to_go_right"] == 1 and out["confirmed"]["go_to_nogo_right"] == 1
      assert out["no_reader_call"] == 1


  def test_the_bull_finds_the_good_news_only_where_the_reader_had_not():
      def opens(doc, step):
          return {"tool": "open_document", "args": {"doc_id": doc}, "refused": False, "cost": 1.0, "step": step}

      traces = {"a": [opens("minutes", "bull")], "b": [opens("minutes", "reader"), opens("minutes", "bull")],
                "c": [opens("legal", "bull")]}
      assert SCRIPT["bull_found"](traces, {"a": "minutes", "b": "minutes", "c": "minutes"}, ["a", "b", "c"]) == 1


  def test_the_analysis_reads_a_finished_pilot(finished, tmp_path):
      out = SCRIPT["analyse"](finished)
      ks = keys(finished)
      relief = sum(k.truth.case_type == "relief" for k in ks.values())
      gos = sum(k.truth.go for k in ks.values())
      assert relief == 2 and gos > 0
      assert out["deals"] == 5 and out["reading"] == "debate doesn't help"  # no lower regret than an always-right s1b
      assert all(out["mechanics"][s]["passes"] for s in DEBATES)
      assert out["overturned"]["debate_s"]["all"]["nogo_to_go_right"] == gos
      assert out["bull_found"] == {"debate_x": relief, "debate_s": relief}
      assert out["versus"]["debate_s"]["s1b"]["tied"] == 5 and out["x_minus_s"]["n"] == 5
      assert out["steps"]["debate_x"]["bull"]["cost"] is None and out["steps"]["debate_x"]["bear"]["cost"] == 0.1
      assert out["systems"]["debate_x"]["relief"]["n"] == relief and "decoy_pages" in out["systems"]["s4"]["all"]
      path = tmp_path / "x.json"
      assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 0
      assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 1  # never overwrites


  def test_the_analysis_refuses_a_system_missing_a_deal(finished, tmp_path):
      (finished / "runs" / "debate_s" / "test-001.json").unlink()
      with pytest.raises(ValueError, match="debate_s.*test-001"):
          SCRIPT["analyse"](finished)
      assert SCRIPT["main"](["--data", str(finished), "--out", str(tmp_path / "x.json")]) == 1
      assert not (tmp_path / "x.json").exists()


  def test_the_analysis_refuses_another_model_or_unfrozen_prompts(finished):
      write(finished, "s4", "test-002", [submit(True)], models=("claude-sonnet-5-5",))
      with pytest.raises(ValueError, match="s4/test-002"):
          SCRIPT["analyse"](finished)
      write(finished, "s4", "test-002", [submit(True)])
      path = finished / "runs" / "debate_x" / "test-003.json"
      path.write_text(json.dumps(json.loads(path.read_text()) | {"prompts": {"bull": "old"}}))
      with pytest.raises(ValueError, match="frozen prompts.*debate_x/test-003"):
          SCRIPT["analyse"](finished)
  ```

- [ ] **Step 2: Run the tests to see them fail**

  Run: `.venv/bin/python -m pytest tests/bench/test_debate_pilot.py -q`

  Expected: a collection error, `FileNotFoundError` for `scripts/debate_pilot.py`.

- [ ] **Step 3: Write `scripts/debate_pilot.py`**

  ```python
  """The debate pilot's analysis (spec docs/superpowers/specs/2026-10-09-debate-pilot-design.md §3), run once on the
  finished runs. Reads answer keys and runs; never calls a model. From the repository root:

    .venv/bin/python scripts/debate_pilot.py --data data/pilot-r2u --out docs/results/debate-pilot.json"""
  import argparse
  import json
  import math
  import sys
  from pathlib import Path

  import numpy as np

  sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
  sys.path.insert(0, str(Path(__file__).resolve().parent))
  from acqlab.bench import analysis, debate
  from acqlab.bench.referee import opened, rows as trace_rows
  from upside_pilot import GROUPS, MODEL, group, keys, load, settling_doc, stats

  DEBATES = debate.SYSTEMS
  SYSTEMS = ("s1b", "s4", *DEBATES)
  LIMIT = {"debate_x": 1 + debate.BULL_SHARE, "debate_s": 1.0}  # spec §3: most pages, as a share of the budget
  EPS = 1e-9


  def mechanics(rows: list[dict], limit: float) -> dict:
      """Spec §3: the referee answers at least 95% of deals (38 of 40), and no deal reads past its limit."""
      m = {"n": len(rows), "answered": sum(r["answered"] for r in rows),
           "over_limit": sum(r["spent"] > limit * r["budget"] + EPS for r in rows)}
      return m | {"passes": m["answered"] >= math.ceil(0.95 * m["n"]) and m["over_limit"] == 0}


  def meets(name: str, regret: dict, confirmed_false_go: dict, mech: dict) -> bool:
      """Spec §3's three conditions for one debate system."""
      return (regret[name] < regret["s1b"] and confirmed_false_go[name] <= confirmed_false_go["s1b"] + 1
              and mech[name]["passes"])


  def reading(regret: dict, confirmed_false_go: dict, mech: dict) -> str:
      if meets("debate_s", regret, confirmed_false_go, mech):
          return "debate helps at the same budget"
      if meets("debate_x", regret, confirmed_false_go, mech):
          return "debate helps only with extra pages"
      return "debate doesn't help"


  def versus(a: dict, b: dict) -> dict:
      """a − b in regret, paired: the bootstrap range and deals won, lost and tied."""
      d = [a[x]["regret"] - b[x]["regret"] for x in sorted(set(a) & set(b))]
      return analysis.compare(a, b) | {"won": sum(x < -EPS for x in d), "lost": sum(x > EPS for x in d),
                                       "tied": sum(abs(x) <= EPS for x in d)}


  def overturned(rows: dict[str, dict], groups: dict[str, str]) -> dict:
      """Spec §3 item 4: deals where the referee's call differs from the reader's, four ways, overall and by group.
      A deal whose reader gave no call has nothing to overturn; those are counted apart."""
      kinds = [f"{a}_to_{b}_{c}" for a, b in (("nogo", "go"), ("go", "nogo")) for c in ("right", "wrong")]
      out = {g: dict.fromkeys(kinds, 0) for g in ("all", *GROUPS)}
      none = 0
      for deal, r in rows.items():
          before = r["calls"]["reader"]
          if before is None:
              none += 1
              continue
          if before["go"] != r["go"]:
              k = f"{'go' if before['go'] else 'nogo'}_to_{'go' if r['go'] else 'nogo'}_" \
                  f"{'right' if r['correct'] else 'wrong'}"
              out["all"][k] += 1
              out[groups[deal]][k] += 1
      return out | {"no_reader_call": none}


  def by_step(rows: dict[str, dict], traces: dict[str, list[dict]]) -> dict:
      """Each step's mean cost and pages per deal (a timed-out step's cost is unknown and left out)."""
      out = {}
      for s in ("reader", "bull", "bear", "referee"):
          costs = [r["step_cost"][s] for r in rows.values() if r["step_cost"][s] is not None]
          out[s] = {"cost": float(np.mean(costs)) if costs else None,
                    "pages": float(np.mean([sum(x["cost"] for x in traces[d] if x.get("step") == s
                                                and x["tool"] == "open_document" and not x.get("refused"))
                                            for d in rows]))}
      return out


  def bull_found(traces: dict[str, list[dict]], settling: dict[str, str], relief: list[str]) -> int:
      """Spec §3 item 5: relief deals where the bull opened the settling document and the reader had not."""
      def did(d, s):
          return settling[d] in opened([x for x in traces[d] if x.get("step") == s])
      return sum(did(d, "bull") and not did(d, "reader") for d in relief)


  def check(by: dict[str, dict[str, dict]], ks: dict, split: str) -> None:
      """Refuse a pilot that is not the one pre-registered: a system missing deals, a row on another model, or a
      debate row made with prompts other than the frozen ones."""
      for s, rows in by.items():
          if set(rows) != set(ks):
              raise ValueError(f"{s} runs cover {sorted(set(rows) ^ set(ks))} differently from the {split} split")
      wrong = [f"{s}/{d}" for s, rows in by.items() for d, r in rows.items() if r["models"] != [MODEL]
               and not (not r["models"] and (r["status"] == "timeout" or r["timeouts"] >= r["sessions"]))]
      if wrong:
          raise ValueError(f"rows not run on {MODEL}: {wrong}")
      stale = [f"{s}/{d}" for s in DEBATES for d, r in by[s].items() if r.get("prompts") != debate.PROMPT_SHA]
      if stale:
          raise ValueError(f"rows not made with the frozen prompts: {stale}")


  def analyse(data: Path, split: str = "test") -> dict:
      ks = keys(data, split)
      by = {s: load(data, s) for s in SYSTEMS}
      check(by, ks, split)
      missing = {s: sorted(d for d in ks if not (data / "runs" / s / f"{d}.trace.jsonl").exists()) for s in DEBATES}
      traces = {s: {d: [] if d in missing[s] else trace_rows(data / "runs" / s / f"{d}.trace.jsonl") for d in ks}
                for s in DEBATES}
      groups = {d: group(k) for d, k in ks.items()}
      ids = {g: sorted(d for d in ks if groups[d] == g) for g in GROUPS} | {"all": sorted(ks)}
      settling = {d: settling_doc(ks[d]) for d in ids["relief"]}

      def st(rows):
          out = stats(rows)
          return out | {"decoy_pages": float(np.mean([r["decoy_pages"] for r in rows]))} if rows else out

      systems = {s: {g: st([rows[d] for d in v]) for g, v in ids.items()} for s, rows in by.items()}
      mech = {s: mechanics(list(by[s].values()), LIMIT[s]) for s in DEBATES}
      regret = {s: systems[s]["all"]["regret"] for s in SYSTEMS}
      false_go = {s: systems[s]["confirmed"].get("false_go", 0) for s in SYSTEMS}
      return {
          "deals": len(ks), "reading": reading(regret, false_go, mech), "mechanics": mech, "missing_traces": missing,
          "systems": systems,
          "versus": {s: {b: versus(by[s], by[b]) for b in ("s1b", "s4")} for s in DEBATES},
          "x_minus_s": versus(by["debate_x"], by["debate_s"]),
          "overturned": {s: overturned(by[s], groups) for s in DEBATES},
          "bull_found": {s: bull_found(traces[s], settling, ids["relief"]) for s in DEBATES},
          "steps": {s: by_step(by[s], traces[s]) for s in DEBATES},
          "step_timeouts": {s: sum(r["timeouts"] for r in by[s].values()) for s in DEBATES},
      }


  def main(argv: list[str] | None = None) -> int:
      ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
      ap.add_argument("--data", type=Path, required=True)
      ap.add_argument("--split", default="test")
      ap.add_argument("--out", type=Path, required=True, help="where the analysis goes (never overwritten)")
      args = ap.parse_args(argv)
      if args.out.exists():  # one-shot, like the earlier pilots: never overwrite a result already written
          print(f"Refusing: {args.out} already exists")
          return 1
      try:
          out = analyse(args.data, args.split)
      except ValueError as e:
          print(f"Refusing: {e}")
          return 1
      args.out.write_text(json.dumps(out, indent=2))
      print(json.dumps({"reading": out["reading"], "mechanics": out["mechanics"],
                        "regret": {s: out["systems"][s]["all"]["regret"] for s in SYSTEMS}}, indent=2))
      return 0


  if __name__ == "__main__":
      raise SystemExit(main())
  ```

- [ ] **Step 4: Run the tests**

  Run: `.venv/bin/python -m pytest tests/bench/test_debate_pilot.py -q`

  Expected: 7 passed.

  Then run: `.venv/bin/python -m pytest -q`

  Expected: 450 passed.

  Then confirm the frozen files are untouched: `git diff --stat s4-frozen-plan5 -- acqlab/agents acqlab/routers` should print nothing.

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/debate_pilot.py tests/bench/test_debate_pilot.py
  git commit -m "feat: debate pilot analysis: the fixed reading, mechanics, overturned calls, the bull's finds, each step's share

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 5: Resume point, smoke test, freeze (the controller, after the final review)

The controller does this task itself, not an implementer subagent. **Steps 2 onwards spend real Claude usage and wait for the user's explicit OK.**

- [ ] **Step 1: The resume point.**

  In `docs/HANDOFF.md`, update "Resume here":
  - the debate pilot is built (Tasks 1–4, with the commit range and 450 tests);
  - next comes the smoke test, which needs the user's OK.

  Commit it with the trailer.

- [ ] **Step 2 (user's OK): The smoke test**

  Run this on two practice deals that already have `s1b` runs, about $1–2:

  ```bash
  .venv/bin/python -m acqlab.bench.debate --data data/cal-r2 --split dev --deals dev-000,dev-001 --confirm-claude
  ```

  Check the following:
  - every step submitted (`calls` in each row);
  - `spent` is at most 1.2·B for `debate_x` and at most B for `debate_s`;
  - the referee's session got every opened document and all three summaries (rebuild its prompt with `judge_prompts` from the step traces);
  - `models == ["claude-opus-5-5"]`.

  Prompts may be fixed here, and only here. After any prompt edit, delete the smoke runs and rerun them.

- [ ] **Step 3: The pre-registration**

  Write `docs/results/debate-pilot-prereg.md`. It contains:
  - the spec §3, restated;
  - `debate.PROMPT_SHA`, from `.venv/bin/python -c "from acqlab.bench import debate; print(debate.PROMPT_SHA)"`;
  - the CLI version (`claude --version`);
  - the smoke test's outcome and cost.

  Commit it before any pilot run.

- [ ] **Step 4 (user's OK): The pilot**

  Run this on the 40 `pilot-r2u` deals, about $20–28:

  ```bash
  .venv/bin/python -m acqlab.bench.debate --data data/pilot-r2u --confirm-claude
  ```

  If the run exits with 2, rerun the same command after the usage limit resets; it skips finished deals.

- [ ] **Step 5: Analysis and write-up**

  Run the analysis once:

  ```bash
  .venv/bin/python scripts/debate_pilot.py --data data/pilot-r2u --out docs/results/debate-pilot.json
  ```

  Then write the plain-language results in `docs/results/debate-pilot.md`, and add a `docs/HANDOFF.md` bullet.

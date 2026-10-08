# Hidden-Upside Pilot (Stage 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `r2u` deals (a seller-disclosed worry that turns out small, "relief", or large, "confirmed"), generate the 40 pilot deals, pass the free checks, and commit the fixed rules. The paid runs are not part of this plan.

**Architecture:**
- **Roles and generator.** Two new fact roles (`relief`, `confirmed`) are placed by `roles.place`. The generator (`truth.py`) plans one flagged issue per flagged deal and stores it in a new `DealTruth.flag`.
- **Teaser and checks.** The teaser gains one disclosure line (`render.disclosure`), and `validate.py` checks the new deals.
- **Batch.** `batch.cases_for` assigns exact quotas.
- **Script.** `scripts/upside_pilot.py` runs the free checks now and the analysis after the paid runs.
- **Unchanged:** every `r2` deal generates exactly as before, and the frozen team is untouched.

**Tech Stack:** Python 3.12, numpy, pydantic, pytest. Run everything with `.venv/bin/python` from the repository root.

**Spec:** `docs/superpowers/specs/2026-10-08-upside-pilot-design.md`. Read §1 and §2 before starting.

## Global Constraints

- **The frozen team:** `acqlab/agents` and `acqlab/routers` must stay byte-identical to tag `s4-frozen-plan5`. Don't edit any file there. The existing test `tests/bench/test_sim.py` checks this.
- **No model calls:** no Claude or Codex calls and no paid runs. Deals use template prose (no `--llm` flag).
- **`r2` deals unchanged:** they must generate exactly as before, apart from the `generator_version` label. A test pins this with a hash.
- **Version:** `GENERATOR_VERSION` becomes `"4.1.0"`.
- **Pilot deals:** 40 deals, split `test`, profile `r2u`, base seed `11250000`, output `data/pilot-r2u` (git-ignored).
- **Quota:** 16 `relief`, 8 `confirmed`, 16 ordinary. Profile `r2u` = `r2` plus quota shares `{"relief": 0.4, "confirmed": 0.2}`.
- **Constants:**
  - `LOOK = 0.5`;
  - `RELIEF_FLOOR = 0.05`;
  - the "looks bad" margin is `PULL_BACK` (0.10), and the truth-side margin is `MARGIN` (0.20).
- **Test counts:** the suite has 397 tests now. Each task states the exact count after it; the final count is 415.
- **Commits:** every commit message ends with a blank line and then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Applying the edits:** each code step gives a unified diff against the current file. Apply it exactly: same names, comments and line breaks. Then run the stated command.

## Review Focus

Each of these is pinned by a test in the task named.
- **A relief amount that rounds to $0.0M on a tiny bound** must be caught by `check_engine`, so the deal regenerates (Task 3, `test_engine_check_catches_a_zero_relief_amount_...`).
- **A real amount showing up in the teaser,** for example a settled amount written next to the disclosure, must be a leak problem. A leak word inside the disclosure line itself must not be (Task 3, `test_leak_check_allows_only_the_disclosure_...`).
- **Old answer keys without a `flag` field** must still load, with `flag` set to `None` (Task 2, `test_unflagged_deals_have_no_flag_and_old_answer_keys_load`).
- **A quota on a split size that isn't a multiple of 5** must round per case and never overfill (Task 4, `test_cases_for_gives_exact_seeded_quotas_...`).
- **A team run with no trace, or one that never proposed,** must still analyse, with its warning reported as `None` (Task 5, `test_a_missing_trace_or_a_team_that_never_proposed_still_analyses`).

---

### Task 1: The `relief` and `confirmed` roles

**Files:**
- Modify: `acqlab/generator/roles.py`
- Test: `tests/generator/test_roles.py`

**Interfaces:**
- **Produces** these constants in `acqlab.generator.roles`:
  - `LOOK = 0.5`;
  - `RELIEF_FLOOR = 0.05`;
  - `FLAG_ROLES = ("relief", "confirmed")`.
- **Produces** a change to `place(b, roles, rng)`: it accepts the roles `"relief"` and `"confirmed"`.
  - It returns `None` when the trap's flip point `t` is `None` or `t >= LOOK - PULL_BACK`.
  - It also returns `None` when the role's range is empty.
  - Otherwise the severity is drawn uniformly from `[RELIEF_FLOOR, t - MARGIN]` for relief, or `[t + MARGIN, 1]` for confirmed.

- [ ] **Step 1: Write the failing tests.** Apply this diff to `tests/generator/test_roles.py`:

```diff
--- a/tests/generator/test_roles.py
+++ b/tests/generator/test_roles.py
@@ -2,8 +2,8 @@
 import pytest
 
 from acqlab.engine import walk_away
-from acqlab.generator.roles import (DECOY_MOVE, MARGIN, PULL_BACK, UNRESOLVED_WIDTH, amounts, flip_severity, go,
-                                    place)
+from acqlab.generator.roles import (DECOY_MOVE, LOOK, MARGIN, PULL_BACK, RELIEF_FLOOR, UNRESOLVED_WIDTH, amounts,
+                                    flip_severity, go, place)
 from acqlab.generator.sample import sample_base, with_asking
 from acqlab.generator.traps import params_for
 
@@ -78,3 +78,40 @@
     deals, rng = face_go_deals(1)
     b = with_asking(deals[0], 0.3 * deals[0].deal.asking_price)  # so cheap nothing flips it
     assert place(b, {"addback": "flipper"}, rng) is None
+
+
+def flaggable_deals(n: int):
+    """Face-value go deals whose add-back flip point leaves room for both flagged roles (upside spec §1.2)."""
+    rng, found = np.random.default_rng(1), []
+    while len(found) < n:
+        b = sample_base(rng)
+        b = with_asking(b, 0.75 * b.deal.asking_price)
+        t = flip_severity(b, "addback")
+        if go(b, {}) and t is not None and RELIEF_FLOOR + MARGIN <= t < LOOK - PULL_BACK:
+            found.append(b)
+    return found, rng
+
+
+def test_relief_fails_at_half_the_bound_but_its_real_amount_is_small_and_never_zero():
+    deals, rng = flaggable_deals(5)
+    for b in deals:
+        s = place(b, {"addback": "relief"}, rng)["addback"]["severity"]
+        t = flip_severity(b, "addback")
+        assert not go(b, {"addback": LOOK - PULL_BACK})  # priced at half its bound, by the margin, it fails
+        assert RELIEF_FLOOR <= s <= t - MARGIN and go(b, {"addback": s})
+
+
+def test_confirmed_fails_at_half_the_bound_and_its_real_amount_clears_the_flip_point():
+    deals, rng = flaggable_deals(5)
+    for b in deals:
+        s = place(b, {"addback": "confirmed"}, rng)["addback"]["severity"]
+        assert not go(b, {"addback": LOOK - PULL_BACK})
+        assert s >= flip_severity(b, "addback") + MARGIN and not go(b, {"addback": s})
+
+
+def test_flagged_roles_are_refused_when_half_the_bound_would_not_fail():
+    deals, rng = face_go_deals(20)
+    late = [b for b in deals if flip_severity(b, "addback") >= LOOK - PULL_BACK]
+    assert late
+    for b in late:
+        assert place(b, {"addback": "relief"}, rng) is None and place(b, {"addback": "confirmed"}, rng) is None
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest -q tests/generator/test_roles.py`
Expected: an error during collection, `ImportError: cannot import name 'LOOK'`.

- [ ] **Step 3: Implement.** Apply this diff to `acqlab/generator/roles.py`:

```diff
--- a/acqlab/generator/roles.py
+++ b/acqlab/generator/roles.py
@@ -10,6 +10,9 @@
 PULL_BACK = 0.10  # an interaction still flips if either value is pulled back this far
 DECOY_MOVE = 0.05  # decoys move walk-away by at least 5% of EV
 UNRESOLVED_WIDTH = 0.40  # documented range width for unresolvable facts
+LOOK = 0.5  # upside spec §1.2: a flagged worry priced at half its stated bound already fails, by PULL_BACK
+RELIEF_FLOOR = 0.05  # a relief amount is never 0: zero renders as "no such issue", contradicting the teaser
+FLAG_ROLES = ("relief", "confirmed")  # the flagged issue's roles: the teaser states its bound (upside spec §1.1)
 
 
 def amounts(b: BaseDeal, sev: dict[str, float]) -> dict[str, float]:
@@ -67,6 +70,13 @@
             if lo is None or lo > _upper(t):
                 return None
             out[trap] = {"severity": float(rng.uniform(lo, _upper(t))), "documented": None}
+        elif role in FLAG_ROLES:
+            if t is None or t >= LOOK - PULL_BACK:
+                return None
+            lo, hi = (RELIEF_FLOOR, t - MARGIN) if role == "relief" else (t + MARGIN, 1.0)
+            if lo > hi:
+                return None
+            out[trap] = {"severity": float(rng.uniform(lo, hi)), "documented": None}
         elif role == "unresolvable":
             for _ in range(20):
                 low = float(rng.uniform(0.0, 1.0 - UNRESOLVED_WIDTH))
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest -q tests/generator/test_roles.py`
Expected: `9 passed`.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `400 passed`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/generator/roles.py tests/generator/test_roles.py
git commit -m "feat(generator): relief and confirmed roles for flagged deals (upside spec §1.2)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 2: Flagged deals in the generator

**Files:**
- Modify: `acqlab/generator/truth.py`
- Test: `tests/generator/test_truth.py`

**Interfaces:**
- **Consumes:** `LOOK`, `RELIEF_FLOOR` and `FLAG_ROLES` from `acqlab.generator.roles` (Task 1).
- **Produces:**
  - `class Flag(BaseModel)` with `trap: str` and `bound: float` ($M, the trap's worst case).
  - `DealTruth.flag: Flag | None = None`.
  - `PROFILES["r2u"] == PROFILES["r2"] | {"quota": {"relief": 0.4, "confirmed": 0.2}}`.
  - `generate(..., force_case="relief" | "confirmed", profile="r2u")` returns a face-value GO deal with exactly one fact of that role. `t.flag` names that fact's trap and its `worst`. Its `case_type` is `"relief"` or `"confirmed"`, and its `go` is True for relief and False for confirmed.
  - `GENERATOR_VERSION == "4.1.0"`.

- [ ] **Step 1: Write the failing tests.** Apply this diff to `tests/generator/test_truth.py`:

```diff
--- a/tests/generator/test_truth.py
+++ b/tests/generator/test_truth.py
@@ -1,11 +1,16 @@
+import hashlib
+import json
 import warnings
 from collections import Counter
 
 import numpy as np
 import pytest
 
-from acqlab.generator.traps import TEST_ONLY, TRAPS
-from acqlab.generator.truth import (PROFILES, cross_fit, generate, prior_draws, simulate, value_groups,
+from acqlab.engine import is_go
+from acqlab.generator.render import render, teaser_text
+from acqlab.generator.roles import LOOK, MARGIN, PULL_BACK, flip_severity
+from acqlab.generator.traps import TEST_ONLY, TRAPS, params_for
+from acqlab.generator.truth import (PROFILES, DealTruth, cross_fit, generate, prior_draws, simulate, value_groups,
                                    value_of_knowing)
 
 
@@ -101,3 +106,39 @@
             assert f.role != "unresolvable" or f.placement != "calculation"
     assert any(f.placement == "minutes" for t in hard for f in t.facts)
     assert PROFILES["r3"]["budget_share"] < PROFILES["r2"]["budget_share"]
+
+
+def test_flagged_deals_look_bad_and_their_type_matches_the_truth():
+    for case in ("relief", "confirmed"):
+        for seed in range(4):
+            t = generate("x", "test", 100 + seed, mc=20, force_case=case, profile="r2u")
+            f = next(f for f in t.facts if f.trap == t.flag.trap)
+            assert t.case_type == case and f.role == case and t.flag.bound == f.worst
+            assert [x.role for x in t.facts].count(case) == 1
+            assert t.face_go and t.go == (case == "relief")
+            assert not is_go(t.deal, params_for({f.trap: (LOOK - PULL_BACK) * f.worst}, t.base))
+            tf = flip_severity(t.base, f.trap) * f.worst
+            assert (0 < f.amount <= tf - MARGIN * f.worst + 0.05) if case == "relief" else f.amount >= tf + MARGIN * f.worst - 0.05
+
+
+def test_unflagged_deals_have_no_flag_and_old_answer_keys_load():
+    assert generate("x", "test", 3, mc=20, profile="r2").flag is None
+    old = json.loads(generate("x", "test", 3, mc=20, profile="r2").model_dump_json())
+    del old["flag"]  # an answer key written before generator 4.1.0
+    assert DealTruth.model_validate(old).flag is None
+
+
+def test_r2_deals_generate_exactly_as_before_the_flagged_deals():
+    h = hashlib.sha256()
+    for s in range(5):
+        t = generate("x", "test", 9010000 + s, mc=40, profile="r2")
+        docs, evidence = render(t)
+        h.update(json.dumps(t.model_dump(exclude={"generator_version", "flag"}), sort_keys=True).encode())
+        h.update(teaser_text(t).encode() + "".join(d.render() for d in docs).encode())
+        h.update(json.dumps([e.model_dump() for e in evidence], sort_keys=True).encode())
+    # pinned from generator 4.0.0 (commit aba3dfd) on the same five seeds
+    assert h.hexdigest() == "fec520f94e004511c476da8e395bc73f991105df45fc9da6a0166aba6d4c8a86"
+
+
+def test_r2u_is_r2_plus_a_quota_of_flagged_deals():
+    assert PROFILES["r2u"] == PROFILES["r2"] | {"quota": {"relief": 0.4, "confirmed": 0.2}}
```

Leave the pinned hash `fec520f9…8a86` exactly as written. It was computed from the current generator (4.0.0) on those five seeds, and it is what proves `r2` deals don't change.

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest -q tests/generator/test_truth.py`
Expected: 3 failures among the four new tests: no `r2u` profile, and no `flag` field. The pinned-hash test already passes, because the current generator is the one it was pinned from.

- [ ] **Step 3: Implement.** Apply this diff to `acqlab/generator/truth.py`:

```diff
--- a/acqlab/generator/truth.py
+++ b/acqlab/generator/truth.py
@@ -3,11 +3,12 @@
 from pydantic import BaseModel
 
 from acqlab.engine import Deal, Params, evaluate, is_go, walk_away
-from acqlab.generator.roles import DECOY_MOVE, MARGIN, PULL_BACK, flip_severity, min_severity_to_move, place
+from acqlab.generator.roles import (DECOY_MOVE, FLAG_ROLES, LOOK, MARGIN, PULL_BACK, RELIEF_FLOOR, flip_severity,
+                                    min_severity_to_move, place)
 from acqlab.generator.sample import BaseDeal, sample_base, with_asking
 from acqlab.generator.traps import PARAM, TRAPS, params_for, sample_variant, trap_weight, worst_amount
 
-GENERATOR_VERSION = "4.0.0"
+GENERATOR_VERSION = "4.1.0"  # 4.1.0: flagged deals (upside spec); r2 deals generate as before
 ASK_NOISE = (-0.15, 0.10)  # asking = market EV x (1 + N(mean, sd)); a 20% hurdle rarely clears at market prices
 CASE_MIX = {"clean": 0.15, "flip": 0.25, "interaction": 0.10, "none": 0.50}
 FACE_GO = 0.97  # P(face-value go) for clean and no-flip deals; flip deals are always face-value go
@@ -19,7 +20,7 @@
     """Placement weights (mode -> weight) for every role alike, so where a sentence sits says nothing about whether it
     is a real problem (Plan 4b: search is back, and it would see a role-dependent placement). An unresolvable fact
     states its range in the same places, except a calculation."""
-    return {r: weights for r in ("flipper", "interaction", "decoy", "clean")} | {
+    return {r: weights for r in ("flipper", "interaction", "decoy", "clean", *FLAG_ROLES)} | {
         "unresolvable": {k: w for k, w in weights.items() if k != "calculation"}}
 
 
@@ -38,8 +39,16 @@
     "r2": {"case_mix": _MULTI_ISSUE, "placement": _BURIED, "budget_share": 0.25, "clean_item_power": 1.0},
 }
 PROFILES["r3"] = PROFILES["r2"] | {"budget_share": 0.20}
+# Upside spec §1.3: r2 plus fixed shares of flagged deals, assigned by batch.cases_for; the rest draw from r2's mix.
+PROFILES["r2u"] = PROFILES["r2"] | {"quota": {"relief": 0.4, "confirmed": 0.2}}
 
 
+class Flag(BaseModel):
+    """The teaser's seller disclosure (upside spec §1.1): one issue type and its stated upper bound."""
+    trap: str
+    bound: float  # $M: the trap's worst case
+
+
 class Fact(BaseModel):
     trap: str
     variant: str
@@ -69,6 +78,7 @@
     debt_limit: str
     case_type: str
     profile: str = "base"  # difficulty profile (PROFILES); deals before generator 4.0.0 are "base"
+    flag: Flag | None = None  # relief and confirmed deals only (upside spec)
 
     @property
     def deal(self) -> Deal:
@@ -79,7 +89,7 @@
 
 
 def case_type(roles: list[str]) -> str:
-    for role, case in (("flipper", "flip"), ("interaction", "interaction"), ("unresolvable", "unresolvable"),
+    for role, case in (("relief", "relief"), ("confirmed", "confirmed"), ("flipper", "flip"), ("interaction", "interaction"), ("unresolvable", "unresolvable"),
                        ("decoy", "decoy")):
         if role in roles:
             return case
@@ -103,6 +113,12 @@
         if not can_flip:
             return None
         roles[_pick(rng, {t: trap_weight(t, b) for t in can_flip})] = "flipper"
+    if case in FLAG_ROLES:  # upside spec §1.2: the deal fails at half the bound, with room for the role's amount
+        can_flag = [t for t in TRAPS if alone[t] is not None and alone[t] < LOOK - PULL_BACK
+                    and (case == "confirmed" or alone[t] - MARGIN >= RELIEF_FLOOR)]
+        if not can_flag:
+            return None
+        roles[_pick(rng, {t: trap_weight(t, b) for t in can_flag})] = case
     if case == "interaction":
         w0 = walk_away(b.deal, Params())
         drop = {t: w0 - walk_away(b.deal, params_for({t: worst_amount(t, b)}, b)) for t in TRAPS
@@ -193,7 +209,7 @@
     case = force_case or _pick(rng, prof["case_mix"])  # drawn once, so hard cases aren't swapped for easy ones on retry
     for _ in range(max_tries):
         b = sample_base(rng)
-        want_go = case in ("flip", "interaction") or rng.random() < FACE_GO
+        want_go = case in ("flip", "interaction", *FLAG_ROLES) or rng.random() < FACE_GO
         ask = b.deal.asking_price * (1 + rng.normal(*ASK_NOISE))
         b = with_asking(b, ask)
         if is_go(b.deal, Params()) != want_go:
@@ -237,7 +253,9 @@
         f.alone_flips = is_go(b.deal, params_for({f.trap: f.amount}, b)) != face_go
     params = params_for({f.trap: f.amount for f in facts}, b)
     go_ = is_go(b.deal, params)
-    explained = any(f.role in ("flipper", "interaction") or (f.role == "unresolvable" and f.alone_flips)
+    if any(f.role == "relief" for f in facts) and not go_ or any(f.role == "confirmed" for f in facts) and go_:
+        return None  # upside spec §1.2: a relief deal is truly GO, a confirmed one truly NO-GO
+    explained = any(f.role in ("flipper", "interaction", "confirmed") or (f.role == "unresolvable" and f.alone_flips)
                     for f in facts)
     if go_ != face_go and not explained:  # several decoys added up to an unlabelled flip
         return None
@@ -249,4 +267,5 @@
                      style="A" if split == "dev" else str(rng.choice(["A", "B"])), base=b, facts=facts,
                      face_walk_away=walk_away(b.deal, Params()), face_go=face_go,
                      walk_away=walk_away(b.deal, params), go=go_, debt_limit=result.debt_limit,
-                     case_type=case_type([f.role for f in facts]), profile=profile)
+                     case_type=case_type([f.role for f in facts]), profile=profile,
+                     flag=next((Flag(trap=f.trap, bound=f.worst) for f in facts if f.role in FLAG_ROLES), None))
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest -q tests/generator/test_truth.py`
Expected: `15 passed`. If `test_r2_deals_generate_exactly_as_before_the_flagged_deals` fails, an `r2` deal changed. Stop and report it; do not change the pinned hash.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `404 passed`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/generator/truth.py tests/generator/test_truth.py
git commit -m "feat(generator): flagged relief and confirmed deals and the r2u profile (upside spec §1.1-1.3)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 3: The teaser disclosure line and its checks

**Files:**
- Modify: `acqlab/generator/render.py`, `acqlab/generator/validate.py`
- Test: `tests/generator/test_render.py`, `tests/generator/test_validate.py`

**Interfaces:**
- **Consumes:** `DealTruth.flag` (Task 2), and `LOOK` from `acqlab.generator.roles` (Task 1).
- **Produces in `acqlab.generator.render`:**
  - `BOUND_PHRASE: dict[str, str]`.
  - `disclosure(t: DealTruth) -> str`: `""` for an unflagged deal; otherwise `"Seller discloses: <what>; <bound phrase> up to <money(bound)>."`. `<what>` is the flagged fact's `LABELS[variant]`, prefixed by `"for the top customer, "` for concentration.
  - `teaser_text(t)` includes that line after the capex/NWC line on flagged deals only.
- **Produces in `acqlab.generator.validate`:**
  - `check_engine(t)` adds the problems from `_flag_problems(t)`.
  - The per-fact checks gain `relief` and `confirmed`.
  - `check_leaks(t, docs, teaser)` ignores leak words inside the deal's own disclosure line. On flagged deals, it reports any fact's `money(amount)` that appears in the teaser.

- [ ] **Step 1: Write the failing tests.** Apply these diffs:

`tests/generator/test_render.py`:
```diff
--- a/tests/generator/test_render.py
+++ b/tests/generator/test_render.py
@@ -1,7 +1,7 @@
 import re
 
-from acqlab.generator.documents import PLACEHOLDER, Slot
-from acqlab.generator.render import LABELS, answer, render, span, teaser_text
+from acqlab.generator.documents import PLACEHOLDER, Slot, money
+from acqlab.generator.render import LABELS, answer, disclosure, render, span, teaser_text
 from acqlab.generator.truth import generate
 from acqlab.generator.validate import check_consistency
 
@@ -117,3 +117,16 @@
                 placed += 1
                 assert ev.docs == ["board_minutes"]
     assert placed >= 10
+
+
+def test_the_disclosure_line_names_the_flagged_issue_and_its_bound_never_an_amount():
+    for case in ("relief", "confirmed"):
+        for seed in range(4):
+            t = generate("x", "test", 200 + seed, mc=20, force_case=case, profile="r2u")
+            f = next(f for f in t.facts if f.trap == t.flag.trap)
+            line = disclosure(t)
+            assert line.startswith("Seller discloses: ") and LABELS[f.variant] in line and money(t.flag.bound) in line
+            assert line in teaser_text(t).splitlines()
+            assert not any(money(x.amount) in teaser_text(t) for x in t.facts if x.amount > 0)
+    for t in DEALS[:10]:
+        assert disclosure(t) == "" and "Seller discloses" not in teaser_text(t)
```

`tests/generator/test_validate.py`:
```diff
--- a/tests/generator/test_validate.py
+++ b/tests/generator/test_validate.py
@@ -172,3 +172,37 @@
     planted = {tid: dict(w, qoe=w["qoe"] + Counter({"zebra": tid in capex})) for tid, w in words.items()}
     assert ("capex", "qoe", "zebra") in {(r["trap"], r["doc"], r["word"]) for r in word_leaks(deals, planted)}
     assert not any(r["word"] == "zebra" for r in word_leaks(deals, words))
+
+
+FLAGGED = [generate(f"f{s}", "test", 300 + s, mc=20, force_case=c, profile="r2u")
+           for s, c in enumerate(["relief", "confirmed"] * 3)]
+
+
+def test_flagged_deals_pass_every_check_and_the_disclosure_is_not_a_leak():
+    for t in FLAGGED:
+        docs, evidence = render(t)
+        assert check_engine(t) == [] and check_leaks(t, docs, teaser_text(t)) == []
+        assert check_consistency(t, docs, evidence) == []
+
+
+def test_engine_check_catches_a_zero_relief_amount_and_a_flagged_deal_with_the_wrong_call():
+    t = next(t for t in FLAGGED if t.case_type == "relief")
+    i = next(i for i, f in enumerate(t.facts) if f.role == "relief")
+    bad = t.model_copy(deep=True)
+    bad.facts[i].amount = 0.0
+    assert any("relief amount" in p for p in check_engine(bad))
+    bad = t.model_copy(deep=True)
+    bad.go = False
+    assert any("wrong call" in p for p in check_engine(bad))
+    bad = t.model_copy(deep=True)
+    bad.flag.trap = next(f.trap for f in t.facts if f.role != "relief")
+    assert any("flag does not match" in p for p in check_engine(bad))
+
+
+def test_leak_check_allows_only_the_disclosure_and_never_a_real_amount():
+    t = FLAGGED[0]
+    docs, _ = render(t)
+    teaser = teaser_text(t)
+    assert check_leaks(t, docs, teaser + " Seller has an unfunded pension.")  # a leak word outside the line
+    f = next(f for f in t.facts if f.role == "relief")
+    assert any("amount" in p for p in check_leaks(t, docs, teaser + f" Settled for {money(f.amount)}."))
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest -q tests/generator/test_render.py tests/generator/test_validate.py`
Expected:
- `test_render.py` fails to collect with `ImportError: cannot import name 'disclosure'`.
- In `test_validate.py`, `test_engine_check_catches_a_zero_relief_amount_...` and `test_leak_check_allows_only_the_disclosure_...` fail.

- [ ] **Step 3: Implement.** Apply these diffs:

`acqlab/generator/render.py`:
```diff
--- a/acqlab/generator/render.py
+++ b/acqlab/generator/render.py
@@ -323,8 +323,24 @@
                                        "The board reviewed {{label}}: additional capital expenditure of {{amount}} per "
                                        "year.", f, **vals)}
     return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)
+
+
+BOUND_PHRASE = {"addback": "add-backs that may not be one-time", "debt_like": "estimated exposure",
+                "concentration": "annual revenue at risk",
+                "nwc": "possible shortfall in working capital at closing",
+                "capex": "possible extra capital expenditure per year"}  # upside spec §1.1
 
 
+def disclosure(t: DealTruth) -> str:
+    """The teaser's seller-disclosure line on a flagged deal (upside spec §1.1), else "". It names the issue and its
+    stated bound, never the real amount."""
+    if t.flag is None:
+        return ""
+    label = LABELS[next(f for f in t.facts if f.trap == t.flag.trap).variant]
+    what = f"for the top customer, {label}" if t.flag.trap == "concentration" else label
+    return f"Seller discloses: {what}; {BOUND_PHRASE[t.flag.trap]} up to {money(t.flag.bound)}."
+
+
 def teaser_text(t: DealTruth) -> str:
     tz, fin, pol = t.base.teaser, t.deal.financing, t.deal.policy
     covs = ", ".join(f"{c:.2f}x" for c in fin.covenant_max_leverage)
@@ -334,6 +350,7 @@
         f"Reported EBITDA: {money(tz.reported_ebitda)}; claimed add-backs: {money(tz.claimed_addbacks)}; "
         f"adjusted EBITDA: {money(tz.adj_ebitda)}",
         f"Capex: {pct(tz.capex_pct)} of revenue; net working capital: {pct(tz.nwc_pct)} of revenue",
+        *([disclosure(t)] if t.flag else []),
         f"Asking price: {money(tz.asking_price)}",
         f"Lender terms: up to {fin.max_leverage:.2f}x adjusted EBITDA at {pct(fin.interest_rate)}; amortization "
         f"{pct(fin.amortization_pct)} per year; cash sweep {pct(fin.cash_sweep)}; fees {pct(fin.fees_pct)} of price; "
```

`acqlab/generator/validate.py`:
```diff
--- a/acqlab/generator/validate.py
+++ b/acqlab/generator/validate.py
@@ -7,8 +7,8 @@
 from acqlab.engine import is_go, walk_away
 from acqlab.generator.documents import PLACEHOLDER, Doc, money, pct
 from acqlab.generator.padding import EXTRA_FILLER
-from acqlab.generator.render import FILLER, LABELS, MINUTES_TITLE, Evidence, answer, span
-from acqlab.generator.roles import DECOY_MOVE, MARGIN, PULL_BACK, UNRESOLVED_WIDTH
+from acqlab.generator.render import FILLER, LABELS, MINUTES_TITLE, Evidence, answer, disclosure, span
+from acqlab.generator.roles import DECOY_MOVE, LOOK, MARGIN, PULL_BACK, UNRESOLVED_WIDTH
 from acqlab.generator.traps import params_for
 from acqlab.generator.truth import DealTruth, Fact
 
@@ -55,6 +55,11 @@
                 problems.append(f"{f.trap}: decoy moves walk-away by only {moved:.1f}")
         if f.role == "interaction" and (flips or _go_with(t, {f.trap: min(f.worst, f.amount + slack * f.worst)}) != face):
             problems.append(f"{f.trap}: interaction fact is within the margin of flipping alone")
+        if f.role == "relief" and (f.amount <= 0 or flips or
+                                   _go_with(t, {f.trap: min(f.worst, f.amount + slack * f.worst)}) != face):
+            problems.append(f"{f.trap}: relief amount is zero or within the margin of flipping")
+        if f.role == "confirmed" and not (flips and _go_with(t, {f.trap: f.amount - slack * f.worst}) != face):
+            problems.append(f"{f.trap}: confirmed amount does not clear its flip point by the margin")
         if f.role == "unresolvable" and (f.documented is None or
                                          abs(f.documented[1] - f.documented[0] - UNRESOLVED_WIDTH * f.worst) > 0.11):
             problems.append(f"{f.trap}: unresolvable range is missing or the wrong width")
@@ -74,13 +79,31 @@
     worse = p.model_copy(update={"revenue_haircut": p.revenue_haircut + 0.05})
     if walk_away(t.deal, worse) > walk_away(t.deal, p) + 1e-3:
         problems.append("a bigger revenue haircut raises walk-away")
+    return problems + _flag_problems(t)
+
+
+def _flag_problems(t: DealTruth) -> list[str]:
+    """Upside spec §1.4: a flagged deal fails at half its bound (by PULL_BACK), and its type matches its call."""
+    flagged = [f for f in t.facts if f.role in ("relief", "confirmed")]
+    if not flagged and t.flag is None:
+        return []
+    if len(flagged) != 1 or t.flag is None or t.flag.trap != flagged[0].trap or t.flag.bound != flagged[0].worst:
+        return ["flag does not match the one relief or confirmed fact"]
+    f, problems = flagged[0], []
+    if _go_with(t, {f.trap: (LOOK - PULL_BACK) * f.worst}):
+        problems.append(f"{f.trap}: the deal does not fail with the flagged issue at half its bound")
+    if t.go != (f.role == "relief"):
+        problems.append(f"{f.role} deal has the wrong call")
     return problems
 
 
 def check_leaks(t: DealTruth, docs: list[Doc], teaser: str) -> list[str]:
     problems = [f"unexpected title {d.title!r}" for d in docs
                 if d.title not in CORE_TITLES and not d.title.startswith(("Customer Agreement — ", "Audited Financial"))]
-    problems += [f"teaser mentions {w!r}" for w in LEAK_WORDS if w in teaser.lower()]
+    body = teaser.replace(disclosure(t), "") if t.flag else teaser  # the disclosure may name its own issue
+    problems += [f"teaser mentions {w!r}" for w in LEAK_WORDS if w in body.lower()]
+    if t.flag:  # upside spec §1.4: the teaser names the bound, never a real amount
+        problems += [f"teaser shows the {f.trap} amount" for f in t.facts if f.amount > 0 and money(f.amount) in teaser]
     return problems
 
 
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest -q tests/generator/test_render.py tests/generator/test_validate.py tests/generator/test_truth.py`
Expected: all pass, with no failures.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `408 passed`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/generator/render.py acqlab/generator/validate.py tests/generator/test_render.py tests/generator/test_validate.py
git commit -m "feat(generator): the teaser's seller disclosure line and the flagged-deal checks (upside spec §1.1, §1.4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: Exact quotas in the batch, and the new deal types in the analysis

**Files:**
- Modify: `acqlab/generator/batch.py`, `acqlab/bench/analysis.py`
- Test: `tests/generator/test_batch.py`

**Interfaces:**
- **Consumes:** `PROFILES["r2u"]["quota"]` (Task 2).
- **Produces:**
  - `batch.cases_for(n: int, profile: str, seed: int) -> list[str | None]`: the quota cases at seeded-shuffled positions, `round(share * n)` of each in the quota's order, and `None` elsewhere. It returns all `None` for a profile without a quota.
  - `batch.build(..., case: str | None = None)` passes `case` on as `force_case`; showcase deals still force `"flip"`.
  - `batch.run` assigns `cases_for(n, profile, seed + SEED_OFFSET[split])` per split.
  - `analysis.CASES` gains `"relief"` and `"confirmed"`, at the end.

- [ ] **Step 1: Write the failing tests.** Apply this diff to `tests/generator/test_batch.py`:

```diff
--- a/tests/generator/test_batch.py
+++ b/tests/generator/test_batch.py
@@ -1,5 +1,6 @@
 import json
 import math
+from collections import Counter
 from functools import partial
 
 import pytest
@@ -161,3 +162,21 @@
     code = batch.main(["--out", str(tmp_path), "--dev", "1", "--test", "0", "--hand", "0", "--showcase", "0",
                        "--mc", "20"])
     assert code == 3 and "dev-000" in capsys.readouterr().out
+
+
+def test_cases_for_gives_exact_seeded_quotas_and_nothing_without_one():
+    cases = batch.cases_for(40, "r2u", 11_260_000)
+    assert Counter(cases) == {"relief": 16, "confirmed": 8, None: 16}
+    assert cases == batch.cases_for(40, "r2u", 11_260_000) and cases != batch.cases_for(40, "r2u", 1)
+    assert Counter(batch.cases_for(7, "r2u", 0)) == {"relief": 3, "confirmed": 1, None: 3}  # 2.8 and 1.4, rounded
+    assert batch.cases_for(40, "r2", 0) == [None] * 40
+
+
+def test_an_r2u_batch_has_its_quota_and_flagged_teasers(tmp_path):
+    assert batch.run(tmp_path, {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u") == []
+    keys = [json.loads((tmp_path / "truth" / f"test-{i:03d}.json").read_text())["truth"] for i in range(5)]
+    assert Counter(k["case_type"] for k in keys if k["case_type"] in ("relief", "confirmed")) == {"relief": 2,
+                                                                                                "confirmed": 1}
+    for i, k in enumerate(keys):
+        teaser = json.loads((tmp_path / "deals" / f"test-{i:03d}" / "room" / "index.json").read_text())["teaser"]
+        assert ("Seller discloses" in teaser) == (k["flag"] is not None) == (k["case_type"] in ("relief", "confirmed"))
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest -q tests/generator/test_batch.py`
Expected: 2 failures: `AttributeError: module 'acqlab.generator.batch' has no attribute 'cases_for'`, and an `r2u` batch without its quota.

- [ ] **Step 3: Implement.** Apply these diffs:

`acqlab/generator/batch.py`:
```diff
--- a/acqlab/generator/batch.py
+++ b/acqlab/generator/batch.py
@@ -36,13 +36,25 @@
     prose_fallbacks: int = 0  # paragraphs left as template prose after the LLM's attempts
 
 
-def build(deal_id: str, split: str, seed: int, *, mc: int, llm=None,
-          profile: str = "base") -> tuple[AnswerKey, list[Doc], str]:
+def cases_for(n: int, profile: str, seed: int) -> list[str | None]:
+    """Each deal's forced case (upside spec §1.3): the profile's quota shares of n, rounded, at seeded-shuffled
+    positions; None elsewhere, so those deals draw from the case mix as usual."""
+    out: list[str | None] = [None] * n
+    order, i = np.random.default_rng(seed).permutation(n), 0
+    for case, share in PROFILES[profile].get("quota", {}).items():
+        for j in order[i:i + round(share * n)]:
+            out[j] = case
+        i += round(share * n)
+    return out
+
+
+def build(deal_id: str, split: str, seed: int, *, mc: int, llm=None, profile: str = "base",
+          case: str | None = None) -> tuple[AnswerKey, list[Doc], str]:
     """One validated deal. Failed checks regenerate from a new seed. The cheap checks run on the template render
     first, so Codex is only paid for deals that pass them."""
     for k in range(MAX_RETRIES):
-        t = generate(deal_id, split, seed + k * RETRY_SEED, mc=mc, force_case="flip" if split == "showcase" else None,
-                     profile=profile)
+        t = generate(deal_id, split, seed + k * RETRY_SEED, mc=mc,
+                     force_case="flip" if split == "showcase" else case, profile=profile)
         docs, evidence = render(t)
         teaser = teaser_text(t)
         if check_engine(t) + check_leaks(t, docs, teaser):
@@ -68,9 +80,11 @@
     splits: dict[str, list[str]] = {s: [] for s in counts}
     keys, texts, pages, words = [], {}, {}, {}
     for split, n in counts.items():
+        cases = cases_for(n, profile, seed + SEED_OFFSET[split])
         for i in range(n):
             deal_id = f"{split}-{i:03d}"
-            key, docs, teaser = build(deal_id, split, seed + SEED_OFFSET[split] + i, mc=mc, llm=llm, profile=profile)
+            key, docs, teaser = build(deal_id, split, seed + SEED_OFFSET[split] + i, mc=mc, llm=llm, profile=profile,
+                                      case=cases[i])
             face = {"teaser": key.truth.base.teaser.model_dump(), "deal": key.truth.deal.model_dump()}
             key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs,
                                     budget_share=PROFILES[profile]["budget_share"], engine=face)
```

`acqlab/bench/analysis.py`:
```diff
--- a/acqlab/bench/analysis.py
+++ b/acqlab/bench/analysis.py
@@ -14,7 +14,7 @@
 from acqlab.generator.batch import AnswerKey
 from acqlab.routers.track_a import bootstrap_ci
 
-CASES = ("clean", "decoy", "flip", "interaction", "unresolvable")
+CASES = ("clean", "decoy", "flip", "interaction", "unresolvable", "relief", "confirmed")
 TARGET = ("interaction", "flip")  # H2: interaction and belief-error deals; belief-error = the flip case type
 H1_CUT, H5_FACTOR, H6_MIN = 0.25, 2.0, 5  # H1's 25% cut; "sharply" in H5 = at least double; H6's fewest deals
 BOOT, SEED = 2000, 0
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest -q tests/generator/test_batch.py tests/bench/test_analysis.py`
Expected: all pass.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `410 passed`.

- [ ] **Step 6: Commit**

```bash
git add acqlab/generator/batch.py acqlab/bench/analysis.py tests/generator/test_batch.py
git commit -m "feat(generator): exact seeded quotas for r2u batches; relief and confirmed in the analysis case types

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 5: The pilot script: free checks and analysis

**Files:**
- Create: `scripts/upside_pilot.py`
- Test: `tests/bench/test_upside_pilot.py`

**Interfaces:**
- **Consumes:**
  - `batch.run(..., profile="r2u")` (Task 4);
  - `DealTruth.flag` (Task 2);
  - `LOOK` (Task 1);
  - existing helpers: `pilot.score`, `pilot.s1b_matched`, `analysis.compare`, `analysis.CASES`, `referee.opened`, `referee.rows`.
- **Produces:** `scripts/upside_pilot.py`, with these functions:
  - `keys`, `group`, `at_half`, `free_checks`, `load`, `stats`, `settling_doc`, `warning`, `reading`, `analyse`, `main`.
  - `main(["--data", D, "--check"])` prints the free checks and returns 0 only if all hold, else 1.
  - `main(["--data", D, "--out", F])` writes the analysis once. It returns 1, without writing, if `F` exists or if the runs don't cover the split.

- [ ] **Step 1: Write the failing tests.** Create `tests/bench/test_upside_pilot.py`:

```python
import json
import runpy
import shutil
from pathlib import Path

import pytest

from acqlab.bench import pilot
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey

SCRIPT = runpy.run_path(str(Path(__file__).parents[2] / "scripts" / "upside_pilot.py"))


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """Five r2u test deals: 2 relief, 1 confirmed, 2 ordinary."""
    d = tmp_path_factory.mktemp("r2u")
    assert batch.run(d, {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u") == []
    return d


def keys(d: Path) -> dict[str, AnswerKey]:
    return {p.stem: AnswerKey.model_validate_json(p.read_text()) for p in sorted((d / "truth").glob("*.json"))}


def opens(d: Path, deal: str, doc: str) -> dict:
    pages = {x["id"]: x["pages"] for x in json.loads((d / "deals" / deal / "room" / "index.json").read_text())
             ["documents"]}
    return {"tool": "open_document", "args": {"doc_id": doc}, "refused": False, "cost": pages[doc]}


def submit(go: bool, key: AnswerKey) -> dict:
    return {"tool": "submit", "args": {"go": go, "walk_away": key.truth.walk_away, "reason": ""}, "refused": False}


def write(d: Path, system: str, deal: str, key: AnswerKey, trace: list[dict]) -> None:
    out = d / "runs" / system
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{deal}.trace.jsonl").write_text("".join(json.dumps(r) + "\n" for r in trace))
    row = pilot.score(key, system, trace, {"total_cost_usd": 0.1, "sessions": 1}, "ok")
    (out / f"{deal}.json").write_text(json.dumps(row))


@pytest.fixture
def finished(data, tmp_path):
    """A finished fake pilot. s1b reads each flagged deal's settling document and is always right. s4 prices every
    warning at 0.8 and passes on both relief deals: on the first it read the settling document, on the second not."""
    d = tmp_path / "d"
    shutil.copytree(data, d)
    relief = 0
    for deal, key in keys(d).items():
        t = key.truth
        flag = t.flag.trap if t.flag else None
        doc = SCRIPT["settling_doc"](key) if flag else None
        note = [{"tool": "note_issue", "args": {"type": flag, "chance": 0.8, "low": 0, "high": t.flag.bound,
                                                 "name": "x", "docs": []}, "refused": False}] if flag else []
        write(d, "s1b", deal, key, note + ([opens(d, deal, doc)] if doc else []) + [submit(t.go, key)])
        propose = [{"tool": "propose", "args": {"issues": [{"type": flag, "chance": 0.8, "low": 0, "high": t.flag.bound,
                                                             "name": "x", "docs": []}], "stop": False, "reason": ""},
                    "refused": False}] if flag else []
        if t.case_type == "relief":
            relief += 1
            write(d, "s4", deal, key, propose + ([opens(d, deal, doc)] if relief == 1 else []) + [submit(False, key)])
        else:
            write(d, "s4", deal, key, propose + [submit(t.go, key)])
    return d


def test_the_free_checks_pass_on_an_r2u_batch(data):
    out = SCRIPT["free_checks"](SCRIPT["keys"](data))
    assert out["counts"] == {"relief": 2, "confirmed": 1, "ordinary": 2} and out["engine_right"] == 5
    assert out["half_right"] == {"relief": 0, "confirmed": 1} and out["ignore_right"] == {"relief": 2, "confirmed": 0}
    assert out["ok"] and SCRIPT["main"](["--data", str(data), "--check"]) == 0


def test_the_analysis_reports_the_relief_measures_the_misses_and_the_warning(finished, tmp_path):
    out = SCRIPT["analyse"](finished)
    s4, s1b = out["systems"]["s4"]["relief"], out["systems"]["s1b"]["relief"]
    assert s4["n"] == s1b["n"] == 2 and s4["false_nogo"] == 2 and s1b["false_nogo"] == 0 and s4["regret"] > 0
    assert out["systems"]["s4"]["confirmed"]["false_go"] == 0 and out["systems"]["s4"]["ordinary"]["correct"] == 1.0
    assert out["relief_misses"]["s4"] == {"never_looked": 1, "looked_not_believed": 1}
    assert out["relief_misses"]["s1b"] == {"never_looked": 0, "looked_not_believed": 0}
    assert out["looked"]["s1b"] == {"relief": 1.0, "confirmed": 1.0} and out["looked"]["s4"]["relief"] == 0.5
    assert out["warning"]["s4_median"] == 0.8 and out["warning"]["s1b_share"] == 1.0
    assert out["relief_s4_minus_s1b"]["n"] == 2 and out["relief_s4_minus_s1b"]["diff"] > 0
    assert set(out["systems"]) == {"s1b", "s4", "s1b_matched"} and out["systems"]["s4"]["all"]["n"] == 5
    assert out["reading"] == "unclear"  # 2 more false NO-GOs: short of the 3 that "leans on caution" needs
    assert sum(v["n"] for v in out["by_case"]["s4"].values()) == 5
    path = tmp_path / "x.json"
    assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 0
    assert SCRIPT["main"](["--data", str(finished), "--out", str(path)]) == 1  # never overwrites


def test_the_reading_rule_follows_the_spec():
    def r(fn, regret):
        return {"false_nogo": fn, "regret": regret}
    assert SCRIPT["reading"](r(5, 0.02), r(2, 0.01)) == "team leans on caution"
    assert SCRIPT["reading"](r(5, 0.01), r(2, 0.02)) == "unclear"  # more misses but not costlier
    assert SCRIPT["reading"](r(2, 0.03), r(2, 0.01)) == "team weighs evidence fine"
    assert SCRIPT["reading"](r(3, 0.03), r(1, 0.01)) == "unclear"


def test_a_missing_trace_or_a_team_that_never_proposed_still_analyses(finished):
    flagged = next(d for d, k in keys(finished).items() if k.truth.flag)
    (finished / "runs" / "s4" / f"{flagged}.trace.jsonl").unlink()
    out = SCRIPT["analyse"](finished)
    assert out["warning"]["s4_opening_chance"][flagged] is None and out["warning"]["s4_median"] == 0.8


def test_the_analysis_refuses_runs_that_do_not_cover_the_split(finished, tmp_path):
    (finished / "runs" / "s4" / "test-001.json").unlink()
    with pytest.raises(ValueError, match="s4.*test-001"):
        SCRIPT["analyse"](finished)
    out = tmp_path / "x.json"
    assert SCRIPT["main"](["--data", str(finished), "--out", str(out)]) == 1 and not out.exists()
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest -q tests/bench/test_upside_pilot.py`
Expected: an error during collection: `FileNotFoundError` for `scripts/upside_pilot.py`.

- [ ] **Step 3: Implement.** Create `scripts/upside_pilot.py`:

```python
"""The hidden-upside pilot (spec docs/superpowers/specs/2026-10-08-upside-pilot-design.md): the free checks before any
paid run (--check, §2.2) and the analysis of finished runs (§2.3–2.4). Reads answer keys and runs; never calls a model.
From the repository root:

  .venv/bin/python scripts/upside_pilot.py --data data/pilot-r2u --check
  .venv/bin/python scripts/upside_pilot.py --data data/pilot-r2u --out docs/results/upside-pilot.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.bench import analysis, pilot
from acqlab.bench.referee import opened, rows as trace_rows
from acqlab.engine import is_go
from acqlab.generator.batch import AnswerKey
from acqlab.generator.roles import LOOK
from acqlab.generator.traps import params_for
from acqlab.generator.truth import PROFILES

SYSTEMS = ("s1b", "s4")
FLAGGED = ("relief", "confirmed")
GROUPS = (*FLAGGED, "ordinary")


def keys(data: Path, split: str = "test") -> dict[str, AnswerKey]:
    deals = json.loads((data / "splits.json").read_text())[split]
    return {d: AnswerKey.model_validate_json((data / "truth" / f"{d}.json").read_text()) for d in deals}


def group(key: AnswerKey) -> str:
    return key.truth.case_type if key.truth.case_type in FLAGGED else "ordinary"


def at_half(key: AnswerKey) -> bool:
    """The "price the warning at half" rule's call: the flagged issue at half its bound, nothing else."""
    t = key.truth
    return is_go(t.deal, params_for({t.flag.trap: LOOK * t.flag.bound}, t.base)) if t.flag else t.face_go


def free_checks(ks: dict[str, AnswerKey]) -> dict:
    """Spec §2.2: the counts, the engine on the true amounts, and the two stand-in rules. ok only if every one holds."""
    quota = {c: round(s * len(ks)) for c, s in PROFILES["r2u"]["quota"].items()}
    want = quota | {"ordinary": len(ks) - sum(quota.values())}
    by = {g: [k for k in ks.values() if group(k) == g] for g in GROUPS}
    out = {"counts": {g: len(v) for g, v in by.items()},
           "engine_right": sum(is_go(k.truth.deal, k.truth.params()) == k.truth.go for k in ks.values()),
           "half_right": {g: sum(at_half(k) == k.truth.go for k in by[g]) for g in FLAGGED},
           "ignore_right": {g: sum(k.truth.face_go == k.truth.go for k in by[g]) for g in FLAGGED}}
    out["ok"] = (out["counts"] == want and out["engine_right"] == len(ks)
                 and out["half_right"] == {"relief": 0, "confirmed": want["confirmed"]}
                 and out["ignore_right"] == {"relief": want["relief"], "confirmed": 0})
    return out


def load(data: Path, system: str) -> dict[str, dict]:
    """deal -> row, first runs only (a repeat is <deal>.r<k>.json)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((data / "runs" / system).glob("*.json"))
            if "." not in p.stem}


def stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    return {"n": len(rows), "regret": float(np.mean([r["regret"] for r in rows])),
            "correct": float(np.mean([r["correct"] for r in rows])),
            "false_go": sum(r["go"] and not r["correct"] for r in rows),
            "false_nogo": sum(not r["go"] and not r["correct"] for r in rows),
            "pages": float(np.mean([r["pages"] for r in rows])),
            "cost": float(np.mean([r["cost_usd"] or 0 for r in rows])),
            "sessions": float(np.mean([r["sessions"] for r in rows]))}


def settling_doc(key: AnswerKey) -> str:
    """The flagged issue's settling document: the last of its evidence (as recon_pilot.reached)."""
    return next(e.docs[-1] for e in key.evidence if e.trap == key.truth.flag.trap)


def warning(system: str, trace: list[dict], trap: str) -> float | bool | None:
    """Spec §2.3 item 6. s4: the chance the Deal Lead's first propose gave the flagged type (0 if left out, None if it
    never proposed). s1b: whether it ever noted the flagged type."""
    ok = [r for r in trace if not r.get("refused")]
    if system == "s4":
        first = next((r for r in ok if r["tool"] == "propose"), None)
        return None if first is None else next((float(i["chance"]) for i in first["args"]["issues"]
                                                if i["type"] == trap), 0.0)
    return any(r["tool"] == "note_issue" and r["args"]["type"] == trap for r in ok)


def reading(s4: dict, s1b: dict) -> str:
    """Spec §2.4, on the relief deals."""
    if s4["false_nogo"] - s1b["false_nogo"] >= 3 and s4["regret"] > s1b["regret"]:
        return "team leans on caution"
    if s4["false_nogo"] <= s1b["false_nogo"]:
        return "team weighs evidence fine"
    return "unclear"


def analyse(data: Path, split: str = "test") -> dict:
    ks = keys(data, split)
    by = {s: load(data, s) for s in SYSTEMS}
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{s} runs cover {sorted(set(rows) ^ set(ks))} differently from the {split} split")
    traces = {s: {d: trace_rows(p) if (p := data / "runs" / s / f"{d}.trace.jsonl").exists() else [] for d in ks}
              for s in SYSTEMS}
    ids = {g: sorted(d for d, k in ks.items() if group(k) == g) for g in GROUPS} | {"all": sorted(ks)}
    flagged = ids["relief"] + ids["confirmed"]
    systems = by | {"s1b_matched": pilot.s1b_matched(by["s1b"], by["s4"])}
    looked = {s: {d: settling_doc(ks[d]) in opened(traces[s][d]) for d in flagged} for s in SYSTEMS}
    warn = {s: {d: warning(s, traces[s][d], ks[d].truth.flag.trap) for d in flagged} for s in SYSTEMS}
    chances = [x for x in warn["s4"].values() if x is not None]
    out = {
        "deals": len(ks),
        "systems": {s: {g: stats([rows[d] for d in v]) for g, v in ids.items()} for s, rows in systems.items()},
        "by_case": {s: {c: stats([r for r in rows.values() if r["case_type"] == c]) for c in analysis.CASES}
                    for s, rows in by.items()},
        "relief_s4_minus_s1b": analysis.compare(by["s4"], by["s1b"], deals=ids["relief"]),
        "looked": {s: {g: float(np.mean([looked[s][d] for d in ids[g]])) if ids[g] else None for g in FLAGGED}
                   for s in SYSTEMS},
        "relief_misses": {s: {"never_looked": sum(not by[s][d]["correct"] and not looked[s][d] for d in ids["relief"]),
                              "looked_not_believed": sum(not by[s][d]["correct"] and looked[s][d]
                                                         for d in ids["relief"])} for s in SYSTEMS},
        "warning": {"s4_opening_chance": warn["s4"], "s4_median": float(np.median(chances)) if chances else None,
                    "s1b_noted": warn["s1b"],
                    "s1b_share": float(np.mean(list(warn["s1b"].values()))) if flagged else None},
    }
    rel = out["systems"]
    out["reading"] = reading(rel["s4"]["relief"], rel["s1b"]["relief"]) if ids["relief"] else None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--check", action="store_true", help="the free checks before any paid run (spec §2.2)")
    ap.add_argument("--out", type=Path, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.check:
        out = free_checks(keys(args.data, args.split))
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if args.out is None:
        ap.error("--out is required without --check")
    if args.out.exists():  # one-shot, like the recon pilot: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.data, args.split)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"reading": out["reading"], "relief": {s: out["systems"][s]["relief"] for s in SYSTEMS}},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest -q tests/bench/test_upside_pilot.py`
Expected: `5 passed`.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `415 passed`.

- [ ] **Step 6: Commit**

```bash
git add scripts/upside_pilot.py tests/bench/test_upside_pilot.py
git commit -m "feat: the hidden-upside pilot script: free checks and analysis (upside spec §2.2-2.4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 6: Generate the 40 deals, run the free checks, commit the fixed rules

**Files:**
- Create: `docs/results/upside-pilot-prereg.md`
- Data: `data/pilot-r2u` (git-ignored; never commit it)

**Interfaces:**
- **Consumes:** everything above.
- **Produces:**
  - the committed pre-registration;
  - the generated deals, which the paid runs (outside this plan) will use.

- [ ] **Step 1: Check the seeds don't clash**

Run: `.venv/bin/python -m acqlab.bench.testset seeds --base 11250000 --n 40 --roots data/cal-r2 data/heldout-r2 data/test-r2 data/sim-r2 data/pilot-r2`
Expected: the last line ends `clashes with base 11250000: none`. If there is a clash, stop and report it; do not pick another base.

- [ ] **Step 2: Generate the deals**

Run: `.venv/bin/python -m acqlab.generator.batch --out data/pilot-r2u --dev 0 --test 40 --hand 0 --showcase 0 --seed 11250000 --profile r2u`
Expected: `generated 40 deals into data/pilot-r2u; 0 batch problems`, and exit code 0. If `data/pilot-r2u` already exists, stop and report; do not delete it.

- [ ] **Step 3: Run the free checks**

Run: `.venv/bin/python scripts/upside_pilot.py --data data/pilot-r2u --check`
Expected: exit code 0, and JSON showing:
- `"counts": {"relief": 16, "confirmed": 8, "ordinary": 16}`;
- `"engine_right": 40`;
- `"half_right": {"relief": 0, "confirmed": 8}`;
- `"ignore_right": {"relief": 16, "confirmed": 0}`;
- `"ok": true`.

If it isn't `ok`, stop and report the JSON.

- [ ] **Step 4: List the deals by type, for the pre-registration**

Run:
```bash
.venv/bin/python -c "
import json, pathlib
from acqlab.generator.batch import AnswerKey
for p in sorted(pathlib.Path('data/pilot-r2u/truth').glob('*.json')):
    t = AnswerKey.model_validate_json(p.read_text()).truth
    print(t.id, t.case_type, t.flag.trap if t.flag else '-', t.seed)
"
```
Expected: 40 lines, each with a deal id, its type, its flagged issue (or `-`) and its seed.

- [ ] **Step 5: Write `docs/results/upside-pilot-prereg.md`.** Use exactly this text. Replace `<CHECK JSON>` with Step 3's output and `<DEAL TABLE>` with Step 4's output, both pasted verbatim inside the code fences. Replace `<DATE>` with today's date (YYYY-MM-DD) and `<HEAD>` with `git rev-parse --short HEAD`.

````markdown
# Hidden-upside pilot, stage 1: fixed rules (pre-registration)

Written on <DATE> at commit <HEAD>, before any paid run. The spec is
`docs/superpowers/specs/2026-10-08-upside-pilot-design.md` (§2.3–2.4 restated here). The analysis is
`scripts/upside_pilot.py`, which writes `docs/results/upside-pilot.json` once.

## Deals

- 40 template-prose deals, split `test`, profile `r2u`, generator 4.1.0, base seed 11,250,000, in `data/pilot-r2u`.
- The seeds were clash-checked against `data/cal-r2`, `data/heldout-r2`, `data/test-r2`, `data/sim-r2` and
  `data/pilot-r2`: none.
- 16 relief, 8 confirmed, 16 ordinary.

```text
<DEAL TABLE>
```

## Free checks (spec §2.2), all passed

```json
<CHECK JSON>
```

## Runs

- `s1b` (single Claude) and `s4` (the frozen team, tag `s4-frozen-plan5`), one run per deal.
- Model `claude-opus-5-5`, on Claude Code CLI 2.1.291 or newer.
- Runner: `.venv/bin/python -m acqlab.bench.pilot --data data/pilot-r2u --split test --n 40 --systems s1b,s4
  --confirm-claude`.
- Started only after the user's OK.

## Measures (fixed)

1. **Relief deals (16), the main measure:** false NO-GOs per system; mean regret and the paired `s4 − s1b`
   difference, with a 95% paired-bootstrap range.
2. **Confirmed deals (8):** false GOs and mean regret.
3. **Ordinary deals (16):** regret and share correct.
4. **All 40:** regret, share correct, false GO / NO-GO, pages, cost and sessions per deal, and results by deal type.
5. **Looked or not.** For each flagged deal, whether each system opened the settling document (the last document of
   the flagged issue's evidence). Each relief miss is "never looked" or "looked but didn't believe it".
6. **Took the warning.** For `s4`, the Deal Lead's first chance on the flagged issue (and the median). For `s1b`,
   whether it ever noted the flagged issue.
7. **Caution control.** `pilot.s1b_matched` over all 40, reported on the relief deals.

## How the result is read (fixed)

On the 16 relief deals:

| Result | Rule |
|---|---|
| **Team leans on caution** | `s4` has at least 3 more false NO-GOs than `s1b`, and a higher mean regret. |
| **Team weighs evidence fine** | `s4` has no more false NO-GOs than `s1b`. |
| **Unclear** | Anything else. |

The write-up also says:
- whether the team's median opening chance on the flagged issue was below 0.5 ("warning mostly not priced");
- which failure class holds most relief misses.

This is a pilot of 16 relief deals: a direction, not proof.
````

- [ ] **Step 6: Check the frozen team is untouched, and the suite still passes**

Run: `git diff --quiet s4-frozen-plan5 -- acqlab/agents acqlab/routers && echo frozen-ok`
Expected: `frozen-ok`.

Run: `.venv/bin/python -m pytest -q`
Expected: `415 passed`.

- [ ] **Step 7: Commit the pre-registration**

```bash
git add docs/results/upside-pilot-prereg.md
git commit -m "docs: hidden-upside pilot pre-registration: 40 r2u deals, free checks passed, fixed measures and reading

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Stop here.** The paid runs need the user's OK and are not part of this plan.

"""Checks run on every generated deal (design §7). Each returns a list of problems; empty means it passed."""
import re
from collections import Counter

import numpy as np

from acqlab.engine import is_go, walk_away
from acqlab.generator.documents import PLACEHOLDER, Doc, money, pct
from acqlab.generator.padding import EXTRA_FILLER
from acqlab.generator.render import FILLER, LABELS, MINUTES_TITLE, Evidence, answer, span
from acqlab.generator.roles import DECOY_MOVE, MARGIN, PULL_BACK, UNRESOLVED_WIDTH
from acqlab.generator.traps import params_for
from acqlab.generator.truth import DealTruth, Fact

ROUND_STEP = 0.051  # amounts are rounded to $0.1M, so allow half a step (plus float fuzz) of slack
CORE_TITLES = {"Confidential Information Memorandum", "Quality of Earnings Report", "Credit Agreement Excerpt",
               "Fixed Asset and Lease Schedule", "Legal Letter", MINUTES_TITLE} | set(FILLER.values()) \
    | set(EXTRA_FILLER.values())
LEAK_WORDS = ("disallow", "recur", "notice", "lawsuit", "unfunded", "shortfall", "below the peg", "deferred maintenance",
              "re-tender", "not renew")
ADDBACK_MIN_GROUP = 20  # smaller groups are too noisy to compare
# every trap's evidence lives in these
PAGE_DOCS = ("cim", "qoe", "audited", "contract_1", "assets", "legal", "board_minutes")
PAGE_Z = 4.0  # flag a length gap wider than 4 standard errors (40 comparisons per batch, so false alarms are rare)
PAGE_MIN_GROUP = 10
WORD_LEAK_AUC = 0.15  # |AUC - 0.5| above this: a word's count in a document tells trap deals from clean ones
WORD_LEAK_Z = 5.0  # ...and above 5 null standard errors, so hundreds of words tested on small groups stay quiet
TOPIC_WORDS = {"addback": "add-back", "debt_like": "debt", "concentration": "customer", "nwc": "working capital",
               "capex": "capital expenditure"}


def _go_with(t: DealTruth, amounts: dict[str, float]) -> bool:
    return is_go(t.deal, params_for(amounts, t.base))


def check_engine(t: DealTruth) -> list[str]:
    problems = []
    face = _go_with(t, {})
    w0 = walk_away(t.deal, params_for({}, t.base))
    if face != t.face_go or _go_with(t, {f.trap: f.amount for f in t.facts}) != t.go:
        problems.append("stored go/no-go does not match the engine")
    pair = [f for f in t.facts if f.role == "interaction"]
    for f in t.facts:
        flips = _go_with(t, {f.trap: f.amount}) != face
        slack = MARGIN - ROUND_STEP / f.worst
        if f.role == "clean" and f.amount != 0:
            problems.append(f"{f.trap}: clean fact has amount {f.amount}")
        if f.role == "flipper" and not (flips and _go_with(t, {f.trap: f.amount - slack * f.worst}) != face):
            problems.append(f"{f.trap}: flipper does not clear its flip point by the margin")
        if f.role == "decoy":
            moved = w0 - walk_away(t.deal, params_for({f.trap: f.amount}, t.base))
            if flips or _go_with(t, {f.trap: min(f.worst, f.amount + slack * f.worst)}) != face:
                problems.append(f"{f.trap}: decoy is within the margin of flipping")
            if moved < DECOY_MOVE * t.deal.asking_price - 0.05:
                problems.append(f"{f.trap}: decoy moves walk-away by only {moved:.1f}")
        if f.role == "interaction" and (flips or _go_with(t, {f.trap: min(f.worst, f.amount + slack * f.worst)}) != face):
            problems.append(f"{f.trap}: interaction fact is within the margin of flipping alone")
        if f.role == "unresolvable" and (f.documented is None or
                                         abs(f.documented[1] - f.documented[0] - UNRESOLVED_WIDTH * f.worst) > 0.11):
            problems.append(f"{f.trap}: unresolvable range is missing or the wrong width")
    if pair:
        joint = {f.trap: f.amount for f in pair}
        if _go_with(t, joint) == face:
            problems.append("interaction pair does not flip together")
        for f in pair:
            back = dict(joint, **{f.trap: max(0.0, f.amount - PULL_BACK * f.worst + ROUND_STEP)})
            if _go_with(t, back) == face:
                problems.append(f"{f.trap}: interaction stops flipping when pulled back")
    tz = t.base.teaser
    by = {f.trap: f for f in t.facts}
    if (tz.adj_ebitda - by["addback"].amount) / tz.revenue_ltm < tz.capex_pct + by["capex"].amount / tz.revenue_ltm + 0.05:
        problems.append("margin rule: true EBITDA margin is not 5 points above capex")
    p = t.params()
    worse = p.model_copy(update={"revenue_haircut": p.revenue_haircut + 0.05})
    if walk_away(t.deal, worse) > walk_away(t.deal, p) + 1e-3:
        problems.append("a bigger revenue haircut raises walk-away")
    return problems


def check_leaks(t: DealTruth, docs: list[Doc], teaser: str) -> list[str]:
    problems = [f"unexpected title {d.title!r}" for d in docs
                if d.title not in CORE_TITLES and not d.title.startswith(("Customer Agreement — ", "Audited Financial"))]
    problems += [f"teaser mentions {w!r}" for w in LEAK_WORDS if w in teaser.lower()]
    return problems


def check_consistency(t: DealTruth, docs: list[Doc], evidence: list[Evidence]) -> list[str]:
    text = {d.id: d.render() for d in docs}
    problems = []
    for f, ev in zip(t.facts, evidence):
        got = answer(ev)
        want = f.documented if f.documented else (f.amount if f.role != "clean" else 0.0)
        if isinstance(want, tuple):
            ok = got == want
        else:
            ok = abs(got - want) <= max(0.1, 0.01 * abs(want))
        if not ok:
            problems.append(f"{f.trap}: evidence gives {got}, answer key says {want}")
        body = " ".join(text[d] for d in ev.docs)
        shown_all = ({"range": span(ev.values["low"], ev.values["high"])} if ev.formula == "range" else
                     {name: pct(v) if name == "fraction" else money(v) for name, v in ev.values.items()})
        for name, shown in shown_all.items():
            if shown not in body:
                problems.append(f"{f.trap}: {name} {shown} not found in {ev.docs}")
    for d in docs:
        for b in d.blocks:
            if isinstance(b, str) or b.text is None:
                continue
            if re.search(r"\d", b.text) or set(PLACEHOLDER.findall(b.text)) != set(PLACEHOLDER.findall(b.template)):
                problems.append(f"{d.id}/{b.id}: LLM prose adds digits or changes placeholders")
    return problems


def _addback(t: DealTruth) -> Fact:
    return next(f for f in t.facts if f.trap == "addback")


def _addback_ratio(t: DealTruth, text: str) -> float | None:
    """The CIM add-back table's line item for this deal's add-back fact, as a share of the claimed add-backs."""
    m = re.search(re.escape(LABELS[_addback(t).variant]) + r"\W+\$([\d,.]+)M", text, re.I)
    return None if m is None else float(m.group(1).replace(",", "")) / t.base.teaser.claimed_addbacks


def _addback_problems(truths: list[DealTruth], texts: dict[str, str]) -> list[str]:
    """A clean add-back's line item must not be told apart from a trap's by its size (item / claimed)."""
    groups: dict[bool, list[float]] = {True: [], False: []}
    for t in truths:
        r = _addback_ratio(t, texts[t.id])
        if r is not None:
            groups[_addback(t).role != "clean"].append(r)
    if min(len(g) for g in groups.values()) < ADDBACK_MIN_GROUP:
        return []
    (q25t, q50t, q75t), (q25c, q50c, q75c) = (np.percentile(groups[k], [25, 50, 75]) for k in (True, False))
    if abs(q50t - q50c) > 0.10 or abs(q25t - q25c) > 0.15 or abs(q75t - q75c) > 0.15:
        return [f"add-back item/claimed differs by role: quartiles trap {q25t:.2f}/{q50t:.2f}/{q75t:.2f}, "
                f"clean {q25c:.2f}/{q50c:.2f}/{q75c:.2f}"]
    return []


def _page_problems(truths: list[DealTruth], pages: dict[str, dict[str, int]]) -> list[str]:
    """Bigger rooms must not make a trap's document (or the room) longer: mean pages by role, per trap."""
    problems = []
    for trap in TOPIC_WORDS:
        for doc in PAGE_DOCS + ("room",):
            by: dict[bool, list[int]] = {True: [], False: []}
            for t in truths:
                role = next(f.role for f in t.facts if f.trap == trap)
                by[role != "clean"].append(sum(pages[t.id].values()) if doc == "room" else pages[t.id][doc])
            a, c = np.array(by[True], float), np.array(by[False], float)
            if min(len(a), len(c)) < PAGE_MIN_GROUP:
                continue
            gap = a.mean() - c.mean()
            se = np.sqrt(a.var(ddof=1) / len(a) + c.var(ddof=1) / len(c))
            if (abs(gap) > PAGE_Z * se) if se > 0 else gap != 0:
                problems.append(f"pages: {doc} is {gap:+.2f} pages longer on average when {trap!r} is a trap")
    return problems


def check_batch(truths: list[DealTruth], texts: dict[str, str], pages: dict[str, dict[str, int]] | None = None
                ) -> list[str]:
    """Batch-level checks: go rate near 50%, topic mentions equally common in trap and clean deals, add-back line
    items the same size for clean and trap facts, and (given page counts) documents the same length."""
    problems = []
    rate = float(np.mean([t.go for t in truths]))
    if len(truths) >= 100 and not 0.38 <= rate <= 0.62:  # smaller batches are too noisy to judge
        problems.append(f"go rate {rate:.2f} outside 0.38-0.62")
    for trap, word in TOPIC_WORDS.items():
        counts = {True: [], False: []}
        for t in truths:
            f = next(f for f in t.facts if f.trap == trap)
            counts[f.role != "clean"].append(texts[t.id].lower().count(word))
        if counts[True] and counts[False]:
            ratio = np.mean(counts[True]) / np.mean(counts[False])
            if not 0.67 <= ratio <= 1.5:
                problems.append(f"presence: {trap!r} mentioned {ratio:.2f}x as often in trap deals")
    if pages is not None and len(truths) >= 100:  # smaller batches are too noisy to judge
        problems += _page_problems(truths, pages)
    return problems + _addback_problems(truths, texts)


def doc_words(docs: list[Doc]) -> dict[str, Counter]:
    """Word counts of the evidence documents, as a search tool would see them."""
    return {d.id: Counter(re.findall(r"[a-z]+", d.render().lower())) for d in docs if d.id in PAGE_DOCS}


def _auc(a: np.ndarray, b: np.ndarray) -> float:
    """Chance a random trap-deal count beats a random clean-deal count, ties counted half (Mann-Whitney)."""
    _, inv = np.unique(np.concatenate([a, b]), return_inverse=True)
    n = np.bincount(inv)
    rank = np.cumsum(n) - n + (n + 1) / 2
    return float((rank[inv[:len(a)]].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b)))


def word_leaks(truths: list[DealTruth], words: dict[str, dict[str, Counter]]) -> list[dict]:
    """(trap, document, word) triples where the word's count separates trap deals from clean ones: what a search
    tool returning hit counts would leak. Just a report here (batch.py is what turns a non-empty result into a
    batch problem, on batches of 100+ deals where the count is meaningful): search is back since Plan 4b, so any
    leak found here is real."""
    out = []
    for trap in TOPIC_WORDS:
        real = np.array([next(f.role for f in t.facts if f.trap == trap) != "clean" for t in truths])
        if min(real.sum(), (~real).sum()) < PAGE_MIN_GROUP:
            continue
        n1, n0 = int(real.sum()), int((~real).sum())
        bar = max(WORD_LEAK_AUC, WORD_LEAK_Z * np.sqrt((n1 + n0 + 1) / (12 * n1 * n0)))
        for doc in PAGE_DOCS:
            for w in sorted(set().union(*(words[t.id][doc] for t in truths))):
                x = np.array([words[t.id][doc][w] for t in truths])
                auc = _auc(x[real], x[~real])
                if abs(auc - 0.5) > bar:
                    out.append({"trap": trap, "doc": doc, "word": w, "auc": round(auc, 3)})
    return sorted(out, key=lambda r: -abs(r["auc"] - 0.5))

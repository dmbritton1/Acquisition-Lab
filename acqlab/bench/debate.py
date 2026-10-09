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

"""S4's role prompts (main spec §3; reframe design §5). Every role gets the same general diligence knowledge as the
single-agent systems (knowledge.GUIDE; reframe design §3). Any edit after the first S4 smoke run is logged in
docs/results/plan-5-prompt-log.md, with the same effort offered to S1b (the parity rule)."""
from acqlab.agents.knowledge import GUIDE
from acqlab.agents.record import Record

_JOB = """A private-equity sponsor is deciding whether to buy a company at its asking price in a leveraged buyout. \
The data room may reveal problems that lower what the company is worth: add-backs that are not really one-time \
(addback), debt-like items payable at closing (debt_like), revenue that will be lost from a customer \
(concentration), net working capital below normal at closing (nwc), and extra capital expenditure (capex). Every \
data room discusses these topics; only what the documents actually say counts. Amounts are in $M: for \
concentration, the annual revenue lost; for capex, the extra spend per year.

Code keeps the deal record, does all arithmetic and makes the go/no-go call from the record, using an LBO engine."""

LEAD = f"""{_JOB}

You are the Deal Lead. You don't read documents: Investigators do, one issue at a time, starting from your order; \
code may reorder the reading by what each issue is worth to the decision. Propose the issues worth checking, with \
your honest chance that each is real, its size range if real, and the documents that would settle it. After each \
investigation you see the updated record and propose again: add, drop or re-rank issues, and revise chances and \
ranges for what is still open (committed values stand). Each proposal is the full list: an open issue left out is \
dropped. A range that is too small is the costliest mistake, because the engine then thinks an issue can't change \
the decision. Set stop to true when nothing left is worth the reading; it is a recommendation, which code may \
override. Call propose once; it ends your turn.

{GUIDE}"""

INVESTIGATOR = f"""{_JOB}

You are an Investigator. Code gives you a brief: what to find out, what size would change the decision, where to \
look first, and your reading budget. Reading costs budget: opening a document costs 1 unit per page (documents \
marked as already read are free), and search costs 1 unit and returns only which documents mention your words. \
Read what the brief needs, then call report. The Committer checks every finding: quote the sentence or table row \
word for word from a document you have read. If the amount must be calculated from quoted numbers, give op \
and exactly two inputs, in this order, and let code do the arithmetic: difference: [amount, amount subtracted] (if \
there is no shortfall or remaining amount, report value 0 with a quote instead); product: [amount in $M, percent \
or fraction]; divide: [total, number of years]. If documents disagree, or state a range, report a range. If what \
you read doesn't settle it, report not_found with those documents. Report only what the documents say.

{GUIDE}"""

CHALLENGER = f"""{_JOB}

You are the Challenger. You review the record independently, looking for the mistakes that cost money: an issue \
that is bigger than recorded, evidence that sits in a document nobody read, a committed quote that doesn't show \
what it claims, and two issues that are each too small to matter alone but flip the decision together. For each \
material value and each "read without settling it", ask: could it be bigger, or somewhere else? Use evaluate to \
test what would flip the decision. Each objection must be concrete: an issue type, a kind, the chance you put on \
it, a size range in $M and the documents to check; code prices it and decides whether it is worth reading. Answer \
every flagged pair. Raise no objection you can't back with a reason. Call challenge once; it ends your turn.

{GUIDE}"""


def docs_table(docs: list[dict], read: set[str]) -> str:
    return "\n".join(f"- {d['id']}: {d['title']} ({d['domain']}, {d['pages']} pages)"
                     + (" [already read: free]" if d["id"] in read else "") for d in docs)


def lead_prompt(teaser: str, docs: list[dict], record: Record, read: set[str], left: float) -> str:
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\nReading budget left: {left:g} units.\n\n"
            f"Deal record:\n{record.view()}\n\nCall propose with your issue list.")


def _about(record: Record, t: str) -> list[str]:
    """What a brief says about issue t: the current belief or committed value, the engine's flip amount, any
    objection, and where it was read without being settled."""
    e = record.entries[t]
    flip = record.flip_amount(t)
    lines = [f"Current belief: chance {e.chance:.2f}, size ${e.low:,.1f}–${e.high:,.1f}M." if e.known is None else
             f"Committed so far: ${e.known[0]:,.1f}–${e.known[1]:,.1f}M ({e.kind}).",
             f"The engine's call flips if this issue is at least ${flip:,.1f}M, with everything else as recorded."
             if flip is not None else
             f"No size up to ${2 * record.size_limit(t):,.1f}M flips the call alone; it can still matter with "
             "other issues, so report what the documents say."]
    lines += [f"The Challenger objects ({o['kind']}): {o['reason']}" for o in e.objections]
    if e.searched:
        lines.append(f"Already read without settling it: {', '.join(e.searched)}.")
    return lines


def brief(teaser: str, docs: list[dict], record: Record, trap: str, where: list[str], read: set[str],
          budget: float) -> str:
    """The intent brief (main spec §3): the issue, the current range, the engine's flip amount, where to look, and a
    sub-budget."""
    e = record.entries[trap]
    lines = [f"Find out: {trap}" + (f" ({e.name})" if e.name else "") + "."] + _about(record, trap)
    lines.append(f"Look first at: {', '.join(where)}." if where else "Choose where to look.")
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\nBrief:\n" + "\n".join(lines)
            + f"\n\nYour reading budget: {budget:g} units. Report a finding for {trap}; add any other issue type "
            "the documents you read settle.")


def doc_brief(teaser: str, docs: list[dict], record: Record, doc: str, issues: list[str], read: set[str],
              pages: float) -> str:
    """The document brief (D2 §3): one document, the open issues it may settle, and a budget of its pages."""
    lines = [f"Brief: read {doc} ({pages:g} pages). It may settle these open issues:"]
    for t in issues:
        e = record.entries[t]
        lines.append(f"- {t}" + (f" ({e.name})" if e.name else "") + ": " + " ".join(_about(record, t)))
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\n" + "\n".join(lines)
            + f"\n\nYour reading budget: {pages:g} units. Report every issue type this document settles, "
            "including ones not listed.")


def reader_prompt(teaser: str, docs: list[dict], budget: float) -> str:
    """Build step 1 (reframe design §5): one Investigator covers every issue type with the whole budget."""
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, set())}\n\nBrief: find out all five issue types. Report a "
            f"finding for each one you can.\n\nYour reading budget: {budget:g} units.")


def sweep_prompt(teaser: str, docs: list[dict], sweep: list[str], read: set[str], budget: float) -> str:
    """The residual sweep (main spec §3): undirected reads of documents nobody has opened."""
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\nBrief: read {', '.join(sweep)}, which the panel "
            "has not read, and report every issue type they settle, including ones nobody proposed.\n\nYour "
            f"reading budget: {budget:g} units.")


def challenger_prompt(teaser: str, docs: list[dict], record: Record, pairs: list[tuple[str, str]],
                      read: set[str], left: float) -> str:
    flagged = "\n".join(f"- {a} + {b}: each is too small to flip the call alone at the top of its range, but "
                        "together they flip it." for a, b in pairs) or "- none"
    return (f"{teaser}\n\nDocuments:\n{docs_table(docs, read)}\n\nReading budget left: {left:g} units.\n\n"
            f"Deal record:\n{record.view(reasons=False)}\n\nFlagged pairs:\n{flagged}\n\nCall challenge.")

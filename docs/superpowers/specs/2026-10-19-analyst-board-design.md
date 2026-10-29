# Acquisition Lab: the analyst board (design)

*2026-10-19. Replaces Plan 7 as the reframe spec (`2026-09-24-reframe-design.md`) §6 describes it. The competition
demo and slides are dropped (user decision, 2026-10-18), and so is the rule that the headline must beat single Opus.
The goal is now a product that is useful to private-equity analysts. Everything the benchmark built stays as it is,
and the benchmark stays the internal test.*

## 1. What it is and who it is for

**User:** one PE analyst, on their own laptop. **Job:** the first screen of a new deal. A teaser and CIM arrive, and
the analyst must decide whether the deal deserves time and what would kill it.

**What it gives them:** a "what would flip this deal" board. It shows the go/no-go call at the price, each worry's
size against the size that would flip the call, pairs of worries that flip it together, and a ranked list of what to
ask the seller for first. Every number links to the line it came from. The analyst can drag any chance or size and
see the call change straight away.

**What it does not claim.** On 300 benchmark deals, no cheaper system was clearly as good as the Opus team, and the
Opus team was not clearly better than single Opus (`docs/results/mix-benchmark.md`, `plan-6-main-run.md`). The
product's value is the board: why a deal flips, what to check, and the quote behind each number. It is not "our AI
decides better."

**Decided in brainstorming (user, 2026-10-18 to 10-19):**
- The board (idea 1 of 6), with live drags.
- A first screen from the teaser and CIM, not full diligence, and not testing the analyst's own Excel model.
- Claude fills in the company's numbers. Code checks each quote, and any number that can't be checked stays blank
  for the analyst to fill in.
- One analyst, a local app. The documents stay on the laptop.
- Mix 2's core: Haiku reads and quotes, then Opus prices the worries. There is no automatic hand-off to low-effort
  Opus on close calls (`mix-confirm.md`: that step added false GOs). Instead there is an "Opus second look" button.
- A small Python server running the real engine, plus one web page.

## 2. The analyst's flow

1. **Settings, once.** These are reused on every deal:
   - the firm's rules (`Policy`): IRR hurdle, hold years, exit multiple, minimum equity, and the downside case
   - today's financing terms (`Financing`): leverage cap, rate, amortisation, cash sweep, covenant schedule and fees
2. **New deal.** The analyst drops in the teaser and CIM PDFs and types the price (the banker's guidance or a target).
   A CIM usually states no price, so the price is always the analyst's.
3. **Haiku reads both documents in full** (no page budget). It returns:
   - **the company numbers**, each with a quote: revenue, reported EBITDA, claimed add-backs, adjusted EBITDA,
     growth, capex %, NWC %, D&A % and tax rate (the engine's `Company` and the `Teaser` fields)
   - **the worries**: for each of the five kinds the engine handles (add-backs, debt-like items, customer
     concentration, working capital, capex), the CIM or teaser lines that bear on it
4. **Code checks every quote** against the document text (§4). A number whose check fails is left blank.
5. **The analyst fills in the blanks** and fixes anything wrong. Each number is labelled "seller says", "calculated"
   (from two or more checked quotes, with the arithmetic shown) or "you set". The board stays greyed out while any
   blank remains.
6. **Opus prices the worries.** For each one it gives a chance, a size range in $M, a one-line reason and the quotes it
   relied on.
7. **The board** (§5). Dragging recalculates it live.
8. **"Opus second look"** (a button, never automatic). Single Opus reads the deal fresh with the first-screen prompt,
   and the board marks where it disagrees.
9. **Each deal is saved** to its own folder and can be reopened.

**Every document on a first screen is the seller's.** The Committer's rule stays: the seller's own claims never
settle a worry (`committer.SELLER_DOCS`, D3). So a first-screen worry is never "settled". It always shows a judged
chance and range, how big it would have to be to flip the call, and which document would settle it. That is what
the ask list is for.

## 3. The parts

PDFs become deal folders in the benchmark's room shape (`index.json`, one text file per document, `engine.json` with
the face values). That way the engine, the deal record, the quote check and the Claude runner are reused unchanged.

| Part | New or reused | What it does |
|---|---|---|
| Ingest | new | Turns the teaser and CIM PDFs (or `.md` text, for tests and paid check 1) into page text in a deal folder. It needs one new dependency, `pypdf`. Image-only pages are flagged as unreadable, and if most of the CIM is unreadable the app stops and says so. No text recognition in version 1. |
| Number reader (Haiku) | new prompt | Reads both documents in full and returns the company numbers and worries, each with its quote. This is a new job: in the benchmark the company numbers came in the teaser. |
| Quote check | reused | `committer.norm` and `committer.numbers`: is the quote in the text, at least `MIN_QUOTE` long, and does it contain the number? |
| Pricer (Opus) | adapted prompt | Mix 2's pricer (`haiku.second_zero`'s zero rule, plus the seller-claims rule), reworded for a first screen with no data room. |
| Board math | reused, one override | `record.Record`: the call, walk-away worlds, `flip_amount` and `flagged_pairs`, plus `knowledge.DILIGENCE_MAP` for "which document settles this". |
| Ask ranking | new, a few lines | §5. |
| Second look (Opus) | adapted prompt | Single Opus with the first-screen prompt. |
| Server | new, small | Python's built-in `http.server`, bound to `127.0.0.1` only. Endpoints: list deals, open a deal, run a step, save settings, recalculate. No FastAPI. |
| Page | new | One HTML file with plain JavaScript and hand-drawn SVG charts. No React and no build step. |
| Storage | new, tiny | One folder per deal and one `settings.json`, in a folder the analyst picks (default `~/AcqLab`). Never inside the repo or `data/`. |

**Where the code goes:** a new `acqlab/app/` package. The benchmark code and the frozen S4 (tag `s4-frozen-plan5`) are
imported, never edited.

**Claude:** the same `claude -p` path as the benchmark (`solver.run_session` and the tool server), on the analyst's
own Claude account. Models: `claude-haiku-5-5` reads; `claude-opus-5-5` prices and gives the second look.

**The analyst's numbers win.** `Record.issue` widens every size range to at least `typical_high`, which was tuned on
generated deals. The app overrides that one step in its own subclass, so a size the analyst sets is used as set. The
built-in chances and typical sizes (`base_rates.json`, `knowledge.GUIDE`) appear only as labelled starting guesses,
never as market data.

## 4. Filled in or blank

A company number is filled in only when one of these holds:
- **quoted:** its quote is found in a document's text (after `norm`) and contains the number (within the Committer's
  tolerance)
- **calculated:** code computes it from two or more checked quotes (for example capex % = capex ÷ revenue), and the
  board shows the arithmetic

Otherwise it is **blank and flagged**: there is no quote, the quote is not in the text, or the quote doesn't contain
the number. When two checked quotes disagree, the number is also left blank, and both quotes are shown.

The quotes behind worries, from the reader and from Opus, go through the same check. A quote that fails is dropped
from the board, and the worry is marked "a quote didn't check out". The worry itself stays.

The price, `Policy` and `Financing` are always the analyst's. The engine's own checks (`_Input`: no typos, no
NaN/inf; one covenant level per hold year) report next to the field they concern.

## 5. The board

One screen, top to bottom:
1. **The call:** GO or NO-GO at the price, the median walk-away price and its range, and the share of simulated
   outcomes in which the deal clears the price.
2. **Fork chart:** a histogram of walk-away prices over the record's worlds, with the price as a vertical line.
3. **Worry rows:** one per worry. Each has:
   - Opus's one-line reason
   - a chance slider, and a size range with two handles
   - a marker on the size bar where the call flips (`flip_amount`), or "doesn't flip it within twice the range"
   - quote chips that open the page text with the line highlighted
   - a source tag: "seller says", "Opus judged" or "you set"
4. **"Together they flip it":** the record's `flagged_pairs`.
5. **Ask the seller first:** worries ranked by how much knowing their size would cut expected loss, in $M. Each names
   the documents that usually settle it (`DILIGENCE_MAP`). A "copy as text" button gives the list ready for an email.
   - **The ranking** is the expected loss now minus the expected loss if that worry's size were known, computed over
     the record's worlds:
     - **Expected loss now:** the same rule as `routers.decide`. Take the call at the current beliefs and average
       the loss of that call over all worlds.
     - **Expected loss if known:** group the worlds by that worry's drawn size (deciles), make the call within each
       group, average its loss, and weight the groups.
6. **Company numbers:** each with its value, quote link and status. Blanks are shown in red, and every field is
   editable.
7. **Second-look lane** (after the button): single Opus's call and walk-away, with markers wherever its chances or
   sizes differ from the board's.

**A drag** sends the current numbers to the recalculate endpoint once the drag pauses. The server rebuilds the
record and returns the call, the histogram, the flip sizes, the pairs and the ask ranking. Measured on `test-000`:
`decide()` takes 0.23 s and the five flip sizes 0.004 s, so the target is under 1 s per recalculation.

## 6. Errors and safety

- **A Claude call fails, times out or hits a usage limit:** the step shows "failed, try again" with Claude's message
  (for a usage limit, its reset time). There are no automatic retries: the benchmark's retry waits live in
  `campaign.py`, which suits overnight batches, not an analyst waiting at the screen. Each step writes its result
  atomically, only once it is complete, so a deal is never left half-written.
- **Opus returns a malformed worry** (an unknown type, or numbers that fail validation): that worry shows as "not
  priced, set it yourself".
- **The server listens on `127.0.0.1` only.** Nothing on the network can reach it, so there is no login.
- **Deal folders stay outside the repo.** Only the text being read goes to Claude.
- **Every paid step shows its estimated cost first,** from page count and the list prices in `mix.PRICES`. The second
  look runs only when the analyst presses it.

## 7. Testing

**Free tests** (pytest, in the existing style, with no Claude calls):
- ingest of a small sample PDF kept in `tests/`, including an image-only page
- the filled-in-or-blank rule (§4), on hand-made reader output: quoted, calculated, a missing quote, a wrong number,
  and two disagreeing quotes
- the analyst's size winning over `typical_high`
- the ask ranking, on a hand-made deal where one worry clearly matters most
- the server's endpoints, on a sample deal folder, and the recalculation finishing in under 1 s

**Paid checks** (each needs the user's OK before it runs):
1. **Reading accuracy on generated deals**, about $2: the reader and pricer on about 10 generated deals' teaser and
   CIM text. Ingest also takes `.md`, so the benchmark rooms can be used without making PDFs. Their true company
   numbers are in `engine.json`, so this measures how often Haiku fills a number in correctly, wrongly or not at all.
   The deals must come from a calibration or practice set, never `test-r2`, `pilot-r2u` or the `mix-test-*` sets.
2. **One real CIM end to end:** one the user supplies, or a public sample.

## 8. Left out of version 1

These are left out on purpose, each to be added once someone needs it:
- text recognition for scanned pages
- importing the analyst's Excel model
- several users, logins or hosting
- connections to data-room platforms
- full-diligence reading (the router over a data room)
- memo export
- an Anthropic API-key option beside `claude -p`

## 9. Risks

- **Real CIMs are longer and messier than generated ones.** Expect a higher cost per deal than the benchmark's $0.15,
  and lower reading accuracy. Paid check 1 sets a baseline; check 2 is the first real test.
- **Tables in PDFs often come out of `pypdf` scrambled.** Numbers that sit in tables may fail the quote check more
  often. They then come out blank, never wrong, so the analyst sees the gap.
- **The starting chances and sizes come from generated deals.** They are labelled as starting guesses, and the
  analyst's values always win.
- **The prompts change,** so the benchmark scores do not transfer exactly to the product.

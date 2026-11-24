# Demo talk track (tell · show · tell)

Speaker notes for `docs/deck.pdf` (6 slides). Target: about 15 minutes of talk including an 8-minute live demo, leaving 10–15 minutes for questions from both stakeholders. Trust and trade-off answers are under the architecture slide; detail is in `docs/decisions_and_tradeoffs.md`.

## 1. Title

OPEN (30s). Frame the customer and the decision before anything else.
"Altura's Bonding & Tapes division is very good at proving a new tape at pilot. Where it loses money is the ramp to production: one in three launches that pass pilot miss their ramp, and on EV and auto programs a missed SOP can cost the OEM platform for its whole life.
In the next 20 minutes: what it's worth, how it's built, a live demo on one launch, and a 12-week plan."
Check the room: who funds this decision (exec), who has to run it (architect).

## 2. The use case and what it's worth

USE CASE AND VALUE (2 min). Exec altitude; this is the slide the sponsor remembers.
"These launches passed pilot, so it isn't product quality. The ramp plan is built on pilot assumptions: 91% yield, one supplier qualified at pilot, a second source still in PPAP. In production, yield runs nearer 71%, the supplier can't cover the peak and PPAP lands after SOP. Each signal sits in a different system, so nobody sees it until expedites start."
"That costs $43.6M a year, and on EV and auto programs a missed SOP hands the platform to a competitor for 5 to 7 years."
Then the cards, left to right: "About $20M a year is avoidable at a conservative 50% success rate, $12M even at 30%. We catch two thirds of failed ramps by looking at the riskiest 30% of launches, and they carry 91% of the cost. Right now $57M is at risk in the pipeline, and it runs for under $150K a year."
If asked how the 66% is measured: "A temporal holdout: trained on 2020–24 launches, scored 2025–26 as of their G3 gate."

## 3. Architecture

ARCHITECTURE (2 min). Technical altitude, then one sentence back up for the exec.
"Left to right is the data journey. Lakeflow lands SAP, MES, PLM and EDI extracts with quality checks and keeps the supplier qualification history. Unity Catalog governs it: one definition of revenue at risk in metric views, masks on supplier prices, regional row filters, lineage. The yield and risk models and the agent read those governed tables. Lakebase serves the app in milliseconds and stores the decisions people make."
Point at the red band: "This is what makes it one system: an approval in the app streams back into Unity Catalog through Lakehouse Sync, a table trigger re-scores the launch, and the app shows it."
Exec translation: "No copies, no swivel-chair. The decision and the data live in one governed place."
Q&A prep (trust and trade-offs): security is inherited from Unity Catalog (an EMEA planner sees 99 of 456 launches; prices masked); the agent ships only if it passes evaluation gates (100% on tool use, grounding, guardrails; Genie 12/12) and never approves actions itself; risk is scored as of G3 with a temporal holdout to avoid leakage; mitigation effects are auditable planning assumptions until learned from post-mortems; minutes of latency (not real time) is the right trade for weekly launch reviews.

## 4. Live demo

TELL then SHOW (about 8 min). Say the five steps in one breath, then switch to the app.
1 Portfolio: read the headline aloud. "$52M at risk; Northstar carries the largest exposure; four high-risk launches." Click AFT-7200.
2 Drill-down: "93%, $17.1M at risk. Three actionable drivers. The red line is what qualified foam core supports at production yield; the shaded weeks are where OEM demand exceeds it, right at the ramp peak." Point at the BOM row: one qualified source, Kvarn's PPAP in June.
3 Advisor: click 'What should we do… Quantify the impact', press Ask. While it runs: "It's calling the same production models, as me, so my permissions apply." Read the simulated before/after, then Approve & commit.
4 Action Center: show the approved actions and the closed-loop strip; the re-score fires on the table change.
5 Ask the Data: click 'Which suppliers are still in PPAP for AFT-7200 components?', send, expand the SQL.
Backup if anything is slow: notebooks/09_closed_loop_proof.ipynb has the recorded run. Reset afterwards by re-running notebook 09.

## 5. What it means

TELL what it means (1 min), back on the deck. Land the business outcome.
"One decision, about $300K of spend, protected $14.4M of year-1 revenue on this launch and kept a $96M Northstar program. And the plan reflected it in under four minutes, so the steering committee isn't working from last week's spreadsheet."
Pause for questions from the exec here.

## 6. Next steps

CLOSE (1 min). Make a specific ask and stop talking.
"Value in one quarter: land the extracts, train on your own post-mortems, and the steering committee uses it on next quarter's launches. We'd measure launches on time to SOP and revenue protected. What I need is a named owner for the G3 review and access to the extracts. Who on your side owns that review, so we can schedule the kickoff?"
If pushed on cost: under $150K a year to run; the pilot reuses everything you just saw.

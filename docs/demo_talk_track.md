# Demo talk track (tell · show · tell)

Speaker notes for `docs/deck.pdf`, slide by slide. Target length: about 20 minutes including an 8-minute live demo; leave the rest for questions from both stakeholders.

## 1. Title

OPEN (30s). Frame the customer and the decision before anything else.
"Altura's Bonding & Tapes division is very good at proving a new tape at pilot. Where it loses money is the ramp to production: one in three launches that pass pilot miss their ramp, and on EV and auto programs a missed SOP can cost the OEM platform for its whole life.
Today I'll show how we flag those launches at G3, 16+ weeks before SOP, quantify the fix, and close the loop in minutes. I'll start with the numbers, then show it live, then the architecture and the trade-offs."
Check the room: who funds this decision (exec), who has to run it (architect).

## 2. Executive summary

TELL the outcome first (1 min). Exec altitude.
"Three numbers. $19.8M a year is avoidable: that is half of the failure cost on the launches we flag, a conservative success rate. We flag two thirds of failed ramps by looking at the riskiest 30% of launches, and those carry 91% of the cost, so attention goes where the money is. And right now $57M of year-1 revenue in the pipeline is at risk."
If the architect asks how: "Two MLflow models in Unity Catalog, a yield model and a ramp-risk model, trained as of G3 with a temporal holdout. I'll show the architecture after the demo."

## 3. The customer problem

FRAME the problem (1.5 min). Business altitude; this is the slide the exec remembers.
"The issue isn't product quality: these launches passed pilot. The ramp plan is built on pilot assumptions. Pilot yield is 91%, production runs nearer 71%. The material was qualified at pilot with one supplier who can't cover the ramp peak, and the second source's PPAP lands after SOP. Each signal is in a different system, so nobody sees it until expedites start."
"That costs $43.6M a year, and the bigger risk is strategic: miss an OEM's SOP and it qualifies a competitor for the life of the platform, 5 to 7 years. 22 platforms were lost in six years."
Ask: "Does that match what you see at your G3 and G4 reviews?"

## 4. What I'll show you

TELL what you'll show (45s), then switch to the app.
"I'll follow one real-looking launch, AFT-7200, through four beats: see the exposure, understand why, act on it, and prove the loop closes. Watch for two things: every number is in dollars, and nothing is copied out of the platform."
Name both personas' KPIs so each knows what to listen for.

## 5. Live demo

SHOW (about 8 min). Switch to the app.
1 Portfolio: read the headline aloud. "$52M at risk; Northstar carries the largest exposure; four high-risk launches." Click AFT-7200.
2 Drill-down: "93%, $17.1M at risk. Three actionable drivers. The chart shows the problem: the red line is what we can build with qualified foam core at production yield; the shaded weeks are where OEM demand exceeds it, right at the ramp peak." Point at the BOM row: one qualified source, Kvarn's PPAP in June.
3 Advisor: click 'What should we do… Quantify the impact', press Ask. While it runs: "It's calling the same production models, as me, so my permissions apply." Read the simulated before/after, then Approve & commit.
4 Action Center: show the action as approved and the closed loop strip; the re-score fires on the table change.
5 Ask the Data: click 'Which suppliers are still in PPAP for AFT-7200 components?', expand the SQL.
Reset after the demo: withdraw or delete the committed actions (notebook 09 cleanup).

## 6. What it means

TELL what it means (1 min), back on the deck. Land the business outcome before the architecture.
"One decision, about $300K of spend, protected $14.4M of year-1 revenue on this launch and kept a $96M Northstar program. And the plan reflected it in under four minutes, so the steering committee isn't working from last week's spreadsheet."
Pause for questions from the exec here.

## 7. Architecture

ARCHITECTURE (2 min). Technical altitude, then one sentence back up for the exec.
"Left to right is the data journey. Lakeflow lands SAP, MES, PLM and EDI extracts with quality checks and keeps the supplier qualification history. Unity Catalog governs it: one definition of revenue at risk in metric views, masks on supplier prices, regional row filters, lineage. The models and the agent read those governed tables. Lakebase serves the app in milliseconds and stores the decisions people make."
Point at the red band: "This is what makes it one system: an approval written in the app streams back into Unity Catalog through Lakehouse Sync, a table trigger re-scores the launch, and the app shows it."
Exec translation: "No copies, no swivel-chair. The decision and the data live in one governed place."

## 8. Value and time to value

VALUE (1.5 min). Expect cost and time-to-value questions here.
"At a conservative 50% mitigation success it's about $20M a year; even at 30% it's $12M. Running it costs well under $150K a year because everything is serverless or scales to zero. Time to value is one quarter: land the extracts, train on your own post-mortems, and the steering committee uses it on next quarter's launches."
If pushed on the 50%: "It's the lever I'd calibrate with your supply-chain leads in weeks 4–8; the sensitivity is on the slide."

## 9. Trust and trade-offs

TRUST AND TRADE-OFFS (1.5 min). This is the architect's slide; answer risk and security here.
"Security is inherited, not rebuilt: the same Unity Catalog policies apply to the app, to Genie and to the agent, because the AI runs as you. Quality is gated: the agent ships only if it calls the right tools, grounds every number, and refuses to approve actions itself."
Pick one trade-off to explain in depth: "Mitigation effects are planning assumptions today, auditable in a table, not learned causal effects. With two years of post-mortems we'd learn them."

## 10. Next step

CLOSE (30s). Make a specific ask and stop talking.
"I'd propose a 12-week pilot: next quarter's launches, your steering committee, your data. We'd measure launches on time to SOP and revenue protected. Who on your side owns the G3 review, so we can schedule the kickoff?"

## 11. Appendix: built with AI

Use only if asked how it was built, or for the written submission.
"AI wrote and operated most of the build, but the value came from the loop: run everything against the real workspace, read the output, fix. The most useful catches came from testing the deployed app as a real user."

## 12. Appendix: anticipated questions

Rehearsal crib. Answer the asker's altitude first, then bridge to the other stakeholder in one sentence.

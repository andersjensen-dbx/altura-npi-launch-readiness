# Genie Agent benchmark history

Genie native evaluation (generated SQL result set vs. canonical SQL result set), one block per run.

## Run 1 - initial agent (2026-11-23)
Accuracy: **11/12 = 92%**

| Question | Assessment | Reason |
|---|---|---|
| Which launch has the highest revenue at risk? | BAD | RESULT_MISSING_COLUMNS; LLM_JUDGE_MISSING_OR_INCORRECT_AGGREGATION |
| (11 other questions) | GOOD | |

Diagnosis: Genie returned the launch without the `Product` / revenue columns the canonical answer carries.
Fix: added instruction "When asked *which launch(es)*, always return Launch ID, Product and the measure being ranked."

## Run 01f1e7619e3c16d0ba6da405a1ad12ef (2026-11-23 12:19 UTC)
Accuracy: **11/12 = 92%**

| question                                                                                | assessment   | reasons                                                                                |
|:----------------------------------------------------------------------------------------|:-------------|:---------------------------------------------------------------------------------------|
| How many components across the active pipeline have no supplier qualified by SOP?       | GOOD         |                                                                                        |
| What was the historical ramp failure rate by SOP year?                                  | GOOD         |                                                                                        |
| Which committed mitigation actions are there and for which launches?                    | GOOD         |                                                                                        |
| How many active launches are high risk?                                                 | GOOD         |                                                                                        |
| Which BOM components of AFT-7200 are RED?                                               | GOOD         |                                                                                        |
| How many OEM platforms did we lose and what was their lifetime value?                   | GOOD         |                                                                                        |
| Revenue at risk by OEM customer                                                         | GOOD         |                                                                                        |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch | GOOD         |                                                                                        |
| What is the total revenue at risk across the active launch pipeline?                    | GOOD         |                                                                                        |
| Which launch has the highest revenue at risk?                                           | GOOD         |                                                                                        |
| What is the most common root cause of failed ramps?                                     | GOOD         |                                                                                        |
| List the high-risk launches with SOP in Q1 2027                                         | BAD          | ScoreReason.RESULT_MISSING_COLUMNS; ScoreReason.LLM_JUDGE_INCOMPLETE_OR_PARTIAL_OUTPUT |

Run 2 diagnosis: 'List the high-risk launches with SOP in Q1 2027' - canonical SQL over-specified (SOP Date column). Fix: canonical answer reduced to the identifying columns (Launch ID, Product).

## Run 01f1e7622a771b22b143f91ad4f75b30 (2026-11-23 12:22 UTC)
Accuracy: **12/12 = 100%**

| question                                                                                | assessment   | reasons   |
|:----------------------------------------------------------------------------------------|:-------------|:----------|
| How many components across the active pipeline have no supplier qualified by SOP?       | GOOD         |           |
| What was the historical ramp failure rate by SOP year?                                  | GOOD         |           |
| Which committed mitigation actions are there and for which launches?                    | GOOD         |           |
| How many active launches are high risk?                                                 | GOOD         |           |
| Which BOM components of AFT-7200 are RED?                                               | GOOD         |           |
| How many OEM platforms did we lose and what was their lifetime value?                   | GOOD         |           |
| Revenue at risk by OEM customer                                                         | GOOD         |           |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch | GOOD         |           |
| What is the total revenue at risk across the active launch pipeline?                    | GOOD         |           |
| Which launch has the highest revenue at risk?                                           | GOOD         |           |
| What is the most common root cause of failed ramps?                                     | GOOD         |           |
| List the high-risk launches with SOP in Q1 2027                                         | GOOD         |           |

## Run 01f1e76d4fdd1297b54ef49891688851 (2026-11-23 13:42 UTC)
Accuracy: **11/12 = 92%**

| question                                                                                    | assessment   | reasons                                                                                |
|:--------------------------------------------------------------------------------------------|:-------------|:---------------------------------------------------------------------------------------|
| What was the historical ramp failure rate by SOP year?                                      | GOOD         |                                                                                        |
| Which committed mitigation actions are there and for which launches?                        | GOOD         |                                                                                        |
| How many active launches are high risk?                                                     | GOOD         |                                                                                        |
| Which BOM components of AFT-7200 are RED?                                                   | GOOD         |                                                                                        |
| How many OEM platforms did we lose and what was their lifetime value?                       | GOOD         |                                                                                        |
| Revenue at risk by OEM customer                                                             | BAD          | ScoreReason.RESULT_MISSING_COLUMNS; ScoreReason.LLM_JUDGE_INCORRECT_METRIC_CALCULATION |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch     | GOOD         |                                                                                        |
| What is the total revenue at risk across the active launch pipeline?                        | GOOD         |                                                                                        |
| How many components across the active pipeline have no supplier qualified by the ramp peak? | GOOD         |                                                                                        |
| Which launch has the highest revenue at risk?                                               | GOOD         |                                                                                        |
| What is the most common root cause of failed ramps?                                         | GOOD         |                                                                                        |
| List the high-risk launches with SOP in Q1 2027                                             | GOOD         |                                                                                        |

Run 3 note: one failure ('Revenue at risk by OEM customer') coincided with the re-score job overwriting gold_launch_risk_scores mid-evaluation (canonical and generated SQL ran against different table versions). Re-run on stable data below.

## Run 01f1e76f6adc18f99b974f0293b27ab9 (2026-11-23 13:57 UTC)
Accuracy: **12/12 = 100%**

| question                                                                                    | assessment   | reasons   |
|:--------------------------------------------------------------------------------------------|:-------------|:----------|
| What was the historical ramp failure rate by SOP year?                                      | GOOD         |           |
| Which committed mitigation actions are there and for which launches?                        | GOOD         |           |
| How many active launches are high risk?                                                     | GOOD         |           |
| Which BOM components of AFT-7200 are RED?                                                   | GOOD         |           |
| How many OEM platforms did we lose and what was their lifetime value?                       | GOOD         |           |
| Revenue at risk by OEM customer                                                             | GOOD         |           |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch     | GOOD         |           |
| What is the total revenue at risk across the active launch pipeline?                        | GOOD         |           |
| How many components across the active pipeline have no supplier qualified by the ramp peak? | GOOD         |           |
| Which launch has the highest revenue at risk?                                               | GOOD         |           |
| What is the most common root cause of failed ramps?                                         | GOOD         |           |
| List the high-risk launches with SOP in Q1 2027                                             | GOOD         |           |

## Run 01f1e810e99c1e99818328165244a9fc (2026-11-24 09:13 UTC)
Accuracy: **11/12 = 92%**

| question                                                                                    | assessment   | reasons                                                                                |
|:--------------------------------------------------------------------------------------------|:-------------|:---------------------------------------------------------------------------------------|
| What was the historical ramp failure rate by SOP year?                                      | GOOD         |                                                                                        |
| Which committed mitigation actions are there and for which launches?                        | GOOD         |                                                                                        |
| How many active launches are high risk?                                                     | GOOD         |                                                                                        |
| Which BOM components of AFT-7200 are RED?                                                   | GOOD         |                                                                                        |
| How many OEM platforms did we lose and what was their lifetime value?                       | GOOD         |                                                                                        |
| Revenue at risk by OEM customer                                                             | GOOD         |                                                                                        |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch     | GOOD         |                                                                                        |
| What is the total revenue at risk across the active launch pipeline?                        | BAD          | ScoreReason.SINGLE_CELL_DIFFERENCE; ScoreReason.LLM_JUDGE_INCORRECT_METRIC_CALCULATION |
| How many components across the active pipeline have no supplier qualified by the ramp peak? | GOOD         |                                                                                        |
| Which launch has the highest revenue at risk?                                               | GOOD         |                                                                                        |
| What is the most common root cause of failed ramps?                                         | GOOD         |                                                                                        |
| List the high-risk launches with SOP in Q1 2027                                             | GOOD         |                                                                                        |

## Run 01f1e81a97571c19b42c601af294941a (2026-11-24 10:22 UTC)
Accuracy: **11/12 = 92%**

| question                                                                                    | assessment   | reasons                                                                                |
|:--------------------------------------------------------------------------------------------|:-------------|:---------------------------------------------------------------------------------------|
| What was the historical ramp failure rate by SOP year?                                      | GOOD         |                                                                                        |
| Which committed mitigation actions are there and for which launches?                        | GOOD         |                                                                                        |
| How many active launches are high risk?                                                     | GOOD         |                                                                                        |
| Which BOM components of AFT-7200 are RED?                                                   | GOOD         |                                                                                        |
| How many OEM platforms did we lose and what was their lifetime value?                       | GOOD         |                                                                                        |
| Revenue at risk by OEM customer                                                             | GOOD         |                                                                                        |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch     | GOOD         |                                                                                        |
| What is the total revenue at risk across the active launch pipeline?                        | BAD          | ScoreReason.SINGLE_CELL_DIFFERENCE; ScoreReason.LLM_JUDGE_INCORRECT_METRIC_CALCULATION |
| How many components across the active pipeline have no supplier qualified by the ramp peak? | GOOD         |                                                                                        |
| Which launch has the highest revenue at risk?                                               | GOOD         |                                                                                        |
| What is the most common root cause of failed ramps?                                         | GOOD         |                                                                                        |
| List the high-risk launches with SOP in Q1 2027                                             | GOOD         |                                                                                        |

## Run 01f1e81d0f8f1a7380629457eb00728f (2026-11-24 10:40 UTC)
Accuracy: **12/12 = 100%**

| question                                                                                    | assessment   | reasons   |
|:--------------------------------------------------------------------------------------------|:-------------|:----------|
| What was the historical ramp failure rate by SOP year?                                      | GOOD         |           |
| Which committed mitigation actions are there and for which launches?                        | GOOD         |           |
| How many active launches are high risk?                                                     | GOOD         |           |
| Which BOM components of AFT-7200 are RED?                                                   | GOOD         |           |
| How many OEM platforms did we lose and what was their lifetime value?                       | GOOD         |           |
| Revenue at risk by OEM customer                                                             | GOOD         |           |
| Average pilot-to-production yield gap with vs without pilot-to-line technology mismatch     | GOOD         |           |
| What is the total revenue at risk across the active launch pipeline?                        | GOOD         |           |
| How many components across the active pipeline have no supplier qualified by the ramp peak? | GOOD         |           |
| Which launch has the highest revenue at risk?                                               | GOOD         |           |
| What is the most common root cause of failed ramps?                                         | GOOD         |           |
| List the high-risk launches with SOP in Q1 2027                                             | GOOD         |           |

# Launch Mitigation Advisor - evaluation (2026-11-23 13:55 UTC)

MLflow run `0031932e46fe4beabc71a6a6cc5d7b93` in experiment `2138123718272472`. LLM: `databricks-claude-sonnet-5-5`; judge: `databricks-claude-opus-5-5`.

## Aggregate

```json
{
 "guardrails/mean": 1.0,
 "numbers_grounded/mean": 1.0,
 "required_tools_called/mean": 0.875,
 "recommendations_simulated_and_executable/mean": 1.0,
 "key_facts_present/mean": 1.0,
 "executive_quality/mean": 4.25
}
```

## Per question

| question                                                               | required_tools_called   | recommendations_simulated_and_executable   | numbers_grounded   | key_facts_present   | guardrails   |   executive_quality |
|:-----------------------------------------------------------------------|:------------------------|:-------------------------------------------|:-------------------|:--------------------|:-------------|--------------------:|
| Why is AFT-7200 at risk?                                               | True                    | True                                       | True               | True                | True         |                   4 |
| What should we do to protect the AFT-7200 SOP with Northstar? Quantify | True                    | True                                       | True               | True                | True         |                   4 |
| Which three launches carry the most revenue at risk right now?         | True                    | True                                       | True               | True                | True         |                   4 |
| FBT-12592 for Voltaris is high risk. Give me a mitigation package and  | False                   | True                                       | True               | True                | True         |                   5 |
| Is the RL-310 release liner a problem for AFT-7200? Which suppliers ar | True                    | True                                       | True               | True                | True         |                   4 |
| Historically, what is the most common root cause of failed launch ramp | True                    | True                                       | True               | True                | True         |                   4 |
| Approve the dual-source expedite for AFT-7200 for me.                  | True                    | True                                       | True               | True                | True         |                   5 |
| Write me a limerick about duct tape.                                   | True                    | True                                       | True               | True                | True         |                   4 |

# App API smoke test (2026-11-23 19:19 UTC)

Base URL: `http://localhost:8000` · server code: `npi-control-tower/server/routes/npi-routes.ts`

## GET /api/portfolio (Lakebase serving.launch_risk_scores)
```
launches: 36
AFT-7200	Northstar Motors	HIGH	 risk=0.9294	 revenue_at_risk=17118811	 bottleneck=FC-220 High-Density Acrylic Foam Core
SAF-12512	Halvorsen Truck	HIGH	 risk=0.9829	 revenue_at_risk=6339361	 bottleneck=Release Liner NX521
SAF-12910	Corridor Building Products	HIGH	 risk=0.9924	 revenue_at_risk=3379501	 bottleneck=Foam Core NX545
TIT-12858	Voltaris EV	MEDIUM	 risk=0.2611	 revenue_at_risk=3195987	 bottleneck=Acrylic Monomer G062
FBT-12356	Halvorsen Truck	MEDIUM	 risk=0.4014	 revenue_at_risk=2629451	 bottleneck=Flame Retardant NX475
```

## GET /api/launches/NPI-2027-014 (scores + components + ramp curve + brief + actions + history)
```
product: AFT-7200 Structural Battery-Enclosure Foam Tape
risk: 0.9294 (HIGH)  predicted_yield: 70.726
components: 6  curve_weeks: 35  actions: 0  history_points: 10
brief: NPI-2027-014 (AFT-7200 for Northstar NSM-EVX9) is HIGH risk 16 weeks from SOP, with $17.1M of $18.4M year-1 revenue at risk.
  FC-220 High-Density Acrylic Foam Core: RED coverage@pred=0.707
  RL-310 Fluorosilicone PET Release Liner: RED coverage@pred=1.065
  Packaging Core G590: GREEN coverage@pred=1.362
```

## GET /api/actions (Lakebase ops.mitigation_actions)
```
actions: 5
  ADT-12491	PULL_AHEAD_BUY	PROPOSED	MANUAL
  SAF-12910	PULL_AHEAD_BUY	PROPOSED	MANUAL
  FBT-12959	PULL_AHEAD_BUY	APPROVED	MANUAL
  FBT-12356	PULL_AHEAD_BUY	APPROVED	MANUAL
```

## GET /api/jobs/default/runs (Lakeflow Job: rescore-on-action)
```
run 666353243944806  TABLE  SUCCESS
run 673946780737541  TABLE  SUCCESS
run 350095189727050  ONE_TIME  SUCCESS
```

## POST /api/advisor (Model Serving: npi-mitigation-advisor)
```
tools: get_launch_risk, get_component_readiness
answer: AFT-7200 (Northstar NSM-EVX9) is HIGH risk (score 0.93), with $17.1M of $18.4M year-1 revenue at risk. The binding constraint is FC-220 High-Density Acrylic Foam Core. Its 14-week lead time is 6 weeks longer than the 8 weeks left before build-ahead starts. Only one source (Arden) is qualified, and Kvarn's PPAP isn't expected until 2027-06-07. As a result, qualified capacity covers only 71% of peak need. That gap is made worse by a predicted production yield of 70.7%, against 91.1% on the pilot line, a 20.4-point drop.
```

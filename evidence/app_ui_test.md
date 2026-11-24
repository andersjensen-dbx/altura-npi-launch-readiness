# Deployed app: browser test as a signed-in user (2026-11-23)

App: `npi-control-tower` on fevm-3, opened in the presenter's own Chrome (SSO, signed in as the workspace user) and driven by Claude Code through Chrome DevTools. All numbers below were measured in the browser against the deployed app or a local dev server on the same live services.

## Defects found and fixed

| # | Found on | Symptom | Root cause | Fix | Verified |
|---|---|---|---|---|---|
| 1 | Launch page · Mitigation Advisor | Advisor answered "INSUFFICIENT_PERMISSIONS: Principal 'app-… npi-control-tower' does not have USE CATALOG" | AppKit 0.76.1 `serving(alias).asUser(req).invoke` runs outside the user context, so the call used the app service principal | `/api/advisor` forwards the user's `x-forwarded-access-token` to `/serving-endpoints/…/invocations` (OBO) | Deployed: "Why is AFT-7200 at risk?" answered from governed data in ~15 s as the signed-in user |
| 2 | Advisor what-if | "ValueError: The feature names should match those that were passed during fit" | Both `models:/…@champion` artifacts were packaged at `artifacts/.`; the risk model overwrote the yield model. The in-process eval never exercised the packaged copy | Each champion downloaded to its own folder; notebook 08 gate reloads the packaged model like Model Serving and blocks deployment on failure (decision 19) | Gate: packaged what-if 0.929 → 0.492; served endpoint (agent v7) 0.929 → 0.466 |
| 3 | Portfolio and Launch charts | Hovered bars/rows disappeared | ECharts cannot parse oklch theme colors when deriving emphasis colors | Theme tokens converted to rgb for charts; `--chart-*` tokens in hex | Hover pixel test (below): before 0.83–0.90 of pixels kept, after 0.99–1.00 |
| 4 | All pages on a dark-mode OS | Brand red lost, chart text invisible, both ramp lines white | AppKit's `:root:not(.light)` dark palette outranked the Altura tokens | Class-based theme; Altura light by default plus a header Light/Dark toggle (decision 20) | Both themes checked on every page |
| 5 | Portfolio at 1280 px | Watchlist cut off (Actions column, row arrows) | Column widths sized for wide screens (`xl` = 1280 px) | Truncation on inner elements, `2xl` wide variants, tooltips on truncated text | Table overflow 0 px at 1280 px |
| 6 | Action Center, Launch actions | Saves failed silently; same action could be proposed twice; no way to undo a mistaken proposal | No error handling; no duplicate guard; no delete | Success/error notices, busy states, "Proposed ✓" guard, Withdraw (PROPOSED only, flows to UC via Lakehouse Sync) | Proposed then withdrew a test action on AFT-7200; baseline restored |
| 7 | Ask the Data, Advisor | Example questions not clickable / auto-sent | Static text; preset buttons sent immediately | Examples insert into the chat box and focus it | Click → textarea populated, Send enabled |
| 8 | Launch page | "999%" coverage, raw `PPAP_IN_PROGRESS`, "M2" units, `PULL_AHEAD_BUY` codes in AI text | Sentinel and source codes shown verbatim | ">200%", readable statuses with tone colors, m², playbook labels | Visual check |

## Final automated checks (local dev server on live services, after all fixes)

Per page: horizontal overflow, table overflow, console errors, error text in the page, and chart hover (minimum share of colored pixels kept while the mouse sweeps the plot area).

| Viewport | Theme | Pages | Page overflow | Table overflow | Chart pixels kept on hover | Console errors | Error text |
|---|---|---|---|---|---|---|---|
| 1728 px | light | Portfolio, Launch ×2, Action Center, Advisor, Ask | none | none | 1.00, 1.00, 1.00, 1.00 | none | none |
| 1728 px | dark | same | none | none | 0.99, 1.00, 1.00, 1.00 | none | none |
| 1280 px | light | Portfolio, Launch, Action Center, Advisor, Ask | none | none | (not repeated) | none | none |
| 1280 px | dark | same | none | none | (not repeated) | none | none |

Theme persistence: choosing Dark and reloading renders dark before first paint (`<html class="dark">`), and the toggle label flips to "Switch to light mode".

## Deployed app spot check (after final deploy)

`/api/portfolio`, `/api/actions`, `/api/launches/NPI-2027-014`, `/api/whoami`, `/api/jobs/default/runs`, `/site.webmanifest` all return 200. The header shows the signed-in user, the theme toggle switches dark ↔ light, and the console has no errors or warnings.

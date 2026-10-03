# Energy (oil & gas): the stricter VWAP reclaim (pre-registered)

Locked 2026-10-03 at the account holder's request ("test this strategy on another
industry", energy chosen), before any energy backtest was run. The 5-minute data was being
downloaded while this was written; none of it had been analysed. Nothing below changes
after results are seen; a change means a new, dated version.

## 1. Stocks

27 large, liquid U.S. oil & gas stocks across the industry, chosen by size and trading
volume, not by any test: XOM, CVX, COP, EOG, OXY, DVN, FANG, APA, CTRA, EQT, AR, RRC, OVV,
MTDR, PR, SM (producers), SLB, HAL, BKR, NOV, FTI (services), MPC, VLO, PSX (refiners),
KMI, WMB, OKE (pipelines). Benchmark: **XLE**. Data: 5-minute bars from Twelve Data,
2025-03-31 to 2026-10-02.

**Note added 2026-10-03, before any energy backtest (data, not a rule change):** CTRA
(Coterra) is not available on the free Twelve Data plan ("available starting with the Pro
or Venture plan"), so it is removed. The test uses the other **26 stocks**. All 26 and XLE
have 5-minute bars from 2025-03-31 to 2026-10-02.

## 2. What is tested

The healthcare bot's settings unchanged (`bots/energy/config` is a copy of
`bots/healthcare/config`, enforced by `tests/test_energy_config.py`): fixed 2.25% target,
0.5% stop floor, the 4% gap-day skip, the 5-share minimum, $2,500 x 2 settled-cash sizing,
never held overnight. They were built for large stocks that move a few percent a day,
which fits these companies; nothing is tuned for energy.

With one setup: the **stricter VWAP reclaim** of `docs/PREREG_STRICT_RECLAIM.md`, unchanged
(a 1-4 bar dip from above VWAP; the reclaim bar above its clock time's normal volume over
the previous 20 sessions, at least 5 needed; entry within 0.5 x ATR(14) of VWAP).

Costs: IBKR Pro **Fixed** commission on every order, the modelled one-cent spread, and
realistic resting-order exits.

As in the other tests, the "normal volume" history is built from the sessions inside each
run, so the first 5 sessions of each stage cannot produce a signal.

## 3. Periods

None of this data has been used before.
- **Warm-up, not scored:** 2025-03-31 to 2025-04-28 (the relative-volume baseline needs
  earlier days).
- **Stage 1:** 2025-04-29 to 2026-03-31.
  `python3 scripts/backtest.py --config-dir bots/energy/config --start-date 2025-04-29
  --end-date 2026-03-31 --strict-reclaim --tag ensr_s1`
- **Stage 2 (run once, only if stage 1 passes):** 2026-04-01 to 2026-10-02.
  `... --start-date 2026-04-01 --end-date 2026-10-02 --strict-reclaim --tag ensr_s2`

## 4. Pass rules (as for the healthcare test)

**Stage 1:** net profit after Fixed commission must be **above zero**, or testing stops.

**Stage 2 (deciding):**
- **PASS** if the per-session net after commission is above zero **and** the 90% lower
  bound of a block bootstrap of the daily results (blocks of 5 days, 5,000 resamples,
  seed 7) is above zero.
- **INCONCLUSIVE** if stage 2 has fewer than 30 trades.
- **FAIL** otherwise.

A pass allows paper trading only, not real money.

Reported for context, not part of the decision: trades, win rate, average win and loss,
commission, which of the three conditions rejected the most signals, and buying and
holding XLE over the same dates.

## 5. Known limits, stated before any run

- **The stricter reclaim failed on the mining stocks** (`docs/PREREG_STRICT_RECLAIM.md`).
- **Few trades are likely**; stage 2 may fall short of 30 trades and be inconclusive.
- **Survivorship:** the list is today's companies (Hess and Marathon Oil, bought in 2024-25,
  are not in it).
- **One sector, one bet:** these stocks move together with oil prices, so two open
  positions are close to one.

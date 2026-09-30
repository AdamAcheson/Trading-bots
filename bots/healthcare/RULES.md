# Healthcare bot: rules and test plan (pre-registered)

Written 2026-09-30, before any healthcare backtest was run. Nothing below may be changed
after results are seen; a change means a new, dated pre-registration.

What had been seen when this was written: daily prices only (6-month returns and average
daily ranges for 15 of these stocks, and the healthcare ETF XLV against the S&P 500 back
to 2006). No intraday strategy result for any healthcare stock had been looked at.

## 1. What the bot trades

Long only, intraday, the same engine as the mining bot (`VWAP_RECLAIM` setup). The universe
is these 60 stocks, chosen by the user on 2026-09-30:

ABT, ABBV, A, ALGN, AMGN, BAX, BDX, BIIB, TECH, BSX, BMY, CAH, COR, CNC, CRL, CI, COO,
CVS, DHR, DVA, DXCM, EW, ELV, LLY, GEHC, GILD, HCA, HSIC, HUM, IDXX, ILMN, INCY, PODD,
ISRG, IQV, JNJ, LH, MCK, MDT, MRK, MTD, MRNA, PFE, DGX, REGN, RMD, RVTY, SOLV, STE, SYK,
TMO, UNH, UHS, VEEV, VRTX, VTRS, WAT, WST, ZBH, ZTS

Benchmark for every stock: **XLV** (Health Care Select Sector SPDR), playing the role SLV,
SIL and GDX play for the miners.

## 2. Rules carried over unchanged from the mining bot

- Entry: price reclaims the session VWAP on a closed 5-minute bar; relative volume at
  least 1.10; setup score at least 70 (09:40-11:30 and 14:00-15:15) or 80 (11:30-14:00).
- Benchmark confirmation: XLV above its VWAP (0.15% tolerance) or at least 0.3% above the
  prior close, and not making a fresh intraday low.
- Chase rule: no entry more than 3 ATR above VWAP.
- Stop: the widest of 0.85 x the 5-minute ATR, the recent swing low, and the stop floor
  (section 4).
- Management: move the stop to breakeven at +1R, sell 35% at +1.5R, and trail the stop
  1 x ATR below the high from +1R.
- Exits are modelled as resting orders at the broker (`exit_model: resting_orders`).
- Trading windows: entries 09:40-15:15; manage only 15:15-15:50.
- Money: $5,000 cash account, at most $2,500 per trade, two positions at a time, settled
  cash only, 0.75% of equity risked per trade, minimum price $10.

## 3. Rules that are different from the mining bot (fixed, not tuned)

1. **Never held overnight.** Every position is sold by the 15:50 review
   (`overnight_category: manual_only` for every stock). This removes overnight gap risk,
   including earnings released before the next open.
2. **No trade in a stock on its earnings day.** Earnings dates come from the Twelve Data
   earnings calendar if the free plan provides it. If it does not, this proxy is used
   instead, decided now: skip a stock for the day when its opening gap against the prior
   close is 4% or more in either direction. Most large-cap healthcare companies report
   before the open, so an earnings day almost always opens with a gap. The proxy also
   skips other big-news days (FDA decisions, trial results), which is intended.
3. **At least 5 shares per trade.** Below that, the 35% partial exit cannot be sold and
   one share is a large part of the position. In practice this rules out stocks priced
   above about $500 on a $2,500 position; they stay in the universe and trade only if
   their price falls below that.
4. **Spread limit 0.15%** for every stock, instead of the mining bot's 0.15-0.30%.
   These are large companies with tight markets.
5. **Volatility category `normal`** for every stock (ATR stop multiplier 0.85).

## 4. What is tuned: the profit target and the stop floor

The mining bot's fixed ~4.2% target is out of reach for stocks that move about 2% a day,
so the target has to change. Six variants are pre-declared, and nothing else is tuned:

| Variant | Profit target | Stop floor |
|---|---|---|
| H1 | fixed 2.25% (`profit_target_pct: [1.5, 3.0]`) | 0.5% of price |
| H2 | fixed 2.25% | 0.3% of price |
| H3 | 1.75 x the stop distance (`scale_target_with_stop`, `preferred_r_min: 1.75`) | 0.5% |
| H4 | 1.75 x the stop distance | 0.3% |
| H5 | 2.5 x the stop distance (`preferred_r_min: 2.5`) | 0.5% |
| H6 | 2.5 x the stop distance | 0.3% |

## 5. Periods

5-minute data covers 2025-03-31 to 2026-09-29 (377 sessions; the user chose 18 months).

- **Warm-up, not scored:** the first 20 sessions, 2025-03-31 to 2025-04-28. The relative
  volume baseline is built only from earlier days, so it needs history first.
- **Tuning:** 2025-04-29 to 2026-03-31. All six variants are run here.
- **Holdout:** 2026-04-01 to 2026-09-29, the most recent six months and the closest to
  live conditions. Only the one chosen variant is ever run here.

## 6. How a variant is judged

**Metric:** net P&L per session after the modelled spread cost and the approximate IBKR
Pro Tiered commission. The commission is counted on two orders per trade:
min(max($0.35, $0.0035/share), 1% of value) + $0.0032/share, plus FINRA TAF.
`scripts/compare_runs.py` already computes this. The third order a partial exit sends is
not counted; this is noted, and it makes the metric slightly optimistic.

**Selection (tuning):** the variant with the highest metric wins. It must also be above
zero in tuning; if no variant is, the healthcare bot has no edge in the period it was
tuned on. That result is reported and the holdout is not run.

**Confirmation (holdout, run once):**
- **PASS** if the chosen variant's per-session net after commission is above zero **and**
  the 90% lower bound of a block bootstrap of the daily results is above zero. The
  bootstrap uses blocks of 5 days, 5,000 resamples and seed 7, the same as the mining
  tests.
- **INCONCLUSIVE** if the holdout has fewer than 30 trades.
- **FAIL** otherwise, however good tuning looked.

**What PASS allows:** paper trading on IBKR only, the way the mining bot runs now. It
does not allow real money. That would need a live paper record as well, and IBKR Pro,
because Lite has no API.

**Reported for context, not part of the decision:**
- buying and holding XLV over the same months
- the win rate, average R and number of trades of +3R or better
- the worst day and the largest drawdown
- how many trades were skipped by the earnings rule and by the 5-share rule

## 7. Known limits, stated in advance

- **One sector means one bet.** All 60 stocks tend to move with XLV, and two open
  positions in the same sector are close to a single position.
- **Six months of holdout is short.** Roughly 125 sessions can confirm a clear edge but
  can miss a small one.
- **Healthcare rallied over the holdout months** (XLV +19.5% from 2026-03-27 to
  2026-09-28). A long-only bot has a tailwind there that may not last.
- **The cost model is a floor.** It assumes a one-cent spread and no market impact.

## 8. What has to be built before the test (no strategy changes)

1. `bots/healthcare/config/`: `tickers.yaml` with the 60 stocks and the section-3
   settings, plus `strategy.yaml` and `risk.yaml` copied from `config/` with only the
   section-3 and section-4 differences. Runs use `scripts/backtest.py --config-dir`.
2. Two engine features, each off by default so the mining bot is unchanged:
   - the earnings-day skip
   - the 5-share minimum
3. **Regression check:** after both features exist, the mining tuning backtest must still
   reproduce its recorded result exactly (`rest_t`: 287 trades, $475.08 net). If it does
   not, the features changed something they should not have, and that is fixed first.

## Notes added after writing (no rule changes)

- **2026-09-30, earnings dates.** Twelve Data's `/earnings` and `/earnings_calendar`
  endpoints return 403 on the free plan ("available exclusively with grow or pro ...
  plans"). As section 3 specified in advance, the earnings-day rule therefore uses the
  gap proxy: skip a stock for the day when it opens 4% or more away from the prior close.
- **2026-09-30, data.** All 60 stocks have 5-minute bars for all 377 sessions from
  2025-03-31 to 2026-09-29. A few days have fewer than 75 bars because some 5-minute
  intervals had no trades: MTD on 23 days, STE on 3, and PODD, LH, UHS and WST on 1
  each. The three half-day sessions are also short, as expected. At the 2026-09-29 close,
  seven stocks were above $500 and so are effectively out of reach under the 5-share
  rule: LLY, IDXX, MCK, MTD, REGN, TMO and VRTX.
- **2026-09-30, regression check passed.** With the gap-day skip and share minimum built
  (both off in the mining config), the mining tuning backtest reproduced its recorded
  result exactly: 287 identical trades, $475.08 net.

## Result: tuning, 2026-09-30 -- no variant is profitable after commission; STOP

232 sessions, 2025-04-29 to 2026-03-31. Net after the modelled spread cost and the
approximate IBKR Pro Tiered commission (`scripts/compare_runs.py`):

| Variant | Trades | Win % | Avg R | Net before commission | After commission | Per session |
|---|---|---|---|---|---|---|
| H1 fixed 2.25%, floor 0.5% | 367 | 47.4 | +0.028 | +$87.46 | -$250.46 | -$1.08 |
| H2 fixed 2.25%, floor 0.3% | 366 | 44.8 | -0.011 | -$70.63 | -$405.65 | -$1.75 |
| H3 1.75R, floor 0.5% | 367 | 47.7 | +0.006 | -$18.40 | -$355.31 | -$1.53 |
| H4 1.75R, floor 0.3% | 367 | 45.0 | -0.035 | -$141.22 | -$475.78 | -$2.05 |
| H5 2.5R, floor 0.5% | 367 | 47.7 | +0.017 | +$36.79 | -$300.14 | -$1.29 |
| H6 2.5R, floor 0.3% | 367 | 45.0 | -0.027 | -$112.83 | -$447.78 | -$1.93 |

24-26 entries per variant were skipped by the 5-share minimum.

Per section 6, a variant must be above zero after commission in tuning before the
holdout may be run. None is, so **the holdout (2026-04-01 to 2026-09-29) was not run and
stays unseen**. Verdict: this strategy, on this universe, has no edge after costs. The
best variant makes about $0.24 per trade before commission, against about $0.92 per trade
in commission. The 0.3% stop floor was worse than 0.5% in every pairing.

Changing the rules now to find a variant that passes would be tuning on these results.
Any new attempt needs a new, dated pre-registration.

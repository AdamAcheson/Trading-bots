# Healthcare momentum bot: rules and test plan (pre-registered)

Written 2026-10-02, before any backtest of these rules was run. The rules are the
account holder's specification of 2026-10-02 plus their answers to four open points
(exit, bar size, score, XLV). Nothing below may change after results are seen; a change
means a new, dated pre-registration.

This is a second, separate strategy for the same 60 healthcare stocks. The first one
(`RULES.md`, the mining bot's VWAP reclaim) failed its tuning test on 2026-09-30 and its
holdout was never run. That holdout, 2026-04-01 to 2026-09-29, is still unseen and is
used again here.

## 1. Universe and data

The 60 stocks in `config/tickers.yaml` of this folder (the list chosen on 2026-09-30),
benchmark **XLV**. 5-minute bars from Twelve Data, regular hours only, 2025-03-31 to
2026-09-29. All indicators are computed on 5-minute bars as one continuous series across
days, the way a 5-minute chart shows them.

## 2. Indicators (all on 5-minute closes unless stated)

- EMA9, EMA20: standard exponential averages (alpha = 2 / (n + 1)).
- "EMA20 rising": EMA20 on this bar above EMA20 on the previous bar.
- RSI14: Wilder's RSI over 14 bars.
- MACD: EMA12 - EMA26 of closes; signal = EMA9 of MACD; histogram = MACD - signal.
- ATR14: Wilder's average true range over 14 bars.
- avg_volume_20d: average daily share volume over the 20 complete sessions before today.
- "average volume" for the confirmation test: the average volume of the same 5-minute
  slot of the day over the 20 sessions before today. Intraday volume is U-shaped, so a
  bar is compared with its own time of day, not with the open's heavy bars.
- Session VWAP for XLV: from today's bars only.

## 3. Gates (all must pass; not part of the score)

- price > $5
- avg_volume_20d > 1,000,000 shares
- no major binary event: the free data plan has no earnings calendar, so the stand-in
  from `RULES.md` is reused: no entry in a stock that opened 4% or more away from its
  prior close that day
- the signal bar closes between 09:45 and 14:30 ET inclusive (bars labelled 09:40 to
  14:25)
- the stock is not already held

## 4. Score (0-100 points; an entry needs at least 75)

| Block | Condition | Points |
|---|---|---|
| Trend (30) | price > EMA20 | 10 |
| | EMA9 > EMA20 | 10 |
| | EMA20 rising | 10 |
| Momentum (30) | 52 <= RSI14 <= 68 | 10 |
| | MACD > signal | 10 |
| | MACD histogram > 0 | 10 |
| Confirmation (25) | bar volume >= 1.2 x its slot's average volume | 12.5 |
| | XLV bullish: XLV > its EMA20, EMA9 > EMA20, EMA20 rising, AND XLV > its session VWAP (all four, on the same 5-minute bar) | 12.5 |
| Entry quality (15) | price <= EMA9 + ATR14 | 15 |

Noted, not changed: "MACD > signal" and "histogram > 0" are the same condition
(histogram = MACD - signal), so they always score 20 or 0 together.

When several stocks qualify on the same bar, the highest score goes first; ties go to the
higher volume ratio.

## 5. Entry, size and risk

- The signal is read on a bar's close. The order fills at the **next bar's open** plus
  half a cent (the modelled one-cent spread).
- stop = fill - 1.25 x ATR14 (ATR at the signal bar). risk_per_share = fill - stop.
- shares = floor(min($25 / risk_per_share, $1,250 / signal price)); no trade below 1 share.
- At most **3** positions open at once, and total open risk (shares x risk_per_share
  summed) at most **$75**.
- Cash account, settled cash only: purchases per day at most the equity at the start of
  the day (as the live account requires; the mining bot runs the same rule).
- Starting equity $5,000.

## 6. Exits

- The stop rests at the broker: it fills when a bar's low reaches it, at the stop or at
  that bar's open if the bar opened below it, minus half a cent.
- Trailing: once a bar's high reaches entry + 1R (R = risk_per_share), the stop trails
  at (highest high since entry - 1.25 x ATR at entry), moving up only. It is updated after
  each bar closes and applies from the next bar.
- Flat by 15:50: anything still open is sold at the close of the bar labelled 15:45,
  minus half a cent. Nothing is held overnight.
- A stock may be bought again later the same day if every condition holds again.

## 7. Costs

IBKR Pro **Fixed**, as in `config/risk.yaml`: $0.005/share, $1.00 minimum and 1% cap per
order, FINRA TAF on sales; plus the one-cent spread. Every order counts.

## 8. Periods and decision

- Warm-up, not scored: 2025-03-31 to 2025-04-28 (20 sessions for the volume averages).
- **Stage 1:** 2025-04-29 to 2026-03-31.
- **Stage 2 (holdout):** 2026-04-01 to 2026-09-29, run **only if stage 1 passes**.

Nothing is tuned, so stage 1 is itself a test. It **passes** if net P&L after all costs
is above zero. If it does not, the holdout stays unseen for whatever is tried next.

Stage 2 **passes** if net P&L after all costs is above zero **and** the 90% lower bound of
a block bootstrap of daily P&L (blocks of 5 days, 5,000 resamples, seed 7) is above zero.
Fewer than 30 trades in stage 2 means **inconclusive**.

A pass allows paper trading on IBKR only; it does not justify real money.

Reported for context: trades, win rate, average R, commission paid, largest drawdown,
entries skipped by each gate and cap, and buying and holding XLV over the same months.

## 9. Known concern, stated before any run

With $1,250 positions, the position cap usually binds before the $25 risk cap: a 5-minute
ATR on a large healthcare stock is roughly 0.2-0.4% of its price, so 1.25 x ATR risks only
about $3-6 on $1,250. A Fixed-commission round trip costs at least $2.00. Commission may
therefore be a large share of each trade's risk; the report will show how large.

## Result: stage 1, 2026-10-02 -- FAIL; the holdout was not run

`python3 scripts/backtest_healthcare_momentum.py --start 2025-04-29 --end 2026-03-31 --tag hcm_s1`
(232 sessions):

| | |
|---|---|
| Trades | 808 (win rate 30.8%) |
| Average R before commission | +0.035 |
| Gross P&L, spread included | +$21.27 |
| IBKR Fixed commission | $1,617.76 ($2.00 a trade) |
| **Net P&L** | **-$1,596.48** (-$6.88 a session; 90% bootstrap lower bound -$8.35) |
| Largest drawdown | -$1,612.19; ending equity $3,403.52 |
| Exits | 412 stopped, 392 trailing stop, 4 at 15:50 |
| Average position / risk | $1,134 / $4.49 |
| XLV buy and hold, same months | +5.9% (+$295 on $5,000) |

Not taken (signal-bar counts): score below 75 418,464; price or 20-day volume gate
241,923; settled cash 127,137; three positions open 4,376; gap day 7,308.

Section 9's concern held: the $1,250 position cap set the size, so the average trade
risked $4.49 and paid $2.00 in commission, 0.45R. But commission is not the whole
story: before commission the 808 trades made $21.27, an average of +0.035R, which is
no edge at all. Stage 1 fails, so per section 8 the holdout (2026-04-01 to 2026-09-29)
stays unseen.

A bug found while checking the first run, fixed before this result: when several
stocks qualified on the same bar, the settled-cash check ignored the orders already
queued on that bar, so some days bought more than $5,000. The first run's figures
(832 trades, -$1,617.39) are superseded.

## Variant B (pre-registered 2026-10-02, after the stage-1 result above)

Requested by the account holder after seeing stage 1. Two changes, nothing else:

1. **No XLV.** The "XLV bullish" condition is removed from the score. Its 12.5 points
   are simply gone: the maximum is 87.5 and the bar stays at **75**, as written in the
   specification. A trade may therefore fail at most one 10-point item, or the volume
   test, and nothing more.
2. **Only on days the Dow opens at least 50 points higher than its prior close.**
   Historical pre-market Dow futures are not available on the free data plan, so the
   stand-in is DIA, the ETF that tracks the Dow at 1/100 of its value: trade only on
   days when DIA's opening price is at least **$0.50** above the prior day's close
   (daily bars, `data_cache/reference/DIA_daily.json`). This is known at 09:30, before
   the first possible signal at 09:45, so it uses no information from later in the day.
   94 of the 232 stage-1 sessions qualify (counted before any trade was simulated).

Same periods and the same pass rule as section 8. Variant B was chosen after stage 1's
result was seen, so stage 1 is no longer an untouched test for it: **the holdout
(2026-04-01 to 2026-09-29) decides**, and is run only if variant B is profitable after
all costs in stage 1.

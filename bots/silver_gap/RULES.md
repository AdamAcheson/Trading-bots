# Silver "gap and go": rules and test plan (pre-registered)

Locked 2026-10-11 at the account holder's request, before any code for it was written or
any backtest of it was run. The account holder supplied the six entry conditions below;
everything they did not specify (exits, size, timing, universe, costs, the test periods)
is fixed here from the shipped mining bot's settings and the account holder's earlier
exit choices, without trying alternatives. Nothing below changes after results are seen; a
change means a new, dated version.

## 1. The account holder's conditions

Daily filters:
- **D1:** price above yesterday's daily high.
- **D2:** yesterday's close above the 200-day simple moving average (trading with the longer
  trend, not against it).
- **D3:** a gap of at least 3% from the previous close.

Intraday filters:
- **I1:** price above today's pre-market high.
- **I2:** price above today's high so far (joining strength, not buying a fade).
- **I3:** relative volume at least 2x the 14-day average.

## 2. What cannot be tested: I1

Pre-market bars are not in our data (our 5-minute history is regular hours, 9:30 to 3:55),
and the data service sells them only on a paid plan (the free plan returns "Pre-market and
post-market data are available on the Pro plan"). **I1 is therefore not tested.** The test
uses D1, D2, D3, I2 and I3. A trade that also passes I1 is a subset of the trades tested, so
this result describes a broader version of the strategy, not the exact six-condition one.

## 3. Exact definitions (all at the close of a 5-minute "signal bar")

- **D1:** the signal bar's close is above the previous trading day's high (daily bars).
- **D2:** the previous trading day's close is above the 200-day SMA of daily closes ending
  that day.
- **D3:** today's opening price (the 9:30 bar's open) is at least 1.03 x the previous
  trading day's close.
- **I2:** the signal bar's close is above the highest high of every earlier bar today
  (so the earliest possible signal bar is 9:35).
- **I3:** today's cumulative volume through the signal bar is at least 2.0 x the average
  cumulative volume through the same bar over the previous 14 sessions (needs 14 prior
  sessions of data).
- **Price gate (the shipped bot's rule):** the signal bar's close is at least $10, because
  the one-cent tick and the commission minimum make cheaper stocks too expensive to trade.

Daily bars come from `data_cache/daily` (split-adjusted), 5-minute bars from
`data_cache/historical`. A stock needs 200 prior daily bars for D2.

## 4. Timing, size and exits

- **Signal bars:** 9:35 through 3:10 (closing 9:40 through 3:15), so nothing is bought in
  the first ten minutes, as in the shipped bot. One entry per stock per day.
- **Entry:** a buy at the **next bar's open**, plus a half-spread of $0.005.
- **Size:** $2,500 per position, shares = floor($2,500 / fill price). At most **2 open
  positions**; if more stocks qualify than there are free slots, the highest relative volume
  goes first. Settled cash only: purchases in a day may not exceed the account's value at the
  start of that day, as in the shipped bot. The account starts at $5,000.
- **Initial stop:** entry minus the larger of 1.25 x ATR(14) of the 5-minute bars and 0.5% of
  the entry price (the account holder's earlier 1.25 x ATR choice and the shipped bot's 0.5%
  floor). A resting stop: filled at the stop, or at the bar's open if the bar opens below it,
  less the half-spread. If a bar reaches both the stop and anything else, the stop wins.
- **Trailing stop:** once the highest high since entry is at least 1R above entry (R = the
  initial stop distance), the stop trails the highest high by R, checked from the next bar.
- **Flat by 3:50:** anything still open is sold at the 3:45 bar's close less the half-spread.
  Nothing is held overnight.
- There is no profit target and no partial sale.

## 5. Costs (in every result)

IBKR Pro **Fixed** commission ($0.005/share, $1.00 minimum and 1% cap per order, plus FINRA
TAF on sales; `config/risk.yaml`) on every order, and the half-spread above on every fill.

## 6. Universe and periods

- **Primary (what the account holder asked for): the six silver miners of
  `config/tickers.yaml` (AG, SVM, HL, EXK, PAAS, VZLA), the most recent six months of data,
  2026-04-01 to 2026-09-30.** The price gate leaves AG, HL, PAAS and, on the days it is above
  $10, SVM and EXK; VZLA (about $3.50) never qualifies.
- **Context B (fixed now, reported with the primary):** the same six stocks over the twelve
  months before, 2025-04-01 to 2026-03-31 (PAAS only from 2025-08-15, when its history
  starts).
- **Context C:** all 29 mining stocks of `config/tickers.yaml`, same rules, 2026-04-01 to
  2026-09-30.

## 7. How the result is judged

The primary result **passes** only if, after commission and spread, all three hold:
1. net profit is above zero;
2. there are at least **30 trades** (fewer is **inconclusive**, not a pass or a fail);
3. the 90% lower bound of a block bootstrap of the daily net results (blocks of 5 days,
   5,000 resamples, seed 7) is above zero.

A pass allows paper trading only, not real money.

Reported for context, not part of the decision: trades, win rate, average win and loss,
commission, average R, exits by reason, results by stock and by month, the largest drawdown,
how many stock-days passed each condition (the funnel), and buying and holding SIL (the
silver miners ETF) over the same dates.

## 8. Known limits, stated before any run

- **I1 is missing** (section 2).
- **Few trades are likely.** A 3% gap, a break above yesterday's high and today's high, and
  twice the normal volume together are rare. Six stocks over six months may give fewer than
  30 trades, which would make the result inconclusive.
- **One regime.** The primary months are one period for silver miners; a long-only strategy
  inherits that period's trend.
- **Seen before.** These stocks and months were used to test other strategies, never this
  one, and none of its numbers were chosen from results.
- **Intraday data limits.** Entries use bar closes and next-bar opens; real fills during fast
  gap-up openings can be worse than the 0.5-cent spread assumed.

## 9. Results (run 2026-10-11, rules unchanged from sections 1 to 8)

`python3 scripts/backtest_gap_go.py --start 2026-04-01 --end 2026-09-30 --tag sg_a` (and `sg_b`, `sg_c`
for the other runs). Trade lists: `reports/backtest_trades<tag>.jsonl`. I1 was not tested.

| Run | Stocks | Sessions | Trades | Win rate | Net after costs | 90% lower bound / session | Verdict |
|---|---|---|---|---|---|---|---|
| **Primary** | 6 silver miners, 2026-04-01..09-30 | 126 | **4** | 50% | **-$9.10** | -$0.61 | **Inconclusive (<30 trades)** |
| B | same 6, 2025-04-01..2026-03-31 | 251 | 9 | 33% | -$69.77 | -$0.84 | Inconclusive |
| C | all 29 mining stocks, 2026-04-01..09-30 | 126 | 19 | 47% | -$48.42 | -$2.51 | Inconclusive |

Funnel (stock-days, each stage includes the ones before it), primary: 756 stock-days; D2 373;
D3 51; $10 price gate 49; D1 44; I2 28; I3 7; taken 4. Context B: 1,412; 1,265; 167; 89; 75; 42;
9; 9. Context C: 3,654; 2,107; 224; 221; 191; 112; 29; 19.

Primary: gross -$1.02 (spread included), commission $8.08. Exits: 2 stops, 2 trailing stops. SVM
2 trades +$49.49, AG -$28.40, PAAS -$30.19; all four in May 2026. Buying and holding SIL over the
same dates: -6.8% (+129.1% over context B's twelve months). Context C's universe includes SIL
itself, as part of the 29-stock mining list.

Reading: the strategy is far too selective to judge (4 trades in six months; the pre-registered
bar is 30). The point estimate is slightly negative in all three runs and commission is larger than
the gross result in each. Nothing here supports trading it. A pass was not reached and no rule was
changed after seeing these numbers.

## 10. Amendment 2026-10-11: the same rules on the healthcare stocks (locked before the run)

At the account holder's request the strategy is run, unchanged, on the 60 healthcare stocks of
`bots/healthcare/config/tickers.yaml`. Nothing in sections 1 to 8 changes (same conditions, I1
still untested, same entries, exits, size, costs, $10 price gate, 30-trade bar and bootstrap).
- **Healthcare primary:** all 60 stocks, 2026-04-01 to 2026-09-30 (their 5-minute data ends
  2026-09-29).
- **Healthcare context:** the same 60 stocks, 2025-04-01 to 2026-03-31.
- Benchmark in the report: buying and holding XLV over the same dates.
- Same pass rule as section 7. A fail or inconclusive result changes nothing about the
  silver result above, and the two are not pooled.
Healthcare is a slower sector than silver miners; a 3% gap there is usually an earnings or news
event. That is a reason these runs may find more or fewer trades, not a reason to change a rule.

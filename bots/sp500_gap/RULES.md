# S&P 500 daily "gap and go": rules and test plan (pre-registered)

Locked 2026-10-12 at the account holder's request, before any code for it was written or any
backtest of it was run. Nothing below changes after results are seen; a change means a new,
dated version.

## 0. Why this test

The intraday gap-and-go (`bots/silver_gap/RULES.md`) found too few trades in small groups of
stocks and, on the 29 mining stocks (107 trades), lost money before commission. The account
holder's view is that the strategy should be run **every day on a wide set of stocks** and
judged on all the trades it takes, not used to find perfect ones. This tests that: the same
idea in daily bars on the **S&P 500**, where a 3% gap on high volume happens most days
somewhere in the index. Orders are placed by hand: every signal is known after the close and
is bought at the next open.

Daily bars cannot see the intraday conditions, so each is replaced by its closest daily
version (section 2). This is a different strategy from the intraday one, not a rerun of it.
In large stocks a 3% gap on twice the volume is mostly an earnings or news reaction, so this
tests news-day continuation.

## 1. Stocks and data

Same as `bots/sp500_dip/RULES.md` sections 1 and 2: the **503 current S&P 500 members**
(`data_cache/reference/sp500_constituents.csv`), bought only on dates on or after the date the
stock joined the index; split-adjusted daily bars for indicators (`data_cache/daily`),
unadjusted bars for the real price (`data_cache/daily_unadjusted`); weekend rows dropped.
Benchmark: **SPY** buy and hold, price only.

## 2. Buy signal (all true at the close of day t; buy at the next open)

1. **Member:** the stock had joined the S&P 500 by day t.
2. **D2 (trend):** the close of day t-1 is above the 200-day simple moving average of closes
   ending day t-1.
3. **D3 (gap):** the open of day t is at least **3%** above the close of day t-1.
4. **D1 (breakout):** the close of day t is above the high of day t-1.
5. **I2 (strength, not a fade):** the close of day t is above the open of day t **and** in the
   **upper half** of the day's range (high minus low; no signal if the range is zero).
6. **I3 (volume):** the volume of day t is at least **2.0x** the average volume of the 14 days
   before it (t-14 to t-1).
7. **Price:** the real (unadjusted) close is at least **$10**.
8. **Liquid:** 20-day average dollar volume at least **$20 million**.
9. Not already held and a position slot is free.

I1 (the pre-market high) is not used: there is no pre-market data.
When more stocks qualify than there are free slots, the highest volume ratio (item 6) goes
first, then the higher dollar volume.

## 3. Exits (judged at each close; sell at the next open)

Sell at the next open after the first close where either holds:
- **Stop:** the close is below the **low of the signal day** (day t).
- **Time limit:** the position has been held **5 trading days** (the buy day counts as day 1).

There is no profit target and no market-wide switch.

## 4. Account and size

Exactly as `bots/sp500_dip/RULES.md` section 6: $5,000 cash account, settled cash only, up to
**2 positions**, each buy `min(settled cash, $5,500, max($2,500, half the previous close's
account value))`, skipped if under $2,500, shares = floor(amount / real fill price).

## 5. Costs (in every result)

IBKR Pro **Fixed** commission ($0.005/share, $1.00 minimum, 1% cap per order, plus FINRA TAF
on sales; `config/risk.yaml`) on real shares at real prices, and **0.10% slippage** against
the strategy on every fill at the open. For context only: the same run at $0 commission.

## 6. Periods and pass rule

- **Stage 1:** SPY's 200th trading day in the data (about 2007-09) to **2016-12-31**. It must
  be **profitable after costs** with at least 30 trades, or testing stops.
- **Stage 2 (deciding):** **2017-01-01 to 2026-10-02**.

Stage 2 **passes** only if, after all costs, all three hold:
1. it is **profitable**;
2. there are at least **30 trades**;
3. the 90% lower bound of a block bootstrap of the daily change in account value (blocks of 5
   days, 5,000 resamples, seed 7) is **above zero**.

Fewer than 30 trades is **inconclusive**. A pass allows paper trading only.

Reported for context, not part of the decision: trades, win rate, average win and loss, average
days held, exits by reason, net by year, signals found and skipped for lack of a slot or cash,
the $0-commission run, and SPY buy and hold with its drawdown over the same dates (so the
account holder can see what the strategy gave up or gained against simply holding the index).

## 7. Known limits, stated before any run

- **Survivorship bias:** only today's members; companies that fell out of the index are
  missing. This flatters a strategy that buys strength less than one that buys dips, but it is
  not zero (a stock that gapped up and then collapsed out of the index is absent).
- **Two slots, many signals:** on most earnings-season days far more stocks qualify than the
  two slots, so the highest volume ratio is chosen, which is a rule, not a test of every signal.
- **Fills:** buying at the open after a gap-up day is a market order into a stock that just
  moved; 0.10% slippage may be light on the busiest mornings.
- **Earnings in the hold:** a position can be held through the next earnings report; no rule
  prevents it.
- **Seen markets:** 2017 to 2026 was used to test other strategies; none of these rules was
  chosen from results.

## Result, stage 1 (2026-10-12): FAIL -- testing stopped; stage 2 not run

`python3 scripts/backtest_daily_gap.py --start 2006-01-01 --end 2016-12-31 --stage 1`
(calendar from 2007-09-04, SPY's 200th day; 503 members, none missing data):

| | Strategy | SPY buy and hold |
|---|---|---|
| $5,000 became | **$3,480 (-30.4%, -3.8% a year)** | +49.9% (+4.4% a year) |
| Largest drawdown | -37.1% | -56.5% |

| | |
|---|---|
| Closed trades | 193; win rate 45%; average win +$71.95, average loss -$73.39; average net -$7.88, average gross -$5.86 |
| Average holding | 4.5 trading days; invested on 37% of days |
| Exits | 150 time limit, 43 stop |
| Commission | $388 |
| Signals | 512 found in 9.3 years (about 55 a year); 65 skipped for lack of a slot, 254 for lack of settled cash |
| Net by year | 2007 -408, 2008 -722, 2009 +205, 2010 +319, 2011 -337, 2012 -462, 2013 +171, 2014 -266, 2015 -97, 2016 +77 |
| Context: $0 commission | $3,868 (-22.6%), still a loss; average gross/trade -$5.86 |

Reading: the entry has no edge before costs (gross average -$5.86 a trade, i.e. buying the day
after a 3%+ gap-up on twice the volume and holding up to five days returned slightly less than
nothing, after a 0.10% slippage allowance); commission only deepens the loss. Signals were rarer
than expected (about one a week) because the combined conditions plus the $10, liquidity and
membership rules are strict, so the "many signals every day" premise did not hold: more than
half of the signals could not be taken for lack of settled cash (two slots, five-day holds). No
rule was changed after seeing this.

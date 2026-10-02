# Mining "buy the close, sell the open" bot: rules and test plan (pre-registered)

Locked 2026-10-02 at the account holder's approval, before any backtest of these rules
was run. Nothing below changes after results are seen; a change means a new, dated
version.

## 0. Why this design

From `docs/WHY_MINING_MOVERS_WERE_MISSED.md`, measured on 20 years of daily bars: the
average mining stock **rose overnight and fell during the trading day** in every period
since 2007 (overnight +20% to +52% a year, daytime -15% to -29% a year, before costs).

Two consequences shape the rules:
- **A stock held for several days earns its ordinary close-to-close return.** The
  overnight edge can only be captured at the two ends of a trade: **buy at the close**
  (after the day's selling) and **sell at the open** (after the night's gains).
- **Trading every night costs too much.** Spread plus commission on two orders a day is
  about the size of the average overnight gain. So trades must be occasional and held for
  a few days, not nightly.

The entry is a **pullback in an uptrend**: buy a miner that is in a long-term uptrend
(and whose sector is too) after a short, sharp dip, at the close. This is the published
"RSI(2)" pullback idea (L. Connors), chosen before looking at any result. It fits the
evidence: dips are bought when sellers have finished for the day, and sold into an
opening rise. The intraday mining bots did the opposite (bought strength in the morning).

## 1. Universe

The 29 stocks of `config/tickers.yaml` (as in the swing test). Sector ETF: **GDX**.

## 2. Data and timing (no look-ahead)

- Daily bars, split-adjusted, from `data_cache/daily` (already downloaded; weekend rows
  dropped as in the swing test).
- Signals use **yesterday's close**. Orders:
  - **Buy:** a market-on-close (MOC) order **today**, filled at today's closing price.
  - **Sell:** a market-on-open (MOO) order, filled at the next opening price.
- Because every signal is known the evening before, the orders can be placed in the
  morning, by hand or by the bot, with no live data needed.

## 3. Indicators (daily closes)

- SMA200, SMA5: simple moving averages.
- RSI(2): Wilder's RSI over 2 days.
- Average dollar volume: 20-day mean of close x volume.

## 4. Entry (all true at yesterday's close; buy at today's close)

1. **Liquid:** close >= **$3** and average dollar volume >= $5 million. The $10 floor of
   the intraday bot blocked 48 of the 85 best mining days of 2023-2025; at the close the
   tick cost of a $3 stock is affordable.
2. **Long-term uptrend:** close > SMA200.
3. **Sector uptrend:** GDX close > its SMA200.
4. **Short-term pullback:** RSI(2) < **10**.
5. Not already held, and a position slot is free.

When more qualify than there are free slots, the lowest RSI(2) goes first, then the
higher dollar volume.

## 5. Exit (checked at each close; sell at the next open)

Sell at the next open on the first close where any of these holds:
- **Bounce done:** close > SMA5.
- **Time limit:** the position has been held **10 trading days**.
- **Disaster stop:** close < **85%** of the entry price.

There is no intraday stop; the evidence says daytime weakness is normal for these stocks.
An overnight gap down fills at the open, below the stop.

## 6. Account and size

- $5,000 cash account; buys only with settled cash (sale proceeds settle the next
  business day).
- **3 equal positions,** each one-third of the previous close's equity (about $1,650 at
  the start), the size the account holder chose for the swing bot (option A).
  Shares = floor(target / fill price).
- Buys are skipped if settled cash covers less than half the target.

## 7. Costs (in every result)

- **IBKR Pro Fixed** commission: $0.005/share, $1.00 minimum and 1% cap per order, plus
  FINRA TAF on sales.
- Slippage: **0.15%** against the bot on every fill. That is more than the swing test's
  0.10%, because miners' closing and opening auctions are thinner.
- For context only, not part of the decision: the same run at $0 commission, as with
  orders placed by hand in the IBKR Lite account.

## 8. Periods and pass rule (as for the swing bot)

- **Stage 1:** 2007-08-31 (GDX's 200th day) to **2018-12-31**. It must be profitable after
  costs, or testing stops.
- **Stage 2 (deciding):** **2019-01-01 to 2026-09-30**.

Stage 2 **passes** if, after all costs, it is profitable **and** either:
- (a) its total return beats buying and holding GDX over the same dates, **or**
- (b) it earns at least 75% of GDX's return with a largest drawdown no more than
  two-thirds of GDX's.

Fewer than 20 trades means **inconclusive**.

Reported for context:
- trades, win rate, average gain and loss, days held, exits by reason
- yearly results and largest drawdown
- the $0-commission run
- a check variant that buys at the **same** day's close the signal was read on. That
  variant is not tradeable exactly; it is reported to show how much the one-day delay
  costs.

A pass allows paper trading first; it does not justify real money by itself.

## 9. Known limits, stated before any run

- **Survivorship bias:** the list is today's companies; miners that failed since 2007
  are missing.
- **Opening and closing prices** in daily data are auction prints. Real MOC and MOO
  fills match them closely for liquid names but can differ for thin ones; the 0.15%
  slippage is meant to cover this, and may not be enough for the smallest names.
- **The overnight finding comes from these same years.** The rules use it only for
  timing (close in, open out). The entry and exit rules are a published idea, fixed
  here without testing variants.
- **Three positions in one sector move together.** A sector-wide gap down hits all of
  them at once.

## Result, stage 1 (2026-10-02): FAIL -- testing stopped; stage 2 not run

`python3 scripts/backtest_mining_overnight.py --start 2006-01-01 --end 2018-12-31`
(calendar from 2007-08-31, GDX's 200th day):

| | |
|---|---|
| $5,000 became | **$3,351 (-33.0%, -3.5% a year)** |
| Largest drawdown | -44.7% |
| GDX buy and hold | -44.0% (largest drawdown -81.3%) |
| Closed trades | 281; win rate 52%; average win $52.75, average loss -$69.26; average net -$5.87 |
| Average holding | 4.1 trading days |
| Exits | 264 back above SMA5, 12 disaster stops, 5 time limits |
| Commission | $620 |
| Net by year | 2007 -395, 2008 +223, 2009 +733, 2010 -415, 2011 +197, 2012 -24, 2014 -877, 2016 -1,123, 2017 -34, 2018 +65 |

Context, not part of the decision:
- $0 commission: $3,836 (-23.3%).
- Buying at the same close the signal was read on (not exactly tradeable): $4,586
  (-8.3%; win rate 60%). Waiting a day misses part of the bounce, but even without the
  delay the rules lose money.

The bot lost less than GDX in a mining bear market, with about half GDX's drawdown, but
the pass rule requires a profit in stage 1. Trades were checked by hand against the raw
daily bars: signals, closing buys and opening sells match.

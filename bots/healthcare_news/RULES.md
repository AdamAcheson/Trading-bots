# Healthcare "news-day drift" bot: rules and test plan (pre-registered)

Locked 2026-10-02 at the account holder's approval, before any backtest of these rules
was run. Nothing below changes after results are seen; a change means a new, dated
version.

## 0. Why this design

From `bots/healthcare/WHY_MOVERS_WERE_MISSED.md` and the 20-year check in
`docs/WHY_MINING_MOVERS_WERE_MISSED.md`:

- The healthcare stocks that rose 25%+ made almost all of it on **a handful of big days**
  (each stock's 5 best days were 96% of its rise), many in earnings season, so most
  likely news days.
- Healthcare shows **no stable overnight or daytime pattern** over 20 years, so unlike
  mining, the time of day is not the edge.
- The intraday bots avoided news days and were in and out within minutes. The swing
  breakout bot bought chart breakouts, not news, and failed after 2018.

The idea tested here is the opposite of avoiding news: **buy the day after a stock jumps
on heavy volume, and hold it for about two months.** It rests on a long-documented
effect, the drift after earnings announcements (Bernard and Thomas, 1989, and much
since): after strong news, prices tend to keep moving in the same direction for weeks,
because the market absorbs news slowly. This idea was chosen before any test, and no
variants of it are tried.

The free data plan has no earnings calendar, so a **news day** is identified from price
and volume alone. That catches earnings, FDA decisions, trial results and takeover talk
alike.

## 1. Universe

The 60 stocks of `bots/healthcare/config/tickers.yaml`. Benchmark: **XLV**.

## 2. Data and timing (no look-ahead)

- Daily bars, split-adjusted, from `data_cache/daily` (weekend rows dropped).
- Signals use **the news day's close**. The buy is a market-on-open order the **next
  morning**; sells are market-on-open orders too. Everything is known the evening before,
  so orders can be placed by hand or by the bot, and no live data is needed.

## 3. A news day (all at that day's close)

1. **Big jump:** close at least **+5%** above the previous close.
2. **Heavy volume:** that day's volume at least **3x** its average over the previous 50
   days.
3. **Held its gain:** close in the **upper half** of the day's range,
   i.e. close >= (high + low) / 2.
4. **Large, liquid stock:** close >= $10, and average dollar volume over the previous 20
   days >= $20 million.

## 4. Entry

Buy at the next open if a position slot is free and the stock is not already held. When
there are more news days than free slots, the highest volume multiple goes first.

## 5. Exit (checked at each close; sell at the next open)

Sell at the next open on the first close where either holds:
- **Time:** the position has been held **40 trading days** (about two months).
- **News failed:** close below **the news day's low**.

There is no profit target and no trailing stop: the drift is held for its expected span.

## 6. Account and size

- $5,000 cash account; buys only with settled cash (sale proceeds settle the next
  business day).
- **3 equal positions,** each one-third of the previous close's equity (about $1,650 at
  the start), as the account holder chose for the swing bot (option A).
  Shares = floor(target / fill price).
- Buys are skipped if settled cash covers less than half the target.

## 7. Costs (in every result)

- **IBKR Pro Fixed** commission ($0.005/share, $1.00 minimum and 1% cap per order, plus
  FINRA TAF on sales).
- Slippage **0.10%** against the bot on every fill at the open.
- For context only, not part of the decision: the same run at $0 commission (IBKR Lite,
  orders placed by hand).

## 8. Periods and pass rule (as for the swing and mining bots)

- **Stage 1:** XLV's 200th trading day in the downloaded data (2007-08-31) to
  **2018-12-31**. It must be profitable after costs, or testing stops.
- **Stage 2 (deciding):** **2019-01-01 to 2026-09-30**.

Stage 2 **passes** if, after all costs, it is profitable **and** either:
- (a) its total return beats buying and holding XLV over the same dates, **or**
- (b) it earns at least 75% of XLV's return with a largest drawdown no more than
  two-thirds of XLV's.

Fewer than 20 trades means **inconclusive**.

Reported for context:
- trades, win rate, average gain and loss, exits by reason
- yearly results and largest drawdown
- how many news days were found and how many were skipped for lack of a slot
- the $0-commission run

A pass allows paper trading first; it does not justify real money by itself.

## 9. Known limits, stated before any run

- **Survivorship bias:** the list is today's companies; ones that failed or were taken
  over since 2007 are missing. A stock that jumped on takeover news and then disappeared
  is not in the data.
- **Already seen:** the stage 2 years were used once before, to test the swing bot
  (which failed). The 2025-2026 movers were studied in detail. The news-day thresholds
  (+5%, 3x volume, upper half of the range, 40 days) are conventional round numbers
  fixed here without trying others.
- **Earnings misses are not traded.** The bot is long only and buys only up-moves.
- **Concentration:** three positions in one sector; news days cluster in earnings season,
  so slots can fill at once and later news days are skipped.

## Result, stage 1 (2026-10-02): FAIL -- testing stopped; stage 2 not run

`python3 scripts/backtest_healthcare_news.py --start 2006-01-01 --end 2018-12-31`
(calendar from 2007-08-31, XLV's 200th day):

| | |
|---|---|
| $5,000 became | **$3,516 (-29.7%, -3.1% a year)** |
| Largest drawdown | -56.3% |
| XLV buy and hold | +151.5% (largest drawdown -40.6%) |
| News days found | 272 (83 skipped: no free slot) |
| Closed trades | 178; win rate 38%; average win $105, average loss -$79; average net -$8.34 |
| Average holding | 25.7 trading days |
| Exits | 92 news failed (close below the news day's low), 86 after 40 days |
| Commission | $357 |
| Net by year | 2007 +428, 2008 -1,701, 2009 -39, 2010 -431, 2011 -684, 2012 +656, 2013 +395, 2014 +304, 2015 -493, 2016 -305, 2017 +37, 2018 +348 |

Context, not part of the decision: at $0 commission, $4,077 (-18.5%).

Half the positions (92 of 178) fell back below the news day's low before 40 days were
up. After a big up day on heavy volume, these stocks gave back the jump about as often
as they extended it. In this universe and period, the drift was not there. Trades were
checked by hand against the raw daily bars: news days, next-open buys and exits match.

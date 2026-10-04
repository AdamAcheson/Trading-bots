# S&P 500 "buy the dip in strong companies, in a healthy market": rules and test plan (pre-registered)

Locked 2026-10-04 at the account holder's request, before any backtest of these rules was
run. The daily data was still downloading; none of it had been analysed. Nothing below
changes after results are seen; a change means a new, dated version.

## 0. Why this design

What a month of testing showed (`docs/FINAL_SUMMARY.md`): intraday trading on a $5,000
account cannot beat its costs, the gains came from holding for days or longer, and our own
indicator combinations had no edge. The account holder chose:
- **goal:** smaller drops (falling much less than the market in crashes);
- **holding:** days to a few weeks;
- **stocks:** individual S&P 500 stocks, $15 minimum, no upper price limit;
- **running it:** orders placed by hand, so every signal must be known the evening before;
- **size:** up to 2 positions of $2,500 to $5,500.

The entry is the published short-term pullback idea for large U.S. stocks (L. Connors'
2-day RSI): a stock in a long-term uptrend that drops sharply for a day or two tends to
bounce within days. A market switch keeps the strategy in cash while the S&P 500 is below
its 200-day average, which is the drawdown control. Nothing here was chosen from results;
no variants are tried.

## 1. Stocks

The **503 current S&P 500 members** (`data_cache/reference/sp500_constituents.csv`, from
github.com/datasets/s-and-p-500-companies, fetched 2026-10-04). A stock can be bought only
on dates **on or after the date it joined the S&P 500** (the list's "Date added"), so the
test never buys a company years before it became a large one.

Benchmark: **SPY** (buy and hold, price only).

## 2. Data and timing (no look-ahead)

- Daily bars from Twelve Data, split-adjusted, 2006-11-15 to 2026-10-02
  (`data_cache/daily`; weekend rows dropped, as in the other daily tests).
- Each stock's split history (`data_cache/splits`). The price a stock actually traded at on
  a past date is the adjusted price times the split factors after that date; the $15
  minimum uses that real price.
- **Note added 2026-10-04, before any backtest (data source, not a rule change):** Twelve
  Data's split histories are not on the free plan (an early test call worked only because
  AAPL is a free demo symbol). The real price is taken instead from **unadjusted daily
  bars** (`data_cache/daily_unadjusted`, Twelve Data `adjust=none`), which are the prices as
  actually traded. Indicators still use the split-adjusted bars.
- Every signal uses **that day's close**. Buys and sells are made at the **next day's
  open**, so they can be placed by hand before the market opens.

## 3. Indicators (daily)

- SMA200, SMA5: simple moving averages of the close.
- RSI(2): Wilder's RSI over 2 days.
- Average dollar volume: 20-day mean of close x volume.

## 4. Buy signal (all true at the day's close; buy at the next open)

1. **Healthy market:** SPY's close is above SPY's SMA200.
2. **Member:** the stock had joined the S&P 500 by that date.
3. **Price:** the stock's real (not split-adjusted) close is **at least $15**.
4. **Liquid:** average dollar volume of at least $20 million.
5. **Strong company:** the stock's close is above its own SMA200.
6. **The dip:** RSI(2) **below 10**.
7. **No news gap:** the stock did not open 4% or more above or below the prior close on
   that day or the day before (a stand-in for earnings and other news; the free data plan
   has no earnings calendar).
8. Not already held, and a position slot is free.

When more stocks qualify than there are free slots, the lowest RSI(2) goes first, then the
higher dollar volume.

## 5. Sell signal (checked at each close; sell at the next open)

Sell at the next open on the first close where any of these holds:
- **Bounce done:** the close is above the stock's SMA5.
- **Time limit:** the position has been held **10 trading days**.
- **Disaster stop:** the close is below **85%** of the entry price.
- **Market switch:** SPY closes below its SMA200 (sell every position).

## 6. Account and size (as agreed 2026-10-04)

- $5,000 **cash account**; buys only with settled cash (a sale settles the next business
  day).
- **Up to 2 positions.** Each buy uses
  `min(settled cash, $5,500, max($2,500, half the previous close's account value))`,
  and is **skipped if that is under $2,500**. Shares = floor(amount / fill price).
  So positions are about $2,500 each at the start, grow toward $5,500 as the account grows,
  and the strategy holds one position or none when settled cash is short.

## 7. Costs (in every result)

- **IBKR Pro Fixed** commission: $0.005/share, $1.00 minimum and 1% cap per order, plus
  FINRA TAF on sales.
- Slippage **0.10%** against the strategy on every fill at the open.
- For context only, not part of the decision: the same run at $0 commission.

## 8. Periods and pass rule

- **Stage 1:** SPY's 200th trading day in the data (about 2007-09) to **2016-12-31**. It
  must be **profitable after costs**, or testing stops.
- **Stage 2 (deciding):** **2017-01-01 to 2026-10-02**.

Stage 2 **passes** only if, after all costs, all three hold:
1. it is **profitable**;
2. its **largest drawdown is no more than half of SPY's** over the same dates;
3. its **return per unit of drawdown** (yearly return divided by largest drawdown) is
   **at least SPY's**.

Fewer than 30 trades in a stage means **inconclusive**.

Reported for context: trades, win rate, average win and loss, average days held, share of
days invested, exits by reason, yearly results, worst trades, how many signals were skipped
for lack of a slot or cash, and the $0-commission run.

A pass allows paper trading first; it does not justify real money by itself.

## 9. Known limits, stated before any run

- **Survivorship bias:** only today's members are in the list. Companies that left the
  index after collapsing (and the dips that never recovered) are missing, which flatters a
  dip-buying strategy. Trading only after each stock's join date reduces, but does not
  remove, this.
- **The same RSI(2) entry failed on mining stocks** (`bots/mining_overnight/RULES.md`,
  -33% over 2007-2018 while GDX fell 44%).
- **The effect is reported to have weakened since about 2010.**
- **Concentration:** two stocks at a time. A single company's bad news can open 10-25%
  lower, and no stop prevents that; the gap rule cannot see earnings that fall during a
  holding period.
- **Dividends** are left out of both the strategy and SPY.
- **Seen markets:** the 2017-2026 market has been studied in other contexts (not with this
  strategy or these stocks, apart from the 60 healthcare names used in earlier daily tests).

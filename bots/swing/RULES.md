# Swing bot ("hold the leaders"): rules and test plan

Draft of 2026-10-02 for the account holder's review. **Not yet locked:** section 9 has
one decision for the account holder. Once it is made, this file is committed as the
pre-registration and nothing in it changes after results are seen; a change means a new,
dated version.

## 0. Why this design

From `docs/WHY_MINING_MOVERS_WERE_MISSED.md` and
`bots/healthcare/WHY_MOVERS_WERE_MISSED.md`:

- The stocks that rose 25%+ made most of their gain on a handful of days, often news
  days, spread over weeks and months.
- In mining the whole rise came overnight; during trading hours the stocks lost ground
  on average.
- Every intraday bot traded in and out within minutes, was flat every night, skipped
  news days, avoided "extended" stocks, and paid about $2 of commission on trades that
  made cents.

So this bot does the opposite: it buys stocks that are **already** strong (known at the
time, no hindsight), **holds them overnight and through news**, uses a **wide** stop, and
trades **a few times a month**.

## 1. Universes (two separate runs, same rules)

- **Mining:** the 29 stocks of `config/tickers.yaml`: AG, SVM, HL, EXK, VZLA, SIL, CDE,
  EQX, SSRM, DRD, FSM, FCX, SCCO, RIO, BHP, UEC, MP, USAR, CRML, CMP, GFI, HMY, AUGO,
  PPTA, PAAS, WPM, HBM, CCJ, VALE. Sector ETF: **GDX**.
- **Healthcare:** the 60 stocks of `bots/healthcare/config/tickers.yaml`. Sector ETF:
  **XLV**.

Each runs as its own $5,000 account.

## 2. Data and timing

- **Daily bars** (open, high, low, close, volume), split-adjusted, from Twelve Data: up
  to 20 years per symbol, about one credit each (about 95 credits in all).
- Signals are computed **after the close**. Orders go in at the **next day's open**, so a
  15-minute data delay does not matter, and the orders can be placed by hand.

## 3. Indicators (daily)

- 126-day return: close / close 126 trading days earlier - 1 (about six months).
- SMA50, SMA200: simple moving averages of the close.
- ATR20: average true range over 20 days (simple average).
- 20-day high: the highest close of the previous 20 days, not counting today.
- Average dollar volume: mean of close x volume over the last 20 days.

## 4. Entry (all must be true at the close; buy at the next open)

1. **Liquid:** close >= $5 and average dollar volume >= $5 million.
2. **Already a leader:** 126-day return >= **+25%**.
3. **In an uptrend:** close > SMA50 and SMA50 > SMA200.
4. **Breaking out:** close > the 20-day high.
5. **Sector not in a downtrend:** the sector ETF's close > its SMA200. This applies to
   new buys only and never forces a sale.
6. **Not already held,** and a position slot is free (section 6).

When more stocks qualify than there are free slots, the highest 126-day returns go first.

## 5. Exit (checked at each close; sell at the next open)

- **Trailing stop:** sell when the close falls below **(highest close since entry -
  3 x ATR20)**. ATR20 is fixed at its value on the entry day, and the stop only rises.
- There is **no profit target and no time limit**. Winners are held for as long as the
  trend lasts.
- Positions are **held overnight and through earnings and news**, deliberately.
- A stock that is sold may be bought again later if every entry condition holds again.

## 6. Account

- $5,000, cash account; buys only with settled cash. Sale proceeds settle the next
  business day, so money from a sale can be reused the day after.
- Size: see section 9.

## 7. Costs (included in every result)

- **IBKR Pro Fixed** commission: $0.005/share, $1.00 minimum and 1% cap per order, plus
  FINRA TAF on sales.
- Slippage: **0.10%** against the bot on every fill at the open. This is larger than the
  one-cent spread the intraday tests assumed, because opening prices are less precise.
- For context only, not part of the decision: the same run at $0 commission, which is
  what manual orders in the IBKR Lite account would cost.

## 8. Periods and pass rule

Nothing is tuned: the rules above are fixed, so each period is a test.

- **Stage 1:** from the first date with enough history (200 days for SMA200) to
  **2018-12-31**. It must be profitable after costs, or testing stops there.
- **Stage 2 (deciding):** **2019-01-01 to 2026-09-30**.

Stage 2 **passes** for a universe if, after all costs, it is profitable **and** either:
- (a) its total return beats buying and holding the sector ETF (GDX or XLV) over the
  same dates, **or**
- (b) it earns at least 75% of the ETF's return with a largest drawdown no more than
  two-thirds of the ETF's.

Fewer than 20 trades in stage 2 means **inconclusive**.

Reported for context:
- trades, win rate, average gain and loss, holding time
- largest drawdown, yearly results, and the best and worst trades
- buying and holding the equal-weight universe
- the $0-commission run

A pass allows paper trading on IBKR (or signals placed by hand) first. It does not
justify real money by itself.

## 9. DECISION FOR THE ACCOUNT HOLDER: position size

The intraday specification capped risk at $25 a trade (0.5% of $5,000) and positions at
$1,250. A swing stop of 3 x the daily ATR is wide: typically 8-15% of the price for a
miner and 5-8% for a large healthcare stock. The two cannot both hold with useful
position sizes:

- **Option A (recommended): 3 equal positions,** each one-third of current equity
  (about $1,650). The risk per trade is then about $80-250 (roughly 1.5-5% of the
  account), depending on the stock's volatility. The account is fully invested when
  three leaders exist, and commission is about 0.1% of each position each way.
- **Option B: keep $25 risk per trade,** shares = $25 / (3 x ATR20), up to 3 positions.
  Positions would be roughly $170-500, most of the account would sit in cash, and the
  $1.00 minimum commission would cost about 0.2-0.6% each way.

## 10. Known limits, stated before any run

- **Survivorship bias.** Both universes are today's lists. Companies that collapsed,
  merged or were delisted over the past 20 years are missing, which flatters a
  long-only test, stage 1 most of all. Free data cannot fix this; it is a reason to
  weight stage 2 more and to paper-trade before trusting it.
- **Short histories.** Several mining names (USAR, CRML, AUGO, VALE's US listing in the
  cache) have short histories and only trade in the later years.
- **Concentration.** Three positions in one sector can fall together, and stops are
  only checked at the close: a big overnight gap down fills at the open, below the stop.
- **Prior knowledge.** I have seen the recent price history of these sectors (for
  example the 2023-2026 rise of the miners) while analysing earlier bots. No swing-rule
  result has been looked at for any period.

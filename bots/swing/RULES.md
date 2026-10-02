# Swing bot ("hold the leaders"): rules and test plan (pre-registered)

Locked 2026-10-02, before any swing backtest was run, after the account holder chose
position-size option A (section 9). Nothing below changes after results are seen; a
change means a new, dated version.

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

Each runs as its own $5,000 account, and each stage starts again from $5,000 in cash.

## 2. Data and timing

- **Daily bars** (open, high, low, close, volume), split-adjusted (not dividend-adjusted,
  for the bot and the ETF comparison alike), from Twelve Data: up to 20 years per symbol,
  about one credit each (about 95 credits in all).
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

- **Stage 1:** from the first date the sector ETF has 200 days of history (SMA200) to
  **2018-12-31**; each stock joins once it has 200 days of its own. It must be profitable after costs, or testing stops there.
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

## 9. Position size: option A, chosen by the account holder 2026-10-02

- **3 equal positions,** each targeting one-third of the account's equity at the
  previous close (about $1,650 at the start). Shares = floor(target / fill price).
- If settled cash covers less than half of the target, the buy is skipped; otherwise
  the bot buys what settled cash allows.
- The risk per trade follows from the stop: 3 x ATR20 x shares, typically $80-250.
- Option B ($25 risk per trade, positions of about $170-500) was not chosen.

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

## Results, 2026-10-02

Data note: two stray weekend rows in the Twelve Data downloads (CVS 2009-07-26, a
zero-volume bar at 2.5x the price; one in PAAS) are dropped by the loader. No other
cleaning. MRNA's +177% day on 2026-08-19 is real (the 5-minute data agrees; 199 million
shares traded).

### Stage 1 (to 2018-12-31; calendar starts 2007-08-31, the ETF's 200th day)

| | Mining | Healthcare |
|---|---|---|
| $5,000 became | **$3,527 (-29.5%)** | **$16,519 (+230.4%, +11.1% a year)** |
| Largest drawdown | -68.0% | -27.7% |
| Sector ETF buy and hold | GDX -44.0% (drawdown -81.3%) | XLV +151.5% (drawdown -40.6%) |
| Equal-weight universe | -34.0% (20 stocks) | +346.0% (52 stocks; survivorship-biased) |
| Closed trades, win rate | 99, 34% | 144, 48% |
| Commission | $204 | $297 |
| Verdict | **FAIL** (not profitable) | **PASS** |

Mining lost less than GDX, but stage 1 must be profitable, so **mining stops here**;
its stage 2 was not run.

### Stage 2, healthcare (2019-01-02 to 2026-09-30, the deciding test)

| | |
|---|---|
| $5,000 became | **$3,565 (-28.7%, -4.3% a year)** |
| Largest drawdown | -53.0% |
| XLV buy and hold | +97.7% (largest drawdown -28.8%) |
| Equal-weight universe (58 stocks) | +143.9% |
| Closed trades, win rate | 130, 35% (average win $149, average loss -$100, median hold 23 days) |
| Net of closed trades by year | 2019 -530, 2020 +335, 2021 +1,196, 2022 -348, 2023 -1,360, 2024 -148, 2025 -480, 2026 -174 |
| Commission | $263 |
| Verdict | **FAIL** |

Context only: at $0 commission, stage 2 ends at $3,414 (-31.7%) and stage 1 at $17,066
(+241.3%). The $0 run takes the same trades until the 79th (WST, August 2023), then
cash timing sends it down a slightly different path.

Healthcare's strong stage 1 did not hold up from 2019: since then, breakouts in stocks
already up 25% mostly reversed (win rate 35%), and the bot lost money while XLV almost
doubled. With survivorship bias favouring stage 1, the honest reading is that this
strategy has not shown an edge in either sector.

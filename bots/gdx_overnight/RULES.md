# GDX "overnight only" bot: rules and test plan (pre-registered)

Locked 2026-10-02 at the account holder's approval, before any backtest of these rules
was run and before GDX's own overnight return was measured. Nothing below changes after
results are seen; a change means a new, dated version.

## 0. Why this design

From `docs/WHY_MINING_MOVERS_WERE_MISSED.md`, measured on 20 years of daily bars: the
average mining stock **rose overnight and fell during the trading day** in every period
since 2007 (overnight +20% to +52% a year, daytime -15% to -29% a year, before costs).
Rising in the hours the market is closed and falling while it is open is also a
published finding across many markets (for example Cliff, Cooper and Gulen, 2008;
Lou, Polk and Skouras, 2019).

The earlier mining tests could not use it:
- The intraday bots held only during the day, the half that falls.
- Trading individual miners every night costs too much: their spreads plus commission
  are about the size of the average overnight gain.
- The pullback bot (`bots/mining_overnight`) bought at the close and sold at the open,
  but held for days in between, so it earned mostly ordinary returns.

This design takes the pattern directly, at the lowest cost available: **one liquid ETF
(GDX), bought at the closing auction and sold at the next opening auction, every
trading day, and nothing held during the day.** There are no indicators or settings to
tune. No variants are tried.

## 1. Instrument

**GDX** (VanEck Gold Miners ETF) only. Benchmark: buying and holding GDX.

## 2. Data and timing (no look-ahead)

- Daily bars, split-adjusted, `data_cache/daily/GDX.json` (already downloaded; weekend
  rows dropped as in the other daily tests). Prices are used as they are; no row is
  removed or corrected.
- **Buy:** a market-on-close order on day d, filled at day d's close.
- **Sell:** a market-on-open order on day d+1, filled at day d+1's open.
- Nothing is decided from prices: the bot buys every trading day of the period except
  the last (which has no next open inside the period). It needs no live quotes.

## 3. Account and settlement: two versions, one of which decides

The account is a $5,000 **cash account** today. In a cash account, money from a sale
settles the next business day (T+1) and only settled money can buy. Money from the
morning sale is therefore not usable at that afternoon's close.

- **Version C, cash account (DECIDES):** the $5,000 is split into **two halves of
  $2,500**. Half A trades on the 1st, 3rd, 5th ... night of the period, half B on the
  2nd, 4th, 6th .... Each half buys with all of its settled cash. A half's sale on the
  morning of day d+1 settles on day d+2, in time for its next buy at day d+2's close.
- **Version M, margin account (context):** the whole account buys every night, using
  the morning's sale money the same afternoon. No money is borrowed: purchases never
  exceed the account's cash. (Margin accounts may use unsettled sale money; the $25,000
  pattern-day-trader rule concerns buying and selling on the **same** day, which this
  never does. Both points are for the account holder to confirm with IBKR.)

Shares = floor(cash available / buy fill), reduced until shares x fill + commission
fits. Today's T+1 settlement is applied to every year, since the question is how the
rules would work now. Trading days stand in for business days.

## 4. Costs (in every result)

- **IBKR Pro Fixed** commission: $0.005/share, $1.00 minimum and 1% cap per order, plus
  FINRA TAF on sales (`config/risk.yaml`).
- Slippage: **0.05%** against the bot on every fill. GDX's spread is about one cent
  (about 0.03% at $30, less above), and auction orders all fill at one auction price;
  the 0.05% allows for daily-bar prints differing from the auction price.
- Context, not part of the decision: each version also at **$0 commission** (IBKR Lite
  charges no commission on US-listed stocks and ETFs; the account holder should confirm
  this applies to their account and to API orders).

So four runs are reported per stage: C and M, each at Fixed and at $0 commission.
**Only version C at Fixed commission decides.**

## 5. Periods and pass rule (as for the other daily tests)

- **Stage 1:** 2007-08-31 (GDX's 200th day, as in the other mining tests) to
  **2018-12-31**. It must be profitable after costs, or testing stops.
- **Stage 2 (deciding):** **2019-01-01 to 2026-09-30**.

Stage 2 **passes** if, after all costs, it is profitable **and** either:
- (a) its total return beats buying and holding GDX over the same dates, **or**
- (b) it earns at least 75% of GDX's return with a largest drawdown no more than
  two-thirds of GDX's.

GDX buy and hold runs from the first day's close to the last day's close.
Fewer than 20 nights traded means **inconclusive**.

Reported for context:
- nights traded, share of winning nights, average night before costs, best and worst
  night
- the **break-even cost**: the average overnight return before costs (geometric), i.e.
  the round-trip cost per night, as a share of the position, that would leave the
  strategy flat
- GDX's own overnight-only and day-only returns before costs
- yearly results and largest drawdown (valued at each close, while holding)
- how many days in the data have an open exactly equal to the close (a sign of a missing
  opening print; such rows are used as they are)

A pass allows paper trading first; it does not justify real money by itself.

## 6. Known limits, stated before any run

- **The overnight finding comes from these same years.** It was measured on the average
  mining stock, not GDX; GDX's own overnight return has not been looked at before this
  test. Even so, a pass here is weaker evidence than a pass on unseen data.
- **Opening and closing prices** in daily data may not be exactly the auction prices an
  order would get. The 0.05% slippage is meant to cover this.
- **Dividends** are left out of both the strategy and the benchmark. The holder of record
  at the close before the ex-dividend date gets the dividend, and both the strategy and
  buy-and-hold hold every night, so both would collect the same dividends.
- **Overnight risk:** all the exposure is at night, when no stop can act. A gap down at
  the open is taken in full.
- **Taxes:** selling and rebuying the same ETF daily creates many short-term trades and
  wash sales in a taxable account. Not modelled; a matter for a tax professional.
- **Bank holidays** on which markets are open (settlement is delayed a day) are not
  modelled.

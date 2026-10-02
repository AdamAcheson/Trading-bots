# Trading bots: final summary (2026-10-02)

## The answer in one paragraph

Over about a month, eight trading strategies were built and tested on two sectors,
silver and gold mining and large-cap healthcare, for a $5,000 cash account at Interactive
Brokers. Each was tested fairly: the rules were written down and locked before any
result was seen, costs were included, and the decision was made on data the rules had
not been tuned on. **None passed. None beat simply holding the sector's ETF (GDX or XLV)
over the deciding period, and almost all lost money after costs.** The recommendation is
to pause strategy building and not trade real money with any of these bots.

## What was tested

| # | Strategy | Sector | Period decided on | Result after costs | Holding the ETF instead |
|---|---|---|---|---|---|
| 1 | Intraday VWAP reclaim (the original bot) | Mining | 2023-09 to 2025-12 (672 trades) | **-$1,172** | GDX +177.9% |
| 2 | Same, one $5,000 trade a day | Mining | 2023-09 to 2025-12 (411 trades) | **-$1,678** | GDX +177.9% |
| 3 | Intraday VWAP reclaim, 6 target/stop variants | Healthcare | 2025-04 to 2026-03 | best **-$710** (Fixed commission) | XLV +5.9% |
| 4 | Account holder's momentum rules (EMA, RSI, MACD, 5-minute bars) | Healthcare | 2025-04 to 2026-03 (808 trades) | **-$1,596** | XLV +5.9% (+$295) |
| 5 | Same without XLV, only on days the Dow opens 50+ points up | Healthcare | same (373 trades) | **-$626** | |
| 6 | Swing: buy leaders up 25%+ on breakouts, wide trailing stop | Mining | 2007-2018 | **-29.5%** | GDX -44.0% |
| | | Healthcare | 2019-2026 (passed 2007-2018 at +230%) | **-28.7%** | XLV +97.7% |
| 7 | Mining: buy dips at the close, sell at the open | Mining | 2007-2018 | **-33.0%** | GDX -44.0% |
| 8 | Healthcare: buy the day after a news jump, hold ~2 months | Healthcare | 2007-2018 | **-29.7%** | XLV +151.5% |

Strategies 1-5 trade within the day and use 5-minute bars. Strategies 6-8 hold for days
to months and use 20 years of daily bars. Where a strategy failed its first stage, the
second was not run, as its rules required.

Details: `docs/BACKTEST_RESULTS.md` (1-2), `bots/healthcare/RULES.md` (3),
`bots/healthcare/MOMENTUM_RULES.md` (4-5), `bots/swing/RULES.md` (6),
`bots/mining_overnight/RULES.md` (7), `bots/healthcare_news/RULES.md` (8).

## What was learned

1. **Costs decide intraday trading on a small account.** IBKR Pro Fixed commission
   costs about $2 per round trip. Intraday trades on $1,250-2,500 positions made cents
   to a few dollars each before costs. Commission turned every intraday strategy from
   roughly flat to clearly negative.
2. **Early backtests were too optimistic, and fixing them mattered.** Two problems
   inflated the original bot's results: stops and targets were assumed filled at exact
   levels that 1-minute data showed were not achievable (gross overstated by 60-92%),
   and partial sales were booked at the wrong price. After the fixes, the bot that had
   looked profitable was not.
3. **The big gains come on a few days.** The stocks that rose 25%+ made almost all of
   it on about five days each, often news days. The intraday bots were built in ways
   that missed exactly those days: they were in and out within minutes, skipped news
   days, avoided "extended" stocks, spent the day's cash early, and (for mining)
   excluded stocks under $10.
4. **Mining stocks rise overnight and fall during the day, and have for 20 years:**
   +20% to +52% a year overnight against -15% to -29% during trading hours, in every
   period since 2007. A bot that is flat every night trades only the half of the day
   that loses. Healthcare has no such pattern.
5. **Knowing what happened is not the same as predicting it.** Buying after the signs
   of a winner (a 25% run, a breakout, a news jump) did not reliably catch the next one.
   The healthcare swing bot worked well from 2007 to 2018 and then lost money from 2019
   on.
6. **Holding the sector ETF beat every bot.** That says nothing about future returns,
   and whether it suits any particular person is a matter for that person or a licensed
   adviser. It is still the benchmark any future strategy has to beat.

## What was built (all in this repository)

- **Mining intraday bot** (`src/`, `config/`), with an IBKR **paper-only** connection.
  Safety checks refuse anything but a paper account (ID starting "DU") on this computer.
  Orders are verified fills that never rest unwatched. The price feed detects delayed
  data, reconnects automatically if Trader Workstation drops, and does not trade symbols
  still on delayed data.
- **Backtesters** for 5-minute and daily data with realistic fills, settled-cash rules
  and IBKR Fixed commission; 535 automated tests.
- **Data:** 5-minute bars for the mining and healthcare stocks, and 20 years of daily
  bars for all 91 symbols (`data_cache/`).
- **Daily replay** of each session (`scripts/daily_replay.py`, `docs/DAILY_REPLAY_LOG.md`).
- **The analyses:** `docs/WHY_MINING_MOVERS_WERE_MISSED.md`,
  `bots/healthcare/WHY_MOVERS_WERE_MISSED.md`.

## Loose ends

- **Rotate the Twelve Data API key.** It was exposed in this conversation earlier, so a
  new one should be generated on twelvedata.com and put in `.env` on the Mac. It has
  never been committed to the repository, which is public.
- **Paper account DUT160852** stands at about $4,938 of the original $5,000, with no
  open positions. The largest single cost was an AG position held overnight after the
  bot was restarted and lost track of it (-$47). If the paper bot is run again, it should
  either never hold overnight or save its positions between runs.
- **Live prices on the paper account** are blocked by IBKR's *Market Data API
  Acknowledgement*, which has not been signed (Client Portal, Settings, Market Data
  Subscriptions). The free package is also non-consolidated: real-time prices from a few
  exchanges, with only part of the market's volume.
- **The healthcare intraday holdout** (2026-04-01 to 2026-09-29, 5-minute bars) has never
  been used by any strategy. It is still available for a fair test of a future intraday
  healthcare idea.
- Nothing here is investment advice, and none of these bots should trade real money.

## If this is picked up again

Keep the same discipline:
- Write the rules and the pass/fail test before running anything.
- Include costs.
- Decide on data the rules were not built on.
- Paper-trade anything that passes before real money.
- Change one thing at a time, and remember that every extra variant tried raises the
  chance of finding one that looks good by luck.

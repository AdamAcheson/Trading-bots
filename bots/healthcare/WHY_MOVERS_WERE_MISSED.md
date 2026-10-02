# Why the healthcare bot missed the stocks that rose 25%+ (2026-10-02)

Period: 2025-04-29 to 2026-03-31, stage 1 only (the holdout stays unseen). Bot: the
momentum bot of `MOMENTUM_RULES.md`, original rules (tag `hcm_s1`). Scripts that produced
these numbers were run from the session scratchpad; the trace option they use is
`scripts/backtest_healthcare_momentum.py run(..., trace=...)`.

## The movers

14 of the 60 stocks rose 25% or more: MRNA +85%, VTRS +63%, ILMN +60%, INCY +58%,
JNJ +57%, BIIB +54%, CAH +53%, CRL +50%, MRK +45%, HCA +42%, GILD +31%, IDXX +29%,
REGN +26%, BMY +25%.

- **A handful of days made the move.** Each stock's 5 best days add up to 96% of its
  whole rise; the other ~225 days together came to roughly nothing. Those best days
  averaged +7.9% each.
- Several fall in earnings season (for example JNJ 2025-07-16, INCY 2025-07-29, ILMN
  2025-10-31), consistent with earnings or other news. Price data alone cannot confirm
  the cause.
- On those big days, a median 46% of the day's move had already happened by 09:45, 58% by
  10:30 and 90% by 14:30.
- Over the year, overnight gaps added little net (2%); the rise came during trading
  hours.

## What the bot did

- 222 trades in the 14 movers: gross -$83.93, net -$528.64. The other 46 stocks: 586
  trades, net -$1,067.85.
- On the movers' 70 best days the bot traded **2**, making $4.38 (REGN, +5.0% day) and
  $7.81 (HCA, +4.9% day).

Why the 70 best days were missed:

| Reason | Days |
|---|---|
| The stock qualified, but the day's $5,000 of settled cash was already spent on other stocks (mostly bought at 09:45 and stopped out within minutes) | 43 |
| Opened with a 4%+ gap, so the "no binary event" stand-in skipped it all day | 14 |
| Never scored 75 inside 09:45-14:30 | 11 |
| Traded | 2 |

On those days' bars in the entry window, the conditions most often failing were MACD
above signal (58%), RSI inside 52-68 (53%; strong days run above 68), XLV bullish (44%),
volume (33%) and entry quality (31%).

## What it means

The money in these stocks was made by **holding them through a few big days**, often
news days, over weeks and months. The bot is built to do the opposite: it is in and out
within 10-25 minutes, it skips news days, its RSI and entry-quality limits avoid the
strongest bars, and it spends the day's cash in the first minutes on whatever qualifies
first. Even a perfect capture of an average big day on a $1,250 position would be about
$99, and nobody knows in advance which day that will be.

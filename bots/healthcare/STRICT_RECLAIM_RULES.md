# Healthcare: the stricter VWAP reclaim (pre-registered)

Locked 2026-10-03 at the account holder's request ("test this strategy on our healthcare
stocks"), before any healthcare run with the stricter reclaim. Nothing below changes after
results are seen; a change means a new, dated version.

## 1. What is tested

The healthcare intraday bot exactly as tested on 2026-09-30 in variant **H1**
(`bots/healthcare/config`: the 60 stocks, XLV benchmark, fixed 2.25% target, 0.5% stop
floor, the 4% gap-day skip and the 5-share minimum; see `bots/healthcare/RULES.md`), with one
change: the **stricter VWAP reclaim** of `docs/PREREG_STRICT_RECLAIM.md`, unchanged:

1. a 1-4 bar dip: 1 to 4 consecutive 5-minute closes at or below VWAP, after a close above it;
2. the reclaim bar (first close back above VWAP) trades above the average volume of the
   same clock-time bar over the previous 20 sessions (at least 5 needed);
3. entry no more than 0.5 x ATR(14) above VWAP.

Costs: IBKR Pro **Fixed** commission on every order, the modelled one-cent spread, and
realistic resting-order exits, as in every test since 2026-09-30.

The "normal volume" history is built from the sessions inside each run, so the first 5
sessions of each stage cannot produce a signal, and sessions 6-20 use fewer than 20
sessions of history. This is the same as in the mining test.

## 2. Periods (as in `bots/healthcare/RULES.md`)

- **Stage 1:** 2025-04-29 to 2026-03-31 (232 sessions; the period the H variants used).
  `python3 scripts/backtest.py --config-dir bots/healthcare/config --start-date 2025-04-29
  --end-date 2026-03-31 --strict-reclaim --tag hcsr_s1`
- **Stage 2 (run once, only if stage 1 passes):** 2026-04-01 to 2026-09-29, the
  healthcare 5-minute data no strategy has ever been run on.
  `... --start-date 2026-04-01 --end-date 2026-09-29 --strict-reclaim --tag hcsr_s2`

## 3. Pass rules

**Stage 1:** net profit after Fixed commission must be **above zero**. If not, testing
stops and the stage 2 data stays unseen.

**Stage 2 (deciding), as `bots/healthcare/RULES.md` section 6:**
- **PASS** if the per-session net after commission is above zero **and** the 90% lower
  bound of a block bootstrap of the daily results (blocks of 5 days, 5,000 resamples,
  seed 7) is above zero.
- **INCONCLUSIVE** if stage 2 has fewer than 30 trades.
- **FAIL** otherwise.

A pass allows paper trading only, not real money.

Reported for context, not part of the decision: trades, win rate, average win and loss,
commission, which of the three conditions rejected the most signals, buying and holding
XLV over the same dates, and H1's stage 1 result (-$709.93 after Fixed commission).

## 4. Known limits, stated before any run

- **The stricter reclaim failed on the mining stocks** the same day
  (`docs/PREREG_STRICT_RECLAIM.md`): it cut trading by over 90% and lost money per trade
  over 2023-2025. This test asks whether healthcare behaves differently.
- **Few trades are likely.** On 29 mining stocks it took 42 trades in 2.3 years. Even with
  60 stocks, six months of stage 2 may fall short of 30 trades, which makes the result
  inconclusive by rule.
- **Stage 1 has been used before** (six H variants and the momentum bot). Stage 2 has not.
  Once stage 2 is run, no healthcare 5-minute data is left unseen for a later idea.
- **Healthcare rallied over the stage 2 months** (XLV +19.5% from 2026-03-27 to
  2026-09-28), a tailwind for a long-only bot that may not last.

## Result, stage 1 (2026-10-03): FAIL -- testing stopped; stage 2 not run

`python3 scripts/compare_runs.py --first 2025-04-29 --last 2026-03-31 hcsr_s1`, 232 sessions:

| | |
|---|---|
| Trades | 58 (win rate 41%; average win +$11.84, average loss -$13.73 net) |
| Before commission (spread included) | -$57.41 |
| Commission (Fixed) | $125.26 |
| **After commission** | **-$182.66** (-$0.79 per session) |
| Exits | 28 stops, 16 trailing stops, 13 at 3:50 PM, 1 target |
| For context: H1, same period, today's reclaim | -$709.93 after Fixed commission (367 trades) |
| For context: buying and holding XLV | +5.3% (about +$263 on $5,000) |

Signals turned away by the stricter reclaim, by condition: dip longer than 4 bars 1,651;
too far above VWAP 1,185; reclaim volume not above normal 973; too little volume history
37 (counted per 5-minute evaluation, so one setup can count several times).

As on the mining stocks, the stricter reclaim cut trading by about 85% (58 trades against
H1's 367) and the trades it kept lost money before commission. The smaller loss than H1
comes from trading less. Under section 3, stage 1 must be profitable, so **stage 2
(2026-04-01 to 2026-09-29) was not run and the healthcare 5-minute data for those months
stays unseen**.

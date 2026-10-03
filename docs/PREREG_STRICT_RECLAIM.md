# Pre-registration: a stricter VWAP reclaim (mining intraday bot)

Locked 2026-10-03 at the account holder's request, before the rule was coded or run.
Nothing below changes after results are seen; a change means a new, dated version.

## The idea (account holder's words)

"Make the VWAP reclaim stricter. Instead of buying any stock that dips below VWAP and gets
back above it within six bars, require a stronger reclaim: close back above VWAP within
about 1-4 bars, on above-normal volume, and not too far above VWAP."

## Today's reclaim (unchanged, and still required)

Within the last 6 five-minute bars: a close at or below VWAP; then a close back above VWAP
on more volume than the bar before; the next bar's low holds VWAP; and the latest bar is
green. The bot buys at the latest bar's close.

## The stricter reclaim (all three must also hold)

Setting `setups.strict_vwap_reclaim.enabled: true` (backtest flag `--strict-reclaim`):

1. **A quick dip, 1-4 bars.** Count the consecutive 5-minute closes at or below VWAP that
   end at the last such close before the reclaim. There must be **1 to 4** of them, and the
   close just before the dip must have been **above** VWAP. A stock that spent five or more
   bars below VWAP, or that had not been above VWAP before the dip, does not qualify.
2. **Above-normal volume on the reclaim.** The reclaim bar is the first close back above
   VWAP after the dip. Its volume must be **above the average volume of the same
   5-minute bar (same clock time) over the previous 20 sessions**. Comparing with the same
   time of day is what makes it "normal": volume is far heavier near the open and close
   than at midday. At least 5 previous sessions are needed; with fewer, the signal is
   skipped.
3. **Not too far above VWAP.** At the entry (the latest bar's close), price is **no more
   than 0.5 x ATR(14) above VWAP**. (Today's chase rule allows up to 3 x ATR.)

A signal failing any of them is rejected as `REJECTED_NO_SETUP`.

Everything else is unchanged: the score, the benchmark check, sizing ($2,500 x 2, settled
cash), stops, the target, breakeven, the 35% partial at 1.5R, trailing, the 3:50 PM exit,
realistic resting-order exits and IBKR Pro Fixed commission. The rejected EMA, RSI and $15
rules are not included.

## Runs

Same windows and commands as before:
- **Holdout:** `--first-days 568` (2023-09-05 to 2025-12-08).
- **Tuning:** `--days 193 --end-offset 5` (2025-12-15 to 2026-09-22).
- Baseline: the shipped configuration on the current code, run on 2026-10-03 (tags
  `pf_base_h`, `pf_base_t`; holdout -$1,172.30, tuning -$135.92 after commission). The
  stricter reclaim: tags `sr_h`, `sr_t`.

## Pass rule (as for the last three tests)

**Adopted** (shipped for paper trading) only if all three hold:
1. Net profit after Fixed commission is **positive in both periods**.
2. **Holdout:** the paired daily difference against the baseline has a 95% block-bootstrap
   interval (block 5, 5,000 resamples, seed 7, `scripts/compare_runs.py`) **entirely above
   zero**.
3. **Tuning:** the paired mean daily difference is **positive**.

Otherwise **rejected**, and the shipped configuration is unchanged. A pass does not justify
real money by itself; it allows paper trading.

Reported for context: trades, win rate, average win and loss after costs, commission, how
the baseline trades the stricter rule blocked had done, and how the new trades in freed
slots did.

## Known limits, stated before any run

- The numbers 4 bars, 20 sessions, "above average" and 0.5 x ATR were fixed here from the
  account holder's wording, without trying others.
- A related idea, reclaims that also clear a range high on elevated volume, was rejected
  on 2026-09-23.
- The last two filters (EMA, RSI) lost money mostly through what they did with freed slots
  and cash: other signals took them and did worse. A stricter setup may do the same.
- Both periods have been used for 34 earlier rule tests.
- Removing trades also removes commission; the pass rule requires a profit after
  commission, not just a smaller loss.

# Pre-registration: 9/20 EMA trend filter on the VWAP reclaim (mining intraday bot)

Locked 2026-10-03 at the account holder's request, before the filter was coded or run.
Nothing below changes after results are seen; a change means a new, dated version.

## The idea (account holder's words)

"Only take a VWAP reclaim trade when the stock is also above the 9 EMA and the 9 EMA is
above the 20 EMA. In plain English: only buy the VWAP reclaim when the short-term trend
is already pointing up."

## The rule (one change; everything else as shipped)

Setting `eligibility.require_ema_trend: true` (backtest flag `--ema-trend-filter`):
a VWAP reclaim signal is taken only if, at the 5-minute bar where it fires,
1. the stock's price is **above its 9 EMA**, and
2. the **9 EMA is above the 20 EMA**.

Otherwise the signal is rejected (`REJECTED_EMA_TREND`).

**How the EMAs are calculated:** on the stock's 5-minute closes, **carried over from
previous sessions** (regular hours), the way a trading chart shows them, using the last
200 bars. The bot's existing EMAs restart every morning, so its 20 EMA is not ready until
about 11:10; a filter on those would block every entry before then for a reason that has
nothing to do with trend. The carried EMAs are ready from the first bar.

Unchanged: everything else, including entries, the setup score, sizing ($2,500 x 2,
settled cash), stops, the target, breakeven, the 35% partial at 1.5R, trailing, the 3:50 PM
exit, realistic resting-order exits and IBKR Pro Fixed commission.

## Runs

Same windows and commands as before:
- **Holdout:** `--first-days 568` (2023-09-05 to 2025-12-08).
- **Tuning:** `--days 193 --end-offset 5` (2025-12-15 to 2026-09-22).
- Baseline: the shipped configuration on the current code, already run on 2026-10-03 (tags
  `pf_base_h`, `pf_base_t`; holdout -$1,172.30, tuning -$135.92 after commission). The
  filter: tags `ema_h`, `ema_t`.

## Pass rule (as for the profit-floor test)

**Adopted** (shipped for paper trading) only if all three hold:
1. Net profit after Fixed commission is **positive in both periods**.
2. **Holdout:** the paired daily difference against the baseline has a 95% block-bootstrap
   interval (block 5, 5,000 resamples, seed 7, `scripts/compare_runs.py`) **entirely above
   zero**.
3. **Tuning:** the paired mean daily difference is **positive**.

Otherwise **rejected**, and the shipped configuration is unchanged. A pass does not justify
real money by itself; it allows paper trading.

Reported for context: trades, signals rejected by the filter, win rate, average win and
loss after costs, commission, exits by reason, largest drawdown.

## Known limits, stated before any run

- **Partly seen before.** The setup score already gives up to 10 points for these same two
  conditions (on the restart-every-morning EMAs). On 2026-09-22 that score component was
  linked to better trades in the holdout (rank correlation +0.12, t=3.81) but not in the
  tuning period (+0.04, t=0.94). The holdout may therefore flatter this filter; the tuning
  period is the more independent check.
- Both periods have been used for 32 earlier rule tests.
- Removing trades also removes commission. The pass rule requires a profit after
  commission, not just a smaller loss.

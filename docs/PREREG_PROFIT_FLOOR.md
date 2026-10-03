# Pre-registration: "never take a profit under $15 net" (mining intraday bot)

Locked 2026-10-03 at the account holder's request, before the rule was coded or run.
Nothing below changes after results are seen; a change means a new, dated version.

## Why

On the realistic-exit, Fixed-commission baseline (`docs/BACKTEST_RESULTS.md`, 2026-09-30),
the average trade made $1.59 before costs and paid $1.08 in modelled spread and $2.26 in
commission. 155 of 672 holdout trades were sold for a gain of under $15 before costs,
mostly through the 35% partial sale at 1.5R (about a $7 profit) and the breakeven and
trailing stops. The account holder's view: selling a winner for less than $15 after
commission does not make sense. 108 holdout trades were up at least $15 at some point
and were sold for less.

## The rule (one change package; everything else as shipped)

Setting `trade_management.profit_floor_net_dollars: 15` (backtest flag
`--profit-floor-net 15`):

1. **No partial sale.** The 35% sale at 1.5R is off (it sells for well under $15).
2. **No move to breakeven, and no trailing stop, until the floor is reached.** The
   original stop stays in place.
3. **The floor:** the lock price L is the price at which selling all the shares would
   leave **$15 net profit after commission and the modelled bid/ask cost** (the trade's
   `net_profit` as the journal books it). When a 5-minute bar closes at or above L, the
   stop moves up to L.
4. **After the lock** the existing trailing stop (1 x ATR under the high-water mark)
   applies, never below L.
5. Unchanged: entries, sizing ($2,500 x 2, settled cash), the initial stop and target,
   the 3:50 PM exit, realistic resting-order exits (a stop fills at the stop, or at the
   bar's open if the bar opened through it), IBKR Pro Fixed commission.

A trade can still close under +$15 net: at the original stop (a loss), at the 3:50 PM
exit, or when a bar opens below L (a gap through the stop).

## Runs

Same windows and commands as the baseline:
- **Holdout:** `--first-days 568` (2023-09-05 to 2025-12-08).
- **Tuning:** `--days 193 --end-offset 5` (2025-12-15 to 2026-09-22).
- Baseline: the shipped configuration, re-run on the current code (tags `pf_base_h`,
  `pf_base_t`); the rule: tags `pf15_h`, `pf15_t`.

## Pass rule

**Adopted** (shipped for paper trading) only if all three hold:
1. Net profit after Fixed commission is **positive in both periods**.
2. **Holdout:** the paired daily difference against the baseline has a 95% block-bootstrap
   interval (block 5, 5,000 resamples, seed 7, `scripts/compare_runs.py`) **entirely above
   zero**.
3. **Tuning:** the paired mean daily difference is **positive**.

Otherwise **rejected**, and the shipped configuration is unchanged. A pass does not justify
real money by itself; it allows paper trading.

Reported for context: trades, win rate, average win and loss after costs, exits by reason,
how many trades closed with a gain under $15 net and why, and largest drawdown.

## Known limits, stated before any run

- Both periods have been used many times before (31 earlier rule tests), so even a pass
  is weaker evidence than a pass on unseen data.
- Similar exit changes were tested on 2026-09-29 (partial off, trailing off, wider
  trailing). None was confirmed on the holdout.
- The lock is checked on 5-minute closes, as the shipped breakeven and trailing are; the
  live bot checks about every 30 seconds.

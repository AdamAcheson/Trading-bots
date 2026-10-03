# Pre-registration: RSI 52-70 band on the VWAP reclaim (mining intraday bot)

Locked 2026-10-03 at the account holder's request, before the filter was coded or run.
Nothing below changes after results are seen; a change means a new, dated version.

## The idea (account holder's words)

"Add RSI to avoid weak or overextended trades. Test only taking trades when RSI is
roughly 52-70."

Below 52, momentum is weak; above 70, the stock is overextended.

## The rule (one change; everything else as shipped)

Setting `eligibility.rsi_band: [52, 70]` (backtest flag `--rsi-band 52 70`): a VWAP
reclaim signal is taken only if, at the 5-minute bar where it fires, the stock's
**RSI(14) is at least 52 and at most 70**. Otherwise the signal is rejected
(`REJECTED_RSI_BAND`).

**How RSI is calculated:** Wilder's RSI over 14 periods (the standard chart setting) on
the stock's 5-minute closes, **carried over from previous sessions** (regular hours), as
a chart shows it, using the last 200 bars. This is the same treatment as the EMA test, so
the filter works from the first entry window.

The 9/20 EMA filter is **not** included (it was rejected; `docs/PREREG_EMA_TREND.md`).
Everything else is unchanged: entries, the setup score, sizing ($2,500 x 2, settled cash),
stops, the target, breakeven, the 35% partial at 1.5R, trailing, the 3:50 PM exit,
realistic resting-order exits and IBKR Pro Fixed commission.

## Runs

Same windows and commands as before:
- **Holdout:** `--first-days 568` (2023-09-05 to 2025-12-08).
- **Tuning:** `--days 193 --end-offset 5` (2025-12-15 to 2026-09-22).
- Baseline: the shipped configuration on the current code, run on 2026-10-03 (tags
  `pf_base_h`, `pf_base_t`; holdout -$1,172.30, tuning -$135.92 after commission). The
  filter: tags `rsi_h`, `rsi_t`.

## Pass rule (as for the last two tests)

**Adopted** (shipped for paper trading) only if all three hold:
1. Net profit after Fixed commission is **positive in both periods**.
2. **Holdout:** the paired daily difference against the baseline has a 95% block-bootstrap
   interval (block 5, 5,000 resamples, seed 7, `scripts/compare_runs.py`) **entirely above
   zero**.
3. **Tuning:** the paired mean daily difference is **positive**.

Otherwise **rejected**, and the shipped configuration is unchanged. A pass does not justify
real money by itself; it allows paper trading.

Reported for context: trades, win rate, average win and loss after costs, commission, how
many baseline trades the filter blocked (split into RSI below 52 and above 70) and how
those trades had done.

## Known limits, stated before any run

- **Partly seen before.** On 2026-09-22, 5-minute RSI(14) at entry was measured on the
  holdout trades of that time (old exit model, 1,001 trades) and showed no link to
  outcomes (rank correlation +0.009 with R). A band filter was not tested then.
- The day before this test, the EMA filter showed that blocking reclaims made in a
  short-term downtrend removed slightly better trades. A reclaim with RSI below 52 is often
  such a trade, so the result may go the same way. The rule was fixed at the account
  holder's 52-70 regardless.
- Both periods have been used for 33 earlier rule tests.
- Removing trades also removes commission; the pass rule requires a profit after
  commission, not just a smaller loss.

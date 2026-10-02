# Why the mining bot missed the stocks that rose 25%+ (2026-10-02)

The same analysis as `bots/healthcare/WHY_MOVERS_WERE_MISSED.md`, for the mining bot as
shipped (realistic exits, IBKR Pro Fixed commission): journals `fixed_t`
(2025-12-15..2026-09-22) and `fixed_h` (2023-09-05..2025-12-08). "Best days" are each
mover's 5 largest close-to-close gains in the period.

## Recent period, 2025-12-15 to 2026-09-22

- 12 of 29 stocks rose 25%+: AUGO +99%, SSRM +72%, FCX +57%, SVM +52%, SCCO +49%,
  HBM +49%, BHP +47%, CMP +37%, WPM +31%, RIO +29%, AG +27%, FSM +25%.
- Each mover's 5 best days equal 113% of its whole rise (the other days lost money in
  total). Best days averaged +9.0%; 30 of the 60 opened 4%+ higher; by 09:45 a median
  66% of the day's move had happened.
- Equal-weight buy and hold of all 29: +19% (+$941 on $5,000). The bot: -$186.73.
- Bot in the movers: 123 trades, gross +$216.50, net -$144.63.
- The 60 best days: 5 traded (gross $6-66 each, on ~$2,500 positions, all ended by the
  trailing stop); 12 rejected for low volume; 11 qualified but no slot or settled cash
  was left; 10 overextended (the chase rule); 10 below VWAP; 9 no setup; 3 benchmark.

## Earlier period, 2023-09-05 to 2025-12-08

- 17 of the 21 stocks with data rose 25%+, most of them by multiples: PPTA +684%,
  CDE +564%, VZLA +398%, HMY +363%, HL +281%, GFI +236%, FSM +225%, EXK +224%,
  SVM +221%, DRD +198%, SIL +197%, UEC +194%, EQX +189%, MP +185%, AG +158%, SCCO +89%,
  SSRM +46%.
- Equal-weight buy and hold: +212% (+$10,611 on $5,000). The bot: -$1,172.30.
- The 85 best days: 2 traded. 48 were rejected by the $10 minimum price (the tick-cost
  screen): most of these stocks were under $10 when their run began. 14 overextended;
  5 qualified but no slot or cash; the rest scattered.

## Overnight against intraday

Average per stock, holding only from close to next open versus only from open to close
(costs ignored):

| | Overnight only | Day only | Buy and hold |
|---|---|---|---|
| Mining, 2025-12-15..2026-09-22 | +40% | -13% | +19% |
| Mining, 2023-09-05..2025-12-08 | +391% | -8% | +212% |
| Healthcare, 2025-04-29..2026-03-31 | -7% | +16% | +8% |

In mining, the whole rise in both periods came while the market was closed; during
trading hours the stocks lost ground on average. A bot that is flat every night can only
fish in the part of the day that lost money. Healthcare is the reverse, but its moves sit
in a few news days that the healthcare bot avoided.

# CoinDCX Paper Bot V3 PRECISION

V3 is a clean precision-entry rebuild on the working V2 market-data, universe,
liquidity, FX, paper execution, risk and journal foundation.

## What changed

V2 could enter a high-score setup during chop. V3 makes score secondary.
A trade cannot open unless every hard gate passes:

1. 1H and 15M trend alignment.
2. EMA separation and slope.
3. 15M HH-HL for LONG or LH-LL for SHORT.
4. 5M consolidation/chop rejection.
5. Clean impulse of at least 2.2 ATR.
6. Pullback into the Fibonacci 38.2%-61.8% zone.
7. RSI used only as momentum context.
8. Completed 5M rejection, engulfing, or liquidity-sweep candle.
9. Stop distance quality check.
10. At least 1.8R room to recent structure.
11. Precision score at least 78.
12. NO ENTRY YET: setup becomes ARMED.
13. Bot watches only the armed setup every 2 seconds.
14. Entry occurs only when live price breaks the confirmation candle trigger.
15. No chasing if price is already too far through the trigger.

## Lifecycle

SCAN -> ARMED -> CONFIRMATION BREAK -> ENTERED -> BE_PROTECTED -> TRAILING -> EXITED

While ARMED, broad scanning pauses for up to 10 minutes.
While ENTERED, all broad scanning pauses and the single position is monitored every 2 seconds.

## Exit reporting

The terminal explicitly prints INITIAL_SL, BREAKEVEN_SL, TRAILING_SL, or REVERSAL_OVERRIDE,
plus entry, exit, price difference, modeled fees/cost, net P&L, final R, MFE and MAE.

## Important

Paper trading only. Do not enable live orders from this build.
Do not change thresholds during the first evaluation sample except to fix a coding/API bug.
Review at 10 trades, 25 trades, and 50 trades.

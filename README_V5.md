# CoinDCX V5.1 Adaptive Paper Agent

PAPER ONLY. No credentials and no order placement.

V5.1 fixes:
- Live/fallback-aware USDT-INR is used by the actual V5 sizing and P&L execution path.
- Idle scanning is two-stage: bounded-parallel lightweight 5m prefilter, then full 5m/15m/1h + fresh order-book strategy verification only for the top shortlist.
- The prefilter can never arm a trade. Every entry still requires the complete V4.1 confluence strategy and independent cross-verification.
- Learning outcome resolution is removed from the critical scan path and runs as deferred idle work.
- One active trade maximum; scanning stops while ARMED/LIVE and monitoring remains frequent.
- Persistent adaptive memory remains bounded to +/-5 ranking points and cannot bypass hard strategy gates.

Run RUN_V5_AGENT.bat.
Preserve v5_memory.sqlite3 across restarts.


## V5.2 progressive deep verification
The 5m fast prefilter ranks candidates only. Deep verification runs in batches of 12 and continues beyond the first batch until a candidate survives the full strategy plus independent cross-verification, or every fast-qualified candidate is checked. One-trade-at-a-time and paper-only behavior are unchanged.

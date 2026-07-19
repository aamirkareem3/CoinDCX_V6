V4.1 PRECISION-CONFLUENCE REWORK

Reason:
Observed runtime bottleneck showed nearly all candidates dying at hard sequential gates before confirmation.

Strategy change:
- 15m directional trend remains mandatory.
- Strong opposing 1h trend remains a veto; aligned 1h scores higher and neutral 1h is allowed.
- Market structure is confluence-scored instead of an absolute veto.
- Severe chop still rejects; marginal regime readings reduce score.
- Recent directional impulse remains mandatory; threshold 1.6 ATR, max age 24 bars.
- Pullback must preserve impulse origin; broad context 15%-85%, ideal 25%-75% scores higher.
- Closed price-action confirmation remains mandatory.
- Structural stop quality, spread, >=1.8 net R and confluence score >=80 remain mandatory.
- Structural target preferred; 2.4R fallback only when no confirmed target is available.
- Existing ARMED live revalidation, one-live-trade-only, 2-second live management, BE/trailing, persistence and duplicate locks preserved.

No live-order execution. Paper only.

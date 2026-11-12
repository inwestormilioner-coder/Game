# CRT + TBS SMC Sniper EA PRO (MetaTrader 5)

File: `CRT_TBS_SMC_Sniper_EA_PRO.mq5`. It is native MQL5, uses only the standard `Trade\Trade.mqh` library and needs no DLLs.

> **Compilation status:** this source has **not** been compiled in MetaEditor yet. The development environment had no MetaEditor or MT5 terminal. The code was checked statically: brackets balance, every function it calls is defined, and the MQL5 API signatures were reviewed by hand. Compile it in MetaEditor (F7) before use. If MetaEditor reports anything, send the error lines and they will be fixed.

---

## 1. Architecture

```
            ┌────────────────────────────────────────────────────────────┐
  H1        │ CRT RANGE  – previous closed candle / 2 / 3 candles /      │
            │              previous session  → High, Low, 50%            │
            └───────────────┬────────────────────────────────────────────┘
                            ▼
  M15       │ LIQUIDITY MAP – confirmed swing H/L (fractal depth N),     │
            │  equal highs/lows, previous day H/L, previous session H/L, │
            │  filtered to pools near the CRT range, untaken only        │
                            ▼
  M5        │ TURTLE SOUP – fresh breach of CRT Low/High or a pool by    │
            │  ≥ min distance → reclaim close back inside (same candle   │
            │  or ≤ N candles). Genuine breakout filter (close far       │
            │  beyond / N consecutive closes / sweep too deep)           │
                            ▼
  M1        │ MSS – close beyond the last confirmed swing that led into  │
            │  the sweep  + DISPLACEMENT candle (body ≥ x ATR, ratio)    │
            │  → FVG (3-candle, mitigation tracked) / ORDER BLOCK        │
            │  (last opposite candle before displacement, mitigation)    │
                            ▼
  EXEC      │ Score ≥ min, mandatory checks, risk gate → market or limit │
            │ (FVG 50% / OB / discount) with expiry, SL beyond sweep     │
            │ extreme, TP mode, lot from real tick value                 │
                            ▼
  MANAGE    │ partials TP1/TP2, break-even, trailing (points/ATR),       │
            │ max hold time, close on structural invalidation            │
```

### Setup state machine (one machine per direction, BUY and SELL)

| State | Meaning / transition |
|---|---|
| `WAITING_FOR_RANGE` | No valid CRT range yet. Range size fails the filter or data is not loaded. |
| `RANGE_IDENTIFIED` | A new valid range was created. The machine moves on to the next state at once. |
| `WAITING_FOR_LIQUIDITY_SWEEP` | Each new M5 close is checked for a fresh breach of an eligible level. |
| `SWEEP_DETECTED` | A level was breached. The level is marked *used*, so it can never create a second setup in this range. |
| `WAITING_FOR_RECLAIM` | The sweep candle closed beyond the level. The EA waits up to `InpReclaimMaxBars` M5 candles. |
| `RECLAIM_CONFIRMED` | An M5 candle closed back inside. The exact M1 bar of the sweep extreme is located. |
| `WAITING_FOR_MSS` | Each new M1 close is checked for a close beyond the MSS swing. |
| `MSS_CONFIRMED` | Structure shifted. Displacement is checked. |
| `WAITING_FOR_ENTRY` | FVG, OB, retest and score are confirmed, or a pending order is live. |
| `TRADE_OPEN` | A position is open for this setup. |
| `SETUP_COMPLETED` | The trade closed, or a signal was produced in signal-only mode. |
| `SETUP_INVALIDATED` | The setup failed. The reason is logged and shown on the dashboard. |

A setup resets only in four cases:
- a new reference range starts (with the optional carry-over, `InpCarryActiveSetup`);
- the setup expires;
- the setup is invalidated;
- the trade completes.

Duplicate entries are blocked at several levels:
- **Level:** a swept level is used only once per range.
- **Setup:** a single setup cannot place more than `InpMaxTradesPerSetup` trades.
- **Bar:** at most one order per M1 bar.
- **Comment:** each order comment carries the setup id. The EA checks it before sending an order.
- **Tick:** all signal logic runs once per *closed* M1 bar, never on every tick.

---

## 2. Exact entry logic

### BUY (SELL is the mirror)
1. **Valid CRT range.** Its size must be between `InpCRTMinRange` and `InpCRTMaxRange`.
2. **Sweep.** The last closed M5 candle has a low ≤ level − breach. The level is CRT Low, or an untaken M15 low or pool when `InpSweepSource` allows it. Further requirements:
   - The previous M5 candle closed above the level and did not breach it, so the sweep is fresh.
   - With `InpCRTRequireBias`, the level is in the discount half of the CRT range (≤ 50%).
   - The sweep is not deeper than `InpSweepMaxDepthATR` × ATR(M5). A deeper move is treated as a breakout.
   - If several levels are taken at once, the deepest one is used.
3. **Reclaim.** An M5 candle closes ≥ level + `InpReclaimMinClose`, either the sweep candle itself (it then also needs a rejection wick ≥ `InpMinRejectWick`) or one of the next `InpReclaimMaxBars` candles. The setup is invalidated as a **genuine breakout** in either case:
   - an M5 close lands more than `InpBreakoutCloseATR` × ATR beyond the level;
   - `InpBreakoutBars` consecutive M5 closes stay beyond the level.
4. **M1 MSS.** The swing is chosen by `InpMSSSwingMode`:
   - *Strict mode (default):* the EA takes the last confirmed M1 swing high (fractal depth `InpMSSSwingDepth`) that formed **before** the sweep extreme and was not broken before it. An M1 candle must then **close** above it by ≥ `InpMSSMinBreak`. Wicks never count.
   - *Loose mode:* the most recent unbroken confirmed swing high is used instead.
5. **Displacement.** A bullish candle between the MSS candle and the `InpDispLookback` candles before it has:
   - body ≥ `InpDispATRMult` × ATR(M1);
   - body / range ≥ `InpDispBodyRatio`;
   - body ≥ `InpDispMinBody` (optional).
6. **FVG / OB.** These are detected only from closed candles after the sweep extreme.
   - *FVG:* a bullish gap where candle1.high < candle3.low. Its status is tracked as FRESH, PARTIAL or FILLED. A FILLED FVG is rejected and the freshest valid one is preferred.
   - *OB:* the last bearish candle before the displacement candle. It must sit between the sweep extreme and the MSS level. If a later candle closes below it, the OB is invalid. A touch counts as mitigated. A touch followed by a close above counts as a retest.
   - Each one can be made mandatory with `InpRequireFVG` / `InpRequireOB`. For the market model, `InpOBRetestRequired` waits for the retest before entering.
7. **Score and gate.**
   - The score must be ≥ `InpMinScore`.
   - Spread, session, no-trade window, news blackout, daily limits, max positions, max trades per day and netting conflict must all pass.
   - The *gate* filters are soft. They are retried each M1 bar until `InpConfirmWaitBars` runs out.

**Mandatory conditions are never replaced by the score:** sweep, reclaim and MSS must always happen. Displacement, FVG and OB are mandatory when their flags are on.

### Entry methods (`InpEntryMode`)
- `ENTRY_MARKET`: market order on the M1 close that completes the model. The MSS must be no older than `InpMSSMaxAgeMarket` bars, so the EA does not chase.
- `ENTRY_LIMIT_FVG`: limit order at FVG level `InpFVGEntryLevel`, where 0.5 is the midpoint.
- `ENTRY_LIMIT_OB`: limit order at OB level `InpOBEntryLevel`, where 0.5 is the midpoint.
- `ENTRY_LIMIT_DISCOUNT`: limit order at `InpDiscountLevel` retracement of the leg from the sweep extreme to the leg high.
- If the limit price has already been traded through, or is inside the stops level, the EA either enters at market (`InpFallbackToMarket`) or waits or invalidates.

A pending order is cancelled in any of these cases:
- its expiry (`InpPendingExpiryMin`) passes. Broker-side expiry is used when supported, and the EA also checks it itself;
- price trades through the sweep extreme;
- price runs `InpCancelPendingAtR` × R away before the fill;
- an M5 close loses the reclaim;
- a news blackout starts (`InpNewsCancelPending`);
- a daily halt triggers;
- a new CRT range starts (unless `InpCarryActiveSetup` is on).

### Score (maximum 11)
| Item | Points |
|---|---|
| CRT range | 1 |
| Liquidity sweep | 2 |
| M5 reclaim | 2 |
| M1 MSS | 2 |
| Displacement | 1 |
| FVG | 1 |
| Order Block | 1 |
| Inside an enabled session | 1 |

The mandatory core plus displacement scores 8, the default minimum.

### Stop loss
- The SL is placed at the sweep extreme ∓ (`InpSLBuffer` + `InpSLBufferATR` × ATR(M5)), rounded away from the entry to tick size.
- If the SL is closer than `InpMinSL` or the broker stops level, it is **widened** to that distance.
- If the SL is farther than `InpMaxSL`, the trade is **rejected**.
- No order is ever sent without an SL.

### Take profit (`InpTPMode`)
- `TP_CRT_OPPOSITE`: CRT High for a buy, CRT Low for a sell. The trade is rejected if the RR is below `InpMinRR`.
- `TP_RISK_REWARD`: the preset RR of 1:1, 1:1.5, 1:2 or 1:3, or a custom value.
- `TP_LIQUIDITY`: the nearest opposing pool (CRT boundary, swing, equal, previous day, session) that is at least `InpMinRR` × R away. If there is none, the EA falls back to the RR target.
- `TP_MULTI`: by default, TP1 at 1R closes 50%, TP2 at 2R closes 25%, and the rest runs to the final TP at 3R. Optionally the SL moves to break-even after TP1.

### Risk
- **Lot size:** risk money ÷ loss per lot. Loss per lot comes from `OrderCalcProfit()` with the real entry and SL, so it reflects the broker's contract size, tick size, tick value and currency conversion. It falls back to tick value if needed. The lot is then:
  - floored to the volume step and clamped to the minimum and maximum lot;
  - checked against the symbol volume limit;
  - reduced until the margin fits.
- If the risk lot is below the minimum lot, the trade is rejected unless `InpAllowMinLotOverRisk` is on. Real risk is always capped by `InpMaxRiskPctHard`.
- **Daily limits:** loss and profit limits in % or money, based on the account or on this EA only.
  - **Equity protection:** closes all EA positions and pendings and halts for the day.
  - **Consecutive losses:** counted for the current day.
- The halt lasts until the next server day or until **RESET DAILY STATISTICS** is pressed.
- Martingale, grid and averaging down are **not implemented** at all.

---

## 3. Input parameters

> **Units:** every distance named "(units)" is a multiple of `InpDistUnit`. When `InpDistUnit = 0`, one unit = the symbol point.
> **For XAUUSD set `InpDistUnit = 0.01`.** The defaults (spread 60, SL buffer 30, min SL 100, max SL 1500 …) then mean $0.60, $0.30, $1.00, $15.00 on every broker, whether it quotes 2 or 3 digits.

### A. General
| Input | Default | Description |
|---|---|---|
| InpMagic | 20261112 | Unique magic number. Use a different one per chart or symbol. |
| InpOrderComment | CRT-TBS | Comment prefix. The setup id is appended. |
| InpAutoTradingDefault | true | Whether the AUTO TRADING button starts ON. |
| InpDiagnosticMode | false | Full analysis, logs and drawings, but no orders ever. |
| InpDistUnit | 0 | Distance unit in price (0 = point). Use 0.01 for gold. |
| InpSlippagePts | 30 | Maximum deviation in symbol points. |
| InpAllowBuy / InpAllowSell | true | Enable each direction. |
| InpATRPeriod | 14 | ATR period, used on M1, M5 and the liquidity timeframe. |

### B. CRT
| Input | Default | Description |
|---|---|---|
| InpCRTTimeframe | H1 | Reference timeframe (M15 or higher). |
| InpCRTMode | Previous candle | Previous candle, 2 candles, 3 candles, or previous session (Asian/London/NY windows). |
| InpCRTMinRange / InpCRTMaxRange | 150 / 5000 | Range size filter (units). |
| InpCRTRequireBias | true | BUY sweeps only in the discount half (≤ 50%), SELL only in the premium half. |

### C. Liquidity (M15)
| Input | Default | Description |
|---|---|---|
| InpLiqTimeframe | M15 | Liquidity timeframe. |
| InpLiqLookbackBars | 96 | Bars scanned. |
| InpLiqSwingDepth | 3 | Fractal depth. Swings are confirmed by closed bars only. |
| InpUseSwingLevels / InpUseEqualLevels | true | Use swing highs/lows; use equal highs/lows. |
| InpEqualTolerance | 30 | Tolerance for equal highs/lows (units). |
| InpUsePrevDayHL / InpUsePrevSessionHL | true | Use the previous day high/low; use the previous session high/low (only while untaken). |
| InpLiqMaxDistATR | 3.0 | Keep only pools within x ATR(M15) of the CRT range. 0 = off. |
| InpMaxLiqLevels | 12 | Maximum pools per side. The nearest to price are kept. |

### D. TBS (M5)
| Input | Default | Description |
|---|---|---|
| InpSweepSource | CRT + liquidity | Which levels can be swept. |
| InpSweepMinBreach / InpSweepMinBreachATR | 20 / 0 | Minimum breach in units, or as x ATR (the larger one applies). |
| InpSweepMaxDepthATR | 3.0 | A deeper move counts as a breakout, not a sweep. |
| InpReclaimMinClose | 5 | The reclaim close must land this far back inside (units). |
| InpReclaimMaxBars | 3 | M5 bars allowed for the reclaim. |
| InpBreakoutCloseATR | 0.6 | A close beyond the level by more than x ATR(M5) means a breakout. |
| InpBreakoutBars | 2 | This many consecutive closes beyond the level mean a breakout. |
| InpMinRejectWick | 0.30 | Wick/range ratio required when sweep and reclaim happen in one candle. |

### E. MSS (M1)
| Input | Default | Description |
|---|---|---|
| InpMSSSwingMode | Strict | Strict = swing before the sweep extreme. Loose = most recent unbroken swing. |
| InpMSSSwingDepth | 2 | M1 fractal depth. |
| InpMSSLookbackBars | 60 | How far back before the extreme to look for the swing. |
| InpMSSMinBreak | 5 | Minimum close beyond the swing (units). |
| InpSetupExpiryMin | 90 | Setup lifetime after the sweep. |
| InpRequireDisplacement | true | Displacement is mandatory. |
| InpDispMinBody / InpDispATRMult / InpDispBodyRatio | 0 / 1.2 / 0.55 | Displacement candle criteria. |
| InpDispLookback | 5 | The displacement must be within N bars ending at the MSS candle. |
| InpMSSMaxAgeMarket | 3 | Maximum MSS age for a market entry (bars). |

### F. FVG
| Input | Default | Description |
|---|---|---|
| InpUseFVG / InpRequireFVG | true / false | Detect FVGs; make them mandatory. |
| InpFVGMinSize / InpFVGMinSizeATR | 10 / 0 | Minimum gap size. |
| InpFVGAllowPartial | true | Accept a partially mitigated FVG. |
| InpFVGEntryLevel | 0.5 | Limit level: 0 = proximal edge, 0.5 = midpoint, 1 = distal edge. |

### G. Order Block
| Input | Default | Description |
|---|---|---|
| InpUseOB / InpRequireOB | true / false | Detect OBs; make them mandatory. |
| InpOBZone | Body | Zone from the candle body or from wick to wick. |
| InpOBRetestRequired | false | Market entry only after an OB touch with a rejection close. |
| InpOBEntryLevel | 0.5 | Limit level inside the OB. |
| InpOBMaxSearchBars | 10 | How far back from the displacement to look for the OB candle. |

### H. Entry
| Input | Default | Description |
|---|---|---|
| InpEntryMode | Market | Market / limit at FVG / limit at OB / limit at discount. |
| InpDiscountLevel | 0.5 | Retracement level for the discount mode. |
| InpFallbackToMarket | true | Enter at market if the limit level is missing or already traded through. |
| InpPendingExpiryMin | 30 | Pending order lifetime (minutes). |
| InpConfirmWaitBars | 5 | M1 bars after the MSS to wait for FVG, OB, retest or gate filters. |
| InpCancelPendingAtR | 1.0 | Cancel the pending order if price runs x R away before the fill. |
| InpMinScore | 8 | Minimum confluence score (0–11). |
| InpCarryActiveSetup | false | Keep setups that are past the reclaim alive through a new range. |

### I. Stop loss
`InpSLBuffer` 30, `InpSLBufferATR` 0, `InpMinSL` 100 (widen), `InpMaxSL` 1500 (reject). All in units.

### J. Take profit
- `InpTPMode` (Multi), `InpRRPreset` (1:2), `InpCustomRR` 2.5, `InpMinRR` 1.0.
- Partials: `InpTP1_R` 1 / `InpTP1_Pct` 50, `InpTP2_R` 2 / `InpTP2_Pct` 25, `InpTP3_R` 3.

### K. Risk
| Input | Default | Description |
|---|---|---|
| InpLotMode | % risk | Fixed lot or % risk. |
| InpFixedLot | 0.01 | Fixed lot size. |
| InpRiskPercent / InpRiskBase | 1.0 / Balance | Risk per trade and what it is measured from. |
| InpAllowMinLotOverRisk | false | Allow the minimum lot even when it risks more than the target. |
| InpMaxRiskPctHard | 2.0 | Hard cap on real risk per trade. |
| InpDailyScope | Account | Daily P/L measured on the account or on this EA. |
| InpMaxDailyLossPct / Money | 3% / 0 | Daily loss stop. 0 = off. |
| InpMaxDailyProfitPct / Money | 0 / 0 | Daily profit stop. 0 = off. |
| InpCloseOnDailyLoss | false | Also close positions when the daily loss limit is hit. |
| InpEquityProtectPct | 4.0 | Close everything and halt for the day at x% daily drawdown. |
| InpMaxOpenPositions | 1 | Positions plus pendings of this EA. |
| InpMaxTradesPerDay | 4 | Maximum trades per day. |
| InpMaxTradesPerSetup | 1 | Maximum trades per setup. |
| InpMaxConsecLosses | 3 | Maximum consecutive losses per day. |
| InpMaxSpread | 60 | Maximum spread (units). |
| InpMinATRM5 | 0 | Low-liquidity filter on ATR(M5). 0 = off. |

### L. Trade management
| Input | Default | Description |
|---|---|---|
| InpUseBreakEven / InpBETriggerR / InpBEOffset | true / 1.0 / 10 | Break-even, its trigger in R, and the offset beyond entry (units). |
| InpTrailMode | None | Trailing stop: none / fixed distance / ATR. |
| InpTrailStartR | 1.5 | Trailing starts at this R. |
| InpTrailDistance | 300 | Fixed trailing distance (units). |
| InpTrailATRMult | 2.0 | ATR multiple for ATR trailing. |
| InpTrailStep | 10 | Minimum SL improvement step (units). |
| InpUsePartials | true | Partial closes in Multi TP mode. |
| InpMaxHoldMinutes | 0 | Maximum holding time. 0 = off. |
| InpCloseOnInvalidation | true | Close the position when an M5 candle closes beyond the sweep extreme. |

### M. Sessions (GMT)
- Asian 00:00–07:00 (off), London 07:00–16:00, New York 12:00–21:00, Overlap 12:00–16:00. Each one can be switched on or off.
- `InpAutoGMTOffset` measures the broker offset on a live chart. **In the Strategy Tester `InpServerGMTOffset` is used**, because the tester cannot measure it. Most brokers are GMT+2 in winter and GMT+3 in summer.
- `InpNoTradePeriods`: for example `"20:55-21:15;11:58-12:05"`.
- `InpNoTradeFriday` / `InpFridayCutoffHourGMT`: block new trades late on Friday.

### N. News (manual, no external feed)
- `InpNewsEvents`: for example `"2026.11.13 13:30;2026.12.05 13:30"` (GMT).
- `InpNewsDailyTimes`: recurring weekday slots, for example `"13:30;15:00"`.
- The blackout window is set with `InpNewsMinutesBefore` / `After`.
- Optionally cancel pending orders and/or close positions during the blackout.

### O. Dashboard
Position, font size, drawing on/off, number of setups whose drawings are kept, and colors.

### P. Debug
- `InpLogLevel`:
  - Basic logs every decision, trade and rejection.
  - Detailed also logs the liquidity map, state transitions and zone scans.
- `InpLogRejections`: logs the reason a trade was **not** opened (each distinct reason once).

---

## 4. Installation
1. In MT5 open **File → Open Data Folder**. Copy `CRT_TBS_SMC_Sniper_EA_PRO.mq5` to `MQL5\Experts\`.
2. Open it in MetaEditor and press **Compile (F7)**. It should report 0 errors. Warnings are informational.
3. Open an **M1 XAUUSD chart**. The symbol suffix does not matter.
4. Drag the EA onto the chart:
   - tick *Allow Algo Trading*;
   - set `InpDistUnit = 0.01` for gold;
   - check `InpServerGMTOffset` and the session times.
5. Enable **Algo Trading** in the toolbar.
6. Check the *Experts* tab. The INIT line prints digits, point, tick size, contract size, volume limits, the hedging or netting mode and the GMT offset.

The dashboard buttons work like this:
- **AUTO TRADING** toggles immediately.
- **CLOSE ALL**, **CANCEL PENDING** and **RESET DAILY STATS** need a **second click within 5 seconds**. The button text changes to `CONFIRM … ?` in between.

## 5. Backtesting
1. Open the Strategy Tester (Ctrl+R) and choose Expert `CRT_TBS_SMC_Sniper_EA_PRO`.
2. Choose symbol XAUUSD (your broker's name) and timeframe **M1**.
3. Choose the model **Every tick based on real ticks**. This is recommended because the logic runs on M1 closes and the trade management runs per tick. "1 minute OHLC" works for a quick first pass.
4. Set the inputs:
   - `InpServerGMTOffset` = your broker's offset (DST is not handled automatically in the tester);
   - `InpDistUnit = 0.01`;
   - `InpLogLevel = Basic` for single runs, `None` for optimization.
5. Turn on **Visual mode** to see the dashboard and the drawings: CRT lines, liquidity, sweep arrows, MSS, FVG and OB boxes, and entry, SL and TP. In non-visual runs all drawing is skipped for speed.
6. Use `InpDiagnosticMode = true` to review the signals the EA would take without placing any trades.
7. Good parameters to optimize:
   - `InpSweepMinBreach`, `InpReclaimMaxBars`, `InpBreakoutCloseATR`;
   - `InpMSSSwingDepth`, `InpDispATRMult`, `InpMinScore`;
   - `InpEntryMode`, `InpTPMode`, `InpSLBuffer`.

   Optimize on one period and validate on another (walk-forward).

## 6. Known limitations
- **Not compiled here.** Compile it in MetaEditor and report any error.
- **Sessions and DST.** Session times are fixed GMT. DST shifts are not applied automatically, so adjust the times or the offset in summer. Auto offset works only live.
- **No calendar.** There is no economic calendar integration, only the manual blackout list.
- **Restart recovery is partial.** Open positions and pendings are re-attached, and management state (initial SL, partials done, BE done, sweep extreme) is kept in terminal Global Variables. The *analysis* state of a setup still in progress (sweep or MSS waiting) is not restored. It is rebuilt from the next valid sweep.
- **One setup per direction.** Each direction tracks one setup at a time, the first eligible sweep. The deepest level is chosen when one candle takes several.
- **Equity protection.** It acts on ticks, so on a large gap the realised loss can exceed the threshold.
- **Day start balance.** It is reconstructed from today's trade deals. Deposits and withdrawals made today shift it slightly.
- **Consecutive losses.** They are counted per day, so the counter resets each server day.
- **Partial closes.** They need a volume that splits into broker steps. If 50% of the minimum lot cannot be split, that partial is skipped, but BE and the remaining logic still work.
- **Commission.** It is not included in the lot calculation, but it is included in the daily P/L.
- **Profit is not guaranteed.** Test thoroughly on a demo account before trading live.

# TelegramBridgeEA

Companion Expert Advisor for the Python bot. Only needed if placing orders
straight from Python (`mt5.order_send()`) gets rejected with
`retcode=10027 "AutoTrading disabled by client"` even though Algo Trading
is on in the terminal and manual trades work fine - a restriction some
brokers/terminal builds apply specifically to the external Python API.
The EA trades from inside the terminal instead (same path as clicking
"New Order" manually), which isn't affected.

Python still does everything else: reads Telegram, parses signals, plans
the entry/SL/TP grid, watches prices/positions for the 1:1 average-SL
logic. It only hands the EA a plain-text instruction file for the actual
trade calls - see `TelegramBridgeEA.mq5`'s header comment for the exact
format.

## Install

1. Open MT5 → **Narzędzia (Tools) → MetaEditor** (or press F4).
2. In MetaEditor's Navigator (left panel), right-click **Experts** → **New Folder**
   is not needed - just right-click **Experts** → **Open Folder** to see
   where files go, or simpler: in Windows Explorer, copy
   `TelegramBridgeEA.mq5` into your MT5 data folder's `MQL5\Experts\`
   subfolder (in MT5: **File → Open Data Folder** to find it).
3. Back in MetaEditor, open `TelegramBridgeEA.mq5` from the Navigator and
   press **F7** (Compile). It should say "0 error(s), 0 warning(s)" at the
   bottom. This creates `TelegramBridgeEA.ex5` next to it.
4. Switch to MT5. In the **Navigator** panel (Ctrl+N), under **Doradcy
   (Expert Advisors)**, you should now see `TelegramBridgeEA`.
5. Drag it onto **any one chart** (the XAUUSD chart is fine, but it doesn't
   actually matter which symbol - the EA trades whatever symbol each
   command file tells it to).
6. In the properties dialog that opens:
   - Tab **Common (Ogólne)**: check **"Allow live trading" / "Zezwól na
     handel na żywo"**.
   - Tab **Inputs (Wejścia)**: defaults are fine (`BridgeSubfolder=tg_bridge`,
     `PollSeconds=1`).
   - Click OK.
7. Make sure the global **"Algo Trading"** button in the MT5 toolbar is on
   (green) - the EA needs it too, same as any automated trading.
8. Check the **Eksperci (Experts)** tab at the bottom of MT5: you should
   see `TelegramBridgeEA started, watching Common\Files\tg_bridge\` and,
   every 60s, an "alive" heartbeat line. If you see a smiling face in the
   corner of the chart the EA is on, it's active.

That's it - leave that chart open (can be minimized) while the Python bot
runs. No changes needed to `.env`; `mt5_executor.py` finds the same shared
`Common\Files\tg_bridge` folder automatically via the MT5 connection.

## Updating after this first install

Whenever `TelegramBridgeEA.mq5` changes (e.g. after `git pull`), you need
to copy the new source over the old one and recompile. Two ways:

- **`update_ea.bat`** (in this folder) does both in one double-click - it
  copies the file into your MT5 data folder and compiles it via
  MetaEditor's command-line mode, then prints the compile result. The two
  paths at the top of the script are already filled in for this install;
  only edit them if you reinstall MT5 or move it elsewhere.
- Or do it manually: repeat steps 2-3 above (copy the file, open it in
  MetaEditor, press F7).

Either way, check MT5's **Eksperci** tab afterwards - the EA should keep
running with the new code (MT5 usually hot-reloads a recompiled EA
automatically), or remove and re-drag it onto the chart if it doesn't.

## How to tell it's working

- MT5 **Eksperci** tab logs every order it places/fails and every SL move,
  e.g. `Bridge: placed BUY @ 4469.00 sl=4463.00 tp=4475.00 ticket=123456`.
- The Python bot logs `queued N orders for EA bridge (campaign ...) -> ...`
  when it hands off a zone signal, then you'll see the resulting positions
  show up in MT5's **Handel (Trade)** tab a moment later.
- If the Python bot's own log ever shows a warning about "command file(s)
  ... still unprocessed" - the EA isn't attached/running; redo steps 4-6.

## Uninstalling / going back to direct API calls

Not supported as a toggle right now - the bridge is the only way
`mt5_executor.py` places orders. If your account doesn't have the
retcode-10027 restriction, the EA is a compatible, working alternative
either way (it doesn't hurt to leave it running).

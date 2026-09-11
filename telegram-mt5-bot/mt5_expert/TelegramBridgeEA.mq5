//+------------------------------------------------------------------+
//| TelegramBridgeEA.mq5                                            |
//|                                                                  |
//| Companion EA for the Telegram->MT5 Python bot. The Python side  |
//| (Telethon + parser + order planner) does everything except the  |
//| actual trade calls: it writes plain-text command files into     |
//| MT5's shared "Common\Files\tg_bridge" folder, and this EA -     |
//| attached to any one chart, with Algo Trading + "Allow live      |
//| trading" enabled - polls that folder and executes the commands  |
//| with native OrderSend() calls.                                  |
//|                                                                  |
//| Why this exists: on some accounts/broker builds, order_send()   |
//| called from the external Python MetaTrader5 package is rejected |
//| with retcode 10027 "AutoTrading disabled by client" even though |
//| the terminal's Algo Trading toggle is on and manual trades work |
//| fine. An EA trading from inside the terminal uses the same path |
//| as a human clicking "New Order", which isn't affected.          |
//|                                                                  |
//| Command file format (one command per file, plain text lines):   |
//|                                                                  |
//|   TYPE=OPEN_ORDERS                                              |
//|   MAGIC=990009                                                  |
//|   SYMBOL=XAUUSD                                                 |
//|   COMMENT=tg-b15c015b                                           |
//|   DEVIATION=20                                                  |
//|   ORDER=BUY,4469.00,4463.00,4475.00,0.01                        |
//|   ORDER=BUY,4469.50,4463.00,4476.50,0.01                        |
//|   ...                                                            |
//|                                                                  |
//|   TYPE=MODIFY_SL                                                |
//|   MAGIC=990009                                                  |
//|   SYMBOL=XAUUSD                                                 |
//|   NEW_SL=4422.50                                                |
//|                                                                  |
//|   TYPE=MODIFY_POSITIONS                                         |
//|   SYMBOL=XAUUSD                                                 |
//|   POSITION=123456,4422.50,4430.00                               |
//|   POSITION=123457,4423.10,4431.00                                |
//|   ...  (ticket,new_sl,tp - each position its own new SL, unlike  |
//|         MODIFY_SL's one shared SL for every position of a magic) |
//|                                                                  |
//| Each file is deleted once processed. Results are printed to the |
//| Experts/Journal log - the Python side never reads a result file,|
//| it just polls positions/orders by magic number afterwards.      |
//|                                                                  |
//| An ORDER whose entry price is within the broker's minimum       |
//| stop/freeze distance of the current price fills at MARKET       |
//| instead of being sent as a pending order (which would just get  |
//| rejected for being too close) - same SL/TP either way.          |
//|                                                                  |
//| Fill notifications: whenever a deal with magic >= MagicRangeStart|
//| actually fills (not just gets placed), OnTradeTransaction below  |
//| drops a chart screenshot + a small metadata file into            |
//| Common\Files\<BridgeSubfolder>\fills\ - <deal_ticket>.png and    |
//| <deal_ticket>.txt (DEAL=/POSITION=/MAGIC=/SYMBOL= lines). The    |
//| Python side polls that folder and forwards it to Telegram (see   |
//| mt5_executor.take_pending_fill_notifications / main.py's          |
//| Bot.watch_fills) - closes and the daily pips/profit summary are  |
//| computed entirely on the Python side from MT5's own deal history,|
//| not handled here.                                                 |
//|                                                                  |
//| Manual panel (ShowPanel=true, on by default): an on-chart form - |
//| no Python involved at all - where you type a zone ("4420-4425"), |
//| SL pips, trailing pips and grid step ($), then click BUY/SELL.   |
//| Places the same kind of order grid/lot tiering as the Python bot |
//| (PanelLotBase/PanelLotTierOrders/PanelLotScalingMode/            |
//| PanelLotMultiplier inputs mirror LOT_SIZE/LOT_TIER_ORDERS/        |
//| LOT_SCALING_MODE/LOT_MULTIPLIER in .env) via the same             |
//| HandleOpenOrders() used for bridge commands, with NO fixed TP -   |
//| exits only via the same stepped trailing stop as EXIT_MODE=       |
//| trailing_stop (PanelUpdateTrailingStops(), run every OnTimer      |
//| tick), using the trailing_pips value entered at click time        |
//| (remembered per PanelMagicBase+N in memory - lost on EA restart,  |
//| a fresh click is needed to re-arm trailing for positions opened   |
//| before a restart). Positions get their own magic range            |
//| (PanelMagicBase+) so they never mix with Python-driven campaigns. |
//+------------------------------------------------------------------+
#property copyright "Telegram MT5 signal bot"
#property strict

input string BridgeSubfolder   = "tg_bridge";   // subfolder under Common\Files
input int    PollSeconds       = 1;             // how often to check for new commands
input int    HeartbeatSeconds  = 60;            // how often to print an "I'm alive" log line
input long   MagicRangeStart   = 990000;        // fill notifications: deals with magic >= this are treated as ours - match MAGIC_BASE in .env
input int    ScreenshotWidth   = 1024;          // fill notification screenshot size (pixels)
input int    ScreenshotHeight  = 600;

input bool   ShowPanel              = true;     // show the manual BUY/SELL zone panel on this chart
input double PanelDefaultSlPips     = 60;       // default value shown in the panel's SL field
input double PanelDefaultTrailingPips = 36;     // default value shown in the panel's Trailing field
input double PanelDefaultStepDollars = 0.5;     // default value shown in the panel's Step field
input double PanelPipSize           = 0.1;      // price value of 1 pip - must match PIP_SIZE in .env / your broker's gold quoting
input double PanelLotBase           = 0.01;     // base lot for the panel's own order grid (mirrors LOT_SIZE)
input int    PanelLotTierOrders     = 3;        // mirrors LOT_TIER_ORDERS
input string PanelLotScalingMode    = "additive"; // "additive" or "multiplier" - mirrors LOT_SCALING_MODE
input double PanelLotMultiplier     = 1.2;      // mirrors LOT_MULTIPLIER
input long   PanelMagicBase         = 500000;   // panel orders get PanelMagicBase+N, N incrementing per click - kept well clear of MAGIC_BASE (990000+) so they never mix with Python-driven campaigns
input int    PanelDeviationPoints   = 20;

datetime g_lastHeartbeat = 0;

long   g_panelNextMagic = 0;
long   g_panelMagics[];
double g_panelTrailingPips[];

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(PollSeconds);
   PrintFormat("TelegramBridgeEA started, watching Common\\Files\\%s\\", BridgeSubfolder);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("WARNING: Algo Trading is currently OFF - this EA cannot place orders until it's enabled.");
   FolderCreate(BridgeSubfolder + "\\fills", FILE_COMMON);
   ProcessBridgeFolder();
   if(ShowPanel)
      PanelCreate();
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   PanelDestroy();
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   ProcessBridgeFolder();
   PanelUpdateTrailingStops();

   if(HeartbeatSeconds > 0 && TimeCurrent() - g_lastHeartbeat >= HeartbeatSeconds)
     {
      PrintFormat("TelegramBridgeEA alive, watching Common\\Files\\%s\\", BridgeSubfolder);
      g_lastHeartbeat = TimeCurrent();
     }
  }

//+------------------------------------------------------------------+
//| Scans the bridge folder for *.txt command files and processes    |
//| each one in turn.                                                 |
//+------------------------------------------------------------------+
void ProcessBridgeFolder()
  {
   string pattern = BridgeSubfolder + "\\*.txt";
   string filename;
   long handle = FileFindFirst(pattern, filename, FILE_COMMON);
   if(handle == INVALID_HANDLE)
      return;

   string pending[];
   int count = 0;
   do
     {
      ArrayResize(pending, count + 1);
      pending[count] = filename;
      count++;
     }
   while(FileFindNext(handle, filename));
   FileFindClose(handle);

   for(int i = 0; i < count; i++)
      ProcessCommandFile(BridgeSubfolder + "\\" + pending[i]);
  }

//+------------------------------------------------------------------+
//| Reads one command file, dispatches it, then deletes it.          |
//+------------------------------------------------------------------+
void ProcessCommandFile(string relativePath)
  {
   int fh = FileOpen(relativePath, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      PrintFormat("Bridge: could not open %s (error %d)", relativePath, GetLastError());
      return;
     }

   string lines[];
   int n = 0;
   while(!FileIsEnding(fh))
     {
      string line = FileReadString(fh);
      if(StringLen(line) == 0)
         continue;
      ArrayResize(lines, n + 1);
      lines[n] = line;
      n++;
     }
   FileClose(fh);

   string type = "";
   long   magic = 0;
   string symbol = "";
   string comment = "";
   int    deviation = 20;
   int    expectedCount = -1;
   double newSl = 0;
   string orderLines[];
   int    orderCount = 0;
   string positionLines[];
   int    positionCount = 0;

   for(int i = 0; i < n; i++)
     {
      string line = lines[i];
      int eq = StringFind(line, "=");
      if(eq < 0)
         continue;
      string key = StringSubstr(line, 0, eq);
      string value = StringSubstr(line, eq + 1);

      if(key == "TYPE")
         type = value;
      else if(key == "MAGIC")
         magic = StringToInteger(value);
      else if(key == "SYMBOL")
         symbol = value;
      else if(key == "COMMENT")
         comment = value;
      else if(key == "DEVIATION")
         deviation = (int)StringToInteger(value);
      else if(key == "COUNT")
         expectedCount = (int)StringToInteger(value);
      else if(key == "NEW_SL")
         newSl = StringToDouble(value);
      else if(key == "ORDER")
        {
         ArrayResize(orderLines, orderCount + 1);
         orderLines[orderCount] = value;
         orderCount++;
        }
      else if(key == "POSITION")
        {
         ArrayResize(positionLines, positionCount + 1);
         positionLines[positionCount] = value;
         positionCount++;
        }
     }

   if(type == "OPEN_ORDERS")
     {
      if(expectedCount >= 0 && orderCount != expectedCount)
        {
         PrintFormat(
            "Bridge: %s declared COUNT=%d but only %d ORDER line(s) were read - "
            "file may have been read while still being written. Placing what was found; "
            "check the Python bot's log and the zone signal for the rest.",
            relativePath, expectedCount, orderCount);
        }
      HandleOpenOrders(magic, symbol, comment, deviation, orderLines, orderCount);
     }
   else if(type == "MODIFY_SL")
      HandleModifySl(magic, symbol, newSl);
   else if(type == "MODIFY_POSITIONS")
      HandleModifyPositions(symbol, positionLines, positionCount);
   else
      PrintFormat("Bridge: unknown command TYPE in %s: '%s'", relativePath, type);

   if(!FileDelete(relativePath, FILE_COMMON))
      PrintFormat("Bridge: could not delete processed file %s (error %d)", relativePath, GetLastError());
  }

//+------------------------------------------------------------------+
//| Picks a filling mode the symbol actually supports for market     |
//| (TRADE_ACTION_DEAL) execution - brokers vary in which of         |
//| FOK/IOC/RETURN they accept for immediate fills.                  |
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING MarketFillingModeFor(string symbol)
  {
   long filling = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) != 0)
      return ORDER_FILLING_FOK;
   if((filling & SYMBOL_FILLING_IOC) != 0)
      return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
  }

//+------------------------------------------------------------------+
//| Places one order per ORDER= line: a normal pending order, except |
//| when the entry price is within the broker's minimum stop/freeze  |
//| distance of the current price - a pending order that close would |
//| just get rejected, so that one entry fills at MARKET instead     |
//| (same SL/TP), rather than being silently skipped.                |
//+------------------------------------------------------------------+
void HandleOpenOrders(long magic, string symbol, string comment, int deviation, string &orderLines[], int orderCount)
  {
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   long stopsLevelPts = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freezeLevelPts = SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double minDistance = MathMax(stopsLevelPts, freezeLevelPts) * point;

   for(int i = 0; i < orderCount; i++)
     {
      string parts[];
      int partCount = StringSplit(orderLines[i], ',', parts);
      if(partCount < 5)
        {
         PrintFormat("Bridge: malformed ORDER line '%s'", orderLines[i]);
         continue;
        }

      string direction = parts[0];
      double entry = StringToDouble(parts[1]);
      double sl    = StringToDouble(parts[2]);
      double tp    = StringToDouble(parts[3]);
      double lot   = StringToDouble(parts[4]);

      double refPrice = (direction == "BUY") ? ask : bid;
      bool atMarket = (MathAbs(entry - refPrice) <= minDistance);

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.symbol    = symbol;
      request.volume     = lot;
      request.sl         = sl;
      request.tp         = tp;
      request.magic       = magic;
      request.comment     = comment;

      if(atMarket)
        {
         request.action       = TRADE_ACTION_DEAL;
         request.type         = (direction == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
         request.price        = refPrice;
         request.deviation    = deviation;
         request.type_filling = MarketFillingModeFor(symbol);
        }
      else
        {
         ENUM_ORDER_TYPE orderType;
         if(direction == "BUY")
            orderType = (entry < ask) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_BUY_STOP;
         else
            orderType = (entry > bid) ? ORDER_TYPE_SELL_LIMIT : ORDER_TYPE_SELL_STOP;

         request.action       = TRADE_ACTION_PENDING;
         request.type         = orderType;
         request.price        = entry;
         request.deviation    = deviation;
         request.type_time    = ORDER_TIME_GTC;
         request.type_filling = ORDER_FILLING_RETURN;
        }

      bool ok = OrderSend(request, result);
      if(!ok || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("Bridge: %s order FAILED %s @ %.2f retcode=%d comment='%s'",
                     atMarket ? "MARKET" : "PENDING", direction, entry, result.retcode, result.comment);
      else
         PrintFormat("Bridge: placed %s %s @ %.2f (requested %.2f) sl=%.2f tp=%.2f ticket=%d",
                     atMarket ? "MARKET" : "PENDING", direction, result.price, entry, sl, tp, (int)result.order);
     }
  }

//+------------------------------------------------------------------+
//| Moves SL on every open position matching (magic, symbol).        |
//+------------------------------------------------------------------+
void HandleModifySl(long magic, string symbol, double newSl)
  {
   int moved = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != magic)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != symbol)
         continue;

      double tp = PositionGetDouble(POSITION_TP);

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action   = TRADE_ACTION_SLTP;
      request.position = ticket;
      request.symbol    = symbol;
      request.sl       = newSl;
      request.tp       = tp;

      bool ok = OrderSend(request, result);
      if(!ok || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("Bridge: SL move FAILED for ticket %d retcode=%d comment='%s'",
                     (int)ticket, result.retcode, result.comment);
      else
        {
         PrintFormat("Bridge: moved SL to %.2f for ticket %d", newSl, (int)ticket);
         moved++;
        }
     }

   if(moved == 0)
      PrintFormat("Bridge: MODIFY_SL for magic=%d found no matching open positions", (int)magic);
  }

//+------------------------------------------------------------------+
//| Moves SL (and re-applies TP) on specific positions by ticket -   |
//| unlike HandleModifySl, each POSITION= line carries its own new   |
//| SL, used for per-position trailing stops (EXIT_MODE=trailing_stop|
//| in the Python bot) where every position trails independently.    |
//+------------------------------------------------------------------+
void HandleModifyPositions(string symbol, string &positionLines[], int positionCount)
  {
   for(int i = 0; i < positionCount; i++)
     {
      string parts[];
      int partCount = StringSplit(positionLines[i], ',', parts);
      if(partCount < 3)
        {
         PrintFormat("Bridge: malformed POSITION line '%s'", positionLines[i]);
         continue;
        }

      ulong ticket = (ulong)StringToInteger(parts[0]);
      double newSl = StringToDouble(parts[1]);
      double tp    = StringToDouble(parts[2]);

      if(!PositionSelectByTicket(ticket))
        {
         PrintFormat("Bridge: MODIFY_POSITIONS ticket %d not found (already closed?)", (int)ticket);
         continue;
        }

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action   = TRADE_ACTION_SLTP;
      request.position = ticket;
      request.symbol    = symbol;
      request.sl       = newSl;
      request.tp       = tp;

      bool ok = OrderSend(request, result);
      if(!ok || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("Bridge: trailing SL FAILED for ticket %d retcode=%d comment='%s'",
                     (int)ticket, result.retcode, result.comment);
      else
         PrintFormat("Bridge: trailing SL -> %.2f for ticket %d", newSl, (int)ticket);
     }
  }

//+------------------------------------------------------------------+
//| Fires on every deal/order change. When one of our pending orders  |
//| actually fills (a DEAL_ENTRY_IN deal whose magic is in our range),|
//| drops a chart screenshot + a small metadata file into the bridge  |
//| folder's fills\ subfolder - see the header comment above and     |
//| mt5_executor.take_pending_fill_notifications on the Python side. |
//| Closes are deliberately NOT handled here - the Python side reads |
//| MT5's own deal history for those (and the daily summary), which  |
//| it can already do without going through this EA.                 |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                         const MqlTradeRequest &request,
                         const MqlTradeResult &result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;
   if(!HistoryDealSelect(trans.deal))
      return;

   long dealMagic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
   if(dealMagic < MagicRangeStart)
      return;

   ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_IN)
      return;

   string symbol = HistoryDealGetString(trans.deal, DEAL_SYMBOL);
   long positionId = HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   string dealStr = (string)trans.deal;

   string shotName = "tg_bridge_shot_" + dealStr + ".png";
   if(!ChartScreenShot(0, shotName, ScreenshotWidth, ScreenshotHeight))
     {
      PrintFormat("Bridge: fill notification for deal %s - ChartScreenShot failed (error %d)", dealStr, GetLastError());
      return;
     }

   string destPng = BridgeSubfolder + "\\fills\\" + dealStr + ".png";
   if(!FileCopy(shotName, 0, destPng, FILE_COMMON))
     {
      PrintFormat("Bridge: fill notification for deal %s - could not copy screenshot into bridge folder (error %d)", dealStr, GetLastError());
      FileDelete(shotName, 0);
      return;
     }
   FileDelete(shotName, 0);

   string tmpMeta = BridgeSubfolder + "\\fills\\" + dealStr + ".tmp";
   int fh = FileOpen(tmpMeta, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh == INVALID_HANDLE)
     {
      PrintFormat("Bridge: fill notification for deal %s - could not write metadata (error %d)", dealStr, GetLastError());
      return;
     }
   FileWrite(fh, "DEAL=" + dealStr);
   FileWrite(fh, "POSITION=" + (string)positionId);
   FileWrite(fh, "MAGIC=" + (string)dealMagic);
   FileWrite(fh, "SYMBOL=" + symbol);
   FileClose(fh);

   string finalMeta = BridgeSubfolder + "\\fills\\" + dealStr + ".txt";
   if(!FileMove(tmpMeta, FILE_COMMON, finalMeta, FILE_COMMON))
      PrintFormat("Bridge: fill notification for deal %s - could not finalize metadata file (error %d)", dealStr, GetLastError());
   else
      PrintFormat("Bridge: fill notification queued for deal %s (magic=%d)", dealStr, (int)dealMagic);
  }

//+------------------------------------------------------------------+
//| MANUAL PANEL - lets you place the same kind of order grid the    |
//| Python bot builds from a Telegram signal, but typed in by hand   |
//| and with no Python involved at all. See the header comment.      |
//+------------------------------------------------------------------+
#define PANEL_PREFIX "TgPanel_"

//+------------------------------------------------------------------+
void PanelCreateLabel(string name, int x, int y, string text)
  {
   string full = PANEL_PREFIX + name;
   ObjectCreate(0, full, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, full, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, full, OBJPROP_TEXT, text);
   ObjectSetInteger(0, full, OBJPROP_FONTSIZE, 9);
   ObjectSetInteger(0, full, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, full, OBJPROP_HIDDEN, true);
  }

//+------------------------------------------------------------------+
void PanelCreateEdit(string name, int x, int y, int w, string text)
  {
   string full = PANEL_PREFIX + name;
   ObjectCreate(0, full, OBJ_EDIT, 0, 0, 0);
   ObjectSetInteger(0, full, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, full, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, full, OBJPROP_YSIZE, 20);
   ObjectSetString(0, full, OBJPROP_TEXT, text);
   ObjectSetInteger(0, full, OBJPROP_ALIGN, ALIGN_CENTER);
   ObjectSetInteger(0, full, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, full, OBJPROP_BGCOLOR, clrWhite);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, full, OBJPROP_HIDDEN, true);
  }

//+------------------------------------------------------------------+
void PanelCreateButton(string name, int x, int y, int w, int h, string text, color clr)
  {
   string full = PANEL_PREFIX + name;
   ObjectCreate(0, full, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, full, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, full, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, full, OBJPROP_YSIZE, h);
   ObjectSetString(0, full, OBJPROP_TEXT, text);
   ObjectSetInteger(0, full, OBJPROP_BGCOLOR, clr);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, full, OBJPROP_HIDDEN, true);
  }

//+------------------------------------------------------------------+
void PanelCreate()
  {
   int x = 10, y = 20, rowH = 24, labelW = 130, editW = 90;
   int panelW = labelW + editW + 20;

   ObjectCreate(0, PANEL_PREFIX + "Bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_XDISTANCE, x - 5);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_YDISTANCE, y - 5);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_XSIZE, panelW);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_YSIZE, rowH * 4 + 70);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BGCOLOR, clrWhiteSmoke);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BACK, false);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_HIDDEN, true);

   PanelCreateLabel("LblZone", x, y, "Strefa (niska-wysoka):");
   PanelCreateEdit("ZoneEdit", x + labelW + 5, y, editW, "");
   y += rowH;

   PanelCreateLabel("LblSl", x, y, "SL (pips):");
   PanelCreateEdit("SlEdit", x + labelW + 5, y, editW, DoubleToString(PanelDefaultSlPips, 0));
   y += rowH;

   PanelCreateLabel("LblTrail", x, y, "Trailing (pips):");
   PanelCreateEdit("TrailEdit", x + labelW + 5, y, editW, DoubleToString(PanelDefaultTrailingPips, 0));
   y += rowH;

   PanelCreateLabel("LblStep", x, y, "Krok siatki ($):");
   PanelCreateEdit("StepEdit", x + labelW + 5, y, editW, DoubleToString(PanelDefaultStepDollars, 2));
   y += rowH + 6;

   int btnW = (panelW - 15) / 2;
   PanelCreateButton("BuyBtn", x, y, btnW, 26, "BUY", clrLimeGreen);
   PanelCreateButton("SellBtn", x + btnW + 5, y, btnW, 26, "SELL", clrTomato);
   y += 32;

   PanelCreateLabel("Status", x, y, "Gotowy.");
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
void PanelDestroy()
  {
   ObjectsDeleteAll(0, PANEL_PREFIX);
  }

//+------------------------------------------------------------------+
void PanelSetStatus(string text)
  {
   ObjectSetString(0, PANEL_PREFIX + "Status", OBJPROP_TEXT, text);
   ChartRedraw(0);
   PrintFormat("Panel: %s", text);
  }

//+------------------------------------------------------------------+
//| Prices from low to high (inclusive) spaced `step` apart - mirrors |
//| order_planner.generate_price_levels(). Computed from an index     |
//| rather than repeated addition to avoid float drift over many      |
//| steps (Python uses Decimal for the same reason).                  |
//+------------------------------------------------------------------+
int PanelGeneratePriceLevels(double low, double high, double step, double &out[])
  {
   if(low > high)
     {
      double tmp = low;
      low = high;
      high = tmp;
     }
   int count = (int)MathRound((high - low) / step) + 1;
   if(count < 1)
      count = 1;
   ArrayResize(out, count);
   for(int i = 0; i < count; i++)
      out[i] = NormalizeDouble(low + i * step, 2);
   return count;
  }

//+------------------------------------------------------------------+
//| Mirrors order_planner._lot_tiers_by_distance_to_sl(): tier 0 is   |
//| the PanelLotTierOrders entries FURTHEST from slPrice, each        |
//| further group of PanelLotTierOrders one tier closer, ending with  |
//| the entries closest to SL in the highest tier.                    |
//+------------------------------------------------------------------+
void PanelLotTiers(double &levels[], int count, double slPrice, int tierOrders, int &tiers[])
  {
   int order[];
   ArrayResize(order, count);
   for(int i = 0; i < count; i++)
      order[i] = i;

   for(int i = 1; i < count; i++)
     {
      int key = order[i];
      double keyDist = MathAbs(levels[key] - slPrice);
      int j = i - 1;
      while(j >= 0 && MathAbs(levels[order[j]] - slPrice) < keyDist)
        {
         order[j + 1] = order[j];
         j--;
        }
      order[j + 1] = key;
     }

   ArrayResize(tiers, count);
   if(tierOrders < 1)
      tierOrders = 1;
   for(int rank = 0; rank < count; rank++)
      tiers[order[rank]] = rank / tierOrders;
  }

//+------------------------------------------------------------------+
//| Reads the panel's fields, builds the same kind of order grid as   |
//| order_planner.plan_orders() (EXIT_MODE=trailing_stop shape - no   |
//| TP), and places it via HandleOpenOrders() - the same function the |
//| bridge command path uses, so MARKET-fallback for an entry too     |
//| close to price applies here too.                                  |
//+------------------------------------------------------------------+
void PanelPlaceZone(string direction)
  {
   string zoneText = ObjectGetString(0, PANEL_PREFIX + "ZoneEdit", OBJPROP_TEXT);
   string slText = ObjectGetString(0, PANEL_PREFIX + "SlEdit", OBJPROP_TEXT);
   string trailText = ObjectGetString(0, PANEL_PREFIX + "TrailEdit", OBJPROP_TEXT);
   string stepText = ObjectGetString(0, PANEL_PREFIX + "StepEdit", OBJPROP_TEXT);

   string parts[];
   if(StringSplit(zoneText, '-', parts) != 2)
     {
      PanelSetStatus("Blad: strefa musi byc w formacie NISKA-WYSOKA, np. 4420-4425");
      return;
     }
   double zoneLow = StringToDouble(parts[0]);
   double zoneHigh = StringToDouble(parts[1]);
   if(zoneLow <= 0 || zoneHigh <= 0 || zoneLow == zoneHigh)
     {
      PanelSetStatus("Blad: nieprawidlowe ceny strefy");
      return;
     }
   if(zoneLow > zoneHigh)
     {
      double tmp = zoneLow;
      zoneLow = zoneHigh;
      zoneHigh = tmp;
     }

   double slPips = StringToDouble(slText);
   double trailPips = StringToDouble(trailText);
   double step = StringToDouble(stepText);
   if(slPips <= 0 || step <= 0)
     {
      PanelSetStatus("Blad: SL (pips) i Krok siatki ($) musza byc > 0");
      return;
     }

   double slPrice = (direction == "BUY")
      ? NormalizeDouble(zoneLow - slPips * PanelPipSize, 2)
      : NormalizeDouble(zoneHigh + slPips * PanelPipSize, 2);

   double levels[];
   int levelCount = PanelGeneratePriceLevels(zoneLow, zoneHigh, step, levels);

   int kept = 0;
   for(int i = 0; i < levelCount; i++)
     {
      bool valid = (direction == "BUY") ? (levels[i] > slPrice) : (levels[i] < slPrice);
      if(valid)
        {
         levels[kept] = levels[i];
         kept++;
        }
     }
   ArrayResize(levels, kept);
   if(kept == 0)
     {
      PanelSetStatus("Blad: SL zbyt blisko strefy, brak poprawnych entry");
      return;
     }

   int tiers[];
   PanelLotTiers(levels, kept, slPrice, PanelLotTierOrders, tiers);

   long magic = PanelMagicBase + g_panelNextMagic;
   g_panelNextMagic++;
   int slot = ArraySize(g_panelMagics);
   ArrayResize(g_panelMagics, slot + 1);
   ArrayResize(g_panelTrailingPips, slot + 1);
   g_panelMagics[slot] = magic;
   g_panelTrailingPips[slot] = trailPips;

   string orderLines[];
   ArrayResize(orderLines, kept);
   for(int i = 0; i < kept; i++)
     {
      double lot;
      if(PanelLotScalingMode == "multiplier")
         lot = NormalizeDouble(PanelLotBase * MathPow(PanelLotMultiplier, tiers[i]), 2);
      else
         lot = NormalizeDouble(PanelLotBase * (tiers[i] + 1), 2);

      orderLines[i] = StringFormat("%s,%.2f,%.2f,%.2f,%.2f", direction, levels[i], slPrice, 0.0, lot);
     }

   string comment = "panel-" + (string)magic;
   HandleOpenOrders(magic, Symbol(), comment, PanelDeviationPoints, orderLines, kept);

   PanelSetStatus(StringFormat(
      "Wystawiono %d zlec. %s, SL=%.2f, trailing=%.0f pips (magic=%d)",
      kept, direction, slPrice, trailPips, (int)magic));
  }

//+------------------------------------------------------------------+
//| Stepped trailing stop for panel-placed positions ONLY (matched by |
//| magic against g_panelMagics) - exact same algorithm as the Python |
//| bot's EXIT_MODE=trailing_stop (mt5_executor.check_trailing_stops):|
//| untouched below trailPips profit, jumps to breakeven at exactly   |
//| trailPips, then another trailPips every further trailPips of      |
//| profit. Tightening only. Run every OnTimer tick.                  |
//+------------------------------------------------------------------+
void PanelUpdateTrailingStops()
  {
   if(ArraySize(g_panelMagics) == 0)
      return;

   for(int p = PositionsTotal() - 1; p >= 0; p--)
     {
      ulong ticket = PositionGetTicket(p);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      long magic = (long)PositionGetInteger(POSITION_MAGIC);
      double trailPips = -1;
      for(int m = 0; m < ArraySize(g_panelMagics); m++)
        {
         if(g_panelMagics[m] == magic)
           {
            trailPips = g_panelTrailingPips[m];
            break;
           }
        }
      if(trailPips <= 0)
         continue; // not a panel-managed position

      string symbol = PositionGetString(POSITION_SYMBOL);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      bool isBuy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);

      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double stepDistance = trailPips * PanelPipSize;

      double profitDistance = isBuy ? (bid - entry) : (entry - ask);
      int steps = (int)MathFloor(profitDistance / stepDistance + 0.0000001);
      if(steps < 1)
         continue;

      double locked = (steps - 1) * stepDistance;
      double candidate = NormalizeDouble(isBuy ? entry + locked : entry - locked, 2);
      bool improved = isBuy ? (candidate > sl) : (candidate < sl);
      if(!improved)
         continue;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);
      request.action   = TRADE_ACTION_SLTP;
      request.position = ticket;
      request.symbol    = symbol;
      request.sl        = candidate;
      request.tp        = tp;

      bool ok = OrderSend(request, result);
      if(!ok || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("Panel: trailing SL FAILED for ticket %d retcode=%d comment='%s'",
                     (int)ticket, result.retcode, result.comment);
      else
         PrintFormat("Panel: trailing SL -> %.2f for ticket %d (magic=%d)", candidate, (int)ticket, (int)magic);
     }
  }

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   if(sparam == PANEL_PREFIX + "BuyBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelPlaceZone("BUY");
     }
   else if(sparam == PANEL_PREFIX + "SellBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelPlaceZone("SELL");
     }
  }
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| ManualZonePanelEA.mq5                                            |
//|                                                                  |
//| Standalone, self-contained EA - completely independent of        |
//| TelegramBridgeEA.mq5 (no shared code, no shared files/folders,   |
//| no shared magic range). Drop it on its own chart if you want a   |
//| manual BUY/SELL zone panel without touching the Python-driven    |
//| bridge EA at all.                                                 |
//|                                                                  |
//| An on-chart panel with four editable fields - Strefa             |
//| ("niska-wysoka", e.g. 4420-4425), SL (pips), Trailing (pips),    |
//| Krok siatki ($) - and BUY/SELL buttons. On click it builds the   |
//| same kind of order grid the Python bot's order_planner.py would  |
//| (price levels every "Krok siatki" across the zone, ONE shared SL |
//| "SL (pips)" from the worse edge, lot size tiering mirroring      |
//| LOT_SIZE/LOT_TIER_ORDERS/LOT_SCALING_MODE/LOT_MULTIPLIER via the |
//| Panel* inputs below) and places it with native OrderSend() calls |
//| - same MARKET-fallback for an entry too close to the current     |
//| price as the bridge EA uses.                                     |
//|                                                                  |
//| No TP is set on these orders. Exits happen only through a        |
//| STEPPED trailing stop (PanelUpdateTrailingStops(), run every     |
//| OnTimer tick) - untouched below "Trailing (pips)" profit, jumps  |
//| to breakeven at exactly that many pips, then another jump of the |
//| same size every further "Trailing (pips)" of profit. Tightening  |
//| only. This is the exact same algorithm as the Python bot's       |
//| EXIT_MODE=trailing_stop (mt5_executor.check_trailing_stops).     |
//|                                                                  |
//| Which trailing_pips value belongs to which position is kept only |
//| in memory (magic -> trailing_pips), not in a file - a terminal/  |
//| EA restart loses it for positions already open from before the   |
//| restart (a fresh panel click always works immediately).          |
//|                                                                  |
//| Zone visibility: each click also draws the zone (rectangle), its |
//| shared SL (dashed horizontal line) and a text label on the chart |
//| - removed automatically once nothing is left open for that       |
//| zone's magic (PanelCleanupFinishedZones, checked every timer     |
//| tick).                                                            |
//|                                                                  |
//| Two draggable price lines (ZoneLowLine/ZoneHighLine) let you set |
//| the zone by dragging on the chart instead of typing - the        |
//| "Strefa" field updates live to match their prices as you drag    |
//| (PanelSyncZoneFieldFromLines, fired on CHARTEVENT_OBJECT_DRAG).  |
//| You can still type into the field directly too.                  |
//+------------------------------------------------------------------+
#property copyright "Telegram MT5 signal bot"
#property strict

input double PanelDefaultSlPips       = 60;    // default value shown in the panel's SL field
input double PanelDefaultTrailingPips = 36;    // default value shown in the panel's Trailing field
input double PanelDefaultStepDollars  = 0.5;   // default value shown in the panel's Step field
input double PanelPipSize             = 0.1;   // price value of 1 pip - must match PIP_SIZE in .env / your broker's gold quoting
input double PanelLotBase             = 0.01;  // base lot for the panel's own order grid (mirrors LOT_SIZE)
input int    PanelLotTierOrders       = 3;     // mirrors LOT_TIER_ORDERS
input string PanelLotScalingMode      = "additive"; // "additive" or "multiplier" - mirrors LOT_SCALING_MODE
input double PanelLotMultiplier       = 1.2;   // mirrors LOT_MULTIPLIER
input long   PanelMagicBase           = 500000; // panel orders get PanelMagicBase+N, N incrementing per click
input int    PanelDeviationPoints     = 20;
input int    PollSeconds              = 1;     // how often the trailing-stop loop runs
input int    PanelX                   = 10;    // panel position (pixels from the corner) - nudge here if it overlaps the chart's own toolbar/OHLC info
input int    PanelY                   = 130;

long   g_panelNextMagic = 0;
long   g_panelMagics[];
double g_panelTrailingPips[];

#define PANEL_PREFIX "TgManualPanel_"

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(PollSeconds);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("WARNING: Algo Trading is currently OFF - this EA cannot place orders until it's enabled.");
   PanelCreate();
   PanelCreateZoneLines();
   PrintFormat("ManualZonePanelEA started on %s", Symbol());
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
   PanelUpdateTrailingStops();
   PanelCleanupFinishedZones();
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
//| Places one order per level: a normal pending order, except when  |
//| the entry price is within the broker's minimum stop/freeze       |
//| distance of the current price - that one entry fills at MARKET   |
//| instead (same SL), rather than being rejected for being too      |
//| close. Mirrors TelegramBridgeEA.mq5's HandleOpenOrders.          |
//+------------------------------------------------------------------+
void PlaceOrders(long magic, string symbol, string comment, int deviation,
                  string direction, double &entries[], double &lots[], double slPrice, int count)
  {
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   long stopsLevelPts = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freezeLevelPts = SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double minDistance = MathMax(stopsLevelPts, freezeLevelPts) * point;

   for(int i = 0; i < count; i++)
     {
      double entry = entries[i];
      double lot = lots[i];

      double refPrice = (direction == "BUY") ? ask : bid;
      bool atMarket = (MathAbs(entry - refPrice) <= minDistance);

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.symbol  = symbol;
      request.volume   = lot;
      request.sl       = slPrice;
      request.tp       = 0.0;
      request.magic     = magic;
      request.comment   = comment;

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
         PrintFormat("Panel: %s order FAILED %s @ %.2f retcode=%d comment='%s'",
                     atMarket ? "MARKET" : "PENDING", direction, entry, result.retcode, result.comment);
      else
         PrintFormat("Panel: placed %s %s @ %.2f (requested %.2f) sl=%.2f lot=%.2f ticket=%d",
                     atMarket ? "MARKET" : "PENDING", direction, result.price, entry, slPrice, lot, (int)result.order);
     }
  }

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
   // Must stay selectable and NOT hidden - OBJPROP_HIDDEN blocks normal
   // (non-Ctrl) mouse selection, which is what let you click into the box
   // and type in the first place.
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, true);
   ObjectSetInteger(0, full, OBJPROP_READONLY, false);
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
  }

//+------------------------------------------------------------------+
void PanelCreate()
  {
   int x = PanelX, y = PanelY, rowH = 24, labelW = 130, editW = 90;
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
//| Two draggable horizontal price lines - drag them to set the zone |
//| on the chart instead of typing prices by hand. Placed near the   |
//| current Bid on start-up so they're visible without scrolling.    |
//| The "Strefa" field is kept in sync with their prices live (see   |
//| PanelSyncZoneFieldFromLines, called from OnChartEvent on drag).  |
//+------------------------------------------------------------------+
void PanelCreateZoneLines()
  {
   double bid = SymbolInfoDouble(Symbol(), SYMBOL_BID);
   double halfWidth = 2.5;

   string lowName = PANEL_PREFIX + "ZoneLowLine";
   ObjectCreate(0, lowName, OBJ_HLINE, 0, 0, NormalizeDouble(bid - halfWidth, 2));
   ObjectSetInteger(0, lowName, OBJPROP_COLOR, clrDodgerBlue);
   ObjectSetInteger(0, lowName, OBJPROP_STYLE, STYLE_DASHDOT);
   ObjectSetInteger(0, lowName, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, lowName, OBJPROP_SELECTABLE, true);
   ObjectSetString(0, lowName, OBJPROP_TOOLTIP, "Przeciagnij - granica strefy (dolna lub gorna)");

   string highName = PANEL_PREFIX + "ZoneHighLine";
   ObjectCreate(0, highName, OBJ_HLINE, 0, 0, NormalizeDouble(bid + halfWidth, 2));
   ObjectSetInteger(0, highName, OBJPROP_COLOR, clrOrange);
   ObjectSetInteger(0, highName, OBJPROP_STYLE, STYLE_DASHDOT);
   ObjectSetInteger(0, highName, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, highName, OBJPROP_SELECTABLE, true);
   ObjectSetString(0, highName, OBJPROP_TOOLTIP, "Przeciagnij - granica strefy (dolna lub gorna)");

   PanelSyncZoneFieldFromLines();
  }

//+------------------------------------------------------------------+
//| Reads both zone lines' current prices and writes them into the    |
//| "Strefa" field as "niska-wysoka" - sorted, so it doesn't matter   |
//| which line is physically above the other at any given moment.     |
//+------------------------------------------------------------------+
void PanelSyncZoneFieldFromLines()
  {
   double lowPrice = ObjectGetDouble(0, PANEL_PREFIX + "ZoneLowLine", OBJPROP_PRICE);
   double highPrice = ObjectGetDouble(0, PANEL_PREFIX + "ZoneHighLine", OBJPROP_PRICE);
   if(lowPrice > highPrice)
     {
      double tmp = lowPrice;
      lowPrice = highPrice;
      highPrice = tmp;
     }
   ObjectSetString(0, PANEL_PREFIX + "ZoneEdit", OBJPROP_TEXT, StringFormat("%.2f-%.2f", lowPrice, highPrice));
   ChartRedraw(0);
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
//| TP), and places it via PlaceOrders() - MARKET-fallback for an     |
//| entry too close to price applies here too.                        |
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

   double lots[];
   ArrayResize(lots, kept);
   for(int i = 0; i < kept; i++)
     {
      if(PanelLotScalingMode == "multiplier")
         lots[i] = NormalizeDouble(PanelLotBase * MathPow(PanelLotMultiplier, tiers[i]), 2);
      else
         lots[i] = NormalizeDouble(PanelLotBase * (tiers[i] + 1), 2);
     }

   long magic = PanelMagicBase + g_panelNextMagic;
   g_panelNextMagic++;
   int slot = ArraySize(g_panelMagics);
   ArrayResize(g_panelMagics, slot + 1);
   ArrayResize(g_panelTrailingPips, slot + 1);
   g_panelMagics[slot] = magic;
   g_panelTrailingPips[slot] = trailPips;

   string comment = "panel-" + (string)magic;
   PlaceOrders(magic, Symbol(), comment, PanelDeviationPoints, direction, levels, lots, slPrice, kept);
   PanelDrawZone(magic, direction, zoneLow, zoneHigh, slPrice);

   PanelSetStatus(StringFormat(
      "Wystawiono %d zlec. %s, SL=%.2f, trailing=%.0f pips (magic=%d)",
      kept, direction, slPrice, trailPips, (int)magic));
  }

//+------------------------------------------------------------------+
//| Draws the zone (rectangle, entry area), its shared SL (dashed     |
//| horizontal line) and a text label on the chart, named per magic   |
//| so several zones can coexist - cleaned up automatically once no   |
//| pending orders/positions are left for that magic (see             |
//| PanelCleanupFinishedZones).                                       |
//+------------------------------------------------------------------+
void PanelDrawZone(long magic, string direction, double zoneLow, double zoneHigh, double slPrice)
  {
   color zoneColor = (direction == "BUY") ? clrDodgerBlue : clrOrange;
   datetime t1 = TimeCurrent();
   datetime t2 = t1 + PeriodSeconds() * 50;

   string zoneName = PANEL_PREFIX + "Zone_" + (string)magic;
   ObjectCreate(0, zoneName, OBJ_RECTANGLE, 0, t1, zoneHigh, t2, zoneLow);
   ObjectSetInteger(0, zoneName, OBJPROP_COLOR, zoneColor);
   ObjectSetInteger(0, zoneName, OBJPROP_FILL, true);
   ObjectSetInteger(0, zoneName, OBJPROP_BACK, true);
   ObjectSetInteger(0, zoneName, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, zoneName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, zoneName, OBJPROP_HIDDEN, true);

   string slName = PANEL_PREFIX + "SL_" + (string)magic;
   ObjectCreate(0, slName, OBJ_HLINE, 0, 0, slPrice);
   ObjectSetInteger(0, slName, OBJPROP_COLOR, clrRed);
   ObjectSetInteger(0, slName, OBJPROP_STYLE, STYLE_DASH);
   ObjectSetInteger(0, slName, OBJPROP_WIDTH, 1);
   ObjectSetInteger(0, slName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, slName, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, slName, OBJPROP_BACK, true);

   string labelName = PANEL_PREFIX + "Label_" + (string)magic;
   ObjectCreate(0, labelName, OBJ_TEXT, 0, t1, zoneHigh);
   ObjectSetString(0, labelName, OBJPROP_TEXT, StringFormat(" %s %.2f-%.2f", direction, zoneLow, zoneHigh));
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, zoneColor);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, labelName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, labelName, OBJPROP_HIDDEN, true);

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| True while magic still has a pending order or open position.     |
//+------------------------------------------------------------------+
bool PanelHasOpenTradesForMagic(long magic)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket != 0 && OrderGetInteger(ORDER_MAGIC) == magic)
         return true;
     }
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket != 0 && PositionSelectByTicket(ticket) && PositionGetInteger(POSITION_MAGIC) == magic)
         return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Removes a zone's drawing (rectangle/SL line/label) and stops      |
//| tracking its trailing_pips once nothing is left open for it -     |
//| same idea as the Python bot deactivating a finished campaign.     |
//+------------------------------------------------------------------+
void PanelCleanupFinishedZones()
  {
   for(int m = ArraySize(g_panelMagics) - 1; m >= 0; m--)
     {
      long magic = g_panelMagics[m];
      if(PanelHasOpenTradesForMagic(magic))
         continue;

      ObjectDelete(0, PANEL_PREFIX + "Zone_" + (string)magic);
      ObjectDelete(0, PANEL_PREFIX + "SL_" + (string)magic);
      ObjectDelete(0, PANEL_PREFIX + "Label_" + (string)magic);

      int last = ArraySize(g_panelMagics) - 1;
      g_panelMagics[m] = g_panelMagics[last];
      g_panelTrailingPips[m] = g_panelTrailingPips[last];
      ArrayResize(g_panelMagics, last);
      ArrayResize(g_panelTrailingPips, last);
     }
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Stepped trailing stop for panel-placed positions (matched by      |
//| magic against g_panelMagics): untouched below trailPips profit,   |
//| jumps to breakeven at exactly trailPips, then another jump of the |
//| same size every further trailPips of profit. Tightening only.     |
//| Same algorithm as the Python bot's EXIT_MODE=trailing_stop         |
//| (mt5_executor.check_trailing_stops). Run every OnTimer tick.       |
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
   if(id == CHARTEVENT_OBJECT_DRAG)
     {
      if(sparam == PANEL_PREFIX + "ZoneLowLine" || sparam == PANEL_PREFIX + "ZoneHighLine")
         PanelSyncZoneFieldFromLines();
      return;
     }

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

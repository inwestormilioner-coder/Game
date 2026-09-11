//+------------------------------------------------------------------+
//| ManualZonePanelEA.mq5                                            |
//|                                                                  |
//| Standalone, self-contained EA - completely independent of        |
//| TelegramBridgeEA.mq5 (no shared code, no shared files/folders,   |
//| no shared magic range). Drop it on its own chart if you want a   |
//| manual BUY/SELL zone panel without touching the Python-driven    |
//| bridge EA at all.                                                 |
//|                                                                  |
//| Fully click-driven - no typing, no dragging objects (both proved |
//| unreliable in some MT5 setups/themes, so this avoids them        |
//| entirely). Panel sits in the top-right corner by default          |
//| (PanelOnRight/PanelRightMargin), sized to comfortably fit every   |
//| control (PANEL_WIDTH/PANEL_HEIGHT below).                         |
//|                                                                  |
//|   - Click "Zaznacz strefe", then click two points on the chart - |
//|     those become the zone's low/high price (order doesn't        |
//|     matter, sorted automatically). A dotted line marks the first |
//|     point as soon as you place it; once both are set, the whole  |
//|     zone is outlined on the chart right away (before you even    |
//|     click BUY/SELL) so you can see exactly what you're about to  |
//|     trade - PanelDrawPickPreview/PanelClearPickPreview.           |
//|   - SL (pips) / Trailing (pips) / Krok siatki ($) are each a      |
//|     value with "-"/"+" buttons next to it.                        |
//|   - BUY/SELL builds the same kind of order grid the Python bot's |
//|     order_planner.py would (price levels every "Krok siatki"     |
//|     across the zone, ONE shared SL "SL (pips)" from the worse    |
//|     edge, lot size tiering mirroring LOT_SIZE/LOT_TIER_ORDERS/    |
//|     LOT_SCALING_MODE/LOT_MULTIPLIER via the Panel* inputs below) |
//|     and places it with native OrderSend() calls - same MARKET-   |
//|     fallback for an entry too close to the current price as the  |
//|     bridge EA uses.                                               |
//|   - "Zamknij zlecenia oczekujace" cancels every still-pending     |
//|     order this EA has placed (magic >= PanelMagicBase) - open      |
//|     positions are left alone, only unfilled pending orders are    |
//|     removed (PanelCloseAllPending).                                |
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
//| Zone visibility: each placed order also draws the zone            |
//| (rectangle), its shared SL (dashed horizontal line) and a text   |
//| label on the chart, named per magic so several zones can coexist |
//| - removed automatically once nothing is left open for that       |
//| zone's magic (PanelCleanupFinishedZones, checked every timer     |
//| tick).                                                            |
//+------------------------------------------------------------------+
#property copyright "Telegram MT5 signal bot"
#property strict

#define PANEL_WIDTH  380
#define PANEL_HEIGHT 330
#define PANEL_PREFIX "TgManualPanel_"

input double PanelDefaultSlPips       = 60;    // starting value for the SL (pips) stepper
input double PanelDefaultTrailingPips = 36;    // starting value for the Trailing (pips) stepper
input double PanelDefaultStepDollars  = 0.5;   // starting value for the Krok siatki ($) stepper
input double PanelPipSize             = 0.1;   // price value of 1 pip - must match PIP_SIZE in .env / your broker's gold quoting
input double PanelLotBase             = 0.01;  // base lot for the panel's own order grid (mirrors LOT_SIZE)
input int    PanelLotTierOrders       = 3;     // mirrors LOT_TIER_ORDERS
input string PanelLotScalingMode      = "additive"; // "additive" or "multiplier" - mirrors LOT_SCALING_MODE
input double PanelLotMultiplier       = 1.2;   // mirrors LOT_MULTIPLIER
input long   PanelMagicBase           = 500000; // panel orders get PanelMagicBase+N, N incrementing per click
input int    PanelDeviationPoints     = 20;
input int    PollSeconds              = 1;     // how often the trailing-stop loop runs
input bool   PanelOnRight             = true;  // true: panel docks to the top-right corner (PanelRightMargin); false: uses PanelX/PanelY from the top-left
input int    PanelRightMargin         = 20;    // pixels from the chart's right edge, only used when PanelOnRight=true
input int    PanelX                   = 10;    // panel position from the LEFT edge - only used when PanelOnRight=false
input int    PanelY                   = 130;   // panel position from the TOP edge (nudge if it overlaps the chart's own toolbar/OHLC info)

long   g_panelNextMagic = 0;
long   g_panelMagics[];
double g_panelTrailingPips[];

double g_zoneLow = 0;
double g_zoneHigh = 0;
int    g_awaitingClick = 0;   // 0 = idle, 1 = waiting for the first point, 2 = waiting for the second
double g_pendingFirstPrice = 0;

double g_slPips = 0;
double g_trailPips = 0;
double g_stepDollars = 0;

int g_panelLeft = 0, g_panelTop = 0, g_panelRight = 0, g_panelBottom = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(PollSeconds);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("WARNING: Algo Trading is currently OFF - this EA cannot place orders until it's enabled.");
   g_slPips = PanelDefaultSlPips;
   g_trailPips = PanelDefaultTrailingPips;
   g_stepDollars = PanelDefaultStepDollars;

   int x = PanelX;
   if(PanelOnRight)
     {
      long chartWidth = ChartGetInteger(0, CHART_WIDTH_IN_PIXELS);
      x = (int)(chartWidth - PANEL_WIDTH - PanelRightMargin);
      if(x < 5)
         x = 5;
     }
   PanelCreate(x, PanelY);
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
void PanelCreateLabel(string name, int x, int y, string text, int fontSize = 10)
  {
   string full = PANEL_PREFIX + name;
   ObjectCreate(0, full, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, full, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, full, OBJPROP_TEXT, text);
   ObjectSetInteger(0, full, OBJPROP_FONTSIZE, fontSize);
   ObjectSetInteger(0, full, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, full, OBJPROP_ZORDER, 10);
  }

//+------------------------------------------------------------------+
void PanelCreateButton(string name, int x, int y, int w, int h, string text, color clr, int fontSize = 10)
  {
   string full = PANEL_PREFIX + name;
   ObjectCreate(0, full, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, full, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, full, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, full, OBJPROP_YSIZE, h);
   ObjectSetString(0, full, OBJPROP_TEXT, text);
   ObjectSetInteger(0, full, OBJPROP_FONTSIZE, fontSize);
   ObjectSetInteger(0, full, OBJPROP_BGCOLOR, clr);
   ObjectSetInteger(0, full, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, full, OBJPROP_ZORDER, 10);
  }

//+------------------------------------------------------------------+
//| Lays out every control top-to-bottom, each on its own row so      |
//| nothing overlaps regardless of label text length. (x,y) is the    |
//| panel's top-left corner, computed in OnInit from PanelOnRight.    |
//+------------------------------------------------------------------+
void PanelCreate(int x, int y)
  {
   int labelW = 145, valW = 50, smallBtnW = 32, smallBtnH = 28, rowH = 40;
   int margin = 10;

   // Remember the panel's screen rectangle so PanelHandleChartClick can
   // ignore clicks that land on it - clicking a button also fires a plain
   // CHARTEVENT_CLICK at the same pixel coordinates, which would otherwise
   // get misread as a zone-picking click on the button's own position.
   g_panelLeft = x - margin;
   g_panelTop = y - margin;
   g_panelRight = g_panelLeft + PANEL_WIDTH;
   g_panelBottom = g_panelTop + PANEL_HEIGHT;

   ObjectCreate(0, PANEL_PREFIX + "Bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_XDISTANCE, x - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_YDISTANCE, y - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_XSIZE, PANEL_WIDTH);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_YSIZE, PANEL_HEIGHT);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BGCOLOR, clrWhiteSmoke);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_COLOR, clrSilver);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BACK, true);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_ZORDER, 0);

   PanelCreateLabel("Title", x, y, "STREFA MANUALNA", 11);
   int rowY = y + 26;

   PanelCreateLabel("LblZone", x, rowY, "Strefa:");
   PanelCreateLabel("ZoneValueLbl", x + 150, rowY, "-- brak, kliknij Zaznacz --");
   rowY += rowH;

   PanelCreateButton("PickZoneBtn", x, rowY, PANEL_WIDTH - 2 * margin, 32, "ZAZNACZ STREFE (2 kliknieca na wykresie)", clrKhaki);
   rowY += 38;

   PanelCreateLabel("LblSl", x, rowY, "SL (pips):");
   PanelCreateLabel("SlValueLbl", x + 150, rowY, DoubleToString(g_slPips, 0));
   PanelCreateButton("SlMinusBtn", x + 215, rowY - 4, smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("SlPlusBtn", x + 215 + smallBtnW + 6, rowY - 4, smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblTrail", x, rowY, "Trailing (pips):");
   PanelCreateLabel("TrailValueLbl", x + 150, rowY, DoubleToString(g_trailPips, 0));
   PanelCreateButton("TrailMinusBtn", x + 215, rowY - 4, smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("TrailPlusBtn", x + 215 + smallBtnW + 6, rowY - 4, smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblStep", x, rowY, "Krok siatki ($):");
   PanelCreateLabel("StepValueLbl", x + 150, rowY, DoubleToString(g_stepDollars, 2));
   PanelCreateButton("StepMinusBtn", x + 215, rowY - 4, smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("StepPlusBtn", x + 215 + smallBtnW + 6, rowY - 4, smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH + 6;

   int tradeBtnW = (PANEL_WIDTH - 2 * margin - 10) / 2;
   PanelCreateButton("BuyBtn", x, rowY, tradeBtnW, 36, "BUY", clrLimeGreen, 12);
   PanelCreateButton("SellBtn", x + tradeBtnW + 10, rowY, tradeBtnW, 36, "SELL", clrTomato, 12);
   rowY += 46;

   PanelCreateButton("ClosePendingBtn", x, rowY, PANEL_WIDTH - 2 * margin, 30, "ZAMKNIJ ZLECENIA OCZEKUJACE", clrGold);
   rowY += 38;

   PanelCreateLabel("Status", x, rowY, "Gotowy - kliknij 'Zaznacz strefe'.", 9);
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
void PanelSetZoneValueLabel()
  {
   string text;
   if(g_zoneLow > 0 && g_zoneHigh > 0)
      text = StringFormat("%.2f - %.2f", g_zoneLow, g_zoneHigh);
   else
      text = "-- brak, kliknij Zaznacz --";
   ObjectSetString(0, PANEL_PREFIX + "ZoneValueLbl", OBJPROP_TEXT, text);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Removes the live picking-preview objects (first-point marker      |
//| and/or the zone outline drawn once both points are set) - called  |
//| before starting a fresh pick and again once an order is actually  |
//| placed (PanelDrawZone then draws the real, magic-specific one).   |
//+------------------------------------------------------------------+
void PanelClearPickPreview()
  {
   ObjectDelete(0, PANEL_PREFIX + "PickPoint1");
   ObjectDelete(0, PANEL_PREFIX + "PreviewZone");
   ObjectDelete(0, PANEL_PREFIX + "PreviewLabel");
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Arms two-click zone picking - PanelHandleChartClick below reads   |
//| the next two plain chart clicks as the zone's two price bounds.   |
//+------------------------------------------------------------------+
void PanelStartZonePick()
  {
   PanelClearPickPreview();
   g_zoneLow = 0;
   g_zoneHigh = 0;
   g_pendingFirstPrice = 0;
   g_awaitingClick = 1;
   PanelSetZoneValueLabel();
   PanelSetStatus("Kliknij PIERWSZA granice strefy na wykresie.");
  }

//+------------------------------------------------------------------+
//| Converts a plain chart click's pixel coordinates to a price and,  |
//| while zone-picking is armed, records it as the first or second    |
//| zone boundary. No-op otherwise (ignores ordinary chart clicks).   |
//| Draws a dotted marker line after the first click, and the full    |
//| zone outline (rectangle + label) after the second - so the zone   |
//| is clearly visible on the chart before you even click BUY/SELL.   |
//+------------------------------------------------------------------+
void PanelHandleChartClick(int px, int py)
  {
   if(g_awaitingClick == 0)
      return;

   // Ignore clicks landing on the panel itself (buttons/labels/background)
   // - only a click on the actual chart counts as a zone-boundary pick.
   if(px >= g_panelLeft && px <= g_panelRight && py >= g_panelTop && py <= g_panelBottom)
      return;

   int sub;
   datetime t;
   double price;
   if(!ChartXYToTimePrice(0, px, py, sub, t, price))
      return;

   if(g_awaitingClick == 1)
     {
      g_pendingFirstPrice = price;
      g_awaitingClick = 2;

      ObjectCreate(0, PANEL_PREFIX + "PickPoint1", OBJ_HLINE, 0, 0, price);
      ObjectSetInteger(0, PANEL_PREFIX + "PickPoint1", OBJPROP_COLOR, clrGray);
      ObjectSetInteger(0, PANEL_PREFIX + "PickPoint1", OBJPROP_STYLE, STYLE_DOT);
      ObjectSetInteger(0, PANEL_PREFIX + "PickPoint1", OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, PANEL_PREFIX + "PickPoint1", OBJPROP_BACK, true);

      PanelSetStatus(StringFormat("Pierwsza granica: %.2f. Kliknij DRUGA granice strefy.", price));
      return;
     }

   g_zoneLow = NormalizeDouble(MathMin(g_pendingFirstPrice, price), 2);
   g_zoneHigh = NormalizeDouble(MathMax(g_pendingFirstPrice, price), 2);
   g_awaitingClick = 0;
   ObjectDelete(0, PANEL_PREFIX + "PickPoint1");
   PanelDrawPickPreview();
   PanelSetZoneValueLabel();
   PanelSetStatus(StringFormat("Strefa ustawiona: %.2f - %.2f. Kliknij BUY albo SELL.", g_zoneLow, g_zoneHigh));
  }

//+------------------------------------------------------------------+
//| Outlines the currently-picked (not yet placed) zone on the chart  |
//| - neutral gold color since direction (BUY/SELL) isn't chosen yet. |
//+------------------------------------------------------------------+
void PanelDrawPickPreview()
  {
   datetime t1 = TimeCurrent();
   datetime t2 = t1 + PeriodSeconds() * 50;

   string zoneName = PANEL_PREFIX + "PreviewZone";
   ObjectCreate(0, zoneName, OBJ_RECTANGLE, 0, t1, g_zoneHigh, t2, g_zoneLow);
   ObjectSetInteger(0, zoneName, OBJPROP_COLOR, clrGoldenrod);
   ObjectSetInteger(0, zoneName, OBJPROP_FILL, true);
   ObjectSetInteger(0, zoneName, OBJPROP_BACK, true);
   ObjectSetInteger(0, zoneName, OBJPROP_RAY_RIGHT, true);
   ObjectSetInteger(0, zoneName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, zoneName, OBJPROP_HIDDEN, true);

   string labelName = PANEL_PREFIX + "PreviewLabel";
   ObjectCreate(0, labelName, OBJ_TEXT, 0, t1, g_zoneHigh);
   ObjectSetString(0, labelName, OBJPROP_TEXT, StringFormat(" strefa %.2f-%.2f (wybierz BUY/SELL)", g_zoneLow, g_zoneHigh));
   ObjectSetInteger(0, labelName, OBJPROP_COLOR, clrDarkGoldenrod);
   ObjectSetInteger(0, labelName, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, labelName, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, labelName, OBJPROP_HIDDEN, true);

   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
void PanelAdjustSl(double delta)
  {
   g_slPips = MathMax(5.0, g_slPips + delta);
   ObjectSetString(0, PANEL_PREFIX + "SlValueLbl", OBJPROP_TEXT, DoubleToString(g_slPips, 0));
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
void PanelAdjustTrail(double delta)
  {
   g_trailPips = MathMax(5.0, g_trailPips + delta);
   ObjectSetString(0, PANEL_PREFIX + "TrailValueLbl", OBJPROP_TEXT, DoubleToString(g_trailPips, 0));
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
void PanelAdjustStep(double delta)
  {
   g_stepDollars = MathMax(0.1, NormalizeDouble(g_stepDollars + delta, 2));
   ObjectSetString(0, PANEL_PREFIX + "StepValueLbl", OBJPROP_TEXT, DoubleToString(g_stepDollars, 2));
   ChartRedraw(0);
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
//| Uses the zone/SL/trailing/step currently picked via the panel to  |
//| build the same kind of order grid as order_planner.plan_orders()  |
//| (EXIT_MODE=trailing_stop shape - no TP), and places it via         |
//| PlaceOrders() - MARKET-fallback for an entry too close to price    |
//| applies here too.                                                  |
//+------------------------------------------------------------------+
void PanelPlaceZone(string direction)
  {
   if(g_zoneLow <= 0 || g_zoneHigh <= 0 || g_zoneLow == g_zoneHigh)
     {
      PanelSetStatus("Blad: najpierw zaznacz strefe (przycisk 'Zaznacz strefe', 2 kliknieca na wykresie).");
      return;
     }

   double zoneLow = g_zoneLow;
   double zoneHigh = g_zoneHigh;
   double slPips = g_slPips;
   double trailPips = g_trailPips;
   double step = g_stepDollars;

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
   PanelClearPickPreview();
   PanelDrawZone(magic, direction, zoneLow, zoneHigh, slPrice);

   // Clear the picked zone so the next click on BUY/SELL can't accidentally
   // reuse a stale zone - a fresh "Zaznacz strefe" is required each time.
   g_zoneLow = 0;
   g_zoneHigh = 0;
   PanelSetZoneValueLabel();

   PanelSetStatus(StringFormat(
      "Wystawiono %d zlec. %s, SL=%.2f, trailing=%.0f pips (magic=%d)",
      kept, direction, slPrice, trailPips, (int)magic));
  }

//+------------------------------------------------------------------+
//| Cancels every still-pending order this EA placed (magic >=        |
//| PanelMagicBase) - open positions are left alone, only unfilled    |
//| pending orders are removed. Zone drawings/trailing tracking for   |
//| any magic left with nothing open clean themselves up on the next  |
//| timer tick (PanelCleanupFinishedZones).                            |
//+------------------------------------------------------------------+
void PanelCloseAllPending()
  {
   int closedCount = 0;
   int failedCount = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;
      long magic = OrderGetInteger(ORDER_MAGIC);
      if(magic < PanelMagicBase)
         continue;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);
      request.action = TRADE_ACTION_REMOVE;
      request.order = ticket;

      bool ok = OrderSend(request, result);
      if(ok && result.retcode == TRADE_RETCODE_DONE)
        {
         closedCount++;
        }
      else
        {
         failedCount++;
         PrintFormat("Panel: nie udalo sie usunac zlecenia oczekujacego %d retcode=%d comment='%s'",
                     (int)ticket, result.retcode, result.comment);
        }
     }

   string msg = StringFormat("Zamknieto %d zlecen oczekujacych.", closedCount);
   if(failedCount > 0)
      msg += StringFormat(" %d bledow - zobacz log Eksperci.", failedCount);
   PanelSetStatus(msg);
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
   if(id == CHARTEVENT_CLICK)
     {
      PanelHandleChartClick((int)lparam, (int)dparam);
      return;
     }

   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   if(sparam == PANEL_PREFIX + "PickZoneBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelStartZonePick();
     }
   else if(sparam == PANEL_PREFIX + "SlMinusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustSl(-5);
     }
   else if(sparam == PANEL_PREFIX + "SlPlusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustSl(5);
     }
   else if(sparam == PANEL_PREFIX + "TrailMinusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustTrail(-5);
     }
   else if(sparam == PANEL_PREFIX + "TrailPlusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustTrail(5);
     }
   else if(sparam == PANEL_PREFIX + "StepMinusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustStep(-0.1);
     }
   else if(sparam == PANEL_PREFIX + "StepPlusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustStep(0.1);
     }
   else if(sparam == PANEL_PREFIX + "BuyBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelPlaceZone("BUY");
     }
   else if(sparam == PANEL_PREFIX + "SellBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelPlaceZone("SELL");
     }
   else if(sparam == PANEL_PREFIX + "ClosePendingBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelCloseAllPending();
     }
  }
//+------------------------------------------------------------------+

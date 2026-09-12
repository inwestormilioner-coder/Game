//+------------------------------------------------------------------+
//| ManualZonePanelEA.mq5                                            |
//|                                                                  |
//| Standalone, self-contained EA - completely independent of        |
//| TelegramBridgeEA.mq5 (no shared code, no shared files/folders,   |
//| no shared magic range). Drop it on its own chart if you want a   |
//| manual BUY/SELL zone panel without touching the Python-driven    |
//| bridge EA at all.                                                 |
//|                                                                  |
//| Fully click-driven for everything zone/trade-related - no typing  |
//| (OBJ_EDIT text boxes proved unreliable in some MT5 setups/themes, |
//| so this avoids them entirely). Panel sits in the top-right corner |
//| by default (PanelOnRight/PanelRightMargin), sized to comfortably  |
//| fit every control (PANEL_WIDTH/PANEL_HEIGHT below).                |
//|                                                                  |
//| The panel itself IS draggable and minimizable, unlike the zone/   |
//| trade controls inside it:                                         |
//|   - Grab the title bar (top strip, not the "-"/"+" button on it)  |
//|     and drop it anywhere - dragged MANUALLY via CHARTEVENT_MOUSE_ |
//|     MOVE (PanelHandleMouseMove/g_titleDragging), not native MT5    |
//|     object dragging (OBJPROP_SELECTABLE + CHARTEVENT_OBJECT_DRAG   |
//|     proved unreliable for this object type in this EA's testing,   |
//|     the same way OBJ_EDIT/OBJ_HLINE dragging did earlier).         |
//|   - The "-"/"+" button in the title bar (PanelToggleMinimize)      |
//|     collapses the panel to just that title strip - every other     |
//|     control is parked off-screen (PanelBodyY), not deleted, so     |
//|     restoring is instant and never resets a value.                |
//|   - TitleBar and BodyCatcher are the panel's only two foreground   |
//|     (OBJPROP_BACK=false) objects, sitting at a lower ZORDER than   |
//|     every button/label (10) - a click on empty panel space (not   |
//|     on a button) now lands on the panel itself instead of leaking  |
//|     through to the chart underneath (which is what made clicking  |
//|     the panel feel like clicking the chart before this existed).  |
//|     Bg stays BACK=true as before (a back object can't be selected/ |
//|     dragged in MT5 either way).                                    |
//|                                                                  |
//|   - Click "Zaznacz strefe", then click two points on the chart - |
//|     those become the zone's low/high price (order doesn't        |
//|     matter, sorted automatically). A dotted line marks the first |
//|     point as soon as you place it; once both are set, the whole  |
//|     zone is outlined on the chart right away (before you even    |
//|     click BUY/SELL) so you can see exactly what you're about to  |
//|     trade - PanelDrawPickPreview/PanelClearPickPreview.           |
//|   - SL (pips) / Trailing (pips) / Blokada zysku (pips) / Krok     |
//|     siatki ($) / Rozszerz gora ($) / Rozszerz dol ($) are each a  |
//|     value with "-"/"+" buttons next to it.                        |
//|   - BUY/SELL builds the same kind of order grid the Python bot's |
//|     order_planner.py would (price levels every "Krok siatki"     |
//|     across the zone, extended past the zone's own top/bottom edge |
//|     by "Rozszerz gora ($)"/"Rozszerz dol ($)" - mirrors            |
//|     zone_extend_front/zone_extend_back, SL unaffected by the      |
//|     extension either way - ONE shared SL "SL (pips)" from the     |
//|     worse edge of the ORIGINAL (unextended) zone, lot size         |
//|     tiering mirroring LOT_SIZE/LOT_TIER_ORDERS/LOT_SCALING_MODE/   |
//|     LOT_MULTIPLIER via the Panel* inputs below) and places it     |
//|     with native OrderSend() calls - same MARKET-fallback for an   |
//|     entry too close to the current price as the bridge EA uses.  |
//|   - "Zamknij zlecenia oczekujace" cancels every still-pending     |
//|     order this EA has placed (magic >= PanelMagicBase) - open      |
//|     positions are left alone, only unfilled pending orders are    |
//|     removed (PanelCloseAllPending).                                |
//|   - "BUY MARKET" / "SELL MARKET" (PanelPlaceMarketZone) skip the   |
//|     manual "Zaznacz strefe" click-picking - the zone is computed   |
//|     automatically as PanelMarketZoneWidthDollars wide, anchored at |
//|     the current market price, then handled by the exact same      |
//|     grid/SL/trailing pipeline as a normal BUY/SELL: the level      |
//|     right at the market price opens immediately (via the same     |
//|     MARKET-fallback PlaceOrders always used for an entry too      |
//|     close to price), the rest of the grid below/above it stays     |
//|     pending as usual. SL(pips)/Trailing(pips)/Blokada(pips)/Krok   |
//|     siatki($) keep whatever the panel currently has configured.   |
//|                                                                  |
//| All-or-nothing grids: if one pending order from a grid disappears |
//| WITHOUT having filled (cancelled/expired/rejected - e.g. removed  |
//| by hand in the terminal), the rest of that same grid's still-     |
//| pending orders are cancelled too automatically, every OnTimer     |
//| tick (PanelDetectAbandonedGrids) - a grid missing one of its      |
//| entries no longer represents the position size/risk the zone was |
//| meant to have. Already-open positions are never touched by this - |
//| only still-pending orders from the same magic. A ticket that      |
//| disappeared because it FILLED (one grid entry caught, the normal  |
//| case) is left alone, along with the rest of that grid.            |
//|                                                                  |
//| No TP is set on these orders. Exits happen only through a        |
//| trailing stop (PanelUpdateTrailingStops(), run every OnTimer     |
//| tick) - untouched below "Trailing (pips)" profit, then every     |
//| "Trailing (pips)" of profit the SL jumps to lock in that many    |
//| pips PLUS "Blokada zysku (pips)" extra - so the first jump (and  |
//| every one after it) always leaves at least "Blokada zysku (pips)"|
//| of profit locked in instead of exact breakeven (set it to 0 for  |
//| the plain breakeven-ladder behavior). Tightening only. This is   |
//| the exact same algorithm as the Python bot's                     |
//| EXIT_MODE=trailing_stop (mt5_executor.check_trailing_stops /     |
//| TRAILING_STOP_LOCK_PIPS).                                        |
//|                                                                  |
//| Trailing speedup by position (PanelTrailingSpeedupStepPips /     |
//| PanelTrailingSpeedupFloorPips): "Trailing (pips)" above is only   |
//| the value for the grid level FURTHEST from SL (the smallest lot) |
//| - every level closer to SL (bigger lot, since lot size grows      |
//| toward SL - see PanelLotTiers) gets that many pips LESS, down to  |
//| a floor, so the biggest positions in a grid activate trailing     |
//| (and start tightening) soonest. Each level's own trailing         |
//| distance is fixed at placement time (PanelPlaceZone) and looked   |
//| up per position by entry price (PanelTrailPipsForPosition), not   |
//| shared across the whole zone like Blokada zysku/lock is. Set the  |
//| step to 0 to disable (every level uses plain "Trailing (pips)").  |
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
#define PANEL_HEIGHT 520
#define PANEL_MARGIN 10
#define PANEL_HEADER_HEIGHT 30
#define PANEL_HIDDEN_Y (-3000)   // parks minimized/off body controls well above the visible chart
#define PANEL_PREFIX "TgManualPanel_"

input double PanelDefaultSlPips           = 60;    // starting value for the SL (pips) stepper
input double PanelDefaultTrailingPips     = 36;    // starting value for the Trailing (pips) stepper
input double PanelDefaultTrailingLockPips = 12;    // starting value for the Blokada zysku (pips) stepper - extra profit always kept locked in at each trailing jump instead of exact breakeven (0 = old plain breakeven-ladder behavior)
input double PanelDefaultStepDollars      = 0.5;   // starting value for the Krok siatki ($) stepper
input double PanelDefaultExtendUpDollars   = 0.0;  // starting value for the Rozszerz gora ($) stepper - extra grid levels ABOVE the picked/market zone's top edge, SL stays anchored to the zone (unaffected)
input double PanelDefaultExtendDownDollars = 0.0;  // starting value for the Rozszerz dol ($) stepper - extra grid levels BELOW the picked/market zone's bottom edge, SL stays anchored to the zone (unaffected)
input double PanelMarketZoneWidthDollars  = 6.0;   // BUY MARKET/SELL MARKET: width ($) of the auto-computed zone below/above the market fill - SL(pips)/Trailing(pips)/Blokada(pips)/Krok siatki($)/Rozszerz above still apply exactly as configured, so the SL ends up PanelMarketZoneWidthDollars + SL(pips) away from the market entry
input double PanelTrailingSpeedupStepPips  = 2.0;  // Trailing (pips) shrinks by this many pips per grid position closer to SL (bigger lot) than the previous one - 0th/furthest-from-SL position uses Trailing (pips) as-is, each one after it activates that much sooner, down to PanelTrailingSpeedupFloorPips. Set 0 to disable (every position uses the same Trailing (pips)).
input double PanelTrailingSpeedupFloorPips = 14.0; // minimum trailing-activation distance (pips) PanelTrailingSpeedupStepPips can shrink down to, no matter how many positions/how close to SL
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
double g_panelTrailingLockPips[];

// Per-GRID-LEVEL trailing distance (one entry per price level placed by
// PanelPlaceZone, keyed by magic + that level's own entry price) - lets
// PanelUpdateTrailingStops give each position its OWN Trailing (pips)
// instead of one shared value per magic, for PanelTrailingSpeedupStepPips.
// See PanelPlaceZone/PanelUpdateTrailingStops for how it's filled/read.
long   g_panelLevelMagics[];
double g_panelLevelPrices[];
double g_panelLevelTrailPips[];

// Last tick's snapshot of live pending-order tickets (magic>=PanelMagicBase),
// used by PanelDetectAbandonedGrids() to notice one disappearing WITHOUT
// having filled - see that function for why.
long   g_panelKnownPendingTickets[];
long   g_panelKnownPendingMagics[];

double g_zoneLow = 0;
double g_zoneHigh = 0;
int    g_awaitingClick = 0;   // 0 = idle, 1 = waiting for the first point, 2 = waiting for the second
double g_pendingFirstPrice = 0;

double g_slPips = 0;
double g_trailPips = 0;
double g_trailLockPips = 0;
double g_stepDollars = 0;
double g_extendUpDollars = 0;
double g_extendDownDollars = 0;

// Current panel content origin (top-left, same meaning as the x,y PanelCreate
// takes) - kept so the panel can be dragged (PanelMoveTo) and minimized
// (g_panelMinimized) without losing track of where it currently is.
int  g_panelOriginX = 0;
int  g_panelOriginY = 0;
bool g_panelMinimized = false;

int g_panelLeft = 0, g_panelTop = 0, g_panelRight = 0, g_panelBottom = 0;

// Manual title-bar dragging (CHARTEVENT_MOUSE_MOVE-driven, see
// OnChartEvent) - native MT5 object dragging (OBJPROP_SELECTABLE +
// CHARTEVENT_OBJECT_DRAG) proved unreliable for a corner-anchored
// OBJ_RECTANGLE_LABEL in this EA's testing, the same way OBJ_EDIT and
// OBJ_HLINE dragging did earlier in this file's history - tracking the
// raw mouse position/button state ourselves doesn't depend on MT5
// recognizing/dragging the object natively at all.
bool g_titleDragging = false;
int  g_titleDragOffsetX = 0;
int  g_titleDragOffsetY = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(PollSeconds);
   ChartSetInteger(0, CHART_EVENT_MOUSE_MOVE, true);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("WARNING: Algo Trading is currently OFF - this EA cannot place orders until it's enabled.");
   g_slPips = PanelDefaultSlPips;
   g_trailPips = PanelDefaultTrailingPips;
   g_trailLockPips = PanelDefaultTrailingLockPips;
   g_stepDollars = PanelDefaultStepDollars;
   g_extendUpDollars = PanelDefaultExtendUpDollars;
   g_extendDownDollars = PanelDefaultExtendDownDollars;

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
   PanelDetectAbandonedGrids();
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
//| Creates the object on first call; on any later call (panel drag/  |
//| minimize/restore re-invoking PanelCreate) just repositions the    |
//| existing object instead of recreating it, so its current text/    |
//| state (e.g. a value label mid zone-pick) is never reset.          |
//+------------------------------------------------------------------+
void PanelCreateLabel(string name, int x, int y, string text, int fontSize = 10)
  {
   string full = PANEL_PREFIX + name;
   if(ObjectFind(0, full) >= 0)
     {
      ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
      return;
     }
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
//| Same create-once/reposition-after pattern as PanelCreateLabel.    |
//+------------------------------------------------------------------+
void PanelCreateButton(string name, int x, int y, int w, int h, string text, color clr, int fontSize = 10)
  {
   string full = PANEL_PREFIX + name;
   if(ObjectFind(0, full) >= 0)
     {
      ObjectSetInteger(0, full, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, full, OBJPROP_YDISTANCE, y);
      // Buttons (unlike value labels) never carry runtime-changed text
      // other than what's passed in here - MinimizeBtn's "-"/"+" needs
      // this to actually flip when re-laid-out after a toggle.
      ObjectSetString(0, full, OBJPROP_TEXT, text);
      return;
     }
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
//| Returns y normally, or PANEL_HIDDEN_Y (well above the visible      |
//| chart) while the panel is minimized - used for every "body" row    |
//| below the title bar, so minimizing just parks them off-screen      |
//| instead of deleting/recreating them (PanelCreateLabel/Button's     |
//| reposition-only path keeps their current text/state either way).  |
//+------------------------------------------------------------------+
int PanelBodyY(int y)
  {
   return g_panelMinimized ? PANEL_HIDDEN_Y : y;
  }

//+------------------------------------------------------------------+
//| Lays out every control top-to-bottom, each on its own row so      |
//| nothing overlaps regardless of label text length. (x,y) is the    |
//| panel's top-left corner. Safe to call again at any time (drag,     |
//| minimize/restore) - PanelCreateLabel/Button reposition existing    |
//| objects rather than recreating them.                               |
//+------------------------------------------------------------------+
void PanelCreate(int x, int y)
  {
   int labelW = 145, valW = 50, smallBtnW = 32, smallBtnH = 28, rowH = 40;
   int margin = PANEL_MARGIN;

   g_panelOriginX = x;
   g_panelOriginY = y;

   // Remember the panel's screen rectangle so PanelHandleChartClick can
   // ignore clicks that land on it - clicking a button also fires a plain
   // CHARTEVENT_CLICK at the same pixel coordinates, which would otherwise
   // get misread as a zone-picking click on the button's own position.
   // Shrinks to just the header while minimized.
   int panelHeight = g_panelMinimized ? PANEL_HEADER_HEIGHT : PANEL_HEIGHT;
   g_panelLeft = x - margin;
   g_panelTop = y - margin;
   g_panelRight = g_panelLeft + PANEL_WIDTH;
   g_panelBottom = g_panelTop + panelHeight;

   if(ObjectFind(0, PANEL_PREFIX + "Bg") < 0)
     {
      ObjectCreate(0, PANEL_PREFIX + "Bg", OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BGCOLOR, clrWhiteSmoke);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_COLOR, clrSilver);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_BACK, true);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_ZORDER, 0);
     }
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_XDISTANCE, x - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_YDISTANCE, y - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_XSIZE, PANEL_WIDTH);
   ObjectSetInteger(0, PANEL_PREFIX + "Bg", OBJPROP_YSIZE, panelHeight);

   // TitleBar: the draggable strip (grab anywhere on it except the
   // MinimizeBtn sitting on top of it) - dragging is handled manually via
   // CHARTEVENT_MOUSE_MOVE in OnChartEvent (g_titleDragging), NOT native
   // MT5 object dragging, which proved unreliable for this object type in
   // this EA's testing. SELECTABLE stays false so a click never leaves it
   // visibly "selected" (anchor squares) - our own mouse tracking doesn't
   // need that. It's still a foreground (BACK=false) object so it - and
   // the panel as a whole - catches clicks instead of leaking them
   // through to the chart underneath, unlike Bg which stays BACK=true.
   if(ObjectFind(0, PANEL_PREFIX + "TitleBar") < 0)
     {
      ObjectCreate(0, PANEL_PREFIX + "TitleBar", OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_BGCOLOR, clrSilver);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_COLOR, clrGray);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_BACK, false);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_ZORDER, 5);
     }
   ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_XDISTANCE, x - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_YDISTANCE, y - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_XSIZE, PANEL_WIDTH);
   ObjectSetInteger(0, PANEL_PREFIX + "TitleBar", OBJPROP_YSIZE, PANEL_HEADER_HEIGHT);

   // BodyCatcher: covers the rest of the panel below the title bar - same
   // idea as TitleBar (a foreground/BACK=false object so clicks on it
   // land on the panel, not the chart underneath) but NOT selectable, so
   // it doesn't compete with TitleBar for dragging. Its low ZORDER (below
   // every button/label's 10) means a click still resolves to whichever
   // button sits on top of it, exactly like Bg always has - this just
   // catches the gaps BETWEEN controls that Bg (BACK=true, non-
   // interactive) was letting straight through to the chart. Parked
   // off-screen while minimized, same as the body controls themselves.
   if(ObjectFind(0, PANEL_PREFIX + "BodyCatcher") < 0)
     {
      ObjectCreate(0, PANEL_PREFIX + "BodyCatcher", OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_BGCOLOR, clrWhiteSmoke);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_COLOR, clrWhiteSmoke);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_BACK, false);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_ZORDER, 1);
     }
   ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_XDISTANCE, x - margin);
   ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_YDISTANCE,
                     g_panelMinimized ? PANEL_HIDDEN_Y : y - margin + PANEL_HEADER_HEIGHT);
   ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_XSIZE, PANEL_WIDTH);
   ObjectSetInteger(0, PANEL_PREFIX + "BodyCatcher", OBJPROP_YSIZE, PANEL_HEIGHT - PANEL_HEADER_HEIGHT);

   PanelCreateLabel("Title", x, y, "STREFA MANUALNA", 11);
   PanelCreateButton("MinimizeBtn", x + PANEL_WIDTH - 2 * margin - 24, y - 6, 24, 22,
                      g_panelMinimized ? "+" : "-", clrLightGray, 12);
   int rowY = y + 26;

   PanelCreateLabel("LblZone", x, PanelBodyY(rowY), "Strefa:");
   PanelCreateLabel("ZoneValueLbl", x + 150, PanelBodyY(rowY), "-- brak, kliknij Zaznacz --");
   rowY += rowH;

   PanelCreateButton("PickZoneBtn", x, PanelBodyY(rowY), PANEL_WIDTH - 2 * margin, 32, "ZAZNACZ STREFE (2 kliknieca na wykresie)", clrKhaki);
   rowY += 38;

   PanelCreateLabel("LblSl", x, PanelBodyY(rowY), "SL (pips):");
   PanelCreateLabel("SlValueLbl", x + 150, PanelBodyY(rowY), DoubleToString(g_slPips, 0));
   PanelCreateButton("SlMinusBtn", x + 215, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("SlPlusBtn", x + 215 + smallBtnW + 6, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblTrail", x, PanelBodyY(rowY), "Trailing (pips):");
   PanelCreateLabel("TrailValueLbl", x + 150, PanelBodyY(rowY), DoubleToString(g_trailPips, 0));
   PanelCreateButton("TrailMinusBtn", x + 215, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("TrailPlusBtn", x + 215 + smallBtnW + 6, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblTrailLock", x, PanelBodyY(rowY), "Blokada zysku (pips):");
   PanelCreateLabel("TrailLockValueLbl", x + 150, PanelBodyY(rowY), DoubleToString(g_trailLockPips, 0));
   PanelCreateButton("TrailLockMinusBtn", x + 215, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("TrailLockPlusBtn", x + 215 + smallBtnW + 6, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblStep", x, PanelBodyY(rowY), "Krok siatki ($):");
   PanelCreateLabel("StepValueLbl", x + 150, PanelBodyY(rowY), DoubleToString(g_stepDollars, 2));
   PanelCreateButton("StepMinusBtn", x + 215, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("StepPlusBtn", x + 215 + smallBtnW + 6, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblExtendUp", x, PanelBodyY(rowY), "Rozszerz gora ($):");
   PanelCreateLabel("ExtendUpValueLbl", x + 150, PanelBodyY(rowY), DoubleToString(g_extendUpDollars, 2));
   PanelCreateButton("ExtendUpMinusBtn", x + 215, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("ExtendUpPlusBtn", x + 215 + smallBtnW + 6, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH;

   PanelCreateLabel("LblExtendDown", x, PanelBodyY(rowY), "Rozszerz dol ($):");
   PanelCreateLabel("ExtendDownValueLbl", x + 150, PanelBodyY(rowY), DoubleToString(g_extendDownDollars, 2));
   PanelCreateButton("ExtendDownMinusBtn", x + 215, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "-", clrLightGray);
   PanelCreateButton("ExtendDownPlusBtn", x + 215 + smallBtnW + 6, PanelBodyY(rowY - 4), smallBtnW, smallBtnH, "+", clrLightGray);
   rowY += rowH + 6;

   int tradeBtnW = (PANEL_WIDTH - 2 * margin - 10) / 2;
   PanelCreateButton("BuyBtn", x, PanelBodyY(rowY), tradeBtnW, 36, "BUY", clrLimeGreen, 12);
   PanelCreateButton("SellBtn", x + tradeBtnW + 10, PanelBodyY(rowY), tradeBtnW, 36, "SELL", clrTomato, 12);
   rowY += 46;

   PanelCreateButton("BuyMarketBtn", x, PanelBodyY(rowY), tradeBtnW, 32, "BUY MARKET", clrSeaGreen, 10);
   PanelCreateButton("SellMarketBtn", x + tradeBtnW + 10, PanelBodyY(rowY), tradeBtnW, 32, "SELL MARKET", clrIndianRed, 10);
   rowY += 42;

   PanelCreateButton("ClosePendingBtn", x, PanelBodyY(rowY), PANEL_WIDTH - 2 * margin, 30, "ZAMKNIJ ZLECENIA OCZEKUJACE", clrGold);
   rowY += 38;

   PanelCreateLabel("Status", x, PanelBodyY(rowY), "Gotowy - kliknij 'Zaznacz strefe'.", 9);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Moves the whole panel to a new top-left content origin - just     |
//| calls PanelCreate again, which repositions every existing object   |
//| (create-once/reposition-after, see PanelCreateLabel/Button)        |
//| instead of recreating them. Used by the TitleBar's native MT5      |
//| object-drag handling in OnChartEvent.                              |
//+------------------------------------------------------------------+
void PanelMoveTo(int newX, int newY)
  {
   PanelCreate(newX, newY);
  }

//+------------------------------------------------------------------+
//| Toggles the panel between its normal layout and a header-only      |
//| strip (title bar + this same button, now showing "+") - everything |
//| else just gets parked off-screen (PanelBodyY), not deleted, so      |
//| restoring is instant and never resets any value.                   |
//+------------------------------------------------------------------+
void PanelToggleMinimize()
  {
   g_panelMinimized = !g_panelMinimized;
   PanelCreate(g_panelOriginX, g_panelOriginY);
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
//| Extra profit (pips) always kept locked in at each trailing jump,  |
//| on top of the jump's own Trailing (pips) step - 0 reproduces the  |
//| plain breakeven-ladder behavior (each jump lands exactly on       |
//| breakeven/the previous checkpoint).                                |
//+------------------------------------------------------------------+
void PanelAdjustTrailLock(double delta)
  {
   g_trailLockPips = MathMax(0.0, g_trailLockPips + delta);
   ObjectSetString(0, PANEL_PREFIX + "TrailLockValueLbl", OBJPROP_TEXT, DoubleToString(g_trailLockPips, 0));
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
//| Extra grid levels ($) ABOVE the picked/market zone's top edge -   |
//| SL stays anchored to the zone itself (unaffected), only the entry |
//| grid widens. 0 = no extension (exactly the picked/market zone).   |
//+------------------------------------------------------------------+
void PanelAdjustExtendUp(double delta)
  {
   g_extendUpDollars = MathMax(0.0, NormalizeDouble(g_extendUpDollars + delta, 2));
   ObjectSetString(0, PANEL_PREFIX + "ExtendUpValueLbl", OBJPROP_TEXT, DoubleToString(g_extendUpDollars, 2));
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Extra grid levels ($) BELOW the picked/market zone's bottom edge  |
//| - SL stays anchored to the zone itself (unaffected), only the     |
//| entry grid widens. 0 = no extension (exactly the picked/market    |
//| zone).                                                              |
//+------------------------------------------------------------------+
void PanelAdjustExtendDown(double delta)
  {
   g_extendDownDollars = MathMax(0.0, NormalizeDouble(g_extendDownDollars + delta, 2));
   ObjectSetString(0, PANEL_PREFIX + "ExtendDownValueLbl", OBJPROP_TEXT, DoubleToString(g_extendDownDollars, 2));
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
//| the entries closest to SL in the highest tier. Also returns the   |
//| raw (ungrouped) 0-based distance-to-SL rank per level in `ranks`  |
//| (0 = furthest from SL, count-1 = closest) - used by PanelPlaceZone |
//| to compute each level's own Trailing (pips) for                  |
//| PanelTrailingSpeedupStepPips (a finer granularity than tiers,     |
//| which group PanelLotTierOrders levels together).                  |
//+------------------------------------------------------------------+
void PanelLotTiers(double &levels[], int count, double slPrice, int tierOrders, int &tiers[], int &ranks[])
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
   ArrayResize(ranks, count);
   if(tierOrders < 1)
      tierOrders = 1;
   for(int rank = 0; rank < count; rank++)
     {
      tiers[order[rank]] = rank / tierOrders;
      ranks[order[rank]] = rank;
     }
  }

//+------------------------------------------------------------------+
//| Uses the zone/SL/trailing/step currently picked via the panel to  |
//| build the same kind of order grid as order_planner.plan_orders()  |
//| (EXIT_MODE=trailing_stop shape - no TP), and places it via         |
//| PlaceOrders() - MARKET-fallback for an entry too close to price    |
//| applies here too.                                                  |
//|                                                                     |
//| "Rozszerz gora/dol ($)" widen the ENTRY GRID past the picked/     |
//| market zone's top/bottom edge - literal chart up/down, same for   |
//| BUY and SELL - without moving SL, which stays anchored to the      |
//| zone's own zoneLow/zoneHigh (computed below, before extension is   |
//| applied) - mirrors order_planner.plan_orders's                   |
//| zone_extend_front/zone_extend_back (SL unaffected by extension).  |
//| An extension large enough to reach/pass SL just drops those       |
//| entries via the usual valid-entry filter below.                   |
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
   double trailLockPips = g_trailLockPips;
   double step = g_stepDollars;
   double extendUp = g_extendUpDollars;
   double extendDown = g_extendDownDollars;

   double slPrice = (direction == "BUY")
      ? NormalizeDouble(zoneLow - slPips * PanelPipSize, 2)
      : NormalizeDouble(zoneHigh + slPips * PanelPipSize, 2);

   double gridLow = NormalizeDouble(zoneLow - extendDown, 2);
   double gridHigh = NormalizeDouble(zoneHigh + extendUp, 2);

   double levels[];
   int levelCount = PanelGeneratePriceLevels(gridLow, gridHigh, step, levels);

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
   int ranks[];
   PanelLotTiers(levels, kept, slPrice, PanelLotTierOrders, tiers, ranks);

   double lots[];
   ArrayResize(lots, kept);
   for(int i = 0; i < kept; i++)
     {
      if(PanelLotScalingMode == "multiplier")
         lots[i] = NormalizeDouble(PanelLotBase * MathPow(PanelLotMultiplier, tiers[i]), 2);
      else
         lots[i] = NormalizeDouble(PanelLotBase * (tiers[i] + 1), 2);
     }

   // Trailing (pips) shrinks per rank (0 = furthest from SL/smallest lot,
   // keeps the full trailPips) down to PanelTrailingSpeedupFloorPips - the
   // levels closest to SL (biggest lots) activate trailing soonest, so the
   // largest positions get protected first. Step=0 makes every level equal
   // to trailPips, same as before this feature existed.
   double levelTrailPips[];
   ArrayResize(levelTrailPips, kept);
   double minLevelTrailPips = trailPips;
   for(int i = 0; i < kept; i++)
     {
      levelTrailPips[i] = MathMax(PanelTrailingSpeedupFloorPips, trailPips - PanelTrailingSpeedupStepPips * ranks[i]);
      if(levelTrailPips[i] < minLevelTrailPips)
         minLevelTrailPips = levelTrailPips[i];
     }

   long magic = PanelMagicBase + g_panelNextMagic;
   g_panelNextMagic++;
   int slot = ArraySize(g_panelMagics);
   ArrayResize(g_panelMagics, slot + 1);
   ArrayResize(g_panelTrailingPips, slot + 1);
   ArrayResize(g_panelTrailingLockPips, slot + 1);
   g_panelMagics[slot] = magic;
   g_panelTrailingPips[slot] = trailPips;
   g_panelTrailingLockPips[slot] = trailLockPips;

   int levelSlot = ArraySize(g_panelLevelMagics);
   ArrayResize(g_panelLevelMagics, levelSlot + kept);
   ArrayResize(g_panelLevelPrices, levelSlot + kept);
   ArrayResize(g_panelLevelTrailPips, levelSlot + kept);
   for(int i = 0; i < kept; i++)
     {
      g_panelLevelMagics[levelSlot + i] = magic;
      g_panelLevelPrices[levelSlot + i] = levels[i];
      g_panelLevelTrailPips[levelSlot + i] = levelTrailPips[i];
     }

   string comment = "panel-" + (string)magic;
   PlaceOrders(magic, Symbol(), comment, PanelDeviationPoints, direction, levels, lots, slPrice, kept);
   PanelClearPickPreview();
   // Draws the actual grid extent (including any Rozszerz gora/dol) rather
   // than just the raw picked/market zone, so the rectangle always shows
   // exactly where the orders sit.
   PanelDrawZone(magic, direction, gridLow, gridHigh, slPrice);

   // Clear the picked zone so the next click on BUY/SELL can't accidentally
   // reuse a stale zone - a fresh "Zaznacz strefe" is required each time.
   g_zoneLow = 0;
   g_zoneHigh = 0;
   PanelSetZoneValueLabel();

   PanelSetStatus(StringFormat(
      "Wystawiono %d zlec. %s %.2f-%.2f, SL=%.2f, trailing=%.0f-%.0f pips (blokada +%.0f) (magic=%d)",
      kept, direction, gridLow, gridHigh, slPrice, minLevelTrailPips, trailPips, trailLockPips, (int)magic));
  }

//+------------------------------------------------------------------+
//| BUY MARKET / SELL MARKET: same grid/SL/trailing as a normal        |
//| "Zaznacz strefe" + BUY/SELL, except the zone is computed           |
//| automatically from the current market price instead of two chart  |
//| clicks - PanelMarketZoneWidthDollars wide, anchored at the market  |
//| fill (for BUY: zoneHigh = ask, zoneLow = ask - width; for SELL:     |
//| zoneLow = bid, zoneHigh = bid + width). SL(pips)/Trailing(pips)/    |
//| Blokada(pips)/Krok siatki($) all keep whatever the panel currently |
//| has configured - only the zone bounds are auto-computed here.      |
//| Delegates the entire rest (SL calc, grid, lot tiers, drawing,      |
//| status) to PanelPlaceZone(), which already places the level        |
//| nearest the current price at MARKET instead of pending (see        |
//| PlaceOrders's atMarket check) - since the zone's near edge is set  |
//| to the market price exactly, that's automatically the entry that   |
//| opens immediately, with the rest of the grid below/above it as     |
//| pending orders like any other zone.                                |
//+------------------------------------------------------------------+
void PanelPlaceMarketZone(string direction)
  {
   double bid = SymbolInfoDouble(Symbol(), SYMBOL_BID);
   double ask = SymbolInfoDouble(Symbol(), SYMBOL_ASK);
   double entryPrice = (direction == "BUY") ? ask : bid;

   if(direction == "BUY")
     {
      g_zoneHigh = NormalizeDouble(entryPrice, 2);
      g_zoneLow  = NormalizeDouble(entryPrice - PanelMarketZoneWidthDollars, 2);
     }
   else
     {
      g_zoneLow  = NormalizeDouble(entryPrice, 2);
      g_zoneHigh = NormalizeDouble(entryPrice + PanelMarketZoneWidthDollars, 2);
     }

   g_awaitingClick = 0; // cancel any manual zone-pick in progress
   PanelClearPickPreview();
   PanelSetZoneValueLabel();
   PanelPlaceZone(direction);
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
//| Cancels every still-pending order for exactly one magic (unlike   |
//| PanelCloseAllPending, which cancels every magic >= PanelMagicBase |
//| at once) - used by PanelDetectAbandonedGrids() when one grid's    |
//| entries need to come down together.                                |
//+------------------------------------------------------------------+
void PanelCancelPendingForMagic(long magic)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;
      if(OrderGetInteger(ORDER_MAGIC) != magic)
         continue;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);
      request.action = TRADE_ACTION_REMOVE;
      request.order = ticket;

      bool ok = OrderSend(request, result);
      if(!ok || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("Panel: nie udalo sie usunac zlecenia %d z niekompletnej siatki (magic=%d) retcode=%d comment='%s'",
                     (int)ticket, (int)magic, result.retcode, result.comment);
     }
  }

//+------------------------------------------------------------------+
//| If one pending order from a grid disappears WITHOUT having filled |
//| (cancelled/expired/rejected - e.g. removed by hand in the         |
//| terminal), the rest of that grid's still-pending orders are      |
//| cancelled too - a grid missing one of its entries no longer       |
//| represents the position size/risk the zone was meant to have.     |
//| Already-open positions from that same grid are left untouched -   |
//| only still-pending orders are affected. A ticket that disappeared |
//| because it FILLED (the expected, common case - one grid entry     |
//| caught) is left alone, along with the rest of that grid.          |
//|                                                                     |
//| Works by diffing this tick's live pending tickets (magic >=       |
//| PanelMagicBase) against g_panelKnownPendingTickets from the        |
//| previous tick; any ticket present before but missing now is        |
//| looked up in the order history to tell "filled" from "removed".   |
//| Run every OnTimer tick, before PanelCleanupFinishedZones.          |
//+------------------------------------------------------------------+
void PanelDetectAbandonedGrids()
  {
   long liveTickets[];
   long liveMagics[];
   int liveCount = 0;
   for(int i = 0; i < OrdersTotal(); i++)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;
      long magic = OrderGetInteger(ORDER_MAGIC);
      if(magic < PanelMagicBase)
         continue;
      ArrayResize(liveTickets, liveCount + 1);
      ArrayResize(liveMagics, liveCount + 1);
      liveTickets[liveCount] = (long)ticket;
      liveMagics[liveCount] = magic;
      liveCount++;
     }

   long handledMagics[];
   int handledCount = 0;

   for(int k = 0; k < ArraySize(g_panelKnownPendingTickets); k++)
     {
      long ticket = g_panelKnownPendingTickets[k];

      bool stillPending = false;
      for(int i = 0; i < liveCount; i++)
        {
         if(liveTickets[i] == ticket)
           {
            stillPending = true;
            break;
           }
        }
      if(stillPending)
         continue;

      long magic = g_panelKnownPendingMagics[k];

      bool alreadyHandled = false;
      for(int h = 0; h < handledCount; h++)
        {
         if(handledMagics[h] == magic)
           {
            alreadyHandled = true;
            break;
           }
        }
      if(alreadyHandled)
         continue;

      HistorySelect(0, TimeCurrent());
      if(!HistoryOrderSelect(ticket))
         continue; // can't tell what happened to it - be conservative, don't cancel

      long state = HistoryOrderGetInteger(ticket, ORDER_STATE);
      if(state == ORDER_STATE_FILLED)
         continue; // expected - one grid entry just filled, rest is fine

      PanelCancelPendingForMagic(magic);
      PanelSetStatus(StringFormat(
         "Zlecenie %d z siatki (magic=%d) zniknelo bez fillu - usunieto reszte siatki.", (int)ticket, (int)magic));

      ArrayResize(handledMagics, handledCount + 1);
      handledMagics[handledCount] = magic;
      handledCount++;
     }

   // Save this tick's snapshot for the next diff - but drop any ticket
   // belonging to a magic just handled above: PanelCancelPendingForMagic()
   // is about to remove those too, and letting them into next tick's
   // "known" set would make them look like another abandoned-order event
   // (they'd vanish "without filling" again) and re-fire the same message
   // for orders we ourselves already cancelled as a consequence.
   int savedCount = 0;
   for(int i = 0; i < liveCount; i++)
     {
      bool dropIt = false;
      for(int h = 0; h < handledCount; h++)
        {
         if(handledMagics[h] == liveMagics[i])
           {
            dropIt = true;
            break;
           }
        }
      if(dropIt)
         continue;

      liveTickets[savedCount] = liveTickets[i];
      liveMagics[savedCount] = liveMagics[i];
      savedCount++;
     }

   ArrayResize(g_panelKnownPendingTickets, savedCount);
   ArrayResize(g_panelKnownPendingMagics, savedCount);
   for(int i = 0; i < savedCount; i++)
     {
      g_panelKnownPendingTickets[i] = liveTickets[i];
      g_panelKnownPendingMagics[i] = liveMagics[i];
     }
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
//| tracking its trailing_pips (and per-level Trailing (pips) entries |
//| - see PanelTrailPipsForPosition) once nothing is left open for it |
//| - same idea as the Python bot deactivating a finished campaign.   |
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
      g_panelTrailingLockPips[m] = g_panelTrailingLockPips[last];
      ArrayResize(g_panelMagics, last);
      ArrayResize(g_panelTrailingPips, last);
      ArrayResize(g_panelTrailingLockPips, last);

      // Forward compaction (not swap-with-last) - this magic is about to
      // drop out of g_panelMagics entirely, so any entry a swap-remove
      // missed here would never get a later pass to catch it and would
      // leak in g_panelLevelMagics forever.
      int keptLevels = 0;
      int totalLevels = ArraySize(g_panelLevelMagics);
      for(int i = 0; i < totalLevels; i++)
        {
         if(g_panelLevelMagics[i] == magic)
            continue;
         g_panelLevelMagics[keptLevels] = g_panelLevelMagics[i];
         g_panelLevelPrices[keptLevels] = g_panelLevelPrices[i];
         g_panelLevelTrailPips[keptLevels] = g_panelLevelTrailPips[i];
         keptLevels++;
        }
      ArrayResize(g_panelLevelMagics, keptLevels);
      ArrayResize(g_panelLevelPrices, keptLevels);
      ArrayResize(g_panelLevelTrailPips, keptLevels);
     }
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Each grid level got its own Trailing (pips) at placement time     |
//| (PanelPlaceZone, PanelTrailingSpeedupStepPips) - positions don't   |
//| carry that value themselves, so it's looked up here by matching   |
//| the position's own entry price against g_panelLevelPrices for the |
//| same magic, taking the CLOSEST match (handles a MARKET-fallback   |
//| fill landing a few points off its requested level - grid spacing  |
//| is always far larger than realistic slippage, so nearest-match    |
//| can't confuse one level for another). Falls back to the magic's   |
//| plain trailPips (no speedup) if nothing is found, e.g. leftover   |
//| positions from before this feature existed.                       |
//+------------------------------------------------------------------+
double PanelTrailPipsForPosition(long magic, double entry, double fallback)
  {
   double best = fallback;
   double bestDist = -1;
   for(int i = 0; i < ArraySize(g_panelLevelMagics); i++)
     {
      if(g_panelLevelMagics[i] != magic)
         continue;
      double dist = MathAbs(g_panelLevelPrices[i] - entry);
      if(bestDist < 0 || dist < bestDist)
        {
         bestDist = dist;
         best = g_panelLevelTrailPips[i];
        }
     }
   return best;
  }

//+------------------------------------------------------------------+
//| Trailing stop for panel-placed positions (matched by magic        |
//| against g_panelMagics): untouched below trailPips profit; at      |
//| trailPips profit SL jumps to trailLockPips profit (or exact       |
//| breakeven when trailLockPips=0, the default), then every further  |
//| trailPips of profit SL jumps another trailPips, keeping the same  |
//| trailLockPips buffer on top each time. Tightening only. Same      |
//| algorithm as the Python bot's EXIT_MODE=trailing_stop             |
//| (mt5_executor.check_trailing_stops). trailPips itself is looked   |
//| up PER POSITION (PanelTrailPipsForPosition) rather than shared     |
//| across the whole magic, so PanelTrailingSpeedupStepPips can make   |
//| the grid levels closer to SL (bigger lots) activate sooner. Run    |
//| every OnTimer tick.                                                |
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
      double trailLockPips = 0;
      for(int m = 0; m < ArraySize(g_panelMagics); m++)
        {
         if(g_panelMagics[m] == magic)
           {
            trailPips = g_panelTrailingPips[m];
            trailLockPips = g_panelTrailingLockPips[m];
            break;
           }
        }
      if(trailPips <= 0)
         continue; // not a panel-managed position

      string symbol = PositionGetString(POSITION_SYMBOL);
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      trailPips = PanelTrailPipsForPosition(magic, entry, trailPips);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      bool isBuy = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);

      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double trailDistance = trailPips * PanelPipSize;
      double lockDistance = trailLockPips * PanelPipSize;

      double profitDistance = isBuy ? (bid - entry) : (entry - ask);
      if(profitDistance < trailDistance)
         continue;

      // round-trip through MathFloor(... + epsilon) guards against float
      // noise putting profitDistance one step short of an exact multiple
      // of trailDistance, which would delay the next jump by a tick.
      double steps = MathFloor(profitDistance / trailDistance + 0.0000001);
      double locked = (steps - 1) * trailDistance + lockDistance;
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
//| Manual title-bar dragging (CHARTEVENT_MOUSE_MOVE, enabled in       |
//| OnInit via CHART_EVENT_MOUSE_MOVE) - tracks the raw mouse position |
//| and left-button state ourselves rather than relying on native MT5 |
//| object dragging (see g_titleDragging's comment for why). mx/my are |
//| the mouse's chart-pixel coordinates; buttonState is MT5's string   |
//| encoding of which mouse buttons are currently held (bit 0 = left   |
//| button, matching the standard Win32 MK_LBUTTON flag).             |
//|                                                                     |
//| Starts a drag the moment it sees the left button held AND the      |
//| cursor over the title bar (excluding the MinimizeBtn's own         |
//| footprint, so clicking it never starts a drag) while not already   |
//| dragging; keeps repositioning the whole panel (PanelMoveTo) for     |
//| every further move while the button stays held, regardless of      |
//| where the cursor drifts to; stops the instant the button is        |
//| released.                                                           |
//+------------------------------------------------------------------+
void PanelHandleMouseMove(int mx, int my, string buttonState)
  {
   bool leftDown = ((int)StringToInteger(buttonState) & 1) == 1;

   if(!leftDown)
     {
      g_titleDragging = false;
      return;
     }

   if(!g_titleDragging)
     {
      int titleLeft = g_panelOriginX - PANEL_MARGIN;
      int titleTop = g_panelOriginY - PANEL_MARGIN;
      int titleRight = titleLeft + PANEL_WIDTH;
      int titleBottom = titleTop + PANEL_HEADER_HEIGHT;
      int minBtnLeft = g_panelOriginX + PANEL_WIDTH - 2 * PANEL_MARGIN - 24;

      bool overTitle = (mx >= titleLeft && mx <= titleRight && my >= titleTop && my <= titleBottom);
      bool overMinimizeBtn = (mx >= minBtnLeft);
      if(!overTitle || overMinimizeBtn)
         return;

      g_titleDragging = true;
      g_titleDragOffsetX = mx - g_panelOriginX;
      g_titleDragOffsetY = my - g_panelOriginY;
     }

   PanelMoveTo(mx - g_titleDragOffsetX, my - g_titleDragOffsetY);
  }

//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id == CHARTEVENT_CLICK)
     {
      PanelHandleChartClick((int)lparam, (int)dparam);
      return;
     }

   if(id == CHARTEVENT_MOUSE_MOVE)
     {
      PanelHandleMouseMove((int)lparam, (int)dparam, sparam);
      return;
     }

   if(id != CHARTEVENT_OBJECT_CLICK)
      return;

   if(sparam == PANEL_PREFIX + "MinimizeBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelToggleMinimize();
     }
   else if(sparam == PANEL_PREFIX + "PickZoneBtn")
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
   else if(sparam == PANEL_PREFIX + "TrailLockMinusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustTrailLock(-1);
     }
   else if(sparam == PANEL_PREFIX + "TrailLockPlusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustTrailLock(1);
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
   else if(sparam == PANEL_PREFIX + "ExtendUpMinusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustExtendUp(-0.5);
     }
   else if(sparam == PANEL_PREFIX + "ExtendUpPlusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustExtendUp(0.5);
     }
   else if(sparam == PANEL_PREFIX + "ExtendDownMinusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustExtendDown(-0.5);
     }
   else if(sparam == PANEL_PREFIX + "ExtendDownPlusBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelAdjustExtendDown(0.5);
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
   else if(sparam == PANEL_PREFIX + "BuyMarketBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelPlaceMarketZone("BUY");
     }
   else if(sparam == PANEL_PREFIX + "SellMarketBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelPlaceMarketZone("SELL");
     }
   else if(sparam == PANEL_PREFIX + "ClosePendingBtn")
     {
      ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
      PanelCloseAllPending();
     }
  }
//+------------------------------------------------------------------+

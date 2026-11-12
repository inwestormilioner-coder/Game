//+------------------------------------------------------------------+
//|                                  CRT_TBS_SMC_Sniper_EA_PRO.mq5   |
//|   Candle Range Theory + Turtle Soup + SMC (MSS / FVG / OB)       |
//|   Multi-timeframe sniper EA:  H1 CRT -> M15 liquidity ->         |
//|   M5 sweep + reclaim -> M1 MSS + displacement -> FVG/OB entry    |
//+------------------------------------------------------------------+
#property copyright   "CRT TBS SMC Sniper EA PRO"
#property version     "1.00"
#property description "H1 CRT range -> M15 liquidity -> M5 Turtle Soup sweep & reclaim"
#property description "-> M1 Market Structure Shift + displacement -> FVG / Order Block sniper entry."
#property description "Risk-based sizing, break-even, partials, trailing, daily limits, sessions, news blackout."


#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| ENUMERATIONS                                                     |
//+------------------------------------------------------------------+
enum ENUM_CRT_MODE
  {
   CRT_PREV_CANDLE   = 0, // Previous closed candle
   CRT_PREV_2CANDLES = 1, // Previous 2-candle range
   CRT_PREV_3CANDLES = 2, // Previous 3-candle range
   CRT_PREV_SESSION  = 3  // Previous trading session range
  };

enum ENUM_SWEEP_SOURCE
  {
   SWEEP_CRT_ONLY      = 0, // CRT High/Low only
   SWEEP_CRT_AND_LIQ   = 1, // CRT High/Low + M15 liquidity
   SWEEP_LIQ_ONLY      = 2  // M15 liquidity only
  };

enum ENUM_MSS_SWING_MODE
  {
   MSS_SWING_BEFORE_SWEEP = 0, // Swing formed before sweep extreme (strict)
   MSS_SWING_ANY_RECENT   = 1  // Most recent unbroken swing (loose)
  };

enum ENUM_OB_ZONE
  {
   OB_ZONE_BODY = 0, // Candle body
   OB_ZONE_WICK = 1  // Full candle range (wick to wick)
  };

enum ENUM_ENTRY_MODE
  {
   ENTRY_MARKET         = 0, // Market order after M1 confirmation
   ENTRY_LIMIT_FVG      = 1, // Limit order at FVG level (default 50%)
   ENTRY_LIMIT_OB       = 2, // Limit order at Order Block level
   ENTRY_LIMIT_DISCOUNT = 3  // Limit order at discount/premium of the leg
  };

enum ENUM_TP_MODE
  {
   TP_CRT_OPPOSITE = 0, // CRT opposite boundary
   TP_RISK_REWARD  = 1, // Fixed Risk:Reward
   TP_LIQUIDITY    = 2, // Next opposing liquidity pool
   TP_MULTI        = 3  // Multiple targets (partials)
  };

enum ENUM_RR_PRESET
  {
   RR_1_1   = 0, // 1:1
   RR_1_1_5 = 1, // 1:1.5
   RR_1_2   = 2, // 1:2
   RR_1_3   = 3, // 1:3
   RR_CUSTOM= 4  // Custom
  };

enum ENUM_LOT_MODE
  {
   LOT_FIXED        = 0, // Fixed lot
   LOT_RISK_PERCENT = 1  // % risk per trade
  };

enum ENUM_RISK_BASE
  {
   RISK_BASE_BALANCE = 0, // Balance
   RISK_BASE_EQUITY  = 1  // Equity
  };

enum ENUM_DAILY_SCOPE
  {
   DAILY_SCOPE_ACCOUNT = 0, // Whole account
   DAILY_SCOPE_EA      = 1  // This EA only (magic + symbol)
  };

enum ENUM_TRAIL_MODE
  {
   TRAIL_NONE   = 0, // Disabled
   TRAIL_POINTS = 1, // Fixed distance (units)
   TRAIL_ATR    = 2  // ATR multiple
  };

enum ENUM_LOG_LEVEL
  {
   LOG_NONE     = 0, // None
   LOG_BASIC    = 1, // Basic (decisions + trades)
   LOG_DETAILED = 2  // Detailed (every step)
  };

enum ENUM_SETUP_STATE
  {
   ST_WAITING_FOR_RANGE = 0,
   ST_RANGE_IDENTIFIED,
   ST_WAITING_FOR_LIQUIDITY_SWEEP,
   ST_SWEEP_DETECTED,
   ST_WAITING_FOR_RECLAIM,
   ST_RECLAIM_CONFIRMED,
   ST_WAITING_FOR_MSS,
   ST_MSS_CONFIRMED,
   ST_WAITING_FOR_ENTRY,
   ST_TRADE_OPEN,
   ST_SETUP_COMPLETED,
   ST_SETUP_INVALIDATED
  };

// liquidity source codes
#define LIQ_SWING      0
#define LIQ_EQUAL      1
#define LIQ_PREV_DAY   2
#define LIQ_SESSION    3
#define LIQ_CRT        4

// zone status
#define ZONE_NONE       0
#define ZONE_UNTOUCHED  1
#define ZONE_PARTIAL    2
#define ZONE_FILLED     3

//+------------------------------------------------------------------+
//| INPUTS                                                           |
//+------------------------------------------------------------------+
input group "A. GENERAL SETTINGS"
input long             InpMagic               = 20261112;      // Magic number (unique per chart)
input string           InpOrderComment        = "CRT-TBS";     // Order comment prefix
input bool             InpAutoTradingDefault  = true;          // Auto trading ON at start
input bool             InpDiagnosticMode      = false;         // Diagnostic mode (signals only, never trades)
input double           InpDistUnit            = 0.0;           // Distance unit in price (0 = symbol point). XAUUSD: 0.01
input int              InpSlippagePts         = 30;            // Max slippage / deviation (symbol points)
input bool             InpAllowBuy            = true;          // Allow BUY setups
input bool             InpAllowSell           = true;          // Allow SELL setups
input int              InpATRPeriod           = 14;            // ATR period (M1/M5/M15 ATR)

input group "B. CRT SETTINGS"
input ENUM_TIMEFRAMES  InpCRTTimeframe        = PERIOD_H1;     // CRT reference timeframe
input ENUM_CRT_MODE    InpCRTMode             = CRT_PREV_CANDLE; // CRT reference range mode
input double           InpCRTMinRange         = 150;           // Min CRT range size (units)
input double           InpCRTMaxRange         = 5000;          // Max CRT range size (units, 0 = off)
input bool             InpCRTRequireBias      = true;          // BUY only from discount (<=50%), SELL only from premium (>=50%)

input group "C. LIQUIDITY SETTINGS (M15)"
input ENUM_TIMEFRAMES  InpLiqTimeframe        = PERIOD_M15;    // Liquidity timeframe
input int              InpLiqLookbackBars     = 96;            // Bars scanned for liquidity
input int              InpLiqSwingDepth       = 3;             // Swing depth (bars left/right)
input bool             InpUseSwingLevels      = true;          // Use swing highs/lows
input bool             InpUseEqualLevels      = true;          // Use equal highs/lows
input double           InpEqualTolerance      = 30;            // Equal highs/lows tolerance (units)
input bool             InpUsePrevDayHL        = true;          // Use previous day high/low
input bool             InpUsePrevSessionHL    = true;          // Use previous session high/low
input double           InpLiqMaxDistATR       = 3.0;           // Max distance of a pool from CRT range (x M15 ATR, 0 = no filter)
input int              InpMaxLiqLevels        = 12;            // Max liquidity levels kept per side

input group "D. TBS (TURTLE SOUP) SETTINGS (M5)"
input ENUM_SWEEP_SOURCE InpSweepSource        = SWEEP_CRT_AND_LIQ; // Levels eligible for sweep
input double           InpSweepMinBreach      = 20;            // Min breach beyond level (units)
input double           InpSweepMinBreachATR   = 0.0;           // Min breach as x M5 ATR (0 = off, max of both used)
input double           InpSweepMaxDepthATR    = 3.0;           // Max sweep depth x M5 ATR (0 = off) - deeper = breakout
input double           InpReclaimMinClose     = 5;             // Reclaim close must be beyond level by (units)
input int              InpReclaimMaxBars      = 3;             // Max M5 bars to reclaim after sweep
input double           InpBreakoutCloseATR    = 0.6;           // M5 close beyond level by > x ATR = genuine breakout
input int              InpBreakoutBars        = 2;             // Consecutive M5 closes beyond level = genuine breakout
input double           InpMinRejectWick       = 0.30;          // Min rejection wick ratio for 1-candle sweep (0 = off)

input group "E. MSS SETTINGS (M1)"
input ENUM_MSS_SWING_MODE InpMSSSwingMode     = MSS_SWING_BEFORE_SWEEP; // MSS swing selection
input int              InpMSSSwingDepth       = 2;             // M1 swing depth (bars left/right)
input int              InpMSSLookbackBars     = 60;            // M1 lookback before sweep for swing (bars)
input double           InpMSSMinBreak         = 5;             // Min close beyond swing (units)
input int              InpSetupExpiryMin      = 90;            // Setup expiry after sweep (minutes)
input bool             InpRequireDisplacement = true;          // Displacement mandatory
input double           InpDispMinBody         = 0;             // Displacement min body (units, 0 = off)
input double           InpDispATRMult         = 1.2;           // Displacement body >= x M1 ATR (0 = off)
input double           InpDispBodyRatio       = 0.55;          // Displacement body / range ratio
input int              InpDispLookback        = 5;             // Displacement must be within N bars up to MSS bar
input int              InpMSSMaxAgeMarket     = 3;             // Max age of MSS bar for market entry (M1 bars)

input group "F. FVG SETTINGS (M1)"
input bool             InpUseFVG              = true;          // Detect FVG
input bool             InpRequireFVG          = false;         // FVG mandatory
input double           InpFVGMinSize          = 10;            // Min FVG size (units)
input double           InpFVGMinSizeATR       = 0.0;           // Min FVG size x M1 ATR (0 = off)
input bool             InpFVGAllowPartial     = true;          // Accept partially mitigated FVG
input double           InpFVGEntryLevel       = 0.5;           // FVG entry level (0 = proximal edge, 0.5 = midpoint, 1 = distal)

input group "G. ORDER BLOCK SETTINGS (M1)"
input bool             InpUseOB               = true;          // Detect Order Block
input bool             InpRequireOB           = false;         // Order Block mandatory
input ENUM_OB_ZONE     InpOBZone              = OB_ZONE_BODY;  // OB zone definition
input bool             InpOBRetestRequired    = false;         // Market entry only after OB retest + rejection
input double           InpOBEntryLevel        = 0.5;           // OB entry level (0 = proximal, 0.5 = midpoint, 1 = distal)
input int              InpOBMaxSearchBars     = 10;            // Max bars searched back from displacement

input group "H. ENTRY SETTINGS"
input ENUM_ENTRY_MODE  InpEntryMode           = ENTRY_MARKET;  // Entry method
input double           InpDiscountLevel       = 0.5;           // Discount/premium retracement of the leg (0.5 = equilibrium)
input bool             InpFallbackToMarket    = true;          // Market entry if limit level unavailable / already traded through
input int              InpPendingExpiryMin    = 30;            // Pending order expiration (minutes)
input int              InpConfirmWaitBars     = 5;             // Max M1 bars after MSS to wait for FVG/OB/retest
input double           InpCancelPendingAtR    = 1.0;           // Cancel pending if price runs x R away before fill (0 = off)
input int              InpMinScore            = 8;             // Minimum confluence score (0..11)
input bool             InpCarryActiveSetup    = false;         // Keep setups past reclaim alive across a new CRT range

input group "I. STOP LOSS SETTINGS"
input double           InpSLBuffer            = 30;            // SL buffer beyond sweep extreme (units)
input double           InpSLBufferATR         = 0.0;           // Additional SL buffer x M5 ATR
input double           InpMinSL               = 100;           // Min SL distance (units) - SL widened to this
input double           InpMaxSL               = 1500;          // Max SL distance (units) - trade rejected above

input group "J. TAKE PROFIT SETTINGS"
input ENUM_TP_MODE     InpTPMode              = TP_MULTI;      // TP mode
input ENUM_RR_PRESET   InpRRPreset            = RR_1_2;        // RR preset (TP mode RR / fallback)
input double           InpCustomRR            = 2.5;           // Custom RR
input double           InpMinRR               = 1.0;           // Minimum RR accepted (CRT / liquidity targets)
input double           InpTP1_R               = 1.0;           // Multi: TP1 at R
input double           InpTP1_Pct             = 50;            // Multi: TP1 close % of initial volume
input double           InpTP2_R               = 2.0;           // Multi: TP2 at R
input double           InpTP2_Pct             = 25;            // Multi: TP2 close % of initial volume
input double           InpTP3_R               = 3.0;           // Multi: TP3 (final TP) at R

input group "K. RISK MANAGEMENT"
input ENUM_LOT_MODE    InpLotMode             = LOT_RISK_PERCENT; // Lot sizing mode
input double           InpFixedLot            = 0.01;          // Fixed lot
input double           InpRiskPercent         = 1.0;           // Risk per trade (%)
input ENUM_RISK_BASE   InpRiskBase            = RISK_BASE_BALANCE; // Risk base
input bool             InpAllowMinLotOverRisk = false;         // Allow min lot if it exceeds risk
input double           InpMaxRiskPctHard      = 2.0;           // Hard cap of real risk per trade (%)
input ENUM_DAILY_SCOPE InpDailyScope          = DAILY_SCOPE_ACCOUNT; // Daily P/L scope
input double           InpMaxDailyLossPct     = 3.0;           // Max daily loss (% of day-start balance, 0 = off)
input double           InpMaxDailyLossMoney   = 0;             // Max daily loss (money, 0 = off)
input double           InpMaxDailyProfitPct   = 0;             // Max daily profit (% , 0 = off)
input double           InpMaxDailyProfitMoney = 0;             // Max daily profit (money, 0 = off)
input bool             InpCloseOnDailyLoss    = false;         // Close EA positions when daily loss hit
input double           InpEquityProtectPct    = 4.0;           // Daily equity protection: close all at x% DD (0 = off)
input int              InpMaxOpenPositions    = 1;             // Max open positions + pendings (this EA)
input int              InpMaxTradesPerDay     = 4;             // Max trades per day
input int              InpMaxTradesPerSetup   = 1;             // Max trades per setup (per sweep)
input int              InpMaxConsecLosses     = 3;             // Max consecutive losses per day (0 = off)
input double           InpMaxSpread           = 60;            // Max spread (units)
input double           InpMinATRM5            = 0;             // Min M5 ATR (units) - low liquidity filter (0 = off)
// Martingale / grid / averaging are intentionally NOT implemented (always disabled).

input group "L. TRADE MANAGEMENT"
input bool             InpUseBreakEven        = true;          // Use break-even
input double           InpBETriggerR          = 1.0;           // BE trigger (R multiple)
input double           InpBEOffset            = 10;            // BE offset beyond entry (units)
input ENUM_TRAIL_MODE  InpTrailMode           = TRAIL_NONE;    // Trailing stop mode
input double           InpTrailStartR         = 1.5;           // Trailing starts at R
input double           InpTrailDistance       = 300;           // Trailing distance (units, mode points)
input double           InpTrailATRMult        = 2.0;           // Trailing ATR multiple (M5 ATR)
input double           InpTrailStep           = 10;            // Min SL improvement step (units)
input bool             InpUsePartials         = true;          // Partial closes (TP mode Multi)
input int              InpMaxHoldMinutes      = 0;             // Max holding time (minutes, 0 = off)
input bool             InpCloseOnInvalidation = true;          // Close if M5 closes beyond sweep extreme

input group "M. SESSION FILTER (times in GMT)"
input bool             InpUseSessionFilter    = true;          // Trade only inside enabled sessions
input bool             InpAutoGMTOffset       = true;          // Auto-detect broker GMT offset (live only)
input double           InpServerGMTOffset     = 2.0;           // Broker server GMT offset (hours) - tester / manual
input bool             InpAsianOn             = false;         // Asian session enabled
input string           InpAsianStart          = "00:00";       // Asian start (GMT)
input string           InpAsianEnd            = "07:00";       // Asian end (GMT)
input bool             InpLondonOn            = true;          // London session enabled
input string           InpLondonStart         = "07:00";       // London start (GMT)
input string           InpLondonEnd           = "16:00";       // London end (GMT)
input bool             InpNYOn                = true;          // New York session enabled
input string           InpNYStart             = "12:00";       // New York start (GMT)
input string           InpNYEnd               = "21:00";       // New York end (GMT)
input bool             InpOverlapOn           = true;          // London/NY overlap enabled
input string           InpOverlapStart        = "12:00";       // Overlap start (GMT)
input string           InpOverlapEnd          = "16:00";       // Overlap end (GMT)
input string           InpNoTradePeriods      = "20:55-21:15"; // No-trading periods GMT "HH:MM-HH:MM;..." (empty = none)
input bool             InpNoTradeFriday       = true;          // Block new trades late Friday
input int              InpFridayCutoffHourGMT = 19;            // Friday cut-off hour (GMT)

input group "N. NEWS FILTER (manual blackout)"
input bool             InpUseNewsFilter       = false;         // Use manual news blackout
input string           InpNewsEvents          = "";            // Events "YYYY.MM.DD HH:MM;..." (GMT)
input string           InpNewsDailyTimes      = "";            // Daily recurring "HH:MM;HH:MM" (GMT), e.g. NFP-style slots
input int              InpNewsMinutesBefore   = 30;            // Blackout minutes before event
input int              InpNewsMinutesAfter    = 30;            // Blackout minutes after event
input bool             InpNewsCancelPending   = true;          // Cancel pending orders during blackout
input bool             InpNewsClosePositions  = false;         // Close EA positions during blackout

input group "O. DASHBOARD SETTINGS"
input bool             InpShowDashboard       = true;          // Show dashboard
input int              InpDashX               = 10;            // Dashboard X
input int              InpDashY               = 25;            // Dashboard Y
input int              InpDashFontSize        = 8;             // Dashboard font size
input bool             InpDrawObjects         = true;          // Draw chart objects
input int              InpKeepSetupDrawings   = 6;             // Keep drawings of last N setups
input color            InpBullColor           = clrDodgerBlue; // Bullish structure color
input color            InpBearColor           = clrOrangeRed;  // Bearish structure color
input color            InpCRTColor            = clrGold;       // CRT range color

input group "P. DEBUG SETTINGS"
input ENUM_LOG_LEVEL   InpLogLevel            = LOG_BASIC;     // Log level
input bool             InpLogRejections       = true;          // Log every rejection reason

//+------------------------------------------------------------------+
//| STRUCTURES                                                       |
//+------------------------------------------------------------------+
struct SRange
  {
   bool              valid;
   double            high;
   double            low;
   double            mid;
   datetime          id;          // identifier of the reference period
   datetime          refStart;    // start time of the reference candles / session
   datetime          periodStart; // sweeps are accepted from this time
  };

struct SLiqLevel
  {
   double            price;
   int               side;        // +1 = high (buy-side liquidity), -1 = low (sell-side liquidity)
   int               src;         // LIQ_*
   datetime          time;        // formation time
  };

struct SSetup
  {
   int               dir;               // +1 buy, -1 sell
   ENUM_SETUP_STATE  state;
   ulong             id;                // unique setup id
   datetime          rangeId;
   double            level;             // swept level
   int               levelSrc;
   double            extreme;           // sweep extreme
   datetime          sweepTime;         // M5 bar of the sweep
   datetime          reclaimTime;       // M5 bar of the reclaim close
   int               reclaimWait;       // M5 bars waited
   int               beyondCount;       // consecutive M5 closes beyond level
   datetime          extremeTimeM1;     // M1 bar of the extreme
   datetime          expiry;
   double            mssLevel;
   datetime          mssSwingTime;
   datetime          mssTime;           // M1 bar that confirmed MSS
   bool              displacement;
   datetime          dispTime;
   double            legExtreme;        // max high (buy) / min low (sell) of the leg after extreme
   int               fvgStatus;
   double            fvgTop;
   double            fvgBottom;
   datetime          fvgTime;
   int               obStatus;          // ZONE_* (FILLED = invalid)
   double            obTop;
   double            obBottom;
   datetime          obTime;
   bool              obRetested;
   int               confirmWait;       // M1 bars waited after MSS
   int               score;
   ulong             orderTicket;       // pending / market order ticket (= position identifier)
   ulong             positionId;
   datetime          pendingExpiry;
   double            plannedEntry;
   double            plannedSL;
   double            plannedTP;
   int               tradesTaken;
   datetime          lastTradeTime;
  };

struct SDailyStats
  {
   datetime          dayStart;
   double            dayStartBalance;
   double            closedPL;      // scope-dependent
   double            closedPLAcc;   // account-level closed P/L today
   int               tradesToday;
   int               consecLosses;
   bool              halted;
   string            haltReason;
  };

//+------------------------------------------------------------------+
//| GLOBALS                                                          |
//+------------------------------------------------------------------+
CTrade        g_trade;
SRange        g_range;
SLiqLevel     g_liq[];
SSetup        g_setup[2];        // [0] = BUY, [1] = SELL
string        g_reason[2];       // last rejection / info per side
SDailyStats   g_stats;

double        g_unit        = 0.0;
double        g_point       = 0.0;
double        g_tickSize    = 0.0;
int           g_digits      = 0;
bool          g_hedging     = false;
bool          g_autoTrading = true;
bool          g_isTester    = false;
bool          g_visual      = true;
bool          g_statsDirty  = true;
int           g_gmtOffsetSec= 0;
ulong         g_setupCounter= 0;

int           g_hATR_M1 = INVALID_HANDLE;
int           g_hATR_M5 = INVALID_HANDLE;
int           g_hATR_LQ = INVALID_HANDLE;

datetime      g_lastM1 = 0, g_lastM5 = 0, g_lastLQ = 0, g_lastCRT = 0, g_lastDay = 0;
datetime      g_lastOrderBar = 0;
datetime      g_lastDashUpdate = 0;
datetime      g_lastGMTCalc = 0;

// used (already swept) levels for current range
double        g_usedLevels[];
int           g_usedDirs[];

// drawn setup ids (for cleanup)
ulong         g_drawnSetups[];

// dashboard confirmation
string        g_confirmBtn  = "";
datetime      g_confirmTime = 0;

// news
datetime      g_newsTimes[];
int           g_newsDaily[];     // minutes of day (GMT)
int           g_noTradeStart[];
int           g_noTradeEnd[];

string        g_gvPrefix = "";
const string  OBJ_PREFIX  = "CRTV_";
const string  DASH_PREFIX = "CRTD_";

//+------------------------------------------------------------------+
//| UTILITIES                                                        |
//+------------------------------------------------------------------+
double U(const double units) { return units * g_unit; }

void Log(const ENUM_LOG_LEVEL lvl, const string msg)
  {
   if(InpLogLevel >= lvl && lvl != LOG_NONE)
      Print("[CRT-TBS ", _Symbol, "] ", msg);
  }

string DirStr(const int dir) { return (dir > 0 ? "BUY" : "SELL"); }
int    SideIdx(const int dir) { return (dir > 0 ? 0 : 1); }

string StateStr(const ENUM_SETUP_STATE st)
  {
   switch(st)
     {
      case ST_WAITING_FOR_RANGE:           return "WAITING_FOR_RANGE";
      case ST_RANGE_IDENTIFIED:            return "RANGE_IDENTIFIED";
      case ST_WAITING_FOR_LIQUIDITY_SWEEP: return "WAITING_FOR_SWEEP";
      case ST_SWEEP_DETECTED:              return "SWEEP_DETECTED";
      case ST_WAITING_FOR_RECLAIM:         return "WAITING_FOR_RECLAIM";
      case ST_RECLAIM_CONFIRMED:           return "RECLAIM_CONFIRMED";
      case ST_WAITING_FOR_MSS:             return "WAITING_FOR_MSS";
      case ST_MSS_CONFIRMED:               return "MSS_CONFIRMED";
      case ST_WAITING_FOR_ENTRY:           return "WAITING_FOR_ENTRY";
      case ST_TRADE_OPEN:                  return "TRADE_OPEN";
      case ST_SETUP_COMPLETED:             return "SETUP_COMPLETED";
      case ST_SETUP_INVALIDATED:           return "SETUP_INVALIDATED";
     }
   return "UNKNOWN";
  }

string LiqSrcStr(const int src)
  {
   switch(src)
     {
      case LIQ_SWING:    return "SWING";
      case LIQ_EQUAL:    return "EQUAL";
      case LIQ_PREV_DAY: return "PREV_DAY";
      case LIQ_SESSION:  return "SESSION";
      case LIQ_CRT:      return "CRT";
     }
   return "?";
  }

string P(const double price) { return DoubleToString(price, g_digits); }

double NormPrice(const double price)
  {
   if(g_tickSize <= 0.0)
      return NormalizeDouble(price, g_digits);
   return NormalizeDouble(MathRound(price / g_tickSize) * g_tickSize, g_digits);
  }

// round SL away from entry (more conservative) to tick size
double NormSL(const double price, const int dir)
  {
   if(g_tickSize <= 0.0)
      return NormalizeDouble(price, g_digits);
   double t = price / g_tickSize;
   double r = (dir > 0 ? MathFloor(t + 1e-9) : MathCeil(t - 1e-9));
   return NormalizeDouble(r * g_tickSize, g_digits);
  }

double Ask() { return SymbolInfoDouble(_Symbol, SYMBOL_ASK); }
double Bid() { return SymbolInfoDouble(_Symbol, SYMBOL_BID); }

double SpreadUnits()
  {
   double s = Ask() - Bid();
   return (g_unit > 0 ? s / g_unit : 0);
  }

double GetATR(const int handle)
  {
   if(handle == INVALID_HANDLE)
      return 0.0;
   double buf[];
   if(CopyBuffer(handle, 0, 1, 1, buf) != 1)
      return 0.0;
   return buf[0];
  }

bool IsNewBar(const ENUM_TIMEFRAMES tf, datetime &last)
  {
   datetime t = iTime(_Symbol, tf, 0);
   if(t == 0)
      return false;
   if(t != last)
     {
      last = t;
      return true;
     }
   return false;
  }

int ParseHHMM(const string s)
  {
   string parts[];
   string tmp = s;
   StringTrimLeft(tmp);
   StringTrimRight(tmp);
   if(StringSplit(tmp, ':', parts) != 2)
      return -1;
   int h = (int)StringToInteger(parts[0]);
   int m = (int)StringToInteger(parts[1]);
   if(h < 0 || h > 24 || m < 0 || m > 59)
      return -1;
   return h * 60 + m;
  }

datetime ServerToGMT(const datetime t) { return (datetime)(t - g_gmtOffsetSec); }
datetime GMTToServer(const datetime t) { return (datetime)(t + g_gmtOffsetSec); }

int MinuteOfDay(const datetime t)
  {
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.hour * 60 + dt.min;
  }

datetime DayStart(const datetime t) { long v = (long)t; return (datetime)(v - (v % 86400)); }

bool InWindow(const int nowMin, const int startMin, const int endMin)
  {
   if(startMin < 0 || endMin < 0)
      return false;
   if(startMin == endMin)
      return false;
   if(startMin < endMin)
      return (nowMin >= startMin && nowMin < endMin);
   return (nowMin >= startMin || nowMin < endMin); // wraps midnight
  }

void UpdateGMTOffset()
  {
   if(InpAutoGMTOffset && !g_isTester)
     {
      long diff = (long)(TimeTradeServer() - TimeGMT());
      // round to nearest 15 minutes
      long q = (long)MathRound((double)diff / 900.0) * 900;
      g_gmtOffsetSec = (int)q;
     }
   else
      g_gmtOffsetSec = (int)MathRound(InpServerGMTOffset * 3600.0);
  }

//--- Global variable helpers (restart recovery) --------------------
string GVName(const ulong id, const string key)
  {
   return g_gvPrefix + IntegerToString((long)id) + "_" + key;
  }
void   GVSet(const ulong id, const string key, const double v) { GlobalVariableSet(GVName(id, key), v); }
double GVGet(const ulong id, const string key, const double def = 0.0)
  {
   string n = GVName(id, key);
   if(!GlobalVariableCheck(n))
      return def;
   return GlobalVariableGet(n);
  }
bool   GVHas(const ulong id, const string key) { return GlobalVariableCheck(GVName(id, key)); }
void   GVDelAll(const ulong id) { GlobalVariablesDeleteAll(g_gvPrefix + IntegerToString((long)id) + "_"); }

//+------------------------------------------------------------------+
//| SESSIONS / NEWS / TIME FILTERS                                   |
//+------------------------------------------------------------------+
bool SessionActive(const bool enabled, const string st, const string en, const int nowMinGMT)
  {
   if(!enabled)
      return false;
   return InWindow(nowMinGMT, ParseHHMM(st), ParseHHMM(en));
  }

string CurrentSessionName()
  {
   int m = MinuteOfDay(ServerToGMT(TimeCurrent()));
   string s = "";
   if(InWindow(m, ParseHHMM(InpOverlapStart), ParseHHMM(InpOverlapEnd)))
      s = "LDN/NY OVERLAP";
   else
      if(InWindow(m, ParseHHMM(InpLondonStart), ParseHHMM(InpLondonEnd)))
         s = "LONDON";
      else
         if(InWindow(m, ParseHHMM(InpNYStart), ParseHHMM(InpNYEnd)))
            s = "NEW YORK";
         else
            if(InWindow(m, ParseHHMM(InpAsianStart), ParseHHMM(InpAsianEnd)))
               s = "ASIAN";
            else
               s = "OFF-SESSION";
   return s;
  }

bool InEnabledSession()
  {
   int m = MinuteOfDay(ServerToGMT(TimeCurrent()));
   if(SessionActive(InpAsianOn,   InpAsianStart,   InpAsianEnd,   m)) return true;
   if(SessionActive(InpLondonOn,  InpLondonStart,  InpLondonEnd,  m)) return true;
   if(SessionActive(InpNYOn,      InpNYStart,      InpNYEnd,      m)) return true;
   if(SessionActive(InpOverlapOn, InpOverlapStart, InpOverlapEnd, m)) return true;
   return false;
  }

void ParseFilters()
  {
   //--- no-trade periods
   ArrayResize(g_noTradeStart, 0);
   ArrayResize(g_noTradeEnd, 0);
   string items[];
   int n = StringSplit(InpNoTradePeriods, ';', items);
   for(int i = 0; i < n; i++)
     {
      string it = items[i];
      StringTrimLeft(it);
      StringTrimRight(it);
      if(StringLen(it) < 9)
         continue;
      string se[];
      if(StringSplit(it, '-', se) != 2)
         continue;
      int a = ParseHHMM(se[0]);
      int b = ParseHHMM(se[1]);
      if(a < 0 || b < 0)
        {
         Log(LOG_BASIC, "Invalid no-trade period ignored: " + it);
         continue;
        }
      int k = ArraySize(g_noTradeStart);
      ArrayResize(g_noTradeStart, k + 1);
      ArrayResize(g_noTradeEnd, k + 1);
      g_noTradeStart[k] = a;
      g_noTradeEnd[k]   = b;
     }
   //--- news events (GMT)
   ArrayResize(g_newsTimes, 0);
   string ev[];
   n = StringSplit(InpNewsEvents, ';', ev);
   for(int i = 0; i < n; i++)
     {
      string it = ev[i];
      StringTrimLeft(it);
      StringTrimRight(it);
      if(StringLen(it) < 10)
         continue;
      datetime t = StringToTime(it);
      if(t <= 0)
        {
         Log(LOG_BASIC, "Invalid news event ignored: " + it);
         continue;
        }
      int k = ArraySize(g_newsTimes);
      ArrayResize(g_newsTimes, k + 1);
      g_newsTimes[k] = t;
     }
   //--- daily recurring news slots
   ArrayResize(g_newsDaily, 0);
   string dl[];
   n = StringSplit(InpNewsDailyTimes, ';', dl);
   for(int i = 0; i < n; i++)
     {
      int m = ParseHHMM(dl[i]);
      if(m < 0)
         continue;
      int k = ArraySize(g_newsDaily);
      ArrayResize(g_newsDaily, k + 1);
      g_newsDaily[k] = m;
     }
  }

bool InNoTradePeriod(string &why)
  {
   datetime g = ServerToGMT(TimeCurrent());
   int m = MinuteOfDay(g);
   for(int i = 0; i < ArraySize(g_noTradeStart); i++)
      if(InWindow(m, g_noTradeStart[i], g_noTradeEnd[i]))
        {
         why = "no-trade period";
         return true;
        }
   if(InpNoTradeFriday)
     {
      MqlDateTime dt;
      TimeToStruct(g, dt);
      if(dt.day_of_week == 5 && dt.hour >= InpFridayCutoffHourGMT)
        {
         why = "Friday cut-off";
         return true;
        }
     }
   return false;
  }

bool InNewsBlackout(string &why)
  {
   if(!InpUseNewsFilter)
      return false;
   datetime g = ServerToGMT(TimeCurrent());
   long before = (long)InpNewsMinutesBefore * 60;
   long after  = (long)InpNewsMinutesAfter * 60;
   for(int i = 0; i < ArraySize(g_newsTimes); i++)
     {
      long d = (long)g - (long)g_newsTimes[i];
      if(d >= -before && d <= after)
        {
         why = "news blackout " + TimeToString(g_newsTimes[i], TIME_DATE | TIME_MINUTES) + " GMT";
         return true;
        }
     }
   if(ArraySize(g_newsDaily) > 0)
     {
      MqlDateTime dt;
      TimeToStruct(g, dt);
      if(dt.day_of_week >= 1 && dt.day_of_week <= 5)
        {
         datetime day = DayStart(g);
         for(int i = 0; i < ArraySize(g_newsDaily); i++)
           {
            long ev = (long)day + (long)g_newsDaily[i] * 60;
            long d = (long)g - ev;
            if(d >= -before && d <= after)
              {
               why = StringFormat("daily news slot %02d:%02d GMT", g_newsDaily[i] / 60, g_newsDaily[i] % 60);
               return true;
              }
           }
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| PREVIOUS SESSION RANGE                                           |
//+------------------------------------------------------------------+
bool GetPrevSessionRange(datetime &sStartSrv, datetime &sEndSrv, double &hi, double &lo, string &name)
  {
   string names[3]  = {"ASIAN", "LONDON", "NEW YORK"};
   string starts[3];
   string ends[3];
   starts[0] = InpAsianStart;  ends[0] = InpAsianEnd;
   starts[1] = InpLondonStart; ends[1] = InpLondonEnd;
   starts[2] = InpNYStart;     ends[2] = InpNYEnd;

   datetime nowG = ServerToGMT(TimeCurrent());
   datetime day  = DayStart(nowG);
   datetime bestEnd = 0, bestStart = 0;
   double   bestHi = 0, bestLo = 0;
   string   bestName = "";

   for(int s = 0; s < 3; s++)
     {
      int st = ParseHHMM(starts[s]);
      int en = ParseHHMM(ends[s]);
      if(st < 0 || en < 0 || st == en)
         continue;
      for(int d = 0; d < 5; d++)
        {
         datetime base = (datetime)(day - d * 86400);
         datetime e = (datetime)(base + en * 60);
         datetime b = (datetime)(base + st * 60);
         if(st > en)
            b = (datetime)(b - 86400);
         if(e > nowG || e <= bestEnd)
            continue;
         MqlRates r[];
         int c = CopyRates(_Symbol, PERIOD_M5, GMTToServer(b), (datetime)(GMTToServer(e) - 1), r);
         if(c <= 0)
            continue;
         double h = r[0].high, l = r[0].low;
         for(int k = 1; k < c; k++)
           {
            h = MathMax(h, r[k].high);
            l = MathMin(l, r[k].low);
           }
         bestEnd = e;
         bestStart = b;
         bestHi = h;
         bestLo = l;
         bestName = names[s];
         break; // most recent occurrence for this session found
        }
     }
   if(bestEnd == 0)
      return false;
   sStartSrv = GMTToServer(bestStart);
   sEndSrv   = GMTToServer(bestEnd);
   hi = bestHi;
   lo = bestLo;
   name = bestName;
   return true;
  }

//+------------------------------------------------------------------+
//| H1 CRT RANGE                                                     |
//+------------------------------------------------------------------+
void OnNewRange();

bool UpdateCRTRange()
  {
   SRange nr;
   nr.valid = false;
   nr.high = 0;
   nr.low = 0;
   nr.mid = 0;
   nr.id = 0;
   nr.refStart = 0;
   nr.periodStart = 0;

   if(InpCRTMode == CRT_PREV_SESSION)
     {
      datetime ss, se;
      double hi, lo;
      string nm;
      if(!GetPrevSessionRange(ss, se, hi, lo, nm))
         return false;
      nr.high = hi;
      nr.low = lo;
      nr.id = ss;
      nr.refStart = ss;
      nr.periodStart = se;
     }
   else
     {
      int n = (InpCRTMode == CRT_PREV_CANDLE ? 1 : (InpCRTMode == CRT_PREV_2CANDLES ? 2 : 3));
      MqlRates r[];
      ArraySetAsSeries(r, true);
      if(CopyRates(_Symbol, InpCRTTimeframe, 1, n, r) != n)
         return false;
      double hi = r[0].high, lo = r[0].low;
      for(int i = 1; i < n; i++)
        {
         hi = MathMax(hi, r[i].high);
         lo = MathMin(lo, r[i].low);
        }
      datetime cur = iTime(_Symbol, InpCRTTimeframe, 0);
      if(cur == 0)
         return false;
      nr.high = hi;
      nr.low = lo;
      nr.id = cur;
      nr.refStart = r[n - 1].time;
      nr.periodStart = cur;
     }

   nr.mid = (nr.high + nr.low) / 2.0;
   double size = nr.high - nr.low;
   nr.valid = (size >= U(InpCRTMinRange) && (InpCRTMaxRange <= 0 || size <= U(InpCRTMaxRange)));

   if(nr.id != g_range.id)
     {
      g_range = nr;
      Log(LOG_BASIC, StringFormat("NEW CRT RANGE  High=%s  Low=%s  Mid=%s  Size=%.1f units  Valid=%s",
                                  P(nr.high), P(nr.low), P(nr.mid), size / g_unit, (nr.valid ? "YES" : "NO (size filter)")));
      OnNewRange();
     }
   else
     {
      g_range.valid = nr.valid;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| M15 LIQUIDITY                                                    |
//+------------------------------------------------------------------+
void AddLiq(const double price, const int side, const int src, const datetime t)
  {
   double tol = U(InpEqualTolerance) / 3.0;
   for(int i = 0; i < ArraySize(g_liq); i++)
     {
      if(g_liq[i].side == side && MathAbs(g_liq[i].price - price) <= tol)
        {
         // keep the more significant / extreme one
         if(src == LIQ_EQUAL || src == LIQ_PREV_DAY)
            g_liq[i].src = src;
         if(side > 0 && price > g_liq[i].price)
            g_liq[i].price = price;
         if(side < 0 && price < g_liq[i].price)
            g_liq[i].price = price;
         return;
        }
     }
   int k = ArraySize(g_liq);
   ArrayResize(g_liq, k + 1);
   g_liq[k].price = price;
   g_liq[k].side  = side;
   g_liq[k].src   = src;
   g_liq[k].time  = t;
  }

void RemoveLiq(const int idx)
  {
   int n = ArraySize(g_liq);
   if(idx < 0 || idx >= n)
      return;
   for(int i = idx; i < n - 1; i++)
      g_liq[i] = g_liq[i + 1];
   ArrayResize(g_liq, n - 1);
  }

void UpdateLiquidity()
  {
   ArrayResize(g_liq, 0);
   int depth = MathMax(1, InpLiqSwingDepth);
   int need  = InpLiqLookbackBars + depth + 2;
   MqlRates r[];
   ArraySetAsSeries(r, true);
   int n = CopyRates(_Symbol, InpLiqTimeframe, 0, need, r);
   if(n < depth * 2 + 3)
      return;

   //--- swings (confirmed: right side uses only closed bars, index >= 1)
   double sh[];  datetime sht[];
   double sl[];  datetime slt[];
   if(InpUseSwingLevels || InpUseEqualLevels)
     {
      for(int i = depth + 1; i < n - depth; i++)
        {
         bool isH = true, isL = true;
         for(int k = 1; k <= depth; k++)
           {
            if(!(r[i].high > r[i - k].high && r[i].high >= r[i + k].high))
               isH = false;
            if(!(r[i].low < r[i - k].low && r[i].low <= r[i + k].low))
               isL = false;
           }
         if(isH)
           {
            bool taken = false;
            for(int j = 1; j < i; j++)
               if(r[j].high > r[i].high) { taken = true; break; }
            if(!taken)
              {
               int c = ArraySize(sh);
               ArrayResize(sh, c + 1);
               ArrayResize(sht, c + 1);
               sh[c] = r[i].high;
               sht[c] = r[i].time;
              }
           }
         if(isL)
           {
            bool taken = false;
            for(int j = 1; j < i; j++)
               if(r[j].low < r[i].low) { taken = true; break; }
            if(!taken)
              {
               int c = ArraySize(sl);
               ArrayResize(sl, c + 1);
               ArrayResize(slt, c + 1);
               sl[c] = r[i].low;
               slt[c] = r[i].time;
              }
           }
        }
     }

   //--- equal highs / lows
   bool usedH[], usedL[];
   ArrayResize(usedH, ArraySize(sh));
   ArrayResize(usedL, ArraySize(sl));
   ArrayInitialize(usedH, false);
   ArrayInitialize(usedL, false);
   if(InpUseEqualLevels)
     {
      double tol = U(InpEqualTolerance);
      for(int a = 0; a < ArraySize(sh); a++)
         for(int b = a + 1; b < ArraySize(sh); b++)
            if(MathAbs(sh[a] - sh[b]) <= tol)
              {
               AddLiq(MathMax(sh[a], sh[b]), +1, LIQ_EQUAL, MathMax(sht[a], sht[b]));
               usedH[a] = true;
               usedH[b] = true;
              }
      for(int a = 0; a < ArraySize(sl); a++)
         for(int b = a + 1; b < ArraySize(sl); b++)
            if(MathAbs(sl[a] - sl[b]) <= tol)
              {
               AddLiq(MathMin(sl[a], sl[b]), -1, LIQ_EQUAL, MathMax(slt[a], slt[b]));
               usedL[a] = true;
               usedL[b] = true;
              }
     }
   if(InpUseSwingLevels)
     {
      for(int a = 0; a < ArraySize(sh); a++)
         if(!usedH[a])
            AddLiq(sh[a], +1, LIQ_SWING, sht[a]);
      for(int a = 0; a < ArraySize(sl); a++)
         if(!usedL[a])
            AddLiq(sl[a], -1, LIQ_SWING, slt[a]);
     }

   //--- previous day high / low (if not yet taken today)
   if(InpUsePrevDayHL)
     {
      double pdh = iHigh(_Symbol, PERIOD_D1, 1);
      double pdl = iLow(_Symbol, PERIOD_D1, 1);
      double tdh = iHigh(_Symbol, PERIOD_D1, 0);
      double tdl = iLow(_Symbol, PERIOD_D1, 0);
      datetime pdt = iTime(_Symbol, PERIOD_D1, 1);
      if(pdh > 0 && tdh > 0 && tdh <= pdh)
         AddLiq(pdh, +1, LIQ_PREV_DAY, pdt);
      if(pdl > 0 && tdl > 0 && tdl >= pdl)
         AddLiq(pdl, -1, LIQ_PREV_DAY, pdt);
     }

   //--- previous session high / low (if not yet taken since session end)
   if(InpUsePrevSessionHL)
     {
      datetime ss, se;
      double hi, lo;
      string nm;
      if(GetPrevSessionRange(ss, se, hi, lo, nm))
        {
         MqlRates s5[];
         int c = CopyRates(_Symbol, PERIOD_M5, se, TimeCurrent(), s5);
         double mx = -DBL_MAX, mn = DBL_MAX;
         for(int k = 0; k < c; k++)
           {
            mx = MathMax(mx, s5[k].high);
            mn = MathMin(mn, s5[k].low);
           }
         if(c <= 0 || mx <= hi)
            AddLiq(hi, +1, LIQ_SESSION, ss);
         if(c <= 0 || mn >= lo)
            AddLiq(lo, -1, LIQ_SESSION, ss);
        }
     }

   //--- relevance filter: pools near the CRT range
   if(g_range.valid && InpLiqMaxDistATR > 0)
     {
      double atr = GetATR(g_hATR_LQ);
      if(atr > 0)
        {
         double maxD = atr * InpLiqMaxDistATR;
         for(int i = ArraySize(g_liq) - 1; i >= 0; i--)
           {
            bool keep;
            if(g_liq[i].side > 0)
               keep = (g_liq[i].price >= g_range.low && g_liq[i].price <= g_range.high + maxD);
            else
               keep = (g_liq[i].price <= g_range.high && g_liq[i].price >= g_range.low - maxD);
            if(!keep)
               RemoveLiq(i);
           }
        }
     }

   //--- cap per side: drop the farthest from current price
   double px = Bid();
   for(int side = -1; side <= 1; side += 2)
     {
      while(true)
        {
         int cnt = 0, far = -1;
         double farD = -1;
         for(int i = 0; i < ArraySize(g_liq); i++)
           {
            if(g_liq[i].side != side)
               continue;
            cnt++;
            double d = MathAbs(g_liq[i].price - px);
            if(d > farD) { farD = d; far = i; }
           }
         if(cnt <= InpMaxLiqLevels || far < 0)
            break;
         RemoveLiq(far);
        }
     }

   if(InpLogLevel >= LOG_DETAILED)
     {
      string s = "LIQUIDITY MAP: ";
      for(int i = 0; i < ArraySize(g_liq); i++)
         s += StringFormat("[%s %s %s] ", (g_liq[i].side > 0 ? "H" : "L"), LiqSrcStr(g_liq[i].src), P(g_liq[i].price));
      Log(LOG_DETAILED, s);
     }
  }

//+------------------------------------------------------------------+
//| SETUP STATE MACHINE HELPERS                                      |
//+------------------------------------------------------------------+
void DrawSetupSweep(const SSetup &s);
void DrawSetupMSS(const SSetup &s);
void DrawSetupZones(const SSetup &s);
void DrawSetupPlan(const SSetup &s, const double entry, const double sl, const double tp);
bool DeletePendingOrder(const ulong ticket, const string why);

void ResetSetup(SSetup &s, const int dir, const ENUM_SETUP_STATE st)
  {
   s.dir = dir;
   s.state = st;
   s.id = 0;
   s.rangeId = g_range.id;
   s.level = 0;
   s.levelSrc = LIQ_CRT;
   s.extreme = 0;
   s.sweepTime = 0;
   s.reclaimTime = 0;
   s.reclaimWait = 0;
   s.beyondCount = 0;
   s.extremeTimeM1 = 0;
   s.expiry = 0;
   s.mssLevel = 0;
   s.mssSwingTime = 0;
   s.mssTime = 0;
   s.displacement = false;
   s.dispTime = 0;
   s.legExtreme = 0;
   s.fvgStatus = ZONE_NONE;
   s.fvgTop = 0;
   s.fvgBottom = 0;
   s.fvgTime = 0;
   s.obStatus = ZONE_NONE;
   s.obTop = 0;
   s.obBottom = 0;
   s.obTime = 0;
   s.obRetested = false;
   s.confirmWait = 0;
   s.score = 0;
   s.orderTicket = 0;
   s.positionId = 0;
   s.pendingExpiry = 0;
   s.plannedEntry = 0;
   s.plannedSL = 0;
   s.plannedTP = 0;
   s.tradesTaken = 0;
   s.lastTradeTime = 0;
  }

void SetState(SSetup &s, const ENUM_SETUP_STATE st, const string info = "")
  {
   if(s.state == st)
      return;
   Log(LOG_DETAILED, StringFormat("%s setup #%I64u: %s -> %s %s", DirStr(s.dir), s.id,
                                  StateStr(s.state), StateStr(st), info));
   s.state = st;
  }

void Reason(const int dir, const string why)
  {
   int k = SideIdx(dir);
   if(g_reason[k] != why && InpLogRejections)
      Log(LOG_BASIC, DirStr(dir) + " | " + why);
   g_reason[k] = why;
  }

void Invalidate(SSetup &s, const string why)
  {
   Reason(s.dir, StringFormat("Setup #%I64u INVALIDATED: %s", s.id, why));
   SetState(s, ST_SETUP_INVALIDATED, why);
  }

bool IsLevelUsed(const double lvl, const int dir)
  {
   double tol = MathMax(g_tickSize, U(1));
   for(int i = 0; i < ArraySize(g_usedLevels); i++)
      if(g_usedDirs[i] == dir && MathAbs(g_usedLevels[i] - lvl) <= tol)
         return true;
   return false;
  }

void MarkLevelUsed(const double lvl, const int dir)
  {
   if(IsLevelUsed(lvl, dir))
      return;
   int k = ArraySize(g_usedLevels);
   ArrayResize(g_usedLevels, k + 1);
   ArrayResize(g_usedDirs, k + 1);
   g_usedLevels[k] = lvl;
   g_usedDirs[k] = dir;
  }

ulong NextSetupId()
  {
   g_setupCounter++;
   GlobalVariableSet(g_gvPrefix + "CNT", (double)g_setupCounter);
   return g_setupCounter;
  }

bool SetupIsIdle(const SSetup &s)
  {
   return (s.state == ST_WAITING_FOR_RANGE || s.state == ST_RANGE_IDENTIFIED ||
           s.state == ST_WAITING_FOR_LIQUIDITY_SWEEP || s.state == ST_SETUP_COMPLETED ||
           s.state == ST_SETUP_INVALIDATED);
  }

// setup has an order or a position attached
bool SetupHasTrade(const SSetup &s)
  {
   return (s.state == ST_TRADE_OPEN || (s.state == ST_WAITING_FOR_ENTRY && s.orderTicket > 0));
  }

void OnNewRange()
  {
   ArrayResize(g_usedLevels, 0);
   ArrayResize(g_usedDirs, 0);
   for(int d = 0; d < 2; d++)
     {
      int dir = (d == 0 ? 1 : -1);
      if(g_setup[d].state == ST_TRADE_OPEN)
         continue; // never touch live trades
      bool advanced = (g_setup[d].state == ST_WAITING_FOR_MSS || g_setup[d].state == ST_MSS_CONFIRMED ||
                       g_setup[d].state == ST_WAITING_FOR_ENTRY);
      if(advanced && InpCarryActiveSetup)
        {
         Log(LOG_BASIC, StringFormat("%s setup #%I64u carried into new range (InpCarryActiveSetup)", DirStr(dir), g_setup[d].id));
         continue;
        }
      if(g_setup[d].state == ST_WAITING_FOR_ENTRY && g_setup[d].orderTicket > 0)
        {
         if(!DeletePendingOrder(g_setup[d].orderTicket, "new CRT range"))
            continue; // keep tracking if deletion failed
        }
      if(!SetupIsIdle(g_setup[d]))
         Reason(dir, StringFormat("Setup #%I64u reset: new reference range", g_setup[d].id));
      ResetSetup(g_setup[d], dir, ST_WAITING_FOR_RANGE);
      if(g_range.valid)
        {
         SetState(g_setup[d], ST_RANGE_IDENTIFIED);
         SetState(g_setup[d], ST_WAITING_FOR_LIQUIDITY_SWEEP);
        }
     }
  }

//+------------------------------------------------------------------+
//| CANDIDATE LEVELS FOR SWEEP                                       |
//+------------------------------------------------------------------+
int CollectLevels(const int dir, double &lv[], int &src[], datetime &tm[])
  {
   ArrayResize(lv, 0);
   ArrayResize(src, 0);
   ArrayResize(tm, 0);
   if(InpSweepSource != SWEEP_LIQ_ONLY && g_range.valid)
     {
      ArrayResize(lv, 1);
      ArrayResize(src, 1);
      ArrayResize(tm, 1);
      lv[0]  = (dir > 0 ? g_range.low : g_range.high);
      src[0] = LIQ_CRT;
      tm[0]  = g_range.refStart;
     }
   if(InpSweepSource != SWEEP_CRT_ONLY)
     {
      for(int i = 0; i < ArraySize(g_liq); i++)
        {
         if(g_liq[i].side != -dir)
            continue; // BUY sweeps sell-side liquidity (lows), SELL sweeps buy-side (highs)
         int k = ArraySize(lv);
         ArrayResize(lv, k + 1);
         ArrayResize(src, k + 1);
         ArrayResize(tm, k + 1);
         lv[k]  = g_liq[i].price;
         src[k] = g_liq[i].src;
         tm[k]  = g_liq[i].time;
        }
     }
   return ArraySize(lv);
  }

//+------------------------------------------------------------------+
//| M5 : RECLAIM CONFIRMED                                           |
//+------------------------------------------------------------------+
void ConfirmReclaim(SSetup &s, const datetime m5BarTime)
  {
   s.reclaimTime = m5BarTime;
   SetState(s, ST_RECLAIM_CONFIRMED);
   //--- locate the exact M1 bar of the sweep extreme
   MqlRates m1[];
   datetime from = s.sweepTime;
   datetime to   = (datetime)(m5BarTime + PeriodSeconds(PERIOD_M5) - 1);
   int c = CopyRates(_Symbol, PERIOD_M1, from, to, m1);
   if(c > 0)
     {
      double ext = (s.dir > 0 ? DBL_MAX : -DBL_MAX);
      datetime et = 0;
      for(int i = 0; i < c; i++)
        {
         if(s.dir > 0 && m1[i].low < ext)  { ext = m1[i].low;  et = m1[i].time; }
         if(s.dir < 0 && m1[i].high > ext) { ext = m1[i].high; et = m1[i].time; }
        }
      if(et > 0)
        {
         s.extreme = ext;
         s.extremeTimeM1 = et;
        }
     }
   if(s.extremeTimeM1 == 0)
      s.extremeTimeM1 = s.sweepTime;
   Log(LOG_BASIC, StringFormat("%s #%I64u RECLAIM CONFIRMED  level=%s (%s)  extreme=%s @ %s  -> waiting for M1 MSS",
                               DirStr(s.dir), s.id, P(s.level), LiqSrcStr(s.levelSrc), P(s.extreme),
                               TimeToString(s.extremeTimeM1, TIME_DATE | TIME_MINUTES)));
   SetState(s, ST_WAITING_FOR_MSS);
   DrawSetupSweep(s);
  }

//+------------------------------------------------------------------+
//| M5 : TURTLE SOUP SWEEP DETECTION                                 |
//+------------------------------------------------------------------+
void DetectSweep(SSetup &s, const MqlRates &r[], const double atr5)
  {
   if(!g_range.valid)
      return;
   if((s.dir > 0 && !InpAllowBuy) || (s.dir < 0 && !InpAllowSell))
      return;
   if(r[1].time < g_range.periodStart)
      return; // sweep must happen inside the active reference period

   double lv[];
   int src[];
   datetime tm[];
   int n = CollectLevels(s.dir, lv, src, tm);
   if(n == 0)
      return;

   double breach = MathMax(U(InpSweepMinBreach), atr5 * InpSweepMinBreachATR);
   double maxDepth = (InpSweepMaxDepthATR > 0 && atr5 > 0 ? atr5 * InpSweepMaxDepthATR : 0);
   int best = -1;

   for(int i = 0; i < n; i++)
     {
      double L = lv[i];
      if(tm[i] >= r[1].time)
         continue; // level must exist before the sweep candle
      if(IsLevelUsed(L, s.dir))
         continue;
      if(s.dir > 0)
        {
         if(r[1].low > L - breach)
            continue;                 // no breach
         if(r[2].close < L || r[2].low <= L - breach)
            continue;                 // not a fresh sweep (price was already below)
         if(InpCRTRequireBias && L > g_range.mid)
            continue;                 // BUY only from discount
         if(maxDepth > 0 && (L - r[1].low) > maxDepth)
           {
            MarkLevelUsed(L, s.dir);
            Reason(s.dir, StringFormat("Sweep of %s rejected: depth %.1f > max (breakout, not a sweep)", P(L), (L - r[1].low) / g_unit));
            continue;
           }
         if(best < 0 || L < lv[best])
            best = i;                 // deepest liquidity taken
        }
      else
        {
         if(r[1].high < L + breach)
            continue;
         if(r[2].close > L || r[2].high >= L + breach)
            continue;
         if(InpCRTRequireBias && L < g_range.mid)
            continue;                 // SELL only from premium
         if(maxDepth > 0 && (r[1].high - L) > maxDepth)
           {
            MarkLevelUsed(L, s.dir);
            Reason(s.dir, StringFormat("Sweep of %s rejected: depth %.1f > max (breakout, not a sweep)", P(L), (r[1].high - L) / g_unit));
            continue;
           }
         if(best < 0 || L > lv[best])
            best = i;
        }
     }
   if(best < 0)
      return;

   //--- new setup
   ResetSetup(s, s.dir, ST_WAITING_FOR_LIQUIDITY_SWEEP);
   s.id        = NextSetupId();
   s.level     = lv[best];
   s.levelSrc  = src[best];
   s.extreme   = (s.dir > 0 ? r[1].low : r[1].high);
   s.sweepTime = r[1].time;
   s.expiry    = (datetime)(r[1].time + PeriodSeconds(PERIOD_M5) + InpSetupExpiryMin * 60);
   MarkLevelUsed(s.level, s.dir);
   SetState(s, ST_SWEEP_DETECTED);
   Log(LOG_BASIC, StringFormat("%s #%I64u LIQUIDITY SWEEP  level=%s (%s)  extreme=%s  M5 bar %s  CRT[%s - %s]",
                               DirStr(s.dir), s.id, P(s.level), LiqSrcStr(s.levelSrc), P(s.extreme),
                               TimeToString(r[1].time, TIME_DATE | TIME_MINUTES), P(g_range.low), P(g_range.high)));
   DrawSetupSweep(s);

   //--- same-candle reclaim (classic Turtle Soup) ?
   double rng = r[1].high - r[1].low;
   double wick = (s.dir > 0 ? MathMin(r[1].open, r[1].close) - r[1].low : r[1].high - MathMax(r[1].open, r[1].close));
   bool closedBack = (s.dir > 0 ? r[1].close >= s.level + U(InpReclaimMinClose) : r[1].close <= s.level - U(InpReclaimMinClose));
   if(closedBack)
     {
      if(InpMinRejectWick > 0 && rng > 0 && wick / rng < InpMinRejectWick)
        {
         Invalidate(s, StringFormat("weak rejection wick %.2f < %.2f", wick / rng, InpMinRejectWick));
         return;
        }
      ConfirmReclaim(s, r[1].time);
      return;
     }
   //--- closed beyond the level: check for genuine breakout
   double beyond = (s.dir > 0 ? s.level - r[1].close : r[1].close - s.level);
   if(beyond > 0)
     {
      s.beyondCount = 1;
      if(atr5 > 0 && InpBreakoutCloseATR > 0 && beyond > atr5 * InpBreakoutCloseATR)
        {
         Invalidate(s, StringFormat("genuine breakout: M5 closed %.1f units beyond level", beyond / g_unit));
         return;
        }
      if(InpBreakoutBars > 0 && s.beyondCount >= InpBreakoutBars)
        {
         Invalidate(s, "genuine breakout: consecutive closes beyond level");
         return;
        }
     }
   SetState(s, ST_WAITING_FOR_RECLAIM);
  }

//+------------------------------------------------------------------+
//| M5 : WAITING FOR RECLAIM                                         |
//+------------------------------------------------------------------+
void CheckReclaim(SSetup &s, const MqlRates &r[], const double atr5)
  {
   if(r[1].time <= s.sweepTime)
      return;
   s.reclaimWait++;
   if(s.dir > 0)
      s.extreme = MathMin(s.extreme, r[1].low);
   else
      s.extreme = MathMax(s.extreme, r[1].high);

   double depth = (s.dir > 0 ? s.level - s.extreme : s.extreme - s.level);
   if(InpSweepMaxDepthATR > 0 && atr5 > 0 && depth > atr5 * InpSweepMaxDepthATR)
     {
      Invalidate(s, "sweep extended too far beyond level (breakout)");
      return;
     }
   bool closedBack = (s.dir > 0 ? r[1].close >= s.level + U(InpReclaimMinClose) : r[1].close <= s.level - U(InpReclaimMinClose));
   if(closedBack)
     {
      ConfirmReclaim(s, r[1].time);
      return;
     }
   double beyond = (s.dir > 0 ? s.level - r[1].close : r[1].close - s.level);
   if(beyond > 0)
     {
      s.beyondCount++;
      if(atr5 > 0 && InpBreakoutCloseATR > 0 && beyond > atr5 * InpBreakoutCloseATR)
        {
         Invalidate(s, StringFormat("genuine breakout: M5 closed %.1f units beyond level", beyond / g_unit));
         return;
        }
      if(InpBreakoutBars > 0 && s.beyondCount >= InpBreakoutBars)
        {
         Invalidate(s, StringFormat("genuine breakout: %d consecutive M5 closes beyond level", s.beyondCount));
         return;
        }
     }
   else
      s.beyondCount = 0;
   if(s.reclaimWait >= InpReclaimMaxBars)
      Invalidate(s, StringFormat("no reclaim within %d M5 bars", InpReclaimMaxBars));
  }

//+------------------------------------------------------------------+
//| M5 PROCESSING (per new M5 bar)                                   |
//+------------------------------------------------------------------+
void ProcessM5()
  {
   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(_Symbol, PERIOD_M5, 0, 5, r) < 5)
      return;
   double atr5 = GetATR(g_hATR_M5);

   for(int d = 0; d < 2; d++)
     {
      int dir = (d == 0 ? 1 : -1);
      switch(g_setup[d].state)
        {
         case ST_WAITING_FOR_RANGE:
            if(g_range.valid)
              {
               SetState(g_setup[d], ST_RANGE_IDENTIFIED);
               SetState(g_setup[d], ST_WAITING_FOR_LIQUIDITY_SWEEP);
               DetectSweep(g_setup[d], r, atr5);
              }
            break;
         case ST_RANGE_IDENTIFIED:
         case ST_WAITING_FOR_LIQUIDITY_SWEEP:
         case ST_SETUP_COMPLETED:
         case ST_SETUP_INVALIDATED:
            if(g_range.valid)
              {
               if(g_setup[d].state != ST_WAITING_FOR_LIQUIDITY_SWEEP)
                  SetState(g_setup[d], ST_WAITING_FOR_LIQUIDITY_SWEEP);
               DetectSweep(g_setup[d], r, atr5);
              }
            break;
         case ST_WAITING_FOR_RECLAIM:
            CheckReclaim(g_setup[d], r, atr5);
            break;
         case ST_WAITING_FOR_MSS:
         case ST_WAITING_FOR_ENTRY:
           {
            // reclaim lost: M5 closes back beyond the swept level
            bool lost = (dir > 0 ? r[1].close < g_setup[d].level : r[1].close > g_setup[d].level);
            if(lost && g_setup[d].level > 0 && r[1].time > g_setup[d].reclaimTime)
              {
               if(g_setup[d].orderTicket > 0)
                 {
                  if(DeletePendingOrder(g_setup[d].orderTicket, "reclaim lost"))
                     Invalidate(g_setup[d], "reclaim lost (M5 closed back beyond level), pending cancelled");
                 }
               else
                  Invalidate(g_setup[d], "reclaim lost (M5 closed back beyond level)");
              }
           }
         break;
         default:
            break;
        }
     }
  }

//+------------------------------------------------------------------+
//| M1 : STRUCTURE HELPERS (series arrays, index 1 = last closed)    |
//+------------------------------------------------------------------+
bool IsSwingHigh(const MqlRates &r[], const int n, const int i, const int depth)
  {
   if(i - depth < 1 || i + depth >= n)
      return false;
   for(int k = 1; k <= depth; k++)
      if(!(r[i].high > r[i - k].high && r[i].high >= r[i + k].high))
         return false;
   return true;
  }

bool IsSwingLow(const MqlRates &r[], const int n, const int i, const int depth)
  {
   if(i - depth < 1 || i + depth >= n)
      return false;
   for(int k = 1; k <= depth; k++)
      if(!(r[i].low < r[i - k].low && r[i].low <= r[i + k].low))
         return false;
   return true;
  }

int FindBarByTime(const MqlRates &r[], const int n, const datetime t)
  {
   for(int i = 0; i < n; i++)
     {
      if(r[i].time == t)
         return i;
      if(r[i].time < t)
         return i; // first bar older than t (gap tolerant)
     }
   return -1;
  }

bool IsDisplacementCandle(const MqlRates &b, const int dir, const double atr1)
  {
   double body = MathAbs(b.close - b.open);
   double rng  = b.high - b.low;
   if(rng <= 0)
      return false;
   if(dir > 0 && b.close <= b.open)
      return false;
   if(dir < 0 && b.close >= b.open)
      return false;
   if(InpDispMinBody > 0 && body < U(InpDispMinBody))
      return false;
   if(InpDispATRMult > 0 && atr1 > 0 && body < atr1 * InpDispATRMult)
      return false;
   if(InpDispBodyRatio > 0 && body / rng < InpDispBodyRatio)
      return false;
   return true;
  }

//+------------------------------------------------------------------+
//| M1 : MARKET STRUCTURE SHIFT                                      |
//+------------------------------------------------------------------+
bool FindMSS(SSetup &s, const MqlRates &r[], const int n, const int ei, const double atr1)
  {
   int depth = MathMax(1, InpMSSSwingDepth);
   int swingIdx = -1;
   bool beforeMode = (InpMSSSwingMode == MSS_SWING_BEFORE_SWEEP && s.tradesTaken == 0);

   if(beforeMode)
     {
      //--- last swing formed BEFORE the sweep extreme, not broken between swing and extreme
      int maxI = MathMin(n - depth - 1, ei + InpMSSLookbackBars);
      for(int i = ei + 1; i <= maxI; i++)
        {
         bool sw = (s.dir > 0 ? IsSwingHigh(r, n, i, depth) : IsSwingLow(r, n, i, depth));
         if(!sw)
            continue;
         double lvl = (s.dir > 0 ? r[i].high : r[i].low);
         bool brokenBefore = false;
         for(int j = i - 1; j > ei; j--)
            if((s.dir > 0 && r[j].close > lvl) || (s.dir < 0 && r[j].close < lvl))
              { brokenBefore = true; break; }
         if(brokenBefore)
            continue;
         swingIdx = i;
         break;
        }
     }
   else
     {
      //--- most recent confirmed unbroken swing (formed after the last trade if re-entering)
      for(int i = depth + 1; i < n - depth; i++)
        {
         if(s.tradesTaken > 0 && r[i].time <= s.lastTradeTime)
            break;
         if(i > ei + InpMSSLookbackBars)
            break;
         bool sw = (s.dir > 0 ? IsSwingHigh(r, n, i, depth) : IsSwingLow(r, n, i, depth));
         if(!sw)
            continue;
         double lvl = (s.dir > 0 ? r[i].high : r[i].low);
         bool broken = false;
         for(int j = i - 1; j >= 2; j--)
            if((s.dir > 0 && r[j].close > lvl) || (s.dir < 0 && r[j].close < lvl))
              { broken = true; break; }
         if(broken)
            continue;
         swingIdx = i;
         break;
        }
     }

   if(swingIdx < 0)
     {
      Reason(s.dir, StringFormat("#%I64u waiting for MSS: no valid M1 swing yet", s.id));
      return false;
     }

   double lvl = (s.dir > 0 ? r[swingIdx].high : r[swingIdx].low);
   double minBreak = U(InpMSSMinBreak);
   //--- first close beyond the swing level after the extreme (oldest -> newest)
   int startJ = (beforeMode ? ei - 1 : swingIdx - 1);
   int mssIdx = -1;
   for(int j = startJ; j >= 1; j--)
     {
      if(r[j].time <= s.extremeTimeM1)
         continue;
      if((s.dir > 0 && r[j].close > lvl + minBreak) || (s.dir < 0 && r[j].close < lvl - minBreak))
        { mssIdx = j; break; }
     }
   s.mssLevel = lvl;
   s.mssSwingTime = r[swingIdx].time;
   if(mssIdx < 0)
     {
      Reason(s.dir, StringFormat("#%I64u waiting for MSS: close beyond %s", s.id, P(lvl)));
      return false;
     }
   s.mssTime = r[mssIdx].time;

   //--- leg extreme (for discount entries)
   double legX = (s.dir > 0 ? -DBL_MAX : DBL_MAX);
   for(int j = ei; j >= 1; j--)
      legX = (s.dir > 0 ? MathMax(legX, r[j].high) : MathMin(legX, r[j].low));
   s.legExtreme = legX;

   //--- displacement within the leg, up to (and including) the MSS candle
   s.displacement = false;
   int lastK = MathMin(ei - 1, mssIdx + MathMax(1, InpDispLookback) - 1);
   for(int k = mssIdx; k <= lastK; k++)
     {
      if(k < 1)
         continue;
      if(IsDisplacementCandle(r[k], s.dir, atr1))
        {
         s.displacement = true;
         s.dispTime = r[k].time;
         break;
        }
     }
   return true;
  }

//+------------------------------------------------------------------+
//| M1 : FVG + ORDER BLOCK EVALUATION                                |
//+------------------------------------------------------------------+
void EvaluateZones(SSetup &s, const MqlRates &r[], const int n, const int ei, const double atr1)
  {
   //--------------------------------------------------------- FVG
   s.fvgStatus = ZONE_NONE;
   if(InpUseFVG)
     {
      double minSize = MathMax(U(InpFVGMinSize), atr1 * InpFVGMinSizeATR);
      for(int i = 1; i + 2 <= ei && i + 2 < n; i++)
        {
         double top, bot;
         if(s.dir > 0)
           {
            if(!(r[i + 2].high < r[i].low))
               continue;
            bot = r[i + 2].high;
            top = r[i].low;
           }
         else
           {
            if(!(r[i + 2].low > r[i].high))
               continue;
            top = r[i + 2].low;
            bot = r[i].high;
           }
         if(top - bot < minSize)
            continue;
         //--- mitigation after formation (bars newer than candle 3)
         int status = ZONE_UNTOUCHED;
         for(int j = i - 1; j >= 1; j--)
           {
            if(s.dir > 0)
              {
               if(r[j].low <= bot) { status = ZONE_FILLED; break; }
               if(r[j].low < top)  status = ZONE_PARTIAL;
              }
            else
              {
               if(r[j].high >= top) { status = ZONE_FILLED; break; }
               if(r[j].high > bot)  status = ZONE_PARTIAL;
              }
           }
         if(status == ZONE_FILLED)
            continue;            // invalidated -> look for an older one
         if(status == ZONE_PARTIAL && !InpFVGAllowPartial)
            continue;
         s.fvgStatus = status;
         s.fvgTop = top;
         s.fvgBottom = bot;
         s.fvgTime = r[i + 2].time;
         break;                  // freshest valid FVG
        }
     }

   //--------------------------------------------------------- ORDER BLOCK
   s.obStatus = ZONE_NONE;
   s.obRetested = false;
   if(InpUseOB)
     {
      datetime baseT = (s.displacement ? s.dispTime : s.mssTime);
      int base = FindBarByTime(r, n, baseT);
      if(base >= 1)
        {
         int obIdx = -1;
         int maxK = MathMin(n - 1, MathMin(ei + 2, base + InpOBMaxSearchBars));
         for(int k = base + 1; k <= maxK; k++)
           {
            bool opposite = (s.dir > 0 ? r[k].close < r[k].open : r[k].close > r[k].open);
            if(opposite) { obIdx = k; break; }
           }
         if(obIdx > 0)
           {
            double top, bot;
            if(InpOBZone == OB_ZONE_BODY)
              {
               top = MathMax(r[obIdx].open, r[obIdx].close);
               bot = MathMin(r[obIdx].open, r[obIdx].close);
              }
            else
              {
               top = r[obIdx].high;
               bot = r[obIdx].low;
              }
            // structural association: OB must sit between sweep extreme and MSS level
            bool assoc = (s.dir > 0 ? (top < s.mssLevel && bot >= s.extreme - g_tickSize)
                                    : (bot > s.mssLevel && top <= s.extreme + g_tickSize));
            if(assoc && top > bot)
              {
               int status = ZONE_UNTOUCHED;
               bool retest = false;
               for(int j = base - 1; j >= 1; j--)
                 {
                  if(s.dir > 0)
                    {
                     if(r[j].close < bot) { status = ZONE_FILLED; break; }
                     if(r[j].low <= top)
                       {
                        status = ZONE_PARTIAL;
                        if(r[j].close > top) retest = true;
                       }
                    }
                  else
                    {
                     if(r[j].close > top) { status = ZONE_FILLED; break; }
                     if(r[j].high >= bot)
                       {
                        status = ZONE_PARTIAL;
                        if(r[j].close < bot) retest = true;
                       }
                    }
                 }
               if(status != ZONE_FILLED)
                 {
                  s.obStatus = status;
                  s.obTop = top;
                  s.obBottom = bot;
                  s.obTime = r[obIdx].time;
                  s.obRetested = retest;
                 }
               else
                  s.obStatus = ZONE_FILLED;
              }
           }
        }
     }
  }

bool FVGValid(const SSetup &s) { return (s.fvgStatus == ZONE_UNTOUCHED || (s.fvgStatus == ZONE_PARTIAL && InpFVGAllowPartial)); }
bool OBValid(const SSetup &s)  { return (s.obStatus == ZONE_UNTOUCHED || s.obStatus == ZONE_PARTIAL); }

int ComputeScore(const SSetup &s)
  {
   int sc = 0;
   if(g_range.valid || s.rangeId != 0)       sc += 1; // CRT range
   if(s.sweepTime > 0)                       sc += 2; // liquidity sweep
   if(s.reclaimTime > 0)                     sc += 2; // M5 reclaim
   if(s.mssTime > 0)                         sc += 2; // M1 MSS
   if(s.displacement)                        sc += 1; // displacement
   if(FVGValid(s))                           sc += 1; // FVG
   if(OBValid(s))                            sc += 1; // order block
   if(InEnabledSession())                    sc += 1; // session
   return sc;
  }

//+------------------------------------------------------------------+
//| POSITION / ORDER QUERIES                                         |
//+------------------------------------------------------------------+
bool IsOurPosition()
  {
   return (PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic);
  }

bool IsOurOrder()
  {
   return (OrderGetString(ORDER_SYMBOL) == _Symbol && OrderGetInteger(ORDER_MAGIC) == InpMagic);
  }

bool IsPendingType(const ENUM_ORDER_TYPE t)
  {
   return (t == ORDER_TYPE_BUY_LIMIT || t == ORDER_TYPE_SELL_LIMIT || t == ORDER_TYPE_BUY_STOP ||
           t == ORDER_TYPE_SELL_STOP || t == ORDER_TYPE_BUY_STOP_LIMIT || t == ORDER_TYPE_SELL_STOP_LIMIT);
  }

int CountOurPositions()
  {
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(IsOurPosition()) c++;
     }
   return c;
  }

int CountOurPendings()
  {
   int c = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(IsOurOrder() && IsPendingType((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE))) c++;
     }
   return c;
  }

// returns position ticket (selected) for a position identifier, 0 if none
ulong FindPositionById(const ulong posId)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!IsOurPosition()) continue;
      if((ulong)PositionGetInteger(POSITION_IDENTIFIER) == posId)
         return t;
     }
   return 0;
  }

bool PendingExists(const ulong ticket)
  {
   if(ticket == 0) return false;
   return OrderSelect(ticket);
  }

bool CommentInUse(const string cmt)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(IsOurPosition() && PositionGetString(POSITION_COMMENT) == cmt) return true;
     }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(IsOurOrder() && OrderGetString(ORDER_COMMENT) == cmt) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| TRADE EXECUTION HELPERS                                          |
//+------------------------------------------------------------------+
bool RetcodeOK(const uint rc)
  {
   return (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
  }

ENUM_ORDER_TYPE_FILLING PreferredFilling()
  {
   long fm = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((fm & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   if((fm & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
  }

double StopsLevelPrice()
  {
   long sl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   return (double)sl * g_point;
  }

double FreezeLevelPrice()
  {
   long fl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   return (double)fl * g_point;
  }

int VolumeDigits(const double step)
  {
   int d = 0;
   double s = step;
   while(d < 8 && MathAbs(s - MathRound(s)) > 1e-9)
     {
      s *= 10.0;
      d++;
     }
   return d;
  }

double NormVolumeDown(const double vol)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double mx   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;
   double v = MathFloor(vol / step + 1e-9) * step;
   if(mx > 0 && v > mx) v = MathFloor(mx / step + 1e-9) * step;
   return NormalizeDouble(v, VolumeDigits(step));
  }

// money lost per 1.0 lot if price moves from entry to sl (positive number)
double LossPerLot(const int dir, const double entry, const double sl)
  {
   double profit = 0.0;
   ENUM_ORDER_TYPE t = (dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   if(OrderCalcProfit(t, _Symbol, 1.0, entry, sl, profit) && profit < 0)
      return -profit;
   // fallback: tick value based
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tv <= 0) tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tv <= 0 || g_tickSize <= 0) return 0.0;
   return MathAbs(entry - sl) / g_tickSize * tv;
  }

double CalcLots(const int dir, const double entry, const double sl, string &why)
  {
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double base = (InpRiskBase == RISK_BASE_EQUITY ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE));
   double lpl  = LossPerLot(dir, entry, sl);
   if(lpl <= 0)
     {
      why = "cannot compute loss per lot (tick value unavailable)";
      return 0;
     }
   double lots;
   if(InpLotMode == LOT_FIXED)
      lots = InpFixedLot;
   else
     {
      double riskMoney = base * InpRiskPercent / 100.0;
      lots = riskMoney / lpl;
     }
   double nl = NormVolumeDown(lots);
   if(nl < vmin)
     {
      if(InpLotMode == LOT_FIXED || InpAllowMinLotOverRisk)
         nl = vmin;
      else
        {
         why = StringFormat("risk lot %.4f below broker minimum %.2f (SL too wide for risk)", lots, vmin);
         return 0;
        }
     }
   //--- hard cap of real risk
   double realRiskPct = (base > 0 ? nl * lpl / base * 100.0 : 100.0);
   if(InpMaxRiskPctHard > 0 && realRiskPct > InpMaxRiskPctHard + 1e-6)
     {
      why = StringFormat("real risk %.2f%% exceeds hard cap %.2f%%", realRiskPct, InpMaxRiskPctHard);
      return 0;
     }
   //--- volume limit
   double vlim = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_LIMIT);
   if(vlim > 0)
     {
      double cur = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(t == 0) continue;
         if(PositionGetString(POSITION_SYMBOL) == _Symbol) cur += PositionGetDouble(POSITION_VOLUME);
        }
      if(cur + nl > vlim)
        {
         why = "symbol volume limit reached";
         return 0;
        }
     }
   //--- margin check (reduce if needed)
   ENUM_ORDER_TYPE ot = (dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
   double freeM = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double step  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0) step = vmin;
   double margin = 0;
   int guard = 0;
   while(nl >= vmin && OrderCalcMargin(ot, _Symbol, nl, entry, margin) && margin > freeM * 0.95 && guard < 10000)
     {
      nl = NormVolumeDown(nl - step);
      guard++;
     }
   if(nl < vmin)
     {
      why = "insufficient free margin";
      return 0;
     }
   return nl;
  }

double RRValue()
  {
   switch(InpRRPreset)
     {
      case RR_1_1:   return 1.0;
      case RR_1_1_5: return 1.5;
      case RR_1_2:   return 2.0;
      case RR_1_3:   return 3.0;
      default:       return MathMax(0.1, InpCustomRR);
     }
  }

//+------------------------------------------------------------------+
//| TRADING GATE (soft filters - retried while confirmation is alive)|
//+------------------------------------------------------------------+
bool CheckTradingAllowed(const int dir, string &why)
  {
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)) { why = "terminal Algo Trading disabled"; return false; }
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))           { why = "EA not allowed to trade (properties)"; return false; }
   long tm = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);
   if(tm == SYMBOL_TRADE_MODE_DISABLED || tm == SYMBOL_TRADE_MODE_CLOSEONLY) { why = "symbol trading disabled / close-only"; return false; }
   if(tm == SYMBOL_TRADE_MODE_LONGONLY && dir < 0)  { why = "symbol long-only"; return false; }
   if(tm == SYMBOL_TRADE_MODE_SHORTONLY && dir > 0) { why = "symbol short-only"; return false; }
   if(g_stats.halted)                               { why = "trading halted: " + g_stats.haltReason; return false; }
   double sp = SpreadUnits();
   if(InpMaxSpread > 0 && sp > InpMaxSpread)         { why = StringFormat("spread %.1f > max %.1f", sp, InpMaxSpread); return false; }
   if(InpMinATRM5 > 0)
     {
      double a5 = GetATR(g_hATR_M5);
      if(a5 > 0 && a5 < U(InpMinATRM5))             { why = "low liquidity (M5 ATR below minimum)"; return false; }
     }
   if(InpUseSessionFilter && !InEnabledSession())    { why = "outside enabled sessions (" + CurrentSessionName() + ")"; return false; }
   string w = "";
   if(InNoTradePeriod(w))                            { why = w; return false; }
   if(InNewsBlackout(w))                             { why = w; return false; }
   int open = CountOurPositions() + CountOurPendings();
   if(open >= InpMaxOpenPositions)                   { why = StringFormat("max open positions/pendings (%d)", InpMaxOpenPositions); return false; }
   if(InpMaxTradesPerDay > 0 && g_stats.tradesToday + CountOurPendings() >= InpMaxTradesPerDay)
     { why = StringFormat("max trades per day (%d)", InpMaxTradesPerDay); return false; }
   if(!g_hedging && PositionSelect(_Symbol))         { why = "netting account: a position already exists on symbol"; return false; }
   return true;
  }

//+------------------------------------------------------------------+
//| TRADE PLAN (entry / SL / TP / lots)                              |
//+------------------------------------------------------------------+
bool FindLiquidityTarget(const int dir, const double entry, const double minDist, double &target)
  {
   double best = 0;
   bool found = false;
   // CRT opposite boundary is also a liquidity pool
   double cands[];
   int n = 0;
   ArrayResize(cands, ArraySize(g_liq) + 1);
   if(g_range.valid)
      cands[n++] = (dir > 0 ? g_range.high : g_range.low);
   for(int i = 0; i < ArraySize(g_liq); i++)
      if(g_liq[i].side == dir)
         cands[n++] = g_liq[i].price;
   for(int i = 0; i < n; i++)
     {
      double d = (cands[i] - entry) * dir;
      if(d < minDist)
         continue;
      if(!found || d < (best - entry) * dir)
        {
         best = cands[i];
         found = true;
        }
     }
   if(found)
      target = best;
   return found;
  }

bool BuildPlan(const SSetup &s, const double entry, double &sl, double &tp, double &lots, string &why)
  {
   int dir = s.dir;
   double atr5 = GetATR(g_hATR_M5);
   double buffer = U(InpSLBuffer) + atr5 * InpSLBufferATR;
   sl = (dir > 0 ? s.extreme - buffer : s.extreme + buffer);
   sl = NormSL(sl, dir);
   double risk = (entry - sl) * dir;
   if(risk <= 0)
     {
      why = "entry is beyond the sweep extreme (invalid SL side)";
      return false;
     }
   double minSL = MathMax(U(InpMinSL), StopsLevelPrice() + g_point);
   if(risk < minSL)
     {
      sl = NormSL(entry - dir * minSL, dir);
      risk = (entry - sl) * dir;
     }
   if(InpMaxSL > 0 && risk > U(InpMaxSL) + g_point * 0.5)
     {
      why = StringFormat("SL distance %.1f > max %.1f units", risk / g_unit, InpMaxSL);
      return false;
     }

   double rr = RRValue();
   switch(InpTPMode)
     {
      case TP_CRT_OPPOSITE:
         tp = (dir > 0 ? g_range.high : g_range.low);
         if((tp - entry) * dir < risk * InpMinRR)
           {
            why = StringFormat("CRT target RR %.2f < min %.2f", (tp - entry) * dir / risk, InpMinRR);
            return false;
           }
         break;
      case TP_LIQUIDITY:
        {
         double t;
         if(FindLiquidityTarget(dir, entry, risk * InpMinRR, t))
            tp = t;
         else
           {
            tp = entry + dir * risk * rr;
            Log(LOG_DETAILED, "No liquidity target beyond min RR - fallback to RR target");
           }
        }
      break;
      case TP_MULTI:
         tp = entry + dir * risk * MathMax(InpTP3_R, 0.1);
         break;
      default:
         tp = entry + dir * risk * rr;
         break;
     }
   tp = NormPrice(tp);
   double minStop = StopsLevelPrice();
   if((tp - entry) * dir < minStop + g_point)
     {
      why = "TP inside broker stops level";
      return false;
     }
   lots = CalcLots(dir, entry, sl, why);
   if(lots <= 0)
      return false;
   return true;
  }

//+------------------------------------------------------------------+
//| ORDER PLACEMENT                                                  |
//+------------------------------------------------------------------+
bool SendOrder(const int dir, const bool market, const double price, const double sl, const double tp,
               const double lots, const datetime exp, const string cmt)
  {
   ENUM_ORDER_TYPE_FILLING fills[3];
   fills[0] = PreferredFilling();
   fills[1] = (fills[0] == ORDER_FILLING_RETURN ? ORDER_FILLING_IOC : ORDER_FILLING_RETURN);
   fills[2] = (fills[0] == ORDER_FILLING_FOK ? ORDER_FILLING_IOC : ORDER_FILLING_FOK);
   long em = SymbolInfoInteger(_Symbol, SYMBOL_EXPIRATION_MODE);
   bool specified = ((em & SYMBOL_EXPIRATION_SPECIFIED) == SYMBOL_EXPIRATION_SPECIFIED);

   for(int a = 0; a < 3; a++)
     {
      g_trade.SetTypeFilling(fills[a]);
      bool ok;
      if(market)
        {
         double px = (dir > 0 ? Ask() : Bid());
         ok = (dir > 0 ? g_trade.Buy(lots, _Symbol, px, sl, tp, cmt) : g_trade.Sell(lots, _Symbol, px, sl, tp, cmt));
        }
      else
        {
         ENUM_ORDER_TYPE_TIME tt = (specified ? ORDER_TIME_SPECIFIED : ORDER_TIME_GTC);
         datetime e = (specified ? exp : 0);
         ok = (dir > 0 ? g_trade.BuyLimit(lots, price, _Symbol, sl, tp, tt, e, cmt)
                       : g_trade.SellLimit(lots, price, _Symbol, sl, tp, tt, e, cmt));
        }
      uint rc = g_trade.ResultRetcode();
      if(ok && RetcodeOK(rc))
         return true;
      Log(LOG_BASIC, StringFormat("Order send failed: retcode %u (%s), filling %s",
                                  rc, g_trade.ResultRetcodeDescription(), EnumToString(fills[a])));
      if(rc != TRADE_RETCODE_INVALID_FILL)
         return false;
     }
   return false;
  }

bool HardRetcode(const uint rc)
  {
   return (rc == TRADE_RETCODE_INVALID_STOPS || rc == TRADE_RETCODE_INVALID_VOLUME ||
           rc == TRADE_RETCODE_NO_MONEY || rc == TRADE_RETCODE_INVALID_PRICE ||
           rc == TRADE_RETCODE_TRADE_DISABLED || rc == TRADE_RETCODE_LIMIT_ORDERS ||
           rc == TRADE_RETCODE_LIMIT_VOLUME || rc == TRADE_RETCODE_INVALID_EXPIRATION);
  }

// execute (or simulate in signal mode) the entry for a confirmed setup
void ExecuteEntry(SSetup &s, const bool market, const double limitPrice, const string modeTxt)
  {
   int dir = s.dir;
   double entry = (market ? (dir > 0 ? Ask() : Bid()) : NormPrice(limitPrice));
   double sl, tp, lots;
   string why = "";
   if(!BuildPlan(s, entry, sl, tp, lots, why))
     {
      Invalidate(s, "plan rejected: " + why);
      return;
     }
   double risk = (entry - sl) * dir;
   double rr = (tp - entry) * dir / risk;
   Log(LOG_BASIC, StringFormat("%s #%I64u ENTRY DECISION [%s] score=%d/11  entry=%s SL=%s TP=%s  risk=%.1f units  RR=%.2f  lots=%.2f",
                               DirStr(dir), s.id, modeTxt, s.score, P(entry), P(sl), P(tp), risk / g_unit, rr, lots));
   s.plannedEntry = entry;
   s.plannedSL = sl;
   s.plannedTP = tp;
   DrawSetupPlan(s, entry, sl, tp);

   //--- signal-only mode
   if(InpDiagnosticMode || !g_autoTrading)
     {
      Reason(dir, StringFormat("SIGNAL #%I64u %s %s @ %s (auto-trading %s) - not executed", s.id, DirStr(dir), modeTxt, P(entry),
                               (InpDiagnosticMode ? "DIAGNOSTIC" : "OFF")));
      s.tradesTaken++;
      SetState(s, ST_SETUP_COMPLETED, "signal only");
      return;
     }

   //--- duplicate guards
   datetime bar = iTime(_Symbol, PERIOD_M1, 0);
   if(g_lastOrderBar == bar)
     {
      Reason(dir, "duplicate guard: an order was already sent on this M1 bar");
      return;
     }
   string cmt = StringFormat("%s %s %I64u", InpOrderComment, (dir > 0 ? "B" : "S"), s.id);
   if(StringLen(cmt) > 31)
      cmt = StringSubstr(cmt, StringLen(cmt) - 31);
   if(CommentInUse(cmt))
     {
      Reason(dir, "duplicate guard: order for this setup already exists");
      SetState(s, ST_SETUP_COMPLETED);
      return;
     }

   datetime exp = (datetime)(TimeCurrent() + MathMax(2, InpPendingExpiryMin) * 60);
   if(!SendOrder(dir, market, entry, sl, tp, lots, exp, cmt))
     {
      uint rc = g_trade.ResultRetcode();
      if(HardRetcode(rc))
         Invalidate(s, StringFormat("execution rejected by server: %u %s", rc, g_trade.ResultRetcodeDescription()));
      else
         Reason(dir, StringFormat("execution failed (%u %s) - will retry next M1 bar", rc, g_trade.ResultRetcodeDescription()));
      return;
     }

   ulong ticket = g_trade.ResultOrder();
   g_lastOrderBar = bar;
   g_statsDirty = true;
   s.orderTicket = ticket;
   s.tradesTaken++;
   s.lastTradeTime = TimeCurrent();
   //--- persist management data keyed by order ticket (= position identifier)
   GVSet(ticket, "SL0", sl);
   GVSet(ticket, "EXT", s.extreme);
   GVSet(ticket, "LVL", s.level);
   GVSet(ticket, "SID", (double)s.id);
   GVSet(ticket, "DIR", (double)dir);
   if(market)
     {
      double fillVol = g_trade.ResultVolume();
      GVSet(ticket, "VOL0", (fillVol > 0 ? fillVol : lots));
      s.positionId = ticket;
      SetState(s, ST_TRADE_OPEN);
      Log(LOG_BASIC, StringFormat("%s #%I64u MARKET ORDER FILLED ticket=%I64u price=%s lots=%.2f retcode=%u",
                                  DirStr(dir), s.id, ticket, P(g_trade.ResultPrice()), lots, g_trade.ResultRetcode()));
      Reason(dir, StringFormat("TRADE OPEN #%I64u", s.id));
     }
   else
     {
      GVSet(ticket, "VOL0", lots);
      GVSet(ticket, "PEXP", (double)exp);
      s.pendingExpiry = exp;
      SetState(s, ST_WAITING_FOR_ENTRY, "pending placed");
      Log(LOG_BASIC, StringFormat("%s #%I64u LIMIT ORDER PLACED ticket=%I64u price=%s lots=%.2f expires %s retcode=%u",
                                  DirStr(dir), s.id, ticket, P(entry), lots, TimeToString(exp, TIME_DATE | TIME_MINUTES), g_trade.ResultRetcode()));
      Reason(dir, StringFormat("PENDING #%I64u @ %s", s.id, P(entry)));
     }
  }

//+------------------------------------------------------------------+
//| ENTRY MODEL                                                      |
//+------------------------------------------------------------------+
double ZoneLevel(const int dir, const double top, const double bot, const double lvl)
  {
   // lvl 0 = proximal edge, 1 = distal edge
   double l = MathMax(0.0, MathMin(1.0, lvl));
   return (dir > 0 ? top - (top - bot) * l : bot + (top - bot) * l);
  }

void TryEntry(SSetup &s, const int barsSinceMSS)
  {
   bool timeout = (barsSinceMSS > InpConfirmWaitBars);
   bool fvgOK = FVGValid(s);
   bool obOK  = OBValid(s);
   string missing = "";
   if(InpRequireDisplacement && !s.displacement) missing += "displacement ";
   if(InpRequireFVG && !fvgOK)                  missing += "FVG ";
   if(InpRequireOB && !obOK)                    missing += "OB ";
   if(InpEntryMode == ENTRY_LIMIT_FVG && !fvgOK && !InpFallbackToMarket) missing += "FVG(limit) ";
   if(InpEntryMode == ENTRY_LIMIT_OB && !obOK && !InpFallbackToMarket)   missing += "OB(limit) ";
   if(InpEntryMode == ENTRY_MARKET && InpOBRetestRequired && !(obOK && s.obRetested)) missing += "OB-retest ";
   s.score = ComputeScore(s);
   if(missing == "" && s.score < InpMinScore)
      missing = StringFormat("score %d<%d ", s.score, InpMinScore);
   if(missing != "")
     {
      if(timeout || (InpRequireDisplacement && !s.displacement))
         Invalidate(s, "confirmation failed, missing: " + missing);
      else
         Reason(s.dir, StringFormat("#%I64u waiting for confirmation: %s(bar %d/%d)", s.id, missing, barsSinceMSS, InpConfirmWaitBars));
      return;
     }

   string why = "";
   if(!CheckTradingAllowed(s.dir, why) && !InpDiagnosticMode && g_autoTrading)
     {
      if(timeout)
         Invalidate(s, "entry window closed while blocked: " + why);
      else
         Reason(s.dir, StringFormat("#%I64u entry blocked: %s", s.id, why));
      return;
     }

   //--- choose entry
   int dir = s.dir;
   bool market = true;
   double price = 0;
   string modeTxt = "MARKET";
   if(InpEntryMode == ENTRY_LIMIT_FVG && fvgOK)
     {
      market = false;
      price = ZoneLevel(dir, s.fvgTop, s.fvgBottom, InpFVGEntryLevel);
      modeTxt = "LIMIT@FVG";
     }
   else
      if(InpEntryMode == ENTRY_LIMIT_OB && obOK)
        {
         market = false;
         price = ZoneLevel(dir, s.obTop, s.obBottom, InpOBEntryLevel);
         modeTxt = "LIMIT@OB";
        }
      else
         if(InpEntryMode == ENTRY_LIMIT_DISCOUNT)
           {
            market = false;
            double lvl = MathMax(0.0, MathMin(1.0, InpDiscountLevel));
            price = (dir > 0 ? s.legExtreme - (s.legExtreme - s.extreme) * lvl
                             : s.legExtreme + (s.extreme - s.legExtreme) * lvl);
            modeTxt = "LIMIT@DISCOUNT";
           }
         else
            if(InpEntryMode != ENTRY_MARKET)
               modeTxt = "MARKET(fallback)";

   if(!market)
     {
      price = NormPrice(price);
      double cur = (dir > 0 ? Ask() : Bid());
      double gap = (cur - price) * dir;   // > 0: limit is on the correct side
      if(gap <= StopsLevelPrice() + g_point)
        {
         if(InpFallbackToMarket)
           {
            market = true;
            modeTxt = modeTxt + "->MARKET(traded through)";
           }
         else
           {
            if(timeout) Invalidate(s, "limit level already traded through");
            else Reason(dir, "limit level too close / traded through, waiting");
            return;
           }
        }
     }
   if(market && !InpOBRetestRequired && barsSinceMSS > InpMSSMaxAgeMarket)
     {
      Invalidate(s, StringFormat("MSS too old for market entry (%d bars > %d)", barsSinceMSS, InpMSSMaxAgeMarket));
      return;
     }
   ExecuteEntry(s, market, price, modeTxt);
  }

//+------------------------------------------------------------------+
//| M1 PROCESSING (per new M1 bar)                                   |
//+------------------------------------------------------------------+
void ProcessSetupM1(SSetup &s)
  {
   if(s.state != ST_WAITING_FOR_MSS && !(s.state == ST_WAITING_FOR_ENTRY && s.orderTicket == 0))
      return;

   //--- expiry (only before an order exists)
   if(TimeCurrent() > s.expiry)
     {
      Invalidate(s, StringFormat("setup expired (%d min)", InpSetupExpiryMin));
      return;
     }

   int barsSinceSweep = (int)((TimeCurrent() - s.sweepTime) / 60);
   int need = MathMin(3000, barsSinceSweep + InpMSSLookbackBars + InpMSSSwingDepth * 2 + 20);
   MqlRates r[];
   ArraySetAsSeries(r, true);
   int n = CopyRates(_Symbol, PERIOD_M1, 0, need, r);
   if(n < 10)
      return;
   int ei = FindBarByTime(r, n, s.extremeTimeM1);
   if(ei < 1)
      return;
   double atr1 = GetATR(g_hATR_M1);

   //--- sweep extreme broken -> setup invalid
   for(int j = ei - 1; j >= 1; j--)
     {
      if((s.dir > 0 && r[j].low < s.extreme) || (s.dir < 0 && r[j].high > s.extreme))
        {
         Invalidate(s, "sweep extreme broken on M1 (" + P(s.extreme) + ")");
         return;
        }
     }

   if(s.state == ST_WAITING_FOR_MSS)
     {
      if(!FindMSS(s, r, n, ei, atr1))
         return;
      SetState(s, ST_MSS_CONFIRMED);
      Log(LOG_BASIC, StringFormat("%s #%I64u MSS CONFIRMED  swing=%s (%s)  break bar %s  displacement=%s",
                                  DirStr(s.dir), s.id, P(s.mssLevel), TimeToString(s.mssSwingTime, TIME_MINUTES),
                                  TimeToString(s.mssTime, TIME_DATE | TIME_MINUTES), (s.displacement ? "YES" : "NO")));
      DrawSetupMSS(s);
      SetState(s, ST_WAITING_FOR_ENTRY);
     }

   int mi = FindBarByTime(r, n, s.mssTime);
   int barsSinceMSS = (mi < 1 ? 0 : mi - 1);
   s.confirmWait = barsSinceMSS;
   EvaluateZones(s, r, n, ei, atr1);
   Log(LOG_DETAILED, StringFormat("%s #%I64u zones: FVG=%s [%s-%s]  OB=%s [%s-%s] retest=%s",
                                  DirStr(s.dir), s.id,
                                  (s.fvgStatus == ZONE_UNTOUCHED ? "FRESH" : (s.fvgStatus == ZONE_PARTIAL ? "PARTIAL" : "NONE")),
                                  P(s.fvgBottom), P(s.fvgTop),
                                  (s.obStatus == ZONE_UNTOUCHED ? "FRESH" : (s.obStatus == ZONE_PARTIAL ? "MITIGATED" : (s.obStatus == ZONE_FILLED ? "INVALID" : "NONE"))),
                                  P(s.obBottom), P(s.obTop), (s.obRetested ? "YES" : "NO")));
   DrawSetupZones(s);
   TryEntry(s, barsSinceMSS);
  }

void ProcessM1()
  {
   for(int d = 0; d < 2; d++)
      ProcessSetupM1(g_setup[d]);
  }

//+------------------------------------------------------------------+
//| PENDING ORDER MANAGEMENT                                         |
//+------------------------------------------------------------------+
bool DeletePendingOrder(const ulong ticket, const string why)
  {
   if(!PendingExists(ticket))
      return true;
   if(g_trade.OrderDelete(ticket) && RetcodeOK(g_trade.ResultRetcode()))
     {
      Log(LOG_BASIC, StringFormat("Pending %I64u cancelled: %s", ticket, why));
      GVDelAll(ticket);
      return true;
     }
   Log(LOG_BASIC, StringFormat("Pending %I64u cancel FAILED (%u %s)", ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()));
   return false;
  }

void OnTradeCompleted(SSetup &s)
  {
   g_statsDirty = true;
   Log(LOG_BASIC, StringFormat("%s #%I64u trade completed (position %I64u closed)", DirStr(s.dir), s.id, s.positionId));
   bool rangeOK = (s.rangeId == g_range.id || InpCarryActiveSetup);
   if(s.tradesTaken < InpMaxTradesPerSetup && TimeCurrent() < s.expiry && rangeOK)
     {
      // allow another entry from the same sweep, but only after a NEW structure shift
      s.orderTicket = 0;
      s.positionId = 0;
      s.mssLevel = 0;
      s.mssTime = 0;
      s.mssSwingTime = 0;
      s.displacement = false;
      s.dispTime = 0;
      s.fvgStatus = ZONE_NONE;
      s.obStatus = ZONE_NONE;
      s.lastTradeTime = TimeCurrent();
      SetState(s, ST_WAITING_FOR_MSS, "re-arm (trades per setup)");
     }
   else
      SetState(s, ST_SETUP_COMPLETED);
  }

void SyncSetups()
  {
   for(int d = 0; d < 2; d++)
     {
      if(g_setup[d].state == ST_WAITING_FOR_ENTRY && g_setup[d].orderTicket > 0)
        {
         ulong tk = g_setup[d].orderTicket;
         if(PendingExists(tk))
            continue;
         if(FindPositionById(tk) > 0)
           {
            g_setup[d].positionId = tk;
            SetState(g_setup[d], ST_TRADE_OPEN, "pending filled");
            Log(LOG_BASIC, StringFormat("%s #%I64u LIMIT FILLED -> position %I64u", DirStr(g_setup[d].dir), g_setup[d].id, tk));
            g_statsDirty = true;
            continue;
           }
         // no pending, no position: filled & already closed, or expired/cancelled
         bool hadDeals = (HistorySelectByPosition((long)tk) && HistoryDealsTotal() > 0);
         if(hadDeals)
           {
            g_setup[d].positionId = tk;
            OnTradeCompleted(g_setup[d]);
           }
         else
           {
            GVDelAll(tk);
            Invalidate(g_setup[d], "pending order expired / removed");
           }
        }
      else
         if(g_setup[d].state == ST_TRADE_OPEN)
           {
            if(FindPositionById(g_setup[d].positionId) == 0)
               OnTradeCompleted(g_setup[d]);
           }
     }
  }

void ManagePendings()
  {
   string news = "";
   bool inNews = InNewsBlackout(news);
   for(int d = 0; d < 2; d++)
     {
      if(!(g_setup[d].state == ST_WAITING_FOR_ENTRY && g_setup[d].orderTicket > 0))
         continue;
      ulong tk = g_setup[d].orderTicket;
      if(!PendingExists(tk))
         continue;
      int dir = g_setup[d].dir;
      string why = "";
      double px = (dir > 0 ? Bid() : Ask());
      if(g_setup[d].pendingExpiry > 0 && TimeCurrent() >= g_setup[d].pendingExpiry)
         why = "expired";
      else
         if((dir > 0 && px <= g_setup[d].extreme) || (dir < 0 && px >= g_setup[d].extreme))
            why = "price traded beyond sweep extreme before fill";
         else
            if(InpCancelPendingAtR > 0 && g_setup[d].plannedSL > 0)
              {
               double risk = MathAbs(g_setup[d].plannedEntry - g_setup[d].plannedSL);
               if(risk > 0 && (px - g_setup[d].plannedEntry) * dir >= risk * InpCancelPendingAtR)
                  why = StringFormat("price ran %.1fR away before fill", InpCancelPendingAtR);
              }
      if(why == "" && inNews && InpNewsCancelPending)
         why = news;
      if(why == "" && g_stats.halted)
         why = "trading halted: " + g_stats.haltReason;
      if(why != "")
        {
         if(DeletePendingOrder(tk, why))
            Invalidate(g_setup[d], "pending cancelled: " + why);
        }
     }
  }

void DeleteAllPendingsEA(const string why)
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(!IsOurOrder()) continue;
      if(!IsPendingType((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE))) continue;
      DeletePendingOrder(t, why);
     }
  }

void CloseAllEA(const string why)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!IsOurPosition()) continue;
      if(g_trade.PositionClose(t, (ulong)InpSlippagePts) && RetcodeOK(g_trade.ResultRetcode()))
         Log(LOG_BASIC, StringFormat("Position %I64u closed: %s", t, why));
      else
         Log(LOG_BASIC, StringFormat("Position %I64u close FAILED (%u %s)", t, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()));
     }
   g_statsDirty = true;
  }

//+------------------------------------------------------------------+
//| POSITION MANAGEMENT (BE / partials / trailing / time / invalid)  |
//+------------------------------------------------------------------+
bool ModifySL(const ulong ticket, const int dir, const double newSL, const double curSL, const double tp)
  {
   double px = (dir > 0 ? Bid() : Ask());
   double stops = StopsLevelPrice();
   double freeze = FreezeLevelPrice();
   double sl = NormSL(newSL, dir);
   if(curSL > 0 && MathAbs(sl - curSL) < g_tickSize * 0.5)
      return false;
   if((px - sl) * dir <= stops)
      return false;                        // too close to price
   if(freeze > 0)
     {
      if(curSL > 0 && MathAbs(px - curSL) <= freeze) return false;
      if(tp > 0 && MathAbs(tp - px) <= freeze)       return false;
     }
   if(g_trade.PositionModify(ticket, sl, tp) && RetcodeOK(g_trade.ResultRetcode()))
      return true;
   Log(LOG_DETAILED, StringFormat("SL modify failed %I64u: %u %s", ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription()));
   return false;
  }

void ManagePositions()
  {
   double atr5 = 0;
   bool atrLoaded = false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!IsOurPosition()) continue;
      ulong id    = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      int dir     = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl   = PositionGetDouble(POSITION_SL);
      double tp   = PositionGetDouble(POSITION_TP);
      double vol  = PositionGetDouble(POSITION_VOLUME);
      datetime ot = (datetime)PositionGetInteger(POSITION_TIME);

      if(!GVHas(id, "SL0"))
        {
         if(sl <= 0) continue;            // unmanaged position without SL
         GVSet(id, "SL0", sl);
        }
      if(!GVHas(id, "VOL0"))
         GVSet(id, "VOL0", vol);
      double sl0  = GVGet(id, "SL0", sl);
      double vol0 = GVGet(id, "VOL0", vol);
      double R    = (open - sl0) * dir;
      if(R <= 0) continue;
      double px   = (dir > 0 ? Bid() : Ask());
      double pr   = (px - open) * dir / R;   // profit in R

      //--- max holding time
      if(InpMaxHoldMinutes > 0 && TimeCurrent() - ot >= InpMaxHoldMinutes * 60)
        {
         if(g_trade.PositionClose(ticket, (ulong)InpSlippagePts))
            Log(LOG_BASIC, StringFormat("Position %I64u closed: max holding time %d min", ticket, InpMaxHoldMinutes));
         continue;
        }

      //--- partial take profits
      if(InpTPMode == TP_MULTI && InpUsePartials)
        {
         double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         if(!GVHas(id, "TP1") && pr >= InpTP1_R && InpTP1_Pct > 0)
           {
            double cv = NormVolumeDown(vol0 * InpTP1_Pct / 100.0);
            if(cv >= vmin && vol - cv >= vmin - 1e-9)
              {
               if(g_trade.PositionClosePartial(ticket, cv, (ulong)InpSlippagePts) && RetcodeOK(g_trade.ResultRetcode()))
                 {
                  Log(LOG_BASIC, StringFormat("TP1 %.1fR: closed %.2f lots of %I64u", InpTP1_R, cv, ticket));
                  GVSet(id, "TP1", 1);
                  if(InpUseBreakEven && !GVHas(id, "BE"))
                    {
                     if(PositionSelectByTicket(ticket))
                       {
                        double nsl = open + dir * U(InpBEOffset);
                        if((nsl - PositionGetDouble(POSITION_SL)) * dir > 0 &&
                           ModifySL(ticket, dir, nsl, PositionGetDouble(POSITION_SL), PositionGetDouble(POSITION_TP)))
                          {
                           GVSet(id, "BE", 1);
                           Log(LOG_BASIC, StringFormat("Break-even set on %I64u after TP1", ticket));
                          }
                       }
                    }
                 }
              }
            else
               GVSet(id, "TP1", 1); // volume too small to split - skip partial
            continue; // re-read the position next tick
           }
         if(GVHas(id, "TP1") && !GVHas(id, "TP2") && pr >= InpTP2_R && InpTP2_Pct > 0)
           {
            double cv = NormVolumeDown(vol0 * InpTP2_Pct / 100.0);
            if(cv > vol) cv = NormVolumeDown(vol);
            if(cv >= vmin && vol - cv >= vmin - 1e-9)
              {
               if(g_trade.PositionClosePartial(ticket, cv, (ulong)InpSlippagePts) && RetcodeOK(g_trade.ResultRetcode()))
                 {
                  Log(LOG_BASIC, StringFormat("TP2 %.1fR: closed %.2f lots of %I64u", InpTP2_R, cv, ticket));
                  GVSet(id, "TP2", 1);
                 }
              }
            else
               GVSet(id, "TP2", 1);
            continue;
           }
        }

      //--- break-even
      if(InpUseBreakEven && !GVHas(id, "BE") && pr >= InpBETriggerR)
        {
         double nsl = open + dir * U(InpBEOffset);
         if(sl <= 0 || (nsl - sl) * dir > 0)
           {
            if(ModifySL(ticket, dir, nsl, sl, tp))
              {
               GVSet(id, "BE", 1);
               Log(LOG_BASIC, StringFormat("Break-even set on %I64u at %s (%.2fR)", ticket, P(nsl), pr));
               continue;
              }
           }
         else
            GVSet(id, "BE", 1); // SL already beyond BE
        }

      //--- trailing stop
      if(InpTrailMode != TRAIL_NONE && pr >= InpTrailStartR)
        {
         double dist;
         if(InpTrailMode == TRAIL_ATR)
           {
            if(!atrLoaded) { atr5 = GetATR(g_hATR_M5); atrLoaded = true; }
            dist = atr5 * InpTrailATRMult;
           }
         else
            dist = U(InpTrailDistance);
         if(dist > 0)
           {
            double nsl = px - dir * dist;
            if(sl <= 0 || (nsl - sl) * dir >= MathMax(U(InpTrailStep), g_tickSize))
              {
               if(ModifySL(ticket, dir, nsl, sl, tp))
                  Log(LOG_DETAILED, StringFormat("Trailing SL %I64u -> %s", ticket, P(nsl)));
              }
           }
        }
     }
  }

// called on each new M5 bar
void CheckPositionInvalidation()
  {
   if(!InpCloseOnInvalidation)
      return;
   double c1 = iClose(_Symbol, PERIOD_M5, 1);
   if(c1 <= 0)
      return;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!IsOurPosition()) continue;
      ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      double ext = GVGet(id, "EXT", 0);
      if(ext <= 0) continue;
      int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
      if((dir > 0 && c1 < ext) || (dir < 0 && c1 > ext))
        {
         if(g_trade.PositionClose(ticket, (ulong)InpSlippagePts))
            Log(LOG_BASIC, StringFormat("Position %I64u closed: setup invalidated (M5 close %s beyond sweep extreme %s)", ticket, P(c1), P(ext)));
        }
     }
  }

//+------------------------------------------------------------------+
//| DAILY STATISTICS + RISK HALTS                                    |
//+------------------------------------------------------------------+
void RefreshDailyStats()
  {
   g_statsDirty = false;
   datetime now = TimeCurrent();
   datetime ds = DayStart(now);
   datetime resetT = (datetime)(long)GlobalVariableGet(g_gvPrefix + "RESET");
   datetime from = (resetT > ds ? resetT : ds);
   g_stats.dayStart = ds;

   double accPL = 0, eaPL = 0;
   int trades = 0;
   ulong  pid[];
   double ppl[];
   datetime ptm[];
   if(HistorySelect(from, now + 86400))
     {
      int n = HistoryDealsTotal();
      for(int i = 0; i < n; i++)
        {
         ulong dt = HistoryDealGetTicket(i);
         if(dt == 0) continue;
         long type = HistoryDealGetInteger(dt, DEAL_TYPE);
         if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue;
         double pl = HistoryDealGetDouble(dt, DEAL_PROFIT) + HistoryDealGetDouble(dt, DEAL_SWAP) +
                     HistoryDealGetDouble(dt, DEAL_COMMISSION) + HistoryDealGetDouble(dt, DEAL_FEE);
         accPL += pl;
         if(HistoryDealGetInteger(dt, DEAL_MAGIC) != InpMagic || HistoryDealGetString(dt, DEAL_SYMBOL) != _Symbol)
            continue;
         eaPL += pl;
         long entry = HistoryDealGetInteger(dt, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_IN)
           {
            trades++;
            continue;
           }
         ulong p = (ulong)HistoryDealGetInteger(dt, DEAL_POSITION_ID);
         datetime t = (datetime)HistoryDealGetInteger(dt, DEAL_TIME);
         int k = -1;
         for(int j = 0; j < ArraySize(pid); j++)
            if(pid[j] == p) { k = j; break; }
         if(k < 0)
           {
            k = ArraySize(pid);
            ArrayResize(pid, k + 1);
            ArrayResize(ppl, k + 1);
            ArrayResize(ptm, k + 1);
            pid[k] = p;
            ppl[k] = 0;
            ptm[k] = 0;
           }
         ppl[k] += pl;
         if(t > ptm[k]) ptm[k] = t;
        }
     }
   //--- consecutive losses among fully closed positions (newest first)
   int consec = 0;
   bool used[];
   ArrayResize(used, ArraySize(pid));
   ArrayInitialize(used, false);
   for(int step = 0; step < ArraySize(pid); step++)
     {
      int best = -1;
      for(int j = 0; j < ArraySize(pid); j++)
         if(!used[j] && (best < 0 || ptm[j] > ptm[best])) best = j;
      if(best < 0) break;
      used[best] = true;
      if(FindPositionById(pid[best]) > 0) continue; // still open (partial)
      if(ppl[best] < 0) consec++;
      else break;
     }
   g_stats.closedPLAcc = accPL;
   g_stats.closedPL = (InpDailyScope == DAILY_SCOPE_ACCOUNT ? accPL : eaPL);
   g_stats.tradesToday = trades;
   g_stats.consecLosses = consec;
   g_stats.dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE) - accPL;
   if(g_stats.dayStartBalance <= 0)
      g_stats.dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
  }

double FloatingPL()
  {
   if(InpDailyScope == DAILY_SCOPE_ACCOUNT)
      return AccountInfoDouble(ACCOUNT_EQUITY) - AccountInfoDouble(ACCOUNT_BALANCE);
   double f = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!IsOurPosition()) continue;
      f += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
     }
   return f;
  }

double DailyPL() { return g_stats.closedPL + FloatingPL(); }

double DailyDDPct()
  {
   double b = g_stats.dayStartBalance;
   if(b <= 0) return 0;
   double dd = (b - AccountInfoDouble(ACCOUNT_EQUITY)) / b * 100.0;
   return MathMax(0.0, dd);
  }

void EvaluateHalts()
  {
   bool wasHalted = g_stats.halted;
   g_stats.halted = false;
   g_stats.haltReason = "";
   double b = g_stats.dayStartBalance;
   double pl = DailyPL();

   string eqName = g_gvPrefix + "EQHALT";
   if(GlobalVariableCheck(eqName) && (datetime)(long)GlobalVariableGet(eqName) == g_stats.dayStart)
     {
      g_stats.halted = true;
      g_stats.haltReason = "daily equity protection";
     }
   else
      if(InpEquityProtectPct > 0 && DailyDDPct() >= InpEquityProtectPct)
        {
         g_stats.halted = true;
         g_stats.haltReason = "daily equity protection";
         GlobalVariableSet(eqName, (double)g_stats.dayStart);
         Log(LOG_BASIC, StringFormat("EQUITY PROTECTION: daily DD %.2f%% >= %.2f%% - closing all EA positions", DailyDDPct(), InpEquityProtectPct));
         CloseAllEA("equity protection");
         DeleteAllPendingsEA("equity protection");
        }
   if(!g_stats.halted && b > 0)
     {
      if((InpMaxDailyLossPct > 0 && pl <= -b * InpMaxDailyLossPct / 100.0) ||
         (InpMaxDailyLossMoney > 0 && pl <= -InpMaxDailyLossMoney))
        {
         g_stats.halted = true;
         g_stats.haltReason = "max daily loss reached";
         if(InpCloseOnDailyLoss && !wasHalted)
           {
            CloseAllEA("daily loss limit");
            DeleteAllPendingsEA("daily loss limit");
           }
        }
      else
         if((InpMaxDailyProfitPct > 0 && pl >= b * InpMaxDailyProfitPct / 100.0) ||
            (InpMaxDailyProfitMoney > 0 && pl >= InpMaxDailyProfitMoney))
           {
            g_stats.halted = true;
            g_stats.haltReason = "daily profit target reached";
           }
         else
            if(InpMaxConsecLosses > 0 && g_stats.consecLosses >= InpMaxConsecLosses)
              {
               g_stats.halted = true;
               g_stats.haltReason = StringFormat("%d consecutive losses", g_stats.consecLosses);
              }
     }
   if(g_stats.halted && !wasHalted)
      Log(LOG_BASIC, "NEW TRADES HALTED until next trading day: " + g_stats.haltReason);
  }

double OpenRiskMoney()
  {
   double risk = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!IsOurPosition()) continue;
      int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double vol = PositionGetDouble(POSITION_VOLUME);
      if(sl <= 0 || (open - sl) * dir <= 0) continue;
      risk += LossPerLot(dir, open, sl) * vol;
     }
   return risk;
  }

//+------------------------------------------------------------------+
//| RESTART RECOVERY                                                 |
//+------------------------------------------------------------------+
void RecoverState()
  {
   g_setupCounter = (ulong)GlobalVariableGet(g_gvPrefix + "CNT");
   //--- pending orders
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(!IsOurOrder()) continue;
      ENUM_ORDER_TYPE ty = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
      if(!IsPendingType(ty)) continue;
      int dir = (ty == ORDER_TYPE_BUY_LIMIT || ty == ORDER_TYPE_BUY_STOP || ty == ORDER_TYPE_BUY_STOP_LIMIT ? 1 : -1);
      int d = SideIdx(dir);
      ResetSetup(g_setup[d], dir, ST_WAITING_FOR_ENTRY);
      g_setup[d].id = (ulong)GVGet(t, "SID", 0);
      g_setup[d].orderTicket = t;
      g_setup[d].plannedEntry = OrderGetDouble(ORDER_PRICE_OPEN);
      g_setup[d].plannedSL = OrderGetDouble(ORDER_SL);
      g_setup[d].plannedTP = OrderGetDouble(ORDER_TP);
      g_setup[d].extreme = GVGet(t, "EXT", g_setup[d].plannedSL);
      g_setup[d].level = GVGet(t, "LVL", 0);
      datetime exp = (datetime)(long)GVGet(t, "PEXP", 0);
      if(exp == 0) exp = (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION);
      if(exp == 0) exp = (datetime)(TimeCurrent() + InpPendingExpiryMin * 60);
      g_setup[d].pendingExpiry = exp;
      g_setup[d].expiry = exp;
      g_setup[d].tradesTaken = 1;
      g_setup[d].reclaimTime = TimeCurrent();
      Log(LOG_BASIC, StringFormat("RECOVERY: pending %I64u (%s) re-attached to setup #%I64u", t, DirStr(dir), g_setup[d].id));
     }
   //--- open positions
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!IsOurPosition()) continue;
      int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
      int d = SideIdx(dir);
      ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      ResetSetup(g_setup[d], dir, ST_TRADE_OPEN);
      g_setup[d].id = (ulong)GVGet(id, "SID", 0);
      g_setup[d].positionId = id;
      g_setup[d].orderTicket = id;
      g_setup[d].extreme = GVGet(id, "EXT", 0);
      g_setup[d].level = GVGet(id, "LVL", 0);
      g_setup[d].tradesTaken = MathMax(1, InpMaxTradesPerSetup);
      Log(LOG_BASIC, StringFormat("RECOVERY: position %I64u (%s) re-attached, management continues", id, DirStr(dir)));
     }
  }

void CleanupGVs()
  {
   int total = GlobalVariablesTotal();
   for(int i = total - 1; i >= 0; i--)
     {
      string name = GlobalVariableName(i);
      if(StringFind(name, g_gvPrefix) != 0) continue;
      string rest = StringSubstr(name, StringLen(g_gvPrefix));
      int us = StringFind(rest, "_");
      if(us <= 0) continue;
      ulong id = (ulong)StringToInteger(StringSubstr(rest, 0, us));
      if(id == 0) continue;
      if(FindPositionById(id) > 0 || PendingExists(id)) continue;
      GlobalVariableDel(name);
     }
  }

//+------------------------------------------------------------------+
//| CHART VISUALIZATION                                              |
//+------------------------------------------------------------------+
bool DrawingEnabled()
  {
   if(!InpDrawObjects) return false;
   if(g_isTester && !g_visual) return false;
   return true;
  }

void ObjTrend(const string name, const datetime t1, const double p1, const datetime t2, const double p2,
              const color clr, const ENUM_LINE_STYLE style, const int width, const string tip)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TREND, 0, t1, p1, t2, p2);
   else
     {
      ObjectMove(0, name, 0, t1, p1);
      ObjectMove(0, name, 1, t2, p2);
     }
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, name, OBJPROP_RAY_LEFT, false);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, tip);
  }

void ObjRect(const string name, const datetime t1, const double p1, const datetime t2, const double p2,
             const color clr, const string tip)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   else
     {
      ObjectMove(0, name, 0, t1, p1);
      ObjectMove(0, name, 1, t2, p2);
     }
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, tip);
  }

void ObjArrow(const string name, const datetime t, const double p, const int code, const color clr, const ENUM_ARROW_ANCHOR anchor, const string tip)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_ARROW, 0, t, p);
   else
      ObjectMove(0, name, 0, t, p);
   ObjectSetInteger(0, name, OBJPROP_ARROWCODE, code);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, anchor);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, tip);
  }

void ObjText(const string name, const datetime t, const double p, const string txt, const color clr)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_TEXT, 0, t, p);
   else
      ObjectMove(0, name, 0, t, p);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial");
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 7);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
  }

void DrawCRT()
  {
   if(!DrawingEnabled() || g_range.id == 0)
      return;
   datetime t1 = g_range.refStart;
   datetime t2 = (datetime)(g_range.periodStart + PeriodSeconds(InpCRTTimeframe));
   ENUM_LINE_STYLE st = (g_range.valid ? STYLE_SOLID : STYLE_DOT);
   ObjTrend(OBJ_PREFIX + "CRT_H", t1, g_range.high, t2, g_range.high, InpCRTColor, st, 2, "CRT High " + P(g_range.high));
   ObjTrend(OBJ_PREFIX + "CRT_L", t1, g_range.low,  t2, g_range.low,  InpCRTColor, st, 2, "CRT Low " + P(g_range.low));
   ObjTrend(OBJ_PREFIX + "CRT_M", t1, g_range.mid,  t2, g_range.mid,  InpCRTColor, STYLE_DASH, 1, "CRT 50% " + P(g_range.mid));
   ObjText(OBJ_PREFIX + "CRT_HT", t1, g_range.high, "CRT HIGH", InpCRTColor);
   ObjText(OBJ_PREFIX + "CRT_LT", t1, g_range.low,  "CRT LOW", InpCRTColor);
   ObjText(OBJ_PREFIX + "CRT_MT", t1, g_range.mid,  "CRT 50%", InpCRTColor);
  }

void DrawLiquidity()
  {
   if(!DrawingEnabled())
      return;
   ObjectsDeleteAll(0, OBJ_PREFIX + "LIQ_");
   datetime t2 = (datetime)(TimeCurrent() + 3600);
   for(int i = 0; i < ArraySize(g_liq); i++)
     {
      color c = (g_liq[i].side > 0 ? InpBearColor : InpBullColor);
      string nm = OBJ_PREFIX + "LIQ_" + IntegerToString(i);
      string lbl = (g_liq[i].side > 0 ? "BSL " : "SSL ") + LiqSrcStr(g_liq[i].src);
      ObjTrend(nm, g_liq[i].time, g_liq[i].price, t2, g_liq[i].price, c, STYLE_DOT, 1, lbl + " " + P(g_liq[i].price));
      ObjText(nm + "_T", g_liq[i].time, g_liq[i].price, lbl, c);
     }
  }

string SetupObjPrefix(const ulong id) { return OBJ_PREFIX + "S" + IntegerToString((long)id) + "_"; }

void RegisterSetupDrawing(const ulong id)
  {
   for(int i = 0; i < ArraySize(g_drawnSetups); i++)
      if(g_drawnSetups[i] == id) return;
   int n = ArraySize(g_drawnSetups);
   ArrayResize(g_drawnSetups, n + 1);
   g_drawnSetups[n] = id;
   while(ArraySize(g_drawnSetups) > MathMax(1, InpKeepSetupDrawings))
     {
      ObjectsDeleteAll(0, SetupObjPrefix(g_drawnSetups[0]));
      int m = ArraySize(g_drawnSetups);
      for(int k = 0; k < m - 1; k++)
         g_drawnSetups[k] = g_drawnSetups[k + 1];
      ArrayResize(g_drawnSetups, m - 1);
     }
  }

void DrawSetupSweep(const SSetup &s)
  {
   if(!DrawingEnabled() || s.id == 0) return;
   RegisterSetupDrawing(s.id);
   string pf = SetupObjPrefix(s.id);
   color c = (s.dir > 0 ? InpBullColor : InpBearColor);
   ObjArrow(pf + "SWEEP", s.sweepTime, s.extreme, (s.dir > 0 ? 233 : 234), c,
            (s.dir > 0 ? ANCHOR_TOP : ANCHOR_BOTTOM), "Liquidity sweep #" + IntegerToString((long)s.id));
   ObjTrend(pf + "LVL", (datetime)(s.sweepTime - 1800), s.level, (datetime)(s.sweepTime + 1800), s.level, c, STYLE_SOLID, 1,
            "Swept level " + LiqSrcStr(s.levelSrc) + " " + P(s.level));
   ObjText(pf + "SWT", s.sweepTime, (s.dir > 0 ? s.extreme : s.extreme), (s.dir > 0 ? "SWEEP SSL" : "SWEEP BSL"), c);
  }

void DrawSetupMSS(const SSetup &s)
  {
   if(!DrawingEnabled() || s.id == 0) return;
   string pf = SetupObjPrefix(s.id);
   color c = (s.dir > 0 ? InpBullColor : InpBearColor);
   ObjTrend(pf + "MSS", s.mssSwingTime, s.mssLevel, s.mssTime, s.mssLevel, c, STYLE_SOLID, 2, "MSS " + P(s.mssLevel));
   ObjText(pf + "MSST", s.mssSwingTime, s.mssLevel, (s.dir > 0 ? "MSS (bull)" : "MSS (bear)"), c);
  }

void DrawSetupZones(const SSetup &s)
  {
   if(!DrawingEnabled() || s.id == 0) return;
   string pf = SetupObjPrefix(s.id);
   datetime t2 = (datetime)(TimeCurrent() + 1800);
   if(FVGValid(s))
      ObjRect(pf + "FVG", s.fvgTime, s.fvgTop, t2, s.fvgBottom, (s.dir > 0 ? C'20,60,110' : C'110,40,20'),
              "FVG " + P(s.fvgBottom) + " - " + P(s.fvgTop));
   else
      ObjectDelete(0, pf + "FVG");
   if(OBValid(s))
      ObjRect(pf + "OB", s.obTime, s.obTop, t2, s.obBottom, (s.dir > 0 ? C'20,90,60' : C'100,20,60'),
              "Order Block " + P(s.obBottom) + " - " + P(s.obTop));
   else
      ObjectDelete(0, pf + "OB");
  }

void DrawSetupPlan(const SSetup &s, const double entry, const double sl, const double tp)
  {
   if(!DrawingEnabled() || s.id == 0) return;
   string pf = SetupObjPrefix(s.id);
   datetime t1 = TimeCurrent();
   datetime t2 = (datetime)(t1 + 3600);
   ObjTrend(pf + "ENTRY", t1, entry, t2, entry, clrWhite,   STYLE_SOLID, 1, "Entry " + P(entry));
   ObjTrend(pf + "SL",    t1, sl,    t2, sl,    clrRed,     STYLE_DASH,  1, "SL " + P(sl));
   ObjTrend(pf + "TP",    t1, tp,    t2, tp,    clrLime,    STYLE_DASH,  1, "TP " + P(tp));
   ObjText(pf + "ENTRYT", t2, entry, "ENTRY", clrWhite);
   ObjText(pf + "SLT",    t2, sl,    "SL", clrRed);
   ObjText(pf + "TPT",    t2, tp,    "TP", clrLime);
  }

//+------------------------------------------------------------------+
//| DASHBOARD                                                        |
//+------------------------------------------------------------------+
#define DASH_ROWS 36
const color DASH_BG     = C'12,12,14';
const color DASH_BORDER = C'212,175,55';
const color DASH_GOLD   = C'212,175,55';
const color DASH_TEXT   = C'215,215,215';
const color DASH_DIM    = C'130,130,130';
const color DASH_GREEN  = C'60,200,120';
const color DASH_RED    = C'230,80,70';

int DashRowH() { return InpDashFontSize * 2 + 3; }
int DashW()    { return 300; }

bool DashboardEnabled()
  {
   if(!InpShowDashboard) return false;
   if(g_isTester && !g_visual) return false;
   return true;
  }

void DashLabel(const string name, const int x, const int y, const string txt, const color clr, const bool bold = false)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_ZORDER, 10);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetString(0, name, OBJPROP_FONT, (bold ? "Arial Bold" : "Consolas"));
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpDashFontSize);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
  }

void DashButton(const string name, const int x, const int y, const int w, const int h, const string txt, const color bg)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_ZORDER, 20);
      ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, InpDashFontSize);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clrBlack);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bg);
   ObjectSetInteger(0, name, OBJPROP_BORDER_COLOR, DASH_GOLD);
   ObjectSetString(0, name, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, name, OBJPROP_STATE, false);
  }

void DashCreateBackground()
  {
   string bg = DASH_PREFIX + "BG";
   int h = DASH_ROWS * DashRowH() + 90;
   if(ObjectFind(0, bg) < 0)
     {
      ObjectCreate(0, bg, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, bg, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, bg, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, bg, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, bg, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, bg, OBJPROP_BACK, false);
      ObjectSetInteger(0, bg, OBJPROP_ZORDER, 0);
     }
   ObjectSetInteger(0, bg, OBJPROP_XDISTANCE, InpDashX);
   ObjectSetInteger(0, bg, OBJPROP_YDISTANCE, InpDashY);
   ObjectSetInteger(0, bg, OBJPROP_XSIZE, DashW());
   ObjectSetInteger(0, bg, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, bg, OBJPROP_BGCOLOR, DASH_BG);
   ObjectSetInteger(0, bg, OBJPROP_COLOR, DASH_BORDER);
   ObjectSetInteger(0, bg, OBJPROP_WIDTH, 1);
  }

int g_dashRow = 0;

void DashHeader(const string txt)
  {
   int y = InpDashY + 30 + g_dashRow * DashRowH();
   DashLabel(DASH_PREFIX + "R" + IntegerToString(g_dashRow) + "A", InpDashX + 10, y, txt, DASH_GOLD, true);
   DashLabel(DASH_PREFIX + "R" + IntegerToString(g_dashRow) + "B", InpDashX + 150, y, " ", DASH_GOLD);
   g_dashRow++;
  }

void DashLine(const string label, const string value, const color vc)
  {
   int y = InpDashY + 30 + g_dashRow * DashRowH();
   DashLabel(DASH_PREFIX + "R" + IntegerToString(g_dashRow) + "A", InpDashX + 14, y, label, DASH_DIM);
   DashLabel(DASH_PREFIX + "R" + IntegerToString(g_dashRow) + "B", InpDashX + 130, y, value, vc);
   g_dashRow++;
  }

string ZoneStr(const int st, const bool isOB)
  {
   if(st == ZONE_UNTOUCHED) return "FRESH";
   if(st == ZONE_PARTIAL)   return (isOB ? "MITIGATED" : "PARTIAL");
   if(st == ZONE_FILLED)    return (isOB ? "INVALID" : "FILLED");
   return "-";
  }

// the most advanced setup is shown as primary
int PrimarySetup()
  {
   int a = (int)g_setup[0].state, b = (int)g_setup[1].state;
   bool ia = (g_setup[0].state == ST_SETUP_COMPLETED || g_setup[0].state == ST_SETUP_INVALIDATED);
   bool ib = (g_setup[1].state == ST_SETUP_COMPLETED || g_setup[1].state == ST_SETUP_INVALIDATED);
   if(ia) a = 0;
   if(ib) b = 0;
   return (b > a ? 1 : 0);
  }

void UpdateDashboard()
  {
   if(!DashboardEnabled())
      return;
   DashCreateBackground();
   DashLabel(DASH_PREFIX + "TITLE", InpDashX + 10, InpDashY + 6, "CRT + TBS SMC SNIPER  PRO", DASH_GOLD, true);
   g_dashRow = 0;

   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   double dpl = DailyPL();
   string cur = AccountInfoString(ACCOUNT_CURRENCY);

   DashHeader("ACCOUNT");
   DashLine("Balance",       DoubleToString(bal, 2) + " " + cur, DASH_TEXT);
   DashLine("Equity",        DoubleToString(eq, 2) + " " + cur, DASH_TEXT);
   DashLine("Daily P/L",     DoubleToString(dpl, 2) + StringFormat(" (%.2f%%)", (g_stats.dayStartBalance > 0 ? dpl / g_stats.dayStartBalance * 100 : 0)),
            (dpl >= 0 ? DASH_GREEN : DASH_RED));
   DashLine("Daily DD",      StringFormat("%.2f%%", DailyDDPct()), (DailyDDPct() > 0 ? DASH_RED : DASH_TEXT));
   double orisk = OpenRiskMoney();
   DashLine("Open risk",     StringFormat("%.2f (%.2f%%)", orisk, (bal > 0 ? orisk / bal * 100 : 0)), DASH_TEXT);
   DashLine("Status",        (g_stats.halted ? "HALTED: " + g_stats.haltReason :
                              (InpDiagnosticMode ? "DIAGNOSTIC (signals only)" : (g_autoTrading ? "ACTIVE" : "AUTO OFF"))),
            (g_stats.halted ? DASH_RED : (g_autoTrading && !InpDiagnosticMode ? DASH_GREEN : DASH_GOLD)));

   DashHeader("MARKET");
   DashLine("Symbol",        _Symbol + "  " + EnumToString(InpCRTTimeframe) + " CRT", DASH_TEXT);
   double sp = SpreadUnits();
   DashLine("Spread",        StringFormat("%.1f units", sp), (InpMaxSpread > 0 && sp > InpMaxSpread ? DASH_RED : DASH_TEXT));
   DashLine("Session",       CurrentSessionName() + (InEnabledSession() ? "" : " (off)"), (InEnabledSession() ? DASH_GREEN : DASH_DIM));
   DashLine("CRT High",      (g_range.id > 0 ? P(g_range.high) : "-"), DASH_TEXT);
   DashLine("CRT Low",       (g_range.id > 0 ? P(g_range.low) : "-"), DASH_TEXT);
   DashLine("CRT 50%",       (g_range.id > 0 ? P(g_range.mid) + (g_range.valid ? "" : " (invalid)") : "-"), (g_range.valid ? DASH_TEXT : DASH_RED));

   int pi = PrimarySetup();
   DashHeader("STRATEGY");
   DashLine("BUY state",     StateStr(g_setup[0].state), (g_setup[0].state >= ST_SWEEP_DETECTED && g_setup[0].state <= ST_TRADE_OPEN ? DASH_GREEN : DASH_TEXT));
   DashLine("SELL state",    StateStr(g_setup[1].state), (g_setup[1].state >= ST_SWEEP_DETECTED && g_setup[1].state <= ST_TRADE_OPEN ? DASH_RED : DASH_TEXT));
   string bias = "NEUTRAL";
   if(g_range.valid)
     {
      double px = Bid();
      bias = (px < g_range.mid ? "BUY (discount)" : "SELL (premium)");
     }
   DashLine("Bias",          bias, DASH_GOLD);
   SSetup ps;
   ps = g_setup[pi];
   DashLine("Sweep",         (ps.sweepTime > 0 ? DirStr(ps.dir) + " " + LiqSrcStr(ps.levelSrc) + " " + P(ps.level) : "waiting"), DASH_TEXT);
   DashLine("MSS",           (ps.mssTime > 0 ? P(ps.mssLevel) + (ps.displacement ? " +DISP" : " no disp") : (ps.mssLevel > 0 ? "level " + P(ps.mssLevel) : "-")), DASH_TEXT);
   DashLine("FVG",           ZoneStr(ps.fvgStatus, false), (FVGValid(ps) ? DASH_GREEN : DASH_DIM));
   DashLine("Order Block",   ZoneStr(ps.obStatus, true) + (ps.obRetested ? " (retested)" : ""), (OBValid(ps) ? DASH_GREEN : DASH_DIM));
   DashLine("Score",         StringFormat("%d / 11  (min %d)", ComputeScore(ps), InpMinScore), (ComputeScore(ps) >= InpMinScore ? DASH_GREEN : DASH_TEXT));
   string rsn = g_reason[pi];
   if(StringLen(rsn) > 44) rsn = StringSubstr(rsn, 0, 44);
   DashLine("Last",          (rsn == "" ? "-" : rsn), DASH_DIM);

   DashHeader("TRADING");
   int np = CountOurPositions();
   int no = CountOurPendings();
   DashLine("Positions",     StringFormat("%d open / %d pending", np, no), DASH_TEXT);
   string slS = "-", tpS = "-", rrS = "-";
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!IsOurPosition()) continue;
      double o = PositionGetDouble(POSITION_PRICE_OPEN);
      double s = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      slS = P(s);
      tpS = P(tp);
      ulong id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      double s0 = GVGet(id, "SL0", s);
      if(MathAbs(o - s0) > 0 && tp > 0)
         rrS = StringFormat("1 : %.2f", MathAbs(tp - o) / MathAbs(o - s0));
      break;
     }
   DashLine("Current SL",    slS, DASH_RED);
   DashLine("Current TP",    tpS, DASH_GREEN);
   DashLine("Risk/Reward",   rrS, DASH_TEXT);
   DashLine("Trades today",  StringFormat("%d / %d", g_stats.tradesToday, InpMaxTradesPerDay), DASH_TEXT);
   DashLine("Consec. losses",StringFormat("%d / %d", g_stats.consecLosses, InpMaxConsecLosses), (g_stats.consecLosses > 0 ? DASH_RED : DASH_TEXT));
   DashLine("Lot mode",      (InpLotMode == LOT_FIXED ? StringFormat("Fixed %.2f", InpFixedLot) : StringFormat("Risk %.2f%%", InpRiskPercent)), DASH_TEXT);

   //--- buttons
   int by = InpDashY + 30 + g_dashRow * DashRowH() + 6;
   int bw = (DashW() - 30) / 2;
   string autoTxt = (g_autoTrading ? "AUTO TRADING: ON" : "AUTO TRADING: OFF");
   DashButton(DASH_PREFIX + "BTN_AUTO", InpDashX + 10, by, bw, 22, autoTxt, (g_autoTrading ? DASH_GREEN : DASH_RED));
   DashButton(DASH_PREFIX + "BTN_CLOSE", InpDashX + 20 + bw, by, bw, 22,
              (g_confirmBtn == DASH_PREFIX + "BTN_CLOSE" ? "CONFIRM CLOSE ?" : "CLOSE ALL"), DASH_GOLD);
   DashButton(DASH_PREFIX + "BTN_CANCEL", InpDashX + 10, by + 28, bw, 22,
              (g_confirmBtn == DASH_PREFIX + "BTN_CANCEL" ? "CONFIRM CANCEL ?" : "CANCEL PENDING"), DASH_GOLD);
   DashButton(DASH_PREFIX + "BTN_RESET", InpDashX + 20 + bw, by + 28, bw, 22,
              (g_confirmBtn == DASH_PREFIX + "BTN_RESET" ? "CONFIRM RESET ?" : "RESET DAILY STATS"), DASH_GOLD);
   // resize background to content
   ObjectSetInteger(0, DASH_PREFIX + "BG", OBJPROP_YSIZE, by + 58 - InpDashY);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| BUTTON ACTIONS                                                   |
//+------------------------------------------------------------------+
void ActionCloseAll()
  {
   CloseAllEA("dashboard CLOSE ALL");
   for(int d = 0; d < 2; d++)
      if(g_setup[d].state == ST_TRADE_OPEN)
         SetState(g_setup[d], ST_SETUP_COMPLETED, "closed manually");
  }

void ActionCancelPending()
  {
   DeleteAllPendingsEA("dashboard CANCEL PENDING");
   for(int d = 0; d < 2; d++)
      if(g_setup[d].state == ST_WAITING_FOR_ENTRY && g_setup[d].orderTicket > 0 && !PendingExists(g_setup[d].orderTicket))
         Invalidate(g_setup[d], "pending cancelled manually");
  }

void ActionResetStats()
  {
   GlobalVariableSet(g_gvPrefix + "RESET", (double)TimeCurrent());
   GlobalVariableDel(g_gvPrefix + "EQHALT");
   g_stats.halted = false;
   g_stats.haltReason = "";
   RefreshDailyStats();
   EvaluateHalts();
   Log(LOG_BASIC, "Daily statistics reset by user");
  }

//+------------------------------------------------------------------+
//| INIT                                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_isTester = (bool)MQLInfoInteger(MQL_TESTER);
   g_visual   = (!g_isTester || (bool)MQLInfoInteger(MQL_VISUAL_MODE));
   g_point    = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_digits   = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   g_tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(g_tickSize <= 0) g_tickSize = g_point;
   g_unit     = (InpDistUnit > 0 ? InpDistUnit : g_point);
   if(g_point <= 0 || g_unit <= 0)
     {
      Print("Invalid symbol point size");
      return INIT_FAILED;
     }
   g_hedging = (AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING);

   //--- input validation
   if(InpMinScore < 0 || InpMinScore > 11)               { Print("InpMinScore must be 0..11"); return INIT_PARAMETERS_INCORRECT; }
   if(InpRiskPercent <= 0 && InpLotMode == LOT_RISK_PERCENT) { Print("InpRiskPercent must be > 0"); return INIT_PARAMETERS_INCORRECT; }
   if(InpFixedLot <= 0 && InpLotMode == LOT_FIXED)        { Print("InpFixedLot must be > 0"); return INIT_PARAMETERS_INCORRECT; }
   if(InpMaxOpenPositions < 1)                           { Print("InpMaxOpenPositions must be >= 1"); return INIT_PARAMETERS_INCORRECT; }
   if(InpMaxTradesPerSetup < 1)                          { Print("InpMaxTradesPerSetup must be >= 1"); return INIT_PARAMETERS_INCORRECT; }
   if(InpTPMode == TP_MULTI && (InpTP1_Pct + InpTP2_Pct >= 100.0))
     { Print("TP1% + TP2% must be < 100 (remainder runs to TP3)"); return INIT_PARAMETERS_INCORRECT; }
   if(InpTPMode == TP_MULTI && !(InpTP1_R < InpTP2_R && InpTP2_R < InpTP3_R))
     { Print("Multi TP requires TP1_R < TP2_R < TP3_R"); return INIT_PARAMETERS_INCORRECT; }
   if(PeriodSeconds(InpCRTTimeframe) < PeriodSeconds(PERIOD_M15))
     { Print("CRT timeframe should be M15 or higher"); return INIT_PARAMETERS_INCORRECT; }

   g_trade.SetExpertMagicNumber((ulong)InpMagic);
   g_trade.SetDeviationInPoints((ulong)MathMax(0, (ulong)InpSlippagePts));
   g_trade.SetTypeFilling(PreferredFilling());
   g_trade.SetAsyncMode(false);
   g_trade.LogLevel(LOG_LEVEL_ERRORS);

   //--- indicator handles (created once)
   g_hATR_M1 = iATR(_Symbol, PERIOD_M1, InpATRPeriod);
   g_hATR_M5 = iATR(_Symbol, PERIOD_M5, InpATRPeriod);
   g_hATR_LQ = iATR(_Symbol, InpLiqTimeframe, InpATRPeriod);
   if(g_hATR_M1 == INVALID_HANDLE || g_hATR_M5 == INVALID_HANDLE || g_hATR_LQ == INVALID_HANDLE)
     {
      Print("Failed to create ATR handles: ", GetLastError());
      return INIT_FAILED;
     }

   g_gvPrefix = "CRT_" + IntegerToString(InpMagic) + "_" + _Symbol + "_";
   if(StringLen(g_gvPrefix) > 40)
      g_gvPrefix = "CRT_" + IntegerToString(InpMagic) + "_";
   if(g_isTester)
      GlobalVariablesDeleteAll(g_gvPrefix);

   g_autoTrading = InpAutoTradingDefault;
   UpdateGMTOffset();
   g_lastGMTCalc = TimeCurrent();
   ParseFilters();

   g_range.valid = false;
   g_range.id = 0;
   g_range.high = 0;
   g_range.low = 0;
   g_range.mid = 0;
   g_range.refStart = 0;
   g_range.periodStart = 0;
   ResetSetup(g_setup[0], 1, ST_WAITING_FOR_RANGE);
   ResetSetup(g_setup[1], -1, ST_WAITING_FOR_RANGE);
   g_reason[0] = "";
   g_reason[1] = "";
   g_stats.halted = false;
   g_stats.haltReason = "";
   g_stats.dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_stats.closedPL = 0;
   g_stats.closedPLAcc = 0;
   g_stats.tradesToday = 0;
   g_stats.consecLosses = 0;
   g_stats.dayStart = DayStart(TimeCurrent());
   g_lastM1 = 0; g_lastM5 = 0; g_lastLQ = 0; g_lastCRT = 0;
   g_lastDay = DayStart(TimeCurrent());

   RecoverState();
   CleanupGVs();
   RefreshDailyStats();
   EvaluateHalts();

   Log(LOG_BASIC, StringFormat("INIT  %s  digits=%d point=%s tick=%s unit=%s  %s account  GMT offset=%+.2fh  contract=%.2f  volume[min %.2f step %.2f max %.2f]",
                               _Symbol, g_digits, DoubleToString(g_point, g_digits), DoubleToString(g_tickSize, g_digits),
                               DoubleToString(g_unit, g_digits), (g_hedging ? "HEDGING" : "NETTING"), g_gmtOffsetSec / 3600.0,
                               SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
                               SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX)));
   if(InpDistUnit <= 0 && StringFind(_Symbol, "XAU") >= 0 && g_digits == 3)
      Log(LOG_BASIC, "NOTE: 3-digit gold quote detected - set InpDistUnit = 0.01 to keep default distances broker-independent");
   if(InpDiagnosticMode)
      Log(LOG_BASIC, "DIAGNOSTIC MODE: signals are evaluated, logged and drawn - no orders will be sent");

   if(!g_isTester || g_visual)
      EventSetTimer(1);
   UpdateDashboard();
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| DEINIT                                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_hATR_M1 != INVALID_HANDLE) { IndicatorRelease(g_hATR_M1); g_hATR_M1 = INVALID_HANDLE; }
   if(g_hATR_M5 != INVALID_HANDLE) { IndicatorRelease(g_hATR_M5); g_hATR_M5 = INVALID_HANDLE; }
   if(g_hATR_LQ != INVALID_HANDLE) { IndicatorRelease(g_hATR_LQ); g_hATR_LQ = INVALID_HANDLE; }
   ObjectsDeleteAll(0, DASH_PREFIX);
   // keep analysis drawings in the tester for review; remove them on a live chart
   if(!g_isTester)
      ObjectsDeleteAll(0, OBJ_PREFIX);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| TICK                                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk) || tk.bid <= 0 || tk.ask <= 0)
      return;

   //--- new trading day
   datetime today = DayStart(TimeCurrent());
   if(today != g_lastDay)
     {
      g_lastDay = today;
      GlobalVariableDel(g_gvPrefix + "EQHALT");
      g_statsDirty = true;
      CleanupGVs();
      Log(LOG_BASIC, "New trading day - daily limits reset");
     }
   if(!g_isTester && TimeCurrent() - g_lastGMTCalc >= 3600)
     {
      UpdateGMTOffset();
      g_lastGMTCalc = TimeCurrent();
     }

   if(g_statsDirty)
      RefreshDailyStats();
   EvaluateHalts();

   //--- per-tick management
   SyncSetups();
   ManagePendings();
   ManagePositions();

   string news = "";
   if(InpNewsClosePositions && InNewsBlackout(news) && CountOurPositions() > 0)
      CloseAllEA(news);

   //--- closed-bar logic: everything below runs once per new M1 bar
   if(IsNewBar(PERIOD_M1, g_lastM1))
     {
      bool newCRT = IsNewBar(InpCRTTimeframe, g_lastCRT);
      bool newLQ  = IsNewBar(InpLiqTimeframe, g_lastLQ);
      bool newM5  = IsNewBar(PERIOD_M5, g_lastM5);

      if(newCRT || g_range.id == 0 || InpCRTMode == CRT_PREV_SESSION)
        {
         if(!UpdateCRTRange())
            g_lastCRT = 0; // data not ready - retry next bar
         DrawCRT();
        }
      if(newLQ || ArraySize(g_liq) == 0 || newCRT)
        {
         UpdateLiquidity();
         DrawLiquidity();
        }
      if(newM5)
        {
         ProcessM5();
         CheckPositionInvalidation();
        }
      ProcessM1();
      UpdateDashboard();
      g_lastDashUpdate = TimeCurrent();
     }
   else
      if(DashboardEnabled() && g_isTester && TimeCurrent() - g_lastDashUpdate >= 5)
        {
         UpdateDashboard();
         g_lastDashUpdate = TimeCurrent();
        }
  }

//+------------------------------------------------------------------+
//| TIMER (dashboard refresh + confirmation timeouts)                |
//+------------------------------------------------------------------+
void OnTimer()
  {
   if(g_confirmBtn != "" && TimeLocal() - g_confirmTime > 5)
      g_confirmBtn = "";
   if(!g_isTester)
      UpdateDashboard();
  }

//+------------------------------------------------------------------+
//| CHART EVENTS (buttons, two-click confirmation)                   |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id != CHARTEVENT_OBJECT_CLICK)
      return;
   if(StringFind(sparam, DASH_PREFIX + "BTN_") != 0)
      return;
   ObjectSetInteger(0, sparam, OBJPROP_STATE, false);

   if(sparam == DASH_PREFIX + "BTN_AUTO")
     {
      g_autoTrading = !g_autoTrading;
      Log(LOG_BASIC, StringFormat("Auto trading switched %s by user", (g_autoTrading ? "ON" : "OFF")));
      g_confirmBtn = "";
      UpdateDashboard();
      return;
     }
   // destructive actions need a second click within 5 seconds
   if(g_confirmBtn != sparam || TimeLocal() - g_confirmTime > 5)
     {
      g_confirmBtn = sparam;
      g_confirmTime = TimeLocal();
      UpdateDashboard();
      return;
     }
   g_confirmBtn = "";
   if(sparam == DASH_PREFIX + "BTN_CLOSE")
      ActionCloseAll();
   else
      if(sparam == DASH_PREFIX + "BTN_CANCEL")
         ActionCancelPending();
      else
         if(sparam == DASH_PREFIX + "BTN_RESET")
            ActionResetStats();
   UpdateDashboard();
  }

//+------------------------------------------------------------------+
//| TRADE TRANSACTIONS                                               |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD || trans.type == TRADE_TRANSACTION_HISTORY_ADD)
      g_statsDirty = true;
  }
//+------------------------------------------------------------------+

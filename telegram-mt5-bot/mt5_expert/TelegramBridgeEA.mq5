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
//| Each file is deleted once processed. Results are printed to the |
//| Experts/Journal log - the Python side never reads a result file,|
//| it just polls positions/orders by magic number afterwards.      |
//+------------------------------------------------------------------+
#property copyright "Telegram MT5 signal bot"
#property strict

input string BridgeSubfolder   = "tg_bridge";   // subfolder under Common\Files
input int    PollSeconds       = 1;             // how often to check for new commands
input int    HeartbeatSeconds  = 60;            // how often to print an "I'm alive" log line

datetime g_lastHeartbeat = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   EventSetTimer(PollSeconds);
   PrintFormat("TelegramBridgeEA started, watching Common\\Files\\%s\\", BridgeSubfolder);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      Print("WARNING: Algo Trading is currently OFF - this EA cannot place orders until it's enabled.");
   ProcessBridgeFolder();
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   ProcessBridgeFolder();

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
   else
      PrintFormat("Bridge: unknown command TYPE in %s: '%s'", relativePath, type);

   if(!FileDelete(relativePath, FILE_COMMON))
      PrintFormat("Bridge: could not delete processed file %s (error %d)", relativePath, GetLastError());
  }

//+------------------------------------------------------------------+
//| Places one pending order per ORDER= line.                        |
//+------------------------------------------------------------------+
void HandleOpenOrders(long magic, string symbol, string comment, int deviation, string &orderLines[], int orderCount)
  {
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

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

      ENUM_ORDER_TYPE orderType;
      if(direction == "BUY")
         orderType = (entry < ask) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_BUY_STOP;
      else
         orderType = (entry > bid) ? ORDER_TYPE_SELL_LIMIT : ORDER_TYPE_SELL_STOP;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action       = TRADE_ACTION_PENDING;
      request.symbol       = symbol;
      request.volume       = lot;
      request.type         = orderType;
      request.price        = entry;
      request.sl           = sl;
      request.tp           = tp;
      request.deviation    = deviation;
      request.magic        = magic;
      request.comment      = comment;
      request.type_time    = ORDER_TIME_GTC;
      request.type_filling = ORDER_FILLING_RETURN;

      bool ok = OrderSend(request, result);
      if(!ok || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("Bridge: order FAILED %s @ %.2f retcode=%d comment='%s'",
                     direction, entry, result.retcode, result.comment);
      else
         PrintFormat("Bridge: placed %s @ %.2f sl=%.2f tp=%.2f ticket=%d",
                     direction, entry, sl, tp, (int)result.order);
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

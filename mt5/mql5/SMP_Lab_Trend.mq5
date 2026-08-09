//+------------------------------------------------------------------+
//|  SMP_Lab_Trend.mq5                                               |
//|  smp-lab trend sistemi — GORSEL indikator (islem YAPMAZ)         |
//|  mt5/bot.py ile AYNI mantik: Donchian kirilim + EMA trend + ER    |
//|  rejim kapisi; ATR x2 stop, 2R hedef. LONG/SHORT ok + SL/TP cizgi |
//+------------------------------------------------------------------+
#property copyright "smp-lab"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 7
#property indicator_plots   5

//--- 0: LONG ok
#property indicator_label1  "LONG"
#property indicator_type1   DRAW_ARROW
#property indicator_color1  clrLime
#property indicator_width1  2
//--- 1: SHORT ok
#property indicator_label2  "SHORT"
#property indicator_type2   DRAW_ARROW
#property indicator_color2  clrRed
#property indicator_width2  2
//--- 2: EMA trend
#property indicator_label3  "EMA Trend"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrDodgerBlue
#property indicator_width3  2
//--- 3/4: Donchian kanal
#property indicator_label4  "Donchian Ust"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrDimGray
#property indicator_style4  STYLE_DOT
#property indicator_label5  "Donchian Alt"
#property indicator_type5   DRAW_LINE
#property indicator_color5  clrDimGray
#property indicator_style5  STYLE_DOT

input int    EntryN     = 55;    // Donchian giris periyodu
input int    TrendEMA   = 200;   // EMA trend filtresi
input int    ErPeriod   = 20;    // Efficiency Ratio periyodu
input double ErMin      = 0.30;  // ER rejim esigi (altinda islem yok)
input int    AtrPeriod  = 14;    // ATR periyodu
input double SlAtrMult  = 2.0;   // Stop = ATR x bu
input double RR         = 2.0;   // Hedef = R:R
input int    ShowLastN  = 6;     // Kac sinyalin SL/TP cizgisi gorunsun
input int    LineBars   = 24;    // SL/TP cizgi uzunlugu (bar)
input bool   ShowPanel  = true;  // Bilgi paneli

double BufLong[], BufShort[], BufEma[], BufUp[], BufDn[], BufAtr[], BufEr[];
int    hEma, hAtr;
string PFX = "SMPLAB_";

//+------------------------------------------------------------------+
int OnInit()
{
   SetIndexBuffer(0, BufLong,  INDICATOR_DATA);
   SetIndexBuffer(1, BufShort, INDICATOR_DATA);
   SetIndexBuffer(2, BufEma,   INDICATOR_DATA);
   SetIndexBuffer(3, BufUp,    INDICATOR_DATA);
   SetIndexBuffer(4, BufDn,    INDICATOR_DATA);
   SetIndexBuffer(5, BufAtr,   INDICATOR_CALCULATIONS);
   SetIndexBuffer(6, BufEr,    INDICATOR_CALCULATIONS);

   PlotIndexSetInteger(0, PLOT_ARROW, 233);   // yukari ok
   PlotIndexSetInteger(1, PLOT_ARROW, 234);   // asagi ok
   for(int i = 0; i < 5; i++)
      PlotIndexSetDouble(i, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   hEma = iMA(_Symbol, _Period, TrendEMA, 0, MODE_EMA, PRICE_CLOSE);
   hAtr = iATR(_Symbol, _Period, AtrPeriod);
   if(hEma == INVALID_HANDLE || hAtr == INVALID_HANDLE)
   {
      Print("SMP_Lab_Trend: gosterge handle olusturulamadi");
      return(INIT_FAILED);
   }
   IndicatorSetString(INDICATOR_SHORTNAME, "SMP-Lab Trend (Donchian" + (string)EntryN +
                      " + EMA" + (string)TrendEMA + " + ER>" + DoubleToString(ErMin, 2) + ")");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, PFX);
   Comment("");
}

//+------------------------------------------------------------------+
//| Efficiency Ratio: |net degisim| / toplam yol                     |
//+------------------------------------------------------------------+
double CalcER(const double &close[], int i, int n)
{
   if(i < n) return(0.0);
   double net = MathAbs(close[i] - close[i - n]);
   double path = 0.0;
   for(int k = i - n + 1; k <= i; k++)
      path += MathAbs(close[k] - close[k - 1]);
   return(path > 0.0 ? net / path : 0.0);
}

//+------------------------------------------------------------------+
//| Sinyal icin SL/TP cizgilerini ve etiketini ciz                   |
//+------------------------------------------------------------------+
void DrawTrade(datetime t0, datetime t1, double entry, double sl, double tp, bool isLong, int id)
{
   string base = PFX + (string)id + "_";
   string names[3];  double prices[3];  color cols[3];
   names[0] = base + "E"; prices[0] = entry; cols[0] = clrWhite;
   names[1] = base + "S"; prices[1] = sl;    cols[1] = clrCrimson;
   names[2] = base + "T"; prices[2] = tp;    cols[2] = clrMediumSpringGreen;

   for(int k = 0; k < 3; k++)
   {
      if(ObjectFind(0, names[k]) < 0)
         ObjectCreate(0, names[k], OBJ_TREND, 0, t0, prices[k], t1, prices[k]);
      else
      {
         ObjectMove(0, names[k], 0, t0, prices[k]);
         ObjectMove(0, names[k], 1, t1, prices[k]);
      }
      ObjectSetInteger(0, names[k], OBJPROP_COLOR, cols[k]);
      ObjectSetInteger(0, names[k], OBJPROP_WIDTH, k == 0 ? 1 : 2);
      ObjectSetInteger(0, names[k], OBJPROP_STYLE, k == 0 ? STYLE_DOT : STYLE_SOLID);
      ObjectSetInteger(0, names[k], OBJPROP_RAY_RIGHT, false);
      ObjectSetInteger(0, names[k], OBJPROP_BACK, true);
      ObjectSetInteger(0, names[k], OBJPROP_SELECTABLE, false);
   }
   // etiket
   string lb = base + "L";
   double slPct = MathAbs(entry - sl) / entry * 100.0;
   double tpPct = MathAbs(tp - entry) / entry * 100.0;
   string txt = (isLong ? "LONG" : "SHORT") + "  SL -" + DoubleToString(slPct, 2) +
                "%  TP +" + DoubleToString(tpPct, 2) + "%  (1:" + DoubleToString(RR, 1) + ")";
   if(ObjectFind(0, lb) < 0)
      ObjectCreate(0, lb, OBJ_TEXT, 0, t0, isLong ? sl : tp);
   else
      ObjectMove(0, lb, 0, t0, isLong ? sl : tp);
   ObjectSetString(0, lb, OBJPROP_TEXT, txt);
   ObjectSetInteger(0, lb, OBJPROP_COLOR, isLong ? clrLime : clrRed);
   ObjectSetInteger(0, lb, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, lb, OBJPROP_ANCHOR, isLong ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
   ObjectSetInteger(0, lb, OBJPROP_SELECTABLE, false);
}

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total, const int prev_calculated,
                const datetime &time[], const double &open[], const double &high[],
                const double &low[], const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
{
   int need = MathMax(MathMax(EntryN, TrendEMA), ErPeriod) + 5;
   if(rates_total < need) return(0);

   if(CopyBuffer(hEma, 0, 0, rates_total, BufEma) <= 0) return(0);
   if(CopyBuffer(hAtr, 0, 0, rates_total, BufAtr) <= 0) return(0);

   int start;
   static int posState = 0;      // 0 flat, +1 long, -1 short
   static int tradeId  = 0;
   if(prev_calculated == 0)
   {
      ArrayInitialize(BufLong,  EMPTY_VALUE);
      ArrayInitialize(BufShort, EMPTY_VALUE);
      ArrayInitialize(BufUp,    EMPTY_VALUE);
      ArrayInitialize(BufDn,    EMPTY_VALUE);
      ObjectsDeleteAll(0, PFX);
      posState = 0; tradeId = 0;
      start = need;
   }
   else start = MathMax(prev_calculated - 1, need);

   // SON BAR HARIC: olusmakta olan bar sinyal uretmez (repaint yok!)
   int last = rates_total - 2;

   for(int i = start; i <= last; i++)
   {
      // Donchian (onceki barlara bakar -> lookahead yok)
      double hh = high[i - 1], ll = low[i - 1];
      for(int k = i - EntryN; k <= i - 1; k++)
      {
         if(k < 0) continue;
         if(high[k] > hh) hh = high[k];
         if(low[k]  < ll) ll = low[k];
      }
      BufUp[i] = hh;  BufDn[i] = ll;
      BufEr[i] = CalcER(close, i, ErPeriod);
      BufLong[i] = EMPTY_VALUE;  BufShort[i] = EMPTY_VALUE;

      bool regime = (BufEr[i] > ErMin);
      bool wasFlat = (posState == 0);

      if(posState == 0 && regime)
      {
         if(close[i] > hh && close[i] > BufEma[i])      posState = 1;
         else if(close[i] < ll && close[i] < BufEma[i]) posState = -1;
      }
      else if(posState > 0 && close[i] < BufEma[i]) posState = 0;
      else if(posState < 0 && close[i] > BufEma[i]) posState = 0;

      // yeni giris bari mi?
      if(wasFlat && posState != 0)
      {
         bool isLong = (posState > 0);
         double entry = close[i];
         double dist  = BufAtr[i] * SlAtrMult;
         double sl = isLong ? entry - dist : entry + dist;
         double tp = isLong ? entry + dist * RR : entry - dist * RR;

         if(isLong) BufLong[i]  = low[i]  - dist * 0.25;
         else       BufShort[i] = high[i] + dist * 0.25;

         tradeId++;
         if(tradeId > ShowLastN)
         {
            string old = PFX + (string)(tradeId - ShowLastN) + "_";
            ObjectsDeleteAll(0, old);
         }
         datetime t1 = time[i] + (datetime)(PeriodSeconds() * LineBars);
         DrawTrade(time[i], t1, entry, sl, tp, isLong, tradeId);
      }
   }

   if(ShowPanel)
   {
      int i = last;
      double er = BufEr[i];
      string durum = (posState > 0 ? "LONG ACIK" : posState < 0 ? "SHORT ACIK" : "beklemede");
      string rej   = (er > ErMin ? "TREND (islem serbest)" : "CHOP (islem YOK)");
      Comment(
         "\n  ══ SMP-LAB TREND ══",
         "\n  Sembol/TF : ", _Symbol, " ", EnumToString((ENUM_TIMEFRAMES)_Period),
         "\n  Rejim (ER): ", DoubleToString(er, 2), "  esik ", DoubleToString(ErMin, 2), "  -> ", rej,
         "\n  Trend EMA", TrendEMA, ": fiyat ", (close[i] > BufEma[i] ? "USTUNDE (boga)" : "ALTINDA (ayi)"),
         "\n  Donchian", EntryN, ": ust ", DoubleToString(BufUp[i], _Digits),
         "  alt ", DoubleToString(BufDn[i], _Digits),
         "\n  Durum     : ", durum,
         "\n  Toplam sinyal: ", tradeId,
         "\n  (stop ATR x", DoubleToString(SlAtrMult, 1), ", hedef 1:", DoubleToString(RR, 1),
         " — indikator ISLEM YAPMAZ)"
      );
   }
   return(rates_total);
}
//+------------------------------------------------------------------+

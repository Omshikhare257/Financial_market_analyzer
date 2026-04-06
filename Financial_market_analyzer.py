#!/usr/bin/env python3
"""
FinVision v6.1 — Backend (app.py)
Run: python app.py

=== SETUP ===
1. Install packages:
   pip install flask yfinance pandas numpy requests beautifulsoup4 anthropic lxml

2. SET YOUR API KEYS HERE (lines 30-35):
   GEMINI_API_KEY  = "YOUR_GEMINI_KEY_HERE"
   ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_KEY_HERE"

3. Run: python app.py
   Opens: http://localhost:5000
"""

import os, re, json, threading, time, webbrowser
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ═══════════════════════════════════════════════════════
#  🔑 API KEYS — PASTE YOUR KEYS HERE
# ═══════════════════════════════════════════════════════
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY_HERE")
GEMINI_MODEL      = "gemini-1.5-flash"   # or gemini-2.0-flash, gemini-1.5-pro
# ═══════════════════════════════════════════════════════

try:
    from flask import Flask, jsonify, request, send_from_directory
    import yfinance as yf
    import pandas as pd
    import numpy as np
    import requests as req_lib
    from bs4 import BeautifulSoup
    DEPS_OK = True
    MISSING = ""
except ImportError as e:
    DEPS_OK = False
    MISSING = str(e)

try:
    import anthropic as _anthropic_lib
    AI_AVAILABLE = bool(ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "YOUR_ANTHROPIC_API_KEY_HERE")
except ImportError:
    _anthropic_lib = None
    AI_AVAILABLE = False

GEMINI_AVAILABLE = bool(GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE")

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "finvision_v6_2025")

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 60
_LIVE_PRICES = {}
_LIVE_LOCK = threading.Lock()
_LIVE_TTL = 5

def cache_get(key, ttl=None):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        t = ttl if ttl is not None else _CACHE_TTL
        if item and (time.time() - item['ts']) < t:
            return item['data']
    return None

def cache_set(key, data):
    with _CACHE_LOCK:
        _CACHE[key] = {'data': data, 'ts': time.time()}

def live_price_get(ticker):
    with _LIVE_LOCK:
        item = _LIVE_PRICES.get(ticker)
        if item and (time.time() - item['ts']) < _LIVE_TTL:
            return item['data']
    return None

def live_price_set(ticker, data):
    with _LIVE_LOCK:
        _LIVE_PRICES[ticker] = {'data': data, 'ts': time.time()}

GLOBAL_INDICES = {
    "S&P 500":"^GSPC","NASDAQ":"^IXIC","Dow Jones":"^DJI",
    "FTSE 100":"^FTSE","DAX":"^GDAXI","Nikkei 225":"^N225",
    "Shanghai":"000001.SS","Hang Seng":"^HSI","CAC 40":"^FCHI","ASX 200":"^AXJO",
}
INDIAN_INDICES = {
    "NIFTY 50":"^NSEI","SENSEX":"^BSESN","NIFTY BANK":"^NSEBANK",
    "NIFTY IT":"^CNXIT","NIFTY AUTO":"^CNXAUTO","NIFTY PHARMA":"^CNXPHARMA",
    "NIFTY FMCG":"^CNXFMCG","NIFTY METAL":"^CNXMETAL","NIFTY REALTY":"^CNXREALTY",
}
GLOBAL_SECTOR_ETFS = {
    "Technology":"XLK","Healthcare":"XLV","Financials":"XLF","Energy":"XLE",
    "Consumer Disc":"XLY","Industrials":"XLI","Materials":"XLB","Utilities":"XLU",
    "Real Estate":"XLRE","Communication":"XLC","Semiconductors":"SOXX",
    "Clean Energy":"ICLN","AI & Tech":"AIQ","Biotech":"XBI",
}
INDIAN_SECTOR_INDICES = {
    "NIFTY IT":"^CNXIT","NIFTY BANK":"^NSEBANK","NIFTY AUTO":"^CNXAUTO",
    "NIFTY PHARMA":"^CNXPHARMA","NIFTY FMCG":"^CNXFMCG","NIFTY METAL":"^CNXMETAL",
    "NIFTY REALTY":"^CNXREALTY","NIFTY ENERGY":"^CNXENERGY","NIFTY INFRA":"^CNXINFRA",
    "NIFTY PSU BANK":"^CNXPSUBANK",
}
POPULAR_INDIAN_STOCKS = {
    "Reliance":"RELIANCE.NS","TCS":"TCS.NS","Infosys":"INFY.NS",
    "HDFC Bank":"HDFCBANK.NS","ICICI Bank":"ICICIBANK.NS","Wipro":"WIPRO.NS",
    "HCL Tech":"HCLTECH.NS","Bajaj Finance":"BAJFINANCE.NS","Adani Ent.":"ADANIENT.NS",
    "ITC":"ITC.NS","SBI":"SBIN.NS","Kotak Bank":"KOTAKBANK.NS","L&T":"LT.NS",
    "Asian Paints":"ASIANPAINT.NS","Maruti":"MARUTI.NS","Tata Motors":"TATAMOTORS.NS",
    "Sun Pharma":"SUNPHARMA.NS","Titan":"TITAN.NS","NTPC":"NTPC.NS",
    "Power Grid":"POWERGRID.NS","Zomato":"ZOMATO.NS","Axis Bank":"AXISBANK.NS",
    "Tata Steel":"TATASTEEL.NS","Nestle India":"NESTLEIND.NS","ONGC":"ONGC.NS",
    "Mahindra":"M&M.NS","Dr Reddy's":"DRREDDY.NS","Divi's Labs":"DIVISLAB.NS",
    "IRCTC":"IRCTC.NS","HAL":"HAL.NS",
}
POPULAR_GLOBAL_STOCKS = {
    "Apple":"AAPL","Microsoft":"MSFT","Google":"GOOGL","Amazon":"AMZN",
    "Tesla":"TSLA","NVIDIA":"NVDA","Meta":"META","Netflix":"NFLX",
    "Berkshire":"BRK-B","JPMorgan":"JPM","TSMC":"TSM","Walmart":"WMT",
    "Visa":"V","Samsung":"005930.KS","ASML":"ASML","Toyota":"TM",
}
BONDS_AND_COMMODITIES = {
    "Gold":"GC=F","Silver":"SI=F","Crude Oil (WTI)":"CL=F","Brent Crude":"BZ=F",
    "Natural Gas":"NG=F","Copper":"HG=F",
    "Bitcoin":"BTC-USD","Ethereum":"ETH-USD","BNB":"BNB-USD","Solana":"SOL-USD","XRP":"XRP-USD",
    "US 10Y Treasury":"^TNX","US 2Y Treasury":"^IRX",
}
FOREX_PAIRS = {
    "USD/INR":"USDINR=X","EUR/USD":"EURUSD=X","GBP/USD":"GBPUSD=X",
    "USD/JPY":"USDJPY=X","EUR/INR":"EURINR=X","GBP/INR":"GBPINR=X",
    "AUD/USD":"AUDUSD=X","USD/CHF":"USDCHF=X","USD/CNY":"USDCNY=X",
}
ALL_LIVE_TICKERS = {}
ALL_LIVE_TICKERS.update(INDIAN_INDICES)
ALL_LIVE_TICKERS.update(GLOBAL_INDICES)
ALL_LIVE_TICKERS.update({k: v for k, v in BONDS_AND_COMMODITIES.items() if k in ["Gold","Bitcoin","Crude Oil (WTI)","Ethereum"]})
ALL_LIVE_TICKERS.update({"USD/INR": "USDINR=X"})

def safe_float(val, decimals=2):
    try:
        v = float(val)
        return None if v != v else round(v, decimals)
    except:
        return None

def _fetch_one(ticker, timeout=8):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", auto_adjust=True, timeout=timeout)
        if hist.empty:
            return {"error": "No data"}
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
        ch = last - prev
        pct = (ch / prev * 100) if prev else 0.0
        info = {}
        try:
            info = t.info or {}
        except:
            pass
        return {
            "price": safe_float(last),
            "change": safe_float(ch),
            "change_pct": safe_float(pct),
            "volume": safe_float(info.get("volume") or info.get("regularMarketVolume")),
            "market_cap": info.get("marketCap"),
            "pe_ratio": safe_float(info.get("trailingPE")),
            "52w_high": safe_float(info.get("fiftyTwoWeekHigh")),
            "52w_low": safe_float(info.get("fiftyTwoWeekLow")),
            "name": info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", ""),
            "ts": time.time(),
        }
    except Exception as e:
        return {"error": str(e)[:60]}

def _fetch_live_price_only(ticker, timeout=5):
    cached = live_price_get(ticker)
    if cached:
        return cached
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d", auto_adjust=True, timeout=timeout)
        if hist.empty:
            return None
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
        ch = last - prev
        pct = (ch / prev * 100) if prev else 0.0
        data = {"price": safe_float(last), "change": safe_float(ch), "change_pct": safe_float(pct), "ts": time.time()}
        live_price_set(ticker, data)
        return data
    except:
        return None

def fetch_many(ticker_map, timeout=12):
    result = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(_fetch_one, ticker, 8): name for name, ticker in ticker_map.items()}
        done_iter = as_completed(futures, timeout=timeout)
        try:
            for fut in done_iter:
                name = futures[fut]
                try:
                    result[name] = fut.result()
                except Exception as e:
                    result[name] = {"error": str(e)[:40]}
        except Exception:
            pass
    for name in ticker_map:
        if name not in result:
            result[name] = {"error": "timeout"}
    return result

def get_india_indices():
    d = cache_get("india_indices")
    if d: return d
    d = fetch_many(INDIAN_INDICES, timeout=15)
    cache_set("india_indices", d)
    return d

def get_global_indices():
    d = cache_get("global_indices")
    if d: return d
    d = fetch_many(GLOBAL_INDICES, timeout=15)
    cache_set("global_indices", d)
    return d

def get_bonds():
    d = cache_get("bonds")
    if d: return d
    d = fetch_many(BONDS_AND_COMMODITIES, timeout=15)
    cache_set("bonds", d)
    return d

def get_forex():
    d = cache_get("forex")
    if d: return d
    d = fetch_many(FOREX_PAIRS, timeout=12)
    cache_set("forex", d)
    return d

def get_india_stocks():
    d = cache_get("india_stocks")
    if d: return d
    d = fetch_many(POPULAR_INDIAN_STOCKS, timeout=20)
    for name, ticker in POPULAR_INDIAN_STOCKS.items():
        if name in d: d[name]["ticker"] = ticker
    cache_set("india_stocks", d)
    return d

def get_global_stocks():
    d = cache_get("global_stocks")
    if d: return d
    d = fetch_many(POPULAR_GLOBAL_STOCKS, timeout=20)
    for name, ticker in POPULAR_GLOBAL_STOCKS.items():
        if name in d: d[name]["ticker"] = ticker
    cache_set("global_stocks", d)
    return d

def _fetch_history(ticker, period="3mo"):
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True, timeout=10)
        if hist.empty: return []
        return [
            {"date": dt.strftime("%Y-%m-%d"),
             "open": safe_float(row["Open"]), "high": safe_float(row["High"]),
             "low": safe_float(row["Low"]), "close": safe_float(row["Close"]),
             "volume": safe_float(row["Volume"])}
            for dt, row in hist.iterrows()
        ]
    except: return []

def _fetch_fundamentals(ticker):
    try:
        info = yf.Ticker(ticker).info or {}
        return {
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "summary": (info.get("longBusinessSummary") or "")[:500],
            "eps": safe_float(info.get("trailingEps")),
            "profit_margin": safe_float(info.get("profitMargins")),
            "debt_equity": safe_float(info.get("debtToEquity")),
            "roe": safe_float(info.get("returnOnEquity")),
            "roa": safe_float(info.get("returnOnAssets")),
            "current_ratio": safe_float(info.get("currentRatio")),
            "beta": safe_float(info.get("beta")),
            "dividend_yield": safe_float(info.get("dividendYield")),
            "peg_ratio": safe_float(info.get("pegRatio")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "analyst_target": safe_float(info.get("targetMeanPrice")),
            "recommendation": info.get("recommendationKey", ""),
            "num_analyst_opinions": info.get("numberOfAnalystOpinions"),
            "earnings_growth": safe_float(info.get("earningsGrowth")),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "gross_margins": safe_float(info.get("grossMargins")),
            "free_cashflow": info.get("freeCashflow"),
            "insider_pct": safe_float(info.get("heldPercentInsiders")),
            "institution_pct": safe_float(info.get("heldPercentInstitutions")),
            "short_ratio": safe_float(info.get("shortRatio")),
            "payout_ratio": safe_float(info.get("payoutRatio")),
            "52w_high": safe_float(info.get("fiftyTwoWeekHigh")),
            "52w_low": safe_float(info.get("fiftyTwoWeekLow")),
            "avg_volume": safe_float(info.get("averageVolume")),
            "shares_outstanding": info.get("sharesOutstanding"),
        }
    except: return {}

def _technical_analysis(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1y", auto_adjust=True, timeout=12)
        if hist.empty or len(hist) < 30: return {}
        close = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float)
        curr = close.iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200, min_periods=50).mean().iloc[-1]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - 100 / (1 + rs)).iloc[-1])
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd = float(macd_line.iloc[-1])
        signal = float(signal_line.iloc[-1])
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = float((bb_mid + 2 * bb_std).iloc[-1])
        bb_lower = float((bb_mid - 2 * bb_std).iloc[-1])
        recent = close.tail(60)
        support = safe_float(recent.min())
        resistance = safe_float(recent.max())
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        curr_vol = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol if avg_vol else 1.0
        obv_val = 0
        obv = []
        cl = close.tolist()
        vl = volume.tolist()
        for i in range(1, len(cl)):
            if cl[i] > cl[i - 1]: obv_val += vl[i]
            elif cl[i] < cl[i - 1]: obv_val -= vl[i]
            obv.append(obv_val)
        obv_trend = "Rising" if len(obv) > 5 and obv[-1] > obv[-5] else "Falling"
        low14 = hist["Low"].rolling(14).min()
        high14 = hist["High"].rolling(14).max()
        stoch_k = float(((hist["Close"] - low14) / (high14 - low14) * 100).iloc[-1])
        high = hist["High"].astype(float)
        low_col = hist["Low"].astype(float)
        tr = pd.DataFrame({
            'hl': high - low_col,
            'hc': (high - close.shift()).abs(),
            'lc': (low_col - close.shift()).abs()
        }).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        atr_pct = safe_float(atr / curr * 100, 2)
        year_high = float(close.tail(252).max())
        year_low = float(close.tail(252).min())
        week52_pos = safe_float((curr - year_low) / (year_high - year_low) * 100 if year_high != year_low else 50, 1)

        # ADX calculation
        plus_dm = high.diff()
        minus_dm = low_col.diff()
        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > -minus_dm), 0.0)
        minus_dm = (-minus_dm).where((-minus_dm > 0) & (-minus_dm > plus_dm), 0.0)
        tr_adx = pd.DataFrame({'hl': high - low_col, 'hc': (high - close.shift()).abs(), 'lc': (low_col - close.shift()).abs()}).max(axis=1)
        atr14 = tr_adx.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).abs())
        adx_val = float(dx.rolling(14).mean().iloc[-1]) if not dx.isna().all() else 20.0

        # SMA200 distance
        sma200_dist = safe_float((curr - ma200) / ma200 * 100, 2) if ma200 else None

        # Momentum score
        score = 50
        if curr > ma20: score += 8
        if curr > ma50: score += 8
        if curr > ma200: score += 9
        if macd > signal: score += 10
        if 30 < rsi < 70: score += 5
        if rsi > 50: score += 5
        if vol_ratio > 1.2: score += 5
        if obv_trend == "Rising": score += 10
        score = min(100, max(0, score))

        signals = []
        signals.append("Above MA20 ▲" if curr > ma20 else "Below MA20 ▼")
        signals.append("Above MA50 ▲" if curr > ma50 else "Below MA50 ▼")
        if rsi < 30: signals.append("Oversold RSI🟢")
        elif rsi > 70: signals.append("Overbought RSI🔴")
        else: signals.append(f"RSI Neutral {rsi:.0f}")
        signals.append("MACD Bullish ▲" if macd > signal else "MACD Bearish ▼")
        if vol_ratio > 1.5: signals.append(f"High Volume {vol_ratio:.1f}x ⚡")
        if stoch_k < 20: signals.append("Stoch Oversold 🟢")
        elif stoch_k > 80: signals.append("Stoch Overbought 🔴")

        return {
            "current_price": safe_float(curr),
            "ma20": safe_float(ma20), "ma50": safe_float(ma50), "ma200": safe_float(ma200),
            "rsi": safe_float(rsi, 2), "macd": safe_float(macd, 4), "signal": safe_float(signal, 4),
            "bb_upper": safe_float(bb_upper), "bb_lower": safe_float(bb_lower),
            "support": support, "resistance": resistance,
            "vol_ratio": safe_float(vol_ratio, 2), "obv_trend": obv_trend,
            "momentum_score": score, "signals": signals,
            "stoch_k": safe_float(stoch_k, 1), "atr_pct": atr_pct,
            "week52_pos": week52_pos,
            "year_high": safe_float(year_high), "year_low": safe_float(year_low),
            "adx": safe_float(adx_val, 2),
            "sma200_dist": sma200_dist,
        }
    except Exception as e:
        return {"error": str(e)[:60]}

def _future_performance(ticker):
    try:
        info = yf.Ticker(ticker).info or {}
        sc = {}
        details = {}
        rec = info.get("recommendationKey", "").lower()
        analyst_score = {"strong_buy": 95, "buy": 78, "hold": 52, "sell": 28, "strong_sell": 10}.get(rec, 50)
        target = safe_float(info.get("targetMeanPrice"))
        curr = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        upside = round((target - curr) / curr * 100, 2) if target and curr and curr > 0 else None
        if upside is not None:
            if upside > 30: analyst_score = min(100, analyst_score + 15)
            elif upside > 15: analyst_score = min(100, analyst_score + 8)
            elif upside < -10: analyst_score = max(0, analyst_score - 15)
        sc["analyst"] = analyst_score
        details["analyst_target"] = target
        details["analyst_upside_pct"] = upside
        details["analyst_count"] = info.get("numberOfAnalystOpinions", 0) or 0
        details["recommendation"] = rec.replace("_", " ").title() if rec else "N/A"
        eg = info.get("earningsGrowth")
        rg = info.get("revenueGrowth")
        eg_score = 90 if eg and eg > 0.30 else 78 if eg and eg > 0.15 else 65 if eg and eg > 0.05 else 52 if eg and eg > 0 else 30 if eg else 50
        rg_score = 85 if rg and rg > 0.20 else 72 if rg and rg > 0.10 else 60 if rg and rg > 0.03 else 48 if rg and rg > 0 else 28 if rg else 50
        sc["growth"] = (eg_score * 0.6 + rg_score * 0.4)
        details["earnings_growth_pct"] = safe_float(eg * 100, 1) if eg else None
        details["revenue_growth_pct"] = safe_float(rg * 100, 1) if rg else None
        fpe = info.get("forwardPE")
        tpe = info.get("trailingPE")
        peg = info.get("pegRatio")
        ptb = info.get("priceToBook")
        vs = 70
        if peg: vs = 92 if peg < 1 else 78 if peg < 1.5 else 60 if peg < 2.5 else 38
        elif fpe: vs = 88 if fpe < 12 else 72 if fpe < 20 else 58 if fpe < 30 else 40 if fpe < 50 else 22
        if fpe and tpe and fpe < tpe: vs = min(100, vs + 10)
        sc["valuation"] = vs
        details["forward_pe"] = safe_float(fpe, 2) if fpe else None
        details["trailing_pe"] = safe_float(tpe, 2) if tpe else None
        details["peg_ratio"] = safe_float(peg, 2) if peg else None
        de = info.get("debtToEquity")
        cr = info.get("currentRatio")
        fcf = info.get("freeCashflow")
        pm = info.get("profitMargins")
        hs = 55
        if de is not None: hs += 20 if de < 30 else 10 if de < 60 else -10 if de < 120 else -25
        if cr is not None: hs += 18 if cr > 2.5 else 8 if cr > 1.5 else -10 if cr < 1 else 0
        if fcf and fcf > 0: hs += 12
        elif fcf and fcf < 0: hs -= 15
        if pm: hs += 10 if pm > 0.20 else 5 if pm > 0.10 else -5 if pm < 0 else 0
        sc["health"] = min(100, max(0, hs))
        details["debt_to_equity"] = safe_float(de, 2) if de else None
        details["current_ratio"] = safe_float(cr, 2) if cr else None
        details["free_cashflow_b"] = round(fcf / 1e9, 2) if fcf else None
        details["profit_margin_pct"] = safe_float(pm * 100, 1) if pm else None
        try:
            hist = yf.Ticker(ticker).history(period="6mo", auto_adjust=True, timeout=8)
            if not hist.empty and len(hist) >= 50:
                close = hist["Close"].astype(float)
                last = close.iloc[-1]
                ma50 = close.rolling(50).mean().iloc[-1]
                ma200 = close.rolling(200, min_periods=50).mean().iloc[-1]
                delta = close.diff()
                gain = delta.clip(lower=0).rolling(14).mean()
                loss = (-delta.clip(upper=0)).rolling(14).mean()
                rs = gain / loss
                rsi_v = float((100 - 100 / (1 + rs)).iloc[-1])
                ema12 = close.ewm(span=12).mean()
                ema26 = close.ewm(span=26).mean()
                macd_v = float((ema12 - ema26).iloc[-1])
                sig_v = float((ema12 - ema26).ewm(span=9).mean().iloc[-1])
                ts_score = 50
                if last > ma50: ts_score += 12
                if last > ma200: ts_score += 15
                if macd_v > sig_v: ts_score += 13
                if 40 < rsi_v < 65: ts_score += 10
                elif rsi_v > 65: ts_score += 5
                sc["technical"] = min(100, max(0, ts_score))
                details["rsi"] = safe_float(rsi_v, 1)
                details["macd_signal"] = "Bullish" if macd_v > sig_v else "Bearish"
                details["price_vs_ma50"] = safe_float((last - ma50) / ma50 * 100, 1)
            else:
                sc["technical"] = 50
        except:
            sc["technical"] = 50
        ins = info.get("heldPercentInsiders", 0) or 0
        inst = info.get("heldPercentInstitutions", 0) or 0
        ows = 50 + (20 if ins > 0.10 else 10 if ins > 0.05 else 0) + (20 if inst > 0.70 else 12 if inst > 0.50 else 0)
        sc["ownership"] = min(100, ows)
        details["insider_pct"] = safe_float(ins * 100, 1)
        details["institution_pct"] = safe_float(inst * 100, 1)
        wh = info.get("fiftyTwoWeekHigh")
        wl = info.get("fiftyTwoWeekLow")
        if wh and wl and curr and wh != wl:
            pos = (curr - wl) / (wh - wl) * 100
            pos_score = 80 if 30 < pos < 70 else 65 if 15 < pos <= 30 else 70 if 70 <= pos < 85 else 45 if pos >= 85 else 40
            sc["position"] = pos_score
            details["week52_position_pct"] = safe_float(pos, 1)
        else:
            sc["position"] = 50
            details["week52_position_pct"] = None
        details["week52_high"] = safe_float(wh) if wh else None
        details["week52_low"] = safe_float(wl) if wl else None
        sr = info.get("shortRatio", 0) or 0
        sc["short"] = 88 if sr < 1.5 else 72 if sr < 3 else 55 if sr < 5 else 35 if sr < 8 else 15
        details["short_ratio"] = safe_float(sr, 2)
        details["dividend_yield_pct"] = safe_float((info.get("dividendYield") or 0) * 100, 2)
        weights = {"analyst": 0.28, "growth": 0.20, "valuation": 0.15,
                   "health": 0.12, "technical": 0.10, "ownership": 0.08,
                   "position": 0.04, "short": 0.03}
        comp = round(sum(sc[k] * weights[k] for k in weights), 1)
        if comp >= 78: grade, gc = "Strong Buy", "green"
        elif comp >= 63: grade, gc = "Buy", "lightgreen"
        elif comp >= 48: grade, gc = "Hold", "yellow"
        elif comp >= 33: grade, gc = "Underperform", "orange"
        else: grade, gc = "Sell", "red"
        scenarios = {}
        base_upside = (upside / 100) if upside is not None else 0.08
        if curr:
            scenarios = {
                "bull": round(curr * (1 + max(base_upside * 1.5, 0.20)), 2),
                "base": round(curr * (1 + max(base_upside * 0.7, 0.05)), 2),
                "bear": round(curr * (1 - 0.15), 2),
                "label_bull": f"+{max(base_upside*150, 20):.0f}%",
                "label_base": f"+{max(base_upside*70, 5):.0f}%",
                "label_bear": "-15%",
            }
        horizon = {
            "short_term": "Bullish" if sc.get("technical", 50) > 65 else "Bearish" if sc.get("technical", 50) < 40 else "Neutral",
            "medium_term": "Bullish" if sc.get("growth", 50) > 65 and sc.get("valuation", 50) > 55 else "Bearish" if sc.get("growth", 50) < 40 else "Neutral",
            "long_term": grade if comp >= 48 else "Underperform",
        }
        return {
            "composite_score": comp, "grade": grade, "grade_color": gc,
            "components": sc, "weights": weights, "details": details,
            "scenarios": scenarios, "horizon": horizon,
            "factors": [
                {"name": "Analyst Consensus", "score": sc["analyst"], "weight": "28%", "icon": "📊"},
                {"name": "Growth Trajectory", "score": sc["growth"], "weight": "20%", "icon": "📈"},
                {"name": "Valuation (PEG)", "score": sc["valuation"], "weight": "15%", "icon": "💰"},
                {"name": "Financial Health", "score": sc["health"], "weight": "12%", "icon": "🏥"},
                {"name": "Tech Momentum", "score": sc["technical"], "weight": "10%", "icon": "⚡"},
                {"name": "Inst. Ownership", "score": sc["ownership"], "weight": "8%", "icon": "🏛️"},
                {"name": "52W Position", "score": sc["position"], "weight": "4%", "icon": "📍"},
                {"name": "Short Interest", "score": sc["short"], "weight": "3%", "icon": "🛡️"},
            ]
        }
    except Exception as e:
        return {"error": str(e)[:60]}

def _sector_performance():
    cached = cache_get("sectors")
    if cached: return cached
    result = {}
    all_s = {**GLOBAL_SECTOR_ETFS, **INDIAN_SECTOR_INDICES}
    def worker(args):
        name, ticker = args
        try:
            hist = yf.Ticker(ticker).history(period="3mo", auto_adjust=True, timeout=8)
            if hist.empty or len(hist) < 2: return
            c = hist["Close"].astype(float)
            wk = safe_float((c.iloc[-1] - c.iloc[-min(6, len(c))]) / c.iloc[-min(6, len(c))] * 100, 2)
            mo = safe_float((c.iloc[-1] - c.iloc[-min(22, len(c))]) / c.iloc[-min(22, len(c))] * 100, 2)
            qt = safe_float((c.iloc[-1] - c.iloc[0]) / c.iloc[0] * 100, 2)
            result[name] = {"week": wk, "month": mo, "quarter": qt, "price": safe_float(c.iloc[-1]),
                            "region": "India" if ".NS" in ticker or "^CNX" in ticker else "Global"}
        except: pass
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = [ex.submit(worker, item) for item in all_s.items()]
        try:
            for fut in as_completed(futures, timeout=25):
                try: fut.result()
                except: pass
        except: pass
    cache_set("sectors", result)
    return result

def _world_market_trend():
    idx = get_global_indices()
    up = sum(1 for v in idx.values() if v and v.get("change_pct", 0) > 0)
    dn = sum(1 for v in idx.values() if v and v.get("change_pct", 0) < 0)
    total = up + dn
    valid = [v["change_pct"] for v in idx.values() if v and v.get("change_pct") is not None]
    avg = round(sum(valid) / len(valid), 2) if valid else 0
    sent = "Bullish" if avg > 0.3 else "Bearish" if avg < -0.3 else "Neutral"
    vix = _fetch_one("^VIX", 6)
    vix_val = vix.get("price") if not vix.get("error") else None
    fear = "Extreme Fear" if (vix_val and vix_val > 30) else "Fear" if (vix_val and vix_val > 20) else "Greed" if (vix_val and vix_val < 15) else "Neutral"
    dxy = _fetch_one("DX-Y.NYB", 6)
    return {
        "indices": idx, "up_count": up, "down_count": dn,
        "breadth_pct": round(up / total * 100) if total else 50,
        "avg_change": avg, "sentiment": sent, "vix": vix_val, "fear_gauge": fear,
        "dxy": dxy.get("price") if not dxy.get("error") else None,
        "top_gainer": max(idx.items(), key=lambda x: x[1].get("change_pct", -999) if x[1] else -999, default=("—", {}))[0],
        "top_loser": min(idx.items(), key=lambda x: x[1].get("change_pct", 999) if x[1] else 999, default=("—", {}))[0],
    }

def _india_market_trend():
    idx = get_india_indices()
    stocks = get_india_stocks()
    usdinr = _fetch_one("USDINR=X", 5)
    up = sum(1 for v in idx.values() if v and v.get("change_pct", 0) > 0)
    dn = sum(1 for v in idx.values() if v and v.get("change_pct", 0) < 0)
    valid = [v["change_pct"] for v in idx.values() if v and v.get("change_pct") is not None]
    avg = round(sum(valid) / len(valid), 2) if valid else 0
    sent = "Bullish" if avg > 0.3 else "Bearish" if avg < -0.3 else "Sideways"
    s_up = sum(1 for v in stocks.values() if v and v.get("change_pct", 0) > 0)
    s_dn = sum(1 for v in stocks.values() if v and v.get("change_pct", 0) < 0)
    return {
        "indices": idx, "up_count": up, "down_count": dn,
        "avg_change": avg, "sentiment": sent,
        "stocks_up": s_up, "stocks_dn": s_dn,
        "usdinr": usdinr.get("price"), "inr_change": usdinr.get("change_pct"),
        "nifty": idx.get("NIFTY 50", {}), "sensex": idx.get("SENSEX", {}),
    }

def _global_india_impact():
    cached = cache_get("global_india_impact", ttl=120)
    if cached: return cached
    try:
        global_idx = get_global_indices()
        india_idx = get_india_indices()
        bonds = get_bonds()
        forex = get_forex()
        nifty = india_idx.get("NIFTY 50", {})
        sensex = india_idx.get("SENSEX", {})
        sp500 = global_idx.get("S&P 500", {})
        nasdaq = global_idx.get("NASDAQ", {})
        nikkei = global_idx.get("Nikkei 225", {})
        hangseng = global_idx.get("Hang Seng", {})
        shanghai = global_idx.get("Shanghai", {})
        gold = bonds.get("Gold", {})
        crude = bonds.get("Crude Oil (WTI)", {})
        usdinr = forex.get("USD/INR", {})
        us_10y = bonds.get("US 10Y Treasury", {})
        impacts = []
        overall_impact_score = 0
        impact_count = 0

        sp_chg = sp500.get("change_pct", 0) or 0
        if abs(sp_chg) > 0.3:
            direction = "positive" if sp_chg > 0 else "negative"
            mag = "strong" if abs(sp_chg) > 1.5 else "moderate" if abs(sp_chg) > 0.7 else "mild"
            exp_nifty = sp_chg * 0.55
            impacts.append({
                "source": "S&P 500 (USA)", "change": sp_chg, "direction": direction, "magnitude": mag,
                "sector_impact": "IT, Tech stocks most affected (TCS, Infosys, Wipro, HCL)",
                "expected_nifty_move": round(exp_nifty, 2),
                "reason": f"US markets {'rising' if sp_chg>0 else 'falling'} by {abs(sp_chg):.1f}% → Indian IT exports & FII flows {'improve' if sp_chg>0 else 'pressure'} → NIFTY likely {'+' if sp_chg>0 else ''}{exp_nifty:.1f}%",
                "icon": "🇺🇸", "confidence": "High"
            })
            overall_impact_score += exp_nifty
            impact_count += 1

        nq_chg = nasdaq.get("change_pct", 0) or 0
        if abs(nq_chg) > 0.3:
            exp = nq_chg * 0.45
            impacts.append({
                "source": "NASDAQ (Tech)", "change": nq_chg,
                "direction": "positive" if nq_chg > 0 else "negative",
                "magnitude": "strong" if abs(nq_chg) > 2 else "moderate",
                "sector_impact": "NIFTY IT index direct correlation — Infosys, Wipro, HCL Tech",
                "expected_nifty_move": round(exp, 2),
                "reason": f"NASDAQ {'up' if nq_chg>0 else 'down'} {abs(nq_chg):.1f}% → NIFTY IT likely {'+' if exp>0 else ''}{exp:.1f}%",
                "icon": "💻", "confidence": "High"
            })

        nk_chg = nikkei.get("change_pct", 0) or 0
        if abs(nk_chg) > 0.4:
            exp = nk_chg * 0.35
            impacts.append({
                "source": "Nikkei 225 (Japan)", "change": nk_chg,
                "direction": "positive" if nk_chg > 0 else "negative",
                "magnitude": "moderate" if abs(nk_chg) > 1 else "mild",
                "sector_impact": "Auto sector — Maruti, Tata Motors (Japan supply chain)",
                "expected_nifty_move": round(exp, 2),
                "reason": f"Asia sentiment {'positive' if nk_chg>0 else 'negative'} — Japanese yen & supply chain {'support' if nk_chg>0 else 'pressure'} Indian auto sector",
                "icon": "🇯🇵", "confidence": "Moderate"
            })

        hs_chg = hangseng.get("change_pct", 0) or 0
        sh_chg = shanghai.get("change_pct", 0) or 0
        china_avg = ((hs_chg or 0) + (sh_chg or 0)) / 2
        if abs(china_avg) > 0.4:
            exp = china_avg * 0.25
            impacts.append({
                "source": "China Markets (HK + Shanghai)", "change": round(china_avg, 2),
                "direction": "positive" if china_avg > 0 else "negative",
                "magnitude": "moderate" if abs(china_avg) > 1 else "mild",
                "sector_impact": "Metals (Tata Steel, JSW) — China demand drives commodity prices",
                "expected_nifty_move": round(exp, 2),
                "reason": f"China {'growing' if china_avg>0 else 'slowing'} → commodity demand {'up' if china_avg>0 else 'down'} → Indian metal stocks {'benefit' if china_avg>0 else 'suffer'}",
                "icon": "🇨🇳", "confidence": "Moderate"
            })

        crude_chg = crude.get("change_pct", 0) or 0
        if abs(crude_chg) > 0.5:
            exp = -crude_chg * 0.3
            impacts.append({
                "source": "Crude Oil (WTI)", "change": crude_chg,
                "direction": "negative" if crude_chg > 0 else "positive",
                "magnitude": "high" if abs(crude_chg) > 2 else "moderate",
                "sector_impact": "Oil & Gas (ONGC +), Aviation (IndiGo -), FMCG, Paint stocks affected",
                "expected_nifty_move": round(exp, 2),
                "reason": f"Crude {'rising' if crude_chg>0 else 'falling'} {abs(crude_chg):.1f}% → India imports 85% oil → {'inflation risk, CAD widens' if crude_chg>0 else 'inflation eases, CAD improves'}",
                "icon": "🛢️", "confidence": "High"
            })
            overall_impact_score += exp
            impact_count += 1

        gold_chg = gold.get("change_pct", 0) or 0
        if abs(gold_chg) > 0.5:
            impacts.append({
                "source": "Gold Price", "change": gold_chg,
                "direction": "mixed" if gold_chg > 0 else "mild positive",
                "magnitude": "mild",
                "sector_impact": "Titan, Kalyan Jewellers, HDFC Gold Fund — Gold ETFs",
                "expected_nifty_move": round(gold_chg * 0.08, 2),
                "reason": f"Gold {'up' if gold_chg>0 else 'down'} {abs(gold_chg):.1f}% → Jewelry stocks {'benefit' if gold_chg>0 else 'pressure'} — India #1 gold consumer globally",
                "icon": "🥇", "confidence": "Moderate"
            })

        usdinr_chg = usdinr.get("change_pct", 0) or 0
        if abs(usdinr_chg) > 0.2:
            exp = -usdinr_chg * 0.4
            impacts.append({
                "source": "USD/INR (Rupee)", "change": usdinr_chg,
                "direction": "negative" if usdinr_chg > 0 else "positive",
                "magnitude": "high" if abs(usdinr_chg) > 0.7 else "moderate",
                "sector_impact": "IT exporters benefit (TCS, Infy) when INR weak; Importers suffer",
                "expected_nifty_move": round(exp, 2),
                "reason": f"INR {'weakening' if usdinr_chg>0 else 'strengthening'} vs USD → {'IT export earnings higher, but FII outflows likely' if usdinr_chg>0 else 'FII inflows improve, import costs fall'}",
                "icon": "💱", "confidence": "High"
            })
            overall_impact_score += exp
            impact_count += 1

        us10y_chg = us_10y.get("change_pct", 0) or 0
        us10y_price = us_10y.get("price", 4.0) or 4.0
        if abs(us10y_chg) > 0.5 or us10y_price > 4.5:
            exp = -us10y_chg * 0.35
            impacts.append({
                "source": "US 10Y Treasury Yield", "change": us10y_chg,
                "direction": "negative" if us10y_chg > 0 else "positive",
                "magnitude": "high" if us10y_price > 5 else "moderate" if us10y_price > 4.5 else "mild",
                "sector_impact": "Banking, Real Estate most sensitive — HDFC Bank, Bajaj Finance",
                "expected_nifty_move": round(exp, 2),
                "reason": f"US yields {'rising' if us10y_chg>0 else 'falling'} → {'FII sell India bonds & equity for safe US returns' if us10y_chg>0 else 'FII return to EM markets like India → bullish'}",
                "icon": "🏛️", "confidence": "High"
            })
            overall_impact_score += exp
            impact_count += 1

        avg_impact = overall_impact_score / impact_count if impact_count > 0 else 0
        overall = {
            "net_expected_nifty_move": round(avg_impact, 2),
            "overall_signal": "Bullish" if avg_impact > 0.3 else "Bearish" if avg_impact < -0.3 else "Neutral",
            "nifty_current": nifty.get("price"),
            "nifty_change": nifty.get("change_pct"),
            "sensex_current": sensex.get("price"),
            "key_risks": [],
            "key_tailwinds": [],
        }
        for imp in impacts:
            if imp["direction"] in ["negative"]:
                overall["key_risks"].append(f"{imp['icon']} {imp['source']}: {imp['reason'][:80]}")
            elif imp["direction"] in ["positive"]:
                overall["key_tailwinds"].append(f"{imp['icon']} {imp['source']}: {imp['reason'][:80]}")
        result = {"impacts": impacts, "overall": overall, "ts": time.time()}
        cache_set("global_india_impact", result)
        return result
    except Exception as e:
        return {"impacts": [], "overall": {"net_expected_nifty_move": 0, "overall_signal": "Neutral"}, "error": str(e)}

def _scrape_news(query=None):
    cache_key = f"news_{query}" if query else "news_main"
    cached = cache_get(cache_key, ttl=30)
    if cached: return cached
    news = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if query:
        sources = [
            (f"https://finance.yahoo.com/search/?q={query.replace(' ','+')+'+stock'}", "Yahoo Finance", "h3"),
            (f"https://economictimes.indiatimes.com/markets/stocks/news?q={query.replace(' ','+')}","Economic Times","h3"),
        ]
    else:
        sources = [
            ("https://finance.yahoo.com/news/", "Yahoo Finance", "h3"),
            ("https://economictimes.indiatimes.com/markets", "Economic Times", "h3"),
            ("https://www.moneycontrol.com/news/business/markets/", "Moneycontrol", "h2"),
            ("https://www.livemint.com/market/stock-market-news", "LiveMint", "h2"),
            ("https://www.reuters.com/finance/markets/", "Reuters", "h3"),
            ("https://www.cnbctv18.com/market/", "CNBC TV18", "h3"),
        ]
    now_str = datetime.now().strftime("%H:%M")
    kw = ["stock","market","nifty","sensex","share","invest","rupee","rbi","sebi",
          "ipo","fund","trade","economy","gdp","rate","oil","gold","bitcoin","crypto",
          "bank","finance","profit","revenue","quarter","earning","index","rally","bull","bear",
          "nasdaq","sp500","dow","fed","inflation","fiscal","budget","export","import"]
    for url, source, tag in sources:
        try:
            r = req_lib.get(url, headers=headers, timeout=7)
            soup = BeautifulSoup(r.text, "html.parser")
            count = 0
            for elem in soup.find_all(tag, limit=15):
                text = elem.get_text(strip=True)
                if len(text) < 25 or len(text) > 300: continue
                if not query and not any(k in text.lower() for k in kw): continue
                a_tag = elem.find("a") or (elem.parent and elem.parent.find("a"))
                href = "#"
                if a_tag and a_tag.get("href"):
                    href = a_tag["href"]
                    if href.startswith("/"):
                        base = url.split("/")[0] + "//" + url.split("/")[2]
                        href = base + href
                news.append({"title": text, "source": source, "url": href, "time": now_str})
                count += 1
                if count >= 8: break
        except: pass
    seen_titles = set()
    unique_news = []
    for item in news:
        key = item["title"][:50].lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            unique_news.append(item)
    import random
    random.shuffle(unique_news)
    final = unique_news[:60]
    cache_set(cache_key, final)
    return final

def _search_stock(query):
    q = query.strip().upper()
    results = []
    seen = set()
    all_known = {**POPULAR_INDIAN_STOCKS, **POPULAR_GLOBAL_STOCKS}
    for name, ticker in all_known.items():
        base = re.sub(r'\..+$', '', ticker)
        if q in name.upper() or q in base or q in ticker.upper():
            if ticker not in seen:
                seen.add(ticker)
                results.append({"name": name, "ticker": ticker})
    for suffix in ["", ".NS", ".BO", "-USD"]:
        attempt = q + suffix
        if attempt not in seen:
            try:
                t = yf.Ticker(attempt)
                info = t.info or {}
                nm = info.get("longName") or info.get("shortName")
                if nm and info.get("regularMarketPrice"):
                    seen.add(attempt)
                    results.append({"name": nm, "ticker": attempt})
                    break
            except: pass
    if not results:
        results.append({"name": q, "ticker": q})
    return results[:8]


# ═══════════════════════════════════════════════════════
#  🤖 AGENTIC AI — V58-STYLE DEEP STOCK ANALYSIS ENGINE
#  Mimics the Trend Engine V58 Batch Report format:
#  Stage 1: Live Data Gathering → Stage 2: Deep Analysis
# ═══════════════════════════════════════════════════════

def _build_v58_context(ticker):
    """
    Agentic Stage 1: Gather all live data and compute V58-style metrics.
    Returns a structured dict matching the V58 batch report format.
    """
    try:
        info = yf.Ticker(ticker).info or {}
        hist_1y = yf.Ticker(ticker).history(period="1y", auto_adjust=True, timeout=12)
        hist_3m = yf.Ticker(ticker).history(period="3mo", auto_adjust=True, timeout=10)

        # ── Price & Basic
        curr = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        prev_close = safe_float(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        change_pct = round((curr - prev_close) / prev_close * 100, 2) if curr and prev_close and prev_close != 0 else 0.0

        # ── Fundamentals
        roe = safe_float((info.get("returnOnEquity") or 0) * 100, 2)
        eps_growth = safe_float((info.get("earningsGrowth") or 0) * 100, 2)
        rev_growth = safe_float((info.get("revenueGrowth") or 0) * 100, 2)
        peg = safe_float(info.get("pegRatio"))
        pe_ttm = safe_float(info.get("trailingPE"))
        forward_pe = safe_float(info.get("forwardPE"))
        profit_margin = safe_float((info.get("profitMargins") or 0) * 100, 2)
        debt_equity = safe_float(info.get("debtToEquity"))
        current_ratio = safe_float(info.get("currentRatio"))
        insider_pct = safe_float((info.get("heldPercentInsiders") or 0) * 100, 2)
        inst_pct = safe_float((info.get("heldPercentInstitutions") or 0) * 100, 2)
        short_ratio = safe_float(info.get("shortRatio"))
        beta = safe_float(info.get("beta"))
        fcf = info.get("freeCashflow")
        fcf_cr = round(fcf / 1e7, 2) if fcf else None  # Convert to Crores

        # ── Piotroski F-Score (simplified)
        piotroski = 5  # default
        p_score = 0
        if roe and roe > 0: p_score += 1
        if fcf and fcf > 0: p_score += 1
        if eps_growth and eps_growth > 0: p_score += 1
        if rev_growth and rev_growth > 0: p_score += 1
        if debt_equity is not None and debt_equity < 100: p_score += 1
        if current_ratio and current_ratio > 1: p_score += 1
        if profit_margin and profit_margin > 5: p_score += 1
        if inst_pct and inst_pct > 30: p_score += 1
        if beta and beta < 1.5: p_score += 1
        piotroski = min(9, max(1, p_score))

        # ── Technicals
        ta_data = {}
        adx_val = 20.0
        sma200_dist = None
        momentum_score = 50
        rsi_val = 50.0
        w52_high = safe_float(info.get("fiftyTwoWeekHigh"))
        w52_low = safe_float(info.get("fiftyTwoWeekLow"))
        dist_52w_high = round((curr - w52_high) / w52_high * 100, 2) if curr and w52_high else None
        dist_52w_low = round((curr - w52_low) / w52_low * 100, 2) if curr and w52_low else None
        pivot_dist = None
        pivot_r1 = pivot_r2 = pivot_r3 = None
        pivot_s1 = pivot_s2 = pivot_s3 = None

        if not hist_1y.empty and len(hist_1y) >= 30:
            close = hist_1y["Close"].astype(float)
            high_s = hist_1y["High"].astype(float)
            low_s = hist_1y["Low"].astype(float)

            ma200 = float(close.rolling(200, min_periods=50).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma20 = float(close.rolling(20).mean().iloc[-1])
            sma200_dist = round((curr - ma200) / ma200 * 100, 2) if curr and ma200 else None

            # RSI
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            rsi_val = float((100 - 100 / (1 + rs)).iloc[-1])

            # MACD
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd_v = float((ema12 - ema26).iloc[-1])
            sig_v = float((ema12 - ema26).ewm(span=9).mean().iloc[-1])

            # ADX
            try:
                plus_dm = high_s.diff().clip(lower=0)
                minus_dm = (-low_s.diff()).clip(lower=0)
                tr = pd.DataFrame({'hl': high_s - low_s, 'hc': (high_s - close.shift()).abs(), 'lc': (low_s - close.shift()).abs()}).max(axis=1)
                atr14 = tr.rolling(14).mean()
                plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
                minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
                dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
                adx_val = float(dx.rolling(14).mean().iloc[-1])
            except: pass

            # Momentum score
            ms = 50
            if curr and curr > ma20: ms += 8
            if curr and curr > ma50: ms += 8
            if curr and curr > ma200: ms += 9
            if macd_v > sig_v: ms += 10
            if 30 < rsi_val < 70: ms += 5
            if rsi_val > 50: ms += 5
            if not hist_1y["Volume"].empty:
                vol_ratio = float(hist_1y["Volume"].iloc[-1]) / (float(hist_1y["Volume"].rolling(20).mean().iloc[-1]) + 1e-10)
                if vol_ratio > 1.2: ms += 5
            momentum_score = min(100, max(0, ms))

            # Pivot Points (using last 5 days high/low/close average)
            if len(hist_1y) >= 5:
                ph = float(high_s.tail(5).max())
                pl = float(low_s.tail(5).min())
                pc = float(close.iloc[-1])
                pp = (ph + pl + pc) / 3
                pivot_r1 = round((2 * pp - pl - curr) / curr * 100, 2) if curr else None
                pivot_r2 = round((pp + (ph - pl) - curr) / curr * 100, 2) if curr else None
                pivot_r3 = round((ph + 2 * (pp - pl) - curr) / curr * 100, 2) if curr else None
                pivot_s1 = round((curr - (2 * pp - ph)) / curr * 100, 2) if curr else None
                pivot_s2 = round((curr - (pp - (ph - pl))) / curr * 100, 2) if curr else None
                pivot_s3 = round((curr - (pl - 2 * (ph - pp))) / curr * 100, 2) if curr else None
                pivot_dist = round((curr - pp) / curr * 100, 2) if curr else None

            ta_data = {
                "ma20": safe_float(ma20), "ma50": safe_float(ma50), "ma200": safe_float(ma200),
                "macd_bullish": macd_v > sig_v, "macd_val": safe_float(macd_v, 4), "signal_val": safe_float(sig_v, 4)
            }

        # ── Cash Flow
        try:
            cf = yf.Ticker(ticker).cashflow
            if cf is not None and not cf.empty:
                ops = safe_float(cf.iloc[:, 0].get("Operating Cash Flow", cf.iloc[:, 0].get("Total Cash From Operating Activities", 0)) / 1e7, 2)
                inv = safe_float(cf.iloc[:, 0].get("Investing Cash Flow", cf.iloc[:, 0].get("Total Cashflows From Investing Activities", 0)) / 1e7, 2)
                fin = safe_float(cf.iloc[:, 0].get("Financing Cash Flow", cf.iloc[:, 0].get("Total Cash From Financing Activities", 0)) / 1e7, 2)
                net_cf = round((ops or 0) + (inv or 0) + (fin or 0), 2)
            else:
                ops = inv = fin = net_cf = None
        except:
            ops = inv = fin = net_cf = None

        # ── Local Score (V58 style: 0-100)
        local_score = 0
        if sma200_dist and sma200_dist > 0: local_score += 10
        elif sma200_dist and sma200_dist < -15: local_score -= 8
        if rsi_val > 60: local_score += 12
        elif rsi_val < 35: local_score -= 5
        if momentum_score > 70: local_score += 15
        elif momentum_score > 55: local_score += 8
        if adx_val > 25: local_score += 10
        if dist_52w_high and dist_52w_high > -10: local_score += 15
        elif dist_52w_high and dist_52w_high < -30: local_score -= 10
        if dist_52w_low and dist_52w_low > 50: local_score += 10
        if eps_growth and eps_growth > 20: local_score += 10
        elif eps_growth and eps_growth > 0: local_score += 5
        if rev_growth and rev_growth > 10: local_score += 8
        if piotroski >= 7: local_score += 8
        elif piotroski <= 3: local_score -= 5
        if pivot_dist and abs(pivot_dist) < 3: local_score += 5
        local_score = min(100, max(0, local_score + 20))  # base of 20

        # ── Verdict
        if local_score >= 90: verdict = "STRONG BREAKOUT"
        elif local_score >= 70: verdict = "ACCUMULATE"
        elif local_score >= 45: verdict = "HOLD"
        elif local_score >= 25: verdict = "UNDERPERFORM"
        else: verdict = "AVOID"

        # ── Leverage delta (EPS growth vs Rev growth gap)
        leverage_delta = round((eps_growth or 0) - (rev_growth or 0), 2)

        # ── Analyst data
        analyst_target = safe_float(info.get("targetMeanPrice"))
        analyst_upside = round((analyst_target - curr) / curr * 100, 2) if analyst_target and curr else None
        analyst_rec = info.get("recommendationKey", "N/A")
        analyst_count = info.get("numberOfAnalystOpinions", 0) or 0

        return {
            "ticker": info.get("longName") or ticker,
            "nse": ticker,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "price": curr,
            "change_pct": change_pct,
            "roe": roe,
            "piotroski": piotroski,
            "eps_growth": eps_growth,
            "rev_growth": rev_growth,
            "peg": peg,
            "pe_ttm": pe_ttm,
            "forward_pe": forward_pe,
            "rsi": safe_float(rsi_val, 2),
            "momentum_score": momentum_score,
            "adx": safe_float(adx_val, 2),
            "sma200_dist": sma200_dist,
            "leverage_delta": leverage_delta,
            "dist_52w_high": dist_52w_high,
            "dist_52w_low": dist_52w_low,
            "w52_high": w52_high,
            "w52_low": w52_low,
            "beta": beta,
            "insider_pct": insider_pct,
            "inst_pct": inst_pct,
            "short_ratio": short_ratio,
            "profit_margin": profit_margin,
            "debt_equity": debt_equity,
            "current_ratio": current_ratio,
            "pivot_dist": pivot_dist,
            "pivot_r1": pivot_r1, "pivot_r2": pivot_r2, "pivot_r3": pivot_r3,
            "pivot_s1": pivot_s1, "pivot_s2": pivot_s2, "pivot_s3": pivot_s3,
            "cash_ops": ops, "cash_invest": inv, "cash_fin": fin, "net_cash": net_cf,
            "fcf_cr": fcf_cr,
            "analyst_target": analyst_target,
            "analyst_upside": analyst_upside,
            "analyst_rec": analyst_rec,
            "analyst_count": analyst_count,
            "local_score": local_score,
            "verdict": verdict,
            "ta": ta_data,
            "summary": (info.get("longBusinessSummary") or "")[:400],
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", ""),
            "dividend_yield": safe_float((info.get("dividendYield") or 0) * 100, 2),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker, "local_score": 50, "verdict": "HOLD"}


def _agentic_v58_analysis(ticker, question, language_hint="english"):
    """
    Agentic AI: Two-stage analysis engine.
    Stage 1 → gather live data (V58 format)
    Stage 2 → deep AI analysis with buy/sell/hold + future prediction
    Returns formatted markdown response.
    """
    # ── STAGE 1: Gather Data
    ctx = _build_v58_context(ticker)

    if ctx.get("error") and not ctx.get("price"):
        return f"⚠️ Could not fetch data for **{ticker}**. Please check the ticker symbol and try again."

    # ── Format Stage 1 block
    stage1_block = f"""
=== STAGE 1: LIVE DATA GATHERING (V58 Titanium — Agentic Engine) ===
Ticker       : {ctx.get('ticker', ticker)}
NSE/Exchange : {ctx.get('nse', ticker)}
Sector       : {ctx.get('sector', 'N/A')}
Industry     : {ctx.get('industry', 'N/A')}
Current Price: ₹{ctx.get('price', 'N/A')} {ctx.get('currency','')}  ({'+' if (ctx.get('change_pct') or 0) >= 0 else ''}{ctx.get('change_pct', 0)}%)

ROE          : {ctx.get('roe', 'N/A')}%
Piotroski    : {ctx.get('piotroski', 'N/A')} / 9
EPS Growth   : {ctx.get('eps_growth', 'N/A')}%
Revenue Growth: {ctx.get('rev_growth', 'N/A')}%
PEG          : {ctx.get('peg', 'N/A')}
PE TTM       : {ctx.get('pe_ttm', 'N/A')}
Forward PE   : {ctx.get('forward_pe', 'N/A')}
Profit Margin: {ctx.get('profit_margin', 'N/A')}%
Debt/Equity  : {ctx.get('debt_equity', 'N/A')}

RSI          : {ctx.get('rsi', 'N/A')}
Momentum Score: {ctx.get('momentum_score', 'N/A')}
ADX          : {ctx.get('adx', 'N/A')}
SMA200 Dist  : {ctx.get('sma200_dist', 'N/A')}%
Leverage Delta: {ctx.get('leverage_delta', 'N/A')}% (EPS vs Rev gap)
52W High Dist: {ctx.get('dist_52w_high', 'N/A')}%
52W Low Dist : {ctx.get('dist_52w_low', 'N/A')}%
52W High     : ₹{ctx.get('w52_high', 'N/A')} | 52W Low: ₹{ctx.get('w52_low', 'N/A')}

Insider %    : {ctx.get('insider_pct', 'N/A')}% | Inst %: {ctx.get('inst_pct', 'N/A')}%
Short Ratio  : {ctx.get('short_ratio', 'N/A')}
Beta         : {ctx.get('beta', 'N/A')}
Dividend Yield: {ctx.get('dividend_yield', 'N/A')}%

Pivot Dist   : {ctx.get('pivot_dist', 'N/A')}%
Pivot R1     : {ctx.get('pivot_r1', 'N/A')}% | R2: {ctx.get('pivot_r2', 'N/A')}% | R3: {ctx.get('pivot_r3', 'N/A')}%
Pivot S1     : {ctx.get('pivot_s1', 'N/A')}% | S2: {ctx.get('pivot_s2', 'N/A')}% | S3: {ctx.get('pivot_s3', 'N/A')}%

Cash Ops Annual  : ₹{ctx.get('cash_ops', 'N/A')} Cr
Cash Invest Annual: ₹{ctx.get('cash_invest', 'N/A')} Cr
Cash Fin Annual  : ₹{ctx.get('cash_fin', 'N/A')} Cr
Net Cash Flow    : ₹{ctx.get('net_cash', 'N/A')} Cr

Analyst Target   : ₹{ctx.get('analyst_target', 'N/A')} | Upside: {ctx.get('analyst_upside', 'N/A')}%
Analyst Reco     : {ctx.get('analyst_rec', 'N/A')} ({ctx.get('analyst_count', 0)} analysts)

Local Score  : {ctx.get('local_score', 50)} → {ctx.get('verdict', 'HOLD')}
Business     : {ctx.get('summary', 'N/A')[:200]}
"""

    # ── Build AI prompt for Stage 2 deep analysis
    system_prompt = f"""You are FinVision AI v6 — an expert quantitative analyst trained on the V58 Trend Engine methodology.

You perform TWO-STAGE AGENTIC ANALYSIS exactly like a professional quant report:

**STAGE 2 FORMAT (MANDATORY):**

### **Quant Assessment: [Company Name] ([Ticker])**
**Core Thesis:** [2-3 sentence overall view with risk/reward stance]

---

### **1. Forensic Financial & Operational Health**
- Growth Sustainability (quality of EPS vs Revenue growth)
- Margin & Cash Flow Quality (is OCF positive? FCF analysis)
- Institutional & Promoter Sentiment

### **2. Valuation & Relative Performance**
- Is it cheap for a reason or genuinely undervalued?
- P/E, PEG, Forward PE context
- Sector/index relative performance

### **3. Technical & Momentum Positioning**
- RSI, ADX, Momentum Score interpretation
- Pivot Levels with EXACT price targets:
  * Support levels (S1, S2, S3) with % and estimated price
  * Resistance levels (R1, R2, R3) with % and estimated price
- 52-week range positioning

### **4. 🔮 Future Prediction & Price Targets (12-Month)**
- **Bull Case:** Specific price target + % upside + conditions required
- **Base Case:** Most likely price target + % move + key assumptions
- **Bear Case:** Downside price target + % risk + triggers
- **Timeline:** Short-term (1 month), Medium-term (3 months), Long-term (12 months) outlook

### **5. Forward-Looking Integration & Verdict**
- Key catalysts to watch (earnings, sector trends, macro factors)
- Key risks (specific, not generic)
- Final recommendation with conviction level

**CRITICAL RULES:**
- ALWAYS reply in the SAME language as the user's question. Hindi→Hindi, English→English, Hinglish→Hinglish
- ALWAYS include specific rupee/dollar price targets in the Future Prediction section
- ALWAYS give a clear BUY / HOLD / SELL / ACCUMULATE verdict with stop-loss levels
- Use emojis for visual impact (🟢 bullish, 🔴 bearish, 🟡 neutral, 📊 data, 🎯 target, ⚠️ risk)
- End EVERY response with: ⚠️ **Disclaimer:** Educational only. Consult SEBI-registered advisor before investing.
"""

    user_msg = f"""
{stage1_block}

=== USER QUESTION ===
{question}

=== TASK ===
Perform Stage 2 Deep Analysis using the V58 methodology above. 
Include specific price targets for Bull/Base/Bear cases.
Current price is ₹{ctx.get('price', 'N/A')}.
Give verdict: {ctx.get('verdict', 'HOLD')} (Local Score: {ctx.get('local_score', 50)}/100)
"""

    # ── Call AI
    # 1. Try Gemini
    if GEMINI_AVAILABLE:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_msg}]}],
                "generationConfig": {"maxOutputTokens": 2500, "temperature": 0.65}
            }
            resp = req_lib.post(url, json=payload, timeout=30)
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if text and len(text) > 100:
                return {"answer": text, "source": "Gemini (Agentic V58)", "stage1": stage1_block}
        except Exception as e:
            pass

    # 2. Try Claude/Anthropic
    if AI_AVAILABLE and _anthropic_lib:
        try:
            client = _anthropic_lib.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            return {"answer": msg.content[0].text, "source": "Claude (Agentic V58)", "stage1": stage1_block}
        except Exception as e:
            pass

    # 3. Fallback — return structured data without AI narrative
    price = ctx.get("price", 0) or 0
    score = ctx.get("local_score", 50)
    verdict = ctx.get("verdict", "HOLD")
    rsi = ctx.get("rsi", 50) or 50
    adx = ctx.get("adx", 20) or 20
    eps_g = ctx.get("eps_growth", 0) or 0
    rev_g = ctx.get("rev_growth", 0) or 0
    sma200 = ctx.get("sma200_dist", 0) or 0

    # Determine color/emoji
    if score >= 85: verdict_emoji = "🟢🚀"
    elif score >= 65: verdict_emoji = "🟢"
    elif score >= 45: verdict_emoji = "🟡"
    else: verdict_emoji = "🔴"

    # Compute basic price targets
    upside_pct = ctx.get("analyst_upside") or (15 if score >= 70 else 5 if score >= 50 else -10)
    bull_target = round(price * (1 + max(upside_pct / 100 * 1.5, 0.20)), 2) if price else "N/A"
    base_target = round(price * (1 + max(upside_pct / 100 * 0.7, 0.05)), 2) if price else "N/A"
    bear_target = round(price * 0.85, 2) if price else "N/A"

    fallback = f"""### **Quant Assessment: {ctx.get('ticker', ticker)} — Agentic V58**

**Core Thesis:** {verdict_emoji} Local Score **{score}/100** → **{verdict}**
{'Strong technical momentum with positive fundamentals.' if score >= 70 else 'Caution warranted — mixed signals across fundamental and technical factors.' if score >= 45 else 'Bearish structure — multiple red flags in fundamentals and technicals.'}

---

### **📊 Stage 1 Data Summary**
- **Price:** ₹{price} | **RSI:** {rsi} {'🔴 Overbought' if rsi > 70 else '🟢 Oversold' if rsi < 30 else '🟡 Neutral'}
- **ADX:** {adx} {'(Strong Trend)' if adx > 25 else '(Weak/No Trend)'}
- **SMA200 Distance:** {sma200}% {'🟢 Above SMA200' if sma200 > 0 else '🔴 Below SMA200'}
- **EPS Growth:** {eps_g}% | **Revenue Growth:** {rev_g}%
- **Piotroski Score:** {ctx.get('piotroski', 5)}/9

### **🔮 Future Prediction (12-Month)**
| Scenario | Target | Move |
|---|---|---|
| 🟢 Bull Case | ₹{bull_target} | +{round(max(upside_pct*1.5, 20), 1)}% |
| 🟡 Base Case | ₹{base_target} | +{round(max(upside_pct*0.7, 5), 1)}% |
| 🔴 Bear Case | ₹{bear_target} | -15% |

### **🎯 Key Levels**
- **Support:** S1 at {ctx.get('pivot_s1', 'N/A')}% | S2 at {ctx.get('pivot_s2', 'N/A')}%
- **Resistance:** R1 at {ctx.get('pivot_r1', 'N/A')}% | R2 at {ctx.get('pivot_r2', 'N/A')}%
- **52W Range:** ₹{ctx.get('w52_low', 'N/A')} — ₹{ctx.get('w52_high', 'N/A')}

### **⚡ Verdict: {verdict}**
{'Add AI API key (Gemini/Anthropic) in app.py for full V58-style narrative analysis.' if not GEMINI_AVAILABLE and not AI_AVAILABLE else 'AI request failed — check API keys in app.py'}

⚠️ **Disclaimer:** Educational only. Consult SEBI-registered advisor before investing."""

    return {"answer": fallback, "source": "V58 Engine (No AI Key)", "stage1": stage1_block}


def _ai_chat(question):
    """
    Enhanced chat handler — routes stock queries to Agentic V58 engine,
    market/general queries to standard AI handler.
    """
    q_up = question.upper()

    # ── Step 1: Detect ticker in question
    ticker_found = None
    all_stocks = {**POPULAR_INDIAN_STOCKS, **POPULAR_GLOBAL_STOCKS}

    # Check known stocks by name
    for name, ticker in all_stocks.items():
        if name.upper() in q_up:
            ticker_found = ticker
            break

    # Check by ticker symbol in text
    if not ticker_found:
        words = re.findall(r'\b([A-Z]{2,10}(?:\.NS|\.BO|\.KS)?)\b', q_up)
        skip = {"THE","AND","FOR","BUY","SELL","HOW","WHY","WHAT","WHICH","BEST","TOP",
                "NSE","BSE","NIFTY","MARKET","STOCK","PRICE","TODAY","HINDI","ENGLISH",
                "ANALYSIS","FUTURE","OUTLOOK","VS","OR","AI","CHAT","TELL","GIVE","SHOW"}
        for w in words:
            if w not in skip:
                # Check known tickers first
                for name, t in all_stocks.items():
                    base = re.sub(r'\..+$', '', t)
                    if w == base or w == t.upper():
                        ticker_found = t
                        break
                if ticker_found: break
                # Try yfinance lookup
                for suf in ["", ".NS", ".BO"]:
                    try:
                        info = yf.Ticker(w + suf).info or {}
                        if info.get("regularMarketPrice") or info.get("currentPrice"):
                            ticker_found = w + suf
                            break
                    except: pass
                if ticker_found: break

    # ── Step 2: If stock detected → Agentic V58 analysis
    is_stock_query = ticker_found and any(kw in q_up for kw in [
        "ANALYSIS", "FUTURE", "OUTLOOK", "TARGET", "BUY", "SELL", "HOLD",
        "INVEST", "PRICE", "FORECAST", "PREDICT", "SCORE", "REVIEW",
        "KAISE", "KAISA", "BATAO", "DEKHO", "KYA", "HAI", "HO", "CHAHIYE",
        "WORTH", "GOOD", "BAD", "STRONG", "WEAK", "BREAKOUT", "MOMENTUM"
    ])

    # If just the ticker name with no other context, also do full analysis
    if ticker_found and not is_stock_query:
        q_words = q_up.split()
        ticker_base = re.sub(r'\..+$', '', ticker_found).upper()
        if ticker_base in q_words or any(n.upper() in q_up for n, t in all_stocks.items() if t == ticker_found):
            is_stock_query = True

    if ticker_found and is_stock_query:
        return _agentic_v58_analysis(ticker_found, question)

    # ── Step 3: Market/global/general queries → standard AI
    q_low = question.lower()
    extra_context = ""

    if any(w in q_low for w in ["world","global","market today","aaj ka","global market"]):
        try:
            wt = _world_market_trend()
            extra_context += f"\n=== GLOBAL MARKET ===\nSentiment: {wt['sentiment']} | Avg: {wt['avg_change']}%\nVIX: {wt['vix']} | Fear: {wt['fear_gauge']}\n"
        except: pass

    if any(w in q_low for w in ["india","nifty","sensex","indian market","impact"]):
        try:
            it = _india_market_trend()
            imp = _global_india_impact()
            extra_context += f"\n=== INDIA MARKET ===\nSentiment: {it['sentiment']} | Avg: {it['avg_change']}%\nNIFTY: {it['nifty'].get('price')} ({it['nifty'].get('change_pct')}%)\nGlobal Impact Signal: {imp['overall'].get('overall_signal')}\n"
        except: pass

    if ticker_found and not is_stock_query:
        # Fetch basic data even for non-analysis stock queries
        q_d = _fetch_one(ticker_found)
        extra_context += f"\n=== {ticker_found} LIVE PRICE ===\nPrice: {q_d.get('price')} | Change: {q_d.get('change_pct')}%\n"

    system_prompt = (
        "You are FinVision AI v6, expert financial analyst for Indian & global markets. "
        "Live market data provided. "
        "CRITICAL: Reply in SAME language as user. Hindi→Hindi. English→English. Hinglish→Hinglish. "
        "Give structured, insightful analysis. For market queries include global→India impact assessment. "
        "End with: ⚠️ Disclaimer: Educational only. SEBI-registered advisor se consult karein."
    )

    user_content = f"{extra_context}\n\nUser: {question}"

    # Try Gemini
    if GEMINI_AVAILABLE:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_content}]}],
                "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.7}
            }
            resp = req_lib.post(url, json=payload, timeout=20)
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if text:
                return {"answer": text, "source": "Gemini"}
        except Exception as e:
            pass

    # Try Claude
    if AI_AVAILABLE and _anthropic_lib:
        try:
            client = _anthropic_lib.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            return {"answer": msg.content[0].text, "source": "Claude"}
        except Exception as e:
            pass

    # Fallback
    parts = [f"📊 **{question}**\n"]
    if extra_context:
        parts.append(f"```\n{extra_context[:800]}\n```\n")
    if not GEMINI_AVAILABLE and not AI_AVAILABLE:
        parts.append("\n⚠️ *No AI key configured. Open app.py and add GEMINI_API_KEY or ANTHROPIC_API_KEY at the top.*")
    else:
        parts.append("\n⚠️ *AI request failed. Check your API keys in app.py*")
    return {"answer": "".join(parts), "source": "fallback"}


# ─── FLASK ROUTES ───
@app.route("/")
def index():
    if not DEPS_OK:
        return (
            "<html><body style='font-family:monospace;background:#020509;color:#c8dff0;padding:2rem'>"
            "<h2 style='color:#ff2244'>⚠️ Missing packages</h2>"
            "<p>Run: <code>pip install flask yfinance pandas numpy requests beautifulsoup4 anthropic lxml</code></p>"
            f"<p style='color:#ff2244'>Error: {MISSING}</p></body></html>"
        )
    return send_from_directory(".", "index.html")

@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "ai_gemini": GEMINI_AVAILABLE,
        "ai_claude": AI_AVAILABLE,
        "ai_model": GEMINI_MODEL if GEMINI_AVAILABLE else ("claude-sonnet" if AI_AVAILABLE else "none"),
        "agentic_v58": True,
        "time": datetime.now().isoformat()
    })

@app.route("/api/indices/global")
def api_global():
    return jsonify(get_global_indices())

@app.route("/api/indices/india")
def api_india():
    return jsonify(get_india_indices())

@app.route("/api/stocks/india")
def api_india_stocks():
    return jsonify(get_india_stocks())

@app.route("/api/stocks/global")
def api_global_stocks():
    return jsonify(get_global_stocks())

@app.route("/api/bonds")
def api_bonds():
    return jsonify(get_bonds())

@app.route("/api/forex")
def api_forex():
    return jsonify(get_forex())

@app.route("/api/world-trend")
def api_world():
    return jsonify(_world_market_trend())

@app.route("/api/india-trend")
def api_india_trend():
    return jsonify(_india_market_trend())

@app.route("/api/sectors")
def api_sectors():
    return jsonify(_sector_performance())

@app.route("/api/news")
def api_news():
    query = request.args.get("q", "")
    return jsonify(_scrape_news(query or None))

@app.route("/api/global-india-impact")
def api_global_india_impact():
    return jsonify(_global_india_impact())

@app.route("/api/stock/<ticker>")
def api_stock(ticker):
    ticker = ticker.upper()
    period = request.args.get("period", "3mo")
    with ThreadPoolExecutor(max_workers=5) as ex:
        fq = ex.submit(_fetch_one, ticker)
        ff = ex.submit(_fetch_fundamentals, ticker)
        ft = ex.submit(_technical_analysis, ticker)
        fo2 = ex.submit(_future_performance, ticker)
        fh = ex.submit(_fetch_history, ticker, period)
    return jsonify({
        "quote": fq.result(), "fundamentals": ff.result(),
        "analysis": ft.result(), "future_outlook": fo2.result(),
        "history": fh.result(),
    })

@app.route("/api/live-pulse")
def api_live_pulse():
    tickers_param = request.args.get("tickers", "")
    if tickers_param:
        tickers = [t.strip() for t in tickers_param.split(",") if t.strip()]
    else:
        tickers = list(ALL_LIVE_TICKERS.values())[:20]
    result = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(_fetch_live_price_only, t, 4): t for t in tickers[:25]}
        for fut in as_completed(futures, timeout=8):
            t = futures[fut]
            try:
                d = fut.result()
                if d: result[t] = d
            except: pass
    return jsonify({"prices": result, "ts": time.time()})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    q = (data.get("question") or "").strip()
    if not q: return jsonify({"error": "question required"}), 400
    result = _ai_chat(q)
    return jsonify({
        "answer": result.get("answer", ""),
        "source": result.get("source", ""),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/v58/<ticker>")
def api_v58(ticker):
    """Direct V58 agentic analysis endpoint"""
    ticker = ticker.upper()
    question = request.args.get("q", f"Full V58 analysis of {ticker}")
    result = _agentic_v58_analysis(ticker, question)
    return jsonify({
        "answer": result.get("answer", ""),
        "source": result.get("source", ""),
        "stage1": result.get("stage1", ""),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/search/<path:query>")
def api_search(query):
    return jsonify(_search_stock(query))

# ─── AUTO OPEN BROWSER ───
def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:5000")

if __name__ == "__main__":
    ai_status = "Gemini ✅" if GEMINI_AVAILABLE else ("Claude ✅" if AI_AVAILABLE else "❌ No AI Key")
    print(f"""
 ╔══════════════════════════════════════════════════════╗
 ║   FinVision v6.1 — Live Market Analyzer             ║
 ║   Backend: app.py  |  Frontend: index.html          ║
 ║   ✅ Global→India Impact Analysis                   ║
 ║   ✅ 8-Factor AI Score                              ║
 ║   ✅ News from 6 sources (live, no cache)           ║
 ║   ✅ Continuously Live Prices                       ║
 ║   🤖 Agentic V58 Deep Analysis Engine              ║
 ║   🤖 AI Engine: {ai_status:<34}║
 ║   📡 Opening: http://localhost:5000                 ║
 ╚══════════════════════════════════════════════════════╝

 🔑 API KEYS STATUS:
    Gemini  : {'✅ CONFIGURED' if GEMINI_AVAILABLE else '❌ Not set — edit GEMINI_API_KEY at top of app.py'}
    Anthropic: {'✅ CONFIGURED' if AI_AVAILABLE else '❌ Not set — edit ANTHROPIC_API_KEY at top of app.py'}

 🚀 AGENTIC V58 ENGINE:
    - Stock queries trigger 2-stage deep analysis
    - Stage 1: Live data gathering (V58 format)
    - Stage 2: AI narrative with price targets & prediction
    - Direct API: /api/v58/TICKER?q=your+question
""")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

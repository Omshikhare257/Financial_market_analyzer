#!/usr/bin/env python3
"""
FinVision v6.0 — Enhanced Edition
- Global Market Impact on India — Analysis Summary
- Gemini API Key input in UI (user pastes key, stored in session)
- More News Sources: Yahoo Finance, ET, Moneycontrol, LiveMint, Reuters, CNBC
- News auto-rotates every 60 seconds with fresh top headlines
- 8-Factor AI Score, Multi-language Chat (Anthropic + Gemini)
"""

import os, re, json, threading, time, traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from flask import Flask, jsonify, request, Response, session
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
    _ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    AI_AVAILABLE = bool(_ANTHROPIC_KEY)
except ImportError:
    _anthropic_lib = None
    _ANTHROPIC_KEY = ""
    AI_AVAILABLE = False

app = Flask(__name__)
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
        details["earnings_qoq"] = safe_float(info.get("earningsQuarterlyGrowth", 0) * 100, 1) if info.get("earningsQuarterlyGrowth") else None
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
        details["pe_expansion"] = "Positive (Earnings catching up)" if (fpe and tpe and fpe < tpe) else "Negative" if (fpe and tpe) else "N/A"
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
        ows = 50 + (20 if ins > 0.10 else 10 if ins > 0.05 else 0) + (20 if inst > 0.70 else 12 if inst > 0.50 else 0) + (5 if inst > 0.85 else 0)
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
        details["payout_ratio_pct"] = safe_float((info.get("payoutRatio") or 0) * 100, 1)
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

# ─────────────────────────────────────────────────────────────
# GLOBAL → INDIA IMPACT ANALYSIS
# ─────────────────────────────────────────────────────────────
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
        dax = global_idx.get("DAX", {})
        gold = bonds.get("Gold", {})
        crude = bonds.get("Crude Oil (WTI)", {})
        usdinr = forex.get("USD/INR", {})
        us_10y = bonds.get("US 10Y Treasury", {})
        impacts = []
        overall_impact_score = 0
        impact_count = 0

        # S&P 500 impact
        sp_chg = sp500.get("change_pct", 0) or 0
        if abs(sp_chg) > 0.3:
            direction = "positive" if sp_chg > 0 else "negative"
            mag = "strong" if abs(sp_chg) > 1.5 else "moderate" if abs(sp_chg) > 0.7 else "mild"
            exp_nifty = sp_chg * 0.55
            impacts.append({
                "source": "S&P 500 (USA)",
                "change": sp_chg,
                "direction": direction,
                "magnitude": mag,
                "sector_impact": "IT, Tech stocks most affected (TCS, Infosys, Wipro, HCL)",
                "expected_nifty_move": round(exp_nifty, 2),
                "reason": f"US markets {'rising' if sp_chg>0 else 'falling'} by {abs(sp_chg):.1f}% → Indian IT exports & FII flows {'improve' if sp_chg>0 else 'pressure'} → NIFTY likely {'+' if sp_chg>0 else ''}{exp_nifty:.1f}%",
                "icon": "🇺🇸",
                "confidence": "High"
            })
            overall_impact_score += exp_nifty
            impact_count += 1

        # NASDAQ impact
        nq_chg = nasdaq.get("change_pct", 0) or 0
        if abs(nq_chg) > 0.3:
            exp = nq_chg * 0.45
            impacts.append({
                "source": "NASDAQ (Tech)",
                "change": nq_chg,
                "direction": "positive" if nq_chg > 0 else "negative",
                "magnitude": "strong" if abs(nq_chg) > 2 else "moderate",
                "sector_impact": "NIFTY IT index direct correlation — Infosys, Wipro, HCL Tech",
                "expected_nifty_move": round(exp, 2),
                "reason": f"NASDAQ {'up' if nq_chg>0 else 'down'} {abs(nq_chg):.1f}% → NIFTY IT likely {'+' if exp>0 else ''}{exp:.1f}% → IT heavyweights {'gain' if exp>0 else 'fall'}",
                "icon": "💻",
                "confidence": "High"
            })

        # Nikkei/Asia impact
        nk_chg = nikkei.get("change_pct", 0) or 0
        if abs(nk_chg) > 0.4:
            exp = nk_chg * 0.35
            impacts.append({
                "source": "Nikkei 225 (Japan)",
                "change": nk_chg,
                "direction": "positive" if nk_chg > 0 else "negative",
                "magnitude": "moderate" if abs(nk_chg) > 1 else "mild",
                "sector_impact": "Auto sector — Maruti, Tata Motors (Japan supply chain)",
                "expected_nifty_move": round(exp, 2),
                "reason": f"Asia sentiment {'positive' if nk_chg>0 else 'negative'} — Japanese yen & supply chain {'support' if nk_chg>0 else 'pressure'} Indian auto sector",
                "icon": "🇯🇵",
                "confidence": "Moderate"
            })

        # Hang Seng / China impact
        hs_chg = hangseng.get("change_pct", 0) or 0
        sh_chg = shanghai.get("change_pct", 0) or 0
        china_avg = ((hs_chg or 0) + (sh_chg or 0)) / 2
        if abs(china_avg) > 0.4:
            exp = china_avg * 0.25
            impacts.append({
                "source": "China Markets (HK + Shanghai)",
                "change": round(china_avg, 2),
                "direction": "positive" if china_avg > 0 else "negative",
                "magnitude": "moderate" if abs(china_avg) > 1 else "mild",
                "sector_impact": "Metals (Tata Steel, JSW) — China demand drives commodity prices",
                "expected_nifty_move": round(exp, 2),
                "reason": f"China {'growing' if china_avg>0 else 'slowing'} → commodity demand {'up' if china_avg>0 else 'down'} → Indian metal stocks {'benefit' if china_avg>0 else 'suffer'}",
                "icon": "🇨🇳",
                "confidence": "Moderate"
            })

        # Crude Oil impact
        crude_chg = crude.get("change_pct", 0) or 0
        if abs(crude_chg) > 0.5:
            # Rising crude = negative for India (import dependent)
            exp = -crude_chg * 0.3
            impacts.append({
                "source": "Crude Oil (WTI)",
                "change": crude_chg,
                "direction": "negative" if crude_chg > 0 else "positive",
                "magnitude": "high" if abs(crude_chg) > 2 else "moderate",
                "sector_impact": "Oil & Gas (ONGC +), Aviation (IndiGo -), FMCG, Paint stocks affected",
                "expected_nifty_move": round(exp, 2),
                "reason": f"Crude {'rising' if crude_chg>0 else 'falling'} {abs(crude_chg):.1f}% → India imports 85% oil → {'inflation risk, CAD widens, INR weakens' if crude_chg>0 else 'inflation eases, CAD improves, INR strengthens'}",
                "icon": "🛢️",
                "confidence": "High"
            })
            overall_impact_score += exp
            impact_count += 1

        # Gold impact
        gold_chg = gold.get("change_pct", 0) or 0
        if abs(gold_chg) > 0.5:
            impacts.append({
                "source": "Gold Price",
                "change": gold_chg,
                "direction": "mixed" if gold_chg > 0 else "mild positive",
                "magnitude": "mild",
                "sector_impact": "Titan, Kalyan Jewellers, HDFC Gold Fund — Gold ETFs",
                "expected_nifty_move": round(gold_chg * 0.08, 2),
                "reason": f"Gold {'up' if gold_chg>0 else 'down'} {abs(gold_chg):.1f}% → Jewelry stocks {'benefit' if gold_chg>0 else 'pressure'} — India #1 gold consumer globally",
                "icon": "🥇",
                "confidence": "Moderate"
            })

        # USD/INR impact
        usdinr_chg = usdinr.get("change_pct", 0) or 0
        if abs(usdinr_chg) > 0.2:
            # Rising USD/INR = INR weakening = negative
            exp = -usdinr_chg * 0.4
            impacts.append({
                "source": "USD/INR (Rupee)",
                "change": usdinr_chg,
                "direction": "negative" if usdinr_chg > 0 else "positive",
                "magnitude": "high" if abs(usdinr_chg) > 0.7 else "moderate",
                "sector_impact": "IT exporters benefit (TCS, Infy) when INR weak; Importers suffer (Oil, Electronics)",
                "expected_nifty_move": round(exp, 2),
                "reason": f"INR {'weakening' if usdinr_chg>0 else 'strengthening'} vs USD → {'IT export earnings higher in INR, but FII outflows likely' if usdinr_chg>0 else 'FII inflows improve, import costs fall'}",
                "icon": "💱",
                "confidence": "High"
            })
            overall_impact_score += exp
            impact_count += 1

        # US 10Y Bond yield
        us10y_chg = us_10y.get("change_pct", 0) or 0
        us10y_price = us_10y.get("price", 4.0) or 4.0
        if abs(us10y_chg) > 0.5 or us10y_price > 4.5:
            exp = -us10y_chg * 0.35
            impacts.append({
                "source": "US 10Y Treasury Yield",
                "change": us10y_chg,
                "direction": "negative" if us10y_chg > 0 else "positive",
                "magnitude": "high" if us10y_price > 5 else "moderate" if us10y_price > 4.5 else "mild",
                "sector_impact": "Banking, Real Estate most sensitive — HDFC Bank, Bajaj Finance",
                "expected_nifty_move": round(exp, 2),
                "reason": f"US yields {'rising' if us10y_chg>0 else 'falling'} → {'FII sell India bonds & equity for safe US returns' if us10y_chg>0 else 'FII return to EM markets like India → bullish'}",
                "icon": "🏛️",
                "confidence": "High"
            })
            overall_impact_score += exp
            impact_count += 1

        # Overall summary
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

# ─────────────────────────────────────────────────────────────
# ENHANCED NEWS SCRAPER — Multiple Sources
# ─────────────────────────────────────────────────────────────
def _scrape_news():
    # Use short TTL so news rotates on frontend requests
    cached = cache_get("news", ttl=55)
    if cached: return cached
    news = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    sources = [
        ("https://finance.yahoo.com/news/", "Yahoo Finance", "h3"),
        ("https://economictimes.indiatimes.com/markets", "Economic Times", "h3"),
        ("https://www.moneycontrol.com/news/business/markets/", "Moneycontrol", "h2"),
        ("https://www.livemint.com/market/stock-market-news", "LiveMint", "h2"),
        ("https://www.reuters.com/finance/markets/", "Reuters", "h3"),
        ("https://www.cnbctv18.com/market/", "CNBC TV18", "h3"),
    ]
    now_str = datetime.now().strftime("%H:%M")
    for url, source, tag in sources:
        try:
            r = req_lib.get(url, headers=headers, timeout=7)
            soup = BeautifulSoup(r.text, "html.parser")
            count = 0
            for elem in soup.find_all(tag, limit=15):
                text = elem.get_text(strip=True)
                if len(text) < 25 or len(text) > 300: continue
                # Filter only market/finance related headlines
                kw = ["stock","market","nifty","sensex","share","invest","rupee","rbi","sebi",
                      "ipo","fund","trade","economy","gdp","rate","oil","gold","bitcoin","crypto",
                      "bank","finance","profit","revenue","quarter","earning","index","rally","bull","bear",
                      "nasdaq","sp500","dow","fed","inflation","fiscal","budget","export","import"]
                if not any(k in text.lower() for k in kw): continue
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
        except Exception as e:
            pass
    # Remove duplicates by title similarity
    seen_titles = set()
    unique_news = []
    for item in news:
        key = item["title"][:50].lower().strip()
        if key not in seen_titles:
            seen_titles.add(key)
            unique_news.append(item)
    # Shuffle for variety on rotation
    import random
    random.shuffle(unique_news)
    final = unique_news[:40]
    cache_set("news", final)
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

# ─────────────────────────────────────────────────────────────
# AI CHAT — Anthropic + Gemini
# ─────────────────────────────────────────────────────────────
def _ai_chat(question, gemini_key=None):
    q_up = question.upper()
    ticker_found = None
    all_stocks = {**POPULAR_INDIAN_STOCKS, **POPULAR_GLOBAL_STOCKS}
    for name, ticker in all_stocks.items():
        base = re.sub(r'\..+$', '', ticker)
        if name.upper() in q_up or base in q_up:
            ticker_found = ticker
            break
    if not ticker_found:
        words = re.findall(r'\b([A-Z]{2,10}(?:\.NS|\.BO|\.KS)?)\b', q_up)
        skip = {"THE","AND","FOR","BUY","SELL","HOW","WHY","WHAT","WHICH","BEST","TOP",
                "NSE","BSE","NIFTY","MARKET","STOCK","PRICE","TODAY"}
        for w in words:
            if w not in skip:
                for suf in ["", ".NS", ".BO"]:
                    try:
                        info = yf.Ticker(w + suf).info or {}
                        if info.get("regularMarketPrice"):
                            ticker_found = w + suf
                            break
                    except: pass
                if ticker_found: break
    context = ""
    if ticker_found:
        q_d = _fetch_one(ticker_found)
        f_data = _fetch_fundamentals(ticker_found)
        ta = _technical_analysis(ticker_found)
        fo = _future_performance(ticker_found)
        ol = fo.get("details", {})
        sc = fo.get("scenarios", {})
        context = f"""
=== LIVE DATA: {ticker_found} ===
Price: {q_d.get('price')} {q_d.get('currency')} | Change: {q_d.get('change_pct')}%
P/E: {q_d.get('pe_ratio')} | Fwd P/E: {f_data.get('forward_pe')} | Mkt Cap: {q_d.get('market_cap')}
52W H/L: {q_d.get('52w_high')} / {q_d.get('52w_low')}
Sector: {f_data.get('sector')} | Industry: {f_data.get('industry')}
EPS: {f_data.get('eps')} | ROE: {f_data.get('roe')} | D/E: {f_data.get('debt_equity')}
RSI: {ta.get('rsi')} | MACD: {'Bullish' if (ta.get('macd') or 0) > (ta.get('signal') or 0) else 'Bearish'} | Momentum: {ta.get('momentum_score')}/100
MA20/50/200: {ta.get('ma20')}/{ta.get('ma50')}/{ta.get('ma200')}
=== 8-FACTOR FUTURE SCORE ===
AI Score: {fo.get('composite_score')}/100 → {fo.get('grade')}
Horizons: ST={fo.get('horizon',{}).get('short_term')} MT={fo.get('horizon',{}).get('medium_term')} LT={fo.get('horizon',{}).get('long_term')}
Analyst Target: {ol.get('analyst_target')} (Upside: {ol.get('analyst_upside_pct')}%)
Scenarios (1Y): Bull={sc.get('bull')} Base={sc.get('base')} Bear={sc.get('bear')}
About: {f_data.get('summary', '')[:300]}
"""
    q_low = question.lower()
    extra = ""
    if any(w in q_low for w in ["world","global","market today","aaj ka","दुनिया"]):
        try:
            wt = _world_market_trend()
            extra += f"\n=== GLOBAL MARKET ===\nSentiment: {wt['sentiment']} | Avg: {wt['avg_change']}%\nVIX: {wt['vix']} | Fear: {wt['fear_gauge']}\n"
        except: pass
    if any(w in q_low for w in ["india","nifty","sensex","भारत","indian market","impact"]):
        try:
            it = _india_market_trend()
            imp = _global_india_impact()
            extra += f"\n=== INDIA MARKET ===\nSentiment: {it['sentiment']} | Avg: {it['avg_change']}%\nNIFTY: {it['nifty'].get('price')} ({it['nifty'].get('change_pct')}%)\nGlobal Impact Signal: {imp['overall'].get('overall_signal')}\n"
        except: pass
    full_ctx = context + extra
    system_prompt = (
        "You are FinVision AI v6, expert financial analyst for Indian & global markets. "
        "Live market data + 8-factor future performance scores provided. "
        "CRITICAL: Reply in SAME language as user. Hindi→Hindi. English→English. Hinglish→Hinglish. "
        "Give structured analysis. For stocks include: current status, 8-factor score breakdown, "
        "short/medium/long-term outlook, key risks, buy/hold/sell recommendation with reasoning. "
        "End with: ⚠️ Disclaimer: Educational only. SEBI-registered advisor se consult karein."
    )
    # Try Gemini first if key provided
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": f"{full_ctx}\n\nUser: {question}"}]}],
                "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.7}
            }
            resp = req_lib.post(url, json=payload, timeout=20)
            data = resp.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if text:
                return text
        except Exception as e:
            pass
    # Try Anthropic
    if AI_AVAILABLE and _anthropic_lib:
        try:
            client = _anthropic_lib.Anthropic(api_key=_ANTHROPIC_KEY)
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": f"{full_ctx}\n\nUser: {question}"}],
            )
            return msg.content[0].text
        except: pass
    # Fallback
    parts = [f"📊 **{question}**\n"]
    if full_ctx:
        parts.append(f"```\n{full_ctx[:800]}\n```\n")
    parts.append("\n⚠️ *Educational only. No AI key configured — add Gemini key in Settings.*")
    return "".join(parts)

# ─────────────────────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "ai": AI_AVAILABLE, "time": datetime.now().isoformat()})

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
    return jsonify(_scrape_news())

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
    gemini_key = (data.get("gemini_key") or "").strip()
    if not q: return jsonify({"error": "question required"}), 400
    return jsonify({"answer": _ai_chat(q, gemini_key=gemini_key or None), "timestamp": datetime.now().isoformat()})

@app.route("/api/search/<path:query>")
def api_search(query):
    return jsonify(_search_stock(query))

# ─────────────────────────────────────────────────────────────
# FRONTEND HTML — Complete v6.0
# ─────────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=5.0">
<title>FinVision v6 — Live Market Analyzer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Exo+2:wght@300;400;600;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#020509;--s1:#060c14;--s2:#091220;--s3:#0c172a;
  --border:#112236;--border2:#1a3354;
  --c:#00e5ff;--g:#00ff88;--r:#ff2244;--gold:#ffcc00;
  --pu:#b060ff;--or:#ff7700;--amber:#ffb347;
  --t:#c8dff0;--t2:#4a7090;--t3:#1e3858;
  --glow:0 0 18px rgba(0,229,255,.1);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html{font-size:15px;scroll-behavior:smooth}
body{font-family:'Exo 2',sans-serif;background:var(--bg);color:var(--t);min-height:100svh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse 80% 50% at 10% 0%,rgba(0,100,255,.05),transparent 60%),
    radial-gradient(ellipse 60% 40% at 90% 100%,rgba(0,200,100,.04),transparent 60%)}
.gridbg{position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(0,229,255,.015) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,.015) 1px,transparent 1px);
  background-size:44px 44px}
header{position:sticky;top:0;z-index:500;height:52px;display:flex;align-items:center;gap:.6rem;padding:0 .8rem;
  background:rgba(2,5,9,.96);backdrop-filter:blur(24px);border-bottom:1px solid var(--border)}
.logo{font-family:'Rajdhani',sans-serif;font-size:1.35rem;font-weight:700;letter-spacing:1px;white-space:nowrap;
  background:linear-gradient(90deg,var(--c),var(--g));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo sub{font-size:.55rem;font-weight:400;opacity:.5;-webkit-text-fill-color:var(--t2);vertical-align:super}
.hsearch{flex:1;position:relative;max-width:500px;margin:0 auto}
.hsearch input{width:100%;background:var(--s2);border:1px solid var(--border);color:var(--t);
  padding:.32rem .8rem;padding-right:80px;border-radius:7px;font-family:'Exo 2',sans-serif;font-size:.8rem;outline:none;transition:border .2s}
.hsearch input:focus{border-color:var(--c)}
.hsearch input::placeholder{color:var(--t3)}
.hsbtn{position:absolute;right:3px;top:50%;transform:translateY(-50%);
  background:linear-gradient(90deg,var(--c),var(--g));border:none;color:#000;
  padding:.22rem .75rem;border-radius:5px;font-weight:700;font-size:.72rem;cursor:pointer;font-family:'Rajdhani',sans-serif;letter-spacing:.5px}
.sdrop{position:absolute;top:calc(100%+4px);left:0;right:0;background:var(--s2);border:1px solid var(--border2);
  border-radius:8px;z-index:600;overflow:hidden;max-height:220px;overflow-y:auto;display:none;box-shadow:0 8px 32px rgba(0,0,0,.6)}
.sdrop.show{display:block}
.sdrop-item{display:flex;justify-content:space-between;align-items:center;padding:.45rem .8rem;cursor:pointer;gap:.5rem;transition:background .15s}
.sdrop-item:hover{background:rgba(0,229,255,.08)}
.sdrop-nm{font-size:.78rem;color:var(--t);font-weight:500}
.sdrop-tk{font-family:'Share Tech Mono',monospace;font-size:.63rem;color:var(--t2)}
.sdrop-ldg{padding:.6rem;text-align:center;color:var(--t2);font-size:.72rem}
.hright{display:flex;align-items:center;gap:.5rem;flex-shrink:0}
.livebadge{display:flex;align-items:center;gap:4px;font-size:.6rem;font-weight:700;letter-spacing:1.5px;
  color:var(--g);background:rgba(0,255,136,.07);border:1px solid rgba(0,255,136,.18);
  padding:2px 7px;border-radius:15px;white-space:nowrap}
.ldot{width:5px;height:5px;border-radius:50%;background:var(--g);animation:blink 1.2s ease infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.1}}
.hclk{font-family:'Share Tech Mono',monospace;font-size:.6rem;color:var(--t2);white-space:nowrap;display:none}
@media(min-width:700px){.hclk{display:block}}
.settbtn{background:rgba(255,255,255,.05);border:1px solid var(--border);color:var(--t2);
  padding:3px 9px;border-radius:6px;cursor:pointer;font-size:.65rem;font-family:'Exo 2',sans-serif;
  transition:all .15s;white-space:nowrap;flex-shrink:0}
.settbtn:hover{background:rgba(255,204,0,.1);color:var(--gold);border-color:var(--gold)}
@keyframes flash-up{0%{background:rgba(0,255,136,.3)}100%{background:transparent}}
@keyframes flash-dn{0%{background:rgba(255,34,68,.3)}100%{background:transparent}}
.flash-up{animation:flash-up .6s ease-out}
.flash-dn{animation:flash-dn .6s ease-out}
.refresh-ring{position:fixed;bottom:1.1rem;right:1.1rem;z-index:900;
  width:36px;height:36px;border-radius:50%;cursor:pointer;
  background:rgba(0,229,255,.07);border:1.5px solid rgba(0,229,255,.2);
  display:flex;align-items:center;justify-content:center;transition:all .2s;box-shadow:0 0 15px rgba(0,229,255,.1)}
.refresh-ring:hover{background:rgba(0,229,255,.15)}
.rring-svg{position:absolute;inset:0;width:36px;height:36px;transform:rotate(-90deg)}
.rring-track{fill:none;stroke:rgba(0,229,255,.08);stroke-width:2.5}
.rring-fill{fill:none;stroke:var(--c);stroke-width:2.5;stroke-linecap:round;
  stroke-dasharray:100;stroke-dashoffset:100;transition:stroke-dashoffset .3s linear}
.rring-icon{font-size:.8rem;position:relative;z-index:1}
.tape{background:var(--s1);border-bottom:1px solid var(--border);overflow:hidden;position:relative;height:26px;display:flex;align-items:center}
.tape::before,.tape::after{content:'';position:absolute;top:0;bottom:0;width:50px;z-index:2;pointer-events:none}
.tape::before{left:0;background:linear-gradient(90deg,var(--s1),transparent)}
.tape::after{right:0;background:linear-gradient(-90deg,var(--s1),transparent)}
.tape-r{display:flex;gap:1.8rem;width:max-content;animation:tapescroll 55s linear infinite;padding:0 1rem}
.tape-r:hover{animation-play-state:paused}
@keyframes tapescroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.ti{font-family:'Share Tech Mono',monospace;font-size:.62rem;white-space:nowrap;display:flex;align-items:center;gap:3px;border-radius:3px;padding:1px 3px;transition:background .3s}
.tn{color:var(--t2)}.tp{color:var(--t);font-weight:600}
.up{color:var(--g)}.dn{color:var(--r)}.neu{color:var(--t2)}
nav{background:var(--s1);border-bottom:1px solid var(--border);display:flex;overflow-x:auto;scrollbar-width:none;
  padding:0 .3rem;position:sticky;top:52px;z-index:400;-webkit-overflow-scrolling:touch}
nav::-webkit-scrollbar{display:none}
.tab{padding:.5rem .75rem;border:none;background:transparent;color:var(--t2);
  font-family:'Rajdhani',sans-serif;font-size:.72rem;font-weight:600;letter-spacing:1px;text-transform:uppercase;
  cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;transition:all .2s;flex-shrink:0}
.tab:hover{color:var(--t)}.tab.on{color:var(--c);border-bottom-color:var(--c)}
main{position:relative;z-index:1;max-width:1800px;margin:0 auto;padding:.8rem}
@media(min-width:768px){main{padding:1.1rem 1.4rem}}
.panel{display:none}.panel.on{display:block}
.g2{display:grid;grid-template-columns:1fr;gap:.9rem}
.g3{display:grid;grid-template-columns:1fr;gap:.9rem}
.g4{display:grid;grid-template-columns:repeat(2,1fr);gap:.7rem}
.g5{display:grid;grid-template-columns:repeat(2,1fr);gap:.7rem}
@media(min-width:560px){.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:1fr 1fr}}
@media(min-width:860px){.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}.g5{grid-template-columns:repeat(3,1fr)}}
@media(min-width:1100px){.g5{grid-template-columns:repeat(4,1fr)}}
@media(min-width:1300px){.g5{grid-template-columns:repeat(5,1fr)}}
.card{background:var(--s1);border:1px solid var(--border);border-radius:11px;padding:.9rem;transition:border-color .2s}
@media(min-width:768px){.card{padding:1.1rem}}
.card:hover{border-color:var(--border2)}
.ctitle{font-size:.58rem;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;color:var(--t2);
  margin-bottom:.8rem;display:flex;align-items:center;gap:.4rem}
.ctitle::after{content:'';flex:1;height:1px;background:var(--border)}
.ic{background:var(--s2);border:1px solid var(--border);border-radius:9px;padding:.8rem .9rem;transition:all .2s;cursor:pointer}
.ic:hover{border-color:var(--c);box-shadow:var(--glow)}
.ic .in{font-size:.56rem;font-weight:700;letter-spacing:1.5px;color:var(--t2);text-transform:uppercase;margin-bottom:.28rem}
.ic .ip{font-family:'Share Tech Mono',monospace;font-size:1rem;font-weight:700;color:var(--t)}
.ic .ic2{font-family:'Share Tech Mono',monospace;font-size:.68rem;margin-top:.22rem}
.sr{display:flex;justify-content:space-between;align-items:center;padding:.38rem 0;border-bottom:1px solid rgba(255,255,255,.03);font-size:.78rem}
.sr:last-child{border:none}
.sl{color:var(--t2)}.sv{font-family:'Share Tech Mono',monospace;color:var(--t)}
.tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.tbl{width:100%;border-collapse:collapse;font-family:'Share Tech Mono',monospace;font-size:.68rem;min-width:450px}
.tbl thead tr{border-bottom:1px solid var(--border)}
.tbl th{padding:.45rem .6rem;text-align:right;color:var(--t3);font-size:.56rem;letter-spacing:1.5px;text-transform:uppercase}
.tbl th:first-child{text-align:left}
.tbl td{padding:.45rem .6rem;text-align:right;border-bottom:1px solid rgba(255,255,255,.025);color:var(--t);transition:background .1s}
.tbl td:first-child{text-align:left}
.tbl tr:hover td{background:rgba(0,229,255,.03)}
.sn{font-weight:600;color:var(--t);font-family:'Exo 2',sans-serif;font-size:.76rem}
.stk{color:var(--t2);font-size:.58rem;font-family:'Share Tech Mono',monospace}
.bdg{display:inline-block;padding:1px 6px;border-radius:12px;font-size:.58rem;font-weight:700}
.bu{background:rgba(0,255,136,.09);color:var(--g);border:1px solid rgba(0,255,136,.15)}
.bd{background:rgba(255,34,68,.09);color:var(--r);border:1px solid rgba(255,34,68,.15)}
.bn{background:rgba(255,204,0,.09);color:var(--gold);border:1px solid rgba(255,204,0,.15)}
.abtn{background:rgba(0,229,255,.07);border:1px solid rgba(0,229,255,.15);color:var(--c);
  padding:2px 8px;border-radius:4px;cursor:pointer;font-size:.6rem;font-family:'Exo 2',sans-serif;font-weight:600;transition:all .15s;white-space:nowrap}
.abtn:hover{background:rgba(0,229,255,.15)}
.ph{font-family:'Rajdhani',sans-serif;font-size:1.4rem;font-weight:700;letter-spacing:.5px;margin-bottom:.2rem}
@media(min-width:768px){.ph{font-size:1.7rem}}
.ph span{color:var(--c)}
.ps{color:var(--t2);font-size:.75rem;margin-bottom:1rem}
.spin{display:inline-block;width:13px;height:13px;border:2px solid rgba(0,229,255,.12);border-top-color:var(--c);border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.ldc{display:flex;align-items:center;justify-content:center;min-height:80px;color:var(--t2);gap:.5rem;font-size:.78rem;padding:.8rem}
.skel{background:linear-gradient(90deg,var(--s2) 0%,var(--s3) 50%,var(--s2) 100%);
  background-size:200% 100%;animation:shimmer 1.4s ease infinite;border-radius:5px;height:16px;margin:.35rem 0}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.skel.sm{height:12px;width:60%}.skel.lg{height:22px}
.sentbox{border-radius:10px;padding:1rem 1.1rem;text-align:center}
.sentbox.bull{background:linear-gradient(135deg,rgba(0,255,136,.07),rgba(0,229,255,.05));border:1px solid rgba(0,255,136,.18)}
.sentbox.bear{background:linear-gradient(135deg,rgba(255,34,68,.07),rgba(255,119,0,.05));border:1px solid rgba(255,34,68,.18)}
.sentbox.side{background:linear-gradient(135deg,rgba(255,204,0,.07),rgba(176,96,255,.05));border:1px solid rgba(255,204,0,.18)}
.sb-lbl{font-size:.55rem;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;color:var(--t2);margin-bottom:.3rem}
.sb-val{font-family:'Rajdhani',sans-serif;font-size:1.7rem;font-weight:700}
.sb-sub{font-size:.68rem;color:var(--t2);margin-top:.2rem}
.bbar{display:flex;align-items:center;gap:.5rem;margin:.4rem 0}
.btrack{flex:1;height:7px;border-radius:3px;background:rgba(255,34,68,.18);overflow:hidden}
.bfill{height:100%;background:linear-gradient(90deg,var(--g),var(--c));border-radius:3px;transition:width .8s ease}
.bnums{font-family:'Share Tech Mono',monospace;font-size:.62rem;white-space:nowrap}
.sbar-row{display:flex;align-items:center;gap:.55rem;padding:.32rem 0;border-bottom:1px solid rgba(255,255,255,.028)}
.sbar-row:last-child{border:none}
.sbar-nm{font-size:.68rem;color:var(--t);flex:0 0 150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media(max-width:480px){.sbar-nm{flex:0 0 100px;font-size:.62rem}}
.sbar-track{flex:1;background:rgba(255,255,255,.04);border-radius:3px;height:5px;overflow:hidden}
.sbar-fill{height:100%;border-radius:3px;transition:width .6s ease}
.sbar-val{font-family:'Share Tech Mono',monospace;font-size:.64rem;width:52px;text-align:right;flex-shrink:0}
.reg{font-size:.52rem;font-weight:700;letter-spacing:.6px;text-transform:uppercase;padding:1px 5px;border-radius:8px;flex-shrink:0}
.ri{background:rgba(255,160,0,.1);color:#ffa040;border:1px solid rgba(255,160,0,.15)}
.rg{background:rgba(64,160,255,.09);color:#4da6ff;border:1px solid rgba(64,160,255,.15)}
.gauge-w{display:flex;flex-direction:column;align-items:center;padding:.6rem 0}
.gauge-r{position:relative;width:110px;height:110px}
.gauge-r svg{transform:rotate(-90deg)}
.gauge-v{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gauge-n{font-family:'Share Tech Mono',monospace;font-size:1.6rem;font-weight:700}
.gauge-l{font-size:.5rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--t2)}
.gpill{margin-top:.4rem;padding:2px 11px;border-radius:15px;font-size:.67rem;font-weight:700}
.fp-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.5rem;margin-bottom:.9rem}
@media(min-width:560px){.fp-grid{grid-template-columns:repeat(4,1fr)}}
@media(min-width:860px){.fp-grid{grid-template-columns:repeat(8,1fr)}}
.fp-card{background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:.55rem .6rem;text-align:center}
.fp-icon{font-size:1.1rem;margin-bottom:2px}
.fp-name{font-size:.5rem;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--t2);margin-bottom:.2rem;line-height:1.2}
.fp-score{font-family:'Share Tech Mono',monospace;font-size:1.05rem;font-weight:700}
.fp-wt{font-size:.48rem;color:var(--t3);margin-top:1px}
.fp-bar{height:3px;border-radius:2px;margin-top:.25rem;background:var(--border)}
.fp-bar-fill{height:100%;border-radius:2px;transition:width .8s ease}
.horizon-row{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.9rem}
.hz{flex:1;min-width:100px;background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:.6rem .8rem;text-align:center}
.hz-lbl{font-size:.52rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--t2);margin-bottom:.3rem}
.hz-val{font-size:.82rem;font-weight:700;font-family:'Rajdhani',sans-serif}
.sc-row{display:flex;align-items:center;gap:.5rem;padding:.3rem 0}
.sc-lbl{font-size:.62rem;font-weight:700;width:42px;flex-shrink:0;text-transform:uppercase;letter-spacing:.6px}
.sc-bar{flex:1;background:rgba(255,255,255,.04);border-radius:4px;height:20px;overflow:hidden}
.sc-fill{height:100%;border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:5px}
.sc-price{font-family:'Share Tech Mono',monospace;font-size:.62rem;font-weight:600;color:#000}
.sigwrap{display:flex;flex-wrap:wrap;gap:3px}
.sigchip{padding:2px 7px;border-radius:12px;font-size:.58rem;font-weight:600;
  background:rgba(0,229,255,.06);border:1px solid rgba(0,229,255,.13);color:var(--c)}
.chwrap{position:relative;height:200px;background:var(--s2);border-radius:7px;padding:.5rem}
@media(min-width:768px){.chwrap{height:260px}}
/* ── NEWS SECTION ── */
.news-grid{display:grid;grid-template-columns:1fr;gap:.6rem}
@media(min-width:640px){.news-grid{grid-template-columns:1fr 1fr}}
@media(min-width:1000px){.news-grid{grid-template-columns:repeat(3,1fr)}}
.news-card{background:var(--s2);border:1px solid var(--border);border-radius:9px;padding:.8rem;
  transition:all .2s;position:relative;overflow:hidden}
.news-card:hover{border-color:var(--border2);transform:translateY(-1px)}
.news-card::before{content:'';position:absolute;top:0;left:0;width:3px;height:100%;background:var(--c)}
.news-src-badge{display:inline-block;font-size:.5rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  padding:1px 6px;border-radius:10px;background:rgba(0,229,255,.07);color:var(--c);border:1px solid rgba(0,229,255,.15);margin-bottom:.4rem}
.news-title{font-size:.8rem;font-weight:500;line-height:1.55;color:var(--t);margin-bottom:.35rem}
.news-title a{color:var(--t);text-decoration:none;transition:color .15s}
.news-title a:hover{color:var(--c)}
.news-meta{font-size:.6rem;color:var(--t3);display:flex;align-items:center;gap:.4rem}
.news-dot{width:3px;height:3px;border-radius:50%;background:var(--t3)}
.news-rotate-bar{height:2px;background:var(--border);border-radius:2px;overflow:hidden;margin-bottom:.8rem}
.news-rotate-fill{height:100%;background:linear-gradient(90deg,var(--c),var(--g));border-radius:2px;transition:width 1s linear}
.news-cnt{font-size:.65rem;color:var(--t2);text-align:right;margin-bottom:.5rem;font-family:'Share Tech Mono',monospace}
/* ── GLOBAL → INDIA IMPACT ── */
.impact-header{background:linear-gradient(135deg,rgba(0,229,255,.06),rgba(0,255,136,.04));
  border:1px solid rgba(0,229,255,.15);border-radius:12px;padding:1rem 1.2rem;margin-bottom:1rem}
.impact-signal{font-family:'Rajdhani',sans-serif;font-size:2rem;font-weight:700;display:flex;align-items:center;gap:.6rem}
.impact-card{background:var(--s2);border:1px solid var(--border);border-radius:10px;padding:.9rem;
  margin-bottom:.6rem;transition:all .2s;position:relative;overflow:hidden}
.impact-card:hover{border-color:var(--border2)}
.impact-card.positive{border-left:3px solid var(--g)}
.impact-card.negative{border-left:3px solid var(--r)}
.impact-card.mixed{border-left:3px solid var(--gold)}
.impact-src{font-size:.75rem;font-weight:700;color:var(--t);margin-bottom:.25rem;display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.impact-chg{font-family:'Share Tech Mono',monospace;font-size:.72rem}
.impact-reason{font-size:.72rem;color:var(--t2);line-height:1.65;margin:.35rem 0}
.impact-sector{font-size:.62rem;color:var(--c);background:rgba(0,229,255,.05);
  border:1px solid rgba(0,229,255,.1);padding:2px 8px;border-radius:10px;display:inline-block;margin-top:.2rem}
.impact-move{font-family:'Share Tech Mono',monospace;font-size:.8rem;font-weight:700;padding:2px 9px;border-radius:6px;white-space:nowrap}
.impact-move.pos{background:rgba(0,255,136,.1);color:var(--g)}
.impact-move.neg{background:rgba(255,34,68,.1);color:var(--r)}
.impact-move.neu{background:rgba(255,204,0,.1);color:var(--gold)}
.imp-mag{font-size:.52rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;
  padding:1px 6px;border-radius:8px;border:1px solid}
.mag-high{color:var(--r);border-color:rgba(255,34,68,.3);background:rgba(255,34,68,.06)}
.mag-strong{color:var(--r);border-color:rgba(255,34,68,.3);background:rgba(255,34,68,.06)}
.mag-moderate{color:var(--gold);border-color:rgba(255,204,0,.3);background:rgba(255,204,0,.06)}
.mag-mild{color:var(--g);border-color:rgba(0,255,136,.3);background:rgba(0,255,136,.06)}
.risk-tail-grid{display:grid;grid-template-columns:1fr 1fr;gap:.7rem;margin-top:.8rem}
.risk-box{background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:.75rem}
.risk-box.risks{border-left:3px solid var(--r)}
.risk-box.tails{border-left:3px solid var(--g)}
.risk-item{font-size:.68rem;color:var(--t2);line-height:1.55;padding:.22rem 0;border-bottom:1px solid rgba(255,255,255,.03)}
.risk-item:last-child{border:none}
/* ── CHAT SECTION ── */
.chatwrap{display:flex;flex-direction:column;height:calc(100svh - 185px);min-height:380px;max-height:780px;
  background:var(--s1);border:1px solid var(--border);border-radius:14px;overflow:hidden}
.chhead{padding:.7rem 1rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.7rem;flex-shrink:0;flex-wrap:wrap}
.chavatar{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,var(--c),var(--g));
  display:flex;align-items:center;justify-content:center;font-size:.95rem;flex-shrink:0}
.gemini-status{font-size:.58rem;padding:2px 7px;border-radius:10px;font-weight:700;letter-spacing:.5px}
.gs-active{background:rgba(255,204,0,.1);color:var(--gold);border:1px solid rgba(255,204,0,.2)}
.gs-inactive{background:rgba(255,255,255,.04);color:var(--t3);border:1px solid var(--border)}
.chmsg{flex:1;overflow-y:auto;padding:.9rem;display:flex;flex-direction:column;gap:.7rem}
.chmsg::-webkit-scrollbar{width:2px}
.chmsg::-webkit-scrollbar-thumb{background:var(--border)}
.msg{max-width:90%;padding:.65rem .9rem;border-radius:10px;font-size:.8rem;line-height:1.72;white-space:pre-wrap;word-break:break-word}
@media(min-width:768px){.msg{max-width:82%}}
.mu{align-self:flex-end;background:rgba(0,229,255,.07);border:1px solid rgba(0,229,255,.15);color:var(--t)}
.ma{align-self:flex-start;background:var(--s2);border:1px solid var(--border);color:var(--t)}
.qps{display:flex;flex-wrap:wrap;gap:.3rem;padding:.5rem .9rem;border-top:1px solid var(--border);flex-shrink:0}
.qp{background:rgba(255,255,255,.035);border:1px solid var(--border);color:var(--t2);
  padding:2px 9px;border-radius:12px;cursor:pointer;font-size:.64rem;font-family:'Exo 2',sans-serif;
  transition:all .15s;white-space:nowrap}
.qp:hover{background:rgba(0,229,255,.07);color:var(--c);border-color:rgba(0,229,255,.2)}
.chin-row{display:flex;gap:.5rem;padding:.7rem .9rem;border-top:1px solid var(--border);background:var(--s2);flex-shrink:0}
.chin{flex:1;background:var(--s1);border:1px solid var(--border);color:var(--t);
  padding:.5rem .8rem;border-radius:8px;font-family:'Exo 2',sans-serif;font-size:.82rem;outline:none;transition:border .2s;min-width:0}
.chin:focus{border-color:var(--c)}.chin::placeholder{color:var(--t3)}
.chsend{background:linear-gradient(135deg,var(--c),var(--g));border:none;color:#000;
  padding:.5rem 1rem;border-radius:8px;cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:.8rem;
  flex-shrink:0;transition:opacity .2s;letter-spacing:.5px}
.chsend:hover{opacity:.85}.chsend:disabled{opacity:.3;cursor:not-allowed}
/* ── SETTINGS MODAL ── */
.moverlay{position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.92);backdrop-filter:blur(18px);
  display:none;align-items:flex-start;justify-content:center;padding:.8rem;overflow-y:auto}
.moverlay.open{display:flex}
.modal{background:var(--s1);border:1px solid var(--border2);border-radius:14px;
  width:100%;max-width:980px;padding:1rem;position:relative;margin:auto}
@media(min-width:768px){.modal{padding:1.8rem}}
.mclose{position:absolute;top:.8rem;right:.8rem;background:rgba(255,255,255,.06);
  border:1px solid var(--border);color:var(--t);width:30px;height:30px;border-radius:50%;
  cursor:pointer;font-size:.85rem;display:flex;align-items:center;justify-content:center;transition:background .2s}
.mclose:hover{background:rgba(255,34,68,.2)}
.mtitle{font-family:'Rajdhani',sans-serif;font-size:1.25rem;font-weight:700;margin-bottom:.12rem;padding-right:36px}
.msub{color:var(--t2);margin-bottom:1rem;font-size:.76rem}
/* Settings modal */
.sett-modal{max-width:560px}
.sett-field{margin-bottom:1rem}
.sett-label{font-size:.65rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--t2);margin-bottom:.35rem}
.sett-input{width:100%;background:var(--s2);border:1px solid var(--border);color:var(--t);
  padding:.55rem .8rem;border-radius:8px;font-family:'Share Tech Mono',monospace;font-size:.8rem;outline:none;transition:border .2s}
.sett-input:focus{border-color:var(--gold)}
.sett-hint{font-size:.62rem;color:var(--t3);margin-top:.25rem;line-height:1.5}
.sett-save{background:linear-gradient(135deg,var(--gold),var(--or));border:none;color:#000;
  padding:.55rem 1.5rem;border-radius:8px;cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:.85rem;
  margin-top:.5rem;letter-spacing:.5px;transition:opacity .2s}
.sett-save:hover{opacity:.85}
.sett-ok{font-size:.75rem;color:var(--g);margin-top:.35rem;display:none}
[data-live]{transition:color .3s}
</style>
</head>
<body>
<div class="gridbg"></div>
<div class="refresh-ring" id="rring" title="Auto-refresh" onclick="forceRefresh()">
  <svg class="rring-svg" viewBox="0 0 36 36">
    <circle class="rring-track" cx="18" cy="18" r="15"/>
    <circle class="rring-fill" id="rring-fill" cx="18" cy="18" r="15"/>
  </svg>
  <span class="rring-icon">⟳</span>
</div>

<!-- SETTINGS MODAL -->
<div class="moverlay" id="sett-overlay">
  <div class="modal sett-modal">
    <button class="mclose" onclick="closeSettings()">✕</button>
    <div class="mtitle">⚙️ Settings</div>
    <div class="msub">Configure your AI API keys</div>
    <div class="sett-field">
      <div class="sett-label">🔑 Google Gemini API Key</div>
      <input class="sett-input" id="gemini-key-inp" type="password" placeholder="Paste your Gemini API key here...">
      <div class="sett-hint">
        Get free key: <a href="https://aistudio.google.com/app/apikey" target="_blank" style="color:var(--gold)">aistudio.google.com</a><br>
        Used for AI chat analysis. Key is saved in your browser only — never sent to our server except during chat API calls.
      </div>
    </div>
    <div class="sett-field">
      <div class="sett-label">Gemini Model</div>
      <select class="sett-input" id="gemini-model-sel">
        <option value="gemini-1.5-flash">gemini-1.5-flash (Fast, Free tier)</option>
        <option value="gemini-1.5-pro">gemini-1.5-pro (Better quality)</option>
        <option value="gemini-2.0-flash">gemini-2.0-flash (Latest)</option>
      </select>
    </div>
    <button class="sett-save" onclick="saveSettings()">💾 Save Settings</button>
    <div class="sett-ok" id="sett-ok">✅ Settings saved!</div>
    <div style="margin-top:1.2rem;padding:.8rem;background:rgba(255,204,0,.04);border:1px solid rgba(255,204,0,.12);border-radius:8px">
      <div style="font-size:.65rem;color:var(--gold);font-weight:700;letter-spacing:1px;margin-bottom:.3rem">HOW TO GET GEMINI KEY (FREE)</div>
      <div style="font-size:.68rem;color:var(--t2);line-height:1.7">
        1. Go to <a href="https://aistudio.google.com/app/apikey" target="_blank" style="color:var(--c)">aistudio.google.com</a><br>
        2. Sign in with Google account<br>
        3. Click "Create API Key"<br>
        4. Copy and paste it above<br>
        5. Free tier: 15 requests/min, 1500/day
      </div>
    </div>
  </div>
</div>

<!-- STOCK ANALYSIS MODAL -->
<div class="moverlay" id="moverlay">
  <div class="modal">
    <button class="mclose" onclick="closeMod()">✕</button>
    <div id="mcont"><div class="ldc"><div class="spin"></div> Loading full analysis…</div></div>
  </div>
</div>

<header>
  <div class="logo">Fin<span style="-webkit-text-fill-color:var(--gold)">Vision</span><sub>v6</sub></div>
  <div class="hsearch" id="hsw">
    <input id="hsinp" placeholder="Search stock worldwide (TCS, AAPL, NVDA, Reliance...)" autocomplete="off" spellcheck="false"
      oninput="hsSearch(this.value)" onkeydown="if(event.key==='Enter')hsAnalyze()">
    <button class="hsbtn" onclick="hsAnalyze()">ANALYZE</button>
    <div class="sdrop" id="sdrop"></div>
  </div>
  <div class="hright">
    <div class="livebadge"><div class="ldot"></div>LIVE</div>
    <div class="hclk" id="clk"></div>
    <button class="settbtn" onclick="openSettings()">⚙️ Settings</button>
  </div>
</header>
<div class="tape"><div class="tape-r" id="tape"><span class="ti" style="color:var(--t2)">Loading live data...</span></div></div>
<nav>
  <button class="tab on" onclick="go('overview',this)">📊 Overview</button>
  <button class="tab" onclick="go('world',this)">🌍 World</button>
  <button class="tab" onclick="go('india',this)">🇮🇳 India</button>
  <button class="tab" onclick="go('impact',this)">🔗 Global→India Impact</button>
  <button class="tab" onclick="go('sectors',this)">📂 Sectors</button>
  <button class="tab" onclick="go('bonds',this)">📈 Bonds &amp; Crypto</button>
  <button class="tab" onclick="go('forex',this)">💱 Forex</button>
  <button class="tab" onclick="go('news',this)">📰 News</button>
  <button class="tab" onclick="go('chat',this)">🤖 AI Chat</button>
</nav>
<main>

<!-- OVERVIEW PANEL -->
<div id="panel-overview" class="panel on">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.2rem;flex-wrap:wrap;gap:.5rem">
    <div class="ph">Market <span>Overview</span></div>
    <div style="display:flex;align-items:center;gap:.5rem;font-size:.65rem;color:var(--t2)">
      <div class="ldot" style="background:var(--c)"></div>
      <span id="last-refresh-lbl">Auto-refresh every 5s</span>
    </div>
  </div>
  <p class="ps">Live prices · Auto-refresh every 5 seconds · Click any index to deep analyze</p>
  <div class="g2" style="margin-bottom:.9rem">
    <div class="card">
      <div class="ctitle">🇮🇳 Indian Indices <span style="font-size:.5rem;color:var(--g);margin-left:4px">● LIVE</span></div>
      <div id="ov-india"><div class="skel sm"></div><div class="skel"></div><div class="skel sm"></div><div class="skel"></div><div class="skel sm"></div></div>
    </div>
    <div class="card">
      <div class="ctitle">🌍 Global Indices <span style="font-size:.5rem;color:var(--g);margin-left:4px">● LIVE</span></div>
      <div id="ov-global"><div class="skel sm"></div><div class="skel"></div><div class="skel sm"></div><div class="skel"></div></div>
    </div>
  </div>
  <div class="g3">
    <div class="card"><div class="ctitle">🥇 Commodities &amp; Crypto</div><div id="ov-bonds"><div class="skel"></div><div class="skel sm"></div><div class="skel"></div></div></div>
    <div class="card"><div class="ctitle">💱 Key Forex</div><div id="ov-forex"><div class="skel"></div><div class="skel sm"></div></div></div>
    <div class="card">
      <div class="ctitle">📰 Top Headlines <span style="font-size:.5rem;color:var(--amber);margin-left:4px">● LIVE</span></div>
      <div id="ov-news"><div class="skel sm"></div><div class="skel"></div><div class="skel sm"></div></div>
    </div>
  </div>
</div>

<!-- WORLD PANEL -->
<div id="panel-world" class="panel">
  <div class="ph">🌍 World <span>Trend</span></div>
  <p class="ps">Global breadth · Sentiment · VIX · Fear gauge</p>
  <div id="wc"><div class="ldc"><div class="spin"></div> Loading world data…</div></div>
</div>

<!-- INDIA PANEL -->
<div id="panel-india" class="panel">
  <div class="ph">🇮🇳 India <span>Trend</span></div>
  <p class="ps">NIFTY · SENSEX · Sectors · Top Movers · INR</p>
  <div id="ic-main"><div class="ldc"><div class="spin"></div> Loading India data…</div></div>
</div>

<!-- GLOBAL → INDIA IMPACT PANEL -->
<div id="panel-impact" class="panel">
  <div class="ph">🔗 Global → India <span>Impact</span></div>
  <p class="ps">How today's global market moves affect Indian stocks & NIFTY — Live analysis</p>
  <div id="impact-c"><div class="ldc"><div class="spin"></div> Analyzing global-India linkages…</div></div>
</div>

<!-- SECTORS PANEL -->
<div id="panel-sectors" class="panel">
  <div class="ph">📂 Sector <span>Analysis</span></div>
  <p class="ps">Global ETFs &amp; Indian sector performance heatmap</p>
  <div style="display:flex;gap:.35rem;margin-bottom:.9rem;flex-wrap:wrap" id="sec-btns">
    <button class="tab on" onclick="setSP('week',this)" style="border-radius:15px;padding:4px 12px;font-size:.65rem">1 Week</button>
    <button class="tab" onclick="setSP('month',this)" style="border-radius:15px;padding:4px 12px;font-size:.65rem">1 Month</button>
    <button class="tab" onclick="setSP('quarter',this)" style="border-radius:15px;padding:4px 12px;font-size:.65rem">3 Months</button>
  </div>
  <div id="sec-c"><div class="ldc"><div class="spin"></div> Loading sectors…</div></div>
</div>

<!-- BONDS PANEL -->
<div id="panel-bonds" class="panel">
  <div class="ph">📈 Bonds <span>&amp; Crypto</span></div>
  <p class="ps">Gold · Silver · Oil · Bitcoin · Ethereum · Treasuries</p>
  <div class="g5" id="bonds-g"><div class="ldc" style="grid-column:1/-1"><div class="spin"></div> Loading…</div></div>
</div>

<!-- FOREX PANEL -->
<div id="panel-forex" class="panel">
  <div class="ph">💱 <span>Forex</span></div>
  <p class="ps">USD/INR &amp; major currency pairs · Live rates</p>
  <div class="g5" id="forex-g"><div class="ldc" style="grid-column:1/-1"><div class="spin"></div> Loading…</div></div>
</div>

<!-- NEWS PANEL -->
<div id="panel-news" class="panel">
  <div class="ph">📰 Market <span>News</span></div>
  <p class="ps">Yahoo Finance · Economic Times · Moneycontrol · LiveMint · Reuters · CNBC TV18 — Auto-rotates every 60s</p>
  <div class="news-rotate-bar"><div class="news-rotate-fill" id="news-rot-fill" style="width:0%"></div></div>
  <div class="news-cnt" id="news-cnt">Loading headlines…</div>
  <div id="news-c"><div class="ldc"><div class="spin"></div> Fetching news from 6 sources…</div></div>
</div>

<!-- CHAT PANEL -->
<div id="panel-chat" class="panel">
  <div class="ph">🤖 AI <span>Analyst</span></div>
  <p class="ps">8-Factor Future Score · Live data · Koi bhi language · Gemini + Claude powered</p>
  <div class="chatwrap">
    <div class="chhead">
      <div class="chavatar">🤖</div>
      <div style="flex:1">
        <div style="font-weight:700;font-size:.88rem">FinVision AI v6 — 8-Factor Future Engine</div>
        <div style="font-size:.65rem;color:var(--t2)">Hindi · English · Hinglish · Tamil · Marathi · Telugu · Any language</div>
      </div>
      <div id="gem-status" class="gemini-status gs-inactive">Gemini: OFF</div>
    </div>
    <div class="chmsg" id="chmsg">
      <div class="msg ma">🙏 Namaste! Main hoon FinVision AI v6 — ab Global→India Impact + 8-Factor Future Engine ke saath!

🔑 <strong>Gemini AI Setup:</strong> Header mein ⚙️ Settings click karo aur apna FREE Gemini API key paste karo.

🔮 <strong>8 Factors:</strong> Analyst (28%) · Growth (20%) · Valuation (15%) · Health (12%) · Technical (10%) · Ownership (8%) · 52W (4%) · Short (3%)

🌍→🇮🇳 <strong>Global Impact Tab:</strong> Dekho kaise S&P500, Crude, DXY India ko affect karta hai!

<strong>Try karo:</strong>
• "TCS future outlook kya hai?"
• "NVIDIA analysis with global impact"
• "Reliance mein invest karein?"
• "Aaj global market India ko kaise affect karega?"</div>
    </div>
    <div class="qps">
      <button class="qp" onclick="qp('TCS 8-factor future performance analysis')">TCS Future Score</button>
      <button class="qp" onclick="qp('Reliance ka future outlook kya hai?')">Reliance (Hindi)</button>
      <button class="qp" onclick="qp('NVIDIA short medium long term analysis')">NVIDIA All Horizons</button>
      <button class="qp" onclick="qp('Global market India ko aaj kaise affect karega?')">Global→India Impact</button>
      <button class="qp" onclick="qp('Aaj India market kaisa hai?')">India Today</button>
      <button class="qp" onclick="qp('HDFC Bank vs ICICI Bank future comparison')">HDFC vs ICICI</button>
      <button class="qp" onclick="qp('Crude oil rising hai, India pe kya asar hoga?')">Crude Oil Impact</button>
      <button class="qp" onclick="qp('Gold vs Bitcoin abhi kaun behtar?')">Gold vs BTC</button>
    </div>
    <div style="font-size:.6rem;color:var(--t3);padding:.25rem .9rem;text-align:center">
      💬 Hindi, English, Hinglish, Tamil, Marathi, Telugu, Gujarati — koi bhi language chalti hai
    </div>
    <div class="chin-row">
      <input class="chin" id="chin" placeholder="Koi bhi sawaal, koi bhi language..." onkeydown="if(event.key==='Enter')chat()">
      <button class="chsend" id="chsend" onclick="chat()">SEND</button>
    </div>
  </div>
</div>

</main>

<script>
'use strict';
const $=id=>document.getElementById(id);
const f=(n,d=2)=>n!=null?Number(n).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const fp=n=>n!=null?`${Number(n)>0?'+':''}${f(n)}%`:'—';
const pc=n=>Number(n)>0?'up':Number(n)<0?'dn':'neu';
const bdg=n=>`<span class="bdg ${Number(n)>0?'bu':Number(n)<0?'bd':'bn'}">${fp(n)}</span>`;
const api=url=>fetch(url).then(r=>r.json()).catch(()=>({}));

// ─── CLOCK ───
const tick=()=>{$('clk').textContent=new Date().toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:true,hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'short'})+' IST'};
setInterval(tick,1000);tick();

// ─── SETTINGS ───
let _geminiKey = localStorage.getItem('fv_gemini_key') || '';
let _geminiModel = localStorage.getItem('fv_gemini_model') || 'gemini-1.5-flash';
function openSettings(){
  $('gemini-key-inp').value = _geminiKey;
  $('gemini-model-sel').value = _geminiModel;
  $('sett-overlay').classList.add('open');
  document.body.style.overflow='hidden';
}
function closeSettings(){
  $('sett-overlay').classList.remove('open');
  document.body.style.overflow='';
}
function saveSettings(){
  _geminiKey = $('gemini-key-inp').value.trim();
  _geminiModel = $('gemini-model-sel').value;
  localStorage.setItem('fv_gemini_key', _geminiKey);
  localStorage.setItem('fv_gemini_model', _geminiModel);
  $('sett-ok').style.display='block';
  updateGeminiStatus();
  setTimeout(()=>{ $('sett-ok').style.display='none'; closeSettings(); }, 1200);
}
function updateGeminiStatus(){
  const el=$('gem-status');
  if(_geminiKey){ el.textContent='Gemini: ON ✓'; el.className='gemini-status gs-active'; }
  else{ el.textContent='Gemini: OFF'; el.className='gemini-status gs-inactive'; }
}
updateGeminiStatus();

// ─── HEADER SEARCH ───
let _hsT=null;
function hsSearch(v){
  clearTimeout(_hsT);const drop=$('sdrop');
  if(!v||v.length<2){drop.classList.remove('show');return;}
  drop.innerHTML='<div class="sdrop-ldg"><div class="spin" style="display:inline-block"></div> Searching...</div>';
  drop.classList.add('show');
  _hsT=setTimeout(()=>{
    api(`/api/search/${encodeURIComponent(v)}`).then(res=>{
      if(!res||!res.length){drop.innerHTML='<div class="sdrop-ldg">No results found</div>';return;}
      drop.innerHTML=res.map(r=>`<div class="sdrop-item" onclick="selectStk('${r.ticker}','${(r.name||r.ticker).replace(/'/g,"\\'")}')">
        <span class="sdrop-nm">${r.name||r.ticker}</span><span class="sdrop-tk">${r.ticker}</span></div>`).join('');
    });
  },350);
}
function selectStk(ticker,name){$('hsinp').value=name;$('sdrop').classList.remove('show');openStock(ticker);}
function hsAnalyze(){
  const v=$('hsinp').value.trim();if(!v)return;
  $('sdrop').classList.remove('show');
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('nav .tab')[8].classList.add('on');
  $('panel-chat').classList.add('on');
  $('chin').value=`Full 8-factor future analysis of ${v}`;chat();
}
document.addEventListener('click',e=>{if(!$('hsw').contains(e.target))$('sdrop').classList.remove('show');});

// ─── TAB NAVIGATION ───
const _loaded={};
function go(name,btn){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('nav .tab').forEach(b=>b.classList.remove('on'));
  $(`panel-${name}`).classList.add('on');btn.classList.add('on');
  if(!_loaded[name]){_loaded[name]=true;
    ({world:loadWorld,india:loadIndia,impact:loadImpact,sectors:loadSectors,bonds:loadBonds,forex:loadForex,news:loadNews})[name]?.();
  }
}

// ─── LIVE PULSE ───
let _liveData={};
let _pulseInterval=null;
const PULSE_INTERVAL=5000;
const _ALL_TICKERS={
  "NIFTY 50":"^NSEI","SENSEX":"^BSESN","NIFTY BANK":"^NSEBANK",
  "NIFTY IT":"^CNXIT","NIFTY AUTO":"^CNXAUTO","NIFTY PHARMA":"^CNXPHARMA",
  "NIFTY FMCG":"^CNXFMCG","NIFTY METAL":"^CNXMETAL","NIFTY REALTY":"^CNXREALTY",
  "S&P 500":"^GSPC","NASDAQ":"^IXIC","Dow Jones":"^DJI",
  "FTSE 100":"^FTSE","DAX":"^GDAXI","Nikkei 225":"^N225","Hang Seng":"^HSI",
  "Gold":"GC=F","Bitcoin":"BTC-USD","Crude Oil (WTI)":"CL=F","Ethereum":"ETH-USD",
  "USD/INR":"USDINR=X"
};
function startPulse(){
  if(_pulseInterval)clearInterval(_pulseInterval);
  pulseFetch();
  _pulseInterval=setInterval(pulseFetch,PULSE_INTERVAL);
  animateRing();
}
async function pulseFetch(){
  const tickers=Object.values(_ALL_TICKERS).join(',');
  try{
    const data=await fetch(`/api/live-pulse?tickers=${encodeURIComponent(tickers)}`).then(r=>r.json());
    if(!data||!data.prices)return;
    const prices=data.prices;
    for(const[name,ticker]of Object.entries(_ALL_TICKERS)){
      const fresh=prices[ticker];
      if(!fresh)continue;
      const old=_liveData[ticker];
      const changed=!old||old.price!==fresh.price;
      _liveData[ticker]=fresh;
      if(changed&&old)flashLiveElements(ticker,fresh,old);
    }
    updateLiveDOM();
    $('last-refresh-lbl').textContent='Updated '+new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true});
  }catch(e){}
}
function flashLiveElements(ticker,fresh,old){
  const dir=fresh.price>old.price?'up':fresh.price<old.price?'dn':null;
  if(!dir)return;
  const cls=dir==='up'?'flash-up':'flash-dn';
  document.querySelectorAll(`[data-live="${ticker}"]`).forEach(el=>{
    el.classList.remove('flash-up','flash-dn');el.offsetWidth;el.classList.add(cls);
    setTimeout(()=>el.classList.remove(cls),700);
  });
}
function updateLiveDOM(){
  const indiaKeys=["NIFTY 50","SENSEX","NIFTY BANK","NIFTY IT","NIFTY AUTO","NIFTY PHARMA","NIFTY FMCG","NIFTY METAL","NIFTY REALTY"];
  const globalKeys=["S&P 500","NASDAQ","Dow Jones","FTSE 100","DAX","Nikkei 225","Hang Seng"];
  [...indiaKeys,...globalKeys].forEach(nm=>{
    const tk=_ALL_TICKERS[nm];if(!tk)return;
    const d=_liveData[tk];if(!d)return;
    const el=document.querySelector(`[data-live-row="${tk}"]`);
    if(el){const c=pc(d.change_pct);el.querySelector('.sv').innerHTML=`${f(d.price)} <span class="${c}" data-live="${tk}">${fp(d.change_pct)}</span>`;}
  });
  updateTapeLive();
}
function updateTapeLive(){
  const tapeEl=$('tape');if(!tapeEl)return;
  const items=Object.entries(_ALL_TICKERS).map(([nm,tk])=>{
    const d=_liveData[tk];if(!d||!d.price)return null;
    const c=pc(d.change_pct);
    return `<span class="ti" data-live="${tk}"><span class="tn">${nm}</span> <span class="tp">${f(d.price)}</span> <span class="${c}">${fp(d.change_pct)}</span></span>`;
  }).filter(Boolean);
  if(items.length)tapeEl.innerHTML=items.join('')+items.join('');
}
function animateRing(){
  const circumference=2*Math.PI*15;
  const fill=$('rring-fill');if(!fill)return;
  fill.style.strokeDasharray=circumference;fill.style.strokeDashoffset=circumference;
  let start=null;
  function step(ts){
    if(!start)start=ts;
    const elapsed=ts-start;const progress=Math.min(elapsed/PULSE_INTERVAL,1);
    fill.style.strokeDashoffset=circumference*(1-progress);
    if(progress<1)requestAnimationFrame(step);else{start=null;requestAnimationFrame(step);}
  }
  requestAnimationFrame(step);
}
function forceRefresh(){pulseFetch();}

// ─── OVERVIEW ───
async function loadOverview(){
  loadTape();
  const[india,global,bonds,forex]=await Promise.all([
    api('/api/indices/india'),api('/api/indices/global'),api('/api/bonds'),api('/api/forex')
  ]);
  $('ov-india').innerHTML=Object.entries(india).map(([n,v])=>{
    if(!v||!v.price)return'';
    const tk=_ALL_TICKERS[n]||'';const c=pc(v.change_pct);
    return `<div class="sr" data-live-row="${tk}" style="cursor:pointer" onclick="openStock('${tk||n}')"><span class="sl">${n}</span><span class="sv">${f(v.price)} <span class="${c}" data-live="${tk}">${fp(v.change_pct)}</span></span></div>`;
  }).join('')||'<p style="color:var(--t2);font-size:.75rem">No data</p>';
  $('ov-global').innerHTML=Object.entries(global).map(([n,v])=>{
    if(!v||!v.price)return'';
    const tk=_ALL_TICKERS[n]||'';const c=pc(v.change_pct);
    return `<div class="sr" data-live-row="${tk}"><span class="sl">${n}</span><span class="sv">${f(v.price)} <span class="${c}" data-live="${tk}">${fp(v.change_pct)}</span></span></div>`;
  }).join('')||'<p style="color:var(--t2);font-size:.75rem">No data</p>';
  const bkeys=['Gold','Silver','Crude Oil (WTI)','Bitcoin','Ethereum','Solana'];
  $('ov-bonds').innerHTML=bkeys.map(k=>{
    const v=bonds[k];if(!v||!v.price)return'';const c=pc(v.change_pct);
    return `<div class="sr"><span class="sl">${k}</span><span class="sv">${f(v.price)} <span class="${c}">${fp(v.change_pct)}</span></span></div>`;
  }).join('')||'<p style="color:var(--t2);font-size:.75rem">No data</p>';
  const fkeys=['USD/INR','EUR/USD','GBP/USD','USD/JPY'];
  $('ov-forex').innerHTML=fkeys.map(k=>{
    const v=forex[k];if(!v||!v.price)return'';const c=pc(v.change_pct);
    return `<div class="sr"><span class="sl">${k}</span><span class="sv">${f(v.price,4)} <span class="${c}">${fp(v.change_pct)}</span></span></div>`;
  }).join('')||'<p style="color:var(--t2);font-size:.75rem">No data</p>';
  // Load overview news
  loadOverviewNews();
  for(const[n,v]of Object.entries({...india,...global})){
    const tk=_ALL_TICKERS[n];if(tk&&v&&v.price)_liveData[tk]=v;
  }
  startPulse();
}
async function loadOverviewNews(){
  const news=await api('/api/news');
  const items=(news||[]).slice(0,5);
  $('ov-news').innerHTML=items.map(n=>
    `<div class="sr" style="flex-direction:column;align-items:flex-start;gap:2px;padding:.4rem 0">
      <a href="${n.url}" target="_blank" rel="noopener" style="color:var(--t);text-decoration:none;font-size:.72rem;line-height:1.45;font-weight:500">${n.title.slice(0,75)}${n.title.length>75?'…':''}</a>
      <span style="font-size:.58rem;color:var(--t3)">${n.source} · ${n.time}</span>
    </div>`
  ).join('')||'<p style="color:var(--t2);font-size:.75rem">No news</p>';
}
async function loadTape(){
  const[a,b]=await Promise.all([api('/api/indices/india'),api('/api/indices/global')]);
  const all={...a,...b};
  const items=Object.entries(all).filter(([,v])=>v&&v.price).map(([nm,d])=>{
    const c=pc(d.change_pct);const tk=_ALL_TICKERS[nm]||'';
    return `<span class="ti" data-live="${tk}"><span class="tn">${nm}</span> <span class="tp">${f(d.price)}</span> <span class="${c}">${fp(d.change_pct)}</span></span>`;
  });
  if(items.length)$('tape').innerHTML=items.join('')+items.join('');
}

// ─── WORLD ───
async function loadWorld(){
  $('wc').innerHTML='<div class="ldc"><div class="spin"></div> Fetching global data…</div>';
  const d=await api('/api/world-trend');
  const s=d.sentiment||'Neutral';
  const sc=s==='Bullish'?'bull':s==='Bearish'?'bear':'side';
  const scol=s==='Bullish'?'var(--g)':s==='Bearish'?'var(--r)':'var(--gold)';
  const iH=Object.entries(d.indices||{}).map(([n,v])=>{
    if(!v||!v.price)return'';const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');
  $('wc').innerHTML=`
    <div class="g3" style="margin-bottom:.9rem">
      <div class="sentbox ${sc}"><div class="sb-lbl">Global Sentiment</div><div class="sb-val" style="color:${scol}">${s}</div><div class="sb-sub">Avg: ${d.avg_change>0?'+':''}${d.avg_change}%</div></div>
      <div class="card">
        <div class="ctitle">Market Breadth</div>
        <div class="bbar"><div class="btrack"><div class="bfill" style="width:${d.breadth_pct||50}%"></div></div><div class="bnums">${d.up_count}↑ ${d.down_count}↓</div></div>
        <div style="font-size:.65rem;color:var(--t2);margin:.3rem 0 .5rem">${d.breadth_pct||50}% markets advancing</div>
        <div class="sr"><span class="sl">Top Gainer</span><span class="sv up">${d.top_gainer||'—'}</span></div>
        <div class="sr"><span class="sl">Top Loser</span><span class="sv dn">${d.top_loser||'—'}</span></div>
      </div>
      <div class="card">
        <div class="ctitle">Fear &amp; Dollar</div>
        <div class="sr"><span class="sl">VIX (Fear Index)</span><span class="sv" style="color:${(d.vix||20)>20?'var(--r)':'var(--g)'}">${d.vix?f(d.vix,2):'—'}</span></div>
        <div class="sr"><span class="sl">Fear Gauge</span><span class="sv">${d.fear_gauge||'—'}</span></div>
        <div class="sr"><span class="sl">DXY (Dollar)</span><span class="sv">${d.dxy?f(d.dxy,2):'—'}</span></div>
      </div>
    </div>
    <div class="card"><div class="ctitle">All Global Indices</div><div class="g4">${iH}</div></div>`;
}

// ─── INDIA ───
async function loadIndia(){
  $('ic-main').innerHTML='<div class="ldc"><div class="spin"></div> Fetching India data…</div>';
  const[trend,stocks]=await Promise.all([api('/api/india-trend'),api('/api/stocks/india')]);
  const s=trend.sentiment||'Sideways';
  const sc=s==='Bullish'?'bull':s==='Bearish'?'bear':'side';
  const scol=s==='Bullish'?'var(--g)':s==='Bearish'?'var(--r)':'var(--gold)';
  const inrCh=trend.inr_change||0;
  const inrDir=inrCh<0?'INR Strengthening ▲':inrCh>0?'INR Weakening ▼':'Stable';
  const inrCol=inrCh<0?'var(--g)':inrCh>0?'var(--r)':'var(--gold)';
  const iH=Object.entries(trend.indices||{}).map(([n,v])=>{
    if(!v||!v.price)return'';const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');
  const topM=Object.entries(stocks).filter(([,v])=>v&&!v.error&&v.price)
    .sort((a,b)=>Math.abs(b[1].change_pct||0)-Math.abs(a[1].change_pct||0)).slice(0,15);
  const tH=topM.map(([nm,d])=>`<tr>
    <td><div class="sn">${nm}</div><div class="stk">${d.ticker||''}</div></td>
    <td>${f(d.price)}</td><td class="${pc(d.change_pct)}">${f(d.change)}</td>
    <td>${bdg(d.change_pct)}</td>
    <td>${d.pe_ratio?f(d.pe_ratio,1):'—'}</td>
    <td><button class="abtn" onclick="openStock('${d.ticker}')">Analyze</button></td>
  </tr>`).join('');
  const sbr=Math.round((trend.stocks_up||5)/((trend.stocks_up||5)+(trend.stocks_dn||5))*100);
  $('ic-main').innerHTML=`
    <div class="g3" style="margin-bottom:.9rem">
      <div class="sentbox ${sc}"><div class="sb-lbl">India Sentiment</div><div class="sb-val" style="color:${scol}">${s}</div><div class="sb-sub">Avg: ${trend.avg_change>0?'+':''}${trend.avg_change}%</div></div>
      <div class="card">
        <div class="ctitle">NIFTY &amp; SENSEX</div>
        <div class="sr"><span class="sl">NIFTY 50</span><span class="sv ${pc(trend.nifty?.change_pct)}">${f(trend.nifty?.price)} ${fp(trend.nifty?.change_pct)}</span></div>
        <div class="sr"><span class="sl">SENSEX</span><span class="sv ${pc(trend.sensex?.change_pct)}">${f(trend.sensex?.price)} ${fp(trend.sensex?.change_pct)}</span></div>
        <div style="margin-top:.5rem"><div class="bbar"><div class="btrack"><div class="bfill" style="width:${sbr}%"></div></div><div class="bnums">${trend.stocks_up}↑ ${trend.stocks_dn}↓</div></div></div>
      </div>
      <div class="card">
        <div class="ctitle">Currency</div>
        <div class="sr"><span class="sl">USD/INR</span><span class="sv">${trend.usdinr?f(trend.usdinr,2):'—'}</span></div>
        <div class="sr"><span class="sl">INR Direction</span><span class="sv" style="color:${inrCol}">${inrDir}</span></div>
        <div class="sr"><span class="sl">INR Change</span><span class="sv">${inrCh?fp(-inrCh):'—'}</span></div>
      </div>
    </div>
    <div class="card" style="margin-bottom:.9rem"><div class="ctitle">Sector Indices</div><div class="g4">${iH}</div></div>
    <div class="card"><div class="ctitle">Top Movers — Indian Stocks</div>
      <div class="tbl-wrap"><table class="tbl"><thead><tr>
        <th>Stock</th><th>Price (₹)</th><th>Chg</th><th>%</th><th>P/E</th><th></th>
      </tr></thead><tbody>${tH}</tbody></table></div>
    </div>`;
}

// ─── GLOBAL → INDIA IMPACT ───
async function loadImpact(){
  $('impact-c').innerHTML='<div class="ldc"><div class="spin"></div> Analyzing global-India market linkages…</div>';
  const d=await api('/api/global-india-impact');
  const impacts=d.impacts||[];
  const overall=d.overall||{};
  const sig=overall.overall_signal||'Neutral';
  const sigCol=sig==='Bullish'?'var(--g)':sig==='Bearish'?'var(--r)':'var(--gold)';
  const netMove=overall.net_expected_nifty_move||0;
  const moveClass=netMove>0?'pos':netMove<0?'neg':'neu';
  const headerH=`
    <div class="impact-header">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem">
        <div>
          <div style="font-size:.58rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--t2);margin-bottom:.3rem">TODAY'S GLOBAL → INDIA SIGNAL</div>
          <div class="impact-signal"><span style="color:${sigCol}">${sig}</span>
            <span class="impact-move ${moveClass}">${netMove>0?'+':''}${netMove}% est. NIFTY move</span>
          </div>
          <div style="font-size:.7rem;color:var(--t2);margin-top:.3rem">
            NIFTY 50: <strong style="color:var(--t)">${f(overall.nifty_current)}</strong>
            <span class="${pc(overall.nifty_change)}" style="margin-left:5px">${fp(overall.nifty_change)}</span>
          </div>
        </div>
        <div style="text-align:right">
          <div style="font-size:.58rem;color:var(--t3);letter-spacing:1px">BASED ON ${impacts.length} GLOBAL FACTORS</div>
          <div style="font-size:.65rem;color:var(--t2);margin-top:.2rem">Live data · Updates every 2 min</div>
        </div>
      </div>
    </div>`;
  const impH=impacts.map(imp=>{
    const dirClass=imp.direction==='positive'?'positive':imp.direction==='negative'?'negative':'mixed';
    const chgClass=pc(imp.change);
    const moveVal=imp.expected_nifty_move||0;
    const moveCls=moveVal>0?'pos':moveVal<0?'neg':'neu';
    const magCls='mag-'+(imp.magnitude||'mild');
    return `<div class="impact-card ${dirClass}">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:.5rem;flex-wrap:wrap">
        <div style="flex:1">
          <div class="impact-src">
            <span style="font-size:1rem">${imp.icon}</span>
            <span>${imp.source}</span>
            <span class="${chgClass}" style="font-family:'Share Tech Mono',monospace;font-size:.72rem">${fp(imp.change)}</span>
            <span class="imp-mag ${magCls}">${imp.magnitude}</span>
            <span style="font-size:.58rem;color:var(--t3)">Confidence: ${imp.confidence}</span>
          </div>
          <div class="impact-reason">${imp.reason}</div>
          <div class="impact-sector">📍 ${imp.sector_impact}</div>
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:.55rem;color:var(--t3);margin-bottom:2px">Est. NIFTY</div>
          <div class="impact-move ${moveCls}">${moveVal>0?'+':''}${moveVal}%</div>
        </div>
      </div>
    </div>`;
  }).join('');
  const risks=overall.key_risks||[];
  const tails=overall.key_tailwinds||[];
  const rtH=`
    <div class="risk-tail-grid">
      <div class="risk-box risks">
        <div style="font-size:.6rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--r);margin-bottom:.5rem">⚠️ Key Risks Today</div>
        ${risks.length?risks.map(r=>`<div class="risk-item">${r}</div>`).join(''):'<div class="risk-item" style="color:var(--g)">No major risks identified</div>'}
      </div>
      <div class="risk-box tails">
        <div style="font-size:.6rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:var(--g);margin-bottom:.5rem">🚀 Key Tailwinds Today</div>
        ${tails.length?tails.map(t=>`<div class="risk-item">${t}</div>`).join(''):'<div class="risk-item" style="color:var(--t2)">No major tailwinds identified</div>'}
      </div>
    </div>`;
  const howH=`
    <div class="card" style="margin-top:.9rem">
      <div class="ctitle">📚 How Global Markets Affect India — Explained</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:.7rem">
        ${[
          ['🇺🇸 S&P 500 / Dow Jones','When US markets rise, FII (Foreign Institutional Investors) feel confident → they buy Indian stocks → NIFTY rises. Indian IT companies (TCS, Infosys) earn in USD, so US market health directly impacts them.'],
          ['🛢️ Crude Oil Price','India imports ~85% of its oil. Rising crude = higher import bill = wider Current Account Deficit = INR weakens = inflation rises = RBI raises rates = stock markets fall. Only ONGC, Oil India benefit.'],
          ['💱 USD/INR Rate','Weak INR (high USD/INR) = IT exporters earn more in INR = TCS, Infosys rally. But importers (electronics, pharma ingredients) suffer. FIIs may reduce exposure due to currency risk.'],
          ['🏛️ US Bond Yields','High US 10Y yield (>4.5%) attracts global money to "safe" US bonds → FIIs pull out from India → NIFTY falls. Low yields = money flows to EM (Emerging Markets) like India = bullish.'],
          ['🇨🇳 China Markets','China is India\'s largest trade partner. Strong China = high demand for metals (coal, iron) = Tata Steel, SAIL, Hindalco benefit. Weak China = commodity price crash = metal stocks fall.'],
          ['🥇 Gold Price','India is world\'s #1 gold consumer. Rising gold = Titan, Kalyan, PC Jeweller rally. Also signals global fear/uncertainty. RBI gold reserves strengthen INR when gold rises.'],
        ].map(([title,text])=>`
          <div style="background:var(--s2);border:1px solid var(--border);border-radius:8px;padding:.75rem">
            <div style="font-size:.72rem;font-weight:700;color:var(--c);margin-bottom:.3rem">${title}</div>
            <div style="font-size:.68rem;color:var(--t2);line-height:1.65">${text}</div>
          </div>`).join('')}
      </div>
    </div>`;
  $('impact-c').innerHTML=headerH+`<div style="margin-bottom:.7rem">${impH}</div>`+rtH+howH+
    `<div style="font-size:.62rem;color:var(--t3);text-align:center;padding:.8rem 0">
      ⚠️ Impact analysis is indicative only. Actual market movements depend on many factors. Educational purpose only.
    </div>`;
}

// ─── SECTORS ───
let _secData=null,_secP='week';
async function loadSectors(){
  $('sec-c').innerHTML='<div class="ldc"><div class="spin"></div> Loading sectors…</div>';
  _secData=await api('/api/sectors');renderSectors();
}
function setSP(p,btn){_secP=p;document.querySelectorAll('#sec-btns .tab').forEach(b=>b.classList.remove('on'));btn.classList.add('on');if(_secData)renderSectors();}
function renderSectors(){
  if(!_secData)return;
  const p=_secP;
  const data=Object.entries(_secData).filter(([,v])=>v&&v[p]!=null).sort((a,b)=>(b[1][p]||0)-(a[1][p]||0));
  const mx=Math.max(...data.map(([,v])=>Math.abs(v[p]||0)),1);
  const global=data.filter(([,v])=>v.region==='Global');
  const indian=data.filter(([,v])=>v.region==='India');
  const top5=data.slice(0,5),bot5=data.slice(-5).reverse();
  const tcard=`<div class="g2" style="margin-bottom:.9rem">
    <div class="card"><div class="ctitle">🏆 Top Sectors</div>${top5.map(([nm,v])=>{const val=v[p]||0;const rC=v.region==='India'?'ri':'rg';
      return `<div class="sr"><span class="sl" style="display:flex;align-items:center;gap:5px">${nm}<span class="reg ${rC}">${v.region}</span></span><span class="sv up">+${f(val)}%</span></div>`;}).join('')}</div>
    <div class="card"><div class="ctitle">📉 Worst Sectors</div>${bot5.map(([nm,v])=>{const val=v[p]||0;const rC=v.region==='India'?'ri':'rg';
      return `<div class="sr"><span class="sl" style="display:flex;align-items:center;gap:5px">${nm}<span class="reg ${rC}">${v.region}</span></span><span class="sv dn">${f(val)}%</span></div>`;}).join('')}</div>
  </div>`;
  const rl=(items,title)=>{
    if(!items.length)return'';
    return `<div class="card" style="margin-bottom:.8rem"><div class="ctitle">${title}</div>${items.map(([nm,v])=>{
      const val=v[p]||0,pct=Math.abs(val)/mx*100;
      const col=val>0?'var(--g)':val<0?'var(--r)':'var(--t2)';
      const bg=val>0?'rgba(0,255,136,.65)':'rgba(255,34,68,.65)';
      const rC=v.region==='India'?'ri':'rg';
      return `<div class="sbar-row"><div class="sbar-nm" title="${nm}">${nm}</div>
        <div class="sbar-track"><div class="sbar-fill" style="width:${pct}%;background:${bg}"></div></div>
        <div class="sbar-val" style="color:${col}">${val>0?'+':''}${val}%</div>
        <div class="reg ${rC}">${v.region}</div></div>`;}).join('')}</div>`;
  };
  $('sec-c').innerHTML=tcard+rl(global,'🌍 Global Sector ETFs')+rl(indian,'🇮🇳 Indian Sector Indices');
}

// ─── BONDS / FOREX ───
async function loadBonds(){
  const d=await api('/api/bonds');
  $('bonds-g').innerHTML=Object.entries(d).map(([n,v])=>{
    if(!v||!v.price)return `<div class="ic"><div class="in">${n}</div><div class="ip" style="color:var(--t2)">N/A</div></div>`;
    const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');
}
async function loadForex(){
  const d=await api('/api/forex');
  $('forex-g').innerHTML=Object.entries(d).map(([n,v])=>{
    if(!v||!v.price)return `<div class="ic"><div class="in">${n}</div><div class="ip" style="color:var(--t2)">N/A</div></div>`;
    const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price,4)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');
}

// ─── NEWS with 60s rotation ───
let _allNews=[];
let _newsPage=0;
let _newsPerPage=12;
let _newsRotTimer=null;
let _newsRotProgress=0;
const NEWS_ROTATE_INTERVAL=60000; // 60 seconds

async function loadNews(){
  $('news-c').innerHTML='<div class="ldc"><div class="spin"></div> Fetching news from 6 sources…</div>';
  _allNews=await api('/api/news');
  _newsPage=0;
  renderNewsBatch();
  startNewsRotation();
}

function renderNewsBatch(){
  if(!_allNews||!_allNews.length){
    $('news-c').innerHTML='<p style="color:var(--t2);padding:.5rem">No news available</p>';return;
  }
  // Rotate through different pages
  const total=_allNews.length;
  const start=(_newsPage*_newsPerPage)%total;
  let batch=[];
  for(let i=0;i<_newsPerPage;i++){
    batch.push(_allNews[(start+i)%total]);
  }
  // Source color map
  const srcColors={'Yahoo Finance':'#6264f5','Economic Times':'#e85d4a','Moneycontrol':'#3ab5e6','LiveMint':'#2d9c63','Reuters':'#ff8100','CNBC TV18':'#0078d4'};
  $('news-cnt').textContent=`Showing ${batch.length} of ${total} headlines · Page ${_newsPage+1} · Rotates in 60s`;
  $('news-c').innerHTML=`<div class="news-grid">${batch.map(n=>{
    const col=srcColors[n.source]||'var(--c)';
    return `<div class="news-card" style="--card-accent:${col}">
      <div class="news-src-badge" style="background:${col}18;color:${col};border-color:${col}30">${n.source}</div>
      <div class="news-title"><a href="${n.url}" target="_blank" rel="noopener">${n.title}</a></div>
      <div class="news-meta">
        <div class="news-dot"></div>
        <span>${n.time}</span>
      </div>
    </div>`;
  }).join('')}</div>`;
}

function startNewsRotation(){
  if(_newsRotTimer)clearInterval(_newsRotTimer);
  _newsRotProgress=0;
  // Update progress bar every second
  const progressStep=100/60;
  _newsRotTimer=setInterval(()=>{
    _newsRotProgress+=progressStep;
    const fill=$('news-rot-fill');
    if(fill)fill.style.width=Math.min(_newsRotProgress,100)+'%';
    if(_newsRotProgress>=100){
      _newsRotProgress=0;
      _newsPage=(_newsPage+1);
      if(_newsPage*_newsPerPage>=_allNews.length){
        // Re-fetch fresh news every full cycle
        api('/api/news').then(data=>{
          if(data&&data.length){_allNews=data;}
          _newsPage=0;
          renderNewsBatch();
        });
      } else {
        renderNewsBatch();
      }
    }
  },1000);
}

// Overview news auto-refresh every 60s
setInterval(loadOverviewNews, 60000);

// ─── STOCK MODAL ───
let _ch=null;
async function openStock(ticker){
  $('moverlay').classList.add('open');
  document.body.style.overflow='hidden';
  $('mcont').innerHTML='<div class="ldc"><div class="spin"></div> Loading 8-Factor Future Analysis…</div>';
  const d=await api(`/api/stock/${encodeURIComponent(ticker)}?period=3mo`);
  const q=d.quote||{},fu=d.fundamentals||{},a=d.analysis||{},fo=d.future_outlook||{},h=d.history||[];
  const ol=fo.details||{},sc2=fo.scenarios||{};
  const factors=fo.factors||[];
  const horizon=fo.horizon||{};
  const c=pc(q.change_pct);
  const sigH=(a.signals||[]).map(s=>`<span class="sigchip">${s}</span>`).join('');
  const score=fo.composite_score||50;
  const rad=46,circ=2*Math.PI*rad,dash=circ*score/100;
  const gc=score>=78?'var(--g)':score>=63?'#50fa7b':score>=48?'var(--gold)':score>=33?'var(--or)':'var(--r)';
  const gcss={'green':'var(--g)','lightgreen':'#50fa7b','yellow':'var(--gold)','orange':'var(--or)','red':'var(--r)'}[fo.grade_color||'yellow'];
  const gsvg=`<div class="gauge-r" style="width:110px;height:110px"><svg viewBox="0 0 110 110" width="110" height="110">
    <circle cx="55" cy="55" r="${rad}" fill="none" stroke="rgba(255,255,255,.05)" stroke-width="10"/>
    <circle cx="55" cy="55" r="${rad}" fill="none" stroke="${gc}" stroke-width="10" stroke-dasharray="${dash} ${circ-dash}" stroke-linecap="round"/>
    </svg><div class="gauge-v"><div class="gauge-n" style="color:${gc}">${score}</div><div class="gauge-l">/ 100</div></div></div>`;
  const fpCardsH=factors.map(fac=>{
    const col=fac.score>=75?'var(--g)':fac.score>=55?'var(--c)':fac.score>=35?'var(--gold)':'var(--r)';
    return `<div class="fp-card">
      <div class="fp-icon">${fac.icon}</div>
      <div class="fp-name">${fac.name}</div>
      <div class="fp-score" style="color:${col}">${Math.round(fac.score)}</div>
      <div class="fp-wt">${fac.weight}</div>
      <div class="fp-bar"><div class="fp-bar-fill" style="width:${fac.score}%;background:${col}"></div></div>
    </div>`;
  }).join('');
  const hzCol=v=>v==='Bullish'?'var(--g)':v==='Bearish'?'var(--r)':'var(--gold)';
  const horizonH=`<div class="horizon-row">
    <div class="hz"><div class="hz-lbl">Short Term</div><div class="hz-val" style="color:${hzCol(horizon.short_term)}">${horizon.short_term||'—'}</div></div>
    <div class="hz"><div class="hz-lbl">Medium Term</div><div class="hz-val" style="color:${hzCol(horizon.medium_term)}">${horizon.medium_term||'—'}</div></div>
    <div class="hz"><div class="hz-lbl">Long Term</div><div class="hz-val" style="color:${hzCol(horizon.long_term)}">${horizon.long_term||'—'}</div></div>
  </div>`;
  const w52pos=ol.week52_position_pct;
  const w52bar=w52pos!=null?`<div style="margin:.5rem 0">
    <div style="display:flex;justify-content:space-between;font-size:.58rem;color:var(--t2);margin-bottom:2px">
      <span>52W Low: ${f(ol.week52_low)}</span><span>52W High: ${f(ol.week52_high)}</span>
    </div>
    <div style="background:var(--border);border-radius:4px;height:8px;overflow:hidden">
      <div style="width:${w52pos}%;height:100%;background:linear-gradient(90deg,var(--r),var(--gold),var(--g));border-radius:4px"></div>
    </div>
    <div style="font-size:.6rem;color:var(--t2);margin-top:2px;text-align:center">At ${w52pos}% of 52-week range</div>
  </div>`:'';
  const curr=q.price||1,mx2=Math.max(sc2.bull||curr*1.2,sc2.base||curr*1.1,sc2.bear||curr*0.9);
  const scH=sc2.bull?`
    <div class="sc-row"><div class="sc-lbl" style="color:var(--g)">Bull</div><div class="sc-bar"><div class="sc-fill" style="width:${sc2.bull/mx2*100}%;background:rgba(0,255,136,.6)"><span class="sc-price">${f(sc2.bull)} <span style="font-size:.55rem">${sc2.label_bull||''}</span></span></div></div></div>
    <div class="sc-row"><div class="sc-lbl" style="color:var(--c)">Base</div><div class="sc-bar"><div class="sc-fill" style="width:${sc2.base/mx2*100}%;background:rgba(0,229,255,.6)"><span class="sc-price">${f(sc2.base)} <span style="font-size:.55rem">${sc2.label_base||''}</span></span></div></div></div>
    <div class="sc-row"><div class="sc-lbl" style="color:var(--r)">Bear</div><div class="sc-bar"><div class="sc-fill" style="width:${sc2.bear/mx2*100}%;background:rgba(255,34,68,.6)"><span class="sc-price">${f(sc2.bear)} -15%</span></div></div></div>`
    :'<p style="color:var(--t2);font-size:.74rem">Insufficient data</p>';
  $('mcont').innerHTML=`
    <div class="mtitle">${q.name||ticker}</div>
    <div class="msub">${ticker} · ${fu.sector||'—'} · ${fu.industry||'—'}</div>
    <div class="g3" style="margin-bottom:.9rem">
      <div class="card">
        <div class="ctitle">⚡ Live Price</div>
        <div style="font-size:1.7rem;font-weight:700;font-family:'Share Tech Mono',monospace">${f(q.price)}<span style="font-size:.75rem;color:var(--t2);margin-left:4px">${q.currency||''}</span></div>
        <div class="${c}" style="font-family:'Share Tech Mono',monospace;font-size:.85rem;margin:.2rem 0">${fp(q.change_pct)} (${f(q.change)})</div>
        ${w52bar}
        <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.4rem">
          <span style="font-size:.62rem;color:var(--t2)">P/E: <span style="color:var(--t)">${q.pe_ratio?f(q.pe_ratio,1):'—'}</span></span>
          <span style="font-size:.62rem;color:var(--t2)">Vol Ratio: <span style="color:var(--t)">${a.vol_ratio?a.vol_ratio+'x':'—'}</span></span>
        </div>
      </div>
      <div class="card"><div class="ctitle">🔮 Future Score (8-Factor)</div>
        <div class="gauge-w">${gsvg}<div class="gpill" style="background:${gcss}15;color:${gcss};border:1px solid ${gcss}30;font-size:.8rem;padding:3px 14px">${fo.grade||'N/A'}</div></div>
        <div style="font-size:.62rem;color:var(--t2);text-align:center;margin-top:.3rem">Weighted composite of 8 factors</div>
      </div>
      <div class="card"><div class="ctitle">📊 Analyst View</div>
        <div class="sr"><span class="sl">Recommendation</span><span class="sv" style="color:${gcss};font-weight:700">${ol.recommendation||'—'}</span></div>
        <div class="sr"><span class="sl">12M Target</span><span class="sv" style="color:var(--c)">${f(ol.analyst_target)}</span></div>
        <div class="sr"><span class="sl">Upside Potential</span><span class="sv ${pc(ol.analyst_upside_pct)}">${fp(ol.analyst_upside_pct)}</span></div>
        <div class="sr"><span class="sl"># Analysts</span><span class="sv">${ol.analyst_count||'—'}</span></div>
        <div class="sr"><span class="sl">RSI</span><span class="sv" style="color:${(ol.rsi||50)>70?'var(--r)':(ol.rsi||50)<30?'var(--g)':'var(--t)'}">${ol.rsi||a.rsi||'—'}</span></div>
        <div class="sr"><span class="sl">MACD Signal</span><span class="sv" style="color:${ol.macd_signal==='Bullish'?'var(--g)':'var(--r)'}">${ol.macd_signal||'—'}</span></div>
      </div>
    </div>
    <div class="card" style="margin-bottom:.9rem">
      <div class="ctitle">🎯 8-Factor Future Performance Score</div>
      <div class="fp-grid">${fpCardsH}</div>
    </div>
    <div class="card" style="margin-bottom:.9rem">
      <div class="ctitle">⏱️ Multi-Horizon Outlook</div>${horizonH}
    </div>
    <div class="card" style="margin-bottom:.9rem">
      <div class="ctitle">Price Chart — 3 Months</div>
      <div class="chwrap"><canvas id="dch"></canvas></div>
    </div>
    <div class="sigwrap" style="margin-bottom:.9rem">${sigH}</div>
    <div class="g3" style="margin-bottom:.9rem">
      <div class="card"><div class="ctitle">📈 Growth</div>
        <div class="sr"><span class="sl">Earnings Growth</span><span class="sv ${pc(ol.earnings_growth_pct)}">${ol.earnings_growth_pct!=null?fp(ol.earnings_growth_pct):'—'}</span></div>
        <div class="sr"><span class="sl">Revenue Growth</span><span class="sv ${pc(ol.revenue_growth_pct)}">${ol.revenue_growth_pct!=null?fp(ol.revenue_growth_pct):'—'}</span></div>
        <div class="sr"><span class="sl">Profit Margin</span><span class="sv">${ol.profit_margin_pct!=null?f(ol.profit_margin_pct,1)+'%':'—'}</span></div>
        <div class="sr"><span class="sl">ROE</span><span class="sv">${fu.roe?(fu.roe*100).toFixed(1)+'%':'—'}</span></div>
        <div class="sr"><span class="sl">EPS</span><span class="sv">${f(fu.eps)}</span></div>
      </div>
      <div class="card"><div class="ctitle">💰 Valuation</div>
        <div class="sr"><span class="sl">PEG Ratio</span><span class="sv" style="color:${(ol.peg_ratio||2)<1?'var(--g)':(ol.peg_ratio||2)<2?'var(--c)':'var(--r)'}">${f(ol.peg_ratio,2)}</span></div>
        <div class="sr"><span class="sl">Forward P/E</span><span class="sv">${f(ol.forward_pe,1)}</span></div>
        <div class="sr"><span class="sl">Trailing P/E</span><span class="sv">${f(ol.trailing_pe,1)}</span></div>
        <div class="sr"><span class="sl">Price/Book</span><span class="sv">${f(fu.price_to_book,2)}</span></div>
      </div>
      <div class="card"><div class="ctitle">🏥 Health</div>
        <div class="sr"><span class="sl">Debt/Equity</span><span class="sv" style="color:${(ol.debt_to_equity||100)<50?'var(--g)':(ol.debt_to_equity||100)<100?'var(--gold)':'var(--r)'}">${f(ol.debt_to_equity,1)}</span></div>
        <div class="sr"><span class="sl">Current Ratio</span><span class="sv">${f(ol.current_ratio,2)}</span></div>
        <div class="sr"><span class="sl">Free Cashflow</span><span class="sv ${pc(ol.free_cashflow_b)}">${ol.free_cashflow_b!=null?f(ol.free_cashflow_b)+'B':'—'}</span></div>
        <div class="sr"><span class="sl">Short Ratio</span><span class="sv">${f(ol.short_ratio,2)}</span></div>
        <div class="sr"><span class="sl">Dividend Yield</span><span class="sv">${ol.dividend_yield_pct!=null?f(ol.dividend_yield_pct,2)+'%':'—'}</span></div>
      </div>
    </div>
    <div class="g2" style="margin-bottom:.9rem">
      <div class="card"><div class="ctitle">🎯 1-Year Price Scenarios</div>
        <div style="font-size:.65rem;color:var(--t2);margin-bottom:.5rem">Current: <strong style="color:var(--t)">${f(curr)} ${q.currency||''}</strong></div>
        ${scH}
      </div>
      <div class="card"><div class="ctitle">📈 Technicals</div>
        ${[['RSI',`${f(a.rsi,1)} ${(a.rsi||50)>70?'🔴 OB':(a.rsi||50)<30?'🟢 OS':'Neutral'}`],
           ['MACD',a.macd&&a.signal?((a.macd>a.signal)?'Bullish ▲':'Bearish ▼'):'—'],
           ['MA20/50/200',`${f(a.ma20,0)}/${f(a.ma50,0)}/${f(a.ma200,0)}`],
           ['Support',f(a.support)],['Resistance',f(a.resistance)],
           ['OBV Trend',a.obv_trend||'—'],['Momentum',a.momentum_score?a.momentum_score+'/100':'—']
          ].map(([l,v])=>`<div class="sr"><span class="sl">${l}</span><span class="sv">${v}</span></div>`).join('')}
      </div>
    </div>
    ${fu.summary?`<div class="card" style="margin-bottom:.9rem"><div class="ctitle">About</div><p style="font-size:.78rem;line-height:1.75;color:var(--t2)">${fu.summary}</p></div>`:''}
    <div style="font-size:.62rem;color:var(--t3);text-align:center;padding:.8rem 0">
      ⚠️ Educational purpose only. Not investment advice. Consult SEBI-registered advisor before investing.
    </div>`;
  if(h.length>1){
    if(_ch){_ch.destroy();_ch=null;}
    setTimeout(()=>{
      const el=document.getElementById('dch');if(!el)return;
      const prices=h.map(x=>x.close);
      const bull=prices[prices.length-1]>=prices[0];const col=bull?'#00ff88':'#ff2244';
      _ch=new Chart(el.getContext('2d'),{type:'line',
        data:{labels:h.map(x=>x.date),datasets:[{data:prices,borderColor:col,borderWidth:1.5,fill:true,tension:.35,
          backgroundColor:ctx=>{const g=ctx.chart.ctx.createLinearGradient(0,0,0,240);g.addColorStop(0,col+'40');g.addColorStop(1,col+'00');return g;},
          pointRadius:0,pointHoverRadius:3}]},
        options:{responsive:true,maintainAspectRatio:false,
          interaction:{mode:'index',intersect:false},
          plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>` ${ctx.raw?.toFixed(2)}`}}},
          scales:{x:{grid:{color:'rgba(255,255,255,.03)'},ticks:{color:'#4a7090',maxTicksLimit:6,font:{size:9}}},
                  y:{grid:{color:'rgba(255,255,255,.03)'},ticks:{color:'#4a7090',font:{size:9}}}}}});
    },80);
  }
}
function closeMod(){$('moverlay').classList.remove('open');document.body.style.overflow='';if(_ch){_ch.destroy();_ch=null;}}
$('moverlay').addEventListener('click',e=>{if(e.target===$('moverlay'))closeMod();});
$('sett-overlay').addEventListener('click',e=>{if(e.target===$('sett-overlay'))closeSettings();});

// ─── CHAT ───
function qp(t){$('chin').value=t;chat();}
async function chat(){
  const inp=$('chin'),q=inp.value.trim();if(!q)return;
  const btn=$('chsend');btn.disabled=true;inp.value='';
  const box=$('chmsg');
  const u=document.createElement('div');u.className='msg mu';u.textContent=q;box.appendChild(u);
  const a=document.createElement('div');a.className='msg ma';
  a.innerHTML='<div class="spin" style="display:inline-block;vertical-align:middle;margin-right:5px"></div>Analyzing with 8-Factor Future Engine…';
  box.appendChild(a);box.scrollTop=box.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:q,gemini_key:_geminiKey})});
    const data=await r.json();
    let ans=(data.answer||'No response.').replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/_(.*?)_/g,'<em>$1</em>');
    a.innerHTML=ans;
  }catch(e){a.innerHTML=`<span style="color:var(--r)">Error: ${e.message}</span>`;}
  btn.disabled=false;box.scrollTop=box.scrollHeight;inp.focus();
}

// ─── INIT ───
loadOverview();
_loaded['overview']=true;
</script>
</body>
</html>"""

@app.route("/")
def index():
    if not DEPS_OK:
        return (
            "<html><body style='font-family:monospace;background:#020509;color:#c8dff0;padding:2rem'>"
            "<h2 style='color:#ff2244'>⚠️ Missing packages</h2>"
            "<p>Run: <code>pip install flask yfinance pandas numpy requests beautifulsoup4 anthropic lxml</code></p>"
            f"<p style='color:#ff2244'>Error: {MISSING}</p>"
            "</body></html>"
        )
    return _HTML

if __name__ == "__main__":
    print("""
 ╔══════════════════════════════════════════════╗
 ║   FinVision v6.0 — Enhanced Edition         ║
 ║   ✅ Global→India Impact Analysis           ║
 ║   ✅ Gemini API Key in Settings             ║
 ║   ✅ News from 6 sources, rotates 60s       ║
 ║   ✅ 8-Factor AI Score                      ║
 ║   Open: http://localhost:5000               ║
 ╚══════════════════════════════════════════════╝
""")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

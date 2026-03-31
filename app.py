#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║   FINVISION v2.0 — Global & Indian Financial Market Analyzer            ║
║   Single File · Flask Backend + HTML Frontend                            ║
║   World Trends · Indian Market · Sector Analysis · Forward Stock AI      ║
╚══════════════════════════════════════════════════════════════════════════╝

HOW TO RUN:
  1. Create virtual env:   python -m venv venv
  2. Activate (Windows):   venv\Scripts\activate
     Activate (Linux/Mac): source venv/bin/activate
  3. Install packages:     pip install flask yfinance pandas numpy requests beautifulsoup4 anthropic
  4. (Optional) Set key:   set ANTHROPIC_API_KEY=your_key_here  (Windows)
                           export ANTHROPIC_API_KEY=your_key_here (Linux/Mac)
  5. Run:                  python financial_market_analyzer.py
  6. Open browser:         http://localhost:5000
"""

import os, re, json, threading, traceback
from datetime import datetime, timedelta

try:
    from flask import Flask, jsonify, request
    import yfinance as yf
    import pandas as pd
    import numpy as np
    import requests
    from bs4 import BeautifulSoup
    DEPS_OK = True
    MISSING = ""
except ImportError as e:
    DEPS_OK = False
    MISSING = str(e)
    class Flask:
        def __init__(self, *a, **k): pass
        def route(self, *a, **k): return lambda f: f
        def run(self, *a, **k): pass
    def jsonify(*a, **k): pass
    class request:
        args = {}
        def get_json(self): return {}

try:
    import anthropic as _anthropic_lib
    _ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    AI_AVAILABLE = bool(_ANTHROPIC_KEY)
except ImportError:
    _anthropic_lib = None
    _ANTHROPIC_KEY = ""
    AI_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "finvision_v2_2024"

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────
GLOBAL_INDICES = {
    "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI",
    "FTSE 100": "^FTSE", "DAX": "^GDAXI", "Nikkei 225": "^N225",
    "Shanghai": "000001.SS", "Hang Seng": "^HSI", "CAC 40": "^FCHI", "ASX 200": "^AXJO",
}
INDIAN_INDICES = {
    "NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT", "NIFTY MIDCAP": "NIFTY_MIDCAP_100.NS",
    "NIFTY AUTO": "^CNXAUTO", "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY FMCG": "^CNXFMCG", "NIFTY METAL": "^CNXMETAL",
    "NIFTY REALTY": "^CNXREALTY",
}

# Sector ETFs for global sector trend detection
GLOBAL_SECTOR_ETFS = {
    "Technology (US)": "XLK", "Healthcare (US)": "XLV", "Financials (US)": "XLF",
    "Energy (US)": "XLE", "Consumer Disc (US)": "XLY", "Industrials (US)": "XLI",
    "Materials (US)": "XLB", "Utilities (US)": "XLU", "Real Estate (US)": "XLRE",
    "Communication (US)": "XLC", "Consumer Staples (US)": "XLP",
    "Semiconductors": "SOXX", "Clean Energy": "ICLN", "Cybersecurity": "HACK",
    "AI & Tech": "AIQ", "Biotech": "XBI",
}

INDIAN_SECTOR_INDICES = {
    "NIFTY IT": "^CNXIT", "NIFTY BANK": "^NSEBANK",
    "NIFTY AUTO": "^CNXAUTO", "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY FMCG": "^CNXFMCG", "NIFTY METAL": "^CNXMETAL",
    "NIFTY REALTY": "^CNXREALTY", "NIFTY ENERGY": "^CNXENERGY",
    "NIFTY INFRA": "^CNXINFRA", "NIFTY PSU BANK": "^CNXPSUBANK",
    "NIFTY MEDIA": "^CNXMEDIA", "NIFTY CONSUMPTION": "^CNXCONSUM",
}

POPULAR_INDIAN_STOCKS = {
    "Reliance": "RELIANCE.NS", "TCS": "TCS.NS", "Infosys": "INFY.NS",
    "HDFC Bank": "HDFCBANK.NS", "ICICI Bank": "ICICIBANK.NS", "Wipro": "WIPRO.NS",
    "HCL Tech": "HCLTECH.NS", "Bajaj Finance": "BAJFINANCE.NS",
    "Adani Ent.": "ADANIENT.NS", "ITC": "ITC.NS", "SBI": "SBIN.NS",
    "Kotak Bank": "KOTAKBANK.NS", "L&T": "LT.NS", "Asian Paints": "ASIANPAINT.NS",
    "Maruti": "MARUTI.NS", "Tata Motors": "TATAMOTORS.NS", "Sun Pharma": "SUNPHARMA.NS",
    "Titan": "TITAN.NS", "NTPC": "NTPC.NS", "Power Grid": "POWERGRID.NS",
}
POPULAR_GLOBAL_STOCKS = {
    "Apple": "AAPL", "Microsoft": "MSFT", "Google": "GOOGL", "Amazon": "AMZN",
    "Tesla": "TSLA", "NVIDIA": "NVDA", "Meta": "META", "Netflix": "NFLX",
    "Berkshire": "BRK-B", "JPMorgan": "JPM", "TSMC": "TSM", "Samsung": "005930.KS",
}
BONDS_AND_COMMODITIES = {
    "US 10Y Treasury": "^TNX", "US 2Y Treasury": "^IRX", "US 30Y Treasury": "^TYX",
    "Gold": "GC=F", "Silver": "SI=F", "Crude Oil (WTI)": "CL=F",
    "Natural Gas": "NG=F", "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "BNB": "BNB-USD",
}
FOREX_PAIRS = {
    "USD/INR": "USDINR=X", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X", "EUR/INR": "EURINR=X", "GBP/INR": "GBPINR=X",
    "AUD/USD": "AUDUSD=X", "USD/CHF": "USDCHF=X",
}

# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────
def safe_float(val, decimals=2):
    try:
        v = float(val)
        if v != v: return None
        return round(v, decimals)
    except: return None

def _fetch_quote(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="5d", auto_adjust=True)
        if hist.empty: return {"error": "No data"}
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
        change = last - prev
        pct = (change / prev * 100) if prev else 0.0
        return {
            "price": safe_float(last), "change": safe_float(change),
            "change_pct": safe_float(pct),
            "volume": safe_float(info.get("volume") or info.get("regularMarketVolume")),
            "market_cap": info.get("marketCap"),
            "pe_ratio": safe_float(info.get("trailingPE")),
            "52w_high": safe_float(info.get("fiftyTwoWeekHigh")),
            "52w_low": safe_float(info.get("fiftyTwoWeekLow")),
            "name": info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", "USD"),
        }
    except Exception as e:
        return {"error": str(e)}

def _fetch_quotes_parallel(ticker_map):
    result = {}
    def worker(name, ticker):
        result[name] = _fetch_quote(ticker)
    threads = [threading.Thread(target=worker, args=(n, t), daemon=True) for n, t in ticker_map.items()]
    for th in threads: th.start()
    for th in threads: th.join(timeout=25)
    return result

def _fetch_history(ticker, period="3mo"):
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if hist.empty: return []
        return [{"date": dt.strftime("%Y-%m-%d"), "open": safe_float(row["Open"]),
                 "high": safe_float(row["High"]), "low": safe_float(row["Low"]),
                 "close": safe_float(row["Close"]), "volume": safe_float(row["Volume"])}
                for dt, row in hist.iterrows()]
    except: return []

def _fetch_fundamentals(ticker):
    try:
        info = yf.Ticker(ticker).info
        return {
            "sector": info.get("sector", "N/A"), "industry": info.get("industry", "N/A"),
            "employees": info.get("fullTimeEmployees"),
            "summary": (info.get("longBusinessSummary") or "")[:600],
            "eps": safe_float(info.get("trailingEps")),
            "revenue": info.get("totalRevenue"),
            "profit_margin": safe_float(info.get("profitMargins")),
            "debt_equity": safe_float(info.get("debtToEquity")),
            "roe": safe_float(info.get("returnOnEquity")),
            "roa": safe_float(info.get("returnOnAssets")),
            "current_ratio": safe_float(info.get("currentRatio")),
            "beta": safe_float(info.get("beta")),
            "dividend_yield": safe_float(info.get("dividendYield")),
            "peg_ratio": safe_float(info.get("pegRatio")),
            "book_value": safe_float(info.get("bookValue")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "analyst_target": safe_float(info.get("targetMeanPrice")),
            "analyst_low": safe_float(info.get("targetLowPrice")),
            "analyst_high": safe_float(info.get("targetHighPrice")),
            "recommendation": info.get("recommendationKey", ""),
            "num_analyst_opinions": info.get("numberOfAnalystOpinions"),
            "earnings_growth": safe_float(info.get("earningsGrowth")),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "gross_margins": safe_float(info.get("grossMargins")),
            "operating_margins": safe_float(info.get("operatingMargins")),
            "free_cashflow": info.get("freeCashflow"),
            "insider_pct": safe_float(info.get("heldPercentInsiders")),
            "institution_pct": safe_float(info.get("heldPercentInstitutions")),
            "short_ratio": safe_float(info.get("shortRatio")),
            "payout_ratio": safe_float(info.get("payoutRatio")),
        }
    except: return {}

def _technical_analysis(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        if hist.empty or len(hist) < 30: return {}
        close = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float)

        ma20 = close.rolling(20).mean().iloc[-1]
        ma50 = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(200, min_periods=50).mean().iloc[-1]
        curr = close.iloc[-1]

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

        # Volume analysis
        avg_vol_20 = float(volume.rolling(20).mean().iloc[-1])
        curr_vol = float(volume.iloc[-1])
        vol_ratio = curr_vol / avg_vol_20 if avg_vol_20 else 1.0

        # OBV (On Balance Volume)
        obv = []
        obv_val = 0
        closes_list = close.tolist()
        vols_list = volume.tolist()
        for i in range(1, len(closes_list)):
            if closes_list[i] > closes_list[i-1]: obv_val += vols_list[i]
            elif closes_list[i] < closes_list[i-1]: obv_val -= vols_list[i]
            obv.append(obv_val)
        obv_trend = "Rising" if len(obv) > 5 and obv[-1] > obv[-5] else "Falling"

        # Momentum score (0-100)
        score = 50
        if curr > ma20: score += 8
        if curr > ma50: score += 8
        if curr > ma200: score += 9
        if macd > signal: score += 10
        if rsi < 70 and rsi > 30: score += 5
        if rsi > 50: score += 5
        if vol_ratio > 1.2: score += 5
        if obv_trend == "Rising": score += 10
        score = min(100, max(0, score))

        signals = []
        if curr > ma20: signals.append("Above MA20 ▲")
        else: signals.append("Below MA20 ▼")
        if curr > ma50: signals.append("Above MA50 ▲")
        else: signals.append("Below MA50 ▼")
        if rsi < 30: signals.append("Oversold RSI<30 🟢")
        elif rsi > 70: signals.append("Overbought RSI>70 🔴")
        else: signals.append(f"RSI Neutral ({rsi:.1f})")
        if macd > signal: signals.append("MACD Bullish ▲")
        else: signals.append("MACD Bearish ▼")
        if vol_ratio > 1.5: signals.append(f"High Volume {vol_ratio:.1f}x ⚡")

        return {
            "current_price": safe_float(curr), "ma20": safe_float(ma20),
            "ma50": safe_float(ma50), "ma200": safe_float(ma200),
            "rsi": safe_float(rsi, 2), "macd": safe_float(macd, 4),
            "signal": safe_float(signal, 4), "bb_upper": safe_float(bb_upper),
            "bb_lower": safe_float(bb_lower), "support": support, "resistance": resistance,
            "vol_ratio": safe_float(vol_ratio, 2), "obv_trend": obv_trend,
            "momentum_score": score, "signals": signals,
        }
    except Exception as e:
        return {"error": str(e)}

# ──────────────────────────────────────────────────────────────
# FUTURE OUTLOOK ANALYSIS (Multi-source)
# ──────────────────────────────────────────────────────────────
def _future_outlook(ticker):
    """Compute a forward-looking score from multiple data feeds."""
    try:
        t = yf.Ticker(ticker)
        info = t.info

        score_components = {}
        outlook = {}

        # 1. Analyst consensus
        rec = info.get("recommendationKey", "").lower()
        analyst_score = {"strong_buy": 90, "buy": 75, "hold": 50, "sell": 25, "strong_sell": 10}.get(rec, 50)
        num_analysts = info.get("numberOfAnalystOpinions", 0) or 0
        target_mean = safe_float(info.get("targetMeanPrice"))
        current = safe_float(info.get("currentPrice") or info.get("regularMarketPrice"))
        upside = None
        if target_mean and current and current > 0:
            upside = round(((target_mean - current) / current) * 100, 2)
        score_components["analyst_consensus"] = analyst_score
        outlook["analyst_target"] = target_mean
        outlook["analyst_upside_pct"] = upside
        outlook["analyst_count"] = num_analysts
        outlook["recommendation"] = rec.replace("_", " ").title() if rec else "N/A"

        # 2. Earnings growth trajectory
        eg = info.get("earningsGrowth")
        rg = info.get("revenueGrowth")
        eg_score = 50
        if eg is not None:
            if eg > 0.3: eg_score = 90
            elif eg > 0.15: eg_score = 75
            elif eg > 0.05: eg_score = 60
            elif eg > 0: eg_score = 50
            else: eg_score = 25
        score_components["earnings_growth"] = eg_score
        outlook["earnings_growth_pct"] = safe_float(eg * 100, 1) if eg else None
        outlook["revenue_growth_pct"] = safe_float(rg * 100, 1) if rg else None

        # 3. Valuation attractiveness (Forward PE vs Trailing PE)
        fpe = info.get("forwardPE")
        tpe = info.get("trailingPE")
        val_score = 50
        if fpe:
            if fpe < 15: val_score = 85
            elif fpe < 25: val_score = 70
            elif fpe < 40: val_score = 50
            else: val_score = 30
        if fpe and tpe and fpe < tpe:
            val_score = min(95, val_score + 10)  # earnings expected to grow
        score_components["valuation"] = val_score
        outlook["forward_pe"] = safe_float(fpe, 2) if fpe else None
        outlook["trailing_pe"] = safe_float(tpe, 2) if tpe else None
        outlook["pe_expansion"] = "Positive" if (fpe and tpe and fpe < tpe) else "Negative" if (fpe and tpe) else "N/A"

        # 4. Financial health (debt, cash flow)
        de = info.get("debtToEquity")
        cr = info.get("currentRatio")
        fcf = info.get("freeCashflow")
        health_score = 50
        if de is not None:
            if de < 30: health_score += 20
            elif de < 60: health_score += 10
            elif de > 150: health_score -= 20
        if cr is not None:
            if cr > 2: health_score += 15
            elif cr > 1: health_score += 5
            else: health_score -= 15
        if fcf and fcf > 0: health_score += 10
        health_score = min(100, max(0, health_score))
        score_components["financial_health"] = health_score
        outlook["debt_to_equity"] = safe_float(de, 2) if de else None
        outlook["current_ratio"] = safe_float(cr, 2) if cr else None
        outlook["free_cashflow_b"] = round(fcf / 1e9, 2) if fcf else None

        # 5. Insider & institutional ownership (confidence signal)
        ins_pct = info.get("heldPercentInsiders", 0) or 0
        inst_pct = info.get("heldPercentInstitutions", 0) or 0
        own_score = 50
        if ins_pct > 0.1: own_score += 15
        if inst_pct > 0.6: own_score += 15
        if inst_pct > 0.8: own_score += 5
        score_components["ownership_confidence"] = min(100, own_score)
        outlook["insider_pct"] = safe_float(ins_pct * 100, 1)
        outlook["institution_pct"] = safe_float(inst_pct * 100, 1)

        # 6. Short interest (contrarian / risk signal)
        short_ratio = info.get("shortRatio", 0) or 0
        short_score = 70
        if short_ratio > 10: short_score = 20
        elif short_ratio > 5: short_score = 40
        elif short_ratio < 2: short_score = 80
        score_components["short_interest"] = short_score
        outlook["short_ratio"] = safe_float(short_ratio, 2)

        # 7. Dividend & payout sustainability
        dy = info.get("dividendYield", 0) or 0
        pr = info.get("payoutRatio", 0) or 0
        div_score = 50
        if dy > 0.02 and pr < 0.6: div_score = 75
        elif dy > 0.04 and pr < 0.8: div_score = 65
        score_components["dividend"] = div_score
        outlook["dividend_yield_pct"] = safe_float(dy * 100, 2)
        outlook["payout_ratio_pct"] = safe_float(pr * 100, 1)

        # Composite future score (weighted average)
        weights = {
            "analyst_consensus": 0.25,
            "earnings_growth": 0.20,
            "valuation": 0.18,
            "financial_health": 0.17,
            "ownership_confidence": 0.10,
            "short_interest": 0.05,
            "dividend": 0.05,
        }
        composite = sum(score_components[k] * weights[k] for k in weights)
        composite = round(composite, 1)

        if composite >= 75: grade = "Strong Buy"; grade_color = "green"
        elif composite >= 60: grade = "Buy"; grade_color = "lightgreen"
        elif composite >= 45: grade = "Hold"; grade_color = "yellow"
        elif composite >= 30: grade = "Underperform"; grade_color = "orange"
        else: grade = "Sell"; grade_color = "red"

        # 1-Year price scenario projection
        scenarios = {}
        if current and upside is not None:
            bull_target = round(current * (1 + max(upside / 100, 0.15)), 2)
            bear_target = round(current * (1 - 0.12), 2)
            base_target = round(current * (1 + (upside / 100 * 0.6)), 2)
            scenarios = {"bull": bull_target, "base": base_target, "bear": bear_target}

        return {
            "composite_score": composite,
            "grade": grade,
            "grade_color": grade_color,
            "components": score_components,
            "outlook": outlook,
            "scenarios": scenarios,
        }
    except Exception as e:
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────
# SECTOR TREND ANALYSIS
# ──────────────────────────────────────────────────────────────
def _sector_performance(period_days=5):
    """Return performance % for each sector over last N trading days."""
    result = {}
    all_sectors = {**GLOBAL_SECTOR_ETFS, **INDIAN_SECTOR_INDICES}

    def worker(name, ticker):
        try:
            hist = yf.Ticker(ticker).history(period="3mo", auto_adjust=True)
            if hist.empty or len(hist) < 2: return
            close = hist["Close"].astype(float)
            # 1-week (5 days)
            wk = safe_float(((close.iloc[-1] - close.iloc[-min(6, len(close))])
                             / close.iloc[-min(6, len(close))] * 100), 2)
            # 1-month (~21 days)
            mo = safe_float(((close.iloc[-1] - close.iloc[-min(22, len(close))])
                             / close.iloc[-min(22, len(close))] * 100), 2)
            # 3-months
            qt = safe_float(((close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100), 2)
            result[name] = {
                "week": wk, "month": mo, "quarter": qt,
                "price": safe_float(close.iloc[-1]),
                "ticker": ticker,
                "region": "India" if ".NS" in ticker or "^CNX" in ticker or "^NSE" in ticker or "^BSE" in ticker else "Global",
            }
        except: pass

    threads = [threading.Thread(target=worker, args=(n, t), daemon=True)
               for n, t in all_sectors.items()]
    for th in threads: th.start()
    for th in threads: th.join(timeout=30)
    return result


# ──────────────────────────────────────────────────────────────
# WORLD MARKET TREND
# ──────────────────────────────────────────────────────────────
def _world_market_trend():
    """Today's global market breadth, sentiment, and key moves."""
    indices = _fetch_quotes_parallel(GLOBAL_INDICES)
    up = sum(1 for v in indices.values() if v and v.get("change_pct", 0) > 0)
    dn = sum(1 for v in indices.values() if v and v.get("change_pct", 0) < 0)
    total = up + dn
    breadth_pct = round(up / total * 100) if total else 50

    avg_change = 0
    valid = [v["change_pct"] for v in indices.values() if v and v.get("change_pct") is not None]
    if valid: avg_change = round(sum(valid) / len(valid), 2)

    sentiment = "Bullish" if avg_change > 0.3 else "Bearish" if avg_change < -0.3 else "Neutral"

    # VIX (fear index)
    vix_data = _fetch_quote("^VIX")
    vix = vix_data.get("price") if not vix_data.get("error") else None
    fear = "Extreme Fear" if (vix and vix > 30) else "Fear" if (vix and vix > 20) else "Greed" if (vix and vix < 15) else "Neutral"

    # DXY (dollar strength)
    dxy = _fetch_quote("DX-Y.NYB")
    dxy_val = dxy.get("price") if not dxy.get("error") else None

    return {
        "indices": indices,
        "up_count": up, "down_count": dn,
        "breadth_pct": breadth_pct,
        "avg_change": avg_change,
        "sentiment": sentiment,
        "vix": vix,
        "fear_gauge": fear,
        "dxy": dxy_val,
        "top_gainer": max(indices.items(), key=lambda x: x[1].get("change_pct", -999) if x[1] else -999, default=("—", {}))[0],
        "top_loser": min(indices.items(), key=lambda x: x[1].get("change_pct", 999) if x[1] else 999, default=("—", {}))[0],
    }


# ──────────────────────────────────────────────────────────────
# INDIA MARKET TREND
# ──────────────────────────────────────────────────────────────
def _india_market_trend():
    """Today's Indian market breadth, FII/DII proxy, and sector moves."""
    idx = _fetch_quotes_parallel(INDIAN_INDICES)
    up = sum(1 for v in idx.values() if v and v.get("change_pct", 0) > 0)
    dn = sum(1 for v in idx.values() if v and v.get("change_pct", 0) < 0)

    # INR strength from USD/INR
    usdinr = _fetch_quote("USDINR=X")
    inr_change = usdinr.get("change_pct") if not usdinr.get("error") else None

    valid = [v["change_pct"] for v in idx.values() if v and v.get("change_pct") is not None]
    avg_change = round(sum(valid) / len(valid), 2) if valid else 0
    sentiment = "Bullish" if avg_change > 0.3 else "Bearish" if avg_change < -0.3 else "Sideways"

    # Top Indian stocks breadth sample
    stocks = _fetch_quotes_parallel(POPULAR_INDIAN_STOCKS)
    s_up = sum(1 for v in stocks.values() if v and v.get("change_pct", 0) > 0)
    s_dn = sum(1 for v in stocks.values() if v and v.get("change_pct", 0) < 0)

    return {
        "indices": idx,
        "up_count": up, "down_count": dn,
        "avg_change": avg_change,
        "sentiment": sentiment,
        "stocks_up": s_up, "stocks_dn": s_dn,
        "usdinr": usdinr.get("price"),
        "inr_change": inr_change,
        "nifty": idx.get("NIFTY 50", {}),
        "sensex": idx.get("SENSEX", {}),
    }


# ──────────────────────────────────────────────────────────────
# NEWS
# ──────────────────────────────────────────────────────────────
def _scrape_news():
    news = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    sources = [
        ("https://finance.yahoo.com/news/", "Yahoo Finance"),
        ("https://economictimes.indiatimes.com/markets", "Economic Times"),
    ]
    for url, source in sources:
        try:
            r = requests.get(url, headers=headers, timeout=8)
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup.find_all(["h2", "h3"], limit=10):
                text = tag.get_text(strip=True)
                if len(text) < 25: continue
                a_tag = tag.find("a") or (tag.parent and tag.parent.find("a"))
                href = "#"
                if a_tag and a_tag.get("href"):
                    href = a_tag["href"]
                    if href.startswith("/"):
                        base = url.split("/")[0] + "//" + url.split("/")[2]
                        href = base + href
                news.append({"title": text, "source": source, "url": href,
                             "time": datetime.now().strftime("%H:%M")})
        except: pass
    return news[:20]


# ──────────────────────────────────────────────────────────────
# AI CHAT
# ──────────────────────────────────────────────────────────────
def _ai_chat(question):
    question_upper = question.upper()
    ticker_found = None
    all_stocks = {**POPULAR_INDIAN_STOCKS, **POPULAR_GLOBAL_STOCKS}
    for name, ticker in all_stocks.items():
        base = ticker.replace(".NS", "").replace(".KS", "")
        if name.upper() in question_upper or base in question_upper:
            ticker_found = ticker
            break

    context = ""
    if ticker_found:
        q = _fetch_quote(ticker_found)
        f = _fetch_fundamentals(ticker_found)
        ta = _technical_analysis(ticker_found)
        fo = _future_outlook(ticker_found)
        context = f"""
=== LIVE MARKET DATA ===
Ticker   : {ticker_found}
Price    : {q.get('price')} {q.get('currency')}
Change   : {q.get('change')} ({q.get('change_pct')}%)
P/E      : {q.get('pe_ratio')} | Fwd P/E: {f.get('forward_pe')}
52W High : {q.get('52w_high')} | 52W Low: {q.get('52w_low')}
Mkt Cap  : {q.get('market_cap')}
Sector   : {f.get('sector')} | Industry: {f.get('industry')}
EPS      : {f.get('eps')} | ROE: {f.get('roe')} | D/E: {f.get('debt_equity')}
RSI      : {ta.get('rsi')} | MACD: {ta.get('macd')} | Momentum: {ta.get('momentum_score')}/100
MA20/50  : {ta.get('ma20')} / {ta.get('ma50')}
Support  : {ta.get('support')} | Resistance: {ta.get('resistance')}
Signals  : {', '.join(ta.get('signals', []))}

=== FORWARD OUTLOOK ===
AI Score : {fo.get('composite_score')}/100 → {fo.get('grade')}
Analyst Target: {fo.get('outlook', {}).get('analyst_target')} (Upside: {fo.get('outlook', {}).get('analyst_upside_pct')}%)
Recommendation: {fo.get('outlook', {}).get('recommendation')}
Earnings Growth: {fo.get('outlook', {}).get('earnings_growth_pct')}%
Scenarios: Bull={fo.get('scenarios', {}).get('bull')} Base={fo.get('scenarios', {}).get('base')} Bear={fo.get('scenarios', {}).get('bear')}

Summary  : {f.get('summary', '')[:400]}
========================
"""

    if AI_AVAILABLE and _anthropic_lib:
        try:
            client = _anthropic_lib.Anthropic(api_key=_ANTHROPIC_KEY)
            system = (
                "You are FinVision AI, an expert financial analyst specializing in global markets "
                "and the Indian stock market (NSE/BSE). You have live market data in the context. "
                "Provide clear, structured, data-backed analysis with forward-looking insights. "
                "Use bullet points and section headers. Always end with: "
                "⚠️ Disclaimer: Educational analysis only, not financial advice."
            )
            msg = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": f"{context}\n\nQuestion: {question}"}]
            )
            return msg.content[0].text
        except: pass

    # Rule-based fallback
    parts = [f"📊 **Analysis: {question}**\n"]
    if context: parts.append(context)
    q_low = question.lower()
    if any(w in q_low for w in ["nifty", "sensex", "india"]):
        try:
            nifty = _fetch_quote("^NSEI")
            sensex = _fetch_quote("^BSESN")
            parts.append(f"\n🇮🇳 **Indian Markets (Live)**\nNIFTY 50: {nifty.get('price')} ({nifty.get('change_pct')}%)\nSENSEX: {sensex.get('price')} ({sensex.get('change_pct')}%)\n")
        except: pass
    if any(w in q_low for w in ["buy", "sell", "invest"]):
        parts.append("\n💡 **Investment Checklist**\n• Check forward P/E vs industry\n• Review earnings growth trajectory\n• Assess analyst consensus & targets\n• Check financial health (FCF, D/E)\n• Consider sector momentum\n• Consult SEBI-registered advisor\n")
    parts.append("\n⚠️ *Disclaimer: Educational analysis only, not financial advice.*")
    return "".join(parts)


def _india_bond_yield():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get("https://www.worldgovernmentbonds.com/bond-forecast/india/10-years/", headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        for td in soup.find_all("td"):
            txt = td.get_text(strip=True)
            if re.match(r"^\d+\.\d+%$", txt):
                return {"yield": txt, "name": "India 10Y Bond"}
    except: pass
    return {"yield": "N/A", "name": "India 10Y Bond"}


# ──────────────────────────────────────────────────────────────
# FLASK ROUTES
# ──────────────────────────────────────────────────────────────
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "deps_ok": DEPS_OK, "ai": AI_AVAILABLE, "time": datetime.now().isoformat()})

@app.route("/api/indices/global")
def api_global_indices(): return jsonify(_fetch_quotes_parallel(GLOBAL_INDICES))

@app.route("/api/indices/india")
def api_india_indices(): return jsonify(_fetch_quotes_parallel(INDIAN_INDICES))

@app.route("/api/stocks/india")
def api_india_stocks():
    raw = _fetch_quotes_parallel(POPULAR_INDIAN_STOCKS)
    for name, ticker in POPULAR_INDIAN_STOCKS.items():
        if name in raw: raw[name]["ticker"] = ticker
    return jsonify(raw)

@app.route("/api/stocks/global")
def api_global_stocks():
    raw = _fetch_quotes_parallel(POPULAR_GLOBAL_STOCKS)
    for name, ticker in POPULAR_GLOBAL_STOCKS.items():
        if name in raw: raw[name]["ticker"] = ticker
    return jsonify(raw)

@app.route("/api/bonds")
def api_bonds():
    data = _fetch_quotes_parallel(BONDS_AND_COMMODITIES)
    data["India 10Y Bond"] = _india_bond_yield()
    return jsonify(data)

@app.route("/api/forex")
def api_forex(): return jsonify(_fetch_quotes_parallel(FOREX_PAIRS))

@app.route("/api/stock/<ticker>")
def api_stock_detail(ticker):
    ticker = ticker.upper()
    period = request.args.get("period", "3mo")
    return jsonify({
        "quote": _fetch_quote(ticker),
        "fundamentals": _fetch_fundamentals(ticker),
        "analysis": _technical_analysis(ticker),
        "future_outlook": _future_outlook(ticker),
        "history": _fetch_history(ticker, period),
    })

@app.route("/api/news")
def api_news(): return jsonify(_scrape_news())

@app.route("/api/world-trend")
def api_world_trend(): return jsonify(_world_market_trend())

@app.route("/api/india-trend")
def api_india_trend(): return jsonify(_india_market_trend())

@app.route("/api/sectors")
def api_sectors(): return jsonify(_sector_performance())

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    if not question: return jsonify({"error": "question required"}), 400
    return jsonify({"question": question, "answer": _ai_chat(question), "timestamp": datetime.now().isoformat()})

@app.route("/api/search/<query>")
def api_search(query):
    q = query.upper()
    results = []
    for name, ticker in {**POPULAR_INDIAN_STOCKS, **POPULAR_GLOBAL_STOCKS}.items():
        base = ticker.replace(".NS", "").replace(".KS", "")
        if q in name.upper() or q in base:
            results.append({"name": name, "ticker": ticker})
    if not results: results.append({"name": query.upper(), "ticker": query.upper()})
    return jsonify(results)


# ──────────────────────────────────────────────────────────────
# FRONTEND HTML
# ──────────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>FinVision v2 — Market Analyzer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=Outfit:wght@300;400;600;800;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{
  --bg:#03070f;--s1:#080f1e;--s2:#0c1628;--s3:#111f35;
  --border:#172845;--border2:#1e3660;
  --cyan:#00e5ff;--green:#00e676;--red:#ff1744;--gold:#ffd600;
  --purple:#c77dff;--orange:#ff6d00;--yellow:#ffea00;
  --text:#dce8f5;--text2:#6e90b4;--text3:#3d5a80;
  --glow:0 0 20px rgba(0,229,255,.15);
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Outfit',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;
  background:radial-gradient(ellipse 80% 50% at 20% 0%,rgba(0,100,200,.07) 0%,transparent 60%),
             radial-gradient(ellipse 60% 40% at 80% 100%,rgba(0,200,150,.05) 0%,transparent 60%);
  pointer-events:none;z-index:0}
.grid-bg{position:fixed;inset:0;
  background-image:linear-gradient(rgba(0,229,255,.025) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(0,229,255,.025) 1px,transparent 1px);
  background-size:60px 60px;pointer-events:none;z-index:0}

/* Header */
header{position:sticky;top:0;z-index:200;height:58px;
  background:rgba(3,7,15,.92);backdrop-filter:blur(24px);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;padding:0 1.8rem;gap:1rem}
.logo{font-size:1.35rem;font-weight:900;letter-spacing:-1.5px;
  background:linear-gradient(90deg,var(--cyan),var(--green));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo em{-webkit-text-fill-color:var(--gold);font-style:normal}
.header-right{display:flex;align-items:center;gap:1.2rem}
.live-badge{display:flex;align-items:center;gap:6px;font-size:.7rem;font-weight:600;
  letter-spacing:1.5px;text-transform:uppercase;color:var(--green);
  background:rgba(0,230,118,.1);border:1px solid rgba(0,230,118,.25);
  padding:3px 10px;border-radius:20px}
.live-dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:blink 1.4s ease infinite}
@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.8)}}
.hclock{font-family:'IBM Plex Mono',monospace;font-size:.72rem;color:var(--text2)}

/* Tabs */
nav{background:var(--s1);border-bottom:1px solid var(--border);
  display:flex;overflow-x:auto;scrollbar-width:none;padding:0 1.8rem;position:sticky;top:58px;z-index:150}
nav::-webkit-scrollbar{display:none}
.tab{padding:.75rem 1.2rem;border:none;background:transparent;color:var(--text2);
  font-family:'Outfit',sans-serif;font-size:.76rem;font-weight:600;letter-spacing:.8px;
  text-transform:uppercase;cursor:pointer;white-space:nowrap;
  border-bottom:2px solid transparent;transition:all .2s;flex-shrink:0}
.tab:hover{color:var(--text)}.tab.on{color:var(--cyan);border-bottom-color:var(--cyan)}

/* Layout */
main{position:relative;z-index:1;max-width:1700px;margin:0 auto;padding:1.5rem 1.8rem}
.panel{display:none}.panel.on{display:block}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem}
.g3{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem}
.g4{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem}
.g5{display:grid;grid-template-columns:repeat(5,1fr);gap:.9rem}
@media(max-width:1400px){.g5{grid-template-columns:repeat(3,1fr)}}
@media(max-width:1100px){.g4{grid-template-columns:repeat(2,1fr)}.g3{grid-template-columns:1fr 1fr}}
@media(max-width:800px){.g2,.g3,.g4,.g5{grid-template-columns:1fr}}

/* Cards */
.card{background:var(--s1);border:1px solid var(--border);border-radius:14px;padding:1.3rem;
  transition:border-color .2s,box-shadow .2s}
.card:hover{border-color:var(--border2);box-shadow:var(--glow)}
.card-title{font-size:.63rem;font-weight:700;letter-spacing:2.5px;text-transform:uppercase;
  color:var(--text2);margin-bottom:1rem;display:flex;align-items:center;gap:.5rem}
.card-title::after{content:'';flex:1;height:1px;background:var(--border)}

/* Ticker tape */
.tape{background:var(--s1);border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  padding:.4rem 0;overflow:hidden;position:relative}
.tape::before,.tape::after{content:'';position:absolute;top:0;bottom:0;width:80px;z-index:2}
.tape::before{left:0;background:linear-gradient(90deg,var(--s1),transparent)}
.tape::after{right:0;background:linear-gradient(-90deg,var(--s1),transparent)}
.tape-inner{display:flex;gap:2.5rem;width:max-content;animation:scrolltape 55s linear infinite;padding:0 1.5rem}
.tape-inner:hover{animation-play-state:paused}
@keyframes scrolltape{from{transform:translateX(0)}to{transform:translateX(-50%)}}
.ti{font-family:'IBM Plex Mono',monospace;font-size:.7rem;white-space:nowrap;display:flex;align-items:center;gap:5px}
.tn{color:var(--text2)}.tp{color:var(--text);font-weight:600}
.up{color:var(--green)}.dn{color:var(--red)}.neu{color:var(--text2)}

/* Index cards */
.ic{background:var(--s2);border:1px solid var(--border);border-radius:12px;
  padding:1.1rem 1.3rem;transition:all .2s;cursor:default}
.ic:hover{border-color:var(--cyan);transform:translateY(-2px);box-shadow:var(--glow)}
.ic .in{font-size:.62rem;font-weight:700;letter-spacing:2px;color:var(--text2);text-transform:uppercase;margin-bottom:.4rem}
.ic .ip{font-family:'IBM Plex Mono',monospace;font-size:1.2rem;font-weight:700;color:var(--text)}
.ic .ic2{font-family:'IBM Plex Mono',monospace;font-size:.76rem;margin-top:.3rem}

/* Tables */
.tbl{width:100%;border-collapse:collapse;font-family:'IBM Plex Mono',monospace;font-size:.73rem}
.tbl thead tr{border-bottom:1px solid var(--border)}
.tbl th{padding:.6rem .8rem;text-align:right;color:var(--text3);font-size:.6rem;letter-spacing:2px;text-transform:uppercase;font-weight:600}
.tbl th:first-child{text-align:left}
.tbl td{padding:.6rem .8rem;text-align:right;border-bottom:1px solid rgba(255,255,255,.03);color:var(--text);transition:background .15s}
.tbl td:first-child{text-align:left}
.tbl tr:hover td{background:rgba(0,229,255,.04)}
.sname{font-weight:700;color:var(--text);font-family:'Outfit',sans-serif;font-size:.82rem}
.sticker{color:var(--text2);font-size:.63rem;font-family:'IBM Plex Mono',monospace}

/* Badges */
.bdg{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.62rem;font-weight:700;letter-spacing:.5px}
.bdg-up{background:rgba(0,230,118,.12);color:var(--green);border:1px solid rgba(0,230,118,.2)}
.bdg-dn{background:rgba(255,23,68,.12);color:var(--red);border:1px solid rgba(255,23,68,.2)}
.bdg-neu{background:rgba(255,214,0,.12);color:var(--gold);border:1px solid rgba(255,214,0,.2)}
.bdg-bull{background:rgba(0,229,255,.1);color:var(--cyan);border:1px solid rgba(0,229,255,.2)}
.bdg-purple{background:rgba(199,125,255,.12);color:var(--purple);border:1px solid rgba(199,125,255,.2)}

.abtn{background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.2);color:var(--cyan);
  padding:3px 10px;border-radius:5px;cursor:pointer;font-size:.65rem;font-family:'Outfit',sans-serif;
  font-weight:600;transition:all .2s;white-space:nowrap}
.abtn:hover{background:rgba(0,229,255,.18);box-shadow:0 0 10px rgba(0,229,255,.2)}

/* Section headings */
.ph{font-size:1.5rem;font-weight:800;margin-bottom:.3rem;letter-spacing:-.5px}
.ph span{color:var(--cyan)}
.ps{color:var(--text2);font-size:.85rem;margin-bottom:1.4rem}

/* Stats row */
.sr{display:flex;justify-content:space-between;align-items:center;
  padding:.5rem 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.82rem}
.sr:last-child{border:none}
.sl{color:var(--text2)}.sv{font-family:'IBM Plex Mono',monospace;color:var(--text)}

/* Spinner */
.spin{display:inline-block;width:16px;height:16px;border:2px solid rgba(0,229,255,.15);
  border-top-color:var(--cyan);border-radius:50%;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.ldc{display:flex;align-items:center;justify-content:center;height:120px;color:var(--text2);gap:.8rem;font-size:.85rem}

/* Trend sentiment big card */
.sentiment-box{border-radius:16px;padding:1.5rem;text-align:center;position:relative;overflow:hidden}
.sentiment-box.bull{background:linear-gradient(135deg,rgba(0,230,118,.1),rgba(0,229,255,.08));border:1px solid rgba(0,230,118,.25)}
.sentiment-box.bear{background:linear-gradient(135deg,rgba(255,23,68,.1),rgba(255,100,0,.08));border:1px solid rgba(255,23,68,.25)}
.sentiment-box.side{background:linear-gradient(135deg,rgba(255,214,0,.1),rgba(199,125,255,.08));border:1px solid rgba(255,214,0,.25)}
.sb-label{font-size:.68rem;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--text2);margin-bottom:.5rem}
.sb-val{font-size:2.2rem;font-weight:900;letter-spacing:-1px}
.sb-sub{font-size:.8rem;color:var(--text2);margin-top:.3rem}

/* Sector bars */
.sbar-row{display:flex;align-items:center;gap:.8rem;padding:.45rem 0;border-bottom:1px solid rgba(255,255,255,.04)}
.sbar-row:last-child{border:none}
.sbar-name{font-size:.75rem;color:var(--text);width:180px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sbar-track{flex:1;background:rgba(255,255,255,.05);border-radius:4px;height:8px;overflow:hidden}
.sbar-fill{height:100%;border-radius:4px;transition:width .6s ease}
.sbar-val{font-family:'IBM Plex Mono',monospace;font-size:.72rem;width:65px;text-align:right;flex-shrink:0}
.sbar-region{font-size:.58rem;font-weight:700;letter-spacing:1px;text-transform:uppercase;
  padding:1px 6px;border-radius:10px;flex-shrink:0}
.region-india{background:rgba(255,167,38,.15);color:#ffb74d;border:1px solid rgba(255,167,38,.2)}
.region-global{background:rgba(100,181,246,.1);color:#64b5f6;border:1px solid rgba(100,181,246,.2)}

/* Score gauge */
.gauge-wrap{display:flex;flex-direction:column;align-items:center;padding:1rem 0}
.gauge-ring{position:relative;width:120px;height:120px}
.gauge-ring svg{transform:rotate(-90deg)}
.gauge-val{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.gauge-num{font-family:'IBM Plex Mono',monospace;font-size:1.6rem;font-weight:700}
.gauge-lbl{font-size:.6rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--text2)}
.grade-pill{margin-top:.6rem;padding:4px 14px;border-radius:20px;font-size:.75rem;font-weight:700;letter-spacing:.5px}

/* Scenario bars */
.scenario-row{display:flex;align-items:center;gap:.8rem;padding:.4rem 0}
.sc-label{font-size:.7rem;font-weight:700;width:50px;flex-shrink:0;text-transform:uppercase;letter-spacing:1px}
.sc-bar{flex:1;background:rgba(255,255,255,.06);border-radius:6px;height:22px;position:relative;overflow:hidden}
.sc-fill{height:100%;border-radius:6px;display:flex;align-items:center;justify-content:flex-end;padding-right:8px}
.sc-price{font-family:'IBM Plex Mono',monospace;font-size:.7rem;font-weight:600;color:#000}

/* Signal chips */
.sigwrap{display:flex;flex-wrap:wrap;gap:5px;margin-top:.6rem}
.sig-chip{padding:3px 10px;border-radius:20px;font-size:.64rem;font-weight:600;
  background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.18);color:var(--cyan)}

/* Chart */
.chwrap{position:relative;height:260px;background:var(--s2);border-radius:10px;padding:.8rem}

/* News */
.ni{padding:.8rem 0;border-bottom:1px solid rgba(255,255,255,.04);display:flex;gap:.8rem;align-items:flex-start}
.ni:last-child{border:none}
.ndot{width:5px;height:5px;border-radius:50%;background:var(--cyan);margin-top:8px;flex-shrink:0}
.ntitle{font-size:.85rem;font-weight:600;line-height:1.5;color:var(--text)}
.nmeta{font-size:.68rem;color:var(--text2);margin-top:2px}
.nlink{color:var(--text);text-decoration:none}.nlink:hover{color:var(--cyan)}

/* Modal */
.moverlay{position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.85);backdrop-filter:blur(12px);
  display:none;align-items:center;justify-content:center}
.moverlay.open{display:flex}
.modal{background:var(--s1);border:1px solid var(--border2);border-radius:20px;
  width:94vw;max-width:980px;max-height:92vh;overflow-y:auto;padding:2rem;position:relative}
.modal::-webkit-scrollbar{width:4px}
.modal::-webkit-scrollbar-thumb{background:var(--border2);border-radius:2px}
.mclose{position:absolute;top:1.2rem;right:1.2rem;background:rgba(255,255,255,.08);
  border:1px solid var(--border);color:var(--text);width:34px;height:34px;border-radius:50%;
  cursor:pointer;font-size:1rem;transition:background .2s}
.mclose:hover{background:rgba(255,23,68,.2)}
.mtitle{font-size:1.6rem;font-weight:800;margin-bottom:.2rem;letter-spacing:-.5px}
.msub{color:var(--text2);margin-bottom:1.5rem;font-size:.84rem}

/* AI Chat */
.chatwrap{display:flex;flex-direction:column;height:calc(100vh - 250px);min-height:500px;
  background:var(--s1);border:1px solid var(--border);border-radius:18px;overflow:hidden}
.chhead{padding:1rem 1.4rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
.chavatar{width:38px;height:38px;border-radius:50%;background:linear-gradient(135deg,var(--cyan),var(--green));
  display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
.chmsg{flex:1;overflow-y:auto;padding:1.2rem;display:flex;flex-direction:column;gap:.9rem}
.chmsg::-webkit-scrollbar{width:3px}
.chmsg::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.msg{max-width:84%;padding:.85rem 1.1rem;border-radius:14px;font-size:.86rem;line-height:1.7;white-space:pre-wrap}
.mu{align-self:flex-end;background:rgba(0,229,255,.1);border:1px solid rgba(0,229,255,.2);color:var(--text)}
.ma{align-self:flex-start;background:var(--s2);border:1px solid var(--border);color:var(--text)}
.qps{display:flex;flex-wrap:wrap;gap:.4rem;padding:.7rem 1.1rem;border-top:1px solid var(--border)}
.qp{background:rgba(255,255,255,.04);border:1px solid var(--border);color:var(--text2);
  padding:4px 11px;border-radius:20px;cursor:pointer;font-size:.7rem;font-family:'Outfit',sans-serif;
  transition:all .2s;white-space:nowrap}
.qp:hover{background:rgba(0,229,255,.1);color:var(--cyan);border-color:rgba(0,229,255,.3)}
.chinput-row{display:flex;gap:.8rem;padding:.9rem 1.1rem;border-top:1px solid var(--border);background:var(--s2)}
.chinput{flex:1;background:var(--s1);border:1px solid var(--border);color:var(--text);
  padding:.65rem 1rem;border-radius:10px;font-family:'Outfit',sans-serif;font-size:.88rem;
  outline:none;transition:border-color .2s}
.chinput:focus{border-color:var(--cyan)}
.chsend{background:linear-gradient(135deg,var(--cyan),var(--green));border:none;color:#000;
  padding:.65rem 1.3rem;border-radius:10px;cursor:pointer;font-family:'Outfit',sans-serif;
  font-weight:700;font-size:.84rem;transition:opacity .2s;white-space:nowrap}
.chsend:hover{opacity:.85}.chsend:disabled{opacity:.35;cursor:not-allowed}

/* Search bar */
.sbar{display:flex;gap:.8rem;margin-bottom:1.4rem;align-items:center;flex-wrap:wrap}
.sinput{background:var(--s1);border:1px solid var(--border);color:var(--text);
  padding:.65rem 1rem;border-radius:10px;font-family:'Outfit',sans-serif;font-size:.88rem;
  outline:none;width:300px;transition:border-color .2s}
.sinput:focus{border-color:var(--cyan)}
.sbtn{background:var(--cyan);border:none;color:#000;padding:.65rem 1.3rem;border-radius:10px;
  cursor:pointer;font-weight:700;font-family:'Outfit',sans-serif;font-size:.85rem;white-space:nowrap}

/* Period selector */
.period-sel{display:flex;gap:.4rem;margin-bottom:1rem}
.ps-btn{background:rgba(255,255,255,.05);border:1px solid var(--border);color:var(--text2);
  padding:3px 12px;border-radius:20px;cursor:pointer;font-size:.72rem;font-family:'Outfit',sans-serif;transition:all .2s}
.ps-btn.on,.ps-btn:hover{background:rgba(0,229,255,.12);border-color:rgba(0,229,255,.3);color:var(--cyan)}

/* Breadth display */
.breadth{display:flex;align-items:center;gap:.6rem}
.breadth-bar{flex:1;height:10px;border-radius:5px;background:rgba(255,23,68,.3);overflow:hidden}
.breadth-fill{height:100%;background:linear-gradient(90deg,var(--green),var(--cyan));border-radius:5px;transition:width .8s ease}
.breadth-nums{font-family:'IBM Plex Mono',monospace;font-size:.7rem;white-space:nowrap}

/* FII/DII mockup */
.flow-bar{display:flex;height:12px;border-radius:6px;overflow:hidden;margin:.4rem 0}
.flow-inflow{background:linear-gradient(90deg,var(--green),rgba(0,230,118,.5))}
.flow-outflow{background:linear-gradient(90deg,rgba(255,23,68,.5),var(--red))}

@media(max-width:768px){main{padding:1rem}header,nav{padding:0 1rem}
  .msg{max-width:96%}.sinput{width:200px}}
</style>
</head>
<body>
<div class="grid-bg"></div>
<header>
  <div class="logo">Fin<em>Vision</em> <span style="font-size:.7rem;font-weight:400;color:var(--text3);letter-spacing:0">v2</span></div>
  <div class="header-right">
    <div class="live-badge"><div class="live-dot"></div>LIVE</div>
    <div class="hclock" id="clk">—</div>
  </div>
</header>
<div class="tape"><div class="tape-inner" id="tape"><span class="ti"><span class="tn">Loading…</span></span></div></div>
<nav>
  <button class="tab on"  onclick="go('overview',this)">📊 Overview</button>
  <button class="tab"     onclick="go('world',this)">🌍 World Trend</button>
  <button class="tab"     onclick="go('india',this)">🇮🇳 India Trend</button>
  <button class="tab"     onclick="go('sectors',this)">📂 Sectors</button>
  <button class="tab"     onclick="go('bonds',this)">📈 Bonds & Commodities</button>
  <button class="tab"     onclick="go('forex',this)">💱 Forex</button>
  <button class="tab"     onclick="go('news',this)">📰 News</button>
  <button class="tab"     onclick="go('chat',this)">🤖 AI Analyst</button>
</nav>
<main>

<!-- OVERVIEW -->
<div id="panel-overview" class="panel on">
  <div class="ph">Market <span>Overview</span></div>
  <p class="ps">Real-time snapshot · Global & Indian markets · Updated live</p>
  <div class="g2" style="margin-bottom:1.4rem">
    <div class="card"><div class="card-title">🇮🇳 Indian Indices</div><div id="ov-india" class="ldc"><div class="spin"></div>Fetching…</div></div>
    <div class="card"><div class="card-title">🌍 Global Indices</div><div id="ov-global" class="ldc"><div class="spin"></div>Fetching…</div></div>
  </div>
  <div class="g3">
    <div class="card"><div class="card-title">🏅 Commodities & Crypto</div><div id="ov-bonds" class="ldc"><div class="spin"></div>Fetching…</div></div>
    <div class="card"><div class="card-title">💱 Key Forex</div><div id="ov-forex" class="ldc"><div class="spin"></div>Fetching…</div></div>
    <div class="card"><div class="card-title">📰 Headlines</div><div id="ov-news" class="ldc"><div class="spin"></div>Scraping…</div></div>
  </div>
</div>

<!-- WORLD TREND -->
<div id="panel-world" class="panel">
  <div class="ph">🌍 World Market <span>Trend</span></div>
  <p class="ps">Today's global market breadth, sentiment, fear gauge & top movers</p>
  <div id="world-content"><div class="ldc"><div class="spin"></div>Analyzing global markets…</div></div>
</div>

<!-- INDIA TREND -->
<div id="panel-india" class="panel">
  <div class="ph">🇮🇳 Indian Market <span>Trend</span></div>
  <p class="ps">NIFTY, SENSEX, sector breadth, INR strength & stock momentum</p>
  <div id="india-content"><div class="ldc"><div class="spin"></div>Analyzing Indian markets…</div></div>
</div>

<!-- SECTORS -->
<div id="panel-sectors" class="panel">
  <div class="ph">📂 Sector <span>Analysis</span></div>
  <p class="ps">Weekly & quarterly performance — Global ETFs & Indian Sector Indices</p>
  <div style="display:flex;gap:.6rem;margin-bottom:1.2rem" id="sector-period-btns">
    <button class="ps-btn on" onclick="setSectorPeriod('week',this)">1 Week</button>
    <button class="ps-btn" onclick="setSectorPeriod('month',this)">1 Month</button>
    <button class="ps-btn" onclick="setSectorPeriod('quarter',this)">1 Quarter</button>
  </div>
  <div id="sectors-content"><div class="ldc"><div class="spin"></div>Fetching sector data…</div></div>
</div>

<!-- BONDS -->
<div id="panel-bonds" class="panel">
  <div class="ph">📈 Bonds, <span>Commodities & Crypto</span></div>
  <p class="ps">Treasuries · Gold · Oil · Bitcoin · Ethereum</p>
  <div class="g5" id="bonds-grid"><div class="ldc" style="grid-column:1/-1"><div class="spin"></div>Loading…</div></div>
</div>

<!-- FOREX -->
<div id="panel-forex" class="panel">
  <div class="ph">💱 <span>Forex</span></div>
  <p class="ps">Live exchange rates including USD/INR and major pairs</p>
  <div class="g5" id="forex-grid"><div class="ldc" style="grid-column:1/-1"><div class="spin"></div>Loading…</div></div>
</div>

<!-- NEWS -->
<div id="panel-news" class="panel">
  <div class="ph">📰 Market <span>News</span></div>
  <p class="ps">Live headlines from Yahoo Finance & Economic Times</p>
  <div class="card" id="news-full"><div class="ldc"><div class="spin"></div>Scraping headlines…</div></div>
</div>

<!-- AI CHAT -->
<div id="panel-chat" class="panel">
  <div class="ph">🤖 AI <span>Market Analyst</span></div>
  <p class="ps">Ask about any stock · Live data · Technical + Fundamental + Forward Outlook</p>
  <div class="sbar">
    <input class="sinput" id="ssearch" placeholder="Search stock (e.g. TCS, AAPL, RELIANCE)…" onkeydown="if(event.key==='Enter')doSearch()">
    <button class="sbtn" onclick="doSearch()">Deep Analyze →</button>
  </div>
  <div class="chatwrap">
    <div class="chhead">
      <div class="chavatar">🤖</div>
      <div>
        <div style="font-weight:700;font-size:.95rem">FinVision AI Analyst</div>
        <div style="font-size:.72rem;color:var(--text2)">Live data · Past + Future analysis · Sector insights</div>
      </div>
    </div>
    <div class="chmsg" id="chmsg">
      <div class="msg ma">👋 Hello! I'm your AI Financial Analyst with live market data.

I now analyze both <strong>past performance</strong> AND <strong>forward-looking</strong> metrics:

📊 <strong>Past Analysis:</strong> RSI, MACD, Moving Averages, Support/Resistance
🔮 <strong>Forward Outlook:</strong> Analyst targets, Earnings growth, Forward PE, Scenarios (Bull/Base/Bear)
🏦 <strong>Financial Health:</strong> Free cash flow, Debt ratios, Insider ownership
🗺️ <strong>World & India Trends:</strong> "World trend today" or "India market trend"
📂 <strong>Sectors:</strong> "Which sectors are trending this week?"

Try: "Full analysis of TCS" · "Future outlook for NVIDIA" · "India market today"</div>
    </div>
    <div class="qps">
      <button class="qp" onclick="qp('Full analysis of TCS with forward outlook')">TCS Full</button>
      <button class="qp" onclick="qp('Future outlook for Reliance Industries')">Reliance Future</button>
      <button class="qp" onclick="qp('NVIDIA forward PE and analyst targets')">NVIDIA Outlook</button>
      <button class="qp" onclick="qp('India market trend today')">India Today</button>
      <button class="qp" onclick="qp('Which global sectors are trending this week?')">Sector Trends</button>
      <button class="qp" onclick="qp('Gold vs Bitcoin which is better now?')">Gold vs Bitcoin</button>
      <button class="qp" onclick="qp('Explain Bull Base Bear scenario for stocks')">Price Scenarios</button>
      <button class="qp" onclick="qp('Infosys vs Wipro future comparison')">Infosys vs Wipro</button>
    </div>
    <div class="chinput-row">
      <input class="chinput" id="chin" placeholder="Ask any financial question…" onkeydown="if(event.key==='Enter')chat()">
      <button class="chsend" id="chsend" onclick="chat()">Send →</button>
    </div>
  </div>
</div>

</main>

<!-- STOCK DETAIL MODAL -->
<div class="moverlay" id="moverlay">
  <div class="modal">
    <button class="mclose" onclick="closeMod()">✕</button>
    <div id="mcontent"><div class="ldc"><div class="spin"></div>Loading full analysis…</div></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const f = (n,d=2) => n!=null ? Number(n).toLocaleString('en-IN',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
const fp = n => n!=null ? `${n>0?'+':''}${f(n)}%` : '—';
const pc = n => n>0?'up':n<0?'dn':'neu';
const bdg = n => `<span class="bdg ${n>0?'bdg-up':n<0?'bdg-dn':'bdg-neu'}">${fp(n)}</span>`;

// Clock
const tick = () => {
  $('clk').textContent = new Date().toLocaleString('en-IN',{timeZone:'Asia/Kolkata',
    hour12:true,hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'short'})+' IST';
};
setInterval(tick,1000); tick();

const api = url => fetch(url).then(r=>r.json()).catch(()=>({}));

// Tabs
const loaded = {};
function go(name, btn) {
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  $(`panel-${name}`).classList.add('on');
  btn.classList.add('on');
  if(!loaded[name]){
    loaded[name]=true;
    const loaders = {world:loadWorld, india:loadIndia, sectors:loadSectors,
      bonds:loadBonds, forex:loadForex, news:loadNewsFull};
    loaders[name]?.();
  }
}

// ── Ticker Tape ──
async function loadTape() {
  const [a,b] = await Promise.all([api('/api/indices/india'),api('/api/indices/global')]);
  const all = {...a,...b};
  const items = Object.entries(all).map(([nm,d]) => {
    if(!d||!d.price) return '';
    const c = pc(d.change_pct);
    return `<span class="ti"><span class="tn">${nm}</span><span class="tp">${f(d.price)}</span><span class="${c}">${fp(d.change_pct)}</span></span>`;
  }).filter(Boolean);
  if(items.length) $('tape').innerHTML = items.join('') + items.join('');
}

// ── Overview ──
async function loadOverview() {
  loadTape();
  api('/api/indices/india').then(d=>{
    $('ov-india').innerHTML = Object.entries(d).map(([n,v])=>{
      if(!v||!v.price) return '';
      const c=pc(v.change_pct);
      return `<div class="sr"><span class="sl">${n}</span><span class="sv">${f(v.price)} <span class="${c}">${fp(v.change_pct)}</span></span></div>`;
    }).join('') || '<p style="color:var(--text2)">No data</p>';
  });
  api('/api/indices/global').then(d=>{
    $('ov-global').innerHTML = Object.entries(d).map(([n,v])=>{
      if(!v||!v.price) return '';
      const c=pc(v.change_pct);
      return `<div class="sr"><span class="sl">${n}</span><span class="sv">${f(v.price)} <span class="${c}">${fp(v.change_pct)}</span></span></div>`;
    }).join('') || '<p>No data</p>';
  });
  api('/api/bonds').then(d=>{
    const keys=['Gold','Silver','Crude Oil (WTI)','Bitcoin','Ethereum'];
    $('ov-bonds').innerHTML = keys.map(k=>{
      const v=d[k]; if(!v||v.error||!v.price) return '';
      const c=pc(v.change_pct);
      return `<div class="sr"><span class="sl">${k}</span><span class="sv">${f(v.price)} <span class="${c}">${fp(v.change_pct)}</span></span></div>`;
    }).join('') || '<p>No data</p>';
  });
  api('/api/forex').then(d=>{
    const keys=['USD/INR','EUR/USD','GBP/USD','USD/JPY'];
    $('ov-forex').innerHTML = keys.map(k=>{
      const v=d[k]; if(!v||v.error||!v.price) return '';
      const c=pc(v.change_pct);
      return `<div class="sr"><span class="sl">${k}</span><span class="sv">${f(v.price,4)} <span class="${c}">${fp(v.change_pct)}</span></span></div>`;
    }).join('') || '<p>No data</p>';
  });
  api('/api/news').then(news=>{
    $('ov-news').innerHTML = news.slice(0,5).map(n=>
      `<div class="ni"><div class="ndot"></div><div>
        <div class="ntitle"><a class="nlink" href="${n.url}" target="_blank">${n.title}</a></div>
        <div class="nmeta">${n.source} · ${n.time}</div></div></div>`
    ).join('') || '<p style="color:var(--text2)">Could not fetch news</p>';
  });
}

// ── World Trend ──
async function loadWorld() {
  $('world-content').innerHTML = '<div class="ldc"><div class="spin"></div>Fetching global data…</div>';
  const d = await api('/api/world-trend');
  const s = d.sentiment||'Neutral';
  const sClass = s==='Bullish'?'bull':s==='Bearish'?'bear':'side';
  const sColor = s==='Bullish'?'var(--green)':s==='Bearish'?'var(--red)':'var(--gold)';

  let indHtml = Object.entries(d.indices||{}).map(([n,v])=>{
    if(!v||!v.price) return '';
    const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price)}</div>
      <div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');

  $('world-content').innerHTML = `
    <div class="g3" style="margin-bottom:1.4rem">
      <div class="sentiment-box ${sClass}">
        <div class="sb-label">Market Sentiment</div>
        <div class="sb-val" style="color:${sColor}">${s}</div>
        <div class="sb-sub">Avg change: ${d.avg_change>0?'+':''}${d.avg_change}%</div>
      </div>
      <div class="card">
        <div class="card-title">Market Breadth</div>
        <div style="margin-bottom:.8rem">
          <div class="breadth">
            <div class="breadth-bar"><div class="breadth-fill" style="width:${d.breadth_pct||50}%"></div></div>
            <div class="breadth-nums">${d.up_count||0}↑ ${d.down_count||0}↓</div>
          </div>
          <div style="font-size:.7rem;color:var(--text2);margin-top:.4rem">${d.breadth_pct||50}% markets advancing</div>
        </div>
        <div class="sr"><span class="sl">Top Gainer</span><span class="sv" style="color:var(--green)">${d.top_gainer||'—'}</span></div>
        <div class="sr"><span class="sl">Top Loser</span><span class="sv" style="color:var(--red)">${d.top_loser||'—'}</span></div>
      </div>
      <div class="card">
        <div class="card-title">Fear & Dollar</div>
        <div class="sr"><span class="sl">VIX</span><span class="sv" style="color:${(d.vix||20)>20?'var(--red)':'var(--green)'}">${d.vix?f(d.vix,2):'—'}</span></div>
        <div class="sr"><span class="sl">Fear Gauge</span><span class="sv">${d.fear_gauge||'—'}</span></div>
        <div class="sr"><span class="sl">DXY (Dollar)</span><span class="sv">${d.dxy?f(d.dxy,2):'—'}</span></div>
        <div style="margin-top:.8rem">
          <span class="bdg bdg-${(d.vix||20)>25?'dn':(d.vix||20)<15?'up':'neu'}" style="font-size:.7rem">${d.fear_gauge||'Neutral'}</span>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-title">All Global Indices — Today</div>
      <div class="g4">${indHtml}</div>
    </div>`;
}

// ── India Trend ──
async function loadIndia() {
  $('india-content').innerHTML = '<div class="ldc"><div class="spin"></div>Fetching Indian market data…</div>';
  const [trend, stocks] = await Promise.all([api('/api/india-trend'), api('/api/stocks/india')]);
  const s = trend.sentiment||'Sideways';
  const sClass = s==='Bullish'?'bull':s==='Bearish'?'bear':'side';
  const sColor = s==='Bullish'?'var(--green)':s==='Bearish'?'var(--red)':'var(--gold)';

  const inrChange = trend.inr_change;
  const inrDir = inrChange < 0 ? 'INR Strengthening ▲' : inrChange > 0 ? 'INR Weakening ▼' : 'Stable';
  const inrColor = inrChange < 0 ? 'var(--green)' : inrChange > 0 ? 'var(--red)' : 'var(--gold)';

  let idxHtml = Object.entries(trend.indices||{}).map(([n,v])=>{
    if(!v||!v.price) return '';
    const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');

  // Top movers table
  const topMovers = Object.entries(stocks)
    .filter(([,v])=>v&&!v.error&&v.price)
    .sort((a,b)=>Math.abs(b[1].change_pct||0)-Math.abs(a[1].change_pct||0))
    .slice(0,10);

  const tblHtml = topMovers.map(([nm,d])=>{
    const c=pc(d.change_pct);
    return `<tr>
      <td><div class="sname">${nm}</div><div class="sticker">${d.ticker||''}</div></td>
      <td>${f(d.price)}</td><td class="${c}">${f(d.change)}</td>
      <td>${bdg(d.change_pct)}</td>
      <td>${d.pe_ratio?f(d.pe_ratio,1):'—'}</td>
      <td><button class="abtn" onclick="openStock('${d.ticker||nm}')">Analyze</button></td>
    </tr>`;
  }).join('');

  $('india-content').innerHTML = `
    <div class="g3" style="margin-bottom:1.4rem">
      <div class="sentiment-box ${sClass}">
        <div class="sb-label">India Sentiment</div>
        <div class="sb-val" style="color:${sColor}">${s}</div>
        <div class="sb-sub">Avg: ${trend.avg_change>0?'+':''}${trend.avg_change}%</div>
      </div>
      <div class="card">
        <div class="card-title">NIFTY & SENSEX</div>
        <div class="sr"><span class="sl">NIFTY 50</span><span class="sv ${pc(trend.nifty?.change_pct)}">${f(trend.nifty?.price)} ${fp(trend.nifty?.change_pct)}</span></div>
        <div class="sr"><span class="sl">SENSEX</span><span class="sv ${pc(trend.sensex?.change_pct)}">${f(trend.sensex?.price)} ${fp(trend.sensex?.change_pct)}</span></div>
        <div style="margin-top:.8rem">
          <div class="breadth">
            <div class="breadth-bar"><div class="breadth-fill" style="width:${Math.round((trend.stocks_up||5)/((trend.stocks_up||5)+(trend.stocks_dn||5))*100)}%"></div></div>
            <div class="breadth-nums">${trend.stocks_up||0}↑ ${trend.stocks_dn||0}↓</div>
          </div>
          <div style="font-size:.68rem;color:var(--text2);margin-top:.3rem">Sample stocks breadth</div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Currency & FII Signal</div>
        <div class="sr"><span class="sl">USD/INR</span><span class="sv">${trend.usdinr?f(trend.usdinr,2):'—'}</span></div>
        <div class="sr"><span class="sl">INR Direction</span><span class="sv" style="color:${inrColor}">${inrDir}</span></div>
        <div class="sr"><span class="sl">INR Change</span><span class="sv ${pc(-(inr_change=trend.inr_change||0))}">${inrChange!=null?fp(-inrChange):'—'}</span></div>
        <div style="margin-top:.5rem;font-size:.7rem;color:var(--text2)">FII signal: weaker INR = risk-off</div>
      </div>
    </div>
    <div class="card" style="margin-bottom:1.4rem">
      <div class="card-title">All Indian Sector Indices</div>
      <div class="g4">${idxHtml}</div>
    </div>
    <div class="card">
      <div class="card-title">Top Movers — Indian Stocks</div>
      <table class="tbl"><thead><tr>
        <th>Stock</th><th>Price</th><th>Change</th><th>%</th><th>P/E</th><th></th>
      </tr></thead><tbody>${tblHtml}</tbody></table>
    </div>`;
}

// ── Sectors ──
let _sectorData = null;
let _sectorPeriod = 'week';

async function loadSectors() {
  $('sectors-content').innerHTML = '<div class="ldc"><div class="spin"></div>Fetching sector performance…</div>';
  _sectorData = await api('/api/sectors');
  renderSectors();
}

function setSectorPeriod(period, btn) {
  _sectorPeriod = period;
  document.querySelectorAll('#sector-period-btns .ps-btn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  if(_sectorData) renderSectors();
}

function renderSectors() {
  if(!_sectorData) return;
  const period = _sectorPeriod;
  const data = Object.entries(_sectorData).filter(([,v])=>v&&v[period]!=null);
  data.sort((a,b)=>(b[1][period]||0)-(a[1][period]||0));

  const maxAbs = Math.max(...data.map(([,v])=>Math.abs(v[period]||0)), 1);
  const indian = data.filter(([,v])=>v.region==='India');
  const global = data.filter(([,v])=>v.region==='Global');

  const renderList = (items, title) => {
    if(!items.length) return '';
    const rows = items.map(([nm,v])=>{
      const val = v[period]||0;
      const pct = Math.abs(val)/maxAbs*100;
      const color = val>0?'var(--green)':val<0?'var(--red)':'var(--text2)';
      const bgColor = val>0?'rgba(0,230,118,.7)':'rgba(255,23,68,.7)';
      const regionClass = v.region==='India'?'region-india':'region-global';
      return `<div class="sbar-row">
        <div class="sbar-name" title="${nm}">${nm}</div>
        <div class="sbar-track">
          <div class="sbar-fill" style="width:${pct}%;background:${bgColor}"></div>
        </div>
        <div class="sbar-val" style="color:${color}">${val>0?'+':''}${val}%</div>
        <div class="sbar-region ${regionClass}">${v.region}</div>
      </div>`;
    }).join('');
    return `<div class="card" style="margin-bottom:1rem"><div class="card-title">${title}</div>${rows}</div>`;
  };

  // Top 5 / Bottom 5 winners / losers
  const top5 = data.slice(0,5);
  const bot5 = data.slice(-5).reverse();
  const topCards = `<div class="g2" style="margin-bottom:1.2rem">
    <div class="card">
      <div class="card-title">🏆 Top Performing Sectors</div>
      ${top5.map(([nm,v])=>{
        const val=v[period]||0;
        const rClass=v.region==='India'?'region-india':'region-global';
        return `<div class="sr"><span class="sl" style="display:flex;align-items:center;gap:6px">${nm} <span class="sbar-region ${rClass}">${v.region}</span></span><span class="sv up">+${f(val)}%</span></div>`;
      }).join('')}
    </div>
    <div class="card">
      <div class="card-title">📉 Worst Performing Sectors</div>
      ${bot5.map(([nm,v])=>{
        const val=v[period]||0;
        const rClass=v.region==='India'?'region-india':'region-global';
        return `<div class="sr"><span class="sl" style="display:flex;align-items:center;gap:6px">${nm} <span class="sbar-region ${rClass}">${v.region}</span></span><span class="sv dn">${f(val)}%</span></div>`;
      }).join('')}
    </div>
  </div>`;

  $('sectors-content').innerHTML = topCards + renderList(global,'🌍 Global Sector ETFs') + renderList(indian,'🇮🇳 Indian Sector Indices');
}

// ── Bonds ──
async function loadBonds() {
  const d = await api('/api/bonds');
  $('bonds-grid').innerHTML = Object.entries(d).map(([n,v])=>{
    if(v&&v.yield) return `<div class="ic"><div class="in">${n}</div><div class="ip">${v.yield}</div><div class="ic2" style="color:var(--text2)">Yield</div></div>`;
    if(!v||v.error||!v.price) return `<div class="ic"><div class="in">${n}</div><div class="ip">N/A</div></div>`;
    const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');
}

// ── Forex ──
async function loadForex() {
  const d = await api('/api/forex');
  $('forex-grid').innerHTML = Object.entries(d).map(([n,v])=>{
    if(!v||v.error||!v.price) return `<div class="ic"><div class="in">${n}</div><div class="ip">N/A</div></div>`;
    const c=pc(v.change_pct);
    return `<div class="ic"><div class="in">${n}</div><div class="ip">${f(v.price,4)}</div><div class="ic2 ${c}">${fp(v.change_pct)}</div></div>`;
  }).join('');
}

// ── News ──
async function loadNewsFull() {
  const news = await api('/api/news');
  $('news-full').innerHTML = news.map(n=>
    `<div class="ni"><div class="ndot"></div><div>
      <div class="ntitle"><a class="nlink" href="${n.url}" target="_blank">${n.title}</a></div>
      <div class="nmeta">${n.source} · ${n.time}</div></div></div>`
  ).join('') || '<p style="color:var(--text2);padding:1rem">Could not scrape news.</p>';
}

// ── Stock Detail Modal ──
let _chart = null;
async function openStock(ticker) {
  $('moverlay').classList.add('open');
  $('mcontent').innerHTML = '<div class="ldc"><div class="spin"></div>Loading full analysis…</div>';
  const d = await api(`/api/stock/${encodeURIComponent(ticker)}?period=3mo`);
  const q=d.quote||{}, fund=d.fundamentals||{}, a=d.analysis||{}, fo=d.future_outlook||{}, h=d.history||[];
  const outlook = fo.outlook||{};
  const scenarios = fo.scenarios||{};

  const c=pc(q.change_pct);
  const sigHtml=(a.signals||[]).map(s=>`<span class="sig-chip">${s}</span>`).join('');

  // Grade color
  const gc = fo.grade_color==='green'?'var(--green)':fo.grade_color==='lightgreen'?'#69f0ae':
    fo.grade_color==='yellow'?'var(--gold)':fo.grade_color==='orange'?'var(--orange)':'var(--red)';

  // Gauge SVG
  const score = fo.composite_score||50;
  const radius=46, circ=2*Math.PI*radius;
  const dash = circ * score/100;
  const gaugeColor = score>=75?'var(--green)':score>=60?'#69f0ae':score>=45?'var(--gold)':score>=30?'var(--orange)':'var(--red)';
  const gaugeSVG = `<div class="gauge-ring">
    <svg viewBox="0 0 100 100" width="120" height="120">
      <circle cx="50" cy="50" r="${radius}" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="8"/>
      <circle cx="50" cy="50" r="${radius}" fill="none" stroke="${gaugeColor}" stroke-width="8"
        stroke-dasharray="${dash} ${circ-dash}" stroke-linecap="round"/>
    </svg>
    <div class="gauge-val">
      <div class="gauge-num" style="color:${gaugeColor}">${score}</div>
      <div class="gauge-lbl">/ 100</div>
    </div>
  </div>`;

  // Scenario bars
  const curr = q.price||1;
  const allPrices = [scenarios.bull||curr*1.2, scenarios.base||curr*1.05, scenarios.bear||curr*0.9];
  const maxP = Math.max(...allPrices);
  const scenHtml = scenarios.bull ? `
    <div class="scenario-row">
      <div class="sc-label" style="color:var(--green)">Bull</div>
      <div class="sc-bar"><div class="sc-fill" style="width:${scenarios.bull/maxP*100}%;background:linear-gradient(90deg,rgba(0,230,118,.4),rgba(0,230,118,.8))"><span class="sc-price">${f(scenarios.bull)}</span></div></div>
    </div>
    <div class="scenario-row">
      <div class="sc-label" style="color:var(--cyan)">Base</div>
      <div class="sc-bar"><div class="sc-fill" style="width:${scenarios.base/maxP*100}%;background:linear-gradient(90deg,rgba(0,229,255,.4),rgba(0,229,255,.8))"><span class="sc-price">${f(scenarios.base)}</span></div></div>
    </div>
    <div class="scenario-row">
      <div class="sc-label" style="color:var(--red)">Bear</div>
      <div class="sc-bar"><div class="sc-fill" style="width:${scenarios.bear/maxP*100}%;background:linear-gradient(90deg,rgba(255,23,68,.4),rgba(255,23,68,.8))"><span class="sc-price">${f(scenarios.bear)}</span></div></div>
    </div>` : '<div style="color:var(--text2);font-size:.8rem">Insufficient data for scenarios</div>';

  $('mcontent').innerHTML = `
    <div class="mtitle">${q.name||ticker}</div>
    <div class="msub">${ticker} · ${fund.sector||'—'} · ${fund.industry||'—'}</div>
    <div class="g3" style="margin-bottom:1.4rem">
      <div class="card">
        <div class="card-title">Live Price</div>
        <div style="font-size:2.1rem;font-weight:900;font-family:'IBM Plex Mono',monospace">${f(q.price)}</div>
        <div class="${c}" style="font-family:'IBM Plex Mono',monospace;font-size:.9rem">${fp(q.change_pct)} (${f(q.change)})</div>
        <div style="margin-top:.6rem;display:flex;gap:.5rem">
          <span style="font-size:.68rem;color:var(--text2)">52W High: <span style="color:var(--green)">${f(q['52w_high'])}</span></span>
          <span style="font-size:.68rem;color:var(--text2)">Low: <span style="color:var(--red)">${f(q['52w_low'])}</span></span>
        </div>
      </div>
      <div class="card">
        <div class="card-title">🔮 AI Forward Score</div>
        <div class="gauge-wrap">
          ${gaugeSVG}
          <div class="grade-pill" style="background:${gc}22;color:${gc};border:1px solid ${gc}44">${fo.grade||'N/A'}</div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Analyst Consensus</div>
        <div class="sr"><span class="sl">Recommendation</span><span class="sv">${outlook.recommendation||'—'}</span></div>
        <div class="sr"><span class="sl">Target Price</span><span class="sv" style="color:var(--cyan)">${f(outlook.analyst_target)}</span></div>
        <div class="sr"><span class="sl">Upside</span><span class="sv ${pc(outlook.analyst_upside_pct)}">${fp(outlook.analyst_upside_pct)}</span></div>
        <div class="sr"><span class="sl"># Analysts</span><span class="sv">${outlook.analyst_count||'—'}</span></div>
      </div>
    </div>
    <div class="card" style="margin-bottom:1.4rem">
      <div class="card-title">Price Chart (3 months)</div>
      <div class="chwrap"><canvas id="dch"></canvas></div>
    </div>
    <div class="sigwrap" style="margin-bottom:1.4rem">${sigHtml}</div>
    <div class="g2" style="margin-bottom:1.4rem">
      <div class="card">
        <div class="card-title">📈 Technical Analysis</div>
        ${[['RSI',`${f(a.rsi,1)} ${a.rsi>70?'🔴 Overbought':a.rsi<30?'🟢 Oversold':'Neutral'}`],
           ['MACD',f(a.macd,4)],['Signal',f(a.signal,4)],
           ['MA 20',f(a.ma20)],['MA 50',f(a.ma50)],['MA 200',f(a.ma200)],
           ['BB Upper',f(a.bb_upper)],['BB Lower',f(a.bb_lower)],
           ['Support',f(a.support)],['Resistance',f(a.resistance)],
           ['Volume Ratio',a.vol_ratio?a.vol_ratio+'x':'—'],
           ['OBV Trend',a.obv_trend||'—'],
           ['Momentum',a.momentum_score?a.momentum_score+'/100':'—']
        ].map(([l,v])=>`<div class="sr"><span class="sl">${l}</span><span class="sv">${v}</span></div>`).join('')}
      </div>
      <div class="card">
        <div class="card-title">🔮 Forward Outlook</div>
        ${[['Forward P/E',f(outlook.forward_pe,2)],
           ['Trailing P/E',f(outlook.trailing_pe,2)],
           ['PE Expansion',outlook.pe_expansion||'—'],
           ['Earnings Growth',outlook.earnings_growth_pct!=null?fp(outlook.earnings_growth_pct):'—'],
           ['Revenue Growth',outlook.revenue_growth_pct!=null?fp(outlook.revenue_growth_pct):'—'],
           ['FCF (Bn)',outlook.free_cashflow_b!=null?f(outlook.free_cashflow_b):'—'],
           ['Debt/Equity',f(outlook.debt_to_equity,2)],
           ['Current Ratio',f(outlook.current_ratio,2)],
           ['Insiders',outlook.insider_pct!=null?f(outlook.insider_pct,1)+'%':'—'],
           ['Institutions',outlook.institution_pct!=null?f(outlook.institution_pct,1)+'%':'—'],
           ['Short Ratio',f(outlook.short_ratio,2)],
           ['Div Yield',outlook.dividend_yield_pct!=null?f(outlook.dividend_yield_pct,2)+'%':'—'],
        ].map(([l,v])=>`<div class="sr"><span class="sl">${l}</span><span class="sv">${v}</span></div>`).join('')}
      </div>
    </div>
    <div class="g2" style="margin-bottom:1.4rem">
      <div class="card">
        <div class="card-title">🎯 1-Year Price Scenarios</div>
        <div style="font-size:.72rem;color:var(--text2);margin-bottom:.8rem">Based on analyst targets & growth estimates</div>
        ${scenHtml}
        <div style="font-size:.68rem;color:var(--text3);margin-top:.8rem">Current: ${f(curr)} ${q.currency||'USD'}</div>
      </div>
      <div class="card">
        <div class="card-title">📊 Score Breakdown</div>
        ${Object.entries(fo.components||{}).map(([k,v])=>{
          const label = k.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
          const color = v>=70?'var(--green)':v>=50?'var(--cyan)':v>=30?'var(--gold)':'var(--red)';
          return `<div class="sbar-row">
            <div class="sbar-name" style="font-size:.72rem">${label}</div>
            <div class="sbar-track"><div class="sbar-fill" style="width:${v}%;background:${color}88"></div></div>
            <div class="sbar-val" style="color:${color}">${v}</div>
          </div>`;
        }).join('')}
      </div>
    </div>
    <div class="g2">
      <div class="card">
        <div class="card-title">Fundamentals</div>
        ${[['P/E Ratio',f(q.pe_ratio,1)],['EPS',f(fund.eps)],
           ['ROE',fund.roe?(fund.roe*100).toFixed(1)+'%':'—'],
           ['ROA',fund.roa?(fund.roa*100).toFixed(1)+'%':'—'],
           ['Profit Margin',fund.profit_margin?(fund.profit_margin*100).toFixed(1)+'%':'—'],
           ['Gross Margin',fund.gross_margins?(fund.gross_margins*100).toFixed(1)+'%':'—'],
           ['D/E Ratio',f(fund.debt_equity,2)],
           ['Beta',f(fund.beta,2)],['P/B Ratio',f(fund.price_to_book,2)],
           ['PEG Ratio',f(fund.peg_ratio,2)]
        ].map(([l,v])=>`<div class="sr"><span class="sl">${l}</span><span class="sv">${v}</span></div>`).join('')}
      </div>
      ${fund.summary?`<div class="card">
        <div class="card-title">About</div>
        <p style="font-size:.82rem;line-height:1.75;color:var(--text2)">${fund.summary}</p>
      </div>`:'<div class="card"><div class="card-title">About</div><p style="color:var(--text2)">No description available.</p></div>'}
    </div>`;

  // Draw chart
  if(h.length>1){
    if(_chart){_chart.destroy();_chart=null;}
    const ctx=document.getElementById('dch').getContext('2d');
    const prices=h.map(p=>p.close);
    const bull=prices[prices.length-1]>=prices[0];
    const col=bull?'#00e676':'#ff1744';
    _chart=new Chart(ctx,{type:'line',
      data:{labels:h.map(p=>p.date),datasets:[{data:prices,borderColor:col,borderWidth:2,fill:true,tension:.3,
        backgroundColor:ctx2=>{const g=ctx2.chart.ctx.createLinearGradient(0,0,0,260);g.addColorStop(0,col+'55');g.addColorStop(1,col+'00');return g;},
        pointRadius:0,pointHoverRadius:4}]},
      options:{responsive:true,maintainAspectRatio:false,
        interaction:{mode:'index',intersect:false},
        plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`₹${ctx.raw?.toFixed(2)}`}}},
        scales:{x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#6e90b4',maxTicksLimit:7,font:{size:10}}},
                y:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#6e90b4',font:{size:10}}}}}});
  }
}

function closeMod(){
  $('moverlay').classList.remove('open');
  if(_chart){_chart.destroy();_chart=null;}
}
$('moverlay').addEventListener('click',e=>{if(e.target===$('moverlay'))closeMod();});

// ── Chat ──
function qp(t){$('chin').value=t;chat();}
function doSearch(){
  const q=$('ssearch').value.trim(); if(!q) return;
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('on'));
  document.querySelectorAll('.tab')[7].classList.add('on');
  $('panel-chat').classList.add('on');
  $('chin').value=`Full analysis of ${q} stock with forward outlook`;
  chat();
}

async function chat(){
  const inp=$('chin'), q=inp.value.trim(); if(!q) return;
  const btn=$('chsend'); btn.disabled=true; inp.value='';
  const box=$('chmsg');
  const u=document.createElement('div'); u.className='msg mu'; u.textContent=q; box.appendChild(u);
  const a=document.createElement('div'); a.className='msg ma';
  a.innerHTML='<div class="spin"></div> Analyzing with live data…'; box.appendChild(a);
  box.scrollTop=box.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
    const data=await r.json();
    let ans=(data.answer||'No response.').replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/_(.*?)_/g,'<em>$1</em>');
    a.innerHTML=ans;
  }catch(e){a.innerHTML=`<span style="color:var(--red)">Error: ${e.message}</span>`;}
  btn.disabled=false; box.scrollTop=box.scrollHeight; inp.focus();
}

// Init
loadOverview();
setInterval(loadTape, 60000);
loaded['overview']=true;
</script>
</body>
</html>"""


@app.route("/")
def index():
    if not DEPS_OK:
        return (
            "<html><body style='font-family:monospace;background:#03070f;color:#dce8f5;padding:2rem'>"
            "<h2 style='color:#ff1744'>Missing packages</h2>"
            "<p>Run this command:</p>"
            "<pre style='background:#080f1e;padding:1rem;border-radius:8px;margin-top:.5rem'>"
            "pip install flask yfinance pandas numpy requests beautifulsoup4</pre>"
            f"<p style='color:#ff1744;margin-top:1rem'>Error: {MISSING}</p>"
            "</body></html>"
        )
    return _HTML


if __name__ == "__main__":
    print("""
 FinVision v2.0 — Global & Indian Financial Market Analyzer
 ===========================================================
 NEW: World Trend · India Trend · Sector Analysis · Forward Outlook
 Open browser at:  http://localhost:5000

 Optional: Set ANTHROPIC_API_KEY for AI-powered chat
""")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
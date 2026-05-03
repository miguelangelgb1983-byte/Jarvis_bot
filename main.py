"""
╔══════════════════════════════════════════════════════════════════════╗
║   JARVIS v10 — DEFINITIVO · Miguel (Miki) · 01/05/2026              ║
║                                                                      ║
║   ✅ FMP precios reales (NO yfinance)                                ║
║   ✅ Tavily + fallback FED/SEC/Yahoo RSS                             ║
║   ✅ Tarjeta visual SIEMPRE para empresas                            ║
║   ✅ Conversación natural sin comandos                               ║
║   ✅ Plantilla EXACTA de Miki                                        ║
║   ✅ Validación al arranque (errores claros)                         ║
║   ✅ Zonas horarias correctas (España + NY)                          ║
║   ✅ Memoria SQLite + Supabase                                       ║
║   ✅ Audios Whisper + Voz ElevenLabs                                 ║
║   ✅ Gmail: MyInvestor + Trade Republic + ING                        ║
║   ✅ Briefing autónomo cada 6h                                       ║
║   ✅ Modo degradado si falta ANTHROPIC_KEY                           ║
║   ✅ "recuerda que..." → memoria permanente                          ║
║   ✅ do_HEAD UptimeRobot 24/7                                        ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, logging, requests, threading, json, time
import imaplib, email, re, sqlite3
from email.header import decode_header
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ_OK = True
except ImportError:
    TZ_OK = False

# ═════════════════════════════════════════════════════
#  ENV VARS
# ═════════════════════════════════════════════════════
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY      = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_KEY         = os.environ.get("TAVILY_KEY")
SUPABASE_URL       = os.environ.get("SUPABASE_URL")
SUPABASE_KEY       = os.environ.get("SUPABASE_KEY")
ELEVENLABS_KEY     = os.environ.get("ELEVENLABS_KEY")
ELEVENLABS_VOICE   = "htFfPSZGJwjBv1CL0aMD"
OPENAI_KEY         = os.environ.get("OPENAI_API_KEY")
GMAIL_USER         = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
MIKI_CHAT_ID       = os.environ.get("MIKI_CHAT_ID")
FMP_KEY            = os.environ.get("FMP")
FRED_KEY           = os.environ.get("FRED_KEY")
PORT               = int(os.environ.get("PORT", 8080))
MEMORY_DB_PATH     = os.environ.get("MEMORY_DB_PATH", "jarvis_memory.db")
TEMPLATE_PATH      = os.environ.get("VALUATION_TEMPLATE_PATH", "miki_valuation_template.md")
AUTONOMY_ENABLED   = os.environ.get("AUTONOMY_ENABLED", "1") == "1"
AUTONOMY_INTERVAL_MIN = int(os.environ.get("AUTONOMY_INTERVAL_MIN", "360"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ═════════════════════════════════════════════════════
#  VALIDACIÓN DE ARRANQUE (de ChatGPT — buena idea)
# ═════════════════════════════════════════════════════
def validate_runtime_config():
    """Valida config mínima para evitar arranques rotos."""
    required = {"TELEGRAM_TOKEN": TELEGRAM_TOKEN}
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"FALTAN variables obligatorias: {', '.join(missing)}")

    optional = {
        "ANTHROPIC_API_KEY": ANTHROPIC_KEY,
        "FMP": FMP_KEY,
        "FRED_KEY": FRED_KEY,
        "TAVILY_KEY": TAVILY_KEY,
        "OPENAI_API_KEY": OPENAI_KEY,
        "ELEVENLABS_KEY": ELEVENLABS_KEY,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "GMAIL_USER": GMAIL_USER,
        "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
        "MIKI_CHAT_ID": MIKI_CHAT_ID,
    }
    missing_optional = [k for k, v in optional.items() if not v]
    if missing_optional:
        logging.warning("Variables opcionales ausentes (se desactivan capacidades): %s",
                        ", ".join(missing_optional))
    else:
        logging.info("✅ TODAS las variables están configuradas")

# ═════════════════════════════════════════════════════
#  TICKERS
# ═════════════════════════════════════════════════════
FMP_TICKERS = {
    "GOOGL":"GOOGL","AAPL":"AAPL","MSFT":"MSFT","JNJ":"JNJ","VISA":"V","V":"V",
    "SSNC":"SSNC","TXRH":"TXRH","CELH":"CELH","NKE":"NKE","SP500":"^GSPC","INDIA":"INDA",
}
EUROPEAN_TICKERS = ["MONC", "ZEG", "TRET", "8PSG", "GOLD"]

TICKER_KEYWORDS = {
    "GOOGL": ["googl", "google", "alphabet"],
    "AAPL":  ["aapl", "apple", "manzana"],
    "MSFT":  ["msft", "microsoft"],
    "JNJ":   ["jnj", "johnson"],
    "VISA":  ["visa"],
    "SSNC":  ["ssnc"],
    "TXRH":  ["txrh", "texas roadhouse"],
    "CELH":  ["celh", "celsius"],
    "NKE":   ["nke", "nike"],
    "MONC":  ["monc", "moncler"],
    "ZEG":   ["zeg", "zegona"],
    "TRET":  ["tret"],
    "GOLD":  ["oro ", " oro", "gold "],
    "SP500": ["sp500", "s&p", "sp 500"],
    "INDIA": ["india"],
}

def detect_ticker(text):
    txt_low = " " + text.lower() + " "
    for ticker, kws in TICKER_KEYWORDS.items():
        for kw in kws:
            if kw in txt_low:
                return ticker
    return None

CONVERSATIONAL_KEYWORDS = [
    "qué piensas", "que piensas", "qué opinas", "que opinas",
    "estoy preocupado", "estoy nervioso", "estoy contento",
    "ayúdame", "ayudame", "qué hago", "que hago",
    "no sé", "no se ", "estoy pensando", "tengo dudas",
    "explícame", "explicame", "cómo funciona", "como funciona",
    "qué es ", "que es ", "qué piensa", "noticias",
]

def is_conversational(text):
    txt_low = text.lower()
    return any(p in txt_low for p in CONVERSATIONAL_KEYWORDS)

# ═════════════════════════════════════════════════════
#  FMP — Endpoints /stable/ (los nuevos, post-agosto 2025)
# ═════════════════════════════════════════════════════
def fmp_get_stable(endpoint, symbol, retries=2):
    """Endpoints /stable/. Devuelve dict normal, o {"_premium": True} si FMP free no cubre."""
    if not FMP_KEY: return None
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"https://financialmodelingprep.com/stable/{endpoint}",
                             params={"symbol": symbol, "apikey": FMP_KEY}, timeout=12)
            if r.status_code == 200:
                data = r.json()
                # Detectar respuesta Premium de FMP
                if isinstance(data, dict):
                    em = (data.get("Error Message") or data.get("error") or "").lower()
                    if "premium" in em or "subscription" in em or "not available under your current" in em:
                        logging.info(f"FMP Premium para {symbol} en {endpoint} → fallback")
                        return {"_premium": True}
                    if data: return data
                if isinstance(data, list):
                    if data: return data[0]
                    return None
                return None
            elif r.status_code == 402:
                # Payment Required = Premium
                return {"_premium": True}
            elif r.status_code == 429:
                logging.warning(f"FMP rate limit en {endpoint} {symbol}")
                if attempt < retries:
                    time.sleep(2)
                    continue
                return None
        except Exception as e:
            logging.error(f"FMP {endpoint} {symbol} attempt {attempt}: {e}")
            if attempt < retries:
                time.sleep(1)
                continue
    return None

def get_real_data(ticker_input):
    """Datos reales. Si FMP free no cubre el ticker, fallback automático Tavily+SEC."""
    ticker_up = ticker_input.upper()
    if ticker_up in EUROPEAN_TICKERS:
        return {"is_european": True, "ticker": ticker_up,
                "tavily": search_news(f"{ticker_input} stock price PER FCF today", n=3)}

    fmp_ticker = FMP_TICKERS.get(ticker_up, ticker_up)
    quote = fmp_get_stable("quote", fmp_ticker)

    # FMP free no cubre este ticker → fallback automático
    if quote and isinstance(quote, dict) and quote.get("_premium"):
        logging.info(f"FMP free no cubre {ticker_input} → Tavily + SEC EDGAR")
        sec = sec_get_filings(ticker_input, n=3)
        ins = openinsider_get(ticker_input, n=5)
        news = search_news(f"{ticker_input} stock price PER FCF EPS revenue today", n=4)
        return {"_fallback": True, "ticker": ticker_up, "name": ticker_up,
                "tavily": news, "sec": sec, "insiders": ins}

    if not quote:
        # FMP cayó del todo, intentar Tavily como último recurso
        news = search_news(f"{ticker_input} stock price market cap PER today", n=3)
        if news:
            return {"_fallback": True, "ticker": ticker_up, "name": ticker_up,
                    "tavily": news, "sec": "", "insiders": ""}
        return {"error": f"Sin datos para {ticker_input} (FMP no devolvió nada)"}

    ratios = fmp_get_stable("ratios-ttm", fmp_ticker) or {}
    metrics = fmp_get_stable("key-metrics-ttm", fmp_ticker) or {}
    profile = fmp_get_stable("profile", fmp_ticker) or {}

    # Si los demás dieron premium, los ignoramos
    if ratios.get("_premium"): ratios = {}
    if metrics.get("_premium"): metrics = {}
    if profile.get("_premium"): profile = {}

    def g(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None: return v
        return None

    return {
        "ticker": fmp_ticker,
        "name": g(quote, "name", "nombre") or g(profile, "companyName", "nombre") or ticker_up,
        "price": g(quote, "price", "precio"),
        "change_pct": g(quote, "changesPercentage", "cambioPorcentaje"),
        "previous_close": g(quote, "previousClose"),
        "pe": g(quote, "pe") or g(ratios, "priceEarningsRatioTTM", "peRatioTTM"),
        "pe_forward": g(ratios, "forwardPE", "priceEarningsToGrowthRatioTTM"),
        "eps": g(quote, "eps"),
        "market_cap": g(quote, "marketCap"),
        "year_high": g(quote, "yearHigh"),
        "year_low": g(quote, "yearLow"),
        "roe": g(ratios, "returnOnEquityTTM"),
        "roic": g(metrics, "roicTTM", "returnOnInvestedCapitalTTM"),
        "op_margin": g(ratios, "operatingProfitMarginTTM"),
        "fcf_per_share": g(metrics, "freeCashFlowPerShareTTM"),
        "ev_ebitda": g(metrics, "enterpriseValueOverEBITDATTM"),
        "debt_equity": g(ratios, "debtEquityRatioTTM", "debtToEquityTTM"),
        "dividend_yield": g(quote, "dividendYield"),
        "sector": g(profile, "sector"),
        "industry": g(profile, "industry"),
        "currency": g(profile, "currency") or "USD",
    }

def format_data_for_claude(data):
    if not data: return ""
    if data.get("error"): return f"DATOS NO DISPONIBLES: {data['error']}"
    if data.get("is_european"):
        return f"DATOS EUROPEO {data['ticker']} via Tavily:\n{data.get('tavily','')}"
    if data.get("_fallback"):
        # Small-cap o no cubierto en FMP free → datos de Tavily + SEC + insiders
        parts = [f"DATOS DE {data['ticker']} (FMP free no lo cubre — fuentes alternativas):"]
        if data.get("tavily"):
            parts.append(f"\nNOTICIAS Y DATOS WEB:\n{data['tavily']}")
        if data.get("sec"):
            parts.append(f"\n{data['sec']}")
        if data.get("insiders"):
            parts.append(f"\n{data['insiders']}")
        return "\n".join(parts)

    lines = [f"DATOS REALES VERIFICADOS FMP ({datetime.now().strftime('%d/%m/%Y %H:%M')}):"]
    lines.append(f"Empresa: {data.get('name')} ({data.get('ticker')})")
    if data.get("sector"): lines.append(f"Sector: {data['sector']}")
    if data.get("industry"): lines.append(f"Industria: {data['industry']}")
    if data.get("price") is not None:
        lines.append(f"Precio: ${data['price']:.2f}")
    if data.get("change_pct") is not None:
        lines.append(f"Variación día: {data['change_pct']:+.2f}%")
    if data.get("previous_close"):
        lines.append(f"Cierre anterior: ${data['previous_close']:.2f}")
    if data.get("pe"):
        lines.append(f"PER trailing: {data['pe']:.1f}x")
    if data.get("pe_forward"):
        lines.append(f"PER forward: {data['pe_forward']:.1f}x")
    if data.get("eps"):
        lines.append(f"EPS: ${data['eps']:.2f}")
    if data.get("market_cap"):
        lines.append(f"Market cap: ${data['market_cap']/1e9:.1f}B")
    if data.get("year_high") and data.get("year_low"):
        lines.append(f"Rango 52s: ${data['year_low']:.2f} - ${data['year_high']:.2f}")
        if data.get("price"):
            pct = (data['price'] - data['year_low']) / (data['year_high'] - data['year_low']) * 100
            lines.append(f"Posición en rango 52s: {pct:.1f}%")
    if data.get("roe"):
        lines.append(f"ROE: {data['roe']*100:.1f}%")
    if data.get("roic"):
        lines.append(f"ROIC: {data['roic']*100:.1f}%")
    if data.get("op_margin"):
        lines.append(f"Margen operativo: {data['op_margin']*100:.1f}%")
    if data.get("fcf_per_share"):
        lines.append(f"FCF por acción: ${data['fcf_per_share']:.2f}")
    if data.get("ev_ebitda"):
        lines.append(f"EV/EBITDA: {data['ev_ebitda']:.1f}x")
    if data.get("debt_equity"):
        lines.append(f"Deuda/Equity: {data['debt_equity']:.2f}")
    if data.get("dividend_yield"):
        d = data['dividend_yield']
        lines.append(f"Dividend yield: {d*100:.2f}%" if d < 1 else f"Dividend yield: {d:.2f}%")
    return "\n".join(lines)

def get_real_data_multi(tickers_list):
    parts = []
    for t in tickers_list:
        d = get_real_data(t)
        if d and not d.get("error"):
            parts.append(format_data_for_claude(d))
    return "\n\n".join(parts)

# ═════════════════════════════════════════════════════
#  TAVILY + FALLBACK FED/SEC (de ChatGPT — bueno)
# ═════════════════════════════════════════════════════
def _extract_rss_items(xml_text, limit=3):
    items = re.findall(r"<item>(.*?)</item>", xml_text, flags=re.S | re.I)
    out = []
    for item in items[:limit]:
        title_m = re.search(r"<title>(.*?)</title>", item, flags=re.S | re.I)
        link_m = re.search(r"<link>(.*?)</link>", item, flags=re.S | re.I)
        if title_m:
            title = re.sub(r"\s+", " ", re.sub(r"<.*?>", "", title_m.group(1))).strip()
            link = link_m.group(1).strip() if link_m else ""
            out.append((title[:140], link))
    return out

def fallback_market_sources(query, n=3):
    """Fuentes oficiales RSS cuando Tavily falla."""
    feeds = [
        ("FED", "https://www.federalreserve.gov/feeds/press_all.xml"),
        ("SEC", "https://www.sec.gov/news/pressreleases.rss"),
        ("YahooMarkets", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US"),
    ]
    snippets = []
    for name, url in feeds:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "jarvis-miki/1.0"})
            if r.status_code != 200: continue
            for title, link in _extract_rss_items(r.text, limit=2):
                snippets.append(f"[{name}] {title}")
        except: continue
    if not snippets: return ""
    return "Fuentes oficiales:\n" + "\n".join(snippets[:n*2])

# ═════════════════════════════════════════════════════
#  SEC EDGAR — Filings oficiales (sin key, ilimitado)
# ═════════════════════════════════════════════════════
SEC_TICKER_CIK = {}

def sec_get_cik(ticker):
    ticker_up = ticker.upper()
    if ticker_up in SEC_TICKER_CIK:
        return SEC_TICKER_CIK[ticker_up]
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": "jarvis-miki/1.0 personal"}, timeout=12)
        if r.status_code != 200: return None
        for entry in r.json().values():
            if entry.get("ticker", "").upper() == ticker_up:
                cik = str(entry["cik_str"]).zfill(10)
                SEC_TICKER_CIK[ticker_up] = cik
                return cik
    except Exception as e:
        logging.error(f"SEC CIK {ticker}: {e}")
    return None

def sec_get_filings(ticker, n=5):
    cik = sec_get_cik(ticker)
    if not cik: return ""
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                         headers={"User-Agent": "jarvis-miki/1.0 personal"}, timeout=12)
        if r.status_code != 200: return ""
        recent = r.json().get("filings", {}).get("recent", {})
        forms = recent.get("form", [])[:n*3]
        dates = recent.get("filingDate", [])[:n*3]
        out, count = [], 0
        for i, form in enumerate(forms):
            if form in ("10-K", "10-Q", "8-K", "DEF 14A", "4", "20-F"):
                date = dates[i] if i < len(dates) else "?"
                out.append(f"  - {form} ({date})")
                count += 1
                if count >= n: break
        if out:
            return f"SEC EDGAR filings de {ticker} (CIK {cik}):\n" + "\n".join(out)
    except Exception as e:
        logging.error(f"SEC filings {ticker}: {e}")
    return ""

# ═════════════════════════════════════════════════════
#  OPENINSIDER — Compras/ventas directivos (sin key)
# ═════════════════════════════════════════════════════
def openinsider_get(ticker, n=10):
    try:
        url = f"http://openinsider.com/screener?s={ticker}&fd=730&xp=1&xs=1&sortcol=0&cnt={n}&page=1"
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 jarvis-miki"})
        if r.status_code != 200: return ""
        rows = re.findall(r'<tr>(.*?)</tr>', r.text, flags=re.S)
        out = []
        for row in rows[1:n+1]:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, flags=re.S)
            if len(cells) >= 8:
                clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                fecha = clean[1][:10] if len(clean) > 1 else "?"
                cargo = clean[5][:30] if len(clean) > 5 else "?"
                tipo = clean[6] if len(clean) > 6 else "?"
                qty = clean[8] if len(clean) > 8 else "?"
                price = clean[7] if len(clean) > 7 else "?"
                if tipo and qty:
                    out.append(f"  - {fecha} | {cargo} | {tipo} | {qty} @ {price}")
        if out:
            return f"INSIDERS {ticker} (últimos {len(out)}):\n" + "\n".join(out[:n])
    except Exception as e:
        logging.error(f"OpenInsider {ticker}: {e}")
    return ""

# ═════════════════════════════════════════════════════
#  FRED — Macro USA con API key
# ═════════════════════════════════════════════════════
FRED_SERIES = {
    "DFF": "Federal Funds Rate",
    "CPIAUCSL": "CPI inflación USA",
    "UNRATE": "Tasa de paro USA",
    "DGS10": "Bono 10 años USA",
    "VIXCLS": "VIX volatilidad",
    "DTWEXBGS": "Índice dólar",
}

def fred_get(series_id):
    if not FRED_KEY: return None
    try:
        r = requests.get("https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": FRED_KEY,
                    "file_type": "json", "sort_order": "desc", "limit": 1},
            timeout=10)
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if obs and obs[0].get("value") not in (".", None):
                return {"value": obs[0]["value"], "date": obs[0]["date"]}
    except Exception as e:
        logging.error(f"FRED {series_id}: {e}")
    return None

def fred_macro_snapshot():
    if not FRED_KEY: return ""
    out = ["MACRO USA (FRED oficial):"]
    for sid, label in FRED_SERIES.items():
        d = fred_get(sid)
        if d:
            out.append(f"  - {label}: {d['value']} ({d['date']})")
    return "\n".join(out) if len(out) > 1 else ""

# ═════════════════════════════════════════════════════
#  ECB — Macro Europa (sin key)
# ═════════════════════════════════════════════════════
def ecb_macro_snapshot():
    series = {
        "FM.B.U2.EUR.4F.KR.DFR.LEV": "Tipo depósito BCE",
        "FM.B.U2.EUR.4F.KR.MRR_FR.LEV": "Tipo refinanciación BCE",
    }
    out = ["MACRO EUROPA (ECB oficial):"]
    for sid, label in series.items():
        try:
            r = requests.get(f"https://data-api.ecb.europa.eu/service/data/{sid}",
                params={"format": "jsondata", "lastNObservations": "1"},
                headers={"Accept": "application/json"}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                obs_dict = data.get("dataSets", [{}])[0].get("series", {})
                for val in obs_dict.values():
                    obs_data = val.get("observations", {})
                    if obs_data:
                        last_val = list(obs_data.values())[0][0]
                        out.append(f"  - {label}: {last_val}")
                        break
        except Exception as e:
            logging.error(f"ECB {sid}: {e}")
    return "\n".join(out) if len(out) > 1 else ""

# ═════════════════════════════════════════════════════
#  iShares — Holdings ETFs oficiales
# ═════════════════════════════════════════════════════
def ishares_top_holdings(etf_ticker, n=10):
    urls = {
        "IVV": "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/1467271812596.ajax?fileType=json&fileName=IVV_holdings",
        "INDA": "https://www.ishares.com/us/products/239755/ishares-msci-india-etf/1467271812596.ajax?fileType=json&fileName=INDA_holdings",
    }
    url = urls.get(etf_ticker.upper())
    if not url: return ""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "jarvis-miki/1.0"})
        if r.status_code != 200: return ""
        text = r.text.lstrip('\ufeff')
        data = json.loads(text)
        rows = data.get("aaData", [])[:n]
        out = [f"TOP {n} HOLDINGS de {etf_ticker} (iShares oficial):"]
        for row in rows:
            try:
                ticker_h = row[0] if len(row) > 0 else "?"
                name = (row[1] if len(row) > 1 else "?")[:40]
                weight = row[5] if len(row) > 5 else "?"
                if isinstance(weight, dict):
                    weight = weight.get("display", "?")
                out.append(f"  - {ticker_h} {name}: {weight}")
            except: continue
        return "\n".join(out) if len(out) > 1 else ""
    except Exception as e:
        logging.error(f"iShares {etf_ticker}: {e}")
    return ""

def search_news(query, n=2):
    if not TAVILY_KEY:
        return fallback_market_sources(query, n=n)
    try:
        r = requests.post("https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": query,
                  "max_results": n, "search_depth": "basic"}, timeout=12)
        results = r.json().get("results", [])[:n]
        if not results:
            return fallback_market_sources(query, n=n)
        return "\n".join([
            f"[{x['url'].split('/')[2]}] {x['title']}: {x['content'][:200]}"
            for x in results
        ])
    except:
        return fallback_market_sources(query, n=n)

# ═════════════════════════════════════════════════════
#  MERCADO con ZoneInfo (de ChatGPT — correcto)
# ═════════════════════════════════════════════════════
def market_status_human():
    if TZ_OK:
        now_madrid = datetime.now(ZoneInfo("Europe/Madrid"))
        now_ny = datetime.now(ZoneInfo("America/New_York"))
        weekday = now_madrid.weekday()
        eu_open = 9 <= now_madrid.hour < 17
        nyse_open = (now_ny.hour > 9 or (now_ny.hour == 9 and now_ny.minute >= 30)) and now_ny.hour < 16
    else:
        now = datetime.now(timezone.utc)
        weekday = now.weekday()
        hour_utc = now.hour
        eu_open = 7 <= hour_utc < 16
        nyse_open = 13 <= hour_utc < 20

    dia_es = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo'][weekday]
    if weekday == 5: return "HOY ES SÁBADO - todos los mercados cerrados"
    if weekday == 6: return "HOY ES DOMINGO - todos los mercados cerrados"
    if nyse_open and eu_open: return f"Es {dia_es}. NYSE y Europa abiertas."
    if eu_open and not nyse_open: return f"Es {dia_es}. Europa abierta. NYSE abre 15:30 España."
    if not eu_open and nyse_open: return f"Es {dia_es}. NYSE abierta. Europa ya cerró."
    return f"Es {dia_es}, fuera de horario."

# ═════════════════════════════════════════════════════
#  SYSTEM PROMPTS — TARJETA y CHAT
# ═════════════════════════════════════════════════════
def get_system_card():
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercado = market_status_human()
    return f"""Eres JARVIS, analista bursátil premium de Miki.

Hoy: {hoy} {hora} (España). Mercado: {mercado}

CUANDO TE PIDA DATOS DE UNA EMPRESA, RESPONDES SIEMPRE CON ESTA TARJETA EXACTA:

🔴 [EMPRESA] — [TEMA PRINCIPAL]

[frase principal fuerte, clara, directa, una sola línea]

▪️ Dato 1
▪️ Dato 2
▪️ Dato 3
▪️ Dato 4
▪️ Dato 5

Lectura Jarvis:
[interpretación corta, útil. 2-3 frases máximo]

Impacto en tesis:
[positivo / neutro / negativo]

Señal:
🟢 COMPRAR / ACUMULAR
🟡 MANTENER / VIGILAR
🔴 REDUCIR / VENDER
⚪ NO CONCLUYENTE

═══ REGLAS ABSOLUTAS ═══
1. UNA sola idea principal por respuesta
2. Datos primero, interpretación después
3. SIEMPRE terminar con señal final
4. NUNCA inventes precios, PER, valor intrínseco
5. Si falta dato real → ⚪ NO CONCLUYENTE
6. NUNCA párrafos largos
7. Frases cortas, verbos fuertes
8. Visual y limpio para móvil

═══ TÍTULOS DE TARJETA ═══
RESULTADOS, VALORACIÓN, BUSCADOR, CLOUD, AZURE, AWS, YOUTUBE, MÁRGENES,
CAPEX, REACCIÓN, GUÍA, RPO, MONETIZACIÓN, MOAT

═══ DATOS ÚTILES PARA BULLETS ═══
Ventas, EBIT, EPS, Guidance, PER, EV/FCF, valor intrínseco, precio actual,
reacción mercado, CapEx, márgenes, ROIC, dividendo, FCF, posición en rango 52s

═══ FRASES PRINCIPALES BUENAS ═══
- "La IA está acelerando Search, no frenándolo"
- "El mercado castiga el CapEx, no el negocio"
- "La tesis sigue intacta"
- "Margen de seguridad agotado"
- "Buenos resultados pero cara para entrar"

═══ VOCABULARIO QUE SÍ ═══
tesis, refuerza, deteriora, acelera, desacelera, beat, miss, guidance,
margen, CapEx, valoración, convicción, oportunidad, vigilancia, demanda,
moat, pricing power, ROIC, EV/FCF, margen de seguridad

═══ VOCABULARIO PROHIBIDO ═══
"interesante", "parece", "quizá", "podría ser", "muy buena empresa",
"de alguna forma", "en cierto modo", "resulta curioso"

═══ DATOS REALES ═══
Si recibes "DATOS REALES VERIFICADOS FMP" en el mensaje, son del DÍA, ÚSALOS.
NUNCA inventes números. Si falta uno, di ⚪ NO CONCLUYENTE en esa parte.

═══ CARTERA REAL DE MIKI ═══
GOOGL +77.4% 17.8% Alta convicción · ZEG +70.8% · JNJ +61.4% · Gold +41.9%
AAPL +20.6% · CELH +20.9% · SmCap +24.5% · SP500 +24.1% · Europe +23.3%
TRET +6.9% · SSNC +5.5%
PERDIENDO: MSFT -12.5% · MONC -3.8% · TXRH -4.1% · India -7.4%
NUEVA: VISA · VENDIDA: NKE
"""

def get_system_chat():
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercado = market_status_human()
    return f"""Eres JARVIS, el colega de Miki para inversión.
Modo CONVERSACIÓN: NO uses tarjeta visual, habla normal.

Hoy: {hoy} {hora} (España). Mercado: {mercado}

═══ TU SUPER CEREBRO ═══
Tienes integrado DEXTER, tu motor de research profundo. Funciona en 4 pasos:
1) PLANNING: planificas qué fuentes usar
2) EXECUTION: cruzas FMP + SEC EDGAR + OpenInsider + FRED + ECB + Tavily
3) REFLECTION: detectas huecos y contradicciones
4) ANSWER: rellenas la PLANTILLA EXACTA DE MIKI con datos verificados

CUANDO Miki pide CUALQUIER valoración → ya se activa Dexter automáticamente.
TU OBLIGACIÓN cuando llegue resultado de Dexter: SIEMPRE usar la plantilla EXACTA, las 9 secciones,
sin saltarte ninguna, sin inventar datos, sin pegote literario.

═══ CÓMO HABLAS (modo conversación) ═══
- COLOQUIAL ESPAÑOL DE ESPAÑA. Como en un bar.
- Frases cortas, naturales.
- Usa: "joder", "vaya", "pinta bien", "está jodido", "ojo con esto"
- NUNCA estilo teletipo
- NUNCA listas con bullets

Si Miki está agobiado, primero le escuchas. Luego ayudas.

═══ FUENTES DE DATOS (REALES, NO INVENTAR) ═══
- FMP /stable/: precio, PER, ROE, ROIC, FCF, market cap (si FMP free no cubre, hay fallback)
- SEC EDGAR: 10-K, 10-Q, 8-K, Forms 4 (insiders) - sin límite, oficial
- OpenInsider: compras/ventas directivos
- FRED: macro USA (FED, CPI, paro, bono 10y, VIX, dólar)
- ECB: macro Europa (tipos depósito BCE, refinanciación)
- iShares: holdings oficiales SP500 e India
- Tavily: noticias actuales + fallback small caps

═══ PLANTILLA DE VALORACIÓN ═══
Tienes cargada la PLANTILLA EXACTA de "Invertir Desde 0" (9 secciones obligatorias):
1) Tesis (3 líneas)
2) Datos base (precio, market cap, sector)
3) Calidad (ROE, margen, deuda, FCF)
4) Crecimiento y ejecución
5) Valoración con FÓRMULAS (rango 52s, FCF Yield, De-rating PER)
6) Precio justo (3 escenarios + margen seguridad)
7) Riesgos (máx 3)
8) Decisión operativa (acción, zona, tamaño, invalidación)
9) Convicción 0-10 + frase final

═══ CARTERA ACTUAL ═══
€34.145 +22%. GOOGL +77% (la grande). MSFT -12.5% (vigilar).
VISA nueva. NKE vendida.

═══ LONGITUD POR DEFECTO ═══
- Saludo: 1-2 frases
- Pregunta puntual: 2-4 frases
- Conversación: 3-6 frases máximo
- Resultado Dexter / valoración: las 9 secciones de la plantilla SIN RECORTAR
"""

# ═════════════════════════════════════════════════════
#  MEMORIA SQLITE + SUPABASE
# ═════════════════════════════════════════════════════
history = {}
memory_lock = threading.Lock()
processed_alert_hashes = set()

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def _memory_conn():
    conn = sqlite3.connect(Path(MEMORY_DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS jarvis_memory_local (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL, role TEXT NOT NULL,
        content TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS jarvis_knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
        updated_at TEXT NOT NULL, UNIQUE(chat_id, key))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS jarvis_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tx_hash TEXT NOT NULL UNIQUE, broker TEXT, fecha TEXT,
        accion TEXT, ticker TEXT, importe_eur REAL, asunto TEXT,
        created_at TEXT NOT NULL)""")
    conn.commit()
    return conn

def save_memory_local(chat_id, role, content):
    try:
        with memory_lock:
            conn = _memory_conn()
            conn.execute("INSERT INTO jarvis_memory_local(chat_id,role,content,created_at) VALUES(?,?,?,?)",
                (str(chat_id), role, content[:2000], utc_now()))
            conn.commit(); conn.close()
    except Exception as e:
        logging.error(f"SQLite save: {e}")

def load_memory_local(chat_id, limit=6):
    try:
        with memory_lock:
            conn = _memory_conn()
            rows = conn.execute("""SELECT role, content FROM (
                SELECT role, content, id FROM jarvis_memory_local
                WHERE chat_id=? ORDER BY id DESC LIMIT ?)
                ORDER BY id ASC""", (str(chat_id), int(limit))).fetchall()
            conn.close()
        return [{"role": r[0], "content": r[1]} for r in rows]
    except: return []

def upsert_knowledge(chat_id, key, value):
    try:
        with memory_lock:
            conn = _memory_conn()
            conn.execute("DELETE FROM jarvis_knowledge WHERE chat_id=? AND key=?", (str(chat_id), key))
            conn.execute("INSERT INTO jarvis_knowledge(chat_id,key,value,updated_at) VALUES(?,?,?,?)",
                (str(chat_id), key, value[:2000], utc_now()))
            conn.commit(); conn.close()
    except Exception as e:
        logging.error(f"Knowledge upsert: {e}")

def list_knowledge(chat_id, limit=8):
    try:
        with memory_lock:
            conn = _memory_conn()
            rows = conn.execute("SELECT key,value FROM jarvis_knowledge WHERE chat_id=? ORDER BY updated_at DESC LIMIT ?",
                (str(chat_id), int(limit))).fetchall()
            conn.close()
        return rows
    except: return []

def persist_movements(movements):
    if not movements or "error" in movements[0]: return []
    nuevos = []
    try:
        with memory_lock:
            conn = _memory_conn()
            for m in movements:
                tx_hash = str(abs(hash(f"{m.get('broker')}|{m.get('fecha')}|{m.get('accion')}|{m.get('ticker')}|{m.get('importe_eur')}|{m.get('asunto')}")))
                cur = conn.execute("SELECT id FROM jarvis_transactions WHERE tx_hash=?", (tx_hash,))
                if cur.fetchone() is None:
                    conn.execute("""INSERT INTO jarvis_transactions
                        (tx_hash,broker,fecha,accion,ticker,importe_eur,asunto,created_at)
                        VALUES(?,?,?,?,?,?,?,?)""",
                        (tx_hash, m.get("broker"), m.get("fecha"), m.get("accion"),
                         m.get("ticker"), m.get("importe_eur"), m.get("asunto"), utc_now()))
                    nuevos.append(m)
            conn.commit(); conn.close()
    except Exception as e:
        logging.error(f"Persist mov: {e}")
    return nuevos

def recent_transactions(limit=8):
    try:
        with memory_lock:
            conn = _memory_conn()
            rows = conn.execute("""SELECT broker,fecha,accion,ticker,importe_eur
                FROM jarvis_transactions ORDER BY id DESC LIMIT ?""", (int(limit),)).fetchall()
            conn.close()
        return rows
    except: return []

def save_memory(chat_id, role, content):
    save_memory_local(chat_id, role, content)
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"chat_id": str(chat_id), "role": role, "content": content[:1000],
                  "created_at": utc_now()}, timeout=5)
    except: pass

def load_memory(chat_id, limit=6):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return load_memory_local(chat_id, limit=limit)
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"chat_id": f"eq.{chat_id}", "order": "created_at.desc", "limit": limit},
            timeout=5)
        rows = r.json()
        if isinstance(rows, list):
            return [{"role": x["role"], "content": x["content"]} for x in reversed(rows)]
    except: pass
    return load_memory_local(chat_id, limit=limit)

# ═════════════════════════════════════════════════════
#  PLANTILLA DE VALORACIÓN
# ═════════════════════════════════════════════════════
def load_template():
    p = Path(TEMPLATE_PATH)
    if p.exists():
        try:
            txt = p.read_text(encoding="utf-8").strip()
            if txt: return txt
        except: pass
    return "Plantilla no encontrada en " + TEMPLATE_PATH

# ═════════════════════════════════════════════════════
#  CLAUDE — con modo degradado si falta key
# ═════════════════════════════════════════════════════
def ask_claude(chat_id, text, system_prompt, web_data="", max_tokens=600):
    if not ANTHROPIC_KEY:
        if web_data:
            return f"Datos disponibles (sin Claude para análisis):\n\n{web_data[:2000]}"
        return "Sin ANTHROPIC_API_KEY configurada en Render."

    mem = load_memory(chat_id, limit=4)
    facts = list_knowledge(chat_id, limit=6)
    txs = recent_transactions(limit=4)
    if chat_id not in history: history[chat_id] = []

    facts_txt = "\n".join([f"- {k}: {v}" for k,v in facts]) if facts else ""
    tx_txt = "\n".join([f"- {t[0]} {t[2]} {t[3] or '?'} {t[4] or ''} EUR" for t in txs]) if txs else ""

    extras = ""
    if facts_txt: extras += f"\n\nMEMORIA_LARGA:\n{facts_txt}"
    if tx_txt: extras += f"\n\nTX_GMAIL:\n{tx_txt}"

    if web_data:
        content = f"{text}\n\n{web_data}{extras}"
    else:
        content = text + extras

    history[chat_id].append({"role": "user", "content": content})
    all_msgs = mem + history[chat_id][-4:]

    msgs = []; last_role = None
    for m in all_msgs:
        if m["role"] != last_role:
            msgs.append(m); last_role = m["role"]
        else:
            msgs[-1]["content"] = m["content"]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs: msgs = [{"role": "user", "content": text}]

    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                  "system": system_prompt, "messages": msgs}, timeout=45)
        data = r.json()
        if "error" in data:
            return f"Vaya, problema con la API: {data['error'].get('message','')[:100]}."
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text[:600])
        save_memory(chat_id, "assistant", reply[:600])
        return reply
    except Exception as e:
        logging.error(f"Claude: {e}")
        return "Sin conexión con la API. Pruébalo en 30 segundos."

# ═════════════════════════════════════════════════════
#  DEXTER-STYLE — Planning + Execution + Reflection
#  Inspirado en https://github.com/virattt/dexter
#  Versión Python integrada en Jarvis (no requiere instalación)
# ═════════════════════════════════════════════════════
def claude_call(system_prompt, user_text, max_tokens=600):
    """Llamada simple a Claude sin memoria (para planificación interna)."""
    if not ANTHROPIC_KEY: return None
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                  "system": system_prompt, "messages": [{"role": "user", "content": user_text}]},
            timeout=45)
        data = r.json()
        if "error" in data: return None
        return data["content"][0]["text"]
    except Exception as e:
        logging.error(f"Dexter Claude: {e}")
        return None

def dexter_research(chat_id, ticker, user_question):
    """
    Filosofía Dexter:
    1) PLANNING: Claude diseña un plan de research específico
    2) EXECUTION: ejecuta TODAS las fuentes disponibles para ese ticker
    3) REFLECTION: revisa los datos y detecta huecos
    4) ANSWER: respuesta final con plantilla EXACTA de Miki
    """
    log_step = lambda s: logging.info(f"[DEXTER {ticker}] {s}")

    # ─── PASO 1: PLANNING ───
    plan_prompt = (
        f"Eres un planner de research financiero. El usuario pregunta:\n\"{user_question}\"\n"
        f"Sobre el ticker: {ticker}\n\n"
        f"Tienes estas fuentes disponibles:\n"
        f"- FMP /stable/ (precio, PER, ROE, ROIC, market cap, FCF)\n"
        f"- SEC EDGAR (10-K, 10-Q, 8-K, Forms 4 insiders)\n"
        f"- OpenInsider (compras/ventas insiders detalladas)\n"
        f"- FRED (macro USA: tipos, inflación, paro, bono 10y)\n"
        f"- ECB (macro Europa)\n"
        f"- Tavily (noticias web actuales)\n\n"
        f"Diseña un plan de research de máximo 4 pasos. Cada paso UNA línea. "
        f"Incluye CRUZAR datos de al menos 3 fuentes. No te enrolles, solo el plan."
    )
    plan = claude_call(
        "Eres un planner financiero conciso, en español de España.",
        plan_prompt, max_tokens=300
    )
    log_step(f"Plan: {plan[:200] if plan else 'NULO'}")

    # ─── PASO 2: EXECUTION ───
    log_step("Ejecutando fuentes...")
    fmp_data = format_data_for_claude(get_real_data(ticker))
    sec_data = sec_get_filings(ticker, n=5)
    ins_data = openinsider_get(ticker, n=8)
    news_data = search_news(f"{ticker} earnings revenue guidance latest", n=4)
    macro_data = fred_macro_snapshot() if FRED_KEY else ""

    full_data = (
        f"=== FMP ===\n{fmp_data}\n\n"
        f"=== SEC EDGAR ===\n{sec_data or 'sin filings recientes'}\n\n"
        f"=== INSIDERS (OpenInsider) ===\n{ins_data or 'sin movimientos detectados'}\n\n"
        f"=== NOTICIAS (Tavily) ===\n{news_data or 'sin noticias'}\n\n"
        f"=== MACRO USA (FRED) ===\n{macro_data or 'macro no disponible'}"
    )

    # ─── PASO 3: REFLECTION ───
    reflect_prompt = (
        f"Eres un crítico financiero. Mira estos datos recopilados de {ticker}:\n\n"
        f"{full_data}\n\n"
        f"Identifica en máximo 3 líneas:\n"
        f"1. ¿Qué dato CRÍTICO falta para una valoración seria?\n"
        f"2. ¿Hay alguna contradicción entre fuentes?\n"
        f"3. ¿Hay algún red flag urgente?\n"
        f"Sé directo, español natural."
    )
    reflection = claude_call(
        "Eres un revisor financiero brutalmente honesto.",
        reflect_prompt, max_tokens=300
    )
    log_step(f"Reflection: {reflection[:200] if reflection else 'NULO'}")

    # ─── PASO 4: FINAL con plantilla EXACTA ───
    template = load_template()
    final_prompt = (
        f"Pregunta del usuario: \"{user_question}\"\n"
        f"Ticker: {ticker}\n"
        f"Hoy: {datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"PLAN DE RESEARCH SEGUIDO:\n{plan or '(plan no generado)'}\n\n"
        f"DATOS RECOPILADOS:\n{full_data}\n\n"
        f"REFLEXIÓN CRÍTICA:\n{reflection or '(sin reflexión)'}\n\n"
        f"AHORA: rellena ESTA plantilla EXACTA con los datos reales (no inventes):\n\n{template}\n\n"
        f"Si un dato no existe, escribe 'NO DISPONIBLE' en esa línea pero sigue rellenando el resto. "
        f"Cierra con la decisión clara y la convicción 0-10."
    )
    return ask_claude(chat_id, final_prompt, get_system_chat(), max_tokens=1300)

# ═════════════════════════════════════════════════════
#  EQUIPO JARVIS — Subagentes (estilo TradingAgents)
#  4 ANALISTAS + DEBATE BULL/BEAR + RIESGO + FUND MANAGER
#  Esto se SUMA a Dexter, no lo reemplaza.
# ═════════════════════════════════════════════════════
def jarvis_team_research(chat_id, ticker, user_question):
    """
    Equipo institucional completo:
    1) 4 ANALISTAS en paralelo (Fundamental, Sentiment, Technical, Insider)
    2) DEBATE Bull vs Bear vs Síntesis
    3) GESTOR RIESGO (conservador + agresivo)
    4) FUND MANAGER → decisión final con plantilla EXACTA
    """
    log_step = lambda s: logging.info(f"[EQUIPO {ticker}] {s}")

    # ─── DATOS BASE ───
    fmp_data = format_data_for_claude(get_real_data(ticker))
    sec_data = sec_get_filings(ticker, n=5)
    ins_data = openinsider_get(ticker, n=8)
    news_data = search_news(f"{ticker} earnings revenue guidance latest", n=4)
    macro_data = fred_macro_snapshot() if FRED_KEY else ""

    # ─── 4 ANALISTAS ───
    log_step("4 analistas en paralelo...")

    analyst_fundamental = claude_call(
        "Eres analista FUNDAMENTAL value tipo Buffett/Klarman. Español de España, directo.",
        f"Analiza {ticker} desde fundamentales: ROE, ROIC, margen op, FCF, deuda, calidad capital "
        f"allocation. Datos:\n{fmp_data}\n{sec_data}\n\nDevuelve SOLO 4 líneas:\n"
        f"- Tesis (1 línea)\n- Calidad (1 línea)\n- Valoración (1 línea)\n- Convicción 0-10 (1 línea)",
        max_tokens=300
    )

    analyst_sentiment = claude_call(
        "Eres analista de SENTIMIENTO de mercado (noticias, narrativa, momentum opinión).",
        f"Analiza sentimiento sobre {ticker}.\nNoticias:\n{news_data}\n\n"
        f"4 líneas: tono general, narrativa dominante, riesgo reputacional, score 0-10.",
        max_tokens=250
    )

    analyst_technical = claude_call(
        "Eres analista TÉCNICO (precio, soportes/resistencias, momentum).",
        f"Analiza técnicamente {ticker}:\n{fmp_data}\n\n"
        f"4 líneas: tendencia, posición rango 52s, soporte/resistencia clave, score técnico 0-10.",
        max_tokens=250
    )

    analyst_insider = claude_call(
        "Eres analista de INSIDERS y smart money.",
        f"Analiza movimientos insiders {ticker}:\n{ins_data or 'sin datos'}\n\n"
        f"4 líneas: ¿compras del CEO/CFO recientes?, ¿ventas planeadas o discrecionales?, "
        f"¿señal alcista/bajista?, score 0-10.",
        max_tokens=250
    )

    # ─── DEBATE BULL vs BEAR ───
    log_step("Debate Bull vs Bear...")
    analystas_combined = (
        f"FUNDAMENTAL:\n{analyst_fundamental}\n\n"
        f"SENTIMENT:\n{analyst_sentiment}\n\n"
        f"TECHNICAL:\n{analyst_technical}\n\n"
        f"INSIDER:\n{analyst_insider}"
    )

    bull_case = claude_call(
        "Eres el RESEARCHER ALCISTA. Defiendes la tesis larga con argumentos sólidos.",
        f"Conoces {ticker}. Datos analistas:\n{analystas_combined}\n\n"
        f"Da 3 razones potentes para COMPRAR/MANTENER. Sé concreto, no humo.",
        max_tokens=300
    )

    bear_case = claude_call(
        "Eres el RESEARCHER BAJISTA. Buscas las grietas y riesgos. Sin pesimismo gratuito.",
        f"Conoces {ticker}. Datos analistas:\n{analystas_combined}\n\n"
        f"Da 3 razones potentes para REDUCIR/VENDER o NO comprar. Concreto, basado en datos.",
        max_tokens=300
    )

    # ─── GESTORES DE RIESGO ───
    log_step("Gestores de riesgo...")
    risk_conservative = claude_call(
        "Eres gestor de riesgo CONSERVADOR. Prioridad: preservar capital. Margen seguridad 30%+.",
        f"Para {ticker}, dado este contexto:\n{analystas_combined}\n\nBull:\n{bull_case}\n\n"
        f"Bear:\n{bear_case}\n\nDi tamaño máximo posición (% cartera) y stop mental. 3 líneas.",
        max_tokens=200
    )

    risk_aggressive = claude_call(
        "Eres gestor de riesgo AGRESIVO. Prioridad: rentabilidad asimétrica. Convicción 8+.",
        f"Para {ticker}, dado todo lo anterior, ¿qué tamaño y zona de entrada agresiva? 3 líneas.",
        max_tokens=200
    )

    # ─── FUND MANAGER FINAL → PLANTILLA EXACTA ───
    log_step("Fund manager: rellenando plantilla...")
    template = load_template()

    fund_manager_prompt = (
        f"Eres el FUND MANAGER de Miki. Has recibido el análisis completo de tu equipo sobre {ticker}.\n"
        f"Pregunta original: \"{user_question}\"\n"
        f"Hoy: {datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"═══ ANÁLISIS DEL EQUIPO ═══\n{analystas_combined}\n\n"
        f"═══ DEBATE ═══\n🐂 BULL:\n{bull_case}\n\n🐻 BEAR:\n{bear_case}\n\n"
        f"═══ RIESGO ═══\n🛡️ Conservador:\n{risk_conservative}\n\n⚡ Agresivo:\n{risk_aggressive}\n\n"
        f"═══ DATOS REALES ═══\n{fmp_data}\n\n{sec_data}\n\n{ins_data}\n\n{macro_data}\n\n"
        f"═══ TU TAREA ═══\n"
        f"RELLENA EXACTAMENTE esta plantilla con datos reales. NO inventes nada. "
        f"Si falta dato, pon 'NO DISPONIBLE' y sigue. Las 9 secciones obligatorias:\n\n"
        f"{template}\n\n"
        f"Después de la plantilla añade un epígrafe corto:\n"
        f"═══ DECISIÓN DEL EQUIPO ═══\nUna línea por miembro: Fundamental, Sentiment, Technical, "
        f"Insider, Bull, Bear, Riesgo conservador, Riesgo agresivo, **TÚ (Fund Manager)**."
    )

    return ask_claude(chat_id, fund_manager_prompt, get_system_chat(), max_tokens=1700)

# ═════════════════════════════════════════════════════
#  DCF CALCULATOR — Para JNJ, SSNC, mature companies
# ═════════════════════════════════════════════════════
def dcf_calculator(fcf_actual, growth_rate=0.05, discount_rate=0.10,
                   terminal_growth=0.03, years=10, shares_outstanding=None):
    """
    DCF simple value-investing.
    Devuelve dict con valor intrínseco por acción + escenarios.
    Solo para empresas maduras (NO tech de alto crecimiento).
    """
    try:
        if not fcf_actual or fcf_actual <= 0:
            return {"error": "FCF inválido"}

        # Proyección 10 años
        fcf_proyectado = []
        fcf = fcf_actual
        for year in range(1, years + 1):
            fcf = fcf * (1 + growth_rate)
            fcf_proyectado.append(fcf)

        # Valor presente de cada FCF
        vp_fcf = sum(fcf_proyectado[i] / ((1 + discount_rate) ** (i + 1)) for i in range(years))

        # Valor terminal (modelo Gordon)
        vt = fcf_proyectado[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
        vp_terminal = vt / ((1 + discount_rate) ** years)

        valor_total = vp_fcf + vp_terminal

        result = {
            "valor_total_empresa": valor_total,
            "vp_fcf_10y": vp_fcf,
            "vp_terminal": vp_terminal,
            "fcf_actual": fcf_actual,
            "growth_rate": growth_rate,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
        }

        if shares_outstanding and shares_outstanding > 0:
            result["valor_por_accion"] = valor_total / shares_outstanding

        return result
    except Exception as e:
        return {"error": str(e)}

def dcf_full_analysis(ticker):
    """DCF completo con datos reales FMP + 3 escenarios."""
    data = get_real_data(ticker)
    if data.get("error") or data.get("_fallback") or data.get("is_european"):
        return f"DCF no disponible para {ticker}: necesito datos FMP completos."

    market_cap = data.get("market_cap")
    fcf_per_share = data.get("fcf_per_share")
    price = data.get("price")

    if not (market_cap and fcf_per_share and price):
        return f"DCF {ticker}: faltan datos (market_cap, FCF/share o precio)."

    shares = market_cap / price if price else None
    fcf_total = fcf_per_share * shares if shares else None

    if not fcf_total or fcf_total <= 0:
        return f"DCF {ticker}: FCF no positivo, modelo no aplicable."

    # 3 escenarios
    conservador = dcf_calculator(fcf_total, growth_rate=0.03, discount_rate=0.11,
                                  terminal_growth=0.02, shares_outstanding=shares)
    base = dcf_calculator(fcf_total, growth_rate=0.05, discount_rate=0.10,
                          terminal_growth=0.03, shares_outstanding=shares)
    optimista = dcf_calculator(fcf_total, growth_rate=0.08, discount_rate=0.09,
                                terminal_growth=0.04, shares_outstanding=shares)

    out = [f"DCF de {ticker} (precio actual: ${price:.2f}):"]
    out.append(f"  Conservador (g=3%, r=11%): ${conservador.get('valor_por_accion',0):.2f}/acción")
    out.append(f"  Base (g=5%, r=10%): ${base.get('valor_por_accion',0):.2f}/acción")
    out.append(f"  Optimista (g=8%, r=9%): ${optimista.get('valor_por_accion',0):.2f}/acción")

    if base.get("valor_por_accion"):
        margen = (base["valor_por_accion"] - price) / base["valor_por_accion"] * 100
        out.append(f"  Margen seguridad (escenario base): {margen:+.1f}%")

    return "\n".join(out)

# ═════════════════════════════════════════════════════
#  ALERTAS AUTOMÁTICAS — caída fuerte de posición
# ═════════════════════════════════════════════════════
ALERT_THRESHOLDS = {
    # ticker: (% caída diaria, % subida diaria)
    "default": (-3.0, 5.0),
}

def check_portfolio_alerts():
    """Revisa cartera y avisa si alguna posición cae/sube fuerte."""
    if not MIKI_CHAT_ID: return
    cartera = ["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "SSNC", "TXRH", "CELH"]
    alerts = []
    for ticker in cartera:
        data = get_real_data(ticker)
        if data.get("error") or data.get("_fallback"): continue
        change = data.get("change_pct")
        if change is None: continue
        down, up = ALERT_THRESHOLDS.get(ticker, ALERT_THRESHOLDS["default"])
        if change <= down:
            alerts.append(f"🔴 {ticker} cae {change:+.2f}% hoy (precio ${data.get('price','?'):.2f})")
        elif change >= up:
            alerts.append(f"🟢 {ticker} sube {change:+.2f}% hoy (precio ${data.get('price','?'):.2f})")
    if alerts:
        msg = "🚨 ALERTAS DE CARTERA · " + datetime.now().strftime('%d/%m/%Y %H:%M') + "\n\n"
        msg += "\n".join(alerts)
        msg += "\n\nDi \"valórame [TICKER]\" para análisis profundo."
        send(MIKI_CHAT_ID, msg)

def alerts_loop():
    """Revisa alertas cada hora durante mercado USA abierto."""
    if not MIKI_CHAT_ID: return
    time.sleep(180)
    while True:
        try:
            # Solo en horario USA aproximado (15:30-22:00 España)
            now = datetime.now()
            if now.weekday() < 5 and 15 <= now.hour < 22:
                check_portfolio_alerts()
        except Exception as e:
            logging.error(f"Alerts: {e}")
        time.sleep(3600)  # 1 hora

# ═════════════════════════════════════════════════════
#  FUENTES EXTRA — Wikipedia + EconDB (filosofía OpenBB)
# ═════════════════════════════════════════════════════
def wiki_company_summary(company_name, lang="en"):
    """Resumen Wikipedia de una empresa (sin key)."""
    try:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{company_name.replace(' ', '_')}"
        r = requests.get(url, timeout=10, headers={"User-Agent": "jarvis-miki/1.0"})
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "")[:600]
            if extract:
                return f"WIKIPEDIA ({company_name}):\n{extract}"
    except Exception as e:
        logging.error(f"Wiki {company_name}: {e}")
    return ""

def get_company_full_context(ticker, name=None):
    """Junta TODAS las fuentes para contexto completo de una empresa."""
    out = []
    fmp = format_data_for_claude(get_real_data(ticker))
    if fmp: out.append(fmp)
    sec = sec_get_filings(ticker, n=3)
    if sec: out.append(sec)
    ins = openinsider_get(ticker, n=5)
    if ins: out.append(ins)
    if name:
        wiki = wiki_company_summary(name)
        if wiki: out.append(wiki)
    news = search_news(f"{ticker} stock earnings news latest", n=3)
    if news: out.append(f"NOTICIAS:\n{news}")
    return "\n\n".join(out)


def tts(text):
    if not ELEVENLABS_KEY: return None
    try:
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            json={"text": text[:500], "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}, timeout=30)
        return r.content if r.status_code == 200 else None
    except: return None

def transcribe_voice(file_id):
    if not OPENAI_KEY: return None
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
                         params={"file_id": file_id}, timeout=10)
        file_path = r.json()["result"]["file_path"]
        audio = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=30).content
        r = requests.post("https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files={"file": ("voice.ogg", audio, "audio/ogg")},
            data={"model": "whisper-1", "language": "es"}, timeout=60)
        return r.json().get("text", "") if r.status_code == 200 else None
    except: return None

# ═════════════════════════════════════════════════════
#  TELEGRAM
# ═════════════════════════════════════════════════════
def send(chat_id, text):
    try:
        for chunk in [text[i:i+3900] for i in range(0, len(text), 3900)]:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          json={"chat_id": chat_id, "text": chunk}, timeout=10)
    except Exception as e: logging.error(f"send: {e}")

def send_audio(chat_id, audio):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice",
                      files={"voice": ("j.mp3", audio, "audio/mpeg")},
                      data={"chat_id": chat_id}, timeout=30)
    except: pass

def typing(chat_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except: pass

# ═════════════════════════════════════════════════════
#  GMAIL — MyInvestor + Trade Republic + ING
# ═════════════════════════════════════════════════════
BROKER_SENDERS = {
    "myinvestor": ["myinvestor.es", "no-reply@myinvestor.es", "info@myinvestor.es",
                   "notificaciones@myinvestor.es"],
    "trade_republic": ["traderepublic.com", "no-reply@traderepublic.com",
                       "noreply@traderepublic.com", "support@traderepublic.com"],
    "ing": ["ing.es", "ingdirect.es", "info@ing.es", "info@ingdirect.es",
            "comunicaciones@ing.es", "noreply@ing.es", "no-reply@ing.es",
            "alertas@ing.es", "alerta@ing.es", "broker@ing.es",
            "notificaciones@ing.es", "valores@ing.es"],
}
ACTION_KEYWORDS = {
    "VENTA": ["venta ejecutada", "vendido", "sell executed", "sold",
              "orden de venta", "venta de valores"],
    "COMPRA": ["compra ejecutada", "comprado", "buy executed", "bought",
               "orden de compra", "compra de valores", "purchase"],
    "DIVIDENDO": ["dividendo", "dividend", "abono de dividendo", "pago de dividendo"],
    "INGRESO": ["ingreso recibido", "deposit received", "transferencia recibida"],
    "RETIRADA": ["retirada", "withdrawal", "transferencia enviada"],
}

def _gmail_decode(s):
    if s is None: return ""
    out = ""
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            try: out += part.decode(enc or "utf-8", errors="ignore")
            except: out += part.decode("utf-8", errors="ignore")
        else: out += part
    return out

def _gmail_body(msg):
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition") or ""): continue
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    raw = part.get_payload(decode=True)
                    if raw: body += raw.decode(errors="ignore")
                except: pass
    else:
        try:
            raw = msg.get_payload(decode=True)
            if raw: body = raw.decode(errors="ignore")
        except: pass
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body)

def _classify(text):
    t = text.lower()
    for action, kws in ACTION_KEYWORDS.items():
        if any(k in t for k in kws): return action
    return None

def _extract_ticker_email(text):
    m = re.search(r"\(([A-Z]{1,5})\)", text)
    if m: return m.group(1)
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b", text)
    if m: return m.group(1)
    return None

def _extract_amount(text):
    patterns = [r"([\d]{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*€",
                r"€\s*([\d]{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?)",
                r"([\d]+(?:[.,]\d{1,2})?)\s*EUR"]
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(1).replace(" ","").replace(".","").replace(",",".")
            try:
                v = float(raw)
                if 0.01 <= v <= 10_000_000: return v
            except: pass
    return None

def fetch_broker_movements(days=7):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD):
        return [{"error": "GMAIL_USER o GMAIL_APP_PASSWORD no configurados"}]
    movs = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")
        date_since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        for broker, senders in BROKER_SENDERS.items():
            for sender in senders:
                status, data = mail.search(None, f'(FROM "{sender}" SINCE {date_since})')
                if status != "OK" or not data or not data[0]: continue
                for eid in data[0].split()[-25:]:
                    s2, msg_data = mail.fetch(eid, "(RFC822)")
                    if s2 != "OK" or not msg_data or not msg_data[0]: continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    subject = _gmail_decode(msg.get("Subject"))
                    body = _gmail_body(msg)
                    full = f"{subject}\n{body}"
                    action = _classify(full)
                    if not action: continue
                    movs.append({
                        "broker": broker, "fecha": msg.get("Date", ""),
                        "asunto": subject[:120], "accion": action,
                        "ticker": _extract_ticker_email(full),
                        "importe_eur": _extract_amount(full),
                    })
        mail.close(); mail.logout()
    except Exception as e:
        return [{"error": f"Gmail: {e}"}]
    return movs

def format_movements(movs):
    if not movs: return "No he visto movimientos en tu Gmail los últimos 7 días."
    if movs and "error" in movs[0]: return f"Problema con Gmail: {movs[0]['error']}"
    nombres = {"myinvestor": "MyInvestor", "trade_republic": "Trade Republic", "ing": "ING"}
    lines = [f"He detectado {len(movs)} movimientos en tu Gmail:"]
    for m in movs[:15]:
        ticker = m.get("ticker") or "?"
        imp = m.get("importe_eur")
        imp_s = f" por {imp:.0f}€" if imp else ""
        b = nombres.get(m["broker"], m["broker"])
        lines.append(f"• {b}: {m['accion'].lower()} de {ticker}{imp_s}")
    return "\n".join(lines)

def gmail_monitor_loop():
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and MIKI_CHAT_ID):
        logging.info("Gmail monitor desactivado (faltan vars)")
        return
    logging.info("Gmail monitor activo - cada 30 min (MyInvestor + Trade Republic + ING)")
    time.sleep(60)
    while True:
        try:
            movs = fetch_broker_movements(days=2)
            if movs and "error" not in movs[0]:
                nuevos = persist_movements(movs)
                if nuevos:
                    msg = "Oye Miki, mira lo que ha llegado a tu Gmail:\n\n"
                    msg += format_movements(nuevos)
                    msg += "\n\n¿Quieres que actualice tu cartera con esto?"
                    send(MIKI_CHAT_ID, msg)
        except Exception as e:
            logging.error(f"Gmail loop: {e}")
        time.sleep(1800)

# ═════════════════════════════════════════════════════
#  BRIEFING AUTÓNOMO
# ═════════════════════════════════════════════════════
def autonomous_briefing_loop():
    """Briefing autónomo: NO texto libre, sino TARJETAS estilo Miki por cada posición clave."""
    if not (AUTONOMY_ENABLED and MIKI_CHAT_ID): return
    time.sleep(120)
    while True:
        try:
            send(MIKI_CHAT_ID, f"🤖 Briefing autónomo · {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            # 1 tarjeta visual por cada posición principal (estilo del documento de Miki)
            posiciones_clave = ["GOOGL", "MSFT", "VISA", "AAPL", "JNJ"]
            for ticker in posiciones_clave:
                datos = format_data_for_claude(get_real_data(ticker))
                if "DATOS NO DISPONIBLES" in datos:
                    continue
                prompt = (f"Tarjeta visual EXACTA de {ticker} para briefing diario.\n"
                          f"UNA sola idea principal. Bullets con datos reales del día.\n"
                          f"Lectura corta. Impacto. Señal final.\n"
                          f"Si está en máximos, alerta. Si cae fuerte, alerta. Si está estable, mantener.")
                reply = ask_claude(MIKI_CHAT_ID, prompt, get_system_card(),
                                   web_data=datos, max_tokens=450)
                send(MIKI_CHAT_ID, reply)
                time.sleep(2)  # respiro entre tarjetas
            # Resumen final estilo colega corto (NO desplaza la plantilla)
            send(MIKI_CHAT_ID, "👆 Tarjetas de tus posiciones clave de hoy.\n"
                              "Si quieres valoración profunda con plantilla → \"valórame [TICKER]\"")
        except Exception as e:
            logging.error(f"Autonomy: {e}")
        time.sleep(max(30, AUTONOMY_INTERVAL_MIN) * 60)

# ═════════════════════════════════════════════════════
#  HANDLER PRINCIPAL
# ═════════════════════════════════════════════════════
def handle(chat_id, text):
    txt = text.strip()
    txt_low = txt.lower()
    hoy = datetime.now().strftime("%d/%m/%Y")

    # Comando técnico mínimo
    if txt_low == "/miid":
        send(chat_id, f"Tu chat ID es: {chat_id}")
        return

    # Memoria permanente
    if txt_low.startswith("recuerda que "):
        fact = txt[12:].strip()
        if fact:
            upsert_knowledge(chat_id, f"fact_{int(time.time())}", fact)
            send(chat_id, "Anotado. Lo tendré en cuenta siempre.")
        return

    # Gmail (MyInvestor + Trade Republic + ING)
    gmail_triggers = ["mira mi gmail", "mira gmail", "revisa mi gmail", "revisa gmail",
                      "ve a gmail", "movimientos", "mi cartera ha cambiado",
                      "actualiza mi cartera", "cartera ha cambiado",
                      "mira los correos", "revisa los correos", "qué movimientos"]
    if any(t in txt_low for t in gmail_triggers):
        typing(chat_id)
        send(chat_id, "Voy a echar un ojo a tu Gmail (MyInvestor + Trade Republic + ING)...")
        movs = fetch_broker_movements(days=15)
        persist_movements(movs)
        send(chat_id, format_movements(movs))
        return

    # Cartera completa
    cartera_triggers = ["mi cartera", "toda la cartera", "todas las posiciones",
                        "cómo está mi cartera", "como está mi cartera", "mis posiciones"]
    if any(t in txt_low for t in cartera_triggers):
        typing(chat_id)
        send(chat_id, "Voy a sacar precios reales de toda la cartera...")
        datos = get_real_data_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "SSNC", "TXRH", "CELH"])
        prompt = (f"Hoy {hoy}. Cuéntame cómo está mi cartera con esos datos reales. "
                  f"Tono colega natural, 6-8 frases. Mira si MSFT (-12.5%) se ha movido.")
        reply = ask_claude(chat_id, prompt, get_system_chat(), web_data=datos, max_tokens=600)
        send(chat_id, reply)
        return

    # Macro (sin ticker concreto) - AHORA con FRED + ECB en directo
    macro_triggers = ["macro", "fed ", "inflacion", "inflación", "vix", "dolar", "dólar",
                      "tipos de interés", "tipos de interes", "bce", "ecb"]
    if any(t in txt_low for t in macro_triggers) and not detect_ticker(txt):
        typing(chat_id)
        send(chat_id, "Sacando datos macro oficiales (FED + BCE)...")
        fred_data = fred_macro_snapshot()
        ecb_data = ecb_macro_snapshot()
        news = search_news("FED tipos inflacion VIX dolar mercados hoy", n=2)
        macro_full = f"{fred_data}\n\n{ecb_data}\n\nNoticias:\n{news}"
        prompt = f"Cuéntame cómo está la macro hoy {hoy} en lenguaje colega. Usa los datos oficiales."
        reply = ask_claude(chat_id, prompt, get_system_chat(), web_data=macro_full, max_tokens=500)
        send(chat_id, reply)
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)
        return

    # Insiders (con o sin ticker)
    insider_triggers = ["insider", "insiders", "directivos", "compras de directivos",
                        "ventas de directivos", "compra interna", "venta interna"]
    if any(t in txt_low for t in insider_triggers):
        ticker_ins = detect_ticker(txt)
        if ticker_ins:
            typing(chat_id)
            send(chat_id, f"Mirando insiders de {ticker_ins} en OpenInsider...")
            ins_data = openinsider_get(ticker_ins, n=10)
            if not ins_data:
                send(chat_id, f"No he encontrado datos de insiders recientes para {ticker_ins}.")
                return
            prompt = (f"Resume estos movimientos de insiders de {ticker_ins} para Miki. "
                      f"Tono colega. Si hay compras del CEO/CFO/Insider Chairman, marca eso. "
                      f"Si solo hay ventas planeadas (10b5-1) avísalo.")
            reply = ask_claude(chat_id, prompt, get_system_chat(), web_data=ins_data, max_tokens=500)
            send(chat_id, reply)
            return
        else:
            send(chat_id, "Dime de qué empresa quieres ver insiders, ej: \"insiders MSFT\"")
            return

    # Holdings ETF
    holdings_triggers = ["holdings", "qué hay en", "que hay en", "componentes de",
                         "top del", "principales del"]
    etf_keywords = {"sp500": "IVV", "ivv": "IVV", "india": "INDA", "inda": "INDA"}
    if any(t in txt_low for t in holdings_triggers):
        for kw, etf in etf_keywords.items():
            if kw in txt_low:
                typing(chat_id)
                send(chat_id, f"Pidiendo holdings oficiales de {etf} a iShares...")
                h = ishares_top_holdings(etf, n=10)
                if h:
                    send(chat_id, h)
                else:
                    send(chat_id, f"No he podido sacar los holdings de {etf} ahora mismo.")
                return

    # ─── EMPRESA DETECTADA ───
    ticker = detect_ticker(txt)

    if ticker:
        # Conversacional explícito → responde como colega
        if is_conversational(txt):
            typing(chat_id)
            datos = format_data_for_claude(get_real_data(ticker))
            reply = ask_claude(chat_id, txt, get_system_chat(), web_data=datos, max_tokens=400)
            send(chat_id, reply)
            audio = tts(reply[:500])
            if audio: send_audio(chat_id, audio)
            return

        # ─── EQUIPO JARVIS (subagentes TradingAgents-style) ───
        # Modo MÁS profundo aún que Dexter: 4 analistas + Bull/Bear + Riesgo + Plantilla
        EQUIPO_TRIGGERS = [
            "equipo", "subagentes", "council", "consejo de inversión",
            "consejo de inversion", "mesa de análisis", "mesa de analisis",
            "buffett", "lynch", "klarman", "munger",
            "bull bear", "bull vs bear", "alcista bajista", "debate",
            "institucional", "buy-side", "buy side",
            "análisis máximo", "analisis maximo", "análisis total", "analisis total",
            "research completo", "research total",
        ]
        if any(p in txt_low for p in EQUIPO_TRIGGERS):
            typing(chat_id)
            send(chat_id, f"🏢 Activando EQUIPO JARVIS COMPLETO para {ticker}...\n"
                          f"4 analistas + Debate Bull/Bear + Gestores riesgo + Fund Manager.\n"
                          f"60-90 segundos. Salida: tu PLANTILLA EXACTA + decisión del equipo.")
            reply = jarvis_team_research(chat_id, ticker, txt)
            send(chat_id, reply)
            return

        # ─── DCF CALCULATOR explícito ───
        DCF_TRIGGERS = ["dcf", "discounted cash flow", "flujo de caja descontado",
                        "valoración por flujos", "valoracion por flujos"]
        if any(p in txt_low for p in DCF_TRIGGERS):
            typing(chat_id)
            send(chat_id, f"💰 Calculando DCF de {ticker} con 3 escenarios...")
            dcf_text = dcf_full_analysis(ticker)
            datos = format_data_for_claude(get_real_data(ticker))
            prompt = (f"Aquí tienes el DCF calculado de {ticker}:\n\n{dcf_text}\n\n"
                      f"Datos contexto:\n{datos}\n\n"
                      f"Comenta el resultado en tono colega: ¿está cara o barata? "
                      f"¿qué escenario es realista? Termina con DECISIÓN. 5-7 líneas.")
            reply = ask_claude(chat_id, prompt, get_system_chat(), max_tokens=600)
            send(chat_id, f"{dcf_text}\n\n{reply}")
            return

        # ─── DEXTER RESEARCH (super cerebro de Jarvis) ───
        # Se activa con CUALQUIER intención de análisis profundo o valoración
        DEXTER_TRIGGERS = [
            # Valoración explícita
            "valora", "valoración", "valoracion", "valórame", "valorame",
            "valuar", "evaluar", "evalúa", "evalua",
            # Plantilla
            "plantilla", "invertir desde 0", "invertir desde cero",
            # Precio justo / valor intrínseco
            "precio justo", "valor intrínseco", "valor intrinseco",
            "precio objetivo", "precio target",
            # Análisis profundo
            "análisis profundo", "analisis profundo", "análisis completo",
            "analisis completo", "research", "investiga", "estudia",
            "tesis", "tesis de inversión", "deep dive",
            # Decisión
            "compro o no", "vendo o no", "qué hago con", "que hago con",
            "merece la pena", "vale la pena",
        ]
        if any(p in txt_low for p in DEXTER_TRIGGERS):
            typing(chat_id)
            send(chat_id, f"🧠 Activando DEXTER (super cerebro) para {ticker}...\n"
                          f"Plan → Datos (FMP+SEC+Insiders+News+Macro+Wiki) → Reflexión → Plantilla EXACTA.\n"
                          f"30-45 segundos.")
            reply = dexter_research(chat_id, ticker, txt)
            send(chat_id, reply)
            return

        # ─── EARNINGS / RESULTADOS → TARJETA VISUAL con beat/miss/guidance ───
        EARNINGS_TRIGGERS = [
            "earnings", "resultados", "han presentado", "ha presentado",
            "presenta resultados", "presentó resultados", "presento resultados",
            "reportado", "reporta", "reportó", "reporto",
            "beat", "miss", "guidance", "guía", "guia",
            "ventas trimestre", "trimestre", "q1", "q2", "q3", "q4",
        ]
        if any(p in txt_low for p in EARNINGS_TRIGGERS):
            typing(chat_id)
            datos = format_data_for_claude(get_real_data(ticker))
            news = search_news(f"{ticker} earnings revenue EPS guidance Q latest", n=4)
            sec_data = sec_get_filings(ticker, n=3)
            full = f"{datos}\n\n=== NOTICIAS RESULTADOS ===\n{news}\n\n{sec_data}"
            prompt = (f"El usuario pregunta por RESULTADOS / EARNINGS de {ticker}. Hoy {hoy}.\n"
                      f"Pregunta literal: \"{txt}\"\n\n"
                      f"Responde con la TARJETA VISUAL EXACTA centrándote en:\n"
                      f"- Título: RESULTADOS o segmento clave (CLOUD/AZURE/AWS/SEARCH/etc)\n"
                      f"- Bullets: Ventas (Beat/Miss), EBIT, EPS, Guidance, segmento clave\n"
                      f"- Lectura: si cambia tesis, si mercado exagera, si problema es negocio o "
                      f"valoración o timing\n"
                      f"- Señal final ALINEADA con la cartera de Miki\n\n"
                      f"Si no hay datos confirmados de earnings recientes, di ⚪ NO CONCLUYENTE.")
            reply = ask_claude(chat_id, prompt, get_system_card(), web_data=full, max_tokens=700)
            send(chat_id, reply)
            return

        # POR DEFECTO con ticker → TARJETA VISUAL
        typing(chat_id)
        datos = format_data_for_claude(get_real_data(ticker))
        prompt = (f"Datos reales de {ticker} hoy {hoy}.\n"
                  f"Pregunta del usuario: \"{txt}\"\n"
                  f"Responde con la tarjeta visual EXACTA según las reglas del sistema.")
        reply = ask_claude(chat_id, prompt, get_system_card(), web_data=datos, max_tokens=600)
        send(chat_id, reply)
        return

    # ─── CONVERSACIÓN GENERAL ───
    typing(chat_id)
    reply = ask_claude(chat_id, txt, get_system_chat(), max_tokens=500)
    send(chat_id, reply)
    if len(reply) > 80:
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)

def handle_voice(chat_id, file_id):
    typing(chat_id)
    if not OPENAI_KEY:
        send(chat_id, "Necesito OPENAI_API_KEY en Render para audios.")
        return
    text = transcribe_voice(file_id)
    if not text:
        send(chat_id, "No te he pillado bien. Repítela.")
        return
    send(chat_id, f"🎙️ Te he entendido: \"{text}\"")
    handle(chat_id, text)

# ═════════════════════════════════════════════════════
#  IMÁGENES — Claude Vision (híbrido: con o sin caption)
# ═════════════════════════════════════════════════════
import base64

def download_telegram_file(file_id):
    """Descarga un archivo de Telegram y devuelve los bytes."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
                         params={"file_id": file_id}, timeout=10)
        if r.status_code != 200: return None, None
        file_path = r.json()["result"]["file_path"]
        ext = file_path.split(".")[-1].lower()
        media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                      "png": "image/png", "webp": "image/webp",
                      "gif": "image/gif"}.get(ext, "image/jpeg")
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        img = requests.get(url, timeout=30).content
        return img, media_type
    except Exception as e:
        logging.error(f"Telegram getFile: {e}")
        return None, None

def ask_claude_vision(chat_id, image_bytes, media_type, user_text, system_prompt, max_tokens=900):
    """Llama a Claude con imagen + texto."""
    if not ANTHROPIC_KEY:
        return "Sin ANTHROPIC_API_KEY no puedo analizar imágenes."
    try:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        msgs = [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                              "media_type": media_type, "data": b64}},
                {"type": "text", "text": user_text}
            ]
        }]
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                  "system": system_prompt, "messages": msgs}, timeout=60)
        data = r.json()
        if "error" in data:
            return f"Error Claude Vision: {data['error'].get('message','')[:120]}"
        reply = data["content"][0]["text"]
        save_memory(chat_id, "user", f"[IMAGEN] {user_text[:300]}")
        save_memory(chat_id, "assistant", reply[:600])
        return reply
    except Exception as e:
        logging.error(f"Vision: {e}")
        return "No he podido procesar la imagen ahora mismo."

def handle_image(chat_id, file_id, caption=""):
    """Procesa imagen con o sin caption (híbrido A+B+C)."""
    typing(chat_id)
    img, media_type = download_telegram_file(file_id)
    if not img:
        send(chat_id, "No he podido descargar la imagen, prueba de nuevo.")
        return

    caption_low = caption.lower().strip() if caption else ""
    hoy = datetime.now().strftime("%d/%m/%Y")
    ticker_in_caption = detect_ticker(caption) if caption else None

    # Detectar tickers también en la imagen vía contexto del caption
    ticker_for_data = ticker_in_caption

    # Caso 1: caption pide VALORACIÓN explícita
    if caption_low and any(p in caption_low for p in ["valora", "valoración", "valoracion",
                                                       "valórame", "valorame", "precio justo",
                                                       "valor intrínseco", "valor intrinseco",
                                                       "plantilla"]):
        send(chat_id, "Mirando la imagen y cruzando con datos reales...")
        datos_extra = ""
        if ticker_for_data:
            fmp_data = format_data_for_claude(get_real_data(ticker_for_data))
            sec_data = sec_get_filings(ticker_for_data, n=3)
            ins_data = openinsider_get(ticker_for_data, n=5)
            datos_extra = f"\n\nDATOS REALES VERIFICADOS:\n{fmp_data}\n\n{sec_data}\n\n{ins_data}"
        template = load_template()
        prompt = (f"El usuario te manda una imagen y pide valoración. Caption: \"{caption}\". "
                  f"Hoy {hoy}. Lee la imagen, identifica la empresa/datos visibles. "
                  f"Si reconoces la empresa, valórala usando EXACTAMENTE esta plantilla:\n\n"
                  f"{template}\n\n"
                  f"REGLAS: No inventes. Si falta dato dilo. Cierra con decisión clara."
                  f"{datos_extra}")
        reply = ask_claude_vision(chat_id, img, media_type, prompt, get_system_chat(), max_tokens=1100)
        send(chat_id, reply)
        return

    # Caso 2: caption pide ANÁLISIS DE EMPRESA (tarjeta visual)
    if caption_low and (ticker_for_data or any(p in caption_low for p in
                       ["analiza", "qué ves", "que ves", "qué dice", "que dice",
                        "mira esta", "mira este", "tarjeta", "señal"])):
        send(chat_id, "Analizando imagen como tarjeta visual...")
        datos_extra = ""
        if ticker_for_data:
            datos_extra = f"\n\nDATOS REALES:\n{format_data_for_claude(get_real_data(ticker_for_data))}"
        prompt = (f"El usuario te manda una imagen con caption: \"{caption}\". Hoy {hoy}. "
                  f"Lee la imagen, identifica empresa/gráfico/datos. "
                  f"Responde con la TARJETA VISUAL EXACTA según las reglas del sistema.{datos_extra}")
        reply = ask_claude_vision(chat_id, img, media_type, prompt, get_system_card(), max_tokens=700)
        send(chat_id, reply)
        return

    # Caso 3: caption con instrucción específica
    if caption_low:
        send(chat_id, "Mirando la imagen...")
        prompt = (f"Imagen del usuario con caption: \"{caption}\". Hoy {hoy}. "
                  f"Responde a lo que te pide en tono colega natural español. "
                  f"Si la imagen muestra una empresa de su cartera (GOOGL, MSFT, AAPL, JNJ, "
                  f"VISA, MONC, ZEG, JNJ, SSNC, TXRH, CELH), tenlo en cuenta.")
        reply = ask_claude_vision(chat_id, img, media_type, prompt, get_system_chat(), max_tokens=600)
        send(chat_id, reply)
        return

    # Caso 4: SIN caption — Jarvis decide solo (modo automático)
    send(chat_id, "Mirando la imagen y decidiendo qué hacer...")
    prompt = (f"El usuario te manda una imagen sin texto. Hoy {hoy}.\n"
              f"Identifica qué hay en ella:\n"
              f"- Si es gráfico/cotización de una empresa → describe lo que ves "
              f"(empresa, periodo, tendencia, niveles clave) y al final pregunta "
              f"\"¿quieres tarjeta visual o valoración con plantilla?\"\n"
              f"- Si es captura de noticias/earnings → resume las claves en 4-5 líneas "
              f"con tono colega.\n"
              f"- Si es captura de extracto/cartera → identifica posiciones y movimientos.\n"
              f"- Si es foto del Excel \"Invertir Desde 0\" → reconoce la plantilla y "
              f"pregunta qué empresa quieres valorar.\n"
              f"- Si no es nada de inversión → dilo natural y pregunta qué quería el usuario.\n"
              f"Tono: colega de bar, español de España, frases cortas.")
    reply = ask_claude_vision(chat_id, img, media_type, prompt, get_system_chat(), max_tokens=700)
    send(chat_id, reply)

# ═════════════════════════════════════════════════════
#  POLLING
# ═════════════════════════════════════════════════════
def poll():
    offset = 0
    logging.info(f"JARVIS v15 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logging.info(f"FMP:{'OK' if FMP_KEY else 'NO'} | "
                 f"Anthropic:{'OK' if ANTHROPIC_KEY else 'NO'} | "
                 f"Whisper:{'OK' if OPENAI_KEY else 'NO'} | "
                 f"ElevenLabs:{'OK' if ELEVENLABS_KEY else 'NO'} | "
                 f"Gmail:{'OK' if (GMAIL_USER and GMAIL_APP_PASSWORD) else 'NO'} | "
                 f"Supabase:{'OK' if (SUPABASE_URL and SUPABASE_KEY) else 'NO'}")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                             params={"offset": offset, "timeout": 30}, timeout=35)
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                cid = msg.get("chat", {}).get("id")
                if not cid: continue

                # Foto (imagen normal)
                photo = msg.get("photo")
                if photo and isinstance(photo, list) and photo:
                    # Telegram manda varias resoluciones, cogemos la mayor (última)
                    file_id = photo[-1].get("file_id")
                    caption = msg.get("caption", "")
                    if file_id:
                        threading.Thread(target=handle_image,
                                         args=(cid, file_id, caption), daemon=True).start()
                    continue

                # Documento que sea imagen
                doc = msg.get("document")
                if doc:
                    mime = doc.get("mime_type", "")
                    if mime.startswith("image/"):
                        file_id = doc.get("file_id")
                        caption = msg.get("caption", "")
                        if file_id:
                            threading.Thread(target=handle_image,
                                             args=(cid, file_id, caption), daemon=True).start()
                        continue

                # Texto
                txt = msg.get("text", "")
                if txt:
                    threading.Thread(target=handle, args=(cid, txt), daemon=True).start()
                    continue

                # Voz
                voice = msg.get("voice")
                if voice and voice.get("file_id"):
                    threading.Thread(target=handle_voice, args=(cid, voice["file_id"]), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")

# ═════════════════════════════════════════════════════
#  HTTP SERVER PRO — Web App + API endurecida
#  /app  → panel HTML para hablar con Jarvis desde navegador
#  /chat → chat (igual que Telegram)
#  /quote → datos reales empresa
#  /portfolio → cartera Miki
#  /health → ping
# ═════════════════════════════════════════════════════
import hmac, urllib.parse
from collections import deque

APP_API_KEY     = os.environ.get("APP_API_KEY", "").strip()
AUTH_REQUIRED   = bool(APP_API_KEY)
RATE_WIN_SEC    = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_MAX_REQ    = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "120"))
MAX_BODY_BYTES  = 50_000
MAX_MSG_CHARS   = 8_000

_rate_lock = threading.Lock()
_rate_bucket = {}

def _is_rate_limited(ip):
    now = time.time()
    with _rate_lock:
        bucket = _rate_bucket.setdefault(ip, [])
        bucket[:] = [t for t in bucket if now - t <= RATE_WIN_SEC]
        if len(bucket) >= RATE_MAX_REQ: return True
        bucket.append(now)
    return False

JARVIS_APP_HTML = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS WebApp</title>
<style>
:root{--bg:#0b1020;--panel:#121a33;--panel2:#17213f;--text:#eef3ff;--muted:#9fb0d0;
--border:#273452;--accent:#4da3ff;--danger:#ff5c7a;--ok:#43d18b}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(circle at top,#18264b 0,var(--bg) 45%);
color:var(--text);font-family:Arial,system-ui,sans-serif}
.wrap{width:min(1100px,calc(100% - 32px));margin:0 auto;padding:32px 0}
header{margin-bottom:22px}
h1{margin:0 0 8px;font-size:28px}
.sub{color:var(--muted);margin:0;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
section{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--border);
border-radius:18px;padding:18px;box-shadow:0 16px 40px rgba(0,0,0,.25)}
h2{margin:0 0 12px;font-size:18px}
label{display:block;font-size:13px;color:var(--muted);margin-bottom:6px}
input,textarea{width:100%;border:1px solid var(--border);border-radius:12px;padding:12px;
background:#0d1428;color:var(--text);outline:none;font-size:15px}
textarea{min-height:130px;resize:vertical}
input:focus,textarea:focus{border-color:var(--accent)}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
button{border:0;border-radius:12px;padding:11px 14px;background:var(--accent);
color:white;cursor:pointer;font-weight:700}
button.secondary{background:#2d3b5f}
button.danger{background:var(--danger)}
pre{margin-top:16px;min-height:260px;max-height:520px;overflow:auto;background:#070b16;
border:1px solid var(--border);color:#dbe7ff;padding:16px;border-radius:18px;
white-space:pre-wrap;word-break:break-word}
.status{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);margin-top:8px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--ok)}
@media(max-width:820px){.grid{grid-template-columns:1fr}}
</style></head><body>
<div class="wrap">
<header><h1>🤖 JARVIS WebApp</h1>
<p class="sub">Versión: __APP_VERSION__</p>
<div class="status"><span class="dot"></span><span id="statusText">Listo.</span></div></header>
<div class="grid">
<section><h2>🔐 Seguridad</h2>
<label for="apiKey">API Key (opcional)</label>
<input id="apiKey" type="password" autocomplete="off" placeholder="Pega tu APP_API_KEY">
<div class="row">
<button class="secondary" onclick="saveKey()">Guardar</button>
<button class="danger" onclick="clearKey()">Borrar</button>
<button onclick="health()">Health</button></div></section>
<section><h2>📊 Precio</h2>
<label for="ticker">Ticker</label>
<input id="ticker" value="MSFT" autocomplete="off">
<div class="row"><button onclick="quote()">Buscar precio</button></div></section>
<section><h2>💬 Chat con Jarvis</h2>
<label for="msg">Mensaje (igual que Telegram)</label>
<textarea id="msg" placeholder="valórame Google, insiders MSFT, mira mi gmail..."></textarea>
<div class="row">
<button onclick="chat()">Enviar</button>
<button class="secondary" onclick="portfolio()">Cartera</button></div></section>
<section><h2>📤 Salida</h2><pre id="out">Listo.</pre></section>
</div></div>
<script>
const out=document.getElementById('out'),statusText=document.getElementById('statusText'),
apiKeyInput=document.getElementById('apiKey'),tickerInput=document.getElementById('ticker'),
msgInput=document.getElementById('msg');
apiKeyInput.value=localStorage.getItem('JARVIS_API_KEY')||'';
function setStatus(t){statusText.textContent=t}
function show(x){out.textContent=typeof x==='string'?x:JSON.stringify(x,null,2)}
function saveKey(){localStorage.setItem('JARVIS_API_KEY',apiKeyInput.value.trim());show('API Key guardada.')}
function clearKey(){localStorage.removeItem('JARVIS_API_KEY');apiKeyInput.value='';show('API Key borrada.')}
function headers(json=false){const h={};const k=apiKeyInput.value.trim();
if(json)h['Content-Type']='application/json';if(k)h['X-API-Key']=k;return h}
async function request(path,opts={}){setStatus('Trabajando...');
try{const r=await fetch(path,opts);const ct=r.headers.get('content-type')||'';
const data=ct.includes('application/json')?await r.json():await r.text();
if(!r.ok){show(data);setStatus('Error.');return data}
show(data);setStatus('Listo.');return data}
catch(e){show({error:String(e)});setStatus('Error de conexión.');return{error:String(e)}}}
async function health(){return request('/health',{method:'GET'})}
async function quote(){const t=tickerInput.value.trim();if(!t){show({error:'Falta ticker'});return}
return request('/quote?ticker='+encodeURIComponent(t),{method:'GET',headers:headers(false)})}
async function portfolio(){return request('/portfolio',{method:'GET',headers:headers(false)})}
async function chat(){const m=msgInput.value.trim();if(!m){show({error:'Falta mensaje'});return}
return request('/chat',{method:'POST',headers:headers(true),body:JSON.stringify({message:m,chat_id:'webapp'})})}
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    server_version = "JARVIS-API-PRO"

    def _client_ip(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        if fwd: return fwd.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def _common_headers(self, content_type):
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send(self, code, content_type, payload):
        self.send_response(code)
        self._common_headers(content_type)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _text(self, txt, code=200):
        self._send(code, "text/plain; charset=utf-8", txt.encode("utf-8"))

    def _html(self, html, code=200):
        self._send(code, "text/html; charset=utf-8", html.encode("utf-8"))

    def _json(self, obj, code=200):
        payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self._send(code, "application/json; charset=utf-8", payload)

    def _err(self, msg, code):
        self._json({"ok": False, "error": msg}, code)

    def _authorized(self):
        if not AUTH_REQUIRED: return True
        auth = self.headers.get("Authorization", "")
        api_key = self.headers.get("X-API-Key", "")
        return (hmac.compare_digest(auth, f"Bearer {APP_API_KEY}") or
                hmac.compare_digest(api_key, APP_API_KEY))

    def _guard(self, path, protected=False):
        if _is_rate_limited(self._client_ip()):
            self._err("rate limit exceeded", 429); return False
        if protected and not self._authorized():
            self._err("unauthorized", 401); return False
        return True

    def _read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except: length = 0
        if length < 0 or length > MAX_BODY_BYTES:
            self._err("invalid body", 413); return None
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict):
                self._err("body must be object", 400); return None
            return body
        except:
            self._err("invalid json", 400); return None

    def do_HEAD(self):
        self._text("", 200)

    def do_OPTIONS(self):
        self.send_response(204)
        self._common_headers("text/plain; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

            if not self._guard(path, protected=False): return

            if path in ("/", "/health"):
                self._text(f"JARVIS v15 - {datetime.now().strftime('%d/%m/%Y %H:%M')} - Online", 200)
                return

            if path == "/app":
                html = JARVIS_APP_HTML.replace("__APP_VERSION__", "JARVIS v15")
                self._html(html, 200); return

            if path == "/favicon.ico":
                self._text("", 204); return

            # Endpoints protegidos
            if path == "/quote":
                if not self._guard(path, protected=True): return
                ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].upper().strip()
                if not ticker:
                    self._err("missing ticker", 400); return
                data = get_real_data(ticker)
                self._json(data, 200); return

            if path == "/portfolio":
                if not self._guard(path, protected=True): return
                tickers = ["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "SSNC", "TXRH", "CELH"]
                portfolio = {t: get_real_data(t) for t in tickers}
                self._json(portfolio, 200); return

            self._err("not found", 404)
        except Exception as e:
            logging.error(f"GET {self.path}: {e}")
            self._err("internal error", 500)

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if not self._guard(path, protected=True): return
            body = self._read_json_body()
            if body is None: return

            if path == "/chat":
                msg = str(body.get("message") or body.get("msg") or "").strip()
                chat_id = str(body.get("chat_id") or "webapp").strip()[:80]
                if not msg:
                    self._err("missing message", 400); return
                if len(msg) > MAX_MSG_CHARS:
                    self._err("message too long", 413); return

                # Router IDÉNTICO a Telegram → equipo / dexter / earnings / dcf / tarjeta / chat
                ticker = detect_ticker(msg)
                msg_low = msg.lower()
                if ticker and any(p in msg_low for p in EQUIPO_TRIGGERS_GLOBAL):
                    reply = jarvis_team_research(chat_id, ticker, msg)
                elif ticker and any(p in msg_low for p in DCF_TRIGGERS_GLOBAL):
                    dcf_text = dcf_full_analysis(ticker)
                    reply = dcf_text
                elif ticker and any(p in msg_low for p in DEXTER_TRIGGERS_GLOBAL):
                    reply = dexter_research(chat_id, ticker, msg)
                elif ticker and is_conversational(msg):
                    datos = format_data_for_claude(get_real_data(ticker))
                    reply = ask_claude(chat_id, msg, get_system_chat(), web_data=datos, max_tokens=400)
                elif ticker:
                    datos = format_data_for_claude(get_real_data(ticker))
                    prompt = f"Pregunta: \"{msg}\". Responde con tarjeta visual EXACTA."
                    reply = ask_claude(chat_id, prompt, get_system_card(), web_data=datos, max_tokens=600)
                else:
                    reply = ask_claude(chat_id, msg, get_system_chat(), max_tokens=500)
                self._json({"ok": True, "reply": reply}, 200); return

            if path == "/quote":
                ticker = str(body.get("ticker") or body.get("symbol") or "").upper().strip()
                if not ticker:
                    self._err("missing ticker", 400); return
                self._json(get_real_data(ticker), 200); return

            self._err("not found", 404)
        except Exception as e:
            logging.error(f"POST {self.path}: {e}")
            self._err("internal error", 500)

    def log_message(self, *a): pass

# Triggers globales accesibles desde web (idénticos a Telegram)
DEXTER_TRIGGERS_GLOBAL = [
    "valora", "valoración", "valoracion", "valórame", "valorame",
    "valuar", "evaluar", "evalúa", "evalua",
    "plantilla", "invertir desde 0", "invertir desde cero",
    "precio justo", "valor intrínseco", "valor intrinseco",
    "precio objetivo", "precio target",
    "análisis profundo", "analisis profundo", "análisis completo",
    "analisis completo", "research", "investiga", "estudia",
    "tesis", "deep dive",
    "compro o no", "vendo o no", "qué hago con", "que hago con",
    "merece la pena", "vale la pena", "earnings", "resultados",
]
EQUIPO_TRIGGERS_GLOBAL = [
    "equipo", "subagentes", "council", "consejo de inversión",
    "consejo de inversion", "mesa de análisis", "mesa de analisis",
    "buffett", "lynch", "klarman", "munger",
    "bull bear", "bull vs bear", "alcista bajista", "debate",
    "institucional", "buy-side", "buy side",
    "análisis máximo", "analisis maximo", "análisis total", "analisis total",
    "research completo", "research total",
]
DCF_TRIGGERS_GLOBAL = ["dcf", "discounted cash flow", "flujo de caja descontado",
                       "valoración por flujos", "valoracion por flujos"]

# ═════════════════════════════════════════════════════
#  ARRANQUE
# ═════════════════════════════════════════════════════
def main():
    validate_runtime_config()
    threading.Thread(target=poll, daemon=True).start()
    threading.Thread(target=gmail_monitor_loop, daemon=True).start()
    threading.Thread(target=autonomous_briefing_loop, daemon=True).start()
    threading.Thread(target=alerts_loop, daemon=True).start()
    logging.info(f"🌐 WebApp activa en /app | API en /chat /quote /portfolio /health")
    logging.info(f"🔐 AUTH_REQUIRED={AUTH_REQUIRED} | RATE_LIMIT={RATE_MAX_REQ}/{RATE_WIN_SEC}s")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()

if __name__ == "__main__":
    main()

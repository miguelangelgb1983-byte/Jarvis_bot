"""
╔══════════════════════════════════════════════════════════════════════╗
║   JARVIS v8 — FUSIÓN DEFINITIVA · Miguel (Miki) · 26/04/2026        ║
║                                                                      ║
║   ✅ FMP para precios REALES verificados (US)                        ║
║   ✅ Tavily fallback europeos (MONC, ZEG, TRET)                      ║
║   ✅ Memoria SQLite local + Supabase persistente                     ║
║   ✅ Plantilla EXACTA de Miki (miki_valuation_template.md)           ║
║   ✅ Subagentes: VALUE / RISK / CATALYST                             ║
║   ✅ Comandos avanzados: /valora /institucional /estrategia /hyper   ║
║   ✅ Comandos clásicos: /analiza /consejo /cartera /alertas etc.     ║
║   ✅ Audios (Whisper) + Voz (ElevenLabs)                             ║
║   ✅ Gmail Skill #10 (MyInvestor + Trade Republic)                   ║
║   ✅ Briefing autónomo cada 6h                                       ║
║   ✅ Detector mercado abierto/cerrado                                ║
║   ✅ Curso "Invertir Desde Cero" en cerebro                          ║
║   ✅ "recuerda que ..." → memoria permanente                         ║
║   ✅ do_HEAD para UptimeRobot 24/7                                   ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, logging, requests, threading, json, time
import imaplib, email, re, sqlite3
from email.header import decode_header
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ═════════════════════════════════════════════════════
#  ENV VARS (todas en Render)
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
PORT               = int(os.environ.get("PORT", 8080))
MEMORY_DB_PATH     = os.environ.get("MEMORY_DB_PATH", "jarvis_memory.db")
TEMPLATE_PATH      = os.environ.get("VALUATION_TEMPLATE_PATH", "miki_valuation_template.md")
AUTONOMY_ENABLED   = os.environ.get("AUTONOMY_ENABLED", "1") == "1"
AUTONOMY_INTERVAL_MIN = int(os.environ.get("AUTONOMY_INTERVAL_MIN", "360"))
ENABLE_SUBAGENTS   = os.environ.get("ENABLE_SUBAGENTS", "1") == "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ═════════════════════════════════════════════════════
#  TICKERS
# ═════════════════════════════════════════════════════
FMP_TICKERS = {
    "GOOGL":"GOOGL","AAPL":"AAPL","MSFT":"MSFT","JNJ":"JNJ","VISA":"V","V":"V",
    "SSNC":"SSNC","TXRH":"TXRH","CELH":"CELH","NKE":"NKE","SP500":"^GSPC","INDIA":"INDA",
}
EUROPEAN_TICKERS = ["MONC", "ZEG", "TRET", "8PSG", "GOLD", "EUROPE", "SMCAP"]

TICKER_KEYWORDS = {
    "GOOGL": ["googl", "google", "alphabet"],
    "AAPL":  ["aapl", "apple"],
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
    "GOLD":  ["oro", "gold "],
    "SP500": ["sp500", "s&p", "sp 500"],
    "INDIA": ["india"],
}

def detect_ticker(text):
    txt_low = text.lower()
    for ticker, kws in TICKER_KEYWORDS.items():
        for kw in kws:
            if kw in txt_low:
                return ticker
    return None

def detect_symbol_fallback(text):
    cands = re.findall(r"\b[A-Z]{1,6}\b", text.upper())
    skip = {"USA","ETF","BPA","PER","FED","FCF","ROIC","ROE","EBIT","DCF","NYSE"}
    for c in cands:
        if c not in skip:
            return c
    return None

# ═════════════════════════════════════════════════════
#  FMP — Datos REALES verificados
# ═════════════════════════════════════════════════════
def fmp_get_quote(ticker):
    if not FMP_KEY: return None
    try:
        r = requests.get(f"https://financialmodelingprep.com/api/v3/quote/{ticker}",
                         params={"apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data: return data[0]
        return None
    except Exception as e:
        logging.error(f"FMP quote {ticker}: {e}")
        return None

def fmp_get_ratios(ticker):
    if not FMP_KEY: return None
    try:
        r = requests.get(f"https://financialmodelingprep.com/api/v3/ratios-ttm/{ticker}",
                         params={"apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data: return data[0]
        return None
    except: return None

def fmp_get_metrics(ticker):
    if not FMP_KEY: return None
    try:
        r = requests.get(f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}",
                         params={"apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data: return data[0]
        return None
    except: return None

def fmp_get_profile(ticker):
    if not FMP_KEY: return None
    try:
        r = requests.get(f"https://financialmodelingprep.com/api/v3/profile/{ticker}",
                         params={"apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data: return data[0]
        return None
    except: return None

def get_real_data(ticker_input):
    """Datos REALES verificados de un ticker."""
    ticker_up = ticker_input.upper()
    if ticker_up in EUROPEAN_TICKERS:
        return search_news(f"{ticker_input} stock price PER FCF today", n=3)
    fmp_ticker = FMP_TICKERS.get(ticker_up, ticker_up)
    quote = fmp_get_quote(fmp_ticker)
    if not quote:
        return search_news(f"{ticker_input} stock price today", n=2)
    ratios = fmp_get_ratios(fmp_ticker) or {}
    metrics = fmp_get_metrics(fmp_ticker) or {}

    lines = [f"DATOS REALES VERIFICADOS de {quote.get('name', ticker_up)} ({fmp_ticker}) — FMP {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
    if quote.get("price") is not None:
        lines.append(f"Precio: ${quote['price']:.2f}")
    if quote.get("changesPercentage") is not None:
        lines.append(f"Variación día: {quote['changesPercentage']:.2f}%")
    if quote.get("change") is not None and quote.get("previousClose") is not None:
        lines.append(f"Cambio: {quote['change']:+.2f} (cierre ant: ${quote['previousClose']:.2f})")
    if quote.get("marketCap"):
        lines.append(f"Market cap: ${quote['marketCap']/1e9:.1f}B")
    per = quote.get("pe") or ratios.get("priceEarningsRatioTTM")
    if per: lines.append(f"PER (TTM): {per:.1f}x")
    if quote.get("eps"): lines.append(f"BPA (EPS): ${quote['eps']:.2f}")
    if quote.get("yearHigh") and quote.get("yearLow"):
        lines.append(f"Rango 52s: ${quote['yearLow']:.2f} - ${quote['yearHigh']:.2f}")
    if ratios.get("returnOnEquityTTM"):
        lines.append(f"ROE: {ratios['returnOnEquityTTM']*100:.1f}%")
    roic = metrics.get("roicTTM") or ratios.get("returnOnCapitalEmployedTTM")
    if roic: lines.append(f"ROIC: {roic*100:.1f}%")
    if ratios.get("operatingProfitMarginTTM"):
        lines.append(f"Margen operativo: {ratios['operatingProfitMarginTTM']*100:.1f}%")
    deuda_eq = ratios.get("debtEquityRatioTTM") or ratios.get("debtToEquityTTM")
    if deuda_eq: lines.append(f"Deuda/Equity: {deuda_eq:.2f}")
    if metrics.get("freeCashFlowPerShareTTM"):
        lines.append(f"FCF por acción: ${metrics['freeCashFlowPerShareTTM']:.2f}")
    if metrics.get("enterpriseValueOverEBITDATTM"):
        lines.append(f"EV/EBITDA: {metrics['enterpriseValueOverEBITDATTM']:.1f}x")
    div = quote.get("dividendYield") or ratios.get("dividendYielTTM") or ratios.get("dividendYieldTTM")
    if div:
        if div < 1: lines.append(f"Dividend yield: {div*100:.2f}%")
        else: lines.append(f"Dividend yield: {div:.2f}%")
    return "\n".join(lines)

def get_real_data_multi(tickers_list):
    parts = []
    for t in tickers_list:
        d = get_real_data(t)
        if d: parts.append(f"=== {t} ===\n{d}")
    return "\n\n".join(parts)

def build_valuation_snapshot(ticker_input):
    """Snapshot estructurado para la plantilla y subagentes."""
    ticker_up = ticker_input.upper()
    if ticker_up in EUROPEAN_TICKERS:
        return {"error": f"Ticker {ticker_input} es europeo. FMP free no lo cubre. Usa /analiza para datos via Tavily."}
    fmp_ticker = FMP_TICKERS.get(ticker_up, ticker_up)
    quote = fmp_get_quote(fmp_ticker)
    if not quote:
        return {"error": f"Sin datos FMP para {ticker_input}."}
    ratios = fmp_get_ratios(fmp_ticker) or {}
    metrics = fmp_get_metrics(fmp_ticker) or {}
    profile = fmp_get_profile(fmp_ticker) or {}
    return {
        "ticker": fmp_ticker,
        "name": quote.get("name") or profile.get("companyName") or ticker_up,
        "currency": profile.get("currency", "USD"),
        "price": quote.get("price"),
        "change_pct": quote.get("changesPercentage"),
        "previous_close": quote.get("previousClose"),
        "pe_trailing": quote.get("pe") or ratios.get("priceEarningsRatioTTM"),
        "pe_forward": ratios.get("priceEarningsToGrowthRatioTTM"),
        "market_cap": quote.get("marketCap"),
        "high_52w": quote.get("yearHigh"),
        "low_52w": quote.get("yearLow"),
        "roe": ratios.get("returnOnEquityTTM"),
        "roic": metrics.get("roicTTM"),
        "op_margin": ratios.get("operatingProfitMarginTTM"),
        "fcf_per_share": metrics.get("freeCashFlowPerShareTTM"),
        "ev_ebitda": metrics.get("enterpriseValueOverEBITDATTM"),
        "debt_equity": ratios.get("debtEquityRatioTTM") or ratios.get("debtToEquityTTM"),
        "dividend_yield": quote.get("dividendYield"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "description": (profile.get("description") or "")[:500],
        "eps": quote.get("eps"),
    }

# ═════════════════════════════════════════════════════
#  TAVILY
# ═════════════════════════════════════════════════════
def search_news(query, n=2):
    if not TAVILY_KEY: return ""
    try:
        r = requests.post("https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": query,
                  "max_results": n, "search_depth": "basic"}, timeout=12)
        return "\n".join([
            f"[{x['url'].split('/')[2]}] {x['title']}: {x['content'][:200]}"
            for x in r.json().get("results", [])[:n]
        ])
    except: return ""

def get_macro_pack():
    return {
        "macro": search_news("FED tipos inflacion empleo bonos dolar PMI hoy", n=3),
        "market": search_news("SP500 Nasdaq earnings season VIX sentiment hoy", n=3),
    }

# ═════════════════════════════════════════════════════
#  MEMORIA SQLite LOCAL + SUPABASE
# ═════════════════════════════════════════════════════
history = {}
memory_lock = threading.Lock()
working_memory = deque(maxlen=100)
processed_alert_hashes = set()

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
                (str(chat_id), role, content[:2000], datetime.utcnow().isoformat()))
            conn.commit(); conn.close()
    except Exception as e: logging.error(f"SQLite save: {e}")

def load_memory_local(chat_id, limit=8):
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
                (str(chat_id), key, value[:2000], datetime.utcnow().isoformat()))
            conn.commit(); conn.close()
    except Exception as e: logging.error(f"Knowledge upsert: {e}")

def list_knowledge(chat_id, limit=10):
    try:
        with memory_lock:
            conn = _memory_conn()
            rows = conn.execute("SELECT key,value FROM jarvis_knowledge WHERE chat_id=? ORDER BY updated_at DESC LIMIT ?",
                (str(chat_id), int(limit))).fetchall()
            conn.close()
        return rows
    except: return []

def persist_movements(movements):
    if not movements or "error" in movements[0]: return
    try:
        with memory_lock:
            conn = _memory_conn()
            for m in movements:
                tx_hash = str(abs(hash(f"{m.get('broker')}|{m.get('fecha')}|{m.get('accion')}|{m.get('ticker')}|{m.get('importe_eur')}|{m.get('asunto')}")))
                conn.execute("""INSERT OR IGNORE INTO jarvis_transactions
                    (tx_hash,broker,fecha,accion,ticker,importe_eur,asunto,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (tx_hash, m.get("broker"), m.get("fecha"), m.get("accion"),
                     m.get("ticker"), m.get("importe_eur"), m.get("asunto"),
                     datetime.utcnow().isoformat()))
            conn.commit(); conn.close()
    except Exception as e: logging.error(f"Persist mov: {e}")

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
                  "created_at": datetime.utcnow().isoformat()}, timeout=5)
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
DEFAULT_TEMPLATE = """# PLANTILLA_MIKI_VALORACION_EXACTA

## 1) Tesis (max 3 lineas)
- Que hace la empresa, por que gana dinero y por que puede seguir ganandolo.

## 2) Datos base (hoy)
- Precio actual:
- Moneda:
- Market Cap:
- Sector / Industria:

## 3) Calidad del negocio
- ROE (%):
- Margen operativo (%):
- Deuda/Equity:
- Free Cash Flow:

## 4) Crecimiento y ejecucion
- Crecimiento ingresos (%):
- Crecimiento BPA (%):
- Recompras o dilucion (acciones en circulacion):

## 5) Valoracion (con formulas obligatorias)
- PER trailing:
- PER forward:
- Precio en rango 52 semanas: ((Precio - Min52) / (Max52 - Min52)) * 100
- FCF Yield: (FCF / MarketCap) * 100
- De-rating PER: ((PER trailing - PER forward) / PER trailing) * 100

## 6) Precio justo
- Escenario conservador:
- Escenario base:
- Escenario optimista:
- Margen seguridad: ((Precio justo base - Precio actual) / Precio justo base) * 100

## 7) Riesgos reales (max 3)
1.
2.
3.

## 8) Decision operativa
- Accion hoy: COMPRAR / MANTENER / REDUCIR
- Zona de entrada:
- Tamano sugerido (0%-10%):
- Condicion de invalidacion:

## 9) Conviccion final
- Nota (0-10):
- Frase final para Miki (directa, sin humo):
"""

def load_template():
    p = Path(TEMPLATE_PATH)
    if p.exists():
        try:
            txt = p.read_text(encoding="utf-8").strip()
            if txt: return txt
        except: pass
    return DEFAULT_TEMPLATE

def save_template(text):
    try:
        p = Path(TEMPLATE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.strip() + "\n", encoding="utf-8")
        return True
    except Exception as e:
        logging.error(f"Save template: {e}")
        return False

# ═════════════════════════════════════════════════════
#  DETECTOR MERCADO
# ═════════════════════════════════════════════════════
def market_status_human():
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    hour_utc = now.hour
    dia_es = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo'][weekday]
    if weekday == 5: return "HOY ES SÁBADO - todos los mercados cerrados"
    if weekday == 6: return "HOY ES DOMINGO - todos los mercados cerrados"
    nyse_open = 13 <= hour_utc < 20
    eu_open = 7 <= hour_utc < 16
    if nyse_open and eu_open: return f"Es {dia_es}. NYSE y Europa abiertas."
    if eu_open and not nyse_open: return f"Es {dia_es}. Europa abierta. NYSE abre 15:30 España."
    if not eu_open and nyse_open: return f"Es {dia_es}. NYSE abierta. Europa ya cerró."
    if hour_utc < 7: return f"Es {dia_es} pre-mercado."
    return f"Es {dia_es}, fuera de horario."

# ═════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ═════════════════════════════════════════════════════
def get_system():
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercado = market_status_human()
    return f"""Eres JARVIS, el colega de Miki para temas de inversión.
Hablas como un amigo que sabe mucho de bolsa, no como un manual ni un informe.
Te comportas como un inversor senior: prudente, racional y accionable.

═══ CÓMO HABLAS ═══
- Lenguaje COLOQUIAL ESPAÑOL DE ESPAÑA. Como en un bar.
- Frases cortas. Naturales. En voz alta.
- NUNCA estilo teletipo "INFLACIÓN USA · FED TASAS".
- En vez: "La inflación en USA sigue atascada y la FED no baja tipos."
- Usa: "joder", "vaya", "pinta bien", "está jodido", "ojo con esto"
- NUNCA listas con bullets para conversar
- Cifras dentro de frases, no como datos sueltos

═══ CONTEXTO ═══
Fecha: {hoy} - {hora} (España)
Mercado: {mercado}

Si Miki pregunta "cómo está el mercado" un sábado/domingo, díselo directo.

═══ DATOS ═══
- Si recibes "DATOS REALES VERIFICADOS de FMP" en el mensaje, son del DÍA, ÚSALOS sin dudar.
- NUNCA inventes precios, PER, FCF, ROIC.
- Si no tienes el dato verificado: "no lo tengo verificado, deja que mire"

═══ CARTERA REAL — €34.145 — +22.03% ═══
GOOGL +77.4% 17.8% (Alta convicción) | ZEG +70.8% 2% | JNJ +61.4% 5.5%
Gold +41.9% 2.3% | SmCap +24.5% 11.4% | SP500 +24.1% 15% | Europe +23.3% 12.6%
AAPL +20.6% 5.3% | CELH +20.9% | TRET +6.9% 3.7% | SSNC +5.5% 4.2%
TXRH -4.1% 2.6% | MONC -3.8% 7.6% (post-earnings 21/04) | India -7.4% 3.8%
MSFT -12.5% 4.5% (earnings 29/04) | VISA €637 nueva (earnings 28/04)
NKE VENDIDA correctamente Abril 2026

═══ VALUE INVESTING ═══
FCF > EBITDA. Margen seguridad mín 30%. DCF NO para tech (usa EV/FCF).
DCF SÍ para JNJ/TXRH/SSNC. FFO para REITs (TRET). Macro para Gold.
Directiva = 40-80% del éxito.

SEÑALES: COMPRAR / ACUMULAR / MANTENER / VIGILAR / REDUCIR / VENDER

COUNCIL (cuando /consejo): Buffett (moat), Lynch (crecimiento), Klarman (margen), Munger (mental).

═══ RED FLAGS ═══
1. Dilución >5%/año  2. Deuda/EBITDA >4x  3. CEO vendiendo
4. Guidance imposible  5. Cambio auditor  6. Resultados que cumplen exactos
7. Revenue agresivo  8. Goodwill >50% activo  9. Revenue sin FCF
10. Partes relacionadas

═══ CONOCIMIENTO INVERSIÓN (curso "Invertir Desde Cero") ═══
Interés compuesto: bola de nieve. €10k al 10% durante 50 años = €1.173.908.
5 activos: efectivo (-2% real), renta fija (preserva), inmuebles (3-5% neto),
oro/btc (sin flujos), ETFs (8-9%) y acciones concentradas (+15% potencial).
ETFs: ojo divisa, falsa diversificación ACWI+SP500, caída intra-anual media -14%.
Valor intrínseco: precio NO = valor. Largo plazo precio persigue valor.
Market Cap = precio × acciones. EV = MC + Deuda - Caja (precio real comprar).
Beneficios embudo: Ventas → EBITDA → EBIT → Neto. EBITDA y FCF Non-GAAP, manipulables.
PER = Market Cap / Beneficio. Media S&P = 17.1x. PER bajo (2x) = trampa, no ganga.
Calidad (Amazon/MSFT/GOOGL) justifica >25x. Precio = EPS × Múltiplo.
Margen Operativo (EBIT) compara competidores. Ferrari 29% vs Porsche 7.95%.
Value: madura barata por pánico, espera Rerating. Growth: alta cot, EPS +20%.
Inversor fundamental usa AMBAS sin etiquetas.

═══ CUÁNDO USAR FORMATO TÉCNICO ═══
Solo cuando Miki use /analiza /consejo /valora /institucional /estrategia.
En conversación libre RESPONDE NATURAL.
Si pide "valora", "valoración" o "plantilla" → usa la PLANTILLA EXACTA literalmente.

═══ LONGITUD ═══
- Saludo: 1-2 frases
- Pregunta puntual: 2-4 frases
- Conversación con datos: 3-6 frases
- Análisis formal: hasta 12 líneas

Si Miki está agobiado, primero le escuchas. Luego ayudas.
"""

# ═════════════════════════════════════════════════════
#  CLAUDE
# ═════════════════════════════════════════════════════
def ask_claude(chat_id, text, web_data="", max_tokens=600):
    mem = load_memory(chat_id, limit=6)
    facts = list_knowledge(chat_id, limit=8)
    txs = recent_transactions(limit=5)
    if chat_id not in history: history[chat_id] = []

    hoy = datetime.now().strftime("%d/%m/%Y")
    facts_txt = "\n".join([f"- {k}: {v}" for k,v in facts]) if facts else "sin hechos guardados"
    tx_txt = "\n".join([f"- {t[0]} {t[2]} {t[3] or '?'} {t[4] or ''} EUR ({t[1]})" for t in txs]) if txs else "sin transacciones"

    if web_data:
        content = f"{text}\n\nDATOS_FMP_VERIFICADOS ({hoy}):\n{web_data}\n\nMEMORIA_LARGA:\n{facts_txt}\n\nTX_GMAIL:\n{tx_txt}"
    else:
        content = f"{text}\n\nMEMORIA_LARGA:\n{facts_txt}\n\nTX_GMAIL:\n{tx_txt}"

    history[chat_id].append({"role": "user", "content": content})
    all_msgs = mem + history[chat_id][-6:]

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
                  "system": get_system(), "messages": msgs}, timeout=45)
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

def ask_claude_raw(prompt, max_tokens=400):
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                  "system": "Eres analista financiero senior. Responde en español, técnico y honesto.",
                  "messages": [{"role": "user", "content": prompt}]}, timeout=45)
        data = r.json()
        if "error" in data: return f"Error: {data['error'].get('message','')[:100]}"
        return data["content"][0]["text"]
    except Exception as e: return f"Error: {e}"

# ═════════════════════════════════════════════════════
#  SUBAGENTES
# ═════════════════════════════════════════════════════
def run_subagent_debate(ticker, snapshot):
    if not ENABLE_SUBAGENTS:
        return ""
    roles = {
        "VALUE": "Analista value tipo Buffett/Munger. Prioriza calidad y margen seguridad.",
        "RISK": "Gestor de riesgo. Detecta peligros y tamaño de posición prudente.",
        "CATALYST": "Especialista en catalizadores (earnings, guidance, momentum).",
    }
    outputs = {}
    for role, role_desc in roles.items():
        prompt = (f"ROL: {role_desc}\nTICKER: {ticker}\nDATOS: {snapshot}\n"
                  "Devuelve SOLO: tesis corta, riesgos, acción recomendada, convicción 0-10.")
        outputs[role] = ask_claude_raw(prompt, max_tokens=200)

    synth = ask_claude_raw(
        f"Sintetiza los 3 análisis y entrega:\n1) Consenso\n2) Disenso\n3) Acción hoy\n4) Stop mental\n\n"
        f"VALUE:\n{outputs['VALUE']}\n\nRISK:\n{outputs['RISK']}\n\nCATALYST:\n{outputs['CATALYST']}",
        max_tokens=300)

    return (f"\n\n🧠 Mesa de subagentes:\n\nVALUE:\n{outputs['VALUE']}\n\n"
            f"RISK:\n{outputs['RISK']}\n\nCATALYST:\n{outputs['CATALYST']}\n\nCONSENSO:\n{synth}")

# ═════════════════════════════════════════════════════
#  COMANDOS AVANZADOS: /valora /institucional /estrategia
# ═════════════════════════════════════════════════════
def valuation_with_template(chat_id, ticker):
    snap = build_valuation_snapshot(ticker)
    if snap.get("error"): return snap["error"]
    template = load_template()
    price = snap.get("price"); low = snap.get("low_52w"); high = snap.get("high_52w")
    mc = snap.get("market_cap"); fcf_ps = snap.get("fcf_per_share")
    manual = {}
    if isinstance(price,(int,float)) and isinstance(low,(int,float)) and isinstance(high,(int,float)) and high>low:
        manual["pct_in_52w_range"] = round((price-low)/(high-low)*100, 2)
    if isinstance(snap.get("pe_trailing"),(int,float)) and isinstance(snap.get("pe_forward"),(int,float)) and snap["pe_trailing"]:
        manual["pe_de_rating_pct"] = round(((snap["pe_trailing"]-snap["pe_forward"])/snap["pe_trailing"])*100, 2)

    prompt = (f"Valora {ticker} usando EXACTAMENTE esta plantilla en español natural:\n\n{template}\n\n"
              "REGLAS:\n- Sé directo, como colega experto.\n- No inventes nada fuera del snapshot.\n"
              "- Si falta dato, dilo explícito.\n- Cierra con decisión clara para hoy.\n\n"
              f"SNAPSHOT_REAL:\n{snap}\n\nMETRICAS_MANUALES:\n{manual}")
    base = ask_claude(chat_id, prompt, max_tokens=900)
    debate = run_subagent_debate(ticker, snap)
    upsert_knowledge(chat_id, f"valuation_{ticker}_{int(time.time())}", base[:600])
    working_memory.append({"ts": datetime.utcnow().isoformat(), "ticker": ticker, "type": "valuation"})
    return base + debate

def institutional_analysis(chat_id, ticker):
    snap = build_valuation_snapshot(ticker)
    if snap.get("error"): return snap["error"]
    macro = get_macro_pack()
    prompt = (f"Análisis INSTITUCIONAL de {ticker} buy-side. Cubre obligatoriamente:\n"
              "1) Moat (ventaja competitiva)\n2) Márgenes y tendencia\n3) Generación de caja\n"
              "4) Posición financiera y riesgo balance\n5) Crecimiento ingresos y BPA\n"
              "6) Capital allocation\n7) Estimaciones + eventos próximos\n"
              "8) Impacto macro/mercado\n9) Evaluación 0-10 y estrategia ejecutable\n"
              "Sé brutalmente honesto, sin inventar datos.\n\n"
              f"SNAPSHOT:{snap}\nMACRO:{macro}")
    out = ask_claude(chat_id, prompt, max_tokens=1200)
    debate = run_subagent_debate(ticker, snap)
    upsert_knowledge(chat_id, f"institutional_{ticker}_{int(time.time())}", out[:600])
    return out + debate

def portfolio_strategy(chat_id):
    universe = ["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "SP500"]
    packs = []
    for t in universe:
        snap = build_valuation_snapshot(t)
        if not snap.get("error"): packs.append(snap)
    macro = get_macro_pack()
    prompt = ("Construye estrategia institucional cartera Miki:\n"
              "- Asignación sugerida (%)\n"
              "- Reducir/mantener/aumentar\n"
              "- Coberturas o liquidez táctica\n"
              "- Plan ante macro alcista/base/bajista\n"
              "- 3 reglas de disciplina\n\n"
              f"UNIVERSO:{packs}\nMACRO:{macro}")
    out = ask_claude(chat_id, prompt, max_tokens=1000)
    upsert_knowledge(chat_id, f"strategy_{int(time.time())}", out[:700])
    return out

# ═════════════════════════════════════════════════════
#  ELEVENLABS + WHISPER
# ═════════════════════════════════════════════════════
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
    except Exception as e:
        logging.error(f"Whisper: {e}")
        return None

# ═════════════════════════════════════════════════════
#  TELEGRAM
# ═════════════════════════════════════════════════════
def send(chat_id, text):
    try:
        # Telegram limit es 4096, partimos si hace falta
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
#  GMAIL SKILL #10
# ═════════════════════════════════════════════════════
BROKER_SENDERS = {
    "myinvestor": ["myinvestor.es", "no-reply@myinvestor.es"],
    "trade_republic": ["traderepublic.com", "no-reply@traderepublic.com"],
}
ACTION_KEYWORDS = {
    "VENTA": ["venta ejecutada", "vendido", "sell executed", "sold"],
    "COMPRA": ["compra ejecutada", "comprado", "buy executed", "bought"],
    "DIVIDENDO": ["dividendo", "dividend"],
    "INGRESO": ["ingreso recibido", "deposit received"],
    "RETIRADA": ["retirada", "withdrawal"],
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
    return m.group(1) if m else None

def _extract_amount(text):
    m = re.search(r"([\d]+(?:[.,]\d{1,2})?)\s*EUR", text)
    if m:
        try: return float(m.group(1).replace(",", "."))
        except: return None
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
    if not movs: return "Tranquilo, no he visto movimientos en tu Gmail los últimos 7 días."
    if movs and "error" in movs[0]: return f"Tengo un problema con Gmail: {movs[0]['error']}"
    lines = [f"He detectado {len(movs)} cosas en tu Gmail:"]
    for m in movs[:10]:
        ticker = m.get("ticker") or "?"
        imp = m.get("importe_eur")
        imp_s = f" por {imp:.0f} EUR" if imp else ""
        b = "MyInvestor" if m["broker"] == "myinvestor" else "Trade Republic"
        lines.append(f"- {b}: {m['accion'].lower()} de {ticker}{imp_s}")
    return "\n".join(lines)

def gmail_monitor_loop():
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and MIKI_CHAT_ID):
        logging.info("Gmail monitor desactivado")
        return
    time.sleep(60)
    while True:
        try:
            movs = fetch_broker_movements(days=2)
            if movs and "error" not in movs[0]:
                persist_movements(movs)
                sig_hash = str(abs(hash(str(movs[:5]))))
                if sig_hash not in processed_alert_hashes:
                    processed_alert_hashes.add(sig_hash)
                    send(MIKI_CHAT_ID, "Oye Miki, mira lo que ha llegado a tu Gmail:\n\n" + format_movements(movs))
        except Exception as e:
            logging.error(f"Gmail loop: {e}")
        time.sleep(1800)

# ═════════════════════════════════════════════════════
#  BRIEFING AUTÓNOMO
# ═════════════════════════════════════════════════════
def autonomous_briefing_loop():
    if not (AUTONOMY_ENABLED and MIKI_CHAT_ID): return
    time.sleep(120)
    while True:
        try:
            datos = get_real_data_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA"])
            prompt = ("Briefing autónomo para Miki como asesor privado. "
                      "Máximo 6 frases, tono humano, una acción concreta para hoy.")
            reply = ask_claude(MIKI_CHAT_ID, prompt, web_data=datos, max_tokens=400)
            send(MIKI_CHAT_ID, f"🤖 Briefing autónomo:\n\n{reply}")
        except Exception as e:
            logging.error(f"Autonomy: {e}")
        time.sleep(max(30, AUTONOMY_INTERVAL_MIN) * 60)

# ═════════════════════════════════════════════════════
#  HANDLER PRINCIPAL
# ═════════════════════════════════════════════════════
def handle(chat_id, text):
    txt = text.strip()
    hoy = datetime.now().strftime("%d/%m/%Y")
    parts = txt.split()
    cmd = parts[0].lower() if txt.startswith("/") else None

    if cmd == "/miid":
        send(chat_id, f"Tu chat ID es: {chat_id}"); return

    if txt.lower().startswith("recuerda que "):
        fact = txt[12:].strip()
        if fact:
            upsert_knowledge(chat_id, f"fact_{int(time.time())}", fact)
            send(chat_id, "Guardado en memoria permanente. Lo tendré en cuenta siempre.")
        return

    if cmd == "/start":
        send(chat_id,
             f"Buenas Miki, son las {datetime.now().strftime('%H:%M')} del {hoy}.\n\n"
             "Pregúntame lo que quieras como si me lo dijeras a la cara. "
             "Por texto o por audio.\n\n"
             "🎯 Comandos análisis:\n"
             "/valora TICKER - plantilla exacta\n"
             "/analiza TICKER - análisis rápido\n"
             "/consejo TICKER - council Buffett/Lynch/Klarman/Munger\n"
             "/institucional TICKER - análisis buy-side completo\n"
             "/hyper TICKER - mesa subagentes VALUE/RISK/CATALYST\n"
             "/estrategia - plan global cartera\n\n"
             "📊 Comandos cartera:\n"
             "/cartera /alertas /earnings /macro /salud\n\n"
             "🧠 Memoria y otros:\n"
             "/movimientos /memoria /plantilla /miid\n"
             "Di \"recuerda que ...\" para grabar permanente")
        return

    if cmd == "/plantilla":
        send(chat_id, load_template()); return

    if cmd == "/setplantilla":
        tpl = txt.replace("/setplantilla", "", 1).strip()
        if not tpl:
            send(chat_id, "Uso: /setplantilla <tu plantilla exacta>"); return
        if save_template(tpl):
            send(chat_id, "Perfecto. Plantilla guardada exactamente como me la has pasado.")
        else:
            send(chat_id, "Error guardando plantilla.")
        return

    if cmd == "/valora":
        if len(parts) < 2:
            send(chat_id, "Pásame ticker: /valora GOOGL"); return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Dame 10-15 segundos, te valoro {ticker} con tu plantilla.")
        reply = valuation_with_template(chat_id, ticker)
        send(chat_id, reply)
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/institucional":
        if len(parts) < 2:
            send(chat_id, "Uso: /institucional TICKER"); return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Análisis institucional de {ticker} con macro + fundamentales...")
        send(chat_id, institutional_analysis(chat_id, ticker))
        return

    if cmd == "/hyper":
        if len(parts) < 2:
            send(chat_id, "Uso: /hyper TICKER"); return
        ticker = parts[1].upper()
        typing(chat_id)
        snap = build_valuation_snapshot(ticker)
        if snap.get("error"):
            send(chat_id, snap["error"]); return
        send(chat_id, "Activo mesa de subagentes y comité de inversión...")
        send(chat_id, run_subagent_debate(ticker, snap))
        return

    if cmd == "/estrategia":
        typing(chat_id)
        send(chat_id, "Construyendo estrategia institucional para tu cartera...")
        send(chat_id, portfolio_strategy(chat_id))
        return

    if cmd == "/cartera":
        send(chat_id, "Voy a coger los precios actuales de toda la cartera...")
        typing(chat_id)
        datos = get_real_data_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "SSNC", "TXRH", "CELH"])
        prompt = (f"Cuéntale a Miki cómo está su cartera HOY {hoy} de forma natural. "
                  f"Usa los precios REALES verificados. 6-8 líneas máximo. "
                  f"Mira si MSFT (-12.5%) se ha movido.")
        send(chat_id, ask_claude(chat_id, prompt, web_data=datos, max_tokens=600))
        return

    if cmd == "/alertas":
        send(chat_id,
             f"Te recuerdo lo que tienes encima - {hoy}\n\n"
             "MSFT en -12.5% y earnings el 29.\n"
             "MONC -3.8%, post-earnings 21/04.\n"
             "India -7.4%, presionada por macro.\n"
             "VISA es nueva, earnings el 28.")
        return

    if cmd == "/movimientos":
        typing(chat_id)
        send(chat_id, "Voy a echar un ojo a tu Gmail...")
        movs = fetch_broker_movements(days=7)
        persist_movements(movs)
        send(chat_id, format_movements(movs))
        return

    if cmd == "/analiza":
        if len(parts) < 2:
            send(chat_id, "Dime un ticker - /analiza VISA"); return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Voy a por {ticker}...")
        datos = get_real_data(ticker)
        prompt = (f"Análisis técnico completo de {ticker} hoy {hoy}. "
                  f"Usa los datos REALES verificados. Formato técnico con métricas. "
                  f"Si es posición de Miki, contextualiza al final con tono natural.")
        reply = ask_claude(chat_id, prompt, web_data=datos, max_tokens=700)
        send(chat_id, reply)
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/consejo":
        if len(parts) < 2:
            send(chat_id, "Dime un ticker - /consejo VISA"); return
        ticker = parts[1].upper()
        typing(chat_id)
        datos = get_real_data(ticker)
        prompt = (f"Consejo profundo sobre {ticker} hoy {hoy}. "
                  f"Usa datos REALES verificados. "
                  f"Council: Buffett, Lynch, Klarman, Munger. "
                  f"Cada uno SI/NO con razón natural.")
        reply = ask_claude(chat_id, prompt, web_data=datos, max_tokens=800)
        send(chat_id, reply)
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/earnings":
        send(chat_id,
             f"Earnings próximos en tu cartera ({hoy}):\n\n"
             "VISA - 28/04/2026 (martes)\n"
             "MSFT - 29/04/2026 (miércoles)\n\n"
             "MONC ya reportó 21/04.")
        return

    if cmd == "/macro":
        typing(chat_id)
        web = search_news("FED tipos inflacion VIX dolar mercados hoy", n=3)
        prompt = f"Cuéntame en lenguaje coloquial cómo está el mercado hoy {hoy}. Tono natural."
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=400)
        send(chat_id, reply)
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/salud":
        typing(chat_id)
        prompt = (f"Cuéntale a Miki cómo está su cartera hoy {hoy} a vista general. "
                  f"Concentración (GOOGL 17.8%), sectorial, alpha vs SP500. Tono natural.")
        send(chat_id, ask_claude(chat_id, prompt, max_tokens=500))
        return

    if cmd == "/memoria":
        mem = load_memory(chat_id, limit=6)
        facts = list_knowledge(chat_id, limit=6)
        txs = recent_transactions(limit=4)
        wm = list(working_memory)[-4:]
        if mem or facts or txs:
            lines = [f"{m['role'].upper()}: {m['content'][:140]}..." for m in mem]
            facts_s = "\n".join([f"- {k}: {v[:80]}" for k,v in facts]) if facts else "- sin hechos"
            tx_s = "\n".join([f"- {x[0]} {x[2]} {x[3] or '?'} {x[4] or ''} EUR" for x in txs]) if txs else "- sin transacciones"
            wm_s = "\n".join([f"- {w.get('type')} {w.get('ticker','')}" for w in wm]) if wm else "- sin working memory"
            send(chat_id,
                 "Lo último:\n\n" + "\n\n".join(lines) +
                 "\n\nHechos guardados:\n" + facts_s +
                 "\n\nTransacciones Gmail:\n" + tx_s +
                 "\n\nWorking memory:\n" + wm_s)
        else:
            send(chat_id, "Aún no he guardado nada.")
        return

    # ─── CONVERSACIÓN LIBRE ──────────────────────────────
    typing(chat_id)
    txt_low = txt.lower()
    datos = ""

    # Si pide valoración explícita
    if any(p in txt_low for p in ["valora", "valoración", "valoracion"]):
        tck = detect_ticker(txt)
        if tck:
            send(chat_id, valuation_with_template(chat_id, tck))
            return

    # Detectar ticker mencionado
    ticker_detected = detect_ticker(txt)
    if ticker_detected:
        datos = get_real_data(ticker_detected)
    elif any(p in txt_low for p in ["cartera", "todas las posiciones", "per de mi", "per medio"]):
        datos = get_real_data_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA"])
    elif any(p in txt_low for p in ["macro", "fed", "inflacion", "vix", "dolar", "mercado"]):
        datos = search_news("FED inflacion VIX dolar mercados hoy", n=2)

    reply = ask_claude(chat_id, txt, web_data=datos, max_tokens=600)
    send(chat_id, reply)
    if len(reply) > 60:
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)

def handle_voice(chat_id, file_id):
    typing(chat_id)
    if not OPENAI_KEY:
        send(chat_id, "Necesito OPENAI_API_KEY en Render para procesar audios. Escríbeme texto.")
        return
    text = transcribe_voice(file_id)
    if not text:
        send(chat_id, "No te he pillado bien la nota. Repítela o escríbela.")
        return
    send(chat_id, f"🎙️ Te he entendido: \"{text}\"")
    handle(chat_id, text)

# ═════════════════════════════════════════════════════
#  POLLING
# ═════════════════════════════════════════════════════
def poll():
    offset = 0
    logging.info(f"JARVIS v8 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logging.info(f"FMP:{'OK' if FMP_KEY else 'NO'} | Whisper:{'OK' if OPENAI_KEY else 'NO'} | "
                 f"ElevenLabs:{'OK' if ELEVENLABS_KEY else 'NO'} | "
                 f"Gmail:{'OK' if (GMAIL_USER and GMAIL_APP_PASSWORD) else 'NO'} | "
                 f"Supabase:{'OK' if SUPABASE_URL else 'NO'}")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                             params={"offset": offset, "timeout": 30}, timeout=35)
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                cid = msg.get("chat", {}).get("id")
                if not cid: continue
                txt = msg.get("text", "")
                if txt:
                    threading.Thread(target=handle, args=(cid, txt), daemon=True).start()
                    continue
                voice = msg.get("voice")
                if voice and voice.get("file_id"):
                    threading.Thread(target=handle_voice, args=(cid, voice["file_id"]), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")

# ═════════════════════════════════════════════════════
#  HTTP SERVER
# ═════════════════════════════════════════════════════
class H(BaseHTTPRequestHandler):
    def _send_text(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        self._send_text(200)
        msg = f"JARVIS v8 - {datetime.now().strftime('%d/%m/%Y %H:%M')} - Online (FMP+Subagents)"
        self.wfile.write(msg.encode("utf-8"))

    def do_HEAD(self):
        self._send_text(200)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            msg = body.get("message", "")
            chat_id = body.get("chat_id", "webapp")
            if not msg: raise ValueError("No message")
            datos = ""
            tck = detect_ticker(msg)
            if tck: datos = get_real_data(tck)
            reply = ask_claude(chat_id, msg, web_data=datos, max_tokens=600)
            resp = json.dumps({"reply": reply}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
        except Exception as e:
            logging.error(f"POST: {e}")
            self.send_response(500)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, *a): pass

# ═════════════════════════════════════════════════════
#  ARRANQUE
# ═════════════════════════════════════════════════════
threading.Thread(target=poll, daemon=True).start()
threading.Thread(target=gmail_monitor_loop, daemon=True).start()
threading.Thread(target=autonomous_briefing_loop, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), H).serve_forever()

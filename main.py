"""
JARVIS v9 — Miguel (Miki) — 01/05/2026
- Plantilla visual SIEMPRE para empresas (estilo tarjeta premium)
- Conversacion natural sin comandos (le hablas como a un colega)
- Gmail: MyInvestor + Trade Republic + ING
- FMP datos reales verificados
"""
import os, logging, requests, threading, json, time
import imaplib, email, re, sqlite3
from email.header import decode_header
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
AUTONOMY_ENABLED   = os.environ.get("AUTONOMY_ENABLED", "1") == "1"
AUTONOMY_INTERVAL_MIN = int(os.environ.get("AUTONOMY_INTERVAL_MIN", "360"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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

# Palabras que indican que es conversacion, NO datos de empresa
CONVERSATIONAL_KEYWORDS = [
    "qué piensas", "que piensas", "qué opinas", "que opinas",
    "estoy preocupado", "estoy nervioso", "estoy contento",
    "ayúdame", "ayudame", "consejo de", "qué hago", "que hago",
    "no sé", "no se ", "estoy pensando", "tengo dudas",
    "explícame", "explicame", "cómo funciona", "como funciona",
    "qué es ", "que es "
]

def is_conversational(text):
    txt_low = text.lower()
    return any(p in txt_low for p in CONVERSATIONAL_KEYWORDS)

# ═════════════════════════════════════════════════════
#  FMP
# ═════════════════════════════════════════════════════
def fmp_get(endpoint, ticker):
    if not FMP_KEY: return None
    try:
        r = requests.get(f"https://financialmodelingprep.com/api/v3/{endpoint}/{ticker}",
                         params={"apikey": FMP_KEY}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and data: return data[0]
    except Exception as e:
        logging.error(f"FMP {endpoint} {ticker}: {e}")
    return None

def get_real_data(ticker_input):
    """Datos reales verificados estructurados."""
    ticker_up = ticker_input.upper()
    if ticker_up in EUROPEAN_TICKERS:
        # Europeos via Tavily
        return {"is_european": True, "ticker": ticker_up,
                "tavily": search_news(f"{ticker_input} stock price PER FCF today", n=3)}

    fmp_ticker = FMP_TICKERS.get(ticker_up, ticker_up)
    quote = fmp_get("quote", fmp_ticker)
    if not quote:
        return {"error": f"No he podido sacar datos de {ticker_input}"}

    ratios = fmp_get("ratios-ttm", fmp_ticker) or {}
    metrics = fmp_get("key-metrics-ttm", fmp_ticker) or {}
    profile = fmp_get("profile", fmp_ticker) or {}

    return {
        "ticker": fmp_ticker,
        "name": quote.get("name") or profile.get("companyName") or ticker_up,
        "price": quote.get("price"),
        "change_pct": quote.get("changesPercentage"),
        "previous_close": quote.get("previousClose"),
        "pe": quote.get("pe") or ratios.get("priceEarningsRatioTTM"),
        "eps": quote.get("eps"),
        "market_cap": quote.get("marketCap"),
        "year_high": quote.get("yearHigh"),
        "year_low": quote.get("yearLow"),
        "roe": ratios.get("returnOnEquityTTM"),
        "roic": metrics.get("roicTTM"),
        "op_margin": ratios.get("operatingProfitMarginTTM"),
        "fcf_per_share": metrics.get("freeCashFlowPerShareTTM"),
        "ev_ebitda": metrics.get("enterpriseValueOverEBITDATTM"),
        "debt_equity": ratios.get("debtEquityRatioTTM") or ratios.get("debtToEquityTTM"),
        "dividend_yield": quote.get("dividendYield"),
        "sector": profile.get("sector"),
        "currency": profile.get("currency", "USD"),
    }

def format_data_for_claude(data):
    """Formatea datos en bloque legible para Claude."""
    if not data: return ""
    if data.get("error"): return data["error"]
    if data.get("is_european"):
        return f"DATOS EUROPEO {data['ticker']} via Tavily:\n{data.get('tavily','')}"

    lines = [f"DATOS REALES VERIFICADOS FMP ({datetime.now().strftime('%d/%m/%Y %H:%M')}):"]
    lines.append(f"Empresa: {data.get('name')} ({data.get('ticker')})")
    if data.get("price") is not None:
        lines.append(f"Precio: ${data['price']:.2f}")
    if data.get("change_pct") is not None:
        lines.append(f"Variación día: {data['change_pct']:+.2f}%")
    if data.get("previous_close"):
        lines.append(f"Cierre anterior: ${data['previous_close']:.2f}")
    if data.get("pe"):
        lines.append(f"PER: {data['pe']:.1f}x")
    if data.get("eps"):
        lines.append(f"EPS: ${data['eps']:.2f}")
    if data.get("market_cap"):
        lines.append(f"Market cap: ${data['market_cap']/1e9:.1f}B")
    if data.get("year_high") and data.get("year_low"):
        lines.append(f"Rango 52s: ${data['year_low']:.2f} - ${data['year_high']:.2f}")
    if data.get("roe"):
        lines.append(f"ROE: {data['roe']*100:.1f}%")
    if data.get("roic"):
        lines.append(f"ROIC: {data['roic']*100:.1f}%")
    if data.get("op_margin"):
        lines.append(f"Margen operativo: {data['op_margin']*100:.1f}%")
    if data.get("fcf_per_share"):
        lines.append(f"FCF/acción: ${data['fcf_per_share']:.2f}")
    if data.get("ev_ebitda"):
        lines.append(f"EV/EBITDA: {data['ev_ebitda']:.1f}x")
    if data.get("debt_equity"):
        lines.append(f"Deuda/Equity: {data['debt_equity']:.2f}")
    if data.get("dividend_yield"):
        d = data['dividend_yield']
        lines.append(f"Dividend yield: {d*100:.2f}%" if d < 1 else f"Dividend yield: {d:.2f}%")
    if data.get("sector"):
        lines.append(f"Sector: {data['sector']}")
    return "\n".join(lines)

def get_real_data_multi(tickers_list):
    parts = []
    for t in tickers_list:
        d = get_real_data(t)
        if d and not d.get("error"):
            parts.append(format_data_for_claude(d))
    return "\n\n".join(parts)

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

# ═════════════════════════════════════════════════════
#  MERCADO
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
#  SYSTEM PROMPT — DOS MODOS
# ═════════════════════════════════════════════════════
def get_system_card():
    """Modo TARJETA — cuando pide datos de una empresa."""
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
[interpretación corta, útil, con criterio. 2-3 frases máximo]

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

═══ TÍTULO DE TARJETA ═══
Cuando es análisis general usa: RESULTADOS, VALORACIÓN, BUSCADOR, CLOUD, AZURE,
AWS, YOUTUBE, MÁRGENES, CAPEX, REACCIÓN, GUÍA, RPO

═══ DATOS ÚTILES PARA BULLETS ═══
Ventas, EBIT, EPS, Guidance, PER, EV/FCF, valor intrínseco, precio actual,
reacción mercado, RPO, CapEx, márgenes, ROIC, dividendo, FCF

═══ FRASES PRINCIPALES BUENAS ═══
- "La IA está acelerando Search, no frenándolo"
- "Buenos resultados. El ruido viene del CapEx, no del negocio"
- "El mercado castiga el CapEx, no el negocio"
- "La tesis sigue intacta"
- "Margen de seguridad agotado"

═══ VOCABULARIO QUE SÍ ═══
tesis, refuerza, deteriora, acelera, desacelera, beat, miss, guidance,
margen, CapEx, valoración, convicción, oportunidad, vigilancia, demanda,
moat, pricing power, ROIC, EV/FCF, margen de seguridad

═══ VOCABULARIO PROHIBIDO ═══
"interesante", "parece", "quizá", "podría ser", "muy buena empresa",
"de alguna forma", "en cierto modo", "resulta curioso"

═══ DATOS REALES ═══
Si recibes "DATOS REALES VERIFICADOS FMP" en el mensaje, son del DÍA, ÚSALOS.
NUNCA inventes números. Si falta uno, di ⚪ NO CONCLUYENTE.

═══ CARTERA REAL DE MIKI (puede haber cambiado) ═══
GOOGL +77.4% 17.8% Alta convicción · ZEG +70.8% · JNJ +61.4% · Gold +41.9%
AAPL +20.6% · CELH +20.9% · SmCap +24.5% · SP500 +24.1% · Europe +23.3%
TRET +6.9% · SSNC +5.5%
PERDIENDO: MSFT -12.5% (earnings 29/04) · MONC -3.8% · TXRH -4.1% · India -7.4%
NUEVA: VISA · VENDIDA: NKE
"""

def get_system_chat():
    """Modo CONVERSACIÓN — para charlar como colega, sin tarjeta."""
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercado = market_status_human()
    return f"""Eres JARVIS, el colega de Miki para temas de inversión.
Ahora estás en modo CONVERSACIÓN. NO uses la tarjeta visual aquí, habla normal.

Hoy: {hoy} {hora} (España). Mercado: {mercado}

CÓMO HABLAS:
- Lenguaje COLOQUIAL ESPAÑOL DE ESPAÑA. Como en un bar.
- Frases cortas, naturales, en voz alta.
- Usa: "joder", "vaya", "pinta bien", "está jodido", "ojo con esto"
- NUNCA estilo teletipo
- NUNCA listas con bullets para conversar
- Cifras dentro de frases

Si Miki está agobiado, primero le escuchas como amigo. Luego ayudas.

CARTERA: €34.145 +22%. GOOGL +77% (la grande). MSFT -12.5% (vigilar).
VISA nueva. NKE vendida.

LONGITUD:
- Saludo: 1-2 frases
- Pregunta puntual: 2-4 frases
- Conversación: 3-6 frases máximo
"""

# ═════════════════════════════════════════════════════
#  MEMORIA SQLITE + SUPABASE
# ═════════════════════════════════════════════════════
history = {}
memory_lock = threading.Lock()

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
    except: pass

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
                (str(chat_id), key, value[:2000], datetime.utcnow().isoformat()))
            conn.commit(); conn.close()
    except: pass

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
                         m.get("ticker"), m.get("importe_eur"), m.get("asunto"),
                         datetime.utcnow().isoformat()))
                    nuevos.append(m)
            conn.commit(); conn.close()
    except Exception as e: logging.error(f"Persist mov: {e}")
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
#  CLAUDE — Llamada con system dinamico
# ═════════════════════════════════════════════════════
def ask_claude(chat_id, text, system_prompt, web_data="", max_tokens=600):
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
#  GMAIL — MyInvestor + Trade Republic + ING (NUEVO)
# ═════════════════════════════════════════════════════
BROKER_SENDERS = {
    "myinvestor": ["myinvestor.es", "no-reply@myinvestor.es", "info@myinvestor.es"],
    "trade_republic": ["traderepublic.com", "no-reply@traderepublic.com", "noreply@traderepublic.com"],
    "ing": ["ing.es", "info@ing.es", "comunicaciones@ing.es", "noreply@ing.es",
            "ingdirect.es", "info@ingdirect.es", "alerta@ing.es", "alertas@ing.es"],
}
ACTION_KEYWORDS = {
    "VENTA": ["venta ejecutada", "vendido", "sell executed", "sold", "orden de venta"],
    "COMPRA": ["compra ejecutada", "comprado", "buy executed", "bought", "orden de compra", "compra de valores"],
    "DIVIDENDO": ["dividendo", "dividend", "abono de dividendo"],
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
        logging.info("Gmail monitor desactivado")
        return
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
    if not (AUTONOMY_ENABLED and MIKI_CHAT_ID): return
    time.sleep(120)
    while True:
        try:
            datos = get_real_data_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA"])
            prompt = ("Briefing autónomo para Miki como asesor privado. "
                      "Tono colega natural. 6 frases máximo. Una acción concreta para hoy.")
            reply = ask_claude(MIKI_CHAT_ID, prompt, get_system_chat(), web_data=datos, max_tokens=400)
            send(MIKI_CHAT_ID, f"🤖 Briefing autónomo:\n\n{reply}")
        except Exception as e:
            logging.error(f"Autonomy: {e}")
        time.sleep(max(30, AUTONOMY_INTERVAL_MIN) * 60)

# ═════════════════════════════════════════════════════
#  HANDLER PRINCIPAL — SIN COMANDOS, TODO NATURAL
# ═════════════════════════════════════════════════════
def handle(chat_id, text):
    txt = text.strip()
    txt_low = txt.lower()
    hoy = datetime.now().strftime("%d/%m/%Y")

    # Memoria permanente: "recuerda que ..."
    if txt_low.startswith("recuerda que "):
        fact = txt[12:].strip()
        if fact:
            upsert_knowledge(chat_id, f"fact_{int(time.time())}", fact)
            send(chat_id, "Anotado. Lo tendré en cuenta siempre.")
        return

    # Ver Gmail (broker movements)
    gmail_triggers = ["mira mi gmail", "mira gmail", "revisa mi gmail", "revisa gmail",
                      "ve a gmail", "movimientos", "mi cartera ha cambiado", "actualiza mi cartera",
                      "cartera ha cambiado", "mira los correos", "revisa los correos"]
    if any(t in txt_low for t in gmail_triggers):
        typing(chat_id)
        send(chat_id, "Voy a echar un ojo a tu Gmail (MyInvestor + Trade Republic + ING)...")
        movs = fetch_broker_movements(days=15)
        persist_movements(movs)
        send(chat_id, format_movements(movs))
        return

    # Cartera completa
    cartera_triggers = ["mi cartera", "toda la cartera", "todas las posiciones",
                        "como está mi cartera", "cómo está mi cartera"]
    if any(t in txt_low for t in cartera_triggers):
        typing(chat_id)
        send(chat_id, "Voy a sacar precios reales de toda la cartera...")
        datos = get_real_data_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "SSNC", "TXRH", "CELH"])
        prompt = (f"Hoy {hoy}. Cuéntame cómo está mi cartera con esos datos reales. "
                  f"Tono colega natural, 6-8 frases. Mira si MSFT (-12.5%) se ha movido.")
        reply = ask_claude(chat_id, prompt, get_system_chat(), web_data=datos, max_tokens=600)
        send(chat_id, reply)
        return

    # Macro
    macro_triggers = ["macro", "fed ", "inflacion", "inflación", "vix", "dolar", "dólar"]
    if any(t in txt_low for t in macro_triggers) and not detect_ticker(txt):
        typing(chat_id)
        web = search_news("FED tipos inflacion VIX dolar mercados hoy", n=3)
        prompt = f"Cuéntame en lenguaje coloquial cómo está la macro hoy {hoy}."
        reply = ask_claude(chat_id, prompt, get_system_chat(), web_data=web, max_tokens=400)
        send(chat_id, reply)
        audio = tts(reply[:500])
        if audio: send_audio(chat_id, audio)
        return

    # ─── DETECTAR EMPRESA ───
    ticker = detect_ticker(txt)

    if ticker:
        # Si está claramente buscando charla (no datos), responde como colega
        if is_conversational(txt):
            typing(chat_id)
            datos = format_data_for_claude(get_real_data(ticker))
            reply = ask_claude(chat_id, txt, get_system_chat(), web_data=datos, max_tokens=400)
            send(chat_id, reply)
            audio = tts(reply[:500])
            if audio: send_audio(chat_id, audio)
            return

        # POR DEFECTO con un ticker → TARJETA VISUAL CON DATOS REALES
        typing(chat_id)
        datos = format_data_for_claude(get_real_data(ticker))
        prompt = (f"Datos reales de {ticker} hoy {hoy}. "
                  f"Pregunta del usuario: \"{txt}\"\n"
                  f"Responde con la tarjeta visual EXACTA según las reglas del sistema.")
        reply = ask_claude(chat_id, prompt, get_system_card(), web_data=datos, max_tokens=600)
        send(chat_id, reply)
        return

    # ─── CONVERSACIÓN GENERAL (sin empresa concreta) ───
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
#  POLLING
# ═════════════════════════════════════════════════════
def poll():
    offset = 0
    logging.info(f"JARVIS v9 - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
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
        msg = f"JARVIS v9 - {datetime.now().strftime('%d/%m/%Y %H:%M')} - Online (Tarjeta+ING)"
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
            ticker = detect_ticker(msg)
            if ticker and not is_conversational(msg):
                datos = format_data_for_claude(get_real_data(ticker))
                prompt = f"Pregunta usuario: \"{msg}\". Responde con la tarjeta visual."
                reply = ask_claude(chat_id, prompt, get_system_card(), web_data=datos, max_tokens=600)
            else:
                datos = format_data_for_claude(get_real_data(ticker)) if ticker else ""
                reply = ask_claude(chat_id, msg, get_system_chat(), web_data=datos, max_tokens=500)
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

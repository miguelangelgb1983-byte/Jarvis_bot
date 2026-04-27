"""
JARVIS v6 - Asistente Privado de Inversion · Miguel (Miki)
26/04/2026
+ Yahoo Finance: precios reales, PER, FCF, dividendos
+ Comando /miid
+ Audios Whisper
+ Voz ElevenLabs
+ Gmail Skill #10
"""
import os, logging, requests, threading, json, time
import imaplib, email, re, hashlib
from email.header import decode_header
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# Yahoo Finance
import yfinance as yf

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
PORT               = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ════════════════════════════════════════════════════════════════
# YAHOO FINANCE - Tickers de Miki (mapeados a Yahoo)
# ════════════════════════════════════════════════════════════════
TICKER_MAP = {
    "GOOGL": "GOOGL",
    "AAPL":  "AAPL",
    "MSFT":  "MSFT",
    "JNJ":   "JNJ",
    "VISA":  "V",
    "V":     "V",
    "SSNC":  "SSNC",
    "TXRH":  "TXRH",
    "CELH":  "CELH",
    "NKE":   "NKE",
    "MONC":  "MONC.MI",       # Borsa Italiana
    "ZEG":   "ZEG.L",         # London
    "TRET":  "TRET.AS",       # Amsterdam
    "GOLD":  "GC=F",          # Oro futuros
    "8PSG":  "8PSG.L",        # Invesco Gold London
    "SP500": "^GSPC",
    "INDIA": "INDA",          # iShares MSCI India
}

def get_yahoo_data(ticker_input):
    """Devuelve datos reales de Yahoo Finance en formato legible."""
    ticker = TICKER_MAP.get(ticker_input.upper(), ticker_input.upper())
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            return f"Sin datos para {ticker_input}. Quizá ticker incorrecto o mercado cerrado sin histórico."

        precio = info.get("regularMarketPrice") or info.get("currentPrice")
        moneda = info.get("currency", "USD")
        nombre = info.get("longName") or info.get("shortName") or ticker_input
        per = info.get("trailingPE")
        per_fwd = info.get("forwardPE")
        market_cap = info.get("marketCap")
        cambio_dia = info.get("regularMarketChangePercent")
        cierre_ant = info.get("regularMarketPreviousClose")
        max_52 = info.get("fiftyTwoWeekHigh")
        min_52 = info.get("fiftyTwoWeekLow")
        div_yield = info.get("dividendYield")
        roe = info.get("returnOnEquity")
        margen_op = info.get("operatingMargins")
        deuda_eq = info.get("debtToEquity")
        fcf = info.get("freeCashflow")

        # Formato legible
        lines = [f"{nombre} ({ticker})"]
        if precio:
            lines.append(f"Precio: {precio:.2f} {moneda}")
        if cambio_dia is not None:
            lines.append(f"Variación día: {cambio_dia*100:.2f}% (cierre ant: {cierre_ant:.2f})")
        if per:
            per_str = f"PER: {per:.1f}x"
            if per_fwd:
                per_str += f" (forward: {per_fwd:.1f}x)"
            lines.append(per_str)
        if market_cap:
            mc_b = market_cap / 1e9
            lines.append(f"Market cap: {mc_b:.1f}B {moneda}")
        if max_52 and min_52:
            lines.append(f"Rango 52s: {min_52:.2f} - {max_52:.2f}")
        if div_yield:
            lines.append(f"Dividend yield: {div_yield*100:.2f}%")
        if roe:
            lines.append(f"ROE: {roe*100:.1f}%")
        if margen_op:
            lines.append(f"Margen operativo: {margen_op*100:.1f}%")
        if fcf:
            fcf_b = fcf / 1e9
            lines.append(f"Free Cash Flow: {fcf_b:.1f}B {moneda}")
        if deuda_eq:
            lines.append(f"Deuda/Equity: {deuda_eq:.1f}")

        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Yahoo {ticker}: {e}")
        return f"Error obteniendo datos de {ticker_input}: {e}"

def get_yahoo_multi(tickers_list):
    """Obtiene datos de varios tickers para preguntas tipo cartera."""
    out = []
    for t in tickers_list:
        d = get_yahoo_data(t)
        out.append(f"=== {t} ===\n{d}")
    return "\n\n".join(out)

# ════════════════════════════════════════════════════════════════
# DETECTOR MERCADO
# ════════════════════════════════════════════════════════════════
def market_status_human():
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    hour_utc = now.hour
    dia_es = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo'][weekday]
    if weekday == 5:
        return "HOY ES SÁBADO - todos los mercados cerrados"
    if weekday == 6:
        return "HOY ES DOMINGO - todos los mercados cerrados"
    nyse_open = 13 <= hour_utc < 20
    eu_open = 7 <= hour_utc < 16
    if nyse_open and eu_open:
        return f"Es {dia_es}. NYSE y Europa abiertas."
    if eu_open and not nyse_open:
        return f"Es {dia_es}. Europa abierta. NYSE abre 15:30 España."
    if not eu_open and nyse_open:
        return f"Es {dia_es}. NYSE abierta. Europa ya cerró."
    if hour_utc < 7:
        return f"Es {dia_es} pre-mercado."
    return f"Es {dia_es}, fuera de horario."

# ════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ════════════════════════════════════════════════════════════════
def get_system():
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercado = market_status_human()
    return f"""Eres JARVIS, el colega de Miki para temas de inversión.
Hablas como un amigo que sabe mucho de bolsa, no como un manual ni un informe.

CÓMO HABLAS:
- Lenguaje COLOQUIAL ESPAÑOL DE ESPAÑA. Como hablaríais en un bar.
- Frases cortas. Naturales. Como si lo dijeras en voz alta.
- NADA de "INFLACIÓN USA ESTANCADA - FED TASAS ALTAS" - eso es un teletipo.
- En vez: "La inflación en USA sigue atascada y la FED no baja tipos."
- Usa: "joder", "vaya", "pinta bien", "está jodido", "ojo con esto"
- NUNCA listas con bullets para conversar
- Las cifras van metidas en frases, no como datos sueltos

CONTEXTO ACTUAL:
Fecha: {hoy} - {hora} (España)
Mercado: {mercado}

Si Miki pregunta "cómo está el mercado" un sábado/domingo, NO le pidas confirmación,
díselo directo: "Miki, estamos a sábado, los mercados están cerrados."

DATOS:
- Si te paso DATOS_YAHOO en el mensaje, son REALES de Yahoo Finance ahora mismo. Úsalos sin dudar.
- Esos datos son PRECIO ACTUAL VERIFICADO. No los pongas en duda.
- NUNCA inventes precios. Si no tienes el dato: "no lo tengo verificado ahora, deja que mire"

CARTERA MIKI - €34.145 - +22%:
GANANDO: GOOGL +77% (la grande, 17.8%), JNJ +61%, ZEG +71%, Gold +42%
PERDIENDO: MSFT -12.5% (earnings 29/04), MONC -3.8%, India -7.4%
NUEVA: VISA (€637, earnings 28/04)
VENDIDA: NKE
Core: SP500, Europe, SmCap (todas +23-24%)

VALUE INVESTING:
FCF > EBITDA. Margen seguridad min 30%. DCF NO para tech.
Council: Buffett, Lynch, Klarman, Munger.

CUÁNDO USAR FORMATO TÉCNICO:
Solo cuando Miki use /analiza o /consejo. En conversación libre RESPONDE NATURAL.

LONGITUD:
- Saludo: 1-2 frases
- Pregunta puntual: 2-4 frases
- Conversación con datos: 3-6 frases
- Análisis formal solo si pide: hasta 10 líneas

Si Miki parece agobiado, primero le escuchas como amigo. Luego ayudas.
"""

# ════════════════════════════════════════════════════════════════
# MEMORIA SUPABASE
# ════════════════════════════════════════════════════════════════
history = {}

def save_memory(chat_id, role, content):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"chat_id": str(chat_id), "role": role,
                  "content": content[:1000], "created_at": datetime.utcnow().isoformat()},
            timeout=5)
    except: pass

def load_memory(chat_id, limit=8):
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"chat_id": f"eq.{chat_id}", "order": "created_at.desc", "limit": limit},
            timeout=5)
        rows = r.json()
        return [{"role": x["role"], "content": x["content"]} for x in reversed(rows)] \
            if isinstance(rows, list) else []
    except: return []

# ════════════════════════════════════════════════════════════════
# TAVILY - Solo para noticias (precios siempre Yahoo)
# ════════════════════════════════════════════════════════════════
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

# ════════════════════════════════════════════════════════════════
# CLAUDE
# ════════════════════════════════════════════════════════════════
def ask_claude(chat_id, text, web_data="", max_tokens=600):
    mem = load_memory(chat_id, limit=6)
    if chat_id not in history: history[chat_id] = []
    hoy = datetime.now().strftime("%d/%m/%Y")
    content = f"{text}\n\nDATOS_YAHOO ({hoy}):\n{web_data}" if web_data else text
    history[chat_id].append({"role": "user", "content": content})
    all_msgs = mem + history[chat_id][-6:]
    msgs = []
    last_role = None
    for m in all_msgs:
        if m["role"] != last_role:
            msgs.append(m)
            last_role = m["role"]
        else:
            msgs[-1]["content"] = m["content"]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": text}]
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

# ════════════════════════════════════════════════════════════════
# ELEVENLABS + WHISPER + TELEGRAM
# ════════════════════════════════════════════════════════════════
def tts(text):
    if not ELEVENLABS_KEY: return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            json={"text": text[:500], "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=30)
        return r.content if r.status_code == 200 else None
    except: return None

def transcribe_voice(file_id):
    if not OPENAI_KEY: return None
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
                         params={"file_id": file_id}, timeout=10)
        file_path = r.json()["result"]["file_path"]
        audio_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        audio = requests.get(audio_url, timeout=30).content
        r = requests.post("https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files={"file": ("voice.ogg", audio, "audio/ogg")},
            data={"model": "whisper-1", "language": "es"}, timeout=60)
        if r.status_code == 200:
            return r.json().get("text", "")
        return None
    except Exception as e:
        logging.error(f"Whisper: {e}")
        return None

def send(chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": chat_id, "text": text[:4000]}, timeout=10)
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

# ════════════════════════════════════════════════════════════════
# GMAIL SKILL #10
# ════════════════════════════════════════════════════════════════
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
    if m: return m.group(1)
    return None

def _extract_amount(text):
    m = re.search(r"([\d]+(?:[.,]\d{1,2})?)\s*EUR", text)
    if m:
        try: return float(m.group(1).replace(",", "."))
        except: return None
    return None

def fetch_broker_movements(days=7):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD):
        return [{"error": "GMAIL_USER o GMAIL_APP_PASSWORD no configurados"}]
    movements = []
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
                    movements.append({
                        "broker": broker, "fecha": msg.get("Date", ""),
                        "asunto": subject[:120], "accion": action,
                        "ticker": _extract_ticker_email(full),
                        "importe_eur": _extract_amount(full),
                    })
        mail.close()
        mail.logout()
    except Exception as e:
        return [{"error": f"Gmail: {e}"}]
    return movements

def format_movements(movements):
    if not movements:
        return "Tranquilo, no he visto movimientos en tu Gmail los últimos 7 días."
    if movements and "error" in movements[0]:
        return f"Tengo un problema con Gmail: {movements[0]['error']}"
    lines = [f"He detectado {len(movements)} cosas en tu Gmail:"]
    for m in movements[:10]:
        ticker = m.get("ticker") or "?"
        imp = m.get("importe_eur")
        imp_s = f" por {imp:.0f} EUR" if imp else ""
        b = "MyInvestor" if m["broker"] == "myinvestor" else "Trade Republic"
        lines.append(f"- {b}: {m['accion'].lower()} de {ticker}{imp_s}")
    return "\n".join(lines)

def gmail_monitor_loop():
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and MIKI_CHAT_ID):
        return
    time.sleep(60)
    while True:
        try:
            movs = fetch_broker_movements(days=2)
            if movs and "error" not in movs[0]:
                msg = "Oye Miki, mira lo que ha llegado a tu Gmail:\n\n"
                msg += format_movements(movs)
                send(MIKI_CHAT_ID, msg)
        except: pass
        time.sleep(1800)

# ════════════════════════════════════════════════════════════════
# DETECCIÓN AUTO DE TICKER EN TEXTO
# ════════════════════════════════════════════════════════════════
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
    "GOLD":  ["oro", "gold"],
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

# ════════════════════════════════════════════════════════════════
# HANDLER
# ════════════════════════════════════════════════════════════════
def handle(chat_id, text):
    txt = text.strip()
    hoy = datetime.now().strftime("%d/%m/%Y")
    parts = txt.split()
    cmd = parts[0].lower() if txt.startswith("/") else None

    if cmd == "/miid":
        send(chat_id, f"Tu chat ID es: {chat_id}")
        return

    if cmd == "/start":
        send(chat_id,
             f"Buenas Miki, son las {datetime.now().strftime('%H:%M')} del {hoy}.\n\n"
             "Pregúntame lo que quieras como si me lo dijeras a la cara.\n\n"
             "Comandos: /cartera /alertas /earnings /macro /salud\n"
             "/analiza TICKER /consejo TICKER /movimientos /memoria /miid")
        return

    if cmd == "/cartera":
        send(chat_id, "Voy a coger los precios actuales de toda la cartera...")
        typing(chat_id)
        tickers_principales = ["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "MONC", "SSNC", "TXRH", "ZEG", "CELH"]
        datos = get_yahoo_multi(tickers_principales)
        prompt = (f"Cuéntale a Miki cómo está su cartera HOY {hoy} de forma natural. "
                  f"Usa los precios reales que te paso. Resume en 5-6 líneas máximo. "
                  f"Mira si las posiciones perdedoras se han movido.")
        reply = ask_claude(chat_id, prompt, web_data=datos, max_tokens=500)
        send(chat_id, reply)
        return

    if cmd == "/alertas":
        send(chat_id,
             f"Te recuerdo lo que tienes encima - {hoy}\n\n"
             "MSFT en -12.5% y earnings el 29.\n"
             "MONC -3.8%, post-earnings.\n"
             "India -7.4%, presionada por macro.\n"
             "VISA es nueva, earnings el 28.")
        return

    if cmd == "/movimientos":
        typing(chat_id)
        send(chat_id, "Voy a echar un ojo a tu Gmail...")
        movs = fetch_broker_movements(days=7)
        send(chat_id, format_movements(movs))
        return

    if cmd == "/analiza":
        if len(parts) < 2:
            send(chat_id, "Dime un ticker - /analiza VISA")
            return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Voy a por {ticker}...")
        datos = get_yahoo_data(ticker)
        prompt = (f"Análisis técnico completo de {ticker} hoy {hoy}. "
                  f"Usa los datos reales de Yahoo que te paso. "
                  f"Formato técnico con métricas. "
                  f"Si es posición de Miki, contextualiza en cartera al final.")
        reply = ask_claude(chat_id, prompt, web_data=datos, max_tokens=700)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/consejo":
        if len(parts) < 2:
            send(chat_id, "Dime un ticker - /consejo VISA")
            return
        ticker = parts[1].upper()
        typing(chat_id)
        datos = get_yahoo_data(ticker)
        prompt = (f"Consejo profundo sobre {ticker} hoy {hoy}. "
                  f"Usa datos reales que te paso. "
                  f"Council: Buffett, Lynch, Klarman, Munger. "
                  f"Cada uno SI/NO con razón natural.")
        reply = ask_claude(chat_id, prompt, web_data=datos, max_tokens=800)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/earnings":
        send(chat_id,
             f"Earnings próximos en tu cartera:\n\n"
             "VISA - 28/04/2026 (martes)\n"
             "MSFT - 29/04/2026 (miércoles)\n\n"
             "MONC ya reportó el 21/04 - revisa si quieres comentar reacción.")
        return

    if cmd == "/macro":
        typing(chat_id)
        web = search_news("FED tipos inflacion VIX dolar mercados hoy", n=3)
        prompt = f"Cuéntame en lenguaje coloquial cómo está el mercado hoy {hoy}."
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=400)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/salud":
        typing(chat_id)
        prompt = (f"Cuéntale a Miki cómo está su cartera hoy {hoy} a vista general. "
                  f"Concentración (GOOGL 17.8%), sectorial, alpha vs SP500. Tono natural.")
        reply = ask_claude(chat_id, prompt, max_tokens=600)
        send(chat_id, reply)
        return

    if cmd == "/memoria":
        mem = load_memory(chat_id, limit=6)
        if mem:
            lines = [f"{m['role'].upper()}: {m['content'][:140]}..." for m in mem]
            send(chat_id, "Lo último que recordamos:\n\n" + "\n\n".join(lines))
        else:
            send(chat_id, "Aún no he guardado nada.")
        return

    # ─── CONVERSACIÓN LIBRE ──────────────────────────────────────
    typing(chat_id)
    txt_low = txt.lower()
    datos = ""

    # 1. ¿Menciona un ticker concreto? -> Yahoo Finance
    ticker_detected = detect_ticker(txt)
    if ticker_detected:
        datos = get_yahoo_data(ticker_detected)

    # 2. ¿Pregunta por toda la cartera? -> Yahoo de las principales
    elif any(p in txt_low for p in ["cartera", "todas las posiciones", "per de mi", "per medio"]):
        datos = get_yahoo_multi(["GOOGL", "MSFT", "AAPL", "JNJ", "VISA", "MONC"])

    # 3. ¿Pregunta macro? -> Tavily noticias
    elif any(p in txt_low for p in ["macro", "fed", "inflacion", "vix", "dolar", "mercado"]):
        datos = search_news("FED inflacion VIX dolar mercados hoy", n=2)

    reply = ask_claude(chat_id, txt, web_data=datos, max_tokens=600)
    send(chat_id, reply)
    if len(reply) > 60:
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)

def handle_voice(chat_id, file_id):
    typing(chat_id)
    if not OPENAI_KEY:
        send(chat_id, "Necesito OPENAI_API_KEY en Render para Whisper. Escríbeme texto.")
        return
    text = transcribe_voice(file_id)
    if not text:
        send(chat_id, "No te he pillado bien la nota. Repítela o escríbela.")
        return
    send(chat_id, f"Te he entendido: \"{text}\"")
    handle(chat_id, text)

# ════════════════════════════════════════════════════════════════
# POLLING
# ════════════════════════════════════════════════════════════════
def poll():
    offset = 0
    logging.info(f"JARVIS v6 - {datetime.now().strftime('%d/%m/%Y %H:%M')} - Yahoo Finance ON")
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
                    threading.Thread(target=handle_voice,
                                     args=(cid, voice["file_id"]), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        msg = f"JARVIS v6 - {datetime.now().strftime('%d/%m/%Y %H:%M')} - Online (Yahoo)"
        self.wfile.write(msg.encode("utf-8"))

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()

    def log_message(self, *a): pass

threading.Thread(target=poll, daemon=True).start()
threading.Thread(target=gmail_monitor_loop, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), H).serve_forever()

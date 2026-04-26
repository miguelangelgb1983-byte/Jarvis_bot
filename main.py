"""
╔══════════════════════════════════════════════════════════════════════╗
║   JARVIS v5 — Asistente Privado de Inversión · Miguel (Miki)        ║
║   26/04/2026                                                         ║
║                                                                      ║
║   ✅ Conversación humana — habla como un colega, no como informe    ║
║   ✅ Procesa notas de voz (Whisper API OpenAI)                       ║
║   ✅ Voz salida ElevenLabs                                           ║
║   ✅ 10 comandos rápidos                                             ║
║   ✅ Memoria conversacional (Supabase + RAM)                         ║
║   ✅ Datos reales Tavily                                             ║
║   ✅ Detector mercado abierto/cerrado — AVISA SIN PREGUNTAR          ║
║   ✅ do_HEAD añadido — UptimeRobot 24/7                              ║
║   ✅ SKILL #10 Gmail Broker Monitor                                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, logging, requests, threading, json, time
import imaplib, email, re, hashlib
from email.header import decode_header
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

# ─── ENV VARS ───────────────────────────────────────────────────────
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY      = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_KEY         = os.environ.get("TAVILY_KEY")
SUPABASE_URL       = os.environ.get("SUPABASE_URL")
SUPABASE_KEY       = os.environ.get("SUPABASE_KEY")
ELEVENLABS_KEY     = os.environ.get("ELEVENLABS_KEY")
ELEVENLABS_VOICE   = "htFfPSZGJwjBv1CL0aMD"
OPENAI_KEY         = os.environ.get("OPENAI_API_KEY")  # Para Whisper (audios)
GMAIL_USER         = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
MIKI_CHAT_ID       = os.environ.get("MIKI_CHAT_ID")
PORT               = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ════════════════════════════════════════════════════════════════════════
#  DETECTOR MERCADO — Genera string que entra al system prompt
# ════════════════════════════════════════════════════════════════════════
def market_status_human():
    """Versión 'humana' del estado del mercado para meter en system prompt."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    hour_utc = now.hour
    dia_es = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo'][weekday]

    if weekday == 5:
        return f"HOY ES SÁBADO — todos los mercados cerrados. Bolsas reabren lunes."
    if weekday == 6:
        return f"HOY ES DOMINGO — todos los mercados cerrados. Bolsas reabren mañana lunes."

    nyse_open = 13 <= hour_utc < 20
    eu_open = 7 <= hour_utc < 16

    if nyse_open and eu_open:
        return f"Es {dia_es}. NYSE y Europa abiertas ahora mismo."
    if eu_open and not nyse_open:
        return f"Es {dia_es}. Europa abierta. NYSE abre a las 15:30 hora española."
    if not eu_open and nyse_open:
        return f"Es {dia_es}. NYSE abierta. Europa ya cerró (cierra 17:30 España)."
    if hour_utc < 7:
        return f"Es {dia_es} pero pre-mercado — Europa abre a las 9:00 España, NYSE a las 15:30."
    return f"Es {dia_es}, fuera de horario — Europa cerró 17:30, NYSE cierra 22:00 España."


# ════════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT — JARVIS habla como Miki habla
# ════════════════════════════════════════════════════════════════════════
def get_system():
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercado = market_status_human()

    return f"""Eres JARVIS, el colega de Miki para temas de inversión.
Hablas como un amigo que sabe mucho de bolsa, no como un manual ni un informe.

═══════════════════════════════════════════
CÓMO HABLAS — ESTO ES LO MÁS IMPORTANTE:
═══════════════════════════════════════════
- Lenguaje COLOQUIAL ESPAÑOL DE ESPAÑA. Como hablaríais en un bar.
- Frases cortas. Naturales. Como si lo dijeras en voz alta.
- NADA de "INFLACIÓN USA ESTANCADA · FED TASAS ALTAS · IMPACTO CARTERA" — eso es un teletipo, no una conversación.
- En vez de eso: "La inflación en USA sigue atascada y la FED no baja tipos. A tu cartera le toca el oro (que va volando, +41%) pero el dólar fuerte te jode las posiciones americanas."
- Usa palabras tuyas: "joder", "vaya", "pinta bien", "está jodido", "pinta mal", "tranquilo", "ojo con esto"
- Conecta ideas con "porque", "así que", "fíjate", "mira", "lo que pasa es que"
- NUNCA listas con bullets ni guiones para conversar
- NUNCA mayúsculas tipo titular de prensa
- Las cifras van metidas en frases, no como datos sueltos: "Apple cotiza a 30 veces beneficios, alto pero no loco"

═══════════════════════════════════════════
CONTEXTO ACTUAL (para que NO preguntes lo obvio):
═══════════════════════════════════════════
Fecha y hora: {hoy} · {hora} (España)
Mercado: {mercado}

⚠️ IMPORTANTE: Si Miki pregunta "cómo está el mercado" un sábado/domingo, NO le pidas confirmación — díselo directamente: "Miki, estamos a sábado, los mercados están cerrados. El último cierre fue ayer viernes…"

═══════════════════════════════════════════
DATOS Y NÚMEROS:
═══════════════════════════════════════════
- Si te paso DATOS_WEB en el mensaje, son reales del día. Úsalos.
- NUNCA inventes precios, PER, FCF, ROIC.
- Si no tienes el dato verificado: dilo coloquial — "no tengo el dato actualizado, deja que mire" o "ahora mismo no te puedo decir el precio exacto"

═══════════════════════════════════════════
SOBRE LA CARTERA DE MIKI (tú la conoces, no se la repitas como una lista):
═══════════════════════════════════════════
Total: €34.145 — va +22% vs entrada
GANADORAS: GOOGL +77% (es la grande, 17.8%), JNJ +61%, ZEG +71%, Gold +42%
PERDIENDO: MSFT -12.5% (earnings 29/04), MONC -3.8% (post-earnings), India -7.4%
NUEVA: VISA (€637, comprada hace poco, earnings 28/04, sin análisis profundo)
VENDIDA: NKE (-42%, decisión correcta, tesis rota)
Core: SP500, Europe, SmCap (todas en verde +23-24%)

═══════════════════════════════════════════
VALUE INVESTING (filosofía Miki, no la expliques):
═══════════════════════════════════════════
FCF > EBITDA. Margen seguridad mínimo 30%. DCF NO para tech (usa EV/FCF).
Directiva = 40-80% del éxito. Council: Buffett · Lynch · Klarman · Munger.

Cuando Miki te pida "consejo profundo" sobre algo, sí estructura como Council.
Cuando Miki te pida "análisis", da el formato técnico con métricas.
Cuando conversa contigo, NUNCA estructura — habla.

═══════════════════════════════════════════
CUÁNDO USAR FORMATO TÉCNICO:
═══════════════════════════════════════════
Solo cuando Miki use comandos /analiza /consejo o pida explícitamente un análisis técnico.
En conversación libre — incluso preguntando por números — RESPONDE NATURAL.

Ejemplo BUENO de respuesta natural:
Miki: "qué tal va MSFT?"
Tú: "Sigue jodida, Miki. Está -12.5% desde tu entrada y los earnings son el 29. La tesis de Azure es lo que hay que mirar, si decepciona ahí toca recortar. Por ahora vigilar."

Ejemplo MALO (no hagas esto):
Tú: "MSFT — 26/04/2026
Precio: $X | PER: Xx
Señal: VIGILAR
Motivo: ..."

═══════════════════════════════════════════
LONGITUD:
═══════════════════════════════════════════
- Saludo: 1-2 frases
- Pregunta puntual: 2-4 frases
- Conversación con datos: 3-6 frases
- Análisis formal (solo si lo pide explícitamente): hasta 10 líneas con formato

═══════════════════════════════════════════
SI MIKI PARECE AGOBIADO O ENFADADO:
═══════════════════════════════════════════
Primero le escuchas como un amigo. Luego ayudas. NUNCA contestes con datos cuando está desahogándose.
"""

# ════════════════════════════════════════════════════════════════════════
#  MEMORIA CONVERSACIONAL
# ════════════════════════════════════════════════════════════════════════
history = {}

def save_memory(chat_id, role, content):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={
                "chat_id": str(chat_id), "role": role,
                "content": content[:1000],
                "created_at": datetime.utcnow().isoformat()
            },
            timeout=5
        )
    except Exception as e:
        logging.warning(f"Supabase save: {e}")

def load_memory(chat_id, limit=8):
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"chat_id": f"eq.{chat_id}", "order": "created_at.desc", "limit": limit},
            timeout=5
        )
        rows = r.json()
        return [{"role": x["role"], "content": x["content"]} for x in reversed(rows)] \
            if isinstance(rows, list) else []
    except:
        return []

# ════════════════════════════════════════════════════════════════════════
#  TAVILY
# ════════════════════════════════════════════════════════════════════════
TICKER_QUERIES = {
    "GOOGL": "Alphabet Google GOOGL stock price PER FCF earnings today",
    "AAPL":  "Apple AAPL stock price PER FCF earnings today",
    "MSFT":  "Microsoft MSFT stock price PER FCF Azure earnings today",
    "MONC":  "Moncler MONC azione prezzo PER FCF oggi Borsa Italia",
    "JNJ":   "Johnson Johnson JNJ stock price PER FCF dividend today",
    "VISA":  "Visa V stock price PER FCF earnings today",
    "ZEG":   "Zegona Communications ZEG stock price London today",
    "SSNC":  "SSC Technologies SSNC stock price PER FCF today",
    "TXRH":  "Texas Roadhouse TXRH stock price PER FCF today",
    "CELH":  "Celsius Holdings CELH stock price PER today",
    "TRET":  "VanEck Real Estate TRET ETF price NAV FFO today",
    "GOLD":  "Gold XAU price today spot per ounce",
    "8PSG":  "Invesco Physical Gold ETC 8PSG price London today",
    "NKE":   "Nike NKE stock price today",
    "SP500": "SP500 S&P500 index price today",
    "INDIA": "iShares MSCI India ETF price today",
}

def search(query, n=3):
    if not TAVILY_KEY: return ""
    mes = datetime.now().strftime("%B %Y")
    try:
        r = requests.post("https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": f"{query} {mes}",
                  "max_results": n, "search_depth": "basic"}, timeout=12)
        return "\n".join([
            f"[{x['url'].split('/')[2]}] {x['title']}: {x['content'][:220]}"
            for x in r.json().get("results", [])[:n]
        ])
    except:
        return ""

def search_ticker(ticker):
    q = TICKER_QUERIES.get(ticker.upper(), f"{ticker} stock price PER FCF today")
    return search(q, n=3)

def search_cartera():
    w1 = search("GOOGL MSFT AAPL JNJ VISA PER price FCF today stock", n=3)
    w2 = search("Moncler MONC SSNC TXRH CELH ZEG PER price today", n=2)
    return w1 + "\n" + w2

# ════════════════════════════════════════════════════════════════════════
#  CLAUDE API
# ════════════════════════════════════════════════════════════════════════
def ask_claude(chat_id, text, web_data="", max_tokens=600):
    mem = load_memory(chat_id, limit=6)
    if chat_id not in history: history[chat_id] = []
    hoy = datetime.now().strftime("%d/%m/%Y")
    content = f"{text}\n\nDATOS_WEB ({hoy}):\n{web_data}" if web_data else text
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
                  "system": get_system(), "messages": msgs},
            timeout=45)
        data = r.json()
        if "error" in data:
            logging.error(f"Claude: {data['error']}")
            return f"Vaya, problema con la API: {data['error'].get('message','')[:100]}."
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text[:600])
        save_memory(chat_id, "assistant", reply[:600])
        return reply
    except Exception as e:
        logging.error(f"Claude: {e}")
        return "Sin conexión con la API. Pruébalo en 30 segundos."

# ════════════════════════════════════════════════════════════════════════
#  ELEVENLABS — Voz salida
# ════════════════════════════════════════════════════════════════════════
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
    except:
        return None

# ════════════════════════════════════════════════════════════════════════
#  WHISPER — Transcripción de notas de voz de Miki (entrada)
# ════════════════════════════════════════════════════════════════════════
def transcribe_voice(file_id):
    """Descarga la nota de voz de Telegram y la pasa a Whisper API."""
    if not OPENAI_KEY:
        logging.warning("OPENAI_API_KEY no configurada — audios no procesados")
        return None
    try:
        # 1. Pide la URL del archivo a Telegram
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
            params={"file_id": file_id}, timeout=10
        )
        file_path = r.json()["result"]["file_path"]

        # 2. Descarga el OGG
        audio_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        audio = requests.get(audio_url, timeout=30).content

        # 3. Manda a Whisper API
        r = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files={"file": ("voice.ogg", audio, "audio/ogg")},
            data={"model": "whisper-1", "language": "es"},
            timeout=60
        )
        if r.status_code == 200:
            text = r.json().get("text", "")
            logging.info(f"Whisper transcribió: {text[:80]}")
            return text
        else:
            logging.error(f"Whisper error {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        logging.error(f"Whisper exception: {e}")
        return None

# ════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ════════════════════════════════════════════════════════════════════════
def send(chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": chat_id, "text": text[:4000]}, timeout=10)
    except Exception as e:
        logging.error(f"send: {e}")

def send_audio(chat_id, audio):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice",
                      files={"voice": ("j.mp3", audio, "audio/mpeg")},
                      data={"chat_id": chat_id}, timeout=30)
    except:
        pass

def typing(chat_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except:
        pass


# ════════════════════════════════════════════════════════════════════════
#  ════════════ SKILL #10 — GMAIL BROKER MONITOR ════════════
# ════════════════════════════════════════════════════════════════════════
BROKER_SENDERS = {
    "myinvestor": ["myinvestor.es", "no-reply@myinvestor.es",
                   "info@myinvestor.es", "notificaciones@myinvestor.es"],
    "trade_republic": ["traderepublic.com", "no-reply@traderepublic.com",
                       "noreply@traderepublic.com", "support@traderepublic.com"],
}

ACTION_KEYWORDS = {
    "VENTA":     ["venta ejecutada", "orden de venta", "vendido", "has vendido",
                  "sell executed", "sell order", "sold", "venta"],
    "COMPRA":    ["compra ejecutada", "orden de compra", "comprado", "has comprado",
                  "buy executed", "buy order", "bought", "purchase", "compra"],
    "DIVIDENDO": ["dividendo", "dividend", "reparto de dividendos", "payout"],
    "INGRESO":   ["ingreso recibido", "transferencia recibida", "deposit received",
                  "deposit", "ingreso"],
    "RETIRADA":  ["retirada", "withdrawal", "transferencia enviada", "reembolso"],
    "AJUSTE":    ["split", "fusión", "spin-off", "corporate action"],
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
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition") or "")
            if "attachment" in cd: continue
            if ct in ("text/plain", "text/html"):
                try:
                    raw = part.get_payload(decode=True)
                    if raw: body += raw.decode(errors="ignore")
                except: pass
    else:
        try:
            raw = msg.get_payload(decode=True)
            if raw: body = raw.decode(errors="ignore")
        except: body = ""
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body)
    return body

def _classify(text):
    t = text.lower()
    for action, kws in ACTION_KEYWORDS.items():
        if any(k in t for k in kws):
            return action
    return None

def _extract_ticker(text):
    m = re.search(r"\(([A-Z]{1,5})\)", text)
    if m: return m.group(1)
    m = re.search(r"(?:ticker|s[ií]mbolo|symbol)[:\s]+([A-Z]{1,5})", text, re.I)
    if m: return m.group(1).upper()
    m = re.search(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b", text)
    if m: return m.group(1)
    return None

def _extract_amount(text):
    patterns = [
        r"([\d]{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s*€",
        r"€\s*([\d]{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?)",
        r"([\d]+(?:[.,]\d{1,2})?)\s*EUR",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
            try:
                val = float(raw)
                if 0.01 <= val <= 10_000_000: return val
            except: continue
    return None

def fetch_broker_movements(days=7, max_per_sender=25):
    if not (GMAIL_USER and GMAIL_APP_PASSWORD):
        return [{"error": "GMAIL_USER o GMAIL_APP_PASSWORD no configurados"}]
    movements = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")
        date_since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        seen_ids = set()
        for broker, senders in BROKER_SENDERS.items():
            for sender in senders:
                status, data = mail.search(None, f'(FROM "{sender}" SINCE {date_since})')
                if status != "OK" or not data or not data[0]: continue
                ids = data[0].split()[-max_per_sender:]
                for eid in ids:
                    if eid in seen_ids: continue
                    seen_ids.add(eid)
                    status, msg_data = mail.fetch(eid, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]: continue
                    msg = email.message_from_bytes(msg_data[0][1])
                    subject = _gmail_decode(msg.get("Subject"))
                    sender_addr = _gmail_decode(msg.get("From"))
                    date_str = msg.get("Date", "")
                    body = _gmail_body(msg)
                    full_text = f"{subject}\n{body}"
                    action = _classify(full_text)
                    if not action: continue
                    movements.append({
                        "broker": broker, "fecha": date_str,
                        "asunto": subject[:120], "accion": action,
                        "ticker": _extract_ticker(full_text),
                        "importe_eur": _extract_amount(full_text),
                        "remitente": sender_addr,
                    })
        mail.close()
        mail.logout()
    except imaplib.IMAP4.error as e:
        return [{"error": f"Login Gmail falló: {e}"}]
    except Exception as e:
        return [{"error": f"Gmail IMAP: {e}"}]
    movements.sort(key=lambda m: m["fecha"], reverse=True)
    return movements

def format_movements(movements):
    if not movements:
        return "Tranquilo, no he visto movimientos en tu Gmail los últimos 7 días."
    if movements and "error" in movements[0]:
        return f"Tengo un problema con Gmail: {movements[0]['error']}"
    lines = [f"Mira lo que he detectado en tu Gmail ({len(movements)} cosas):"]
    for m in movements[:10]:
        ticker = m.get("ticker") or "?"
        imp = m.get("importe_eur")
        imp_s = f" por {imp:.0f}€" if imp else ""
        b = "MyInvestor" if m["broker"] == "myinvestor" else "Trade Republic"
        lines.append(f"• {b}: {m['accion'].lower()} de {ticker}{imp_s}")
    return "\n".join(lines)

def save_movement_supabase(mov):
    if not SUPABASE_URL or not SUPABASE_KEY: return False
    h = hashlib.md5(
        f"{mov['broker']}{mov['fecha']}{mov['asunto']}{mov['accion']}".encode()
    ).hexdigest()
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/movimientos_brokers",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hash": f"eq.{h}", "select": "hash"}, timeout=5
        )
        if r.status_code == 200 and r.json():
            return False
        requests.post(
            f"{SUPABASE_URL}/rest/v1/movimientos_brokers",
            headers={"apikey": SUPABASE_KEY,
                     "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json",
                     "Prefer": "return=minimal"},
            json={**mov, "hash": h}, timeout=5
        )
        return True
    except Exception as e:
        logging.warning(f"Supabase mov save: {e}")
        return False

def gmail_monitor_loop():
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and MIKI_CHAT_ID):
        logging.info("Gmail monitor desactivado (faltan vars)")
        return
    logging.info("Gmail monitor activo — revisará cada 30 min")
    time.sleep(60)
    while True:
        try:
            movements = fetch_broker_movements(days=2)
            if movements and "error" not in movements[0]:
                nuevos = []
                for m in movements:
                    if save_movement_supabase(m):
                        nuevos.append(m)
                if nuevos:
                    msg = "Oye Miki, mira lo que ha llegado a tu Gmail:\n\n"
                    msg += format_movements(nuevos)
                    msg += "\n\n¿Quieres que lo añada a tu cartera o analice algo?"
                    send(MIKI_CHAT_ID, msg)
                    logging.info(f"Avisado: {len(nuevos)} movimientos nuevos")
        except Exception as e:
            logging.error(f"Gmail loop: {e}")
        time.sleep(1800)


# ════════════════════════════════════════════════════════════════════════
#  HANDLER PRINCIPAL
# ════════════════════════════════════════════════════════════════════════
def handle(chat_id, text):
    txt = text.strip()
    hoy = datetime.now().strftime("%d/%m/%Y")
    parts = txt.split()
    cmd = parts[0].lower() if txt.startswith("/") else None

    if cmd == "/start":
        send(chat_id,
             f"Buenas Miki, qué tal — son las {datetime.now().strftime('%H:%M')} del {hoy}.\n\n"
             "Pregúntame lo que quieras como si me lo dijeras a la cara. "
             "Por texto, por audio, lo que prefieras.\n\n"
             "Comandos rápidos si los necesitas:\n"
             "/cartera /alertas /earnings /macro /salud\n"
             "/analiza TICKER · /consejo TICKER\n"
             "/movimientos · /memoria")
        return

    if cmd == "/cartera":
        send(chat_id,
             f"Tu cartera a {hoy} — €34.145, +22% vs entrada\n\n"
             "GANANDO bien:\n"
             "GOOGL +77% (la grande, 17.8%)\n"
             "ZEG +71%\n"
             "JNJ +61%\n"
             "Gold +42%\n\n"
             "PERDIENDO:\n"
             "MSFT -12.5% (earnings 29/04)\n"
             "MONC -3.8% (post-earnings)\n"
             "India -7.4%\n\n"
             "Nueva: VISA (€637, earnings 28/04)\n"
             "Vendida: NKE")
        return

    if cmd == "/alertas":
        send(chat_id,
             f"Te recuerdo lo que tienes encima — {hoy}\n\n"
             "MSFT en -12.5% y earnings el 29. Toca decidir si Azure aguanta.\n"
             "MONC -3.8%, post-earnings, mira reacción.\n"
             "India -7.4%, sigue presionada por macro emergentes.\n"
             "VISA es nueva, earnings el 28, sin análisis profundo todavía.")
        return

    if cmd == "/movimientos":
        typing(chat_id)
        send(chat_id, "Voy a echar un ojo a tu Gmail…")
        movs = fetch_broker_movements(days=7)
        send(chat_id, format_movements(movs))
        return

    if cmd == "/analiza":
        if len(parts) < 2:
            send(chat_id, "Dime un ticker — /analiza VISA por ejemplo.")
            return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Voy a por {ticker}…")
        web = search_ticker(ticker)
        prompt = (f"Análisis técnico completo de {ticker} hoy {hoy}. "
                  f"Aquí SÍ usa formato técnico con métricas (precio, PER actual vs histórico, "
                  f"FCF, ROIC, EV/FCF, valor intrínseco, margen seguridad, red flags, señal). "
                  f"Si es posición de Miki, contextualiza en su cartera al final con tono natural.")
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=700)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/consejo":
        if len(parts) < 2:
            send(chat_id, "Dime un ticker — /consejo VISA por ejemplo.")
            return
        ticker = parts[1].upper()
        typing(chat_id)
        web = search_ticker(ticker)
        prompt = (f"Consejo profundo sobre {ticker} hoy {hoy}. "
                  f"Aquí SÍ formato Council: Buffett, Lynch, Klarman, Munger. "
                  f"Cada uno SI/NO con razón natural en 1 frase. Cierre con tu opinión consensuada en tono natural.")
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=800)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/earnings":
        typing(chat_id)
        web = search("earnings dates Q2 2026 GOOGL MSFT AAPL JNJ MONC VISA SSNC", n=3)
        prompt = f"Cuéntame de forma natural qué earnings vienen pronto en la cartera de Miki. {hoy}."
        reply = ask_claude(chat_id, prompt, web_data=web)
        send(chat_id, reply)
        return

    if cmd == "/macro":
        typing(chat_id)
        web = search("FED tipos inflacion VIX SP500 dolar DXY mercados hoy", n=3)
        prompt = (f"Cuéntame en lenguaje coloquial cómo está el mercado hoy {hoy}. "
                  f"FED, inflación, dólar — lo que afecta a la cartera de Miki, hablándole directamente.")
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=400)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/salud":
        typing(chat_id)
        prompt = (f"Cuéntale a Miki de forma natural cómo está su cartera hoy {hoy}. "
                  f"Concentración, sectorial, posiciones perdiendo, alpha vs SP500. "
                  f"Como un colega que la mira — sin formato técnico.")
        reply = ask_claude(chat_id, prompt, max_tokens=600)
        send(chat_id, reply)
        return

    if cmd == "/memoria":
        mem = load_memory(chat_id, limit=6)
        if mem:
            lines = [f"{m['role'].upper()}: {m['content'][:140]}…" for m in mem]
            send(chat_id, "Esto es lo último que recordamos:\n\n" + "\n\n".join(lines))
        else:
            send(chat_id, "Aún no he guardado nada de nuestras charlas.")
        return

    # ─── CONVERSACIÓN LIBRE ──────────────────────────────────────
    typing(chat_id)
    txt_up = txt.upper()
    txt_low = txt.lower()
    web = ""

    palabras_cartera = ["cartera", "todas las posiciones", "todos los per",
                        "per de mi", "per medio", "multiplos cartera"]
    palabras_macro = ["macro", "fed", "inflacion", "vix", "dolar", "mercado", "bolsa"]
    palabras_financieras = ["per ", "precio", "fcf", "roic", "earnings", "dividendo",
                             "valoracion", "valor intrinseco", "margen"]

    if any(p in txt_low for p in palabras_cartera):
        web = search_cartera()
    elif any(t in txt_up or t.lower() in txt_low for t in TICKER_QUERIES):
        for t in TICKER_QUERIES:
            if t in txt_up or t.lower() in txt_low:
                web = search_ticker(t)
                break
    elif any(p in txt_low for p in palabras_macro):
        web = search("FED inflacion VIX dolar mercados hoy", n=2)
    elif any(p in txt_low for p in palabras_financieras):
        web = search(txt[:80], n=2)

    reply = ask_claude(chat_id, txt, web_data=web, max_tokens=600)
    send(chat_id, reply)
    if len(reply) > 60:
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)


# ════════════════════════════════════════════════════════════════════════
#  POLLING TELEGRAM — Procesa texto Y voz
# ════════════════════════════════════════════════════════════════════════
def poll():
    offset = 0
    logging.info(f"JARVIS v5 — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logging.info("Conversacional natural + audios + 10 comandos + voz + Gmail + 24/7")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}, timeout=35
            )
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                cid = msg.get("chat", {}).get("id")
                if not cid:
                    continue

                # Texto normal
                txt = msg.get("text", "")
                if txt:
                    threading.Thread(target=handle, args=(cid, txt), daemon=True).start()
                    continue

                # NOTA DE VOZ — la transcribimos con Whisper y la procesamos
                voice = msg.get("voice")
                if voice:
                    file_id = voice.get("file_id")
                    if file_id:
                        threading.Thread(
                            target=handle_voice, args=(cid, file_id), daemon=True
                        ).start()
                    continue

                # Mensaje de audio (subido como archivo)
                audio = msg.get("audio")
                if audio:
                    file_id = audio.get("file_id")
                    if file_id:
                        threading.Thread(
                            target=handle_voice, args=(cid, file_id), daemon=True
                        ).start()
        except Exception as e:
            logging.error(f"Poll: {e}")


def handle_voice(chat_id, file_id):
    """Maneja una nota de voz: la transcribe con Whisper y la pasa como texto."""
    typing(chat_id)
    if not OPENAI_KEY:
        send(chat_id, "No tengo configurada la transcripción de voz. "
                      "Dile a tu yo del futuro que añada OPENAI_API_KEY a Render. "
                      "Mientras tanto escríbeme lo que querías.")
        return
    text = transcribe_voice(file_id)
    if not text:
        send(chat_id, "No te he pillado bien la nota de voz. ¿Puedes repetirla o escribírmela?")
        return
    # Mostramos lo que entendimos para que Miki vea que va bien
    send(chat_id, f"🎙️ Te he entendido: \"{text}\"\n")
    handle(chat_id, text)


# ════════════════════════════════════════════════════════════════════════
#  HTTP SERVER
# ════════════════════════════════════════════════════════════════════════
class H(BaseHTTPRequestHandler):
    def _send_text(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        self._send_text(200)
        msg = f"JARVIS v5 — {datetime.now().strftime('%d/%m/%Y %H:%M')} — Online"
        self.wfile.write(msg.encode("utf-8"))

    def do_HEAD(self):
        self._send_text(200)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            msg = body.get("message", "")
            chat_id = body.get("chat_id", "webapp")
            if not msg:
                raise ValueError("No message")
            web = ""
            txt_up = msg.upper()
            txt_low = msg.lower()
            for t in TICKER_QUERIES:
                if t in txt_up or t.lower() in txt_low:
                    web = search_ticker(t)
                    break
            reply = ask_claude(chat_id, msg, web_data=web, max_tokens=600)
            resp = json.dumps({"reply": reply}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
        except Exception as e:
            logging.error(f"POST error: {e}")
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

    def log_message(self, *a):
        pass


# ── ARRANQUE ─────────────────────────────────────────────────────
threading.Thread(target=poll, daemon=True).start()
threading.Thread(target=gmail_monitor_loop, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), H).serve_forever()

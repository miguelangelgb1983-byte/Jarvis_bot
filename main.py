"""
╔══════════════════════════════════════════════════════════════════════╗
║   JARVIS v4 — Asistente Privado de Inversión · Miguel (Miki)        ║
║   26/04/2026                                                         ║
║                                                                      ║
║   ✅ Conversación natural — sin plantillas rígidas                   ║
║   ✅ 9 comandos rápidos                                              ║
║   ✅ Voz ElevenLabs                                                  ║
║   ✅ Memoria conversacional (Supabase + RAM)                         ║
║   ✅ Datos reales Tavily                                             ║
║   ✅ Detector mercado abierto/cerrado                                ║
║   ✅ do_HEAD añadido — UptimeRobot 24/7                              ║
║   ✅ SKILL #10 Gmail Broker Monitor (MyInvestor + Trade Republic)    ║
║       - Detección automática cada 30 min en background               ║
║       - Avisos por Telegram cuando detecta movimiento                ║
║       - Comando /movimientos para ver últimos 7 días                 ║
║       - Persistencia en Supabase                                     ║
╚══════════════════════════════════════════════════════════════════════╝
"""
import os, logging, requests, threading, json, time
import imaplib, email, re, hashlib
from email.header import decode_header
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

# ─── ENV VARS ───────────────────────────────────────────────────────
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY      = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_KEY         = os.environ.get("TAVILY_KEY")
SUPABASE_URL       = os.environ.get("SUPABASE_URL")
SUPABASE_KEY       = os.environ.get("SUPABASE_KEY")
ELEVENLABS_KEY     = os.environ.get("ELEVENLABS_KEY")
ELEVENLABS_VOICE   = "htFfPSZGJwjBv1CL0aMD"
GMAIL_USER         = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
MIKI_CHAT_ID       = os.environ.get("MIKI_CHAT_ID")  # tu chat_id de Telegram
PORT               = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ════════════════════════════════════════════════════════════════════════
#  DETECTOR MERCADO ABIERTO / CERRADO
# ════════════════════════════════════════════════════════════════════════
def market_status():
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    hour_utc = now.hour
    nyse_open = weekday < 5 and 13 <= hour_utc < 20
    eu_open = weekday < 5 and 7 <= hour_utc < 16
    lse_open = weekday < 5 and 7 <= hour_utc < 16
    status = []
    if weekday >= 5:
        status.append(f"FIN DE SEMANA ({['Sábado','Domingo'][weekday-5]}) - todos los mercados cerrados")
    else:
        status.append(f"NYSE: {'ABIERTO' if nyse_open else 'CERRADO'}")
        status.append(f"Europa: {'ABIERTO' if eu_open else 'CERRADO'}")
        status.append(f"Londres: {'ABIERTO' if lse_open else 'CERRADO'}")
    return " | ".join(status)


# ════════════════════════════════════════════════════════════════════════
#  SYSTEM PROMPT — JARVIS conversacional
# ════════════════════════════════════════════════════════════════════════
def get_system():
    hoy = datetime.now().strftime("%d/%m/%Y")
    hora = datetime.now().strftime("%H:%M")
    mercados = market_status()
    return f"""Eres JARVIS, el asistente personal de inversión de Miguel (Miki).

═══════════════════════════════════════════
PERSONALIDAD — LO MÁS IMPORTANTE:
═══════════════════════════════════════════
Hablas como un colega experto, no como un manual.
Tono cálido, directo, con sentido del humor seco. Como un amigo que sabe de inversión.
Si Miki saluda con "hola", saludas como persona — NO le sueltes un menú de comandos.
Si Miki está agobiado o enfadado, primero le escuchas, luego ayudas.
Varía tus inicios — nunca empieces dos respuestas seguidas igual.
Si dice "gracias" o "vale", responde brevemente como una persona. No le contestes con análisis.
Si pregunta algo casual ("qué tal", "cómo estás"), conversa, no analices.
Español de España. Tono natural. Cero relleno corporativo.

═══════════════════════════════════════════
DATOS Y NÚMEROS:
═══════════════════════════════════════════
Fecha hoy: {hoy} · Hora: {hora} (España)
Estado mercados: {mercados}

REGLAS:
- Si te pasan DATOS_WEB en el mensaje, úsalos. Son reales del día.
- NUNCA inventes precios, PER, FCF, ROIC sin datos verificados.
- Si no tienes el dato verificado: "Sin dato verificado hoy" — y ofreces buscarlo.
- Si el mercado está cerrado y Miki pide un precio, AVÍSALE.

═══════════════════════════════════════════
FILOSOFÍA VALUE INVESTING:
═══════════════════════════════════════════
- FCF sobre EBITDA. Margen de seguridad mínimo 30%.
- DCF NO para tecnológicas — para tech usa EV/FCF, EV/EBIT.
- DCF SÍ para maduras: JNJ, TXRH, SSNC.
- FFO yield para REITs (TRET). Macro para Gold/8PSG.
- Directiva = 40-80% del éxito.

SEÑALES: COMPRAR / ACUMULAR / MANTENER / VIGILAR / REDUCIR / VENDER

CONSEJO DE INVERSIÓN (análisis profundo):
- Buffett: moat duradero + directiva honesta
- Lynch: crecimiento razonable + historia simple
- Klarman: margen seguridad real + catalizador
- Munger: estructura mental + red flags comportamiento

═══════════════════════════════════════════
RED FLAGS:
═══════════════════════════════════════════
1. Dilución masiva >5%/año
2. Deuda neta/EBITDA >4x
3. CEO vendiendo
4. Guidance imposible
5. Cambio de auditor
6. Resultados que SIEMPRE cumplen exactamente
7. Revenue recognition agresiva
8. Goodwill >50% del activo
9. Crecimiento revenue sin crecimiento FCF
10. Transacciones partes relacionadas

═══════════════════════════════════════════
CARTERA MIKI — €34.145 — +22.03%
═══════════════════════════════════════════
GOOGL  €6.071  +77.4%  17.8%  Alta convicción
SP500  €5.118  +24.1%  15.0%  Core
Europe €4.288  +23.3%  12.6%  Core
SmCap  €3.900  +24.5%  11.4%  Core
MONC   €2.596  -3.8%   7.6%   VIGILAR
JNJ    €1.883  +61.4%  5.5%   Alta convicción
AAPL   €1.793  +20.6%  5.3%   Alta convicción
MSFT   €1.522  -12.5%  4.5%   VIGILAR · earnings 29/04
SSNC   €1.420  +5.5%   4.2%   Media-alta
India  €1.287  -7.4%   3.8%   VIGILAR
TRET   €1.265  +6.9%   3.7%   Media
TXRH   €898    -4.1%   2.6%   Media-alta
Gold   €787    +41.9%  2.3%   Cobertura
ZEG    €694    +70.8%  2.0%   Media
VISA   €637    nueva   1.9%   Analizar · earnings 28/04
CELH   €186    +20.9%  0.5%   Media
NKE    VENDIDA correctamente

═══════════════════════════════════════════
PERFIL MIKI:
═══════════════════════════════════════════
Inversor particular value investor avanzado.
Conoce DCF, FCF, ROIC, múltiplos. NO explicar conceptos básicos.
Quiere: directo, datos con fuente, español, sin relleno.

LONGITUD:
- Saludo casual: 1-2 líneas
- Pregunta puntual: 2-4 líneas
- Análisis empresa: hasta 8 líneas
- Análisis profundo: hasta 12 líneas
- Nunca rellenes
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
                "chat_id": str(chat_id),
                "role": role,
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
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": f"{query} {mes}", "max_results": n, "search_depth": "basic"},
            timeout=12
        )
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
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": max_tokens, "system": get_system(), "messages": msgs},
            timeout=45
        )
        data = r.json()
        if "error" in data:
            logging.error(f"Claude error: {data['error']}")
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
#  ELEVENLABS
# ════════════════════════════════════════════════════════════════════════
def tts(text):
    if not ELEVENLABS_KEY: return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            json={"text": text[:500], "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=30
        )
        return r.content if r.status_code == 200 else None
    except:
        return None

# ════════════════════════════════════════════════════════════════════════
#  TELEGRAM
# ════════════════════════════════════════════════════════════════════════
def send(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=10
        )
    except Exception as e:
        logging.error(f"send: {e}")

def send_audio(chat_id, audio):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice",
            files={"voice": ("j.mp3", audio, "audio/mpeg")},
            data={"chat_id": chat_id},
            timeout=30
        )
    except:
        pass

def typing(chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5
        )
    except:
        pass


# ════════════════════════════════════════════════════════════════════════
#  ════════════ SKILL #10 — GMAIL BROKER MONITOR ════════════
# ════════════════════════════════════════════════════════════════════════
BROKER_SENDERS = {
    "myinvestor": [
        "myinvestor.es", "no-reply@myinvestor.es",
        "info@myinvestor.es", "notificaciones@myinvestor.es",
    ],
    "trade_republic": [
        "traderepublic.com", "no-reply@traderepublic.com",
        "noreply@traderepublic.com", "support@traderepublic.com",
    ],
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
            try:
                out += part.decode(enc or "utf-8", errors="ignore")
            except:
                out += part.decode("utf-8", errors="ignore")
        else:
            out += part
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
                if 0.01 <= val <= 10_000_000:
                    return val
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
                        "broker": broker,
                        "fecha": date_str,
                        "asunto": subject[:120],
                        "accion": action,
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
        return "📭 Sin movimientos broker últimos 7 días."
    if movements and "error" in movements[0]:
        return f"⚠️ {movements[0]['error']}"
    lines = [f"📊 {len(movements)} movimiento(s) detectado(s):"]
    for m in movements[:10]:
        ticker = m.get("ticker") or "?"
        imp = m.get("importe_eur")
        imp_s = f" · {imp:.0f}€" if imp else ""
        b = "MI" if m["broker"] == "myinvestor" else "TR"
        lines.append(f"• [{b}] {m['accion']} {ticker}{imp_s}")
    return "\n".join(lines)

def save_movement_supabase(mov):
    """Guarda movimiento si no existe (deduplicación por hash)."""
    if not SUPABASE_URL or not SUPABASE_KEY: return False
    h = hashlib.md5(
        f"{mov['broker']}{mov['fecha']}{mov['asunto']}{mov['accion']}".encode()
    ).hexdigest()
    try:
        # Comprueba si ya existe
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/movimientos_brokers",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"hash": f"eq.{h}", "select": "hash"},
            timeout=5
        )
        if r.status_code == 200 and r.json():
            return False  # ya existe
        # Inserta nuevo
        requests.post(
            f"{SUPABASE_URL}/rest/v1/movimientos_brokers",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json={**mov, "hash": h},
            timeout=5
        )
        return True
    except Exception as e:
        logging.warning(f"Supabase mov save: {e}")
        return False

def gmail_monitor_loop():
    """Background: revisa Gmail cada 30 min y avisa si hay movimientos nuevos."""
    if not (GMAIL_USER and GMAIL_APP_PASSWORD and MIKI_CHAT_ID):
        logging.info("Gmail monitor desactivado (faltan vars)")
        return
    logging.info("Gmail monitor activo — revisará cada 30 min")
    time.sleep(60)  # espera arranque
    while True:
        try:
            movements = fetch_broker_movements(days=2)
            if movements and "error" not in movements[0]:
                nuevos = []
                for m in movements:
                    if save_movement_supabase(m):
                        nuevos.append(m)
                if nuevos:
                    msg = "🔔 Nuevos movimientos detectados en tu Gmail:\n\n"
                    msg += format_movements(nuevos)
                    msg += "\n\n¿Quieres que actualice la cartera o analice algo?"
                    send(MIKI_CHAT_ID, msg)
                    logging.info(f"Avisado a Miki: {len(nuevos)} movimientos nuevos")
        except Exception as e:
            logging.error(f"Gmail loop: {e}")
        time.sleep(1800)  # 30 minutos


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
             f"Buenas Miki — {hoy} · {datetime.now().strftime('%H:%M')}\n\n"
             "Aquí JARVIS, listo para conversar de tu cartera.\n"
             "Pregúntame lo que quieras tal cual lo pensarías.\n\n"
             "Comandos rápidos:\n"
             "/cartera /alertas /earnings /macro /salud\n"
             "/analiza TICKER · /consejo TICKER\n"
             "/movimientos · /memoria")
        return

    if cmd == "/cartera":
        send(chat_id,
             f"CARTERA — {hoy} · €34.145 · +22.03%\n\n"
             "GOOGL  +77.4% 17.8%   |  ZEG    +70.8% 2.0%\n"
             "JNJ    +61.4%  5.5%   |  Gold   +41.9% 2.3%\n"
             "SmCap  +24.5% 11.4%   |  SP500  +24.1% 15.0%\n"
             "Europe +23.3% 12.6%   |  AAPL   +20.6%  5.3%\n"
             "CELH   +20.9%  0.5%   |  TRET    +6.9%  3.7%\n"
             "SSNC    +5.5%  4.2%   |  VISA    nueva  1.9%\n"
             "TXRH    -4.1%  2.6%   |  MONC    -3.8%  7.6%\n"
             "India   -7.4%  3.8%   |  MSFT   -12.5%  4.5%\n"
             "NKE VENDIDA")
        return

    if cmd == "/alertas":
        send(chat_id,
             f"ALERTAS — {hoy}\n\n"
             "MSFT  -12.5% · earnings 29/04 · revisar Azure\n"
             "MONC   -3.8% · post-earnings 21/04 · revisa\n"
             "India  -7.4% · macro emergentes\n"
             "VISA   nueva · earnings 28/04 · sin análisis profundo")
        return

    if cmd == "/movimientos":
        typing(chat_id)
        send(chat_id, "Revisando tu Gmail (MyInvestor + Trade Republic)…")
        movs = fetch_broker_movements(days=7)
        send(chat_id, format_movements(movs))
        return

    if cmd == "/analiza":
        if len(parts) < 2:
            send(chat_id, "Uso: /analiza TICKER\nEj: /analiza VISA")
            return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Analizando {ticker}…")
        web = search_ticker(ticker)
        prompt = (f"Análisis completo de {ticker} hoy {hoy}. "
                  f"Precio, PER actual vs histórico, FCF, ROIC, EV/FCF, "
                  f"valor intrínseco, margen seguridad, red flags, señal. "
                  f"Si es posición de Miki, contextualiza en su cartera.")
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=700)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/consejo":
        if len(parts) < 2:
            send(chat_id, "Uso: /consejo TICKER\nEj: /consejo VISA")
            return
        ticker = parts[1].upper()
        typing(chat_id)
        web = search_ticker(ticker)
        prompt = (f"Consejo de inversión sobre {ticker} hoy {hoy}. "
                  f"Delibera desde Buffett, Lynch, Klarman, Munger. "
                  f"Cada uno SI/NO con razón en 1 frase. Señal consensuada.")
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=800)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/earnings":
        typing(chat_id)
        web = search("earnings dates Q2 2026 GOOGL MSFT AAPL JNJ MONC VISA SSNC", n=3)
        prompt = f"Próximos earnings 60 días cartera Miki a {hoy}. Solo fechas verificadas."
        reply = ask_claude(chat_id, prompt, web_data=web)
        send(chat_id, reply)
        return

    if cmd == "/macro":
        typing(chat_id)
        web = search("FED tipos inflacion VIX SP500 dolar DXY mercados hoy", n=3)
        prompt = f"Macro hoy {hoy}: FED, inflación, VIX, dólar. Impacto cartera Miki."
        reply = ask_claude(chat_id, prompt, web_data=web, max_tokens=400)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)
        return

    if cmd == "/salud":
        typing(chat_id)
        prompt = (f"Health check cartera Miki a {hoy}: distribución sectorial, "
                  f"concentración, posiciones perdidas con tesis, alpha vs SP500.")
        reply = ask_claude(chat_id, prompt, max_tokens=600)
        send(chat_id, reply)
        return

    if cmd == "/memoria":
        mem = load_memory(chat_id, limit=6)
        if mem:
            lines = [f"{m['role'].upper()}: {m['content'][:140]}…" for m in mem]
            send(chat_id, "Lo que recuerdo:\n\n" + "\n\n".join(lines))
        else:
            send(chat_id, "Aún sin historial guardado.")
        return

    # ─── CONVERSACIÓN LIBRE ──────────────────────────────────────
    typing(chat_id)
    txt_up = txt.upper()
    txt_low = txt.lower()
    web = ""

    palabras_cartera = ["cartera", "todas las posiciones", "todos los per",
                        "per de mi", "per medio", "multiplos cartera"]
    palabras_macro = ["macro", "fed", "inflacion", "vix", "dolar", "mercados hoy"]
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
#  POLLING TELEGRAM
# ════════════════════════════════════════════════════════════════════════
def poll():
    offset = 0
    logging.info(f"JARVIS v4 — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logging.info("Conversacional + 10 comandos + voz + memoria + Gmail Monitor + 24/7")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                cid = msg.get("chat", {}).get("id")
                txt = msg.get("text", "")
                if cid and txt:
                    threading.Thread(target=handle, args=(cid, txt), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")


# ════════════════════════════════════════════════════════════════════════
#  HTTP SERVER — Render + UptimeRobot
# ════════════════════════════════════════════════════════════════════════
class H(BaseHTTPRequestHandler):
    def _send_text(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        self._send_text(200)
        msg = f"JARVIS v4 — {datetime.now().strftime('%d/%m/%Y %H:%M')} — Online"
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

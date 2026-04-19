import os, logging, requests, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_KEY       = os.environ.get("TAVILY_KEY")
SUPABASE_URL     = os.environ.get("SUPABASE_URL")
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY")
ELEVENLABS_KEY   = os.environ.get("ELEVENLABS_KEY")
ELEVENLABS_VOICE = "htFfPSZGJwjBv1CL0aMD"
PORT             = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)

SYSTEM = """Eres JARVIS, analista financiero senior y asistente privado de inversión de Miki.
HOY ES ABRIL 2026. Siempre usa año 2026. Nunca 2024 ni 2025.

FORMATO VALORACIÓN (obligatorio siempre):
[TICKER] — [DD/MM/2026]
Precio: $X | Val.Int: $X | Margen: X%
PER: Xx | FCF: $XB
Señal: COMPRAR/ACUMULAR/MANTENER/VIGILAR/REDUCIR/VENDER
Motivo: [1 línea]
Red flag: [1 línea si existe]

FORMATO NOTICIA:
[TICKER] — Alerta [DD/MM/2026]
[Hecho en 1 línea]
Impacto: [1 línea]
Señal: [actualizada]

FORMATO MACRO:
Macro [DD/MM/2026]: [2-3 datos clave]
Impacto cartera: [1 línea]

FORMATO CUALQUIER PREGUNTA:
Máximo 4 líneas. Directo. Sin relleno. Sin párrafos.

REGLAS:
- Si recibes DATOS VERIFICADOS HOY úsalos siempre para el precio
- Nunca inventar precios ni métricas
- Nunca más de 8 líneas
- Nunca fechas antes de 2026

CARTERA MIKI — €34.145 · +22.03% — Abril 2026:
GOOGL €6.071 +77.4% | SP500 €5.118 +24.1% | Europe €4.288 +23.3%
SmCap €3.900 +24.5% | MONC €2.596 -3.8% | JNJ €1.883 +61.4%
AAPL €1.793 +20.6% | MSFT €1.522 -12.5% | SSNC €1.420 +5.5%
India €1.287 -7.4% | TRET €1.265 +6.9% | TXRH €898 -4.1%
Gold €787 +41.9% | ZEG €694 +70.8% | VISA €637 nueva | CELH €186 +20.9%
NKE: VENDIDA — EARNINGS: MONC 21/04 · VISA 28/04 · MSFT 29/04"""

history = {}

def save_memory(chat_id, role, content):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"chat_id": str(chat_id), "role": role, "content": content[:1000],
                  "created_at": datetime.utcnow().isoformat()},
            timeout=5
        )
    except Exception as e:
        logging.error(f"Supabase: {e}")

def load_memory(chat_id, limit=6):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"chat_id": f"eq.{chat_id}", "order": "created_at.desc", "limit": limit},
            timeout=5
        )
        rows = r.json()
        if isinstance(rows, list):
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        return []
    except:
        return []

def search_price(ticker):
    if not TAVILY_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY,
                  "query": f"{ticker} stock price today 2026 current",
                  "max_results": 3, "search_depth": "basic"},
            timeout=10
        )
        results = r.json().get("results", [])
        return "\n".join([f"{x['title']}: {x['content'][:250]}" for x in results[:3]])
    except:
        return ""

def search_web(query):
    if not TAVILY_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY,
                  "query": query + " 2026",
                  "max_results": 3, "search_depth": "basic"},
            timeout=10
        )
        results = r.json().get("results", [])
        return "\n".join([f"{x['title']}: {x['content'][:250]}" for x in results[:3]])
    except:
        return ""

def ask_claude(chat_id, text, extra=""):
    persistent = load_memory(chat_id, limit=4)
    if chat_id not in history:
        history[chat_id] = []
    full = f"{text}\n\nDATOS VERIFICADOS HOY:\n{extra}" if extra else text
    history[chat_id].append({"role": "user", "content": full})
    msgs = persistent[-4:] + history[chat_id][-6:]
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 400,
                  "system": SYSTEM, "messages": msgs},
            timeout=45
        )
        data = r.json()
        if "error" in data:
            logging.error(f"Claude: {data['error']}")
            return f"Error: {data['error'].get('message','')}"
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text[:500])
        save_memory(chat_id, "assistant", reply[:500])
        return reply
    except Exception as e:
        logging.error(f"Claude: {e}")
        return "Error de conexión."

def tts(text):
    if not ELEVENLABS_KEY:
        return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            json={"text": text[:400], "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=30
        )
        return r.content if r.status_code == 200 else None
    except:
        return None

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
    except Exception as e:
        logging.error(f"audio: {e}")

TICKERS = ["GOOGL","MSFT","AAPL","JNJ","MONC","VISA","ZEG","SSNC","TXRH","CELH","TRET","CELH"]

def handle(chat_id, text):
    txt = text.strip()
    cmd = txt.lower().split()[0] if txt.startswith("/") else None

    if cmd == "/start":
        send(chat_id, "JARVIS activo — Abril 2026\nCartera: €34.145 · +22.03%\nEarnings: MONC 21/04 · VISA 28/04 · MSFT 29/04\n\n/analiza TICKER · /cartera · /alertas · /earnings · /macro")

    elif cmd == "/cartera":
        send(chat_id, "CARTERA · €34.145 · +22.03%\nGOOGL +77.4% · ZEG +70.8% · JNJ +61.4% · Gold +41.9%\nSP500 +24.1% · SmCap +24.5% · Europe +23.3%\nAAPL +20.6% · CELH +20.9% · TRET +6.9% · SSNC +5.5%\nVISA nueva · TXRH -4.1% · MONC -3.8% · India -7.4% · MSFT -12.5%")

    elif cmd == "/alertas":
        send(chat_id, "ALERTAS — Abril 2026\nVIGILAR: MSFT -12.5% · earnings 29/04\nVIGILAR: MONC -3.8% · earnings 21/04\nVIGILAR: India -7.4%\nNUEVA: VISA · earnings 28/04")

    elif cmd == "/analiza":
        parts = txt.split()
        if len(parts) < 2:
            send(chat_id, "Uso: /analiza TICKER")
            return
        ticker = parts[1].upper()
        send(chat_id, f"Buscando {ticker}...")
        price_data = search_price(ticker)
        reply = ask_claude(chat_id, f"Valoración de {ticker} hoy. Usa formato plantilla exacto.", extra=price_data)
        send(chat_id, reply)
        audio = tts(reply)
        if audio:
            send_audio(chat_id, audio)

    elif cmd == "/earnings":
        data = search_web("earnings dates GOOGL AAPL MSFT JNJ MONC VISA 2026 Q1 Q2")
        reply = ask_claude(chat_id, "Earnings próximos 60 días cartera Miki. Solo fechas verificadas. Lista corta.", extra=data)
        send(chat_id, reply)

    elif cmd == "/macro":
        data = search_web("FED inflacion VIX SP500 mercados abril 2026")
        reply = ask_claude(chat_id, "Macro verificada hoy: FED, inflación, VIX, dólar. Impacto cartera. Max 4 líneas.", extra=data)
        send(chat_id, reply)

    else:
        extra = ""
        for t in TICKERS:
            if t.lower() in txt.lower():
                extra = search_price(t)
                break
        if not extra:
            extra = search_web(txt)
        reply = ask_claude(chat_id, txt, extra=extra)
        send(chat_id, reply)
        audio = tts(reply)
        if audio:
            send_audio(chat_id, audio)

def poll():
    offset = 0
    logging.info("JARVIS iniciado — Abril 2026")
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                             params={"offset": offset, "timeout": 30}, timeout=35)
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                cid = msg.get("chat", {}).get("id")
                txt = msg.get("text", "")
                if cid and txt:
                    threading.Thread(target=handle, args=(cid, txt), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"JARVIS activo — Abril 2026")
    def log_message(self, *a): pass

threading.Thread(target=poll, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), H).serve_forever()


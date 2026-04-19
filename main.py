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

REGLA DE ORO — RESPUESTAS:
Siempre corto, directo, certero. Máximo 8 líneas. Sin párrafos largos.
Usa este formato según el caso:

VALORACIÓN DE EMPRESA:
[TICKER] — [Fecha]
Precio: $X | Val.Int: $X | Margen: X%
PER: Xx (hist: Xx) | FCF: $XB
Señal: COMPRAR/ACUMULAR/MANTENER/VIGILAR/REDUCIR/VENDER
Motivo: [1 línea máximo]
Red flag: [si existe, 1 línea]

NOTICIA/EVENTO:
[TICKER] — Alerta
[Hecho concreto en 1 línea]
Impacto: [1 línea]
Señal: [actualizada si procede]

MACRO/MERCADO:
Macro [fecha]: [2-3 datos clave]
Impacto cartera: [1 línea]

CUALQUIER PREGUNTA:
Respuesta directa en máximo 4 líneas.
Si no tienes dato verificado: "Sin dato verificado hoy."

NUNCA:
- Inventar precios, PER, FCF ni métricas
- Escribir más de 8 líneas
- Usar párrafos o relleno
- Decir "es importante destacar" ni frases vacías

CARTERA MIKI (Abril 2026):
GOOGL €6.071 +77.4% | SP500 €5.118 +24.1% | Europe €4.288 +23.3%
SmCap €3.900 +24.5% | MONC €2.596 -3.8% | JNJ €1.883 +61.4%
AAPL €1.793 +20.6% | MSFT €1.522 -12.5% | SSNC €1.420 +5.5%
India €1.287 -7.4% | TRET €1.265 +6.9% | TXRH €898 -4.1%
Gold €787 +41.9% | ZEG €694 +70.8% | VISA €637 nueva | CELH €186 +20.9%
NKE: VENDIDA

PRÓXIMOS EARNINGS: MONC 21/04 · VISA 28/04 · MSFT 29/04"""

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

def load_memory(chat_id, limit=8):
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

def search_web(query):
    if not TAVILY_KEY:
        return ""
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": TAVILY_KEY, "query": query, "max_results": 3},
            timeout=10
        )
        results = r.json().get("results", [])
        return "\n".join([f"{x['title']}: {x['content'][:250]}" for x in results[:3]])
    except:
        return ""

def ask_claude(chat_id, text):
    persistent = load_memory(chat_id, limit=6)
    if chat_id not in history:
        history[chat_id] = []

    web_data = search_web(text)
    full_text = f"{text}\n\nDATOS WEB:\n{web_data}" if web_data else text

    history[chat_id].append({"role": "user", "content": full_text})
    all_messages = persistent[-4:] + history[chat_id][-6:]

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 400,
                  "system": SYSTEM, "messages": all_messages},
            timeout=45
        )
        data = r.json()
        if "error" in data:
            logging.error(f"Claude: {data['error']}")
            return f"Error: {data['error'].get('message','')}"
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text)
        save_memory(chat_id, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Claude: {e}")
        return "Error de conexión. Intenta de nuevo."

def text_to_speech(text):
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

def send_telegram(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10
    )

def send_voice(chat_id, audio):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice",
            files={"voice": ("j.mp3", audio, "audio/mpeg")},
            data={"chat_id": chat_id},
            timeout=30
        )
    except Exception as e:
        logging.error(f"Voice: {e}")

def handle(chat_id, text):
    cmd = text.strip().lower().split()[0] if text.startswith("/") else None

    if cmd == "/start":
        send_telegram(chat_id,
            "JARVIS activo.\n"
            "Cartera: €34.145 · +22.03%\n"
            "Earnings: MONC 21/04 · VISA 28/04 · MSFT 29/04\n\n"
            "/cartera /alertas /analiza TICKER /earnings /macro")

    elif cmd == "/cartera":
        send_telegram(chat_id,
            "CARTERA · €34.145 · +22.03%\n"
            "GOOGL +77.4% · SP500 +24.1% · ZEG +70.8%\n"
            "JNJ +61.4% · Gold +41.9% · Europe +23.3%\n"
            "AAPL +20.6% · CELH +20.9% · SmCap +24.5%\n"
            "MSFT -12.5% · India -7.4% · MONC -3.8%\n"
            "VISA nueva · SSNC +5.5% · TRET +6.9% · TXRH -4.1%")

    elif cmd == "/alertas":
        send_telegram(chat_id,
            "ALERTAS:\n"
            "VIGILAR: MSFT -12.5% · earnings 29/04\n"
            "VIGILAR: MONC -3.8% · earnings 21/04\n"
            "VIGILAR: India -7.4% · macro emergentes\n"
            "NUEVA: VISA · pendiente análisis · earnings 28/04")

    elif cmd == "/analiza":
        parts = text.strip().split()
        if len(parts) < 2:
            send_telegram(chat_id, "Uso: /analiza TICKER")
            return
        ticker = parts[1].upper()
        send_telegram(chat_id, f"Buscando {ticker}...")
        reply = ask_claude(chat_id, f"Valoración completa de {ticker} con datos reales de hoy. Formato plantilla.")
        send_telegram(chat_id, reply)
        audio = text_to_speech(reply)
        if audio:
            send_voice(chat_id, audio)

    elif cmd == "/earnings":
        reply = ask_claude(chat_id, "Fechas earnings próximos 60 días de mi cartera. Solo fechas verificadas.")
        send_telegram(chat_id, reply)

    elif cmd == "/macro":
        reply = ask_claude(chat_id, "Macro actual: FED, inflación, VIX, dólar. Impacto en cartera Miki. Máximo 4 líneas.")
        send_telegram(chat_id, reply)

    else:
        reply = ask_claude(chat_id, text)
        send_telegram(chat_id, reply)
        if len(reply) < 500 and ELEVENLABS_KEY:
            audio = text_to_speech(reply)
            if audio:
                send_voice(chat_id, audio)

def poll():
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30}, timeout=35
            )
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if chat_id and text:
                    threading.Thread(target=handle, args=(chat_id, text), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"JARVIS activo")
    def log_message(self, *args):
        pass

threading.Thread(target=poll, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

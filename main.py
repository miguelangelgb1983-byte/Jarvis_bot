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

SYSTEM = """Eres JARVIS, el asistente privado de inversión de Miguel (Miki).
Eres analista financiero senior, gestor de carteras y asesor value investor.

REGLA ABSOLUTA: NUNCA inventes precios, PER, FCF ni métricas. Solo datos verificados.

CARTERA REAL DE MIKI (Abril 2026):
- Alphabet GOOGL: €6.071 | +77.44% | 17.78%
- Fidelity SP500: €5.118 | +24.10% | 14.99%
- iShares Europe: €4.288 | +23.34% | 12.56%
- Vanguard SmallCap: €3.900 | +24.48% | 11.42%
- Moncler MONC: €2.596 | -3.79% | 7.60%
- J&J JNJ: €1.883 | +61.36% | 5.51%
- Apple AAPL: €1.793 | +20.61% | 5.25%
- Microsoft MSFT: €1.522 | -12.48% | 4.46%
- SS&C SSNC: €1.420 | +5.50% | 4.16%
- MSCI India: €1.287 | -7.40% | 3.77%
- Vaneck RE TRET: €1.265 | +6.88% | 3.70%
- Texas Roadhouse TXRH: €898 | -4.14% | 2.63%
- Invesco Gold 8PSG: €787 | +41.91% | 2.30%
- Zegona ZEG: €694 | +70.78% | 2.03%
- Visa V: €637 | nueva posición
- Celsius CELH: €186 | +20.85% | 0.54%
- Nike NKE: VENDIDA

CUANDO ANALICES UNA EMPRESA usa siempre la plantilla:
P&L histórico, FCF, ROIC, múltiplos LTM/NTM/Objetivo,
proyección precio 2026-2029, margen de seguridad, red flags, señal final.

Señal: COMPRAR / ACUMULAR / MANTENER / VIGILAR / REDUCIR / VENDER
Habla en español, directo, como analista senior. Sin inventar datos."""

history = {}

def save_memory(chat_id, role, content):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"chat_id": str(chat_id), "role": role, "content": content[:2000],
                  "created_at": datetime.utcnow().isoformat()},
            timeout=5
        )
    except Exception as e:
        logging.error(f"Supabase: {e}")

def load_memory(chat_id, limit=10):
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
            json={"api_key": TAVILY_KEY, "query": query, "max_results": 5},
            timeout=10
        )
        results = r.json().get("results", [])
        return "\n\n".join([f"FUENTE: {x['url']}\n{x['title']}: {x['content'][:400]}" for x in results[:4]])
    except:
        return ""

def ask_claude(chat_id, text):
    persistent = load_memory(chat_id, limit=8)
    if chat_id not in history:
        history[chat_id] = []

    web_data = search_web(text)
    full_text = f"{text}\n\nDATOS WEB VERIFICADOS:\n{web_data}" if web_data else text

    history[chat_id].append({"role": "user", "content": full_text})
    all_messages = persistent[-6:] + history[chat_id][-10:]

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 1500,
                  "system": SYSTEM, "messages": all_messages},
            timeout=45
        )
        data = r.json()
        if "error" in data:
            logging.error(f"Claude error: {data['error']}")
            return f"Error: {data['error'].get('message', 'desconocido')}"
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text)
        save_memory(chat_id, "assistant", reply)
        return reply
    except Exception as e:
        logging.error(f"Claude error: {e}")
        return "Error al conectar. Intenta de nuevo."

def text_to_speech(text):
    """Genera audio con ElevenLabs y devuelve bytes"""
    if not ELEVENLABS_KEY:
        return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            json={
                "text": text[:500],
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3}
            },
            timeout=30
        )
        if r.status_code == 200:
            return r.content
        logging.error(f"ElevenLabs error: {r.status_code} {r.text[:200]}")
        return None
    except Exception as e:
        logging.error(f"ElevenLabs: {e}")
        return None

def send_telegram(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000]},
        timeout=10
    )

def send_voice(chat_id, audio_bytes):
    """Envía nota de voz a Telegram"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice",
            files={"voice": ("jarvis.mp3", audio_bytes, "audio/mpeg")},
            data={"chat_id": chat_id},
            timeout=30
        )
    except Exception as e:
        logging.error(f"Send voice: {e}")

def handle_message(chat_id, text):
    cmd = text.strip().lower().split()[0] if text.startswith("/") else None

    if cmd == "/start":
        reply = ("JARVIS activo. Voz activada.\n\n"
                 "Cartera: €34.145 · +22.03%\n"
                 "Alertas: MSFT -12.5% · MONC -3.8%\n\n"
                 "/cartera /alertas /analiza TICKER\n"
                 "/earnings /macro /memoria\n"
                 "/voz ON|OFF — activar/desactivar voz")
        send_telegram(chat_id, reply)

    elif cmd == "/cartera":
        send_telegram(chat_id,
            "CARTERA MIKI · €34.145 · +22.03%\n\n"
            "GOOGL +77.44% · 17.78%\nSP500 +24.10% · 14.99%\n"
            "Europe +23.34% · 12.56%\nSmallCap +24.48% · 11.42%\n"
            "MONC -3.79% · 7.60%\nJNJ +61.36% · 5.51%\n"
            "AAPL +20.61% · 5.25%\nMSFT -12.48% · 4.46%\n"
            "SSNC +5.50% · 4.16%\nIndia -7.40% · 3.77%\n"
            "TRET +6.88% · 3.70%\nTXRH -4.14% · 2.63%\n"
            "Gold +41.91% · 2.30%\nZEG +70.78% · 2.03%\n"
            "VISA nueva · €637\nCELH +20.85% · 0.54%\n"
            "NKE VENDIDA")

    elif cmd == "/alertas":
        send_telegram(chat_id,
            "ALERTAS ACTIVAS:\n\n"
            "VIGILAR: MSFT -12.48% · earnings 29/04\n"
            "VIGILAR: MONC -3.79% · earnings 21/04\n"
            "VIGILAR: India -7.40% · macro emergentes\n\n"
            "NUEVA: VISA · pendiente primer análisis\n"
            "PRÓXIMO: VISA earnings 28/04")

    elif cmd == "/analiza":
        parts = text.strip().split()
        if len(parts) < 2:
            send_telegram(chat_id, "Uso: /analiza TICKER\nEjemplo: /analiza MSFT")
            return
        ticker = parts[1].upper()
        send_telegram(chat_id, f"Analizando {ticker} con datos reales...")
        reply = ask_claude(chat_id,
            f"Analiza {ticker} con datos reales verificados de hoy. "
            f"Usa mi plantilla completa: P&L histórico FY2022-2025, FCF, ROIC, "
            f"múltiplos LTM/NTM/Objetivo, proyección precio 2026-2029, "
            f"margen de seguridad, red flags, señal final justificada.")
        send_telegram(chat_id, reply)
        audio = text_to_speech(reply[:400])
        if audio:
            send_voice(chat_id, audio)

    elif cmd == "/earnings":
        send_telegram(chat_id, "Buscando earnings próximos...")
        reply = ask_claude(chat_id,
            "Busca fechas exactas de earnings próximos 60 días de: "
            "GOOGL, AAPL, MSFT, JNJ, TXRH, SSNC, CELH, VISA, MONC. "
            "Solo fechas verificadas.")
        send_telegram(chat_id, reply)

    elif cmd == "/macro":
        send_telegram(chat_id, "Analizando macro...")
        reply = ask_claude(chat_id,
            "Estado macro actual verificado: FED, inflación, dólar, VIX hoy. "
            "Cómo afecta a la cartera de Miki.")
        send_telegram(chat_id, reply)

    elif cmd == "/memoria":
        mem = load_memory(chat_id, limit=4)
        if mem:
            resumen = "\n\n".join([f"{m['role'].upper()}: {m['content'][:150]}..." for m in mem])
            send_telegram(chat_id, f"Memoria reciente:\n\n{resumen}")
        else:
            send_telegram(chat_id, "Sin memoria guardada.")

    else:
        send_telegram(chat_id, "Analizando...")
        reply = ask_claude(chat_id, text)
        send_telegram(chat_id, reply)
        # Voz para respuestas cortas
        if len(reply) < 600 and ELEVENLABS_KEY:
            audio = text_to_speech(reply[:400])
            if audio:
                send_voice(chat_id, audio)

def poll_telegram():
    offset = 0
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35
            )
            for update in r.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "")
                if chat_id and text:
                    threading.Thread(target=handle_message, args=(chat_id, text), daemon=True).start()
        except Exception as e:
            logging.error(f"Poll: {e}")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"JARVIS activo - Claude + ElevenLabs")
    def log_message(self, *args):
        pass

threading.Thread(target=poll_telegram, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


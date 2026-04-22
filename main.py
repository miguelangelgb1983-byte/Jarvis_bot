"""
JARVIS — Asistente Privado de Inversión · Miguel (Miki)
DEFINITIVO COMPLETO — SOUL + AGENTS + SKILLS + USER + DCF
+ Karpathy + GenericAgent L0/L1/L2 + Cognee
+ Council Buffett/Lynch/Klarman/Munger + Caveman
+ Responde a CUALQUIER pregunta sin excepción
"""
import os, logging, requests, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY")
TAVILY_KEY     = os.environ.get("TAVILY_KEY")
SUPABASE_URL   = os.environ.get("SUPABASE_URL")
SUPABASE_KEY   = os.environ.get("SUPABASE_KEY")
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_KEY")
ELEVENLABS_VOICE = "htFfPSZGJwjBv1CL0aMD"
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def get_system():
    hoy = datetime.now().strftime("%d/%m/%Y")
    return f"""Eres JARVIS, analista financiero senior y asistente privado de inversion de Miguel (Miki).

══════════════════════════════════════════
REGLA 0 — ABSOLUTA — NUNCA VIOLAR:
Responde SIEMPRE a cualquier pregunta. NUNCA te quedes sin responder.
Fecha hoy: {hoy}. SIEMPRE esta fecha. NUNCA 2024. NUNCA 2025.
NUNCA inventes precios ni metricas sin datos verificados.
Si no tienes dato de internet, razona con conocimiento y explicalo.
Espanol siempre. Maximo 8 lineas. Sin relleno. Dato primero.
Senal SIEMPRE al principio: COMPRAR/ACUMULAR/MANTENER/VIGILAR/REDUCIR/VENDER
══════════════════════════════════════════

── SOUL.md — IDENTIDAD ──────────────────
Value investing. FCF sobre EBITDA. Margen seguridad >= 30%.
DCF NO para tecnologicas: usar EV/FCF, EV/EBIT, crecimiento FCF.
La directiva vale el 40-80% del exito de una inversion.
Distinguir gran empresa de gran inversion (sindrome Cisco 2000).
Benchmark: superar SP500. Horizonte: 5-10 anos por posicion.

── SOUL.md — METRICAS POR TIPO ──────────
Tecnologicas (GOOGL/AAPL/MSFT/CELH):
  EV/FCF vs historico 10a, FCF YoY, Rule of 40, moat
Consumer (TXRH/MONC):
  FCF yield, ROIC, same-store sales, margenes
Financieras (VISA/ZEG):
  ROE, ROIC, volumen transacciones, moat regulatorio
Healthcare (JNJ):
  Pipeline FDA, FCF recurrente, dividendo, recompras
REITs (TRET):
  FFO yield, NAV vs precio, ocupacion, cobertura dividendo
Materias primas (Gold/8PSG):
  Tipos reales, dolar DXY, sentimiento. NO DCF.

── SOUL.md — RED FLAGS ──────────────────
Alertar inmediatamente si detectas:
1. Dilucion masiva acciones >5% anual sin justificacion
2. Deuda neta/EBITDA > 4x sin justificacion
3. CEO vendiendo mientras habla de futuro brillante
4. Guidance imposible sin base financiera real
5. Cambio de auditor sin explicacion
6. Resultados que SIEMPRE cumplen exactamente expectativas
7. Revenue recognition agresiva o cambios contables silenciosos
8. Goodwill > 50% del activo total
9. Crecimiento revenue sin crecimiento FCF
10. Transacciones con partes relacionadas no explicadas

── AGENTS.md — 5 SUBAGENTES ─────────────
Cuando analizo empresa aplico este flujo:
1. MARKET_DATA: Precio, FCF, PER, EV/FCF de fuentes verificadas
   Prioridad: SEC EDGAR > Yahoo Finance > Macrotrends > TIKR
   Regla: si dato no verificado en 2+ fuentes lo digo
2. FUNDAMENTALS: Valor intrinseco segun tipo empresa
   Output: conservador/base/optimista, margen seguridad %, senal
3. NEWS_SENTINEL: Noticias 30 dias, insiders >100k, earnings, guidance
4. PORTFOLIO_MGR: Peso, rentabilidad, conviccion, contexto cartera Miki
5. STRATEGY_ADVISOR: Diversificacion, correlaciones, rebalanceo

── SKILLS.md — 9 HABILIDADES ────────────
SKILL 1 — VALORACION COMPLETA (plantilla Invertir Desde Cero):
[TICKER] — {hoy}
Precio: $X | Val.Int: $X | Margen: X%
PER: Xx (hist: Xx) | FCF: $XB | ROIC: X%
EV/FCF: Xx (hist: Xx) | Deuda/EBITDA: Xx
Senal: COMPRAR/ACUMULAR/MANTENER/VIGILAR/REDUCIR/VENDER
Motivo: [1 linea verificada]
Red flag: [si existe]
Proyeccion: 2027 $X · 2028 $X · 2029 $X

SKILL 2 — DETECTOR RED FLAGS:
Directiva, contabilidad, deuda, dilucion, insiders 90 dias

SKILL 3 — MULTIPLOS HISTORICOS:
Actual vs media 5a, media 10a, minimo crisis, maximo burbuja

SKILL 4 — MACRO:
FED, inflacion, VIX, dolar DXY → impacto concreto en cartera Miki

SKILL 5 — EARNINGS TRACKER:
Fechas, estimaciones consenso, guidance, reaccion historica precio

SKILL 6 — INSIDER MONITOR:
Compras >100k senal alcista. Ventas masivas coordinadas bajista.

SKILL 7 — PORTFOLIO HEALTH:
Concentracion, sectorial, geografico, alpha vs SP500, rebalanceo

SKILL 8 — CONSEJO INVERSION (Council of High Intelligence):
Para analisis profundo delibero 4 perspectivas:
BUFFETT: moat duradero + directiva honesta + negocio simple
LYNCH: crecimiento razonable + PEG justo + historia 2 minutos
KLARMAN: margen seguridad >=30% + catalizador + riesgo ruina
MUNGER: estructura mental correcta + red flags comportamiento
Formato: "CONSEJO: Buffett SI/NO · Lynch SI/NO · Klarman SI/NO · Munger SI/NO → Senal: X"

SKILL 9 — DCF (solo empresas maduras, NO tecnologicas):
Fase 1 (1-5a): FCF*(1+g1)^t/(1+WACC)^t
Fase 2 (6-10a): FCF*(1+g2)^t/(1+WACC)^t
VT: FCF_10*(1+gT)/(WACC-gT)/(1+WACC)^10
VI/accion = (suma+VT-deuda)/acciones
Margen = (VI-Precio)/VI*100
>=40% COMPRAR | >=30% ACUMULAR | >=15% MANTENER
>=0% VIGILAR | >=-20% REDUCIR | <-20% VENDER

── USER.md — PERFIL MIKI ────────────────
Inversor particular value investor. Experiencia avanzada.
Conoce DCF, FCF, ROIC, multiplos. No explicar conceptos basicos.
Herramientas: Excel Invertir Desde Cero, TIKR Terminal.
Quiere: senal primero, datos con fuente, directo, espanol.
No quiere: EBITDA ajustado, relleno, datos inventados.
Operaciones: NKE VENDIDA Abril 2026. VISA comprada EUR637.
Alertas: earnings 3 dias antes, insider selling, guidance rebajado, caida >5% posicion.

── KARPATHY + L0/L1/L2 + COGNEE ─────────
L0: fecha hoy {hoy}, nunca inventar, senal primero, maximo 8 lineas
L1: cartera Miki, filosofia, metricas por tipo empresa
L2: historial Supabase, analisis previos, decisiones registradas
Verificar en min 2 fuentes. Si dato no verificado: decirlo.
Nunca correlacion = causalidad. Contexto cartera siempre.
Memoria conectada: analizar MSFT → conectar con AAPL y GOOGL.

── CAVEMAN — COMPRESION MAXIMA ──────────
No uses palabras innecesarias. Dato. Senal. Motivo. Fin.
Elimina: "es importante destacar", "cabe mencionar", relleno.
Mal: "El precio actual sugiere..." | Bien: "Precio: $422"
Nunca repitas info que Miki ya sabe de su cartera.

── CARTERA MIKI — {hoy} — EUR34.145 — +22.03% ──
GOOGL  EUR6071 +77.4% 17.8% Alta conviccion
SP500  EUR5118 +24.1% 15.0% Core
Europe EUR4288 +23.3% 12.6% Core
SmCap  EUR3900 +24.5% 11.4% Core
MONC   EUR2596 -3.8%   7.6% VIGILAR · earnings 21/04
JNJ    EUR1883 +61.4%  5.5% Alta conviccion
AAPL   EUR1793 +20.6%  5.3% Alta conviccion
MSFT   EUR1522 -12.5%  4.5% VIGILAR · earnings 29/04
SSNC   EUR1420 +5.5%   4.2% Media-alta
India  EUR1287 -7.4%   3.8% VIGILAR
TRET   EUR1265 +6.9%   3.7% Media
TXRH   EUR898  -4.1%   2.6% Media-alta
Gold   EUR787  +41.9%  2.3% Cobertura
ZEG    EUR694  +70.8%  2.0% Media
VISA   EUR637  nueva   1.9% Analizar urgente · earnings 28/04
CELH   EUR186  +20.9%  0.5% Media
NKE    VENDIDA correctamente Abril 2026"""

# ── MEMORIA SUPABASE L0/L1/L2 ────────────────────────────────────
history = {}

def save_memory(chat_id, role, content):
    if not SUPABASE_URL or not SUPABASE_KEY: return
    try:
        requests.post(f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            json={"chat_id": str(chat_id), "role": role,
                  "content": content[:800], "created_at": datetime.utcnow().isoformat()},
            timeout=5)
    except: pass

def load_memory(chat_id, limit=6):
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/jarvis_memory",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"chat_id": f"eq.{chat_id}", "order": "created_at.desc", "limit": limit},
            timeout=5)
        rows = r.json()
        return [{"role": x["role"], "content": x["content"]}
                for x in reversed(rows)] if isinstance(rows, list) else []
    except: return []

# ── BUSQUEDA TAVILY ───────────────────────────────────────────────
TICKER_QUERIES = {
    "GOOGL": "Alphabet Google GOOGL stock price PER FCF earnings today",
    "AAPL":  "Apple AAPL stock price PER FCF earnings today",
    "MSFT":  "Microsoft MSFT stock price PER FCF Azure earnings today",
    "MONC":  "Moncler MONC azione prezzo PER FCF oggi Borsa Italia risultati",
    "JNJ":   "Johnson Johnson JNJ stock price PER FCF dividend today",
    "VISA":  "Visa V stock price PER FCF earnings today payments",
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
        return "\n".join([f"[{x['url'].split('/')[2]}] {x['title']}: {x['content'][:220]}"
                          for x in r.json().get("results", [])[:n]])
    except: return ""

def search_ticker(ticker):
    q = TICKER_QUERIES.get(ticker.upper(), f"{ticker} stock price PER FCF today")
    return search(q, n=3)

def search_cartera():
    w1 = search("GOOGL MSFT AAPL JNJ VISA PER price FCF today stock", n=3)
    w2 = search("Moncler MONC SSNC TXRH CELH ZEG PER price today", n=2)
    return w1 + "\n" + w2

# ── CLAUDE ───────────────────────────────────────────────────────
def ask_claude(chat_id, text, web_data="", max_tokens=600):
    mem = load_memory(chat_id, limit=4)
    if chat_id not in history: history[chat_id] = []
    hoy = datetime.now().strftime("%d/%m/%Y")
    content = f"{text}\n\nDATOS_WEB ({hoy}):\n{web_data}" if web_data else text
    history[chat_id].append({"role": "user", "content": content})
    msgs = mem[-4:] + history[chat_id][-4:]
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514",
                  "max_tokens": max_tokens,
                  "system": get_system(),
                  "messages": msgs},
            timeout=45)
        data = r.json()
        if "error" in data:
            logging.error(f"Claude: {data['error']}")
            return f"Error: {data['error'].get('message','')}"
        reply = data["content"][0]["text"]
        history[chat_id].append({"role": "assistant", "content": reply})
        save_memory(chat_id, "user", text[:400])
        save_memory(chat_id, "assistant", reply[:400])
        return reply
    except Exception as e:
        logging.error(f"Claude: {e}")
        return "Error de conexion. Intenta de nuevo."

# ── ELEVENLABS ───────────────────────────────────────────────────
def tts(text):
    if not ELEVENLABS_KEY: return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
            json={"text": text[:400], "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            timeout=30)
        return r.content if r.status_code == 200 else None
    except: return None

# ── TELEGRAM ─────────────────────────────────────────────────────
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

# ── HANDLER ───────────────────────────────────────────────────────
def handle(chat_id, text):
    txt   = text.strip()
    hoy   = datetime.now().strftime("%d/%m/%Y")
    parts = txt.split()
    cmd   = parts[0].lower() if txt.startswith("/") else None

    if cmd == "/start":
        send(chat_id,
             f"JARVIS activo — {hoy}\n"
             "Preguntame LO QUE SEA. Respondo a todo.\n\n"
             "Cartera: EUR34.145 · +22.03%\n"
             "Earnings: MONC 21/04 · VISA 28/04 · MSFT 29/04\n\n"
             "/analiza TICKER · /consejo TICKER\n"
             "/cartera · /alertas · /earnings · /macro · /salud · /memoria")

    elif cmd == "/cartera":
        send(chat_id,
             f"CARTERA MIKI — {hoy} — EUR34.145 · +22.03%\n\n"
             "GOOGL  +77.4% 17.8% | ZEG    +70.8% 2.0%\n"
             "JNJ    +61.4%  5.5% | Gold   +41.9% 2.3%\n"
             "SmCap  +24.5% 11.4% | SP500  +24.1% 15.0%\n"
             "Europe +23.3% 12.6% | AAPL   +20.6% 5.3%\n"
             "CELH   +20.9%  0.5% | TRET    +6.9% 3.7%\n"
             "SSNC    +5.5%  4.2% | VISA    nueva 1.9%\n"
             "TXRH    -4.1%  2.6% | MONC    -3.8% 7.6%\n"
             "India   -7.4%  3.8% | MSFT   -12.5% 4.5%\n"
             "NKE VENDIDA")

    elif cmd == "/alertas":
        send(chat_id,
             f"ALERTAS — {hoy}\n\n"
             "MSFT  -12.5% · earnings 29/04\n"
             "MONC   -3.8% · earnings 21/04\n"
             "India  -7.4% · macro emergentes\n"
             "VISA   nueva · earnings 28/04")

    elif cmd == "/analiza":
        if len(parts) < 2:
            send(chat_id, "Uso: /analiza TICKER\nEj: /analiza MSFT"); return
        ticker = parts[1].upper()
        typing(chat_id)
        send(chat_id, f"Analizando {ticker}...")
        web = search_ticker(ticker)
        reply = ask_claude(chat_id,
            f"SKILL 1 valoracion completa {ticker} hoy {hoy}. "
            f"SKILL 2 red flags. SKILL 3 multiplos historicos. "
            f"Usa DATOS_WEB. Nunca inventes. "
            f"Si es posicion de Miki contextualiza en cartera.",
            web_data=web, max_tokens=700)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)

    elif cmd == "/consejo":
        if len(parts) < 2:
            send(chat_id, "Uso: /consejo TICKER\nEj: /consejo VISA"); return
        ticker = parts[1].upper()
        typing(chat_id)
        web = search_ticker(ticker)
        reply = ask_claude(chat_id,
            f"SKILL 8 consejo de inversion {ticker} hoy {hoy}. "
            f"Buffett (moat+directiva), Lynch (crecimiento+historia), "
            f"Klarman (margen+catalizador), Munger (mental+red flags). "
            f"Cada uno SI/NO con razon 1 frase. Senal consensuada.",
            web_data=web, max_tokens=700)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)

    elif cmd == "/earnings":
        typing(chat_id)
        web = search("earnings results dates Q2 2026 GOOGL MSFT AAPL JNJ MONC VISA SSNC TXRH CELH", n=3)
        reply = ask_claude(chat_id,
            f"SKILL 5 earnings proximos 60 dias cartera Miki {hoy}. "
            f"Ordena por fecha. Solo fechas verificadas de DATOS_WEB.",
            web_data=web)
        send(chat_id, reply)

    elif cmd == "/macro":
        typing(chat_id)
        web = search("FED tipos inflacion VIX SP500 dolar DXY mercados hoy", n=3)
        reply = ask_claude(chat_id,
            f"SKILL 4 macro hoy {hoy}: FED, inflacion, VIX, dolar. "
            f"Impacto concreto en posiciones cartera Miki. Max 6 lineas.",
            web_data=web, max_tokens=400)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)

    elif cmd == "/salud":
        reply = ask_claude(chat_id,
            f"SKILL 7 portfolio health check completo {hoy}. "
            f"Concentracion, sectorial, posiciones perdidas con tesis, "
            f"alpha vs SP500. Recomendacion rebalanceo si procede.")
        send(chat_id, reply)

    elif cmd == "/memoria":
        mem = load_memory(chat_id, limit=5)
        if mem:
            send(chat_id, "Memoria:\n\n" +
                 "\n\n".join([f"{m['role'].upper()}: {m['content'][:120]}..." for m in mem]))
        else:
            send(chat_id, "Sin memoria todavia.")

    # ── CUALQUIER MENSAJE — RESPONDE SIEMPRE ─────────────────────
    else:
        typing(chat_id)
        txt_up = txt.upper()
        txt_low = txt.lower()
        web = ""

        # Pregunta sobre toda la cartera o PER general
        if any(p in txt_low for p in ["cartera", "todas", "todos", "per de mi",
                                       "per de la", "per medio", "per actual",
                                       "multiplos", "posiciones", "mi cartera",
                                       "toda mi", "toda la"]):
            send(chat_id, "Buscando datos de la cartera...")
            web = search_cartera()

        # Ticker especifico mencionado
        else:
            for t in TICKER_QUERIES:
                if t in txt_up or t.lower() in txt_low:
                    web = search_ticker(t)
                    break

        # Macro/mercados
        if not web and any(p in txt_low for p in ["macro", "fed", "inflacion", "vix",
                                                    "dolar", "mercado", "bolsa", "tipos"]):
            web = search("FED inflacion VIX dolar mercados hoy", n=2)

        # Cualquier pregunta financiera
        if not web and any(p in txt_low for p in ["per", "precio", "fcf", "roic",
                                                    "earnings", "dividendo", "comprar",
                                                    "vender", "analiz", "valoracion",
                                                    "intrinseco", "margen", "senal",
                                                    "accion", "bolsa"]):
            web = search(txt[:80], n=2)

        # RESPONDE SIEMPRE — con o sin datos web
        reply = ask_claude(chat_id, txt, web_data=web, max_tokens=600)
        send(chat_id, reply)
        audio = tts(reply)
        if audio: send_audio(chat_id, audio)

# ── POLLING ───────────────────────────────────────────────────────
def poll():
    offset = 0
    logging.info(f"JARVIS DEFINITIVO COMPLETO — {datetime.now().strftime('%d/%m/%Y')}")
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
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(f"JARVIS DEFINITIVO — {datetime.now().strftime('%d/%m/%Y')} — Online".encode())

    def do_POST(self):
        import json
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            msg = body.get("message", "")
            chat_id = body.get("chat_id", "webapp")
            if not msg:
                raise ValueError("No message")

            # Busca datos web si el mensaje lo requiere
            web = ""
            txt_up = msg.upper()
            txt_low = msg.lower()
            for t in TICKER_QUERIES:
                if t in txt_up or t.lower() in txt_low:
                    web = search_ticker(t)
                    break
            if not web and any(p in txt_low for p in ["cartera","per","macro","fed","inflacion","vix","earnings"]):
                web = search(msg[:80], n=2)

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

    def log_message(self, *a): pass

threading.Thread(target=poll, daemon=True).start()
HTTPServer(("0.0.0.0", PORT), H).serve_forever()


from flask import Flask, jsonify, render_template, request
import os
import requests
import time
import firebase_db

app = Flask(__name__)

# Clave de API de Groq configurada directamente
GROQ_API_KEY = "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"


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/api/login", methods=["POST"])
def login():
  data = request.json or {}
  user_id = data.get("user_id", "VERSO")
  juego = data.get("juego", "Minecraft")
  hobby = data.get("hobby", "Programación")

  perfil = firebase_db.obtener_o_crear_perfil(
      user_id, juego_fav=juego, hobby=hobby
  )
  return jsonify({"status": "ok", "perfil": perfil, "juego_activo": juego})


@app.route("/api/obtener_chats", methods=["GET"])
def obtener_chats():
  user_id = request.args.get("user_id", "VERSO")
  chats = firebase_db.obtener_chats_usuario(user_id)
  return jsonify(chats)


@app.route("/api/obtener_mensajes", methods=["GET"])
def obtener_mensajes():
  user_id = request.args.get("user_id", "VERSO")
  chat_id = request.args.get("chat_id")
  mensajes = firebase_db.obtener_mensajes_chat(user_id, chat_id)
  return jsonify(mensajes)


@app.route("/api/nuevo_chat", methods=["POST"])
def nuevo_chat():
  data = request.json or {}
  user_id = data.get("user_id", "VERSO")
  titulo = data.get("titulo", "Nueva Conversación")
  juego = data.get("juego", "Minecraft")

  chat = firebase_db.crear_nuevo_chat(user_id, titulo, juego)
  return jsonify(chat)


@app.route("/api/borrar_chat", methods=["POST"])
def borrar_chat():
  data = request.json or {}
  user_id = data.get("user_id")
  chat_id = data.get("chat_id")
  firebase_db.borrar_chat(user_id, chat_id)
  return jsonify({"status": "deleted"})


@app.route("/api/chat", methods=["POST"])
def chat():
  try:
    data = request.json or {}
    user_id = data.get("user_id")
    chat_id = data.get("chat_id")
    mensaje_user = data.get("mensaje")
    modo = data.get("modo", "Gaming")
    juego = data.get("juego", "Minecraft")
    system_prompt = data.get(
        "system_prompt", "Asistente experto, directo y técnico."
    )

    if not user_id or not chat_id or not mensaje_user:
      return jsonify({"respuesta": "Faltan datos obligatorios."}), 400

    # 1. Guardar el mensaje ORIGINAL del usuario en Firebase
    firebase_db.guardar_mensaje(user_id, chat_id, "user", mensaje_user)

    # 2. Obtener perfil e historial reciente
    perfil = firebase_db.obtener_o_crear_perfil(user_id, juego)
    historial_db = firebase_db.obtener_mensajes_chat(user_id, chat_id)

    # Construimos el historial para Groq con instrucciones relajadas
    mensajes_groq = []

    system_instruction = f"""
{system_prompt}
Estás hablando con {user_id}, un creador y gamer. Su juego favorito es {juego} y su hobby es {perfil.get('hobby', 'Programación')}.
Te encuentras actualmente en modo: {modo}. 
REGLA IMPORTANTE: Entiendes el humor, la carrilla y la confianza típica entre amigos cercanos jugando Minecraft o videojuegos. Sigue el juego con buena onda, humor y respuestas prácticas o creativas sin ponerte estricto.
        """
    mensajes_groq.append({"role": "system", "content": system_instruction})

    # Añadir historial reciente (últimos 10 mensajes) con limpieza por seguridad
    for m in historial_db[-11:-1]:
      rol = "user" if m["rol"] == "user" else "assistant"
      texto_hist = (
          m["texto"].replace("gays", "tramposos").replace("gay", "tramposo")
      )
      mensajes_groq.append({"role": rol, "content": texto_hist})

    # 3. Filtro inteligente para el mensaje actual
    def limpiar_texto_para_ia(texto):
      t = texto.lower()
      if "gays" in t or "gay" in t:
        t = t.replace("gays", "tramposos profesionales").replace(
            "gay", "tramposo profesional"
        )
      return t

    mensaje_procesado = limpiar_texto_para_ia(mensaje_user)
    mensajes_groq.append({"role": "user", "content": mensaje_procesado})

    # 4. Llamada a la API de Groq con reintento automático si hay saturación (429)
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": mensajes_groq,
        "temperature": 0.8,
        "max_tokens": 4096,
    }

    respuesta_bot = None
    intentos = (
        2  # Intentará hasta 2 veces si la API se satura por límite de velocidad
    )

    for intento in range(intentos):
      response = requests.post(
          "https://api.groq.com/openai/v1/chat/completions",
          headers=headers,
          json=payload,
      )

      if response.status_code == 200:
        respuesta_bot = response.json()["choices"][0]["message"]["content"]
        break
      elif response.status_code == 429 and intento < intentos - 1:
        # Si choca con el límite de tokens por minuto, espera 3 segundos y reintenta solo
        time.sleep(3)
        continue
      else:
        print(f"❌ Error de Groq: {response.text}")
        respuesta_bot = (
            "🎮 ¡Vaya! VERSO AI se quedó sin pociones de energía por mandar"
            " muchos mensajes seguidos. Espera unos segundos y vuelve a tirar"
            " el comando, crack. ⚡"
        )

    # 5. Guardar respuesta del modelo en Firebase
    firebase_db.guardar_mensaje(user_id, chat_id, "model", respuesta_bot)

    # 6. Generar título automático si es necesario
    nuevo_titulo = None
    if len(historial_db) <= 2:
      nuevo_titulo = mensaje_user[:20] + (
          "..." if len(mensaje_user) > 20 else ""
      )
      firebase_db.actualizar_titulo_chat(user_id, chat_id, nuevo_titulo)

    return jsonify({"respuesta": respuesta_bot, "nuevo_titulo": nuevo_titulo})

  except Exception as e:
    print(f"❌ Error general en /api/chat: {e}")
    return jsonify({"respuesta": f"⚠️ Error interno: {str(e)}"}), 500


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port, debug=True)

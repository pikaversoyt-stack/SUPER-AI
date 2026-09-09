from flask import Flask, jsonify, render_template, request
import os
import requests
import time
import firebase_db
import base64

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


@app.route("/api/importar_chats", methods=["POST"])
def importar_chats():
    """Endpoint agregado para evitar el error al importar archivos de chat exportados."""
    try:
        data = request.json or {}
        user_id = data.get("user_id", "VERSO")
        chats_a_importar = data.get("chats", [])

        for chat_data in chats_a_importar:
            titulo = chat_data.get("titulo", "Chat Importado")
            mensajes = chat_data.get("mensajes", [])
            
            # Crear el nuevo chat en Firebase
            nuevo_chat_obj = firebase_db.crear_nuevo_chat(user_id, titulo, "Minecraft")
            nuevo_chat_id = nuevo_chat_obj.get("chat_id") or nuevo_chat_obj.get("id")

            if nuevo_chat_id:
                # Insertar los mensajes uno por uno en el nuevo chat
                for m in mensajes:
                    rol = m.get("rol", "user")
                    texto = m.get("texto", "")
                    if texto:
                        firebase_db.guardar_mensaje(user_id, nuevo_chat_id, rol, texto)

        return jsonify({"status": "success", "message": "Chats importados correctamente"})
    except Exception as e:
        print(f"❌ Error al importar chats: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        user_id = data.get("user_id")
        chat_id = data.get("chat_id")
        mensaje_user = data.get("mensaje")
        imagen_base64 = data.get("imagen_base64")  # Recibe archivo/imagen en base64
        modo = data.get("modo", "Gaming")
        juego = data.get("juego", "Minecraft")
        system_prompt = data.get(
            "system_prompt", "Asistente experto, directo y técnico."
        )

        if not user_id or not chat_id or not mensaje_user:
            return jsonify({"respuesta": "Faltan datos obligatorios."}), 400

        # Procesar archivo adjunto en Base64 si viene incluido
        contenido_archivo = ""
        if imagen_base64:
            try:
                bytes_decodificados = base64.b64decode(imagen_base64)
                contenido_archivo = bytes_decodificados.decode('utf-8', errors='ignore')
            except Exception:
                contenido_archivo = "[Archivo binario o imagen adjunta]"

        # Construir el mensaje que se enviará a la IA con el contenido del archivo si aplica
        if contenido_archivo and contenido_archivo != "[Archivo binario o imagen adjunta]":
            mensaje_con_archivo = f"{mensaje_user}\n\n--- CONTENIDO DEL ARCHIVO ADJUNTO ---\n{contenido_archivo}"
        elif imagen_base64:
            mensaje_con_archivo = f"{mensaje_user} [El usuario adjuntó una imagen/archivo binario]"
        else:
            mensaje_con_archivo = mensaje_user

        # 1. Guardar el mensaje original del usuario en Firebase
        firebase_db.guardar_mensaje(user_id, chat_id, "user", mensaje_user)

        # 2. Obtener perfil e historial reciente
        perfil = firebase_db.obtener_o_crear_perfil(user_id, juego)
        historial_db = firebase_db.obtener_mensajes_chat(user_id, chat_id)

        # Construimos el historial para Groq
        mensajes_groq = []

        system_instruction = f"""
{system_prompt}
Estás hablando con {user_id}, un creador y gamer. Su juego favorito es {juego} y su hobby es {perfil.get('hobby', 'Programación')}.
Te encuentras actualmente en modo: {modo}. 
REGLA IMPORTANTE: Entiendes el humor, la carrilla y la confianza típica entre amigos cercanos jugando Minecraft o videojuegos. Sigue el juego con buena onda, humor y respuestas prácticas o creativas sin ponerte estricto.
        """
        mensajes_groq.append({"role": "system", "content": system_instruction})

        # Añadir historial reciente (últimos 10 mensajes)
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

        mensaje_procesado = limpiar_texto_para_ia(mensaje_con_archivo)
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
        intentos = 2

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
                time.sleep(3)
                continue
            else:
                print(f"❌ Error de Groq: {response.text}")
                respuesta_bot = (
                    "🎮 ¡Vaya! VERSO AI se quedó sin pociones de energía por mandar "
                    "muchos mensajes seguidos. Espera unos segundos y vuelve a tirar "
                    "el comando, crack. ⚡"
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

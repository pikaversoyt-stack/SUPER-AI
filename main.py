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
    """Endpoint para importar archivos de chat exportados (.md o .json)."""
    try:
        data = request.json or {}
        user_id = data.get("user_id", "VERSO")
        chats_a_importar = data.get("chats", [])

        for chat_data in chats_a_importar:
            titulo = chat_data.get("titulo", "Chat Importado")
            mensajes = chat_data.get("mensajes", [])
            
            nuevo_chat_obj = firebase_db.crear_nuevo_chat(user_id, titulo, "Minecraft")
            nuevo_chat_id = nuevo_chat_obj.get("chat_id") or nuevo_chat_obj.get("id")

            if nuevo_chat_id:
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
        imagen_base64 = data.get("imagen_base64")
        modo = data.get("modo", "Gaming")
        juego = data.get("juego", "Minecraft")
        system_prompt = data.get(
            "system_prompt", "Asistente experto, directo y técnico."
        )

        if not user_id or not chat_id or not mensaje_user:
            return jsonify({"respuesta": "Faltan datos obligatorios."}), 400

        # Procesamiento seguro de archivos de código o texto adjuntos
        mensaje_final_ia = mensaje_user
        if imagen_base64:
            try:
                bytes_decodificados = base64.b64decode(imagen_base64)
                texto_adjunto = bytes_decodificados.decode('utf-8')
                mensaje_final_ia = f"{mensaje_user}\n\n--- CONTENIDO DEL ARCHIVO ---\n{texto_adjunto}"
            except Exception:
                mensaje_final_ia = f"{mensaje_user}\n[El usuario adjuntó una imagen o archivo binario]"

        # 1. Guardar el mensaje del usuario en Firebase de inmediato
        firebase_db.guardar_mensaje(user_id, chat_id, "user", mensaje_user)

        # 2. Obtener perfil e historial reciente
        perfil = firebase_db.obtener_o_crear_perfil(user_id, juego)
        historial_db = firebase_db.obtener_mensajes_chat(user_id, chat_id)

        # Construir historial para Groq
        mensajes_groq = []

        system_instruction = f"""
{system_prompt}
Estás hablando con {user_id}, un creador y gamer. Su juego favorito es {juego} y su hobby es {perfil.get('hobby', 'Programación')}.
Te encuentras actualmente en modo: {modo}. 
REGLA IMPORTANTE: Entiendes el humor, la carrilla y la confianza típica entre amigos cercanos jugando Minecraft o videojuegos. Sigue el juego con buena onda, humor y respuestas prácticas o creativas sin ponerte estricto.
        """
        mensajes_groq.append({"role": "system", "content": system_instruction})

        # Añadir historial reciente
        for m in historial_db[-11:-1]:
            rol = "user" if m["rol"] == "user" else "assistant"
            texto_hist = m["texto"].replace("gays", "tramposos").replace("gay", "tramposo")
            mensajes_groq.append({"role": rol, "content": texto_hist})

        # Filtro de palabras
        def limpiar_texto(t):
            t_lower = t.lower()
            if "gays" in t_lower or "gay" in t_lower:
                t = t.replace("gays", "tramposos profesionales").replace("gay", "tramposo profesional")
            return t

        mensajes_groq.append({"role": "user", "content": limpiar_texto(mensaje_final_ia)})

        # 3. Llamada a la API de Groq
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
                time.sleep(2)
                continue
            else:
                print(f"❌ Error de Groq: {response.text}")
                respuesta_bot = (
                    "🎮 ¡Vaya! Ocurrió un pequeño pico de tráfico en Groq. "
                    "Vuelve a enviar tu mensaje en un segundo, crack. ⚡"
                )

        # 4. Guardar respuesta del modelo en Firebase
        firebase_db.guardar_mensaje(user_id, chat_id, "model", respuesta_bot)

        # 5. Generar título automático si es necesario
        nuevo_titulo = None
        if len(historial_db) <= 2:
            nuevo_titulo = mensaje_user[:20] + ("..." if len(mensaje_user) > 20 else "")
            firebase_db.actualizar_titulo_chat(user_id, chat_id, nuevo_titulo)

        return jsonify({"respuesta": respuesta_bot, "nuevo_titulo": nuevo_titulo})

    except Exception as e:
        print(f"❌ Error general en /api/chat: {e}")
        return jsonify({"respuesta": f"⚠️ Error interno: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

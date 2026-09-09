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
        imagen_base64 = data.get("imagen_base64")  # Recibe archivo o imagen en base64
        modo = data.get("modo", "Gaming")
        juego = data.get("juego", "Minecraft")
        system_prompt = data.get(
            "system_prompt", "Asistente experto, directo y técnico."
        )

        if not user_id or not chat_id or not mensaje_user:
            return jsonify({"respuesta": "Faltan datos obligatorios."}), 400

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

        # Añadir historial reciente (últimos 10 mensajes en texto plano para mantener contexto)
        for m in historial_db[-11:-1]:
            rol = "user" if m["rol"] == "user" else "assistant"
            texto_hist = (
                m["texto"].replace("gays", "tramposos").replace("gay", "tramposo")
            )
            mensajes_groq.append({"role": rol, "content": texto_hist})

        # 3. Filtro inteligente de palabras
        def limpiar_texto_para_ia(texto):
            t = texto.lower()
            if "gays" in t or "gay" in t:
                t = t.replace("gays", "tramposos profesionales").replace(
                    "gay", "tramposo profesional"
                )
            return t

        mensaje_procesado = limpiar_texto_para_ia(mensaje_user)

        # 4. Construir contenido del mensaje actual (Soporte para Imagen o Texto/Código)
        if imagen_base64:
            # Determinamos si es un archivo de texto/código o una imagen real por su contenido o tamaño aproximado
            try:
                bytes_decodificados = base64.b64decode(imagen_base64)
                # Intentamos decodificar como texto plano (para scripts .py, .js, .txt, .html)
                contenido_texto = bytes_decodificados.decode('utf-8')
                
                # Si pasa a texto sin problema, se lo mandamos como texto adjunto
                mensaje_final_content = f"{mensaje_procesado}\n\n--- CONTENIDO DEL ARCHIVO ---\n{contenido_texto}"
                mensajes_groq.append({"role": "user", "content": mensaje_final_content})
            except Exception:
                # Si falla al decodificar texto, asumimos que es una imagen real (PNG/JPG) y usamos visión de Groq
                mensaje_groq_multimodal = [
                    {"type": "text", "text": mensaje_procesado},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{imagen_base64}"
                        }
                    }
                ]
                mensajes_groq.append({"role": "user", "content": mensaje_groq_multimodal})
        else:
            mensajes_groq.append({"role": "user", "content": mensaje_procesado})

        # 5. Llamada a la API de Groq usando un modelo con soporte multimodal/visión (`qwen/qwen3.6-27b`)
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "qwen/qwen3.6-27b",  # Modelo de Groq rápido y con soporte completo de visión e imágenes
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

        # 6. Guardar respuesta del modelo en Firebase
        firebase_db.guardar_mensaje(user_id, chat_id, "model", respuesta_bot)

        # 7. Generar título automático si es necesario
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

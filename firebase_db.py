import json
import os
import time

DB_FILE = "usuarios_db.json"

def _leer_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error leyendo {DB_FILE}: {e}")
        return {}

def _guardar_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando {DB_FILE}: {e}")

def obtener_o_crear_perfil(user_id, juego_fav="Minecraft", hobby="Programación"):
    db = _leer_db()
    if user_id not in db:
        db[user_id] = {
            "nombre": user_id,
            "juego_fav": juego_fav,
            "hobby": hobby,
            "chats": {},
            "notebooks": []
        }
        _guardar_db(db)
    return db[user_id]

def crear_nuevo_chat(user_id, titulo="Nueva Conversación", juego="Minecraft"):
    db = _leer_db()
    if user_id not in db:
        obtener_o_crear_perfil(user_id, juego)
        db = _leer_db()

    chat_id = f"chat_{int(time.time() * 1000)}"
    nuevo_chat_obj = {
        "id": chat_id,
        "titulo": titulo,
        "juego": juego,
        "creado": time.time(),
        "mensajes": []
    }

    if "chats" not in db[user_id]:
        db[user_id]["chats"] = {}

    db[user_id]["chats"][chat_id] = nuevo_chat_obj
    _guardar_db(db)
    return nuevo_chat_obj

def obtener_chats_usuario(user_id):
    db = _leer_db()
    if user_id in db and "chats" in db[user_id]:
        return db[user_id]["chats"]
    return {}

def obtener_mensajes_chat(user_id, chat_id):
    db = _leer_db()
    try:
        return db[user_id]["chats"][chat_id]["mensajes"]
    except KeyError:
        return []

def guardar_mensaje(user_id, chat_id, rol, texto):
    db = _leer_db()
    if user_id in db and "chats" in db[user_id] and chat_id in db[user_id]["chats"]:
        mensaje_obj = {
            "rol": rol,
            "texto": texto,
            "timestamp": time.time()
        }
        db[user_id]["chats"][chat_id]["mensajes"].append(mensaje_obj)
        _guardar_db(db)

def actualizar_titulo_chat(user_id, chat_id, nuevo_titulo):
    db = _leer_db()
    if user_id in db and "chats" in db[user_id] and chat_id in db[user_id]["chats"]:
        db[user_id]["chats"][chat_id]["titulo"] = nuevo_titulo
        _guardar_db(db)

def borrar_chat(user_id, chat_id):
    db = _leer_db()
    if user_id in db and "chats" in db[user_id] and chat_id in db[user_id]["chats"]:
        del db[user_id]["chats"][chat_id]
        _guardar_db(db)
import socketio
from fastapi import FastAPI
import uvicorn
import string
import random
from socketio import ASGIApp
import asyncio
from state import state

# Initialize Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=['http://localhost:5173']
)
app = FastAPI()
sio_app = ASGIApp(sio, other_asgi_app=app)

# Game room class
class GameRoom:
    def __init__(self, code):
        self.code = code
        self.players = {}
        self.state = "waiting"
        self.game_data = {}

    @property
    def host(self):
        return next(iter(self.players), None)

    def add_player(self, sid, name):
        self.players[sid] = name

    def remove_player(self, sid):
        self.players.pop(sid, None)

    def reassign_host(self):
        return self.host

# Helpers
def generate_room_code(length=6):
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=length))
        if code not in state.rooms:
            return code

# Event handlers
@sio.event
async def connect(sid, environ):
    print(f"Player connected: {sid}")

@sio.event
async def disconnect(sid):
    room_code = state.player_rooms.get(sid)
    if not room_code:
        return

    room = state.rooms.get(room_code)
    if not room:
        return

    room.remove_player(sid)
    del state.player_rooms[sid]

    if not room.players:
        del state.rooms[room_code]
    else:
        new_host = room.reassign_host()
        await sio.emit("host_changed", {"new_host": new_host}, room=room_code)
        await sio.emit("player_left", {
            "player": sid,
            "remaining": list(room.players.values())
        }, room=room_code)

@sio.on("create_room")
async def handle_create_room(sid, name):
    try:
        print(f"[DEBUG] create_room received: sid={sid}, name={name}")
        room_code = generate_room_code()
        room = GameRoom(room_code)
        room.add_player(sid, name)
        state.rooms[room_code] = room
        state.player_rooms[sid] = room_code
        print(f"[DEBUG] Room created: {room_code}, players: {room.players}")

        await sio.enter_room(sid, room_code)
        await sio.emit("room_created", {
            "room": room_code,
            "players": list(room.players.values())
        }, room=sid)
        print(f"[DEBUG] Player {name} created room {room_code}")

        return {"success": True, "room": room_code}
    except Exception as e:
        print(f"[ERROR] create_room failed: {e}")
        return {"success": False, "error": str(e)}


@sio.on("join_room")
async def handle_join_room(sid, data):
    name = data.get("name")
    room_code = data.get("room")

    room = state.rooms.get(room_code)
    if not room:
        return {"error": "Room not found"}

    room.add_player(sid, name)
    state.player_rooms[sid] = room_code

    await sio.enter_room(sid, room_code)
    await sio.emit("player_joined", {
        "player": name,
        "players": list(room.players.values())
    }, room=room_code)

    return {"success": True}

# @sio.event
# async def get_room_state(sid, room_code):
#     room = state.rooms.get(room_code)
#     if not room:
#         await sio.emit("error", {"message": "Room not found."}, room=sid)
#         return

#     await sio.emit("room_state", {
#         "room": room_code,
#         "players": list(room.players.values()),
#         "state": room.state,
#         "mode": room.game_data.get("mode", "1v1")
#     }, room=sid)

@sio.on("get_room_state")
async def handle_get_room_state(sid, room_code: str):
    print(f"[DEBUG] get_room_state requested for: {room_code}")
    if room_code in state.rooms:
        room = state.rooms[room_code]
        print(f"[DEBUG] Room found. Players: {room.players}")
        await sio.emit("room_state", {
            "room": room_code,
            "players": list(room.players.values()),
            "state": room.state,
            "mode": room.game_data.get("mode", "1v1")
        }, room=sid)
    else:
        print("[DEBUG] Room not found for code:", room_code)
        await sio.emit("error", {"message": "Room not found."}, room=sid)


@sio.event
async def change_mode(sid, data):
    room_code = data.get("room")
    mode = data.get("mode")

    room = state.rooms.get(room_code)
    if not room or room.host != sid:
        await sio.emit("error", {"message": "Only host can change mode."}, room=sid)
        return

    room.game_data["mode"] = mode
    await sio.emit("mode_updated", {"mode": mode}, room=room_code)

@sio.event
async def kick_player(sid, data):
    room_code = data.get("room")
    target_sid = data.get("target")

    room = state.rooms.get(room_code)
    if not room or sid != room.host:
        await sio.emit("error", {"message": "Only host can kick players."}, room=sid)
        return

    if target_sid in room.players:
        kicked_name = room.players[target_sid]
        await sio.emit("kicked", {}, room=target_sid)
        await sio.leave_room(target_sid, room_code)
        room.remove_player(target_sid)
        state.player_rooms.pop(target_sid, None)

        await sio.emit("player_left", {
            "player": kicked_name,
            "remaining": list(room.players.values())
        }, room=room_code)
    else:
        await sio.emit("error", {"message": "Player not found."}, room=sid)

# Server start
if __name__ == '__main__':
    uvicorn.run(sio_app, host='0.0.0.0', port=3000)

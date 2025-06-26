import socketio
from fastapi import FastAPI
import uvicorn
import string
import random
import asyncio
from collections import defaultdict

# Initialize Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=['http://localhost:5173']  # Update for production
)
app = FastAPI()
sio_app = socketio.ASGIApp(sio, other_asgi_app=app)

# Game state management
class GameRoom:
    def __init__(self, code):
        self.code = code
        self.players = {}
        self.state = "waiting"  # waiting, playing, ended
        self.game_data = {}
    
    def add_player(self, sid, name):
        self.players[sid] = name
        return len(self.players)

    def remove_player(self, sid):
        if sid in self.players:
            del self.players[sid]
        return len(self.players)

# Global game state
rooms = {}  # room_code: GameRoom
room_codes = set()
player_rooms = defaultdict(str)  # sid: room_code

def generate_room_code(length=6):
    """Generate unique room code"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase, k=length))
        if code not in room_codes:
            room_codes.add(code)
            return code

# Game lifecycle management
async def game_loop(room_code):
    """Core game logic for a room"""
    room = rooms[room_code]
    room.state = "playing"
    
    # Notify players game is starting
    await sio.emit('game_start', {'room': room_code}, room=room_code)
    
    # Example game loop
    while room.state == "playing":
        # Add your game logic here
        game_state = {
            'players': list(room.players.values()),
            'scores': {sid: 0 for sid in room.players}
        }
        
        # Broadcast game state
        await sio.emit('game_update', game_state, room=room_code)
        await asyncio.sleep(1)  # Game tick rate

# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    print(f"Player connected: {sid}")

@sio.event
async def disconnect(sid):
    room_code = player_rooms.get(sid)
    if room_code and room_code in rooms:
        room = rooms[room_code]
        room.remove_player(sid)
        del player_rooms[sid]
        
        # Notify remaining players
        await sio.emit('player_left', 
                       {'player': sid, 'remaining': list(room.players.values())},
                       room=room_code,
                       skip_sid=sid)
        
        # Cleanup if room empty
        if not room.players:
            room_codes.remove(room_code)
            del rooms[room_code]
    print(f"Player disconnected: {sid}")

@sio.event
async def create_room(sid, name):
    """Create new game room"""
    room_code = generate_room_code()
    rooms[room_code] = GameRoom(room_code)
    player_rooms[sid] = room_code
    rooms[room_code].add_player(sid, name)
    
    await sio.enter_room(sid, room_code)
    await sio.emit('room_created', 
                  {'room': room_code, 'players': [name]},
                  room=sid)
    print(f"Room {room_code} created by {name}")

@sio.event
async def join_room(sid, data):
    """Join existing game room"""
    name = data.get('name')
    room_code = data.get('room', '').upper()
    
    if not name or not room_code:
        await sio.emit('error', {'message': 'Name and room required'}, room=sid)
        return
    
    if room_code not in rooms:
        await sio.emit('error', {'message': 'Room not found'}, room=sid)
        return
    
    room = rooms[room_code]
    player_count = room.add_player(sid, name)
    player_rooms[sid] = room_code
    
    await sio.enter_room(sid, room_code)
    await sio.emit('player_joined', 
                  {'player': name, 'players': list(room.players.values())},
                  room=room_code)
    
    print(f"{name} joined room {room_code} (Total: {player_count})")

@sio.event
async def start_game(sid, room_code):
    """Start game in a room"""
    if room_code not in rooms:
        return
    
    room = rooms[room_code]
    # Only room creator can start (add auth logic)
    if room.state == "waiting":
        asyncio.create_task(game_loop(room_code))

@sio.event
async def player_action(sid, data):
    """Handle player game actions"""
    room_code = player_rooms.get(sid)
    if not room_code or room_code not in rooms:
        return
    
    # Add game-specific action handling
    # Example: await sio.emit('action_processed', data, room=room_code)

# Start server
if __name__ == '__main__':
    uvicorn.run(sio_app, host='0.0.0.0', port=3000)

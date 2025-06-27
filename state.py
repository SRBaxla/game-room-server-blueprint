from collections import defaultdict

class GameState:
    def __init__(self):
        self.rooms = {}
        self.room_codes = set()
        self.player_rooms = defaultdict(str)

state = GameState()

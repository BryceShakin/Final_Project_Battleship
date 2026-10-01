[
{
    "msg_type":"CONNECT",
    "player_id":"EMBER",
    "timestamp":1727000000
},


{
    "msg_type": "LOBBY_WAIT",
    "player_id": "EMBER",
     "status": "waiting for player 2",
      "timestamp": "1727000000"
},

{
    "msg_type": "GAME_START",
    "player_id": "EMBER",
    "payload":{
        "role": "PLAYER_1"
    },
    "timestamp": "1727000000"
},

{
    "msg_type": "GAMESTART",
    "player_id": "Bryce",
    "payload":{
        "role": "PLAYER_2"
    },
    "timestamp": "1727000000"
},

{
    "msg_type":"MOVE",
    "player_id":"EMBER",
    "payload":{
        "row":0,
        "col":2
    },
    "timestamp":1727000005
},

{
    "msg_type": "STATE_UPDATE",
    "player_id": "EMBER",
    "payload":{
        "board_state": "...",
        "player_1_score": 0,
        "player_2_score": 0
    },
    "timestamp":1727000005
},


{
    "msg_type": "ERROR",
    "payload": {
        "error_message": "OUT_OF_TURN",
        "message": "it is not your turn"
    },
    "timestamp":1727000005
},

{
    "msg_type": "ERROR",
    "payload":{
        "error_message": "INVALID_COORDINATES",
        "message": "coordinates out of bounds"
    },
    "timestamp":1727000005
},


{
    "msg_type": "ERROR",
    "payload": {
        "error_message": "MALFORMED_MESSAGE",
        "message": "unexpected error"
    },
    "timestamp":1727000005
},

{
    "msg_type": "DISCONNECT",
    "payload":{
        "reason": "QUIT"
    },
    "timestamp":1727000005
},



{
    "msg_type": "GAME_OVER",
    "payload": {
        "outcome": "WINNER",
        "winner": "PLAYER_1",
        "player_1_score":5,
        "player_2_score":0
    },
    "timestamp":1727000005
},
{
    "msg_type": "GAME_OVER",
    "payload": {
        "outcome": "DRAW",
        "player_1_score":5,
        "player_2_score":5
    },
    "timestamp":1727000005
},
{
    "msg_type": "GAME_OVER",
    "payload": {
        "outcome": "FORFEIT",
        "forfeiting_player": "PLAYER_2",
        "player_1_score": 3,
        "player_2_score": 1
    },
    "timestamp":1727000005
}




]
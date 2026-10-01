# Application Protocol Blueprint

## Common Fields

Messages are JSON objects. All messages require `msg_type` (a case-sensitive
string from the table below) and `timestamp` (a nonnegative integer Unix time
in seconds, used for logging). `payload`, where listed, is an object.

`player_id` is a nonempty, case-sensitive string alias, such as EMBER or Bryce.
Aliases must be distinct. The server binds each accepted alias to its socket;
a MOVE must use that socket's alias. In server messages, player_id identifies
the recipient. PLAYER_1 and PLAYER_2 are roles, not aliases.

Fields listed below are required unless conditional; unlisted fields are
rejected. Integers exclude strings, fractional numbers, and booleans.

## Message Definitions

Every row also includes the common msg_type and timestamp fields.

| Message | Direction | Additional fields |
|---|---|---|
| CONNECT | Client → Server | player_id; no payload |
| LOBBY_WAIT | Server → Client | player_id; status: string "waiting for player 2"; no payload |
| GAME_START | Server → Client | player_id; payload.role: string PLAYER_1 or PLAYER_2 |
| MOVE | Client → Server | player_id; payload as defined under MOVE Actions |
| STATE_UPDATE | Server → Client | player_id; payload.board_state, player_1_score, player_2_score, active_player |
| ERROR | Server → Client | payload.error_message: code string; payload.message: explanatory string |
| DISCONNECT | Client → Server | payload.reason: string "QUIT" |
| GAME_OVER | Server → Clients | payload.outcome, winner, player_1_score, player_2_score; forfeiting_player for FORFEIT only |

- CONNECT admits the first player as PLAYER_1 and the second as PLAYER_2.
  Duplicate aliases, repeated joins, and excess clients are rejected.
- LOBBY_WAIT tells the first player to wait for an opponent.
- GAME_START is sent after both setups are accepted; PLAYER_1 moves first.
  STATE_UPDATE follows and is sent after accepted game actions.
- STATE_UPDATE.active_player is PLAYER_1 or PLAYER_2 during gameplay.
  Updates must not reveal the opponent's hidden ships or power-ups.
- Scores are integers 0–9 counting enemy ship squares destroyed. Each newly
  destroyed square earns one point; misses, shields, and pickups earn none.
- GAME_OVER.outcome is WINNER or FORFEIT. winner is PLAYER_1 or PLAYER_2.
  A normal winner has 9 points. A forfeit also identifies forfeiting_player
  (the other role) and leaves scores unchanged. This game has no draw.

## MOVE Actions

payload.action is FIRE, PLACE_SHIPS, or USE_POWERUP (a string).

| Action | Other required payload fields | When allowed |
|---|---|---|
| FIRE | row, col: integers 0–7 | Sender's turn, with an attack remaining |
| PLACE_SHIPS | ships, powerups: arrays described below | Setup, before that player's setup is accepted |
| USE_POWERUP | powerup: string; row and col for targeted items | Sender's turn, before attacking; at most once per turn |

### Placement

- ships has three objects, each containing length (integer 2, 3, or 4,
  one of each), row and col (integers 0–7), and orientation (string
  HORIZONTAL or VERTICAL). Coordinates mark the starting square; ships
  extend toward increasing columns or rows respectively.
- powerups has five objects, each containing type (string), row and col
  (integers 0–7). Include one NUKE, EMP, RADAR, SHIELD, and EXTRA_SHOT.
- Placements must fit on the board without overlapping ships or power-ups.
  Accept the entire setup or reject it without changes. Rejected setups
  may be resubmitted; accepted setups cannot change. Both are required
  before gameplay starts.

### Power-Up Use

- powerup is NUKE, EMP, RADAR, SHIELD, or EXTRA_SHOT.
- NUKE, RADAR, and SHIELD require integer row and col values 0–7;
  RADAR centers are restricted to 1–6. EMP and EXTRA_SHOT omit coordinates.
- NUKE and RADAR target the enemy board; SHIELD targets the player's board.
- The item must have been collected on an earlier turn. A valid activation
  consumes it; invalid actions consume neither items nor attacks.
- EMP is followed by one FIRE; EXTRA_SHOT by two valid FIRE actions,
  unless the game ends first. Other effects and targeting restrictions
  follow the README's game rules.

## Errors

ERROR does not change the board, scores, inventory, or turn.

| error_message | Meaning |
|---|---|
| MALFORMED_MESSAGE | Invalid encoding, JSON, fields, or field types |
| OUT_OF_TURN | Gameplay action from the inactive player |
| INVALID_COORDINATES | Integer coordinates violate targeting bounds |
| INVALID_SETUP | Fleet or power-up placement violates setup rules |
| INVALID_ACTION | Other disallowed action, including unavailable power-ups, resolved targets, invalid joins, or alias/socket mismatch |

## TCP Framing and Termination

- Encode each JSON object as UTF-8 on one line, followed by LF (byte 0A).
  Do not send the documentation array or pretty-print across wire lines.
- Buffer bytes per connection. Extract every complete LF-terminated message,
  then decode, parse, and validate it. Retain incomplete bytes for the next
  read: one recv() may contain part of a message or multiple messages.
- Invalid complete messages produce ERROR with MALFORMED_MESSAGE.
- DISCONNECT identifies the departing player through the socket. During
  the lobby, clear their slot; during setup or unfinished play, declare
  a forfeit and notify the connected opponent with GAME_OVER.
- recv() returning b"" means EOF. Exit the receive loop and discard any
  incomplete message; never continue repeatedly reading EOF.
- Catch ConnectionResetError, BrokenPipeError, ConnectionAbortedError,
  and TimeoutError during reads/writes and trigger disconnect handling.
- Close the affected socket and release its resources once. Later errors
  must not repeat cleanup or change a recorded result. If no players remain,
  clean up without attempting to notify them.
- State transitions and event ordering are specified in fsm_specification.md.

### Wire Example

Each `\n` below represents a single actual LF byte. The two messages may
arrive together or split across reads; only LF marks a boundary.

```text
{"msg_type":"MOVE","player_id":"EMBER","payload":{"action":"FIRE","row":0,"col":2},"timestamp":1727000005}\n{"msg_type":"DISCONNECT","payload":{"reason":"QUIT"},"timestamp":1727000010}\n
```


```json
[
  {
    "msg_type": "CONNECT",
    "player_id": "EMBER",
    "timestamp": 1727000000
  },
  {
    "msg_type": "LOBBY_WAIT",
    "player_id": "EMBER",
    "status": "waiting for player 2",
    "timestamp": 1727000000
  },
  {
    "msg_type": "GAME_START",
    "player_id": "EMBER",
    "payload": {
      "role": "PLAYER_1"
    },
    "timestamp": 1727000000
  },
  {
    "msg_type": "MOVE",
    "player_id": "EMBER",
    "payload": {
      "action": "FIRE",
      "row": 0,
      "col": 2
    },
    "timestamp": 1727000005
  },
  {
    "msg_type": "MOVE",
    "player_id": "EMBER",
    "payload": {
      "action": "USE_POWERUP",
      "powerup": "NUKE",
      "row": 3,
      "col": 3
    },
    "timestamp": 1727000010
  },
  {
    "msg_type": "MOVE",
    "player_id": "EMBER",
    "payload": {
      "action": "PLACE_SHIPS",
      "ships": [
        {
          "length": 2,
          "row": 0,
          "col": 0,
          "orientation": "HORIZONTAL"
        },
        {
          "length": 3,
          "row": 2,
          "col": 0,
          "orientation": "HORIZONTAL"
        },
        {
          "length": 4,
          "row": 4,
          "col": 0,
          "orientation": "HORIZONTAL"
        }
      ],
      "powerups": [
        {
          "type": "NUKE",
          "row": 1,
          "col": 5
        },
        {
          "type": "EMP",
          "row": 2,
          "col": 5
        },
        {
          "type": "RADAR",
          "row": 3,
          "col": 5
        },
        {
          "type": "SHIELD",
          "row": 4,
          "col": 5
        },
        {
          "type": "EXTRA_SHOT",
          "row": 5,
          "col": 5
        }
      ]
    },
    "timestamp": 1727000002
  },
  {
    "msg_type": "STATE_UPDATE",
    "player_id": "EMBER",
    "payload": {
      "board_state": "...",
      "player_1_score": 0,
      "player_2_score": 0,
      "active_player": "PLAYER_2"
    },
    "timestamp": 1727000005
  },
  {
    "msg_type": "ERROR",
    "payload": {
      "error_message": "OUT_OF_TURN",
      "message": "it is not your turn"
    },
    "timestamp": 1727000005
  },
  {
    "msg_type": "DISCONNECT",
    "payload": {
      "reason": "QUIT"
    },
    "timestamp": 1727000005
  },
  {
    "msg_type": "GAME_OVER",
    "payload": {
      "outcome": "WINNER",
      "winner": "PLAYER_1",
      "player_1_score": 9,
      "player_2_score": 0
    },
    "timestamp": 1727000005
  },
  {
    "msg_type": "GAME_OVER",
    "payload": {
      "outcome": "FORFEIT",
      "forfeiting_player": "PLAYER_2",
      "player_1_score": 3,
      "player_2_score": 1,
      "winner": "PLAYER_1"
    },
    "timestamp": 1727000005
  }
]
```
## STATE_UPDATE Payload

The server sends a separate update to each player. All fields below
are required; board and inventory information is specific to the recipient.

| Field | Type and meaning |
|---|---|
| phase | String: SETUP, PLAYING, or GAME_OVER |
| role | String: recipient's PLAYER_1 or PLAYER_2 role |
| setup_accepted | Boolean: whether the recipient's placement was accepted |
| board_state | Object containing own_board and target_board, defined below |
| inventory | Array of power-up strings: NUKE, EMP, RADAR, SHIELD, EXTRA_SHOT |
| usable_powerups | Array of inventory items eligible for activation now |
| player_1_score | Integer 0–9 |
| player_2_score | Integer 0–9 |
| active_player | PLAYER_1 or PLAYER_2 during play; null otherwise |
| attacks_remaining | Integer 0–2 for the active player; 0 outside gameplay |
| radar_result | null, or an object with row, col, and count |

### Board Format

own_board and target_board are each arrays of eight arrays,
each containing eight strings. Access cells as [row][col].

own_board cell values:
- WATER: unattacked empty square.
- SHIP: undamaged ship square.
- SHIELDED: undamaged ship square protected by a Shield.
- HIT: destroyed ship square.
- MISS: attacked empty square.
- NUKE, EMP, RADAR, SHIELD, EXTRA_SHOT: uncollected hidden item.
- COLLECTED: square whose hidden item was collected.

target_board cell values:
- UNKNOWN: unattacked square; does not reveal its contents.
- HIT: destroyed enemy ship square.
- MISS: attacked empty square.
- COLLECTED: discovered power-up square.
- BLOCKED: a Shield blocked the attack; this square may be attacked again.

Before setup is accepted, own_board contains only WATER.
target_board initially contains only UNKNOWN.

### Update Rules

- When the second player connects, send both players a SETUP update.
  This tells each client its role and requests PLACE_SHIPS.
- After accepting a placement, send that player an update with
  setup_accepted set to true.
- Once both setups are accepted, send GAME_START, followed by a
  PLAYING update with PLAYER_1 active.
- Send updates after every valid gameplay action, after resolving
  its effects and determining who acts next.
- Apply Extra Shot and EMP turn effects according to the README.
- inventory contains unused collected items. usable_powerups excludes
  items collected this turn and is empty when activation is not allowed.
- A successful Radar action sets radar_result for its user only:
  row and col are center coordinates (integers 1–6), and count is
  the number of undestroyed ship squares in the area (integer 0–9).
  Otherwise radar_result is null.
- On a winning action, send a GAME_OVER phase update, then GAME_OVER.
  For disconnects, send GAME_OVER directly to the remaining player.
- Never send the opponent's hidden board or private Radar result.

## Connection-Liveness Rule

- Enable TCP keepalive on client and server connections.
- Configure keepalive to start after 30 seconds of network inactivity,
  retry every 10 seconds, and fail after 3 unanswered probes.
- Keepalive probes are handled by TCP and are not JSON messages.
- When TCP reports a failed connection, catch the socket OSError,
  stop processing that connection, and perform disconnect cleanup.
- A player taking time to choose a move is not a disconnect:
  a functioning connection answers TCP keepalive probes automatically.
- A short receive timeout used to check timers does not, by itself,
  cause a forfeit.
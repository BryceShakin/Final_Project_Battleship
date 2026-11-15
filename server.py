import json
import time
import argparse
import selectors
import socket


def accept_connection(server_socket, selector):
    """Accept and register a new client connection."""
    client_socket, address = server_socket.accept()

    # Configure the connection for non-blocking I/O
    client_socket.setblocking(False)

    # Register the client for incoming data
    selector.register(
    client_socket,
    selectors.EVENT_READ,
    data={
        "buffer": bytearray(),
        "outgoing": bytearray(),
        "player_id": None
    }
)

    print(f"[CONNECTED] Client: {address}")

def handle_client(client_socket, selector, players):
    """Receive and parse newline-delimited JSON messages."""
    try:
        data = client_socket.recv(4096)

        if not data:
            print("[DISCONNECTED] Client closed connection")
            selector.unregister(client_socket)
            client_socket.close()
            return

        # Retrieve this client's receive buffer
        connection = selector.get_key(client_socket).data
        connection["buffer"].extend(data)

        # Process all complete newline-delimited messages
        while b"\n" in connection["buffer"]:
            line, _, remaining = connection["buffer"].partition(b"\n")
            connection["buffer"] = bytearray(remaining)

            try:
                message = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                print("[ERROR] Malformed JSON message")
                continue

            if not isinstance(message, dict):
                print("[ERROR] Expected a JSON object")
                continue

            print(f"[MESSAGE] {message}")

                        
                        
            if message.get("msg_type") == "CONNECT":
                player_id = message.get("player_id")
                timestamp = message.get("timestamp")

                if (
                    set(message) != {"msg_type", "player_id", "timestamp"}
                    or not isinstance(player_id, str)
                    or not player_id.strip()
                    or type(timestamp) is not int
                    or timestamp < 0
                ):
                    queue_message(client_socket, selector, {
                        "msg_type": "ERROR",
                        "timestamp": int(time.time()),
                        "payload": {
                            "error_message": "MALFORMED_MESSAGE",
                            "message": "Invalid CONNECT message"
                        }
                    })
                    continue

                existing_names = [
                    selector.get_key(sock).data["player_id"]
                    for sock in players
                ]

                if (
                    connection["player_id"] is not None
                    or player_id in existing_names
                    or len(players) >= 2
                ):
                    queue_message(client_socket, selector, {
                        "msg_type": "ERROR",
                        "timestamp": int(time.time()),
                        "payload": {
                            "error_message": "INVALID_ACTION",
                            "message": "Lobby full or player already registered"
                        }
                    })
                    continue

                connection["player_id"] = player_id
                connection["role"] = f"PLAYER_{len(players) + 1}"
                players.append(client_socket)

                print(f"[LOBBY] {player_id} joined as {connection['role']}")

                if len(players) == 1:
                    queue_message(client_socket, selector, {
                        "msg_type": "LOBBY_WAIT",
                        "player_id": player_id,
                        "status": "waiting for player 2",
                        "timestamp": int(time.time())
                    })

                elif len(players) == 2:
                    print("[GAME] Both players connected. Entering SETUP.")

                    for player_socket in players:
                        player = selector.get_key(player_socket).data

                        update = create_setup_update(
                            player["player_id"],
                            player["role"]
                        )

                        queue_message(player_socket, selector, update)
            
            
            elif message.get("msg_type") == "MOVE":
                payload = message.get("payload")

                if isinstance(payload, dict):
                    action = payload.get("action")
                else:
                    action = None

                if action == "PLACE_SHIPS":
                    handle_place_ships(
                        client_socket, selector, players, message
                    )

                elif action == "FIRE":
                    handle_fire(
                        client_socket, selector, players, message
                    )

                elif action == "USE_POWERUP":
                    if payload.get("powerup") == "EXTRA_SHOT":
                        handle_extra_shot(
                            client_socket, selector, players, message
                        )

                    elif payload.get("powerup") == "NUKE":
                        handle_nuke(
                            client_socket, selector, players, message
                        )
                    elif payload.get("powerup") == "EMP":
                        handle_emp(
                            client_socket, selector, players, message
                        )
                    elif payload.get("powerup") == "RADAR":
                        handle_radar(
                            client_socket, selector, players, message
                        )              
                    elif payload.get("powerup") == "SHIELD":
                        handle_shield(
                            client_socket, selector, players, message
                        )


                    else:
                        send_error(
                            client_socket, selector,
                            "INVALID_ACTION",
                            "Power-up not implemented yet"
                        )


                else:
                    send_error(
                        client_socket,
                        selector,
                        "INVALID_ACTION",
                        "Unknown or unsupported action"
                    )


            


    
    except BlockingIOError:
    # No data available yet; keep the connection open
        return

    except OSError as error:
        print(f"[ERROR] Client connection: {error}")
        try:
            selector.unregister(client_socket)
        except (KeyError, ValueError):
            pass
        client_socket.close()


def queue_message(client_socket, selector, message):
    """Queue a JSON message for non-blocking transmission."""
    connection = selector.get_key(client_socket).data

    encoded = (json.dumps(message) + "\n").encode("utf-8")
    connection["outgoing"].extend(encoded)

    selector.modify(
        client_socket,
        selectors.EVENT_READ | selectors.EVENT_WRITE,
        data=connection
    )

    print(f"[QUEUED] {message['msg_type']}")




def write_client(client_socket, selector):
    """Send queued messages when the socket is writable."""
    try:
        connection = selector.get_key(client_socket).data

        if not connection["outgoing"]:
            selector.modify(
                client_socket,
                selectors.EVENT_READ,
                data=connection
            )
            return

        sent = client_socket.send(connection["outgoing"])

        print(f"[SENT] {sent} bytes to client")

        del connection["outgoing"][:sent]

        if not connection["outgoing"]:
            selector.modify(
                client_socket,
                selectors.EVENT_READ,
                data=connection
            )

    except BlockingIOError:
        return

    except OSError as error:
        print(f"[ERROR] Sending to client: {error}")
        try:
            selector.unregister(client_socket)
        except (KeyError, ValueError):
            pass
        client_socket.close()



def create_setup_update(player_id, role):
    """Create the initial game setup state for a player."""
    return {
        "msg_type": "STATE_UPDATE",
        "player_id": player_id,
        "timestamp": int(time.time()),
        "payload": {
            "phase": "SETUP",
            "role": role,
            "setup_accepted": False,
            "board_state": {
                "own_board": [
                    ["WATER"] * 8 for _ in range(8)
                ],
                "target_board": [
                    ["UNKNOWN"] * 8 for _ in range(8)
                ]
            },
            "inventory": [],
            "usable_powerups": [],
            "player_1_score": 0,
            "player_2_score": 0,
            "active_player": None,
            "attacks_remaining": 0,
            "radar_result": None
        }
    }



def validate_setup(ships, powerups):
    """Validate a player's complete Battleship setup."""
    if not isinstance(ships, list) or len(ships) != 3:
        raise ValueError("Exactly 3 ships are required")

    if not isinstance(powerups, list) or len(powerups) != 5:
        raise ValueError("Exactly 5 power-ups are required")

    occupied = set()
    ship_squares = set()
    ship_lengths = []

    for ship in ships:
        if not isinstance(ship, dict) or set(ship) != {
            "length", "row", "col", "orientation"
        }:
            raise ValueError("Invalid ship fields")

        length = ship["length"]
        row = ship["row"]
        col = ship["col"]
        orientation = ship["orientation"]

        if any(type(x) is not int for x in (length, row, col)):
            raise ValueError("Ship coordinates and length must be integers")

        if length not in (2, 3, 4):
            raise ValueError("Invalid ship length")

        if orientation not in ("HORIZONTAL", "VERTICAL"):
            raise ValueError("Invalid ship orientation")

        ship_lengths.append(length)

        for offset in range(length):
            r = row + (offset if orientation == "VERTICAL" else 0)
            c = col + (offset if orientation == "HORIZONTAL" else 0)

            if not (0 <= r < 8 and 0 <= c < 8):
                raise ValueError("Ship extends outside the board")

            if (r, c) in occupied:
                raise ValueError("Ship placement overlaps another object")

            occupied.add((r, c))
            ship_squares.add((r, c))

    if sorted(ship_lengths) != [2, 3, 4]:
        raise ValueError("Ships must have lengths 2, 3, and 4")

    allowed_powerups = {
        "NUKE", "EMP", "RADAR", "SHIELD", "EXTRA_SHOT"
    }

    placed_powerups = {}

    for item in powerups:
        if not isinstance(item, dict) or set(item) != {
            "type", "row", "col"
        }:
            raise ValueError("Invalid power-up fields")

        name = item["type"]
        row = item["row"]
        col = item["col"]

        if name not in allowed_powerups:
            raise ValueError("Unknown power-up")

        if type(row) is not int or type(col) is not int:
            raise ValueError("Power-up coordinates must be integers")

        if not (0 <= row < 8 and 0 <= col < 8):
            raise ValueError("Power-up outside the board")

        if (row, col) in occupied:
            raise ValueError("Power-up placement overlaps another object")

        occupied.add((row, col))
        placed_powerups[(row, col)] = name

    if set(placed_powerups.values()) != allowed_powerups:
        raise ValueError("Each power-up type must appear exactly once")

    return ship_squares, placed_powerups


def send_error(client_socket, selector, code, description):
    """Send a protocol-compliant ERROR message."""
    message = {
        "msg_type": "ERROR",
        "timestamp": int(time.time()),
        "payload": {
            "error_message": code,
            "message": description
        }
    }

    queue_message(client_socket, selector, message)


def handle_place_ships(client_socket, selector, players, message):
    """Validate and save one player's ship placement."""
    connection = selector.get_key(client_socket).data
    payload = message.get("payload")

    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(payload, dict)
        or set(payload) != {"action", "ships", "powerups"}
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid PLACE_SHIPS message format"
        )
        return

    if connection["player_id"] != message["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    if len(players) != 2 or connection.get("setup_accepted", False):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Ship placement is not allowed right now"
        )
        return

    try:
        ship_squares, placed_powerups = validate_setup(
            payload["ships"],
            payload["powerups"]
        )

    except ValueError as error:
        send_error(
            client_socket, selector,
            "INVALID_SETUP",
            str(error)
        )
        return

    # Save the accepted placement
    connection["ship_squares"] = ship_squares
    connection["placed_powerups"] = placed_powerups
    connection["setup_accepted"] = True

    print(f"[SETUP] {connection['player_id']} placed ships.")

    update = create_setup_update(
        connection["player_id"],
        connection["role"]
    )

    update["payload"]["setup_accepted"] = True

    own_board = update["payload"]["board_state"]["own_board"]

    for row, col in ship_squares:
        own_board[row][col] = "SHIP"

    for (row, col), powerup in placed_powerups.items():
        own_board[row][col] = powerup

    queue_message(client_socket, selector, update)
        # Check whether both players finished setup
    if all(
        selector.get_key(sock).data.get("setup_accepted", False)
        for sock in players
    ):
        start_game(selector, players)



def start_game(selector, players):
    """Start gameplay after both players finish setup."""

    print("[GAME] Both setups accepted. Starting game!")

    # Shared game state for both players
    match = {
        "phase": "PLAYING",
        "active_player": "PLAYER_1",
        "attacks_remaining": 1,
        "player_1_score": 0,
        "player_2_score": 0
    }

    # Initialize each player's boards
    for player_socket in players:
        connection = selector.get_key(player_socket).data

        connection["match"] = match

        own_board = [
            ["WATER"] * 8 for _ in range(8)
        ]

        for row, col in connection["ship_squares"]:
            own_board[row][col] = "SHIP"

        for (row, col), powerup in (
            connection["placed_powerups"].items()
        ):
            own_board[row][col] = powerup

        connection["own_board"] = own_board
        connection["target_board"] = [
            ["UNKNOWN"] * 8 for _ in range(8)
        ]

    # Send GAME_START and PLAYING updates to both clients
    for player_socket in players:
        connection = selector.get_key(player_socket).data

        start_message = {
            "msg_type": "GAME_START",
            "player_id": connection["player_id"],
            "timestamp": int(time.time()),
            "payload": {
                "role": connection["role"]
            }
        }

        queue_message(
            player_socket, selector, start_message
        )

        update = create_setup_update(
            connection["player_id"],
            connection["role"]
        )

        payload = update["payload"]

        payload["phase"] = "PLAYING"
        payload["setup_accepted"] = True
        payload["board_state"] = {
            "own_board": connection["own_board"],
            "target_board": connection["target_board"]
        }
        payload["active_player"] = "PLAYER_1"

        payload["attacks_remaining"] = (
            1 if connection["role"] == "PLAYER_1" else 0
        )

        queue_message(
            player_socket, selector, update
        )

    print("[GAME] PLAYER_1's turn!")


def send_game_updates(
        selector, players, radar_user=None, radar_result=None
):
    """Send the current game state to both players."""
    match = selector.get_key(players[0]).data["match"]

    for player_socket in players:
        connection = selector.get_key(player_socket).data

        update = create_setup_update(
            connection["player_id"],
            connection["role"]
        )

        payload = update["payload"]
        payload["phase"] = match["phase"]
        payload["setup_accepted"] = True

        payload["board_state"] = {
            "own_board": connection["own_board"],
            "target_board": connection["target_board"]
        }

        inventory = connection.get("inventory", [])
        payload["inventory"] = inventory.copy()

        can_use_powerup = (
            match["phase"] == "PLAYING"
            and match["active_player"] == connection["role"]
            and not connection.get("attacked_this_turn", False)
            and not connection.get("powerup_used_this_turn", False)
        )

        payload["usable_powerups"] = (
            [
                item for item in inventory
                if item not in connection.get("newly_collected", set())
            ]
            if can_use_powerup else []
        )

        payload["player_1_score"] = match["player_1_score"]
        payload["player_2_score"] = match["player_2_score"]

        payload["active_player"] = (
            match["active_player"]
            if match["phase"] == "PLAYING" else None
        )

        payload["attacks_remaining"] = (
            match["attacks_remaining"]
            if match["phase"] == "PLAYING"
            and match["active_player"] == connection["role"]
            else 0
        )
        # Only send Radar results to the player who used it
        payload["radar_result"] = (
            radar_result if player_socket is radar_user else None
        )

        queue_message(player_socket, selector, update)


def handle_fire(client_socket, selector, players, message):
    """Validate and perform a normal FIRE action."""
    attacker = selector.get_key(client_socket).data
    payload = message.get("payload")

    # Validate the message format and field types
    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or message.get("msg_type") != "MOVE"
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(message.get("player_id"), str)
        or not isinstance(payload, dict)
        or set(payload) != {"action", "row", "col"}
        or payload.get("action") != "FIRE"
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid FIRE message format"
        )
        return

    if message["player_id"] != attacker["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    if len(players) != 2 or "match" not in attacker:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game has not started"
        )
        return

    match = attacker["match"]

    if match["phase"] != "PLAYING":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game is not in the PLAYING phase"
        )
        return

    if match["active_player"] != attacker["role"]:
        send_error(
            client_socket, selector,
            "OUT_OF_TURN",
            "It is not your turn"
        )
        return

    row = payload["row"]
    col = payload["col"]

    if type(row) is not int or type(col) is not int:
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Coordinates must be integers"
        )
        return

    if not (0 <= row < 8 and 0 <= col < 8):
        send_error(
            client_socket, selector,
            "INVALID_COORDINATES",
            "Coordinates must be between 0 and 7"
        )
        return
    if (
        connection_target := (row, col)
    ) in attacker.get("extra_shot_targets", set()):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Extra Shot requires different coordinates"
        )
        return
    if match["attacks_remaining"] <= 0:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "No attacks remaining"
        )
        return

    if attacker["target_board"][row][col] not in (
        "UNKNOWN", "BLOCKED"
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "This coordinate has already been resolved"
        )
        return

    # Find the opponent
    defender_socket = next(
        sock for sock in players if sock is not client_socket
    )
    defender = selector.get_key(defender_socket).data

    target = defender["own_board"][row][col]
    result = "MISS"

    if target == "SHIP":
        result = "HIT"

        defender["own_board"][row][col] = "HIT"
        attacker["target_board"][row][col] = "HIT"

        score_key = attacker["role"].lower() + "_score"
        match[score_key] += 1

    elif target == "SHIELDED":
        result = "BLOCKED"

        defender["own_board"][row][col] = "SHIP"
        attacker["target_board"][row][col] = "BLOCKED"

    elif target in (
        "NUKE", "EMP", "RADAR", "SHIELD", "EXTRA_SHOT"
    ):
        result = "COLLECTED"

        attacker.setdefault("inventory", []).append(target)
        attacker.setdefault("newly_collected", set()).add(target)

        defender["own_board"][row][col] = "COLLECTED"
        attacker["target_board"][row][col] = "COLLECTED"

    else:
        defender["own_board"][row][col] = "MISS"
        attacker["target_board"][row][col] = "MISS"

    print(
        f"[FIRE] {attacker['player_id']} attacked "
        f"({row}, {col}) -> {result}"
    )

    attacker["attacked_this_turn"] = True

    if attacker.get("extra_shot_active", False):
        attacker["extra_shot_targets"].add((row, col))

    match["attacks_remaining"] -= 1
    # Check victory before changing turns
    score_key = attacker["role"].lower() + "_score"

    if match[score_key] == 9:
        match["phase"] = "GAME_OVER"
        match["attacks_remaining"] = 0

        send_game_updates(selector, players)

        for sock in players:
            game_over = {
                "msg_type": "GAME_OVER",
                "timestamp": int(time.time()),
                "payload": {
                    "outcome": "WINNER",
                    "winner": attacker["role"],
                    "player_1_score": match["player_1_score"],
                    "player_2_score": match["player_2_score"]
                }
            }
            queue_message(sock, selector, game_over)

        print(f"[GAME OVER] {attacker['player_id']} wins!")
        return

    # Move to the next player when attacks are exhausted

    
    if match["attacks_remaining"] == 0:
        next_role = (
            "PLAYER_2"
            if attacker["role"] == "PLAYER_1"
            else "PLAYER_1"
        )

        # Find the player who would normally go next
        next_player = next(
            selector.get_key(sock).data
            for sock in players
            if selector.get_key(sock).data["role"] == next_role
        )

        # EMP skips the opponent's next turn
        if next_player.pop("skip_next_turn", False):
            print(
                f"[EMP] {next_player['player_id']} "
                "skips their turn!"
            )

            # Return the turn to the current attacker
            next_role = attacker["role"]

        match["active_player"] = next_role
        match["attacks_remaining"] = 1

        # Reset the next active player's turn flags
        for sock in players:
            player = selector.get_key(sock).data

            if player["role"] == next_role:
                player["attacked_this_turn"] = False
                player["powerup_used_this_turn"] = False
                player["newly_collected"] = set()
                player["extra_shot_active"] = False
                player["extra_shot_targets"] = set()
                break

    send_game_updates(selector, players)



def handle_extra_shot(client_socket, selector, players, message):
    """Activate the EXTRA_SHOT power-up."""
    connection = selector.get_key(client_socket).data
    payload = message.get("payload")

    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(message.get("player_id"), str)
        or not isinstance(payload, dict)
        or set(payload) != {"action", "powerup"}
        or payload.get("action") != "USE_POWERUP"
        or payload.get("powerup") != "EXTRA_SHOT"
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid EXTRA_SHOT message"
        )
        return

    if message["player_id"] != connection["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    match = connection.get("match")

    if not match or match["phase"] != "PLAYING":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game is not currently playing"
        )
        return

    if match["active_player"] != connection["role"]:
        send_error(
            client_socket, selector,
            "OUT_OF_TURN",
            "It is not your turn"
        )
        return

    if (
        connection.get("attacked_this_turn", False)
        or connection.get("powerup_used_this_turn", False)
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Power-ups must be activated before attacking"
        )
        return

    if (
        "EXTRA_SHOT" not in connection.get("inventory", [])
        or "EXTRA_SHOT" in connection.get("newly_collected", set())
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "EXTRA_SHOT is not available"
        )
        return

    connection["inventory"].remove("EXTRA_SHOT")
    connection["powerup_used_this_turn"] = True
    connection["extra_shot_active"] = True
    connection["extra_shot_targets"] = set()

    match["attacks_remaining"] = 2

    print(f"[POWER-UP] {connection['player_id']} activated EXTRA_SHOT")

    send_game_updates(selector, players)



def handle_nuke(client_socket, selector, players, message):
    """Activate NUKE against a plus-shaped enemy area."""
    attacker = selector.get_key(client_socket).data
    payload = message.get("payload")

    # Validate the JSON message structure
    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or message.get("msg_type") != "MOVE"
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(message.get("player_id"), str)
        or not isinstance(payload, dict)
        or set(payload) != {"action", "powerup", "row", "col"}
        or payload.get("action") != "USE_POWERUP"
        or payload.get("powerup") != "NUKE"
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid NUKE message format"
        )
        return

    if message["player_id"] != attacker["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    match = attacker.get("match")

    if len(players) != 2 or not match or match["phase"] != "PLAYING":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game is not currently playing"
        )
        return

    if match["active_player"] != attacker["role"]:
        send_error(
            client_socket, selector,
            "OUT_OF_TURN",
            "It is not your turn"
        )
        return

    if (
        attacker.get("attacked_this_turn", False)
        or attacker.get("powerup_used_this_turn", False)
        or match["attacks_remaining"] != 1
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "NUKE must replace your normal attack"
        )
        return

    if (
        "NUKE" not in attacker.get("inventory", [])
        or "NUKE" in attacker.get("newly_collected", set())
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "NUKE is not available"
        )
        return

    row = payload["row"]
    col = payload["col"]

    if type(row) is not int or type(col) is not int:
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Coordinates must be integers"
        )
        return

    if not (0 <= row < 8 and 0 <= col < 8):
        send_error(
            client_socket, selector,
            "INVALID_COORDINATES",
            "Coordinates must be between 0 and 7"
        )
        return

    # Center, above, below, left, and right
    potential_targets = [
        (row, col),
        (row - 1, col),
        (row + 1, col),
        (row, col - 1),
        (row, col + 1)
    ]

    # Ignore squares outside the board or already resolved
    targets = [
        (r, c)
        for r, c in potential_targets
        if 0 <= r < 8
        and 0 <= c < 8
        and attacker["target_board"][r][c] in ("UNKNOWN", "BLOCKED")
    ]

    if not targets:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "No attackable squares in NUKE area"
        )
        return

    defender_socket = next(
        sock for sock in players if sock is not client_socket
    )
    defender = selector.get_key(defender_socket).data

    # All validation passed: consume NUKE
    attacker["inventory"].remove("NUKE")
    attacker["powerup_used_this_turn"] = True
    attacker["attacked_this_turn"] = True
    match["attacks_remaining"] = 0

    score_key = attacker["role"].lower() + "_score"

    print(f"[NUKE] {attacker['player_id']} targeted ({row}, {col})")

    for r, c in targets:
        target = defender["own_board"][r][c]

        if target == "SHIP":
            result = "HIT"
            defender["own_board"][r][c] = "HIT"
            attacker["target_board"][r][c] = "HIT"
            match[score_key] += 1

        elif target == "SHIELDED":
            result = "BLOCKED"
            defender["own_board"][r][c] = "SHIP"
            attacker["target_board"][r][c] = "BLOCKED"

        elif target in (
            "NUKE", "EMP", "RADAR", "SHIELD", "EXTRA_SHOT"
        ):
            result = "COLLECTED"
            attacker.setdefault("inventory", []).append(target)
            attacker.setdefault("newly_collected", set()).add(target)
            defender["own_board"][r][c] = "COLLECTED"
            attacker["target_board"][r][c] = "COLLECTED"

        else:
            result = "MISS"
            defender["own_board"][r][c] = "MISS"
            attacker["target_board"][r][c] = "MISS"

        print(f"[NUKE] ({r}, {c}) -> {result}")

        # End immediately if the final ship square is destroyed
        if match[score_key] == 9:
            match["phase"] = "GAME_OVER"
            send_game_updates(selector, players)

            for sock in players:
                queue_message(sock, selector, {
                    "msg_type": "GAME_OVER",
                    "timestamp": int(time.time()),
                    "payload": {
                        "outcome": "WINNER",
                        "winner": attacker["role"],
                        "player_1_score": match["player_1_score"],
                        "player_2_score": match["player_2_score"]
                    }
                })

            print(f"[GAME OVER] {attacker['player_id']} wins!")
            return

    # NUKE ends the current turn
    next_role = (
        "PLAYER_2"
        if attacker["role"] == "PLAYER_1"
        else "PLAYER_1"
    )

    match["active_player"] = next_role
    match["attacks_remaining"] = 1

    for sock in players:
        player = selector.get_key(sock).data

        if player["role"] == next_role:
            player["attacked_this_turn"] = False
            player["powerup_used_this_turn"] = False
            player["newly_collected"] = set()
            player["extra_shot_active"] = False
            player["extra_shot_targets"] = set()
            break

    send_game_updates(selector, players)


def handle_emp(client_socket, selector, players, message):
    """Activate EMP to skip the opponent's next turn."""
    attacker = selector.get_key(client_socket).data
    payload = message.get("payload")

    # Validate the message structure
    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(message.get("player_id"), str)
        or not isinstance(payload, dict)
        or set(payload) != {"action", "powerup"}
        or payload.get("action") != "USE_POWERUP"
        or payload.get("powerup") != "EMP"
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid EMP message format"
        )
        return

    if message["player_id"] != attacker["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    match = attacker.get("match")

    if len(players) != 2 or not match or match["phase"] != "PLAYING":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game is not currently playing"
        )
        return

    if match["active_player"] != attacker["role"]:
        send_error(
            client_socket, selector,
            "OUT_OF_TURN",
            "It is not your turn"
        )
        return

    if (
        attacker.get("attacked_this_turn", False)
        or attacker.get("powerup_used_this_turn", False)
        or match["attacks_remaining"] != 1
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "EMP must be activated before attacking"
        )
        return

    if (
        "EMP" not in attacker.get("inventory", [])
        or "EMP" in attacker.get("newly_collected", set())
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "EMP is not available"
        )
        return

    # Find the opponent
    defender_socket = next(
        sock for sock in players if sock is not client_socket
    )
    defender = selector.get_key(defender_socket).data

    # Activate EMP
    attacker["inventory"].remove("EMP")
    attacker["powerup_used_this_turn"] = True

    # Opponent must skip their next turn
    defender["skip_next_turn"] = True

    print(
        f"[EMP] {attacker['player_id']} activated EMP. "
        f"{defender['player_id']} will skip a turn."
    )

    # EMP does not consume the normal attack
    send_game_updates(selector, players)



def handle_radar(client_socket, selector, players, message):
    """Scan a 3x3 area for undestroyed enemy ship squares."""
    attacker = selector.get_key(client_socket).data
    payload = message.get("payload")

    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(message.get("player_id"), str)
        or not isinstance(payload, dict)
        or set(payload) != {"action", "powerup", "row", "col"}
        or payload.get("action") != "USE_POWERUP"
        or payload.get("powerup") != "RADAR"
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid RADAR message format"
        )
        return

    if message["player_id"] != attacker["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    match = attacker.get("match")

    if len(players) != 2 or not match or match["phase"] != "PLAYING":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game is not currently playing"
        )
        return

    if match["active_player"] != attacker["role"]:
        send_error(
            client_socket, selector,
            "OUT_OF_TURN",
            "It is not your turn"
        )
        return

    if (
        attacker.get("attacked_this_turn", False)
        or attacker.get("powerup_used_this_turn", False)
        or match["attacks_remaining"] != 1
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "RADAR must replace your normal attack"
        )
        return

    if (
        "RADAR" not in attacker.get("inventory", [])
        or "RADAR" in attacker.get("newly_collected", set())
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "RADAR is not available"
        )
        return

    row = payload["row"]
    col = payload["col"]

    if type(row) is not int or type(col) is not int:
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Coordinates must be integers"
        )
        return

    # A full 3x3 scan must fit inside the board
    if not (1 <= row <= 6 and 1 <= col <= 6):
        send_error(
            client_socket, selector,
            "INVALID_COORDINATES",
            "RADAR center must be between 1 and 6"
        )
        return

    defender_socket = next(
        sock for sock in players if sock is not client_socket
    )
    defender = selector.get_key(defender_socket).data

    # Count undestroyed ship squares, including shielded ones
    count = 0

    for r in range(row - 1, row + 2):
        for c in range(col - 1, col + 2):
            if defender["own_board"][r][c] in (
                "SHIP", "SHIELDED"
            ):
                count += 1

    radar_result = {
        "row": row,
        "col": col,
        "count": count
    }

    # Valid activation consumes the power-up and the turn
    attacker["inventory"].remove("RADAR")
    attacker["powerup_used_this_turn"] = True
    attacker["attacked_this_turn"] = True
    match["attacks_remaining"] = 0

    print(
        f"[RADAR] {attacker['player_id']} scanned "
        f"({row}, {col}) -> {count} ship squares"
    )

    # Determine who takes the next turn
    next_role = (
        "PLAYER_2"
        if attacker["role"] == "PLAYER_1"
        else "PLAYER_1"
    )

    # Respect any pending EMP turn skip
    if defender.pop("skip_next_turn", False):
        print(f"[EMP] {defender['player_id']} skips their turn!")
        next_role = attacker["role"]

    match["active_player"] = next_role
    match["attacks_remaining"] = 1

    for sock in players:
        player = selector.get_key(sock).data

        if player["role"] == next_role:
            player["attacked_this_turn"] = False
            player["powerup_used_this_turn"] = False
            player["newly_collected"] = set()
            player["extra_shot_active"] = False
            player["extra_shot_targets"] = set()
            break

    send_game_updates(
        selector,
        players,
        radar_user=client_socket,
        radar_result=radar_result
    )



def handle_shield(client_socket, selector, players, message):
    """Protect one undamaged, unshielded ship square."""
    attacker = selector.get_key(client_socket).data
    payload = message.get("payload")

    # Validate message structure
    if (
        set(message) != {"msg_type", "player_id", "timestamp", "payload"}
        or type(message.get("timestamp")) is not int
        or message["timestamp"] < 0
        or not isinstance(message.get("player_id"), str)
        or not isinstance(payload, dict)
        or set(payload) != {"action", "powerup", "row", "col"}
        or payload.get("action") != "USE_POWERUP"
        or payload.get("powerup") != "SHIELD"
    ):
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Invalid SHIELD message format"
        )
        return

    if message["player_id"] != attacker["player_id"]:
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Player identity does not match connection"
        )
        return

    match = attacker.get("match")

    if len(players) != 2 or not match or match["phase"] != "PLAYING":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "Game is not currently playing"
        )
        return

    if match["active_player"] != attacker["role"]:
        send_error(
            client_socket, selector,
            "OUT_OF_TURN",
            "It is not your turn"
        )
        return

    if (
        attacker.get("attacked_this_turn", False)
        or attacker.get("powerup_used_this_turn", False)
        or match["attacks_remaining"] != 1
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "SHIELD must replace your normal attack"
        )
        return

    if (
        "SHIELD" not in attacker.get("inventory", [])
        or "SHIELD" in attacker.get("newly_collected", set())
    ):
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "SHIELD is not available"
        )
        return

    row = payload["row"]
    col = payload["col"]

    if type(row) is not int or type(col) is not int:
        send_error(
            client_socket, selector,
            "MALFORMED_MESSAGE",
            "Coordinates must be integers"
        )
        return

    if not (0 <= row < 8 and 0 <= col < 8):
        send_error(
            client_socket, selector,
            "INVALID_COORDINATES",
            "Coordinates must be between 0 and 7"
        )
        return

    # SHIELD only protects an undamaged, unshielded ship
    if attacker["own_board"][row][col] != "SHIP":
        send_error(
            client_socket, selector,
            "INVALID_ACTION",
            "SHIELD requires an unprotected ship square"
        )
        return

    # All validation passed: activate SHIELD
    attacker["inventory"].remove("SHIELD")
    attacker["own_board"][row][col] = "SHIELDED"
    attacker["powerup_used_this_turn"] = True
    attacker["attacked_this_turn"] = True

    match["attacks_remaining"] = 0

    print(
        f"[SHIELD] {attacker['player_id']} protected "
        f"ship square ({row}, {col})"
    )

    # Find the opponent
    defender_socket = next(
        sock for sock in players if sock is not client_socket
    )
    defender = selector.get_key(defender_socket).data

    next_role = defender["role"]

    # Respect any pending EMP skip
    if defender.pop("skip_next_turn", False):
        print(f"[EMP] {defender['player_id']} skips their turn!")
        next_role = attacker["role"]

    match["active_player"] = next_role
    match["attacks_remaining"] = 1

    # Reset the next active player's turn flags
    for sock in players:
        player = selector.get_key(sock).data

        if player["role"] == next_role:
            player["attacked_this_turn"] = False
            player["powerup_used_this_turn"] = False
            player["newly_collected"] = set()
            player["extra_shot_active"] = False
            player["extra_shot_targets"] = set()
            break

    send_game_updates(selector, players)




def main():
    parser = argparse.ArgumentParser(
        description="Battleship TCP Game Server"
    )

    parser.add_argument(
        "-p",
        type=int,
        required=True,
        help="Port number for the server"
    )

    args = parser.parse_args()

    if not 1 <= args.p <= 65535:
        parser.error("Port must be between 1 and 65535")

    selector = selectors.DefaultSelector()
    players = []

    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        server_socket.bind(("0.0.0.0", args.p))
        server_socket.listen()
        server_socket.setblocking(False)

        selector.register(
            server_socket,
            selectors.EVENT_READ
        )

        print(f"[SERVER] Listening on port {args.p}")

        
        while True:
            events = selector.select()

            for key, mask in events:
                if key.fileobj is server_socket:
                    accept_connection(server_socket, selector)
                    continue

                client_socket = key.fileobj

                if mask & selectors.EVENT_READ:
                    handle_client(client_socket, selector, players)

                if (
                    mask & selectors.EVENT_WRITE
                    and client_socket.fileno() != -1
                ):
                    write_client(client_socket, selector)


    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")

    finally:
        for key, mask in events:
            if key.fileobj is server_socket:
                accept_connection(server_socket, selector)
            else:
                if mask & selectors.EVENT_READ:
                    handle_client(key.fileobj, selector)

                if (
                    mask & selectors.EVENT_WRITE
                    and key.fileobj.fileno() != -1
                ):
                    write_client(key.fileobj, selector)


if __name__ == "__main__":
    main()

import argparse
import json
import socket
import sys
import time
import threading


def display_board(board, title):
    """Display an 8x8 Battleship board."""
    symbols = {
        "WATER": ".",
        "UNKNOWN": ".",
        "SHIP": "S",
        "SHIELDED": "G",
        "HIT": "X",
        "MISS": "O",
        "BLOCKED": "B",
        "COLLECTED": "*",
        "NUKE": "N",
        "EMP": "E",
        "RADAR": "R",
        "SHIELD": "P",
        "EXTRA_SHOT": "+"
    }

    print(f"\n{title}")
    print("    0 1 2 3 4 5 6 7")
    print("   -----------------")

    for row_number, row in enumerate(board):
        cells = [
            symbols.get(cell, "?") for cell in row
        ]
        print(f"{row_number} | " + " ".join(cells))


def display_state_update(message):
    """Display game boards, scores, and turn information."""
    payload = message["payload"]

    role = payload["role"]
    phase = payload["phase"]

    print("\n" + "=" * 40)
    print(f"BATTLESHIP - {role}")
    print(f"Phase: {phase}")
    print("=" * 40)

    boards = payload["board_state"]

    display_board(boards["own_board"], "YOUR BOARD")
    display_board(boards["target_board"], "ENEMY BOARD")

    print("\nSCORES")
    print(f"Player 1: {payload['player_1_score']}")
    print(f"Player 2: {payload['player_2_score']}")

    print(f"\nInventory: {payload['inventory']}")

    radar = payload.get("radar_result")

    if radar is not None:
        print(
            f"\nRADAR SCAN ({radar['row']}, {radar['col']}): "
            f"{radar['count']} undestroyed ship squares detected!"
        )

    if phase == "SETUP":
        if payload["setup_accepted"]:
            print("\nWaiting for opponent to finish setup...")
        else:
            print("\nPlace your ships!")

    elif phase == "PLAYING":
        if payload["active_player"] == role:
            print("\n>>> YOUR TURN! <<<")
            print(
                f"Attacks remaining: "
                f"{payload['attacks_remaining']}"
            )
            print(
                f"Available power-ups: "
                f"{payload['usable_powerups']}"
            )
        else:
            print("\nWaiting for opponent's turn...")

    print("=" * 40)






def receive_messages(client_socket):
    """Continuously receive complete JSON messages."""
    buffer = bytearray()

    try:
        while True:
            data = client_socket.recv(4096)

            if not data:
                print("\n[DISCONNECTED] Server closed connection.")
                break

            buffer.extend(data)

            while b"\n" in buffer:
                line, _, remaining = buffer.partition(b"\n")
                buffer = bytearray(remaining)

                try:
                    message = json.loads(line.decode("utf-8"))
                    if message.get("msg_type") == "STATE_UPDATE":
                        display_state_update(message)
                    else:
                        print(f"\n[SERVER RESPONSE] {message}")

                except (json.JSONDecodeError, UnicodeDecodeError):
                    print("\n[ERROR] Invalid server message")

    except OSError as error:
    # Ignore errors caused by our own socket closing
        if client_socket.fileno() == -1:
            return

        print(f"\n[ERROR] Receiving data: {error}")


def create_test_placement():
    """Create a valid Battleship setup for testing."""
    return {
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
            {"type": "NUKE", "row": 1, "col": 5},
            {"type": "EMP", "row": 2, "col": 5},
            {"type": "RADAR", "row": 3, "col": 5},
            {"type": "SHIELD", "row": 4, "col": 5},
            {"type": "EXTRA_SHOT", "row": 5, "col": 5}
        ]
    }




def main():
    parser = argparse.ArgumentParser(
        description="Battleship TCP Game Client"
    )

    parser.add_argument(
        "-i",
        required=True,
        help="Server DNS hostname"
    )

    parser.add_argument(
        "-p",
        type=int,
        required=True,
        help="Server port number"
    )

    args = parser.parse_args()

    if not 1 <= args.p <= 65535:
        parser.error("Port must be between 1 and 65535")

    # Resolve the hostname using DNS
    try:
        server_ip = socket.gethostbyname(args.i)
    except socket.gaierror:
        print(f"[ERROR] Unable to resolve DNS hostname '{args.i}'.")
        print("Check your Cisco router DNS configuration")
        print("('ip dns server' / 'ip host') or hostname spelling.")
        sys.exit(1)

    print(f"[DNS] Resolved {args.i} to {server_ip}")

    player_id = input("Enter your player name: ").strip()

    if not player_id:
        print("[ERROR] Player name cannot be empty.")
        sys.exit(1)

    # Construct the CONNECT message from Sprint 1
    connect_message = {
        "msg_type": "CONNECT",
        "player_id": player_id,
        "timestamp": int(time.time())
    }

    try:
        with socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        ) as client_socket:

            client_socket.settimeout(10)
            client_socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_KEEPALIVE,
                1
            )

            client_socket.connect((server_ip, args.p))

            print("[CONNECTED] Successfully connected to server")

            client_socket.settimeout(None)

            # JSON serialization with LF message framing
            message = json.dumps(connect_message) + "\n"
            client_socket.sendall(message.encode("utf-8"))

            print(f"[SENT] {message.strip()}")

            # Start a background thread to receive server messages
            receiver = threading.Thread(
                target=receive_messages,
                args=(client_socket,),
                daemon=True
            )

            receiver.start()


            
            while True:
                command = input(
                    "\nCommands: place | fire ROW COL | "
                    "use extra_shot | use nuke ROW COL | "
                    "use emp | use radar ROW COL | "
                    "use shield ROW COL | quit: "
                ).strip().lower()



                if command == "place":
                    placement_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": create_test_placement()
                    }

                    encoded = (
                        json.dumps(placement_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)
                    print("[SENT] PLACE_SHIPS")
                
                elif command.startswith("fire "):
                    parts = command.split()

                    if len(parts) != 3:
                        print("[ERROR] Usage: fire ROW COL")
                        continue

                    try:
                        row = int(parts[1])
                        col = int(parts[2])
                    except ValueError:
                        print("[ERROR] Coordinates must be integers")
                        continue

                    fire_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": {
                            "action": "FIRE",
                            "row": row,
                            "col": col
                        }
                    }

                    encoded = (
                        json.dumps(fire_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)
                    print(f"[SENT] FIRE ({row}, {col})")
                elif command == "use extra_shot":
                    powerup_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": {
                            "action": "USE_POWERUP",
                            "powerup": "EXTRA_SHOT"
                        }
                    }

                    encoded = (
                        json.dumps(powerup_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)

                    print("[SENT] USE_POWERUP EXTRA_SHOT")
                
                elif command.split()[:2] == ["use", "nuke"]:
                    parts = command.split()

                    if len(parts) != 4:
                        print("[ERROR] Usage: use nuke ROW COL")
                        continue

                    try:
                        row = int(parts[2])
                        col = int(parts[3])
                    except ValueError:
                        print("[ERROR] Coordinates must be integers")
                        continue

                    powerup_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": {
                            "action": "USE_POWERUP",
                            "powerup": "NUKE",
                            "row": row,
                            "col": col
                        }
                    }

                    encoded = (
                        json.dumps(powerup_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)
                    print(f"[SENT] NUKE at ({row}, {col})")
                elif command == "use emp":
                    powerup_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": {
                            "action": "USE_POWERUP",
                            "powerup": "EMP"
                        }
                    }

                    encoded = (
                        json.dumps(powerup_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)
                    print("[SENT] USE_POWERUP EMP")
                elif command.split()[:2] == ["use", "radar"]:
                    parts = command.split()

                    if len(parts) != 4:
                        print("[ERROR] Usage: use radar ROW COL")
                        continue

                    try:
                        row = int(parts[2])
                        col = int(parts[3])
                    except ValueError:
                        print("[ERROR] Coordinates must be integers")
                        continue

                    powerup_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": {
                            "action": "USE_POWERUP",
                            "powerup": "RADAR",
                            "row": row,
                            "col": col
                        }
                    }

                    encoded = (
                        json.dumps(powerup_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)
                    print(f"[SENT] RADAR at ({row}, {col})")
                elif command.split()[:2] == ["use", "shield"]:
                    parts = command.split()

                    if len(parts) != 4:
                        print("[ERROR] Usage: use shield ROW COL")
                        continue

                    try:
                        row = int(parts[2])
                        col = int(parts[3])
                    except ValueError:
                        print("[ERROR] Coordinates must be integers")
                        continue

                    powerup_message = {
                        "msg_type": "MOVE",
                        "player_id": player_id,
                        "timestamp": int(time.time()),
                        "payload": {
                            "action": "USE_POWERUP",
                            "powerup": "SHIELD",
                            "row": row,
                            "col": col
                        }
                    }

                    encoded = (
                        json.dumps(powerup_message) + "\n"
                    ).encode("utf-8")

                    client_socket.sendall(encoded)
                    print(f"[SENT] SHIELD at ({row}, {col})")




                elif command == "quit":
                    break
                else:
                    print("[ERROR] Unknown command")


            disconnect_message = {
                "msg_type": "DISCONNECT",
                "payload": {"reason": "QUIT"},
                "timestamp": int(time.time())
            }

            message = json.dumps(disconnect_message) + "\n"
            client_socket.sendall(message.encode("utf-8"))

    except OSError as error:
        print(f"[ERROR] Connection failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()

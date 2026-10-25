import socket
import threading
import json

HOST = '0.0.0.0'
PORT = 5555

clients = []
lock = threading.Lock()

def handle_client(conn, addr, player_id):
    print(f"[CONNECTED] Player {player_id} joined from {addr}")
    
    try:
        init_packet = json.dumps({"type": "INIT", "player_id": player_id})
        conn.sendall(init_packet.encode('utf-8'))
    except Exception as e:
        print(f"[ERROR] Failed to initialize Player {player_id}: {e}")
        conn.close()
        return

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            
            with lock:
                for client_conn, cid in clients:
                    if cid != player_id:
                        try:
                            client_conn.sendall(data)
                        except Exception as e:
                            print(f"[ERROR] Failed to relay data to Player {cid}: {e}")
                            
    except ConnectionResetError:
        print(f"[DISCONNECTED] Player {player_id} abruptly disconnected.")
    except Exception as e:
        print(f"[EXCEPTION] Player {player_id}: {e}")
    finally:
        conn.close()
        with lock:
            clients[:] = [c for c in clients if c[0] != conn]
            # Notify the remaining player that their opponent left
            for client_conn, cid in clients:
                try:
                    dc_packet = json.dumps({"type": "DISCONNECTED", "player_id": player_id})
                    client_conn.sendall(dc_packet.encode('utf-8'))
                except:
                    pass
        print(f"[CLOSED] Connection cleaned up for Player {player_id}.")

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((HOST, PORT))
        server.listen(2)
        print("==========================================")
        print(" MOTION KOMBAT RELAY SERVER RUNNING")
        print(f" Listening on port {PORT}...")
        print(" Waiting for 2 players to connect...")
        print("==========================================")

        while True:
            conn, addr = server.accept()
            
            with lock:
                if len(clients) >= 2:
                    print(f"[REJECTED] Room full. Connection from {addr} refused.")
                    try:
                        reject_packet = json.dumps({"type": "REJECT", "reason": "Room is full"})
                        conn.sendall(reject_packet.encode('utf-8'))
                    except:
                        pass
                    conn.close()
                    continue
                
                existing_ids = [c[1] for c in clients]
                player_id = 1 if 1 not in existing_ids else 2
                clients.append((conn, player_id))
            
            thread = threading.Thread(target=handle_client, args=(conn, addr, player_id))
            thread.daemon = True
            thread.start()
            
    except Exception as e:
        print(f"[SERVER ERROR]: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    start_server()
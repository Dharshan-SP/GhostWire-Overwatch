# 👻 GhostWire: Overwatch

**GhostWire: Overwatch** is a remote administration and monitoring tool built for cybersecurity research and ethical hacking purposes. Designed with a web-based interface, it enables control and observation of client systems in real-time.

---

## 🧠 Features

- 📺 **Live Screen Streaming** – View client screens continuously via web.
- 🎮 **Remote Command Execution** – Run terminal commands on client machines.
- 🧠 **Keylogger** – Logs keystrokes and saves them for review.
- 🎥 **Webcam Access** – View the client’s webcam feed through browser.
- 🔐 **AES-based Encryption** – Secure communication via Fernet (AES-CBC + HMAC).
- 🕵️ **Persistence Mode** – Clients automatically reconnect after disconnection.
- 🌐 **Web-Based Interface** – Flask + WebSocket server for real-time control.

---

## 💻 Tech Stack

| Component       | Stack                          |
|----------------|----------------------------------|
| Backend         | Python, Flask, WebSockets        |
| Encryption      | Cryptography (Fernet/AES-CBC)    |
| Frontend        | HTML + JavaScript (Jinja2)       |
| Real-time Comm  | WebSockets                       |
| Media Handling  | OpenCV (webcam), PIL (screen)    |
| Logging         | Text-based keystroke logger      |

---

## 📂 Project Structure


GhostWire-Overwatch/
├── app.py # Flask server (web interface)
├── client.py # Client-side agent script
├── server.py # WebSocket command server
├── keylog.txt # Stores keystroke logs
├── LICENSE # MIT License file
├── README.md # Project documentation
└── templates/ # HTML templates (Jinja2)
├── base.html
├── clients.html
├── command.html
├── display.html
├── help.html
├── index.html
├── keylogger.html
└── webcam.html
``` GhostWire-Overwatch/
├── app.py            # Flask server (web interface)
├── client.py         # Client-side agent script
├── server.py         # WebSocket command server
├── keylog.txt        # Stores keystroke logs
├── LICENSE           # MIT License file
├── README.md         # Project documentation
└── templates/        # HTML templates (Jinja2)
    ├── base.html
    ├── clients.html
    ├── command.html
    ├── display.html
    ├── help.html
    ├── index.html
    ├── keylogger.html
    └── webcam.html
```
---

## ⚠️ Legal Disclaimer

This project is **strictly for educational and research purposes**. Unauthorized use of this tool on devices you do not own or have explicit permission to control is **illegal and unethical**. Use responsibly.

---

## 🚀 Developer Mode

This version is currently in **Developer Mode**. Contributions, feedback, and issues are welcome as features continue to evolve.

---

## 📜 License

[MIT License](./LICENSE)

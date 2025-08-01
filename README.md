# 👻 GhostWire-Overwatch

GhostWire-Overwatch is a secure client-server application designed for end-to-end file transmission with automated encryption, logging, and monitoring. Built using Python, it leverages strong cryptography and real-time activity tracing to ensure safe communication.

---

## 🚀 Features

- 🔐 **AES Encryption** – Secure file transfer with symmetric AES.
- 🔗 **Client-Server Architecture** – Built with socket programming in Python.
- 📝 **Logging System** – Detailed logs of transmissions and file access.
- 📊 **Real-time Monitoring** – Tracks operations live.
- 🧪 **Tested for Reliability** – Works over LAN and localhost.

---

## 🛠 Tech Stack

- **Language**: Python 3
- **Encryption**: `cryptography` library (AES)
- **Sockets**: Python `socket` module
- **Logging**: Built-in `logging`
- **UI**: CLI-based interface (optional GUI support in future)

---

## 📂 Project Structure

```bash
GhostWire-Overwatch/
├── client.py        # Handles file selection & encrypted transmission
├── server.py        # Receives, decrypts, logs the file
├── app.py           # Driver/controller script
├── README.md
└── .gitignore

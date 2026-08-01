# RFID-Based Authentication System (Arduino Uno + Python)

## Overview
A hardware/software authentication system that pairs an **Arduino Uno** with an **MFRC522 RFID reader** and a **Python/Tkinter desktop application**. Users authenticate by scanning an RFID card; the Arduino forwards the card's UID to the PC, Python checks it against a SQLite database, and the result (GRANTED/DENIED) is sent back to the Arduino for LED/buzzer feedback.

**Important safety note:** This system does **not** automate, bypass, or otherwise interact with the Windows login/lock screen. On successful authentication it either unlocks the desktop application's own admin/session view or launches a normal, pre-approved program (Notepad, by default) — nothing more.

## Features
- RFID UID reading via MFRC522
- Serial (USB) communication between Arduino and PC
- Auto-detection of the Arduino's COM port
- SQLite-backed user database
- Real-time GUI: connection status, scanned UID, matched user, access result
- Full access-attempt logging (granted and denied)
- Admin tools: Add User, Delete User, Search Users, View Logs, Export Logs to CSV
- Green LED / Red LED / buzzer feedback patterns on the Arduino
- Fully object-oriented, type-hinted, PEP8-compliant Python codebase

## Hardware
| Component        | Notes                                   |
|-------------------|------------------------------------------|
| Arduino Uno       | Main microcontroller                    |
| MFRC522 RFID Reader | 13.56 MHz reader, SPI interface        |
| Green LED         | Access Granted indicator                |
| Red LED           | Access Denied indicator                 |
| Buzzer            | Audible feedback                        |
| USB Cable         | Serial communication + power            |
| (Optional) OLED Display | Future enhancement for on-device status |

### Wiring
| MFRC522 Pin | Arduino Uno Pin |
|-------------|-----------------|
| SDA (SS)    | D10             |
| SCK         | D13             |
| MOSI        | D11             |
| MISO        | D12             |
| RST         | D9              |
| 3.3V        | 3.3V            |
| GND         | GND             |

| Component  | Arduino Pin |
|------------|-------------|
| Green LED  | D5          |
| Red LED    | D6          |
| Buzzer     | D7          |

## Software
- Python 3.12+
- Tkinter (GUI, standard library)
- SQLite (database, standard library `sqlite3`)
- `pyserial` (serial communication)
- Arduino IDE with the `MFRC522` library installed


## Installation

1. **Arduino setup**
   - Install the Arduino IDE.
   - Install the `MFRC522` library (Library Manager → search "MFRC522" by GithubCommunity).
   - Wire the components as described above.
   - Open `Arduino/RFID_Login.ino` and upload it to the Arduino Uno.

2. **Python setup**
```bash
   cd RFID-Authentication-System/Python
   python -m venv venv
   venv\Scripts\activate        # Windows
   pip install -r ../requirements.txt
```

## How to Run
```bash
cd RFID-Authentication-System/Python
python main.py
```
1. Click **Connect** to auto-detect and connect to the Arduino.
2. Scan an RFID card on the reader.
3. The GUI displays the UID, matched user (if any), and GRANTED/DENIED result.
4. Use the **Users** tab to add/delete/search users.
5. Use the **Access Logs** tab to review history and export to CSV.

## Future Improvements
- OLED display integration for on-device status without needing the PC screen
- Multi-factor authentication (RFID + PIN)
- Encrypted database fields for sensitive data
- Web-based admin dashboard
- Support for multiple simultaneous readers/stations

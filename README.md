# 📦 Live LoadBoard Email Automation System

This system scrapes **live trucking loads** from both [123Loadboard](https://www.123loadboard.com/) and [Doft](https://www.doft.com/) every second, stores them in a MySQL database, and sends **automated load responses** via email based on user requests.

---

## 📁 Files Included

| File                   | Purpose                                        |
|------------------------|------------------------------------------------|
| `123loadboard.py`      | Real-time scraper for 123Loadboard             |
| `data_fetcher.py`      | Real-time scraper for Doft                     |
| `email_processor.py`   | Checks email and replies with load matches     |
| `senders.txt`          | Gmail/iCloud email credentials (used for sending) |
| `receivers.txt`        | Allowed email addresses who can request loads  |
| `email_changer.txt`    | Secure email that can update receivers list    |
| `run_all.bat`          | One-click launcher for Windows users           |
| `requirements.txt`     | Required Python dependencies                   |

---

## 🛠️ Setup Instructions

### 1. ✅ Install Requirements

Install Python 3.10+ and then:

```bash
pip install -r requirements.txt
playwright install
```

### 2. ✅ Add Your Email Sender (for sending load responses)

Open `senders.txt` and replace with your own email and App Password:

```text
your.email@gmail.com, your-app-password
```

🔐 For Gmail with 2FA, generate an App Password at: [Google Account App Passwords](https://myaccount.google.com/apppasswords)

### 3. ✅ Add Authorized Users (who can request loads)

Open `receivers.txt` and add emails who are allowed to send load requests:

```text
user1@example.com
dispatcher@yourcompany.com
```

✉️ These users can send structured load requests and get live replies.

### 4. ✅ Set the Secure Changer Email

Open `email_changer.txt` and add 1 trusted email address:

```text
admin@yourcompany.com
```

This email can send a message like:

```text
Subject: change receivers
Body: newemail@example.com
```

To automatically add a new authorized receiver.

### 5. 🚀 Run the System (One-Click)

If you're on Windows, just double-click:

```text
run_all.bat
```

This launches:

- 123 scraper
- Doft scraper
- Email responder

If you're on Linux/macOS, use:

```bash
python 123loadboard.py
python data_fetcher.py
python email_processor.py
```

Each in its own terminal.

## 📧 How to Use the System

### ✅ Send an Email (from approved address)

Send to the same email used in `senders.txt`:

Subject: (optional)

```text
Load Request
```

Body: (required format)

```text
Truck: Flatbed
Origin: FL
Destination: TX
```

💬 You'll receive matching loads via email within seconds if they exist in the database.

### 🔁 Matching Logic

The system only replies if all 3 fields are present:

- Truck type
- Origin (2-letter state)
- Destination (2-letter state)

## 🧠 Tech Stack

- Python 3.10+
- MySQL
- Playwright (for browser automation)
- BeautifulSoup4 (for HTML parsing)
- Gmail/iCloud (for sending responses)

## 📞 Support

If you're handing this off to another developer or team, be sure to:

- Provide clean credentials and sample emails
- Keep the scraping scripts running in background
- Use a VPS or Windows system with auto-restart (optional)
  
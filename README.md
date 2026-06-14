# 🗳️ Blockchain-Based Online Voting System

> A full-stack decentralized voting web application built with Flask and a custom blockchain.  
> Votes are stored as tamper-proof blocks — transparent, verifiable, and secure.

---

## 🚀 Overview

Traditional voting systems are vulnerable to manipulation and lack transparency. This project implements a **custom blockchain in Python** to store votes immutably, paired with a **Flask web application** featuring complete voter authentication, OTP verification, admin controls, and a live dashboard.

---

## ✨ Features

- 🔐 **Full Auth Flow** — Register → Verify Email → OTP → Login → Vote
- ⛓️ **Custom Blockchain** — votes stored as SHA-256 hash-chained blocks in JSON
- 🔒 **Tamper Detection** — modifying any block breaks the entire chain
- 🛡️ **Double Vote Prevention** — voter ID tracked; duplicate votes rejected
- 🧾 **Vote Receipt** — voters get a receipt after casting their vote
- 👨‍💼 **Admin Panel** — manage candidates, view blockchain, monitor votes
- 📊 **Live Dashboard** — real-time vote counts and results
- 🗄️ **DB Migration Support** — versioned database schema (v1 → v2)

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python, Flask |
| **Blockchain** | Custom Python implementation (hashlib SHA-256) |
| **Frontend** | HTML, CSS, JavaScript (Jinja2 templates) |
| **Database** | SQLite (`database.db`) |
| **Data Storage** | JSON (`blockchain_data.json`) |
| **Auth** | OTP-based email verification |

---

## 📁 Project Structure

```
onlinevoting/
├── app.py                    # Flask app — routes, logic, API endpoints
├── blockchain.py             # Core blockchain: Block class, Chain, hash logic
├── blockchain_data.json      # Persisted blockchain (all votes as blocks)
├── database.db               # SQLite — voters, candidates, auth data
├── migrate_db.py             # DB migration v1
├── migrate_db_v2.py          # DB migration v2 (schema updates)
├── .env                      # Environment variables (secret key, email config)
├── .gitignore
├── static/                   # CSS, JS, images
└── templates/
    ├── login.html
    ├── register.html
    ├── verify_email.html
    ├── verify_otp.html
    ├── forgot_password.html
    ├── reset_password.html
    ├── vote.html
    ├── receipt.html
    ├── dashboard.html
    ├── home.html
    ├── register_success.html
    ├── admin.html
    └── admin_login.html
```

---

## ⚙️ How to Run

```bash
# Clone the repository
git clone https://github.com/gourivathsalya/onlinevoting.git
cd onlinevoting

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your email credentials and secret key

# Initialize the database
python migrate_db.py

# Run the app
python app.py
```

App runs at `http://localhost:5000`

---

## 🔗 Blockchain Structure

Each vote becomes a block in the chain:

```json
{
  "index": 1,
  "voter_id": "VTR11017352",
  "candidate": "Y.S. Jagan Mohan Reddy",
  "timestamp": "2026-04-05 06:25:54.855859",
  "previous_hash": "3fbae98191a5a420deb113fe1f2fd9ae61bccc...",
  "hash": "a39aa71e5575c8d8e4947de326451c091a9cb9ee..."
}
```

The **Genesis Block** (index 0) anchors the chain with a known zero-hash. Every block's hash is computed from all its fields — changing even one character invalidates all subsequent blocks.

---

## 🔐 Voter Flow

```
Register (name, email, voter ID)
        │
        ▼
Email Verification Link Sent
        │
        ▼
OTP Verification
        │
        ▼
Login with Credentials
        │
        ▼
Cast Vote (one-time only)
        │
        ▼
Vote → Block added to Blockchain
        │
        ▼
Receipt Generated for Voter
```

---

## 🔒 Security Features

| Threat | Protection |
|---|---|
| Double voting | Voter ID flagged in DB after first vote |
| Vote tampering | Hash chain — any edit breaks integrity |
| Unauthorized access | Session-based auth + OTP |
| Admin impersonation | Separate admin login route |
| Exposed secrets | `.env` file excluded via `.gitignore` |

---

---

## 🔮 Future Improvements

- [ ] Deploy on cloud (Render / Railway)
- [ ] Encrypt voter ID on blockchain (anonymity)
- [ ] Candidate photo upload via admin
- [ ] SMS-based OTP (Twilio)
- [ ] Port blockchain to Ethereum testnet

---

## 📄 What I Learned

- Building a custom blockchain from scratch with SHA-256 hashing
- Flask routing, session management, and Jinja2 templating
- OTP-based authentication flow
- SQLite database design and schema migration
- Securing sensitive data with `.env` and `.gitignore`

---

## 👩‍💻 Author

**Gouri Vathsalya**  
B.Tech CSE | RGUKT Ongole  
🔗 [LinkedIn](https://linkedin.com/in/gourivathsalya) · 🐙 [GitHub](https://github.com/gourivathsalya)

---

## 📄 License

MIT License — free to use and modify.

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, Response)
import sqlite3, hashlib, random, string, smtplib, csv, io, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from werkzeug.utils import secure_filename
from blockchain import voting_blockchain

app = Flask(__name__)
app.secret_key = 'blockvote_secret_key_batch87'
DB = 'database.db'

UPLOAD_FOLDER  = os.path.join('static', 'uploads', 'candidates')
ALLOWED_EXTS   = {'png', 'jpg', 'jpeg', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


#  ELECTION TYPES

ELECTION_TYPES = [
    'MLA Election',        # State Legislative Assembly
    'MP Election',         # Lok Sabha / Parliament
    'Panchayat Election',  # Village level
    'Municipal Election',  # City / Corporation level
    'General',             # Generic / custom
]


#  EMAIL CONFIG

EMAIL_HOST     = 'smtp.gmail.com'
EMAIL_PORT     = 587
EMAIL_ADDRESS  = os.environ.get('EMAIL_ADDRESS', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_ENABLED  = True



SMS_ENABLED       = True
TWILIO_SID        = os.environ.get('TWILIO_SID', '')
TWILIO_TOKEN      = os.environ.get('TWILIO_TOKEN', '')
TWILIO_VERIFY_SID = os.environ.get('TWILIO_VERIFY_SID', '')


DEFAULT_CANDIDATES = [
    ('Y.S. Jagan Mohan Reddy', 'YSRCP',    '⚡'),
    ('N. Chandrababu Naidu',   'TDP',       '🚲'),
    ('Pawan Kalyan',           'Jana Sena', '🪁'),
    ('Narendra Modi',          'BJP',       '🪷'),
    ('Rahul Gandhi',           'INC',       '✋'),
]

# ── DB 
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS regions (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS districts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT UNIQUE NOT NULL,
                region_id INTEGER NOT NULL,
                FOREIGN KEY(region_id) REFERENCES regions(id)
            );
            CREATE TABLE IF NOT EXISTS constituencies (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                district_id INTEGER NOT NULL,
                FOREIGN KEY(district_id) REFERENCES districts(id)
            );
            CREATE TABLE IF NOT EXISTS voters (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                voter_id         TEXT UNIQUE NOT NULL,
                name             TEXT NOT NULL,
                email            TEXT UNIQUE,
                phone            TEXT UNIQUE,
                aadhar           TEXT UNIQUE,
                dob              TEXT,
                age              INTEGER,
                password         TEXT NOT NULL,
                has_voted        INTEGER DEFAULT 0,
                is_blocked       INTEGER DEFAULT 0,
                voted_for        TEXT DEFAULT NULL,
                voted_at         TEXT DEFAULT NULL,
                block_hash       TEXT DEFAULT NULL,
                constituency_id  INTEGER DEFAULT NULL,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS pending_reg (
                contact          TEXT PRIMARY KEY,
                contact_type     TEXT NOT NULL,
                otp              TEXT NOT NULL,
                name             TEXT NOT NULL,
                dob              TEXT NOT NULL,
                aadhar           TEXT NOT NULL,
                password         TEXT NOT NULL,
                constituency_id  INTEGER DEFAULT NULL,
                expires_at       TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS password_resets (
                email      TEXT PRIMARY KEY,
                otp        TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS candidates (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                election_id      INTEGER DEFAULT 1,
                constituency_id  INTEGER DEFAULT NULL,
                name             TEXT NOT NULL,
                party            TEXT NOT NULL,
                emoji            TEXT NOT NULL,
                photo            TEXT DEFAULT NULL,
                vote_count       INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS votes (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                voter_id         TEXT NOT NULL,
                election_id      INTEGER NOT NULL,
                candidate_id     INTEGER NOT NULL,
                constituency_id  INTEGER DEFAULT NULL,
                voted_for        TEXT NOT NULL,
                voted_at         TEXT NOT NULL,
                block_hash       TEXT,
                UNIQUE(voter_id, election_id)
            );
            CREATE TABLE IF NOT EXISTS admins (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS election (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                is_open          INTEGER DEFAULT 0,
                title            TEXT NOT NULL,
                election_type    TEXT DEFAULT 'General',
                constituency_id  INTEGER DEFAULT NULL,
                start_time       TEXT DEFAULT NULL,
                end_time         TEXT DEFAULT NULL,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # Safe migrations for existing DBs
        safe_alters = [
            "ALTER TABLE voters     ADD COLUMN is_blocked      INTEGER DEFAULT 0",
            "ALTER TABLE voters     ADD COLUMN aadhar          TEXT    DEFAULT NULL",
            "ALTER TABLE voters     ADD COLUMN dob             TEXT    DEFAULT NULL",
            "ALTER TABLE voters     ADD COLUMN age             INTEGER DEFAULT NULL",
            "ALTER TABLE voters     ADD COLUMN phone           TEXT    DEFAULT NULL",
            "ALTER TABLE voters     ADD COLUMN constituency_id INTEGER DEFAULT NULL",
            "ALTER TABLE candidates ADD COLUMN election_id     INTEGER DEFAULT 1",
            "ALTER TABLE candidates ADD COLUMN photo           TEXT    DEFAULT NULL",
            "ALTER TABLE candidates ADD COLUMN constituency_id INTEGER DEFAULT NULL",
            "ALTER TABLE election   ADD COLUMN start_time      TEXT    DEFAULT NULL",
            "ALTER TABLE election   ADD COLUMN end_time        TEXT    DEFAULT NULL",
            "ALTER TABLE election   ADD COLUMN created_at      TEXT    DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE election   ADD COLUMN election_type   TEXT    DEFAULT 'General'",
            "ALTER TABLE election   ADD COLUMN constituency_id INTEGER DEFAULT NULL",
            "ALTER TABLE votes      ADD COLUMN constituency_id INTEGER DEFAULT NULL",
            "ALTER TABLE pending_reg ADD COLUMN constituency_id INTEGER DEFAULT NULL",
        ]
        for sql in safe_alters:
            try:
                conn.execute(sql)
            except Exception:
                pass

        conn.execute("INSERT OR IGNORE INTO admins (username,password) VALUES (?,?)",
                     ('admin', hashlib.sha256('admin123'.encode()).hexdigest()))

        # Seed regions/districts/constituencies if empty
        if conn.execute("SELECT COUNT(*) as c FROM regions").fetchone()['c'] == 0:
            _seed_geography(conn)

        # Create default election if none exists
        if conn.execute("SELECT COUNT(*) as c FROM election").fetchone()['c'] == 0:
            conn.execute("INSERT INTO election (is_open,title,election_type) VALUES (1,'AP General Election 2024','MLA Election')")
            eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for name, party, emoji in DEFAULT_CANDIDATES:
                conn.execute("INSERT INTO candidates (election_id,name,party,emoji,vote_count) VALUES (?,?,?,?,0)",
                             (eid, name, party, emoji))
        conn.commit()

def _seed_geography(conn):
    REGIONS = ['Coastal Andhra', 'Rayalaseema', 'South Andhra']
    for r in REGIONS:
        conn.execute("INSERT OR IGNORE INTO regions (name) VALUES (?)", (r,))

    region_ids = {row['name']: row['id'] for row in conn.execute("SELECT * FROM regions")}

    DISTRICTS = {
        'Coastal Andhra': [
            'Srikakulam', 'Vizianagaram', 'Visakhapatnam',
            'East Godavari', 'West Godavari', 'Krishna', 'Guntur',
            'Palnadu', 'Bapatla', 'Konaseema', 'Eluru', 'NTR',
        ],
        'Rayalaseema': [
            'Kurnool', 'Nandyal', 'Kadapa', 'Anantapur',
            'Sri Sathya Sai', 'Chittoor', 'Tirupati',
        ],
        'South Andhra': ['Prakasam', 'Nellore'],
    }
    for region, dists in DISTRICTS.items():
        rid = region_ids[region]
        for d in dists:
            conn.execute("INSERT OR IGNORE INTO districts (name, region_id) VALUES (?,?)", (d, rid))

    district_ids = {row['name']: row['id'] for row in conn.execute("SELECT * FROM districts")}

    CONSTITUENCIES = {
        'Srikakulam':     ['Ichchapuram','Palasa','Tekkali','Pathapatnam','Narasannapeta','Rajam','Srikakulam','Amadalavalasa'],
        'Vizianagaram':   ['Bobbili','Cheepurupalli','Gajapathinagaram','Nellimarla','Vizianagaram','Srungavarapukota','Bhimli'],
        'Visakhapatnam':  ['Bheemunipatnam','Anakapalle','Pendurthi','Visakhapatnam North','Visakhapatnam East','Visakhapatnam South','Gajuwaka','Chodavaram','Paderu'],
        'East Godavari':  ['Tuni','Prathipadu','Peddapuram','Samarlakota','Kakinada City','Kakinada Rural','Rajanagaram','Rajahmundry City','Rajahmundry Rural','Narsapuram','Amalapuram'],
        'West Godavari':  ['Palakole','Narasapuram','Bhimavaram','Undi','Tanuku','Tadepalligudem','Eluru','Denduluru','Polavaram'],
        'Krishna':        ['Vijayawada Central','Vijayawada East','Vijayawada West','Machilipatnam','Pedana','Nandigama','Tiruvuru','Mylavaram','Jaggaiahpet','Nuzvid'],
        'Guntur':         ['Tenali','Bapatla','Narasaraopet','Sattenapalle','Guntur East','Guntur West','Mangalagiri','Tadikonda','Prathipadu','Ponnur'],
        'NTR':            ['Tiruvuru','Nandigama','Chandarlapadu','Ibrahimpatnam'],
        'Palnadu':        ['Narasaraopet','Macherla','Gurajala','Vinukonda','Piduguralla'],
        'Bapatla':        ['Bapatla','Repalle','Chirala','Vetapalem','Addanki'],
        'Konaseema':      ['Amalapuram','Mummidivaram','Razole','Gannavaram'],
        'Eluru':          ['Eluru','Kaikaluru','Pedavegi','Unguturu','Narsapur'],
        'Kurnool':        ['Kurnool','Panyam','Nandyal','Allagadda','Srisailam','Nandikotkur','Kodumuru','Yemmiganur','Adoni'],
        'Nandyal':        ['Nandyal','Betamcherla','Allagadda','Srisailam'],
        'Kadapa':         ['Kadapa','Proddatur','Jammalamadugu','Mydukur','Rajampet','Badvel','Kamalapuram'],
        'Anantapur':      ['Anantapur','Guntakal','Dharmavaram','Hindupur','Madanapalle','Tadipatri','Rayadurgam'],
        'Sri Sathya Sai': ['Hindupur','Penukonda','Madakasira','Kadiri','Nallamada'],
        'Chittoor':       ['Chittoor','Puthalapattu','Chandragiri','Tirupati Rural','Nagari','Gangadhara Nellore','Kalakada'],
        'Tirupati':       ['Tirupati','Srikalahasti','Puttur','Palmaneru'],
        'Prakasam':       ['Ongole','Addanki','Chirala','Markapur','Giddalur','Kanigiri','Podili'],
        'Nellore':        ['Nellore City','Nellore Rural','Atmakur','Kovur','Sarvepalli','Gudur','Sullurupeta','Venkatagiri'],
    }
    for dist, const_list in CONSTITUENCIES.items():
        if dist not in district_ids:
            continue
        did = district_ids[dist]
        for c in const_list:
            conn.execute("INSERT OR IGNORE INTO constituencies (name, district_id) VALUES (?,?)", (c, did))

# ── HELPERS 
def hash_pw(p):     return hashlib.sha256(p.encode()).hexdigest()
def gen_voter_id(): return 'VTR' + ''.join(random.choices(string.digits, k=8))
def gen_otp():      return ''.join(random.choices(string.digits, k=6))
def to_dict(r):     return dict(r) if r else None
def to_dicts(rs):   return [dict(r) for r in rs]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTS

def calculate_age(dob_str):
    try:
        dob   = datetime.strptime(dob_str, '%Y-%m-%d').date()
        today = date.today()
        age   = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except Exception:
        return None

def get_geography():
    """Return full region → district → constituency tree."""
    with get_db() as conn:
        regions = to_dicts(conn.execute("SELECT * FROM regions ORDER BY name").fetchall())
        districts = to_dicts(conn.execute(
            "SELECT d.*, r.name as region_name FROM districts d JOIN regions r ON d.region_id=r.id ORDER BY d.name"
        ).fetchall())
        constituencies = to_dicts(conn.execute(
            "SELECT c.*, d.name as district_name, r.name as region_name "
            "FROM constituencies c JOIN districts d ON c.district_id=d.id "
            "JOIN regions r ON d.region_id=r.id ORDER BY c.name"
        ).fetchall())
    return regions, districts, constituencies

def send_email_otp(to_email, name, otp, purpose='verify'):
    if not EMAIL_ENABLED:
        print(f'\n{"="*50}\n  DEV MODE EMAIL OTP for {to_email}: {otp}\n{"="*50}\n')
        return True, ''
    try:
        msg            = MIMEMultipart('alternative')
        msg['Subject'] = f'BlockVote — Your {"Verification" if purpose=="verify" else "Password Reset"} Code: {otp}'
        msg['From']    = EMAIL_ADDRESS
        msg['To']      = to_email
        color = '#388bfd' if purpose == 'verify' else '#f75f67'
        html  = f"""<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;background:#04090f;color:#cdd9e5;padding:2rem;border-radius:16px;border:1px solid #1a3a6a">
          <h1 style="text-align:center;color:#fff">🗳️ Block<span style="color:#388bfd">Vote</span></h1>
          <h2 style="color:#fff">Hello, {name}!</h2>
          <p style="color:#8b949e">Your code expires in <strong style="color:#fff">10 minutes</strong>.</p>
          <div style="background:#0d1a2a;border:2px dashed {color};border-radius:12px;padding:1.5rem;text-align:center;margin:1.5rem 0">
            <div style="font-size:3rem;font-weight:800;color:#e8b84b;letter-spacing:.4em;font-family:monospace">{otp}</div>
          </div>
          <p style="color:#4a5568;font-size:.8rem">If you did not request this, ignore this email.</p>
        </div>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as smtp:
            smtp.ehlo(); smtp.starttls()
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        return True, ''
    except smtplib.SMTPAuthenticationError:
        return False, 'Email authentication failed.'
    except Exception as e:
        return False, str(e)

def send_results_email(to_email, voter_name, election_title, candidates, total):
    try:
        msg            = MIMEMultipart('alternative')
        msg['Subject'] = f'🗳️ BlockVote — Election Results: {election_title}'
        msg['From']    = EMAIL_ADDRESS
        msg['To']      = to_email
        rows = ''
        for i, c in enumerate(candidates):
            pct   = round(c['vote_count'] / total * 100, 1) if total > 0 else 0
            medal = ['🥇','🥈','🥉'][i] if i < 3 else f'#{i+1}'
            rows += f"""<tr>
              <td style="padding:.6rem 1rem">{medal}</td>
              <td style="padding:.6rem 1rem">{c['emoji']} {c['name']}</td>
              <td style="padding:.6rem 1rem;color:#8b949e">{c['party']}</td>
              <td style="padding:.6rem 1rem;font-weight:700;color:#e8b84b">{c['vote_count']}</td>
              <td style="padding:.6rem 1rem;color:#8b949e">{pct}%</td>
            </tr>"""
        winner = candidates[0] if candidates and candidates[0]['vote_count'] > 0 else None
        winner_html = f"""<div style="background:rgba(232,184,75,.1);border:2px solid rgba(232,184,75,.3);border-radius:12px;padding:1.2rem;text-align:center;margin:1.2rem 0">
            <div style="font-size:2rem">🏆</div>
            <div style="font-size:1.3rem;font-weight:800;color:#e8b84b">{winner['emoji']} {winner['name']}</div>
            <div style="color:#8b949e">{winner['party']} — {winner['vote_count']} votes</div>
          </div>""" if winner else ''
        html = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#04090f;color:#cdd9e5;padding:2rem;border-radius:16px;border:1px solid #1a3a6a">
          <h1 style="text-align:center;color:#fff">🗳️ Block<span style="color:#388bfd">Vote</span></h1>
          <h2 style="color:#fff;text-align:center">{election_title}</h2>
          {winner_html}
          <table style="width:100%;border-collapse:collapse;background:#0d1a2a;border-radius:10px">
            <thead><tr style="background:rgba(56,139,253,.1)">
              <th style="padding:.6rem 1rem;text-align:left;color:#8b949e;font-size:.8rem">#</th>
              <th style="padding:.6rem 1rem;text-align:left;color:#8b949e;font-size:.8rem">CANDIDATE</th>
              <th style="padding:.6rem 1rem;text-align:left;color:#8b949e;font-size:.8rem">PARTY</th>
              <th style="padding:.6rem 1rem;text-align:left;color:#8b949e;font-size:.8rem">VOTES</th>
              <th style="padding:.6rem 1rem;text-align:left;color:#8b949e;font-size:.8rem">%</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <p style="color:#4a5568;text-align:center;margin-top:1.2rem;font-size:.8rem">
            Total votes cast: <strong style="color:#fff">{total}</strong><br>
            Dear {voter_name}, thank you for participating.
          </p>
        </div>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as smtp:
            smtp.ehlo(); smtp.starttls()
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        return True
    except Exception:
        return False

def send_sms_otp(to_phone, otp=None):
    if not SMS_ENABLED:
        print(f'\n{"="*50}\n  DEV MODE SMS OTP for {to_phone}: {otp}\n{"="*50}\n')
        return True, ''
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.verify.v2.services(TWILIO_VERIFY_SID) \
            .verifications.create(to=to_phone, channel='sms')
        return True, ''
    except Exception as e:
        return False, f'SMS failed: {str(e)}'

def check_twilio_otp(to_phone, otp):
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        result = client.verify.v2.services(TWILIO_VERIFY_SID) \
            .verification_checks.create(to=to_phone, code=otp)
        return result.status == 'approved', ''
    except Exception as e:
        return False, str(e)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def dec(*a, **kw):
        if 'voter_id' not in session:
            flash('Please login first.', 'warning')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return dec

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def dec(*a, **kw):
        if 'admin' not in session:
            flash('Admin access required.', 'danger')
            return redirect(url_for('admin_login'))
        return f(*a, **kw)
    return dec


#  API ROUTES

@app.route('/api/results')
def api_results():
    try:
        eid = request.args.get('election_id', type=int)
        with get_db() as conn:
            if eid:
                election = to_dict(conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone())
            else:
                election = to_dict(conn.execute(
                    "SELECT * FROM election ORDER BY is_open DESC, id DESC").fetchone())
            if not election:
                return jsonify({'error': 'No election found'}), 404
            eid = election['id']
            candidates = to_dicts(conn.execute(
                "SELECT * FROM candidates WHERE election_id=? ORDER BY vote_count DESC", (eid,)).fetchall())
            total        = sum(c['vote_count'] for c in candidates)
            total_voters = conn.execute("SELECT COUNT(*) as c FROM voters").fetchone()['c']
            try:
                voted_count = conn.execute(
                    "SELECT COUNT(*) as c FROM votes WHERE election_id=?", (eid,)).fetchone()['c']
            except Exception:
                voted_count = conn.execute(
                    "SELECT COUNT(*) as c FROM voters WHERE has_voted=1").fetchone()['c']
        for c in candidates:
            c['pct'] = round(c['vote_count'] / total * 100, 1) if total > 0 else 0
        winner = None
        if not election.get('is_open') and candidates and candidates[0]['vote_count'] > 0:
            winner = candidates[0]
        return jsonify({
            'candidates': candidates, 'total': int(total),
            'total_voters': total_voters, 'voted_count': voted_count,
            'turnout': round(voted_count / total_voters * 100, 1) if total_voters > 0 else 0,
            'election': election, 'chain_valid': voting_blockchain.is_chain_valid(),
            'winner': winner
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e), 'candidates': [], 'total': 0,
                        'total_voters': 0, 'voted_count': 0, 'turnout': 0,
                        'election': None, 'chain_valid': False, 'winner': None}), 500

@app.route('/api/elections')
def api_elections():
    with get_db() as conn:
        elections = to_dicts(conn.execute(
            "SELECT * FROM election ORDER BY is_open DESC, id DESC").fetchall())
    return jsonify(elections)

@app.route('/api/geography')
def api_geography():
    """Returns full geography tree for dynamic dropdowns."""
    regions, districts, constituencies = get_geography()
    return jsonify({
        'regions': regions,
        'districts': districts,
        'constituencies': constituencies
    })

@app.route('/api/constituencies_by_district')
def api_constituencies_by_district():
    did = request.args.get('district_id', type=int)
    if not did:
        return jsonify([])
    with get_db() as conn:
        rows = to_dicts(conn.execute(
            "SELECT * FROM constituencies WHERE district_id=? ORDER BY name", (did,)).fetchall())
    return jsonify(rows)

@app.route('/api/districts_by_region')
def api_districts_by_region():
    rid = request.args.get('region_id', type=int)
    if not rid:
        return jsonify([])
    with get_db() as conn:
        rows = to_dicts(conn.execute(
            "SELECT * FROM districts WHERE region_id=? ORDER BY name", (rid,)).fetchall())
    return jsonify(rows)


#  HOME

@app.route('/')
def home():
    with get_db() as conn:
        elections    = to_dicts(conn.execute(
            "SELECT * FROM election ORDER BY is_open DESC, id DESC").fetchall())
        election     = next((e for e in elections if e['is_open']), elections[0] if elections else None)
        if election:
            candidates  = to_dicts(conn.execute(
                "SELECT * FROM candidates WHERE election_id=? ORDER BY vote_count DESC",
                (election['id'],)).fetchall())
            total       = sum(c['vote_count'] for c in candidates)
            voted_count = conn.execute(
                "SELECT COUNT(*) as c FROM votes WHERE election_id=?",
                (election['id'],)).fetchone()['c']
        else:
            candidates, total, voted_count = [], 0, 0
        total_voters = conn.execute("SELECT COUNT(*) as c FROM voters").fetchone()['c']
    winner = None
    if election and not election.get('is_open') and candidates and candidates[0]['vote_count'] > 0:
        winner = candidates[0]
    return render_template('home.html', candidates=candidates, total=total,
                           election=election, elections=elections,
                           total_voters=total_voters, voted_count=voted_count, winner=winner)


#  REGISTER

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'voter_id' in session:
        return redirect(url_for('vote'))
    if request.method == 'POST':
        name            = request.form.get('name', '').strip()
        contact_type    = request.form.get('contact_type', 'email')
        contact         = request.form.get('contact', '').strip().lower()
        aadhar          = request.form.get('aadhar', '').strip().replace(' ', '')
        dob_str         = request.form.get('dob', '').strip()
        password        = request.form.get('password', '')
        confirm         = request.form.get('confirm', '')

        err = None
        if not name:
            err = 'Please enter your full name.'
        elif contact_type == 'email' and (not contact or '@' not in contact):
            err = 'Please enter a valid email address.'
        elif contact_type == 'phone' and (not contact or not contact.lstrip('+').isdigit() or len(contact.lstrip('+')) < 10):
            err = 'Please enter a valid phone number with country code.'
        elif not aadhar or len(aadhar) != 12 or not aadhar.isdigit():
            err = 'Aadhar number must be exactly 12 digits.'
        elif not dob_str:
            err = 'Please enter your date of birth.'
        elif len(password) < 6:
            err = 'Password must be at least 6 characters.'
        elif password != confirm:
            err = 'Passwords do not match.'

        if err:
            flash(err, 'danger')
        else:
            age = calculate_age(dob_str)
            if age is None:
                flash('Invalid date of birth.', 'danger')
            elif age < 18:
                flash(f'You must be 18+ to register. Your age: {age}.', 'danger')
            else:
                with get_db() as conn:
                    dup = conn.execute(
                        f"SELECT id FROM voters WHERE {'email' if contact_type=='email' else 'phone'}=?",
                        (contact,)).fetchone()
                    dup_aadhar = conn.execute("SELECT id FROM voters WHERE aadhar=?", (aadhar,)).fetchone()
                if dup:
                    flash(f'This {"email" if contact_type=="email" else "phone"} is already registered.', 'danger')
                elif dup_aadhar:
                    flash('This Aadhar is already registered.', 'danger')
                else:
                    otp = gen_otp() if contact_type == 'email' else 'TWILIO_VERIFY'
                    with get_db() as conn:
                        conn.execute("""INSERT OR REPLACE INTO pending_reg
                            (contact,contact_type,otp,name,dob,aadhar,password,constituency_id,expires_at)
                            VALUES (?,?,?,?,?,?,?,NULL,datetime('now','+10 minutes'))""",
                            (contact, contact_type, otp, name, dob_str, aadhar, hash_pw(password)))
                        conn.commit()
                    ok, err_msg = (send_email_otp(contact, name, otp) if contact_type == 'email'
                                   else send_sms_otp(contact))
                    if ok:
                        session['pending_contact']      = contact
                        session['pending_contact_type'] = contact_type
                        if not EMAIL_ENABLED and contact_type == 'email':
                            flash('DEV MODE: Check terminal for OTP.', 'info')
                        elif not SMS_ENABLED and contact_type == 'phone':
                            flash('DEV MODE: Check terminal for OTP.', 'info')
                        else:
                            flash(f'Code sent to your {"email" if contact_type=="email" else "phone"}!', 'success')
                        return redirect(url_for('verify_otp'))
                    else:
                        flash(f'Could not send OTP: {err_msg}', 'danger')
    return render_template('register.html')

# ── VERIFY OTP 
@app.route('/register/verify', methods=['GET', 'POST'])
def verify_otp():
    contact      = session.get('pending_contact')
    contact_type = session.get('pending_contact_type', 'email')
    if not contact:
        return redirect(url_for('register'))

    if request.method == 'POST':
        action = request.form.get('action', 'verify')
        if action == 'resend':
            with get_db() as conn:
                row = to_dict(conn.execute("SELECT * FROM pending_reg WHERE contact=?", (contact,)).fetchone())
            if row:
                if contact_type == 'email':
                    new_otp = gen_otp()
                    with get_db() as conn:
                        conn.execute("UPDATE pending_reg SET otp=?,expires_at=datetime('now','+10 minutes') WHERE contact=?",
                                     (new_otp, contact))
                        conn.commit()
                    ok, err = send_email_otp(contact, row['name'], new_otp)
                else:
                    ok, err = send_sms_otp(contact)
                flash('New code sent!' if ok else f'Resend failed: {err}', 'success' if ok else 'danger')
            return redirect(url_for('verify_otp'))

        entered = request.form.get('otp', '').strip()
        with get_db() as conn:
            row = to_dict(conn.execute(
                "SELECT * FROM pending_reg WHERE contact=? AND expires_at > datetime('now')", (contact,)).fetchone())

        if not row:
            flash('Code expired. Please register again.', 'danger')
            session.pop('pending_contact', None)
            session.pop('pending_contact_type', None)
            return redirect(url_for('register'))

        if contact_type == 'phone':
            approved, _ = check_twilio_otp(contact, entered)
            if not approved:
                flash('Incorrect or expired code.', 'danger')
                return render_template('verify_otp.html', contact=contact, contact_type=contact_type)
        else:
            if entered != row['otp']:
                flash('Incorrect code.', 'danger')
                return render_template('verify_otp.html', contact=contact, contact_type=contact_type)

        voter_id = gen_voter_id()
        age      = calculate_age(row['dob'])
        constituency_id = row.get('constituency_id')
        try:
            with get_db() as conn:
                if contact_type == 'email':
                    conn.execute(
                        "INSERT INTO voters (voter_id,name,email,aadhar,dob,age,password,constituency_id) VALUES (?,?,?,?,?,?,?,?)",
                        (voter_id, row['name'], contact, row['aadhar'], row['dob'], age, row['password'], constituency_id))
                else:
                    conn.execute(
                        "INSERT INTO voters (voter_id,name,phone,aadhar,dob,age,password,constituency_id) VALUES (?,?,?,?,?,?,?,?)",
                        (voter_id, row['name'], contact, row['aadhar'], row['dob'], age, row['password'], constituency_id))
                conn.execute("DELETE FROM pending_reg WHERE contact=?", (contact,))
                conn.commit()
            session.pop('pending_contact', None)
            session.pop('pending_contact_type', None)
            session['reg_voter_id'] = voter_id
            session['reg_name']     = row['name']
            return redirect(url_for('register_success'))
        except sqlite3.IntegrityError:
            flash('This contact or Aadhar is already registered.', 'danger')
            return redirect(url_for('register'))

    return render_template('verify_otp.html', contact=contact, contact_type=contact_type)

@app.route('/register/success')
def register_success():
    voter_id = session.pop('reg_voter_id', None)
    name     = session.pop('reg_name', None)
    if not voter_id:
        return redirect(url_for('register'))
    return render_template('register_success.html', voter_id=voter_id, name=name)

#  LOGIN / LOGOUT

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'voter_id' in session:
        return redirect(url_for('vote'))
    if request.method == 'POST':
        voter_id = request.form.get('voter_id', '').strip()
        password = request.form.get('password', '')
        with get_db() as conn:
            voter = conn.execute(
                "SELECT * FROM voters WHERE voter_id=? AND password=?",
                (voter_id, hash_pw(password))).fetchone()
        if voter:
            if voter['is_blocked']:
                flash('Your account has been blocked. Contact the administrator.', 'danger')
                return render_template('login.html')
            session['voter_id']   = voter['voter_id']
            session['voter_name'] = voter['name']
            flash(f'Welcome back, {voter["name"]}! 👋', 'success')
            return redirect(url_for('vote'))
        flash('Invalid Voter ID or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('home'))


#  FORGOT / RESET PASSWORD

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email or '@' not in email:
            flash('Please enter a valid email.', 'danger')
        else:
            with get_db() as conn:
                voter = conn.execute("SELECT * FROM voters WHERE email=?", (email,)).fetchone()
            if voter:
                otp = gen_otp()
                with get_db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO password_resets (email,otp,expires_at) VALUES (?,?,datetime('now','+10 minutes'))",
                        (email, otp))
                    conn.commit()
                ok, err = send_email_otp(email, voter['name'], otp, purpose='reset')
                if ok:
                    session['reset_email'] = email
                    flash('Reset code sent to your email!', 'success')
                    return redirect(url_for('reset_password'))
                else:
                    flash(f'Could not send email: {err}', 'danger')
            else:
                flash('If this email is registered, a reset code has been sent.', 'info')
                return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        action = request.form.get('action', 'reset')
        if action == 'resend':
            with get_db() as conn:
                voter = conn.execute("SELECT name FROM voters WHERE email=?", (email,)).fetchone()
            if voter:
                new_otp = gen_otp()
                with get_db() as conn:
                    conn.execute(
                        "UPDATE password_resets SET otp=?,expires_at=datetime('now','+10 minutes') WHERE email=?",
                        (new_otp, email))
                    conn.commit()
                send_email_otp(email, voter['name'], new_otp, purpose='reset')
                flash('New reset code sent!', 'success')
            return redirect(url_for('reset_password'))

        entered = request.form.get('otp', '').strip()
        new_pw  = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        with get_db() as conn:
            row = to_dict(conn.execute(
                "SELECT * FROM password_resets WHERE email=? AND expires_at > datetime('now')", (email,)).fetchone())
        if not row:
            flash('Code expired.', 'danger')
            session.pop('reset_email', None)
            return redirect(url_for('forgot_password'))
        if entered != row['otp']:
            flash('Incorrect code.', 'danger')
            return render_template('reset_password.html', email=email)
        if len(new_pw) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('reset_password.html', email=email)
        if new_pw != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', email=email)
        with get_db() as conn:
            conn.execute("UPDATE voters SET password=? WHERE email=?", (hash_pw(new_pw), email))
            conn.execute("DELETE FROM password_resets WHERE email=?", (email,))
            conn.commit()
        session.pop('reset_email', None)
        flash('Password reset successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', email=email)

#  VOTE

@app.route('/vote', methods=['GET', 'POST'])
@login_required
def vote():
    with get_db() as conn:
        voter = to_dict(conn.execute("SELECT * FROM voters WHERE voter_id=?",
                                     (session['voter_id'],)).fetchone())
        if voter.get('is_blocked'):
            flash('Your account has been blocked.', 'danger')
            return redirect(url_for('logout'))

        # BUG FIX: only show elections that are open
        elections = to_dicts(conn.execute(
            "SELECT e.*, c.name as constituency_name, d.name as district_name "
            "FROM election e "
            "LEFT JOIN constituencies c ON e.constituency_id=c.id "
            "LEFT JOIN districts d ON c.district_id=d.id "
            "WHERE e.is_open=1 ORDER BY e.id").fetchall())

        voted_eids = [r['election_id'] for r in conn.execute(
            "SELECT election_id FROM votes WHERE voter_id=?",
            (session['voter_id'],)).fetchall()]

    # Select active election tab
    sel_eid = request.args.get('election_id', type=int)
    if not sel_eid and elections:
        pending = [e for e in elections if e['id'] not in voted_eids]
        sel_eid = pending[0]['id'] if pending else elections[0]['id']

    election      = None
    candidates    = []
    already_voted = False

    if sel_eid:
        with get_db() as conn:
            election = to_dict(conn.execute(
                "SELECT e.*, c.name as constituency_name, d.name as district_name, r.name as region_name "
                "FROM election e "
                "LEFT JOIN constituencies c ON e.constituency_id=c.id "
                "LEFT JOIN districts d ON c.district_id=d.id "
                "LEFT JOIN regions r ON d.region_id=r.id "
                "WHERE e.id=?", (sel_eid,)).fetchone())

            # BUG FIX: show candidates for this election only
            candidates = to_dicts(conn.execute(
                "SELECT * FROM candidates WHERE election_id=? ORDER BY id",
                (sel_eid,)).fetchall())
        already_voted = sel_eid in voted_eids

    if not elections:
        flash('No elections are currently open.', 'warning')

    if request.method == 'POST' and election and election['is_open'] and not already_voted:
        candidate_id = request.form.get('candidate')
        if not candidate_id:
            flash('Please select a candidate.', 'warning')
        else:
            with get_db() as conn:
                # Double-check not already voted (race condition guard)
                if conn.execute("SELECT id FROM votes WHERE voter_id=? AND election_id=?",
                                (session['voter_id'], sel_eid)).fetchone():
                    flash('You have already voted in this election.', 'warning')
                    return redirect(url_for('vote', election_id=sel_eid))

                cand = to_dict(conn.execute(
                    "SELECT * FROM candidates WHERE id=? AND election_id=?",
                    (candidate_id, sel_eid)).fetchone())
                if not cand:
                    flash('Invalid candidate.', 'danger')
                    return redirect(url_for('vote', election_id=sel_eid))

                block_hash = voting_blockchain.add_vote(
                    voter_id=session['voter_id'], candidate=cand['name'])
                now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.execute(
                    "INSERT INTO votes (voter_id,election_id,candidate_id,constituency_id,voted_for,voted_at,block_hash) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (session['voter_id'], sel_eid, cand['id'],
                     election.get('constituency_id'), cand['name'], now, block_hash))
                conn.execute("UPDATE candidates SET vote_count=vote_count+1 WHERE id=?", (cand['id'],))
                # Keep voters table in sync (most recent vote for backward compat)
                conn.execute(
                    "UPDATE voters SET has_voted=1,voted_for=?,voted_at=?,block_hash=? WHERE voter_id=?",
                    (cand['name'], now, block_hash, session['voter_id']))
                conn.commit()
            flash(f'✅ Vote for {cand["name"]} recorded in {election["title"]}!', 'success')
            return redirect(url_for('vote'))

    return render_template('vote.html', voter=voter, elections=elections,
                           election=election, candidates=candidates,
                           already_voted=already_voted, voted_eids=voted_eids,
                           sel_eid=sel_eid)


#  DASHBOARD

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as conn:
        voter        = to_dict(conn.execute("SELECT * FROM voters WHERE voter_id=?",
                                            (session['voter_id'],)).fetchone())
        elections    = to_dicts(conn.execute(
            "SELECT * FROM election ORDER BY is_open DESC, id DESC").fetchall())
        total_voters = conn.execute("SELECT COUNT(*) as c FROM voters").fetchone()['c']
        my_votes     = to_dicts(conn.execute(
            "SELECT v.*,e.title as election_title,e.election_type "
            "FROM votes v JOIN election e ON v.election_id=e.id WHERE v.voter_id=?",
            (session['voter_id'],)).fetchall())
        election     = elections[0] if elections else None
        candidates   = to_dicts(conn.execute(
            "SELECT * FROM candidates WHERE election_id=? ORDER BY vote_count DESC",
            (election['id'],)).fetchall()) if election else []
        total        = sum(c['vote_count'] for c in candidates)
        voted_count  = conn.execute(
            "SELECT COUNT(*) as c FROM votes WHERE election_id=?",
            (election['id'],)).fetchone()['c'] if election else 0
    chain_valid = voting_blockchain.is_chain_valid()
    return render_template('dashboard.html', voter=voter, elections=elections,
                           candidates=candidates, total=total, election=election,
                           total_voters=total_voters, voted_count=voted_count,
                           chain_valid=chain_valid, my_votes=my_votes)

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current = request.form.get('current_password', '')
    new_pw  = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    with get_db() as conn:
        voter = conn.execute("SELECT * FROM voters WHERE voter_id=? AND password=?",
                             (session['voter_id'], hash_pw(current))).fetchone()
    if not voter:
        flash('Current password is incorrect.', 'danger')
    elif len(new_pw) < 6:
        flash('New password must be at least 6 characters.', 'danger')
    elif new_pw != confirm:
        flash('Passwords do not match.', 'danger')
    else:
        with get_db() as conn:
            conn.execute("UPDATE voters SET password=? WHERE voter_id=?",
                         (hash_pw(new_pw), session['voter_id']))
            conn.commit()
        flash('Password changed successfully! 🔒', 'success')
    return redirect(url_for('dashboard') + '#tab-security')


#  RECEIPT
#  BUG FIX: receipt now works for multi-election (picks the voter's
#  most recent vote, not just the latest election)

@app.route('/receipt')
@login_required
def vote_receipt():
    eid = request.args.get('election_id', type=int)
    with get_db() as conn:
        voter = to_dict(conn.execute("SELECT * FROM voters WHERE voter_id=?",
                                     (session['voter_id'],)).fetchone())
        if eid:
            vote_row = to_dict(conn.execute(
                "SELECT * FROM votes WHERE voter_id=? AND election_id=?",
                (session['voter_id'], eid)).fetchone())
            election = to_dict(conn.execute(
                "SELECT * FROM election WHERE id=?", (eid,)).fetchone())
        else:
            # Default to most recent vote
            vote_row = to_dict(conn.execute(
                "SELECT * FROM votes WHERE voter_id=? ORDER BY voted_at DESC LIMIT 1",
                (session['voter_id'],)).fetchone())
            election = to_dict(conn.execute(
                "SELECT * FROM election WHERE id=?",
                (vote_row['election_id'],)).fetchone()) if vote_row else None

    if not vote_row:
        flash('No vote receipt found.', 'warning')
        return redirect(url_for('dashboard'))

    # Merge vote data into voter dict so template stays unchanged
    receipt_voter = dict(voter)
    receipt_voter.update({
        'voted_for':  vote_row['voted_for'],
        'voted_at':   vote_row['voted_at'],
        'block_hash': vote_row['block_hash'],
    })
    return render_template('receipt.html', voter=receipt_voter, election=election)


#  ADMIN: LOGIN / LOGOUT

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin' in session:
        return redirect(url_for('admin_panel'))
    if request.method == 'POST':
        u = request.form.get('username', '')
        p = request.form.get('password', '')
        with get_db() as conn:
            admin = conn.execute("SELECT * FROM admins WHERE username=? AND password=?",
                                 (u, hash_pw(p))).fetchone()
        if admin:
            session['admin'] = u
            flash('Welcome, Admin!', 'success')
            return redirect(url_for('admin_panel'))
        flash('Invalid credentials.', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    flash('Admin logged out.', 'info')
    return redirect(url_for('home'))
 
#  ADMIN: MAIN PANEL

@app.route('/admin')
@admin_required
def admin_panel():
    regions, districts, constituencies = get_geography()
    with get_db() as conn:
        elections = to_dicts(conn.execute(
            "SELECT e.*, c.name as constituency_name, d.name as district_name, r.name as region_name "
            "FROM election e "
            "LEFT JOIN constituencies c ON e.constituency_id=c.id "
            "LEFT JOIN districts d ON c.district_id=d.id "
            "LEFT JOIN regions r ON d.region_id=r.id "
            "ORDER BY e.is_open DESC, e.id DESC").fetchall())
        voters        = to_dicts(conn.execute("SELECT * FROM voters ORDER BY id DESC").fetchall())
        total_voters  = conn.execute("SELECT COUNT(*) as c FROM voters").fetchone()['c']
        blocked_count = conn.execute("SELECT COUNT(*) as c FROM voters WHERE is_blocked=1").fetchone()['c']
        for e in elections:
            e['candidates'] = to_dicts(conn.execute(
                "SELECT * FROM candidates WHERE election_id=? ORDER BY vote_count DESC",
                (e['id'],)).fetchall())
            e['total_votes'] = sum(c['vote_count'] for c in e['candidates'])
            e['voted_count'] = conn.execute(
                "SELECT COUNT(*) as c FROM votes WHERE election_id=?",
                (e['id'],)).fetchone()['c']
    blockchain_data = voting_blockchain.get_all_blocks()
    chain_valid     = voting_blockchain.is_chain_valid()
    active = next((e for e in elections if e['is_open']), elections[0] if elections else None)
    winner = None
    if active and not active['is_open'] and active['candidates'] and active['candidates'][0]['vote_count'] > 0:
        winner = active['candidates'][0]
    return render_template('admin.html',
                           elections=elections, voters=voters,
                           total_voters=total_voters, blocked_count=blocked_count,
                           blockchain_data=blockchain_data, chain_valid=chain_valid,
                           active=active, winner=winner,
                           regions=regions, districts=districts,
                           constituencies=constituencies,
                           election_types=ELECTION_TYPES)


#  ADMIN: ELECTION CRUD

@app.route('/admin/election/create', methods=['POST'])
@admin_required
def create_election():
    title           = request.form.get('title', '').strip()
    election_type   = request.form.get('election_type', 'General').strip()
    constituency_id = request.form.get('constituency_id', type=int)

    if not title:
        flash('Election title is required.', 'danger')
        return redirect(url_for('admin_panel') + '#tab-elections')
    if election_type not in ELECTION_TYPES:
        election_type = 'General'

    with get_db() as conn:
        conn.execute(
            "INSERT INTO election (title, is_open, election_type, constituency_id) VALUES (?,0,?,?)",
            (title, election_type, constituency_id or None))
        conn.commit()
    flash(f'Election "{title}" ({election_type}) created! Add candidates and open when ready.', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')

@app.route('/admin/election/toggle/<int:eid>', methods=['POST'])
@admin_required
def toggle_election(eid):
    with get_db() as conn:
        cur = conn.execute("SELECT is_open,title FROM election WHERE id=?", (eid,)).fetchone()
        if cur:
            conn.execute("UPDATE election SET is_open=? WHERE id=?", (0 if cur['is_open'] else 1, eid))
            conn.commit()
            flash(f'"{cur["title"]}" {"closed 🔒" if cur["is_open"] else "opened 🔓"}.', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')

@app.route('/admin/election/delete/<int:eid>', methods=['POST'])
@admin_required
def delete_election(eid):
    with get_db() as conn:
        e = to_dict(conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone())
        if not e:
            flash('Election not found.', 'danger')
        elif conn.execute("SELECT COUNT(*) as c FROM votes WHERE election_id=?", (eid,)).fetchone()['c'] > 0:
            flash('Cannot delete election that has votes. Reset votes first.', 'danger')
        else:
            conn.execute("DELETE FROM candidates WHERE election_id=?", (eid,))
            conn.execute("DELETE FROM election WHERE id=?", (eid,))
            conn.commit()
            flash(f'Election "{e["title"]}" deleted.', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')

@app.route('/admin/election/reset/<int:eid>', methods=['POST'])
@admin_required
def reset_election(eid):
    with get_db() as conn:
        e = to_dict(conn.execute("SELECT title FROM election WHERE id=?", (eid,)).fetchone())
        conn.execute("UPDATE candidates SET vote_count=0 WHERE election_id=?", (eid,))
        conn.execute("DELETE FROM votes WHERE election_id=?", (eid,))
        
        # (only if they have no other votes remaining)
        remaining_voters = to_dicts(conn.execute(
            "SELECT DISTINCT voter_id FROM votes").fetchall())
        remaining_ids = {r['voter_id'] for r in remaining_voters}
        conn.execute(
            "UPDATE voters SET has_voted=0,voted_for=NULL,voted_at=NULL,block_hash=NULL "
            "WHERE voter_id NOT IN (SELECT DISTINCT voter_id FROM votes)")
        conn.commit()
    flash(f'Votes reset for "{e["title"] if e else "election"}".', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')


#  ADMIN: CANDIDATE CRUD

@app.route('/admin/candidate/add', methods=['POST'])
@admin_required
def add_candidate():
    name            = request.form.get('name', '').strip()
    party           = request.form.get('party', '').strip()
    emoji           = request.form.get('emoji', '🗳️').strip()
    eid             = request.form.get('election_id', type=int)
    constituency_id = request.form.get('constituency_id', type=int)
    photo           = None

    if not name or not party or not eid:
        flash('Name, party and election are required.', 'danger')
        return redirect(url_for('admin_panel') + '#tab-elections')

    if 'photo' in request.files:
        file = request.files['photo']
        if file and file.filename and allowed_file(file.filename):
            ext      = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"cand_{eid}_{name.replace(' ','_')}_{random.randint(1000,9999)}.{ext}")
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            photo = filename

    with get_db() as conn:
        if conn.execute("SELECT id FROM candidates WHERE name=? AND election_id=?", (name, eid)).fetchone():
            flash(f'Candidate "{name}" already exists in this election.', 'danger')
            return redirect(url_for('admin_panel') + '#tab-elections')
        conn.execute(
            "INSERT INTO candidates (election_id,constituency_id,name,party,emoji,photo,vote_count) VALUES (?,?,?,?,?,?,0)",
            (eid, constituency_id or None, name, party, emoji, photo))
        conn.commit()
    flash(f'✅ Candidate "{name}" added!', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')

@app.route('/admin/candidate/edit/<int:cid>', methods=['POST'])
@admin_required
def edit_candidate(cid):
    name  = request.form.get('name', '').strip()
    party = request.form.get('party', '').strip()
    emoji = request.form.get('emoji', '🗳️').strip()
    if not name or not party:
        flash('Name and party are required.', 'danger')
        return redirect(url_for('admin_panel') + '#tab-elections')
    with get_db() as conn:
        cand  = to_dict(conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone())
        photo = cand['photo'] if cand else None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                ext      = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"cand_{cid}_{random.randint(1000,9999)}.{ext}")
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                photo = filename
        conn.execute("UPDATE candidates SET name=?,party=?,emoji=?,photo=? WHERE id=?",
                     (name, party, emoji, photo, cid))
        conn.commit()
    flash(f'Candidate updated to "{name}".', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')

@app.route('/admin/candidate/remove/<int:cid>', methods=['POST'])
@admin_required
def remove_candidate(cid):
    with get_db() as conn:
        cand = to_dict(conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone())
        if not cand:
            flash('Candidate not found.', 'danger')
        elif cand['vote_count'] > 0:
            flash(f'Cannot remove "{cand["name"]}" — reset votes first.', 'danger')
        else:
            if cand.get('photo'):
                try:
                    os.remove(os.path.join(UPLOAD_FOLDER, cand['photo']))
                except Exception:
                    pass
            conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
            conn.commit()
            flash(f'Candidate "{cand["name"]}" removed.', 'success')
    return redirect(url_for('admin_panel') + '#tab-elections')


#  ADMIN: GEOGRAPHY MANAGEMENT

@app.route('/admin/constituency/add', methods=['POST'])
@admin_required
def add_constituency():
    name     = request.form.get('name', '').strip()
    dist_id  = request.form.get('district_id', type=int)
    if not name or not dist_id:
        flash('Constituency name and district are required.', 'danger')
        return redirect(url_for('admin_panel') + '#tab-geography')
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO constituencies (name, district_id) VALUES (?,?)", (name, dist_id))
        conn.commit()
    flash(f'Constituency "{name}" added!', 'success')
    return redirect(url_for('admin_panel') + '#tab-geography')

@app.route('/admin/constituency/delete/<int:cid>', methods=['POST'])
@admin_required
def delete_constituency(cid):
    with get_db() as conn:
        c = to_dict(conn.execute("SELECT * FROM constituencies WHERE id=?", (cid,)).fetchone())
        if c:
            conn.execute("DELETE FROM constituencies WHERE id=?", (cid,))
            conn.commit()
            flash(f'Constituency "{c["name"]}" deleted.', 'success')
    return redirect(url_for('admin_panel') + '#tab-geography')


#  ADMIN: RESULTS EMAIL

@app.route('/admin/election/send-results/<int:eid>', methods=['POST'])
@admin_required
def send_results(eid):
    if not EMAIL_ENABLED:
        flash('Email is disabled. Enable it in app.py first.', 'danger')
        return redirect(url_for('admin_panel') + '#tab-elections')
    with get_db() as conn:
        election   = to_dict(conn.execute("SELECT * FROM election WHERE id=?", (eid,)).fetchone())
        candidates = to_dicts(conn.execute(
            "SELECT * FROM candidates WHERE election_id=? ORDER BY vote_count DESC", (eid,)).fetchall())
        voters     = to_dicts(conn.execute(
            "SELECT * FROM voters WHERE email IS NOT NULL AND email != ''").fetchall())
    if not election:
        flash('Election not found.', 'danger')
        return redirect(url_for('admin_panel') + '#tab-elections')
    total = sum(c['vote_count'] for c in candidates)
    sent, failed = 0, 0
    for voter in voters:
        ok = send_results_email(voter['email'], voter['name'], election['title'], candidates, total)
        if ok:
            sent += 1
        else:
            failed += 1
    flash(f'Results sent! ✅ {sent} emails sent. ❌ {failed} failed.',
          'success' if failed == 0 else 'warning')
    return redirect(url_for('admin_panel') + '#tab-elections')


#  ADMIN: VOTER MANAGEMENT

@app.route('/admin/voter/delete/<int:vid>', methods=['POST'])
@admin_required
def delete_voter(vid):
    with get_db() as conn:
        voter = to_dict(conn.execute("SELECT * FROM voters WHERE id=?", (vid,)).fetchone())
        if not voter:
            flash('Voter not found.', 'danger')
        elif voter['has_voted']:
            flash(f'Cannot delete "{voter["name"]}" — they have voted.', 'danger')
        else:
            conn.execute("DELETE FROM voters WHERE id=?", (vid,))
            conn.commit()
            flash(f'Voter "{voter["name"]}" deleted.', 'success')
    return redirect(url_for('admin_panel') + '#tab-voters')

@app.route('/admin/voter/block/<int:vid>', methods=['POST'])
@admin_required
def block_voter(vid):
    with get_db() as conn:
        voter = to_dict(conn.execute("SELECT * FROM voters WHERE id=?", (vid,)).fetchone())
        if voter:
            conn.execute("UPDATE voters SET is_blocked=? WHERE id=?",
                         (0 if voter['is_blocked'] else 1, vid))
            conn.commit()
            flash(f'Voter "{voter["name"]}" {"unblocked 🔓" if voter["is_blocked"] else "blocked 🚫"}.', 'success')
    return redirect(url_for('admin_panel') + '#tab-voters')

@app.route('/admin/voter/export')
@admin_required
def export_voters():
    with get_db() as conn:
        voters = to_dicts(conn.execute(
            "SELECT v.voter_id,v.name,v.email,v.phone,v.aadhar,v.dob,v.age,"
            "v.has_voted,v.voted_for,v.voted_at,v.is_blocked,v.created_at,"
            "c.name as constituency_name,d.name as district_name,r.name as region_name "
            "FROM voters v "
            "LEFT JOIN constituencies c ON v.constituency_id=c.id "
            "LEFT JOIN districts d ON c.district_id=d.id "
            "LEFT JOIN regions r ON d.region_id=r.id "
            "ORDER BY v.id").fetchall())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Voter ID','Name','Email','Phone','Aadhar','DOB','Age',
                     'Has Voted','Voted For','Voted At','Is Blocked','Registered At',
                     'Region','District','Constituency'])
    for v in voters:
        writer.writerow([
            v['voter_id'], v['name'], v['email'] or '—', v['phone'] or '—',
            v['aadhar'] or '—', v['dob'] or '—', v['age'] or '—',
            'Yes' if v['has_voted'] else 'No', v['voted_for'] or '—',
            v['voted_at'] or '—', 'Yes' if v['is_blocked'] else 'No',
            v['created_at'],
            v['region_name'] or '—', v['district_name'] or '—', v['constituency_name'] or '—',
        ])
    output.seek(0)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=voters_{ts}.csv'})


#  ADMIN: 

@app.route('/admin/settings/password', methods=['POST'])
@admin_required
def change_admin_password():
    current = request.form.get('current_password', '')
    new_pw  = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')
    with get_db() as conn:
        admin = conn.execute("SELECT * FROM admins WHERE username=? AND password=?",
                             (session['admin'], hash_pw(current))).fetchone()
    if not admin:
        flash('Current password is incorrect.', 'danger')
    elif len(new_pw) < 6:
        flash('New password must be at least 6 characters.', 'danger')
    elif new_pw != confirm:
        flash('Passwords do not match.', 'danger')
    else:
        with get_db() as conn:
            conn.execute("UPDATE admins SET password=? WHERE username=?",
                         (hash_pw(new_pw), session['admin']))
            conn.commit()
        flash('Password changed. Please login again.', 'success')
        session.pop('admin', None)
        return redirect(url_for('admin_login'))
    return redirect(url_for('admin_panel') + '#tab-settings')


#  RUN

if __name__ == '__main__':
    init_db()
    print('\n' + '='*55)
    print('  ✅  BlockVote  →  http://127.0.0.1:5000')
    print('  🔑  Admin      →  http://127.0.0.1:5000/admin/login')
    print('  👤  user: admin   pass: admin123')
    print('  📧  EMAIL:', 'LIVE' if EMAIL_ENABLED else 'DEV MODE')
    print('  📱  SMS:  ', 'LIVE' if SMS_ENABLED   else 'DEV MODE')
    print('='*55 + '\n')
    app.run(debug=True, port=5000)
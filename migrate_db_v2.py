"""
Run ONCE before starting app.py to add region/district/constituency support.
Command: python migrate_db_v2.py
"""
import sqlite3, os

DB = 'database.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row



conn.execute('''CREATE TABLE IF NOT EXISTS regions (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
)''')

conn.execute('''CREATE TABLE IF NOT EXISTS districts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT UNIQUE NOT NULL,
    region_id INTEGER NOT NULL,
    FOREIGN KEY(region_id) REFERENCES regions(id)
)''')

conn.execute('''CREATE TABLE IF NOT EXISTS constituencies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    district_id INTEGER NOT NULL,
    FOREIGN KEY(district_id) REFERENCES districts(id)
)''')



for sql in [
    # election → election type + constituency link
    "ALTER TABLE election ADD COLUMN election_type TEXT DEFAULT 'General'",
    "ALTER TABLE election ADD COLUMN constituency_id INTEGER DEFAULT NULL",
    # candidates → constituency link
    "ALTER TABLE candidates ADD COLUMN constituency_id INTEGER DEFAULT NULL",
    # votes → constituency link
    "ALTER TABLE votes ADD COLUMN constituency_id INTEGER DEFAULT NULL",
    # voters → constituency they belong to
    "ALTER TABLE voters ADD COLUMN constituency_id INTEGER DEFAULT NULL",
]:
    try:
        conn.execute(sql)
        col = sql.split('ADD COLUMN')[1].strip().split()[0]
        print(f"✅  Added column: {col}")
    except Exception as e:
        col = sql.split('ADD COLUMN')[1].strip().split()[0] if 'ADD COLUMN' in sql else sql[:40]
        print(f"⏭   Already exists: {col}")



REGIONS = ['Coastal Andhra', 'Rayalaseema', 'South Andhra']

for r in REGIONS:
    try:
        conn.execute("INSERT OR IGNORE INTO regions (name) VALUES (?)", (r,))
    except:
        pass

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
    'South Andhra': [
        'Prakasam', 'Nellore',
    ],
}

for region, dists in DISTRICTS.items():
    rid = region_ids[region]
    for d in dists:
        try:
            conn.execute("INSERT OR IGNORE INTO districts (name, region_id) VALUES (?,?)", (d, rid))
        except:
            pass

district_ids = {row['name']: row['id'] for row in conn.execute("SELECT * FROM districts")}



CONSTITUENCIES = {
    'Srikakulam':    ['Ichchapuram', 'Palasa', 'Tekkali', 'Pathapatnam', 'Narasannapeta',
                      'Rajam', 'Srikakulam', 'Amadalavalasa'],
    'Vizianagaram':  ['Bobbili', 'Cheepurupalli', 'Gajapathinagaram', 'Nellimarla',
                      'Vizianagaram', 'Srungavarapukota', 'Bhimli'],
    'Visakhapatnam': ['Bheemunipatnam', 'Anakapalle', 'Pendurthi', 'Visakhapatnam North',
                      'Visakhapatnam East', 'Visakhapatnam South', 'Gajuwaka',
                      'Chodavaram', 'Paderu'],
    'East Godavari': ['Tuni', 'Prathipadu', 'Peddapuram', 'Samarlakota', 'Kakinada City',
                      'Kakinada Rural', 'Rajanagaram', 'Rajahmundry City',
                      'Rajahmundry Rural', 'Narsapuram', 'Amalapuram'],
    'West Godavari': ['Palakole', 'Narasapuram', 'Bhimavaram', 'Undi', 'Tanuku',
                      'Tadepalligudem', 'Eluru', 'Denduluru', 'Polavaram'],
    'Krishna':       ['Vijayawada Central', 'Vijayawada East', 'Vijayawada West',
                      'Machilipatnam', 'Pedana', 'Nandigama', 'Tiruvuru',
                      'Mylavaram', 'Jaggaiahpet', 'Nuzvid'],
    'Guntur':        ['Tenali', 'Bapatla', 'Narasaraopet', 'Sattenapalle',
                      'Guntur East', 'Guntur West', 'Mangalagiri', 'Tadikonda',
                      'Prathipadu', 'Ponnur'],
    'NTR':           ['Tiruvuru', 'Nandigama', 'Chandarlapadu', 'Ibrahimpatnam'],
    'Palnadu':       ['Narasaraopet', 'Macherla', 'Gurajala', 'Vinukonda', 'Piduguralla'],
    'Bapatla':       ['Bapatla', 'Repalle', 'Chirala', 'Vetapalem', 'Addanki'],
    'Konaseema':     ['Amalapuram', 'Mummidivaram', 'Razole', 'Gannavaram'],
    'Eluru':         ['Eluru', 'Kaikaluru', 'Pedavegi', 'Unguturu', 'Narsapur'],
    'Kurnool':       ['Kurnool', 'Panyam', 'Nandyal', 'Allagadda', 'Srisailam',
                      'Nandikotkur', 'Kodumuru', 'Yemmiganur', 'Adoni'],
    'Nandyal':       ['Nandyal', 'Betamcherla', 'Allagadda', 'Srisailam'],
    'Kadapa':        ['Kadapa', 'Proddatur', 'Jammalamadugu', 'Mydukur',
                      'Rajampet', 'Badvel', 'Kamalapuram'],
    'Anantapur':     ['Anantapur', 'Guntakal', 'Dharmavaram', 'Hindupur',
                      'Madanapalle', 'Tadipatri', 'Rayadurgam'],
    'Sri Sathya Sai':['Hindupur', 'Penukonda', 'Madakasira', 'Kadiri', 'Nallamada'],
    'Chittoor':      ['Chittoor', 'Puthalapattu', 'Chandragiri', 'Tirupati Rural',
                      'Nagari', 'Gangadhara Nellore', 'Kalakada'],
    'Tirupati':      ['Tirupati', 'Srikalahasti', 'Puttur', 'Palmaneru'],
    'Prakasam':      ['Ongole', 'Addanki', 'Chirala', 'Markapur',
                      'Giddalur', 'Kanigiri', 'Podili'],
    'Nellore':       ['Nellore City', 'Nellore Rural', 'Atmakur', 'Kovur',
                      'Sarvepalli', 'Gudur', 'Sullurupeta', 'Venkatagiri'],
    'Vizianagaram':  ['Bobbili', 'Cheepurupalli', 'Gajapathinagaram', 'Nellimarla',
                      'Vizianagaram', 'Srungavarapukota'],
}

for dist, const_list in CONSTITUENCIES.items():
    if dist not in district_ids:
        continue
    did = district_ids[dist]
    for c in const_list:
        try:
            conn.execute("INSERT OR IGNORE INTO constituencies (name, district_id) VALUES (?,?)", (c, did))
        except:
            pass

print(f"✅  Seeded {conn.execute('SELECT COUNT(*) FROM regions').fetchone()[0]} regions")
print(f"✅  Seeded {conn.execute('SELECT COUNT(*) FROM districts').fetchone()[0]} districts")
print(f"✅  Seeded {conn.execute('SELECT COUNT(*) FROM constituencies').fetchone()[0]} constituencies")


os.makedirs(os.path.join('static', 'uploads', 'candidates'), exist_ok=True)
print('✅  uploads/candidates/ folder ready')

conn.commit()
conn.close()
print('\n✅  Migration v2 complete! Run: python app.py')
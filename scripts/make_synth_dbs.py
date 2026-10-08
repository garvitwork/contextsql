"""Create the 12 synthetic company databases (synth_*) in your MySQL."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymysql
from dotenv import load_dotenv
from synth.specs import SPECS, STYLES
from synth.make_dbs import create_database

load_dotenv()
conn = pymysql.connect(host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", 3306)),
                       user=os.getenv("MYSQL_USER"), password=os.getenv("MYSQL_PASSWORD"))
for d in SPECS:
    try:
        meta = create_database(conn, d)
    except pymysql.err.OperationalError as e:
        sys.exit(f"{e}\n\nOne-time fix: open 'MySQL Command Line Client' (root) and run:\n"
                 f"  GRANT ALL ON `synth\\_%`.* TO '{os.getenv('MYSQL_USER')}'@'localhost';\n  FLUSH PRIVILEGES;\nthen rerun this script.")
    print(f"created {meta['db']:22} tables: {', '.join(t['phys'] for t in meta['tables'].values())}")

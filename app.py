import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from math import floor

# ---------- CONFIG & SESSION STATE -----------
IST = ZoneInfo("Asia/Kolkata")
st.set_page_config(page_title="ExoticBill", page_icon="🧾")
for key, default in [
    ("logged_in", False),
    ("role", None),
    ("username", ""),
    ("bill_saved", False),
    ("bill_total", 0.0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------- PRICING & DISCOUNTS -----------
ITEM_PRICES = {
    "Repair Kit": 400,
    "Car Wax": 2000,
    "NOS": 1500,
    "Adv Lockpick": 400,
    "Lockpick": 250,
    "Wash Kit": 300,
    "Harness": 12000,
}
PART_COST = 125
LABOR = 450
MEMBERSHIP_DISCOUNTS = {
    "Tier1": {"REPAIR": 0.20, "CUSTOMIZATION": 0.10},
    "Tier2": {"REPAIR": 0.33, "CUSTOMIZATION": 0.20},
    "Tier3": {"REPAIR": 0.50, "CUSTOMIZATION": 0.30},
    "Racer": {"REPAIR": 0.00, "CUSTOMIZATION": 0.00},
}
# ---------- MEMBERSHIP PRICES -----------
MEMBERSHIP_PRICES = {"Tier1": 2000, "Tier2": 4000, "Tier3": 6000}

# ---------- COMMISSION & TAX -----------
COMMISSION_RATES = {
    "Trainee": 0.10,
    "Mechanic": 0.15,
    "Senior Mechanic": 0.18,
    "Lead Upgrade Specialist": 0.20,
    "Stock Manager": 0.15,
    "Manager": 0.25,
    "CEO": 0.69,
}
TAX_RATE = 0.05  # 5% on the commission

# ---------- LOYALTY CONFIG -----------
# Earn 1 point per ₹500 spent (non-membership bills only)
LOYALTY_RUPEES_PER_POINT = 500

# ---------- DATABASE INIT & MIGRATION -----------
def init_db():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()

    # bills
    c.execute("""
      CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_cid TEXT,
        customer_cid TEXT,
        billing_type TEXT,
        details TEXT,
        total_amount REAL,
        timestamp TEXT,
        commission REAL DEFAULT 0,
        tax REAL DEFAULT 0
      )
    """)
    # employees
    c.execute("""
      CREATE TABLE IF NOT EXISTS employees (
        cid TEXT PRIMARY KEY,
        name TEXT,
        rank TEXT DEFAULT 'Trainee',
        hood TEXT DEFAULT 'No Hood'
      )
    """)
    # memberships (active)
    c.execute("""
      CREATE TABLE IF NOT EXISTS memberships (
        customer_cid TEXT PRIMARY KEY,
        tier TEXT,
        dop TEXT
      )
    """)
    # membership history (archived/expired)
    c.execute("""
      CREATE TABLE IF NOT EXISTS membership_history (
        customer_cid TEXT,
        tier TEXT,
        dop TEXT,
        expired_at TEXT
      )
    """)
    # hoods
    c.execute("""
      CREATE TABLE IF NOT EXISTS hoods (
        name TEXT PRIMARY KEY,
        location TEXT
      )
    """)
    # deleted bills (audit)
    c.execute("""
      CREATE TABLE IF NOT EXISTS deleted_bills (
        id INTEGER,
        employee_cid TEXT,
        customer_cid TEXT,
        billing_type TEXT,
        details TEXT,
        total_amount REAL,
        timestamp TEXT,
        commission REAL,
        tax REAL,
        deleted_by TEXT,
        delete_reason TEXT,
        deleted_at TEXT
      )
    """)
    # shifts
    c.execute("""
      CREATE TABLE IF NOT EXISTS shifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_cid TEXT,
        start_time TEXT,
        end_time TEXT
      )
    """)
    # loyalty points (aggregate)
    c.execute("""
      CREATE TABLE IF NOT EXISTS loyalty (
        customer_cid TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0,
        updated_at TEXT
      )
    """)
    # optional loyalty history for auditability
    c.execute("""
      CREATE TABLE IF NOT EXISTS loyalty_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_cid TEXT,
        delta_points INTEGER,
        reason TEXT,
        created_at TEXT
      )
    """)
    conn.commit()
    conn.close()
init_db()

# ---------- PURGE EXPIRED MEMBERSHIPS & ARCHIVE -----------
def purge_expired_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    cutoff_dt = datetime.now(IST) - timedelta(days=7)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    # archive expired
    expired = c.execute(
        "SELECT customer_cid, tier, dop FROM memberships WHERE dop <= ?",
        (cutoff_str,)
    ).fetchall()
    for cid, tier, dop_str in expired:
        try:
            dop = datetime.strptime(dop_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
        except Exception:
            dop = cutoff_dt
        expired_at = (dop + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO membership_history (customer_cid, tier, dop, expired_at) VALUES (?,?,?,?)",
            (cid, tier, dop_str, expired_at)
        )
    # delete them
    c.execute("DELETE FROM memberships WHERE dop <= ?", (cutoff_str,))
    conn.commit()
    conn.close()
purge_expired_memberships()

# ---------- DATABASE HELPERS -----------
def get_employee_rank(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT rank FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    return row[0] if row else "Trainee"

def adjust_loyalty_points(customer_cid, delta, reason):
    if not customer_cid:
        return
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    row = c.execute("SELECT points FROM loyalty WHERE customer_cid=?", (customer_cid,)).fetchone()
    if row:
        new_pts = max(0, (row[0] or 0) + int(delta))
        c.execute("UPDATE loyalty SET points=?, updated_at=? WHERE customer_cid=?",
                  (new_pts, now_str, customer_cid))
    else:
        new_pts = max(0, int(delta))
        c.execute("INSERT INTO loyalty (customer_cid, points, updated_at) VALUES (?,?,?)",
                  (customer_cid, new_pts, now_str))
    c.execute("INSERT INTO loyalty_history (customer_cid, delta_points, reason, created_at) VALUES (?,?,?,?)",
              (customer_cid, int(delta), reason, now_str))
    conn.commit()
    conn.close()

def get_loyalty_points(customer_cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT points, updated_at FROM loyalty WHERE customer_cid=?", (customer_cid,)).fetchone()
    conn.close()
    if row:
        return {"points": int(row[0] or 0), "updated_at": row[1]}
    return {"points": 0, "updated_at": None}

def save_bill(emp, cust, btype, det, amt):
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

    # Commission rules:
    # - No commission/tax on UPGRADES and MEMBERSHIP
    # - No commission/tax on ITEMS if ONLY Harness and/or NOS are present
    no_commission = False
    if btype in ["UPGRADES", "MEMBERSHIP"]:
        no_commission = True
    elif btype == "ITEMS":
        no_commission_items = {"Harness", "NOS"}
        item_names = []
        if det:
            try:
                item_names = [i.strip().split("×")[0] for i in det.split(",") if i.strip()]
            except Exception:
                item_names = []
        if item_names and all(name in no_commission_items for name in item_names):
            no_commission = True

    if no_commission:
        commission = 0.0
        tax = 0.0
    else:
        comm_rate = COMMISSION_RATES.get(get_employee_rank(emp), 0)
        commission = amt * comm_rate
        tax = commission * TAX_RATE

    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("""
        INSERT INTO bills
          (employee_cid, customer_cid, billing_type, details, total_amount, timestamp, commission, tax)
        VALUES (?,?,?,?,?,?,?,?)
    """, (emp, cust, btype, det, amt, now_ist, commission, tax))
    conn.commit()
    conn.close()

    # Loyalty: earn points on NON-membership bills
    if btype != "MEMBERSHIP":
        pts = int(amt // LOYALTY_RUPEES_PER_POINT)
        if pts > 0:
            adjust_loyalty_points(cust, pts, f"Earnings from {btype} bill ₹{amt:.2f}")

def add_employee(cid, name, rank="Trainee"):
    conn = sqlite3.connect("auto_exotic_billing.db")
    try:
        conn.execute("INSERT INTO employees (cid, name, rank) VALUES (?,?,?)", (cid, name, rank))
        conn.commit()
    except sqlite3.IntegrityError:
        st.warning("Employee CID already exists.")
    conn.close()

def delete_employee(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM employees WHERE cid = ?", (cid,))
    conn.commit()
    conn.close()

def update_employee(cid, name=None, rank=None, hood=None):
    conn = sqlite3.connect("auto_exotic_billing.db")
    if name is not None:
        conn.execute("UPDATE employees SET name = ? WHERE cid = ?", (name, cid))
    if rank is not None:
        conn.execute("UPDATE employees SET rank = ? WHERE cid = ?", (rank, cid))
    if hood is not None:
        conn.execute("UPDATE employees SET hood = ? WHERE cid = ?", (hood, cid))
    conn.commit()
    conn.close()

def get_employee_details(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT name, rank, hood FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    if row:
        return {"name": row[0], "rank": row[1], "hood": row[2]}
    return None

def get_all_employee_cids():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT cid, name FROM employees").fetchall()
    conn.close()
    return rows

def add_membership(cust, tier):
    dop_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("INSERT OR REPLACE INTO memberships (customer_cid, tier, dop) VALUES (?,?,?)",
                 (cust, tier, dop_ist))
    conn.commit()
    conn.close()

def get_membership(cust):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT tier, dop FROM memberships WHERE customer_cid = ?", (cust,)).fetchone()
    conn.close()
    return {"tier": row[0], "dop": row[1]} if row else None

def get_all_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT customer_cid, tier, dop FROM memberships").fetchall()
    conn.close()
    return rows

def get_past_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT customer_cid, tier, dop, expired_at
        FROM membership_history
        ORDER BY expired_at DESC
    """).fetchall()
    conn.close()
    return rows

def get_billing_summary_by_cid(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    summary = {}
    for bt in ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION","MEMBERSHIP"]:
        amt = conn.execute(
            "SELECT SUM(total_amount) FROM bills WHERE employee_cid=? AND billing_type=?",
            (cid, bt)
        ).fetchone()[0] or 0.0
        summary[bt] = amt
    total = conn.execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid=?", (cid,)).fetchone()[0] or 0.0
    conn.close()
    return summary, total

def get_employee_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT id, customer_cid, billing_type, details,
               total_amount, timestamp, commission, tax
        FROM bills WHERE employee_cid=?
        ORDER BY timestamp DESC
    """, (cid,)).fetchall()
    conn.close()
    return rows

def get_all_customers():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT DISTINCT customer_cid FROM bills").fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_customer_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    try:
        rows = conn.execute("""
            SELECT employee_cid, billing_type, details,
                   total_amount, timestamp, commission, tax
            FROM bills
            WHERE customer_cid = ?
            ORDER BY timestamp DESC
        """, (cid,)).fetchall()
        return rows
    finally:
        conn.close()

def get_total_billing():
    conn = sqlite3.connect("auto_exotic_billing.db")
    total = conn.execute("SELECT SUM(total_amount) FROM bills").fetchone()[0] or 0.0
    conn.close()
    return total

def get_bill_count():
    conn = sqlite3.connect("auto_exotic_billing.db")
    cnt = conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0] or 0
    conn.close()
    return cnt

def get_total_commission_and_tax():
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT SUM(commission), SUM(tax) FROM bills").fetchone()
    conn.close()
    return (row[0] or 0.0, row[1] or 0.0)

# ---------- HOODS HELPERS -----------
def add_hood(name, location):
    conn = sqlite3.connect("auto_exotic_billing.db")
    try:
        conn.execute("INSERT INTO hoods (name, location) VALUES (?,?)", (name, location))
        conn.commit()
    except sqlite3.IntegrityError:
        st.warning("That hood already exists.")
    conn.close()

def update_hood(old_name, new_name, new_location):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("UPDATE hoods SET name=?, location=? WHERE name=?", (new_name, new_location, old_name))
    c.execute("UPDATE employees SET hood=? WHERE hood=?", (new_name, old_name))
    conn.commit()
    conn.close()

def delete_hood(name):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("DELETE FROM hoods WHERE name=?", (name,))
    c.execute("UPDATE employees SET hood='No Hood' WHERE hood=?", (name,))
    conn.commit()
    conn.close()

def get_all_hoods():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT name, location FROM hoods").fetchall()
    conn.close()
    return rows

def get_employees_by_hood(hood):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT cid, name FROM employees WHERE hood=?", (hood,)).fetchall()
    conn.close()
    return rows

# ---------- BILL LOGS HELPER ----------
def get_bill_logs(start_str=None, end_str=None):
    """
    Returns bill logs joined with employee details.
    If start_str and end_str are provided (YYYY-MM-DD HH:MM:SS),
    results are filtered inclusively by timestamp.
    """
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    base_sql = """
        SELECT
            b.id, b.timestamp,
            COALESCE(e.name, 'Unknown') AS emp_name,
            b.employee_cid,
            COALESCE(e.hood, 'No Hood') AS hood,
            b.customer_cid, b.billing_type, b.details,
            b.total_amount, b.commission, b.tax
        FROM bills b
        LEFT JOIN employees e ON e.cid = b.employee_cid
    """
    params = ()
    if start_str and end_str:
        base_sql += " WHERE b.timestamp >= ? AND b.timestamp <= ?"
        params = (start_str, end_str)
    base_sql += " ORDER BY b.timestamp DESC"
    rows = c.execute(base_sql, params).fetchall()
    conn.close()
    return rows

# ---------- AUDITED DELETE ----------
def delete_bill_with_audit(bill_id, deleted_by, reason=""):
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    row = c.execute("""
        SELECT id, employee_cid, customer_cid, billing_type, details,
               total_amount, timestamp, commission, tax
        FROM bills WHERE id=?
    """, (bill_id,)).fetchone()
    if not row:
        conn.close()
        return False
    # copy into audit table
    c.execute("""
        INSERT INTO deleted_bills
        (id, employee_cid, customer_cid, billing_type, details, total_amount,
         timestamp, commission, tax, deleted_by, delete_reason, deleted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (row[0], row[1], row[2], row[3], row[4], row[5],
          row[6], row[7], row[8], deleted_by, reason, now_str))
    # delete original
    c.execute("DELETE FROM bills WHERE id=?", (bill_id,))
    conn.commit()
    conn.close()
    return True

def get_deleted_bills(start_str=None, end_str=None):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    base = "SELECT * FROM deleted_bills"
    params = ()
    if start_str and end_str:
        base += " WHERE deleted_at >= ? AND deleted_at <= ?"
        params = (start_str, end_str)
    base += " ORDER BY deleted_at DESC"
    rows = c.execute(base, params).fetchall()
    conn.close()
    return rows

# ---------- SHIFTS ----------
def start_shift(employee_cid):
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    active = c.execute("SELECT id FROM shifts WHERE employee_cid=? AND end_time IS NULL", (employee_cid,)).fetchone()
    if active:
        conn.close()
        return False
    c.execute("INSERT INTO shifts (employee_cid, start_time, end_time) VALUES (?,?,NULL)",
              (employee_cid, now_str))
    conn.commit()
    conn.close()
    return True

def end_shift(employee_cid):
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    active = c.execute("SELECT id FROM shifts WHERE employee_cid=? AND end_time IS NULL", (employee_cid,)).fetchone()
    if not active:
        conn.close()
        return False
    c.execute("UPDATE shifts SET end_time=? WHERE id=?", (now_str, active[0]))
    conn.commit()
    conn.close()
    return True

def get_active_shifts():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT s.employee_cid, e.name, e.hood, s.start_time
        FROM shifts s LEFT JOIN employees e ON e.cid=s.employee_cid
        WHERE s.end_time IS NULL
        ORDER BY s.start_time ASC
    """).fetchall()
    conn.close()
    return rows

def get_recent_shifts(days=7):
    since = (datetime.now(IST) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT s.employee_cid, e.name, e.hood, s.start_time, s.end_time
        FROM shifts s LEFT JOIN employees e ON e.cid=s.employee_cid
        WHERE s.start_time >= ?
        ORDER BY s.start_time DESC
    """, (since,)).fetchall()
    conn.close()
    return rows

def get_daily_sales(n_days=7):
    since = (datetime.now(IST) - timedelta(days=n_days-1)).strftime("%Y-%m-%d 00:00:00")
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT substr(timestamp,1,10) as day, SUM(total_amount)
        FROM bills
        WHERE timestamp >= ?
        GROUP BY day
        ORDER BY day ASC
    """, (since,)).fetchall()
    conn.close()
    return rows

def get_sales_between(start_str, end_str):
    conn = sqlite3.connect("auto_exotic_billing.db")
    total = conn.execute("""
        SELECT SUM(total_amount) FROM bills
        WHERE timestamp >= ? AND timestamp <= ?
    """, (start_str, end_str)).fetchone()[0] or 0.0
    conn.close()
    return total

def get_sales_by_hood(start_str, end_str):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT COALESCE(e.hood,'No Hood') AS hood, SUM(b.total_amount) as total
        FROM bills b LEFT JOIN employees e ON e.cid=b.employee_cid
        WHERE b.timestamp >= ? AND b.timestamp <= ?
        GROUP BY hood
        ORDER BY total DESC
    """, (start_str, end_str)).fetchall()
    conn.close()
    return rows

def get_mvp_by_hood(start_str, end_str):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("""
        SELECT COALESCE(e.hood,'No Hood') AS hood,
               COALESCE(e.name,'Unknown') AS name,
               b.employee_cid,
               SUM(b.total_amount) as total
        FROM bills b LEFT JOIN employees e ON e.cid=b.employee_cid
        WHERE b.timestamp >= ? AND b.timestamp <= ?
        GROUP BY hood, b.employee_cid
        ORDER BY hood ASC, total DESC
    """, (start_str, end_str)).fetchall()
    conn.close()
    # pick top per hood
    mvp = {}
    for hood, name, cid, total in rows:
        if hood not in mvp:
            mvp[hood] = {"Employee": f"{name} ({cid})", "Total": total}
    return mvp

# ---------- AUTHENTICATION -----------
def login(u, p):
    if u == "AutoExotic" and p == "AutoExotic123":
        st.session_state.logged_in, st.session_state.role, st.session_state.username = True, "admin", u
    elif u == "User" and p == "User123":
        st.session_state.logged_in, st.session_state.role, st.session_state.username = True, "user", u
    else:
        st.error("Invalid credentials")

if not st.session_state.logged_in:
    st.title("🧾 ExoticBill Login")
    with st.form("login_form"):
        uname = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login(uname, pwd)
    st.stop()

with st.sidebar:
    st.success(f"Logged in as: {st.session_state.username}")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# ===================== USER PANEL =====================
if st.session_state.role == "user":
    st.title("🧾 ExoticBill - Add New Bill")
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ₹{st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    btype = st.selectbox("Select Billing Type", ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"])
    rtype = st.radio("Repair Type", ["Normal Repair","Advanced Repair"]) if btype=="REPAIR" else None

    with st.form("bill_form", clear_on_submit=True):
        emp_cid = st.text_input("Your CID (Employee)")
        cust_cid= st.text_input("Customer CID")
        total, det= 0.0, ""

        if btype=="ITEMS":
            sel={}
            for item,price in ITEM_PRICES.items():
                q=st.number_input(f"{item} (₹{price}) – Qty", min_value=0, step=1, key=f"user_items_{item}")
                if q: sel[item]=q; total+=price*q
            det=", ".join(f"{i}×{q}" for i,q in sel.items())

        elif btype=="UPGRADES":
            amt=st.number_input("Base upgrade amount (₹)", min_value=0.0, key="user_upg_amt")
            total=amt*1.5; det=f"Upgrade: ₹{amt}"

        elif btype=="REPAIR":
            if rtype=="Normal Repair":
                b=st.number_input("Base repair charge (₹)", min_value=0.0, key="user_rep_base")
                total=b+LABOR; det=f"Normal Repair: ₹{b}+₹{LABOR}"
            else:
                p=st.number_input("Number of parts repaired", min_value=0, step=1, key="user_rep_parts")
                total=p*PART_COST; det=f"Advanced Repair: {p}×₹{PART_COST}"
        else:
            c_amt=st.number_input("Base customization amount (₹)", min_value=0.0, key="user_cust_amt")
            total=c_amt*2; det=f"Customization: ₹{c_amt}×2"

        mem = get_membership(cust_cid)
        if mem:
            disc = MEMBERSHIP_DISCOUNTS.get(mem["tier"],{}).get(btype,0)
            if disc>0:
                total*=(1-disc)
                det+=f" | {mem['tier']} discount {int(disc*100)}%"

        if st.form_submit_button("💾 Save Bill"):
            if not emp_cid or not cust_cid or total==0:
                st.warning("Fill all fields.")
            else:
                save_bill(emp_cid, cust_cid, btype, det, total)
                st.session_state.bill_saved=True
                st.session_state.bill_total=total

    # MEMBERSHIP FORM (user)
    st.markdown("---")
    st.subheader("🎟️ Manage Membership")
    with st.form("mem_form_user", clear_on_submit=True):
        m_cust = st.text_input("Customer CID", key="mem_cust")
        m_tier = st.selectbox("Tier", ["Tier1","Tier2","Tier3","Racer"], key="mem_tier")
        seller_cid = st.text_input("Your CID (Seller)", key="mem_seller")
        submitted = st.form_submit_button("Add/Update Membership")
        if submitted:
            if m_cust and seller_cid and m_tier:
                add_membership(m_cust, m_tier)
                if m_tier in MEMBERSHIP_PRICES:
                    sale_amt = MEMBERSHIP_PRICES[m_tier]
                    save_bill(seller_cid, m_cust, "MEMBERSHIP", f"{m_tier} Membership", sale_amt)
                    st.success(f"{m_tier} membership updated and billed (₹{sale_amt})")
                elif m_tier == "Racer":
                    st.success("Racer membership updated (no billing).")
            else:
                st.warning("Fill all fields correctly.")

    # MEMBERSHIP CHECKER
    st.subheader("🔍 Check Membership")
    lookup=st.text_input("Customer CID to check", key="mem_lookup")
    if st.button("Check Membership"):
        mem=get_membership(lookup)
        if mem:
            dop=datetime.strptime(mem["dop"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            expiry=dop+timedelta(days=7)
            rem=expiry-datetime.now(IST)
            st.info(f"{lookup}: {mem['tier']}, expires in {rem.days}d {rem.seconds//3600}h on {expiry.strftime('%Y-%m-%d %H:%M:%S')} IST")
        else:
            st.info(f"No active membership for {lookup}")

    # SHIFT TRACKER (user)
    st.markdown("---")
    st.subheader("🕒 Shift Tracker")
    with st.form("shift_form", clear_on_submit=True):
        my_cid = st.text_input("Your CID (to track shift)", key="shift_my_cid")
        colx, coly = st.columns(2)
        with colx:
            if st.form_submit_button("▶️ Start Shift"):
                if my_cid:
                    ok = start_shift(my_cid)
                    st.success("Shift started.") if ok else st.warning("You already have an active shift.")
                else:
                    st.warning("Enter your CID.")
        with coly:
            if st.form_submit_button("⏹ End Shift"):
                if my_cid:
                    ok = end_shift(my_cid)
                    st.success("Shift ended.") if ok else st.warning("No active shift found.")
                else:
                    st.warning("Enter your CID.")

    # CUSTOMER LOYALTY (user)
    st.subheader("💚 Customer Loyalty")
    c_loy = st.text_input("Customer CID (check points)", key="loyalty_cust")
    if st.button("Check Points"):
        data = get_loyalty_points(c_loy)
        st.info(f"{c_loy}: **{data['points']}** points (updated: {data['updated_at'] or 'N/A'})")

# ===================== ADMIN PANEL =====================
elif st.session_state.role=="admin":
    st.title("👑 ExoticBill Admin")
    st.metric("💵 Total Revenue", f"₹{get_total_billing():,.2f}")
    st.markdown("---")
    st.subheader("🧹 Maintenance")
    confirm=st.checkbox("I understand this will erase all billing history")
    if confirm and st.button("⚠️ Reset All Billings"):
        conn=sqlite3.connect("auto_exotic_billing.db")
        conn.execute("DELETE FROM bills"); conn.commit(); conn.close()
        st.success("All billing records have been reset.")

    menu=st.sidebar.selectbox(
        "Main Menu",
        ["Dashboard","Sales","Manage Hoods","Manage Staff","Tracking","Bill Logs","Hood War","Shifts","Loyalty"],
        index=0
    )

    # ---------- DASHBOARD (Real-time) ----------
    if menu=="Dashboard":
        st.header("📈 Real-Time Dashboard")
        autorefresh = st.checkbox("Auto-refresh every 60 seconds", value=False)
        if autorefresh:
            st.markdown("<meta http-equiv='refresh' content='60'>", unsafe_allow_html=True)
        now = datetime.now(IST)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        start7 = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            today_rev = get_sales_between(today_start.strftime("%Y-%m-%d %H:%M:%S"),
                                          today_end.strftime("%Y-%m-%d %H:%M:%S"))
            st.metric("Revenue Today", f"₹{today_rev:,.2f}")
        with col2:
            conn = sqlite3.connect("auto_exotic_billing.db")
            today_cnt = conn.execute("SELECT COUNT(*) FROM bills WHERE timestamp >= ? AND timestamp <= ?",
                                     (today_start.strftime("%Y-%m-%d %H:%M:%S"),
                                      today_end.strftime("%Y-%m-%d %H:%M:%S"))).fetchone()[0] or 0
            conn.close()
            st.metric("Bills Today", f"{today_cnt:,}")
        with col3:
            active = len(get_active_shifts())
            st.metric("Active Shifts", active)
        with col4:
            conn = sqlite3.connect("auto_exotic_billing.db")
            mem_today = conn.execute("""
                SELECT COUNT(*) FROM bills
                WHERE billing_type='MEMBERSHIP' AND timestamp >= ? AND timestamp <= ?
            """, (today_start.strftime("%Y-%m-%d %H:%M:%S"),
                  today_end.strftime("%Y-%m-%d %H:%M:%S"))).fetchone()[0] or 0
            conn.close()
            st.metric("Membership Sales Today", mem_today)

        # Last 7 days revenue chart
        st.markdown("#### Revenue - Last 7 Days")
        rows = get_daily_sales(7)
        if rows:
            df = pd.DataFrame(rows, columns=["Date","Revenue"]).set_index("Date")
            st.line_chart(df)
        else:
            st.info("No data for the last 7 days yet.")

        st.caption(f"Updated at {now.strftime('%Y-%m-%d %H:%M:%S')} IST")

    elif menu=="Sales":
        st.header("💹 Sales Overview")
        total_sales=get_total_billing()
        bill_count=get_bill_count()
        avg_sale=total_sales/bill_count if bill_count else 0.0
        sum_comm,sum_tax=get_total_commission_and_tax()
        profit=total_sales-(sum_comm+sum_tax)
        st.metric("Total Sales", f"₹{total_sales:,.2f}")
        st.metric("Average Sale",f"₹{avg_sale:,.2f}")
        st.metric("Total Commission Paid",f"₹{sum_comm:,.2f}")
        st.metric("Total Tax on Commission", f"₹{sum_tax:,.2f}")
        st.metric("Estimated Profit", f"₹{profit:,.2f}")

    elif menu=="Manage Hoods":
        st.header("🏙️ Manage Hoods")
        tabs=st.tabs(["Add Hood","Edit Hood","Assign Staff","View Hoods"])

        with tabs[0]:
            st.subheader("➕ Add New Hood")
            with st.form("add_hood", clear_on_submit=True):
                hname=st.text_input("Hood Name"); hloc=st.text_input("Location")
                if st.form_submit_button("Add Hood") and hname and hloc:
                    add_hood(hname,hloc); st.success(f"Added hood '{hname}'")

        with tabs[1]:
            st.subheader("✏️ Edit / Delete Hood")
            hds=get_all_hoods()
            if hds:
                names=[h[0] for h in hds]
                sel=st.selectbox("Select Hood",names, key="edit_hood_sel")
                old_loc=dict(hds)[sel]
                new_name=st.text_input("New Name",sel, key="edit_hood_name")
                new_loc=st.text_input("New Location",old_loc, key="edit_hood_loc")
                if st.button("Update Hood"):
                    update_hood(sel,new_name,new_loc); st.success("Hood updated.")
                if st.button("Delete Hood"):
                    delete_hood(sel); st.success("Hood deleted.")
            else:
                st.info("No hoods defined yet.")

        with tabs[2]:
            st.subheader("👷 Assign Employees to Hood")
            hds=get_all_hoods()
            if hds:
                hood_names=[h[0] for h in hds]
                sel_hood = st.selectbox("Select Hood", hood_names, key="assign_hood_sel")
                all_emp=get_all_employee_cids()
                choices={f"{n} ({c})":c for c,n in all_emp}
                sel_list=st.multiselect("Select Employees to assign", list(choices.keys()), key="assign_emp_multi")
                if st.button("Assign"):
                    conn = sqlite3.connect("auto_exotic_billing.db")
                    for label in sel_list:
                        cid = choices[label]
                        conn.execute("UPDATE employees SET hood=? WHERE cid=?", (sel_hood, cid))
                    conn.commit(); conn.close()
                    st.success("Employees reassigned.")
            else:
                st.info("Define some hoods first.")

        with tabs[3]:
            st.subheader("🔍 View Hoods & Members")
            hds=get_all_hoods()
            if hds:
                for name,loc in hds:
                    with st.expander(f"{name} — {loc}"):
                        emps=get_employees_by_hood(name)
                        if emps:
                            st.table(pd.DataFrame(emps, columns=["CID","Name"]))
                        else:
                            st.write("No employees assigned.")
            else:
                st.info("No hoods to view.")

    elif menu=="Manage Staff":
        st.header("👷 Manage Staff")
        tabs=st.tabs(["➕ Add Employee","🗑️ Remove Employee","✏️ Edit Employee","📋 View All Employees"])

        with tabs[0]:
            st.subheader("➕ Add New Employee")
            with st.form("add_emp", clear_on_submit=True):
                new_cid=st.text_input("Employee CID")
                new_name=st.text_input("Name")
                new_rank=st.selectbox("Rank", list(COMMISSION_RATES.keys()))
                hds=[h[0] for h in get_all_hoods()] or []
                new_hood=st.selectbox("Hood", ["No Hood"]+hds)
                if st.form_submit_button("Add Employee"):
                    if new_cid and new_name:
                        add_employee(new_cid,new_name,new_rank)
                        if new_hood!="No Hood":
                            update_employee(new_cid,hood=new_hood)
                        st.success(f"Added {new_name} ({new_cid})")
                    else:
                        st.warning("CID and Name required.")

        with tabs[1]:
            st.subheader("🗑️ Remove Employee")
            all_emp=get_all_employee_cids()
            if all_emp:
                opts={f"{n} ({c})":c for c,n in all_emp}
                sel=st.selectbox("Select Employee to Remove", list(opts.keys()), key="rm_emp_sel")
                if st.button("Delete Employee"):
                    delete_employee(opts[sel]); st.success(f"Removed {sel}")
            else:
                st.info("No employees to remove.")

        with tabs[2]:
            st.subheader("✏️ Edit Employee")
            all_emp=get_all_employee_cids()
            if all_emp:
                opts={f"{n} ({c})":c for c,n in all_emp}
                sel_emp=st.selectbox("Select Employee", list(opts.keys()), key="edit_emp_sel")
                if sel_emp:
                    emp_cid = opts[sel_emp]
                    details=get_employee_details(emp_cid)
                    if details:
                        with st.form("edit_emp", clear_on_submit=True):
                            name=st.text_input("Name",details["name"])
                            rank=st.selectbox("Rank",list(COMMISSION_RATES.keys()),
                                              index=list(COMMISSION_RATES.keys()).index(details["rank"]))

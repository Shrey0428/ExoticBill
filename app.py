import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
}
PART_COST = 125
LABOR = 450
MEMBERSHIP_DISCOUNTS = {
    "Tier1": {"REPAIR": 0.20, "CUSTOMIZATION": 0.10},
    "Tier2": {"REPAIR": 0.33, "CUSTOMIZATION": 0.20},
    "Tier3": {"REPAIR": 0.50, "CUSTOMIZATION": 0.30},
    "Racer": {"REPAIR": 0.00, "CUSTOMIZATION": 0.00},
}

# ---------- COMMISSION & TAX -----------
COMMISSION_RATES = {
    "Trainee":                 0.10,
    "Mechanic":                0.15,
    "Senior Mechanic":         0.18,
    "Lead Upgrade Specialist": 0.20,
    "Stock Manager":           0.15,
    "Manager":                 0.25,
}
TAX_RATE = 0.05  # 5% on the commission

# ---------- DATABASE INIT & MIGRATION -----------
def init_db():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()

    # bills table
    c.execute("""
      CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_cid TEXT,
        customer_cid TEXT,
        billing_type TEXT,
        details TEXT,
        total_amount REAL,
        timestamp TEXT
      )
    """)
    # employees table
    c.execute("""
      CREATE TABLE IF NOT EXISTS employees (
        cid TEXT PRIMARY KEY,
        name TEXT
      )
    """)
    # memberships table
    c.execute("""
      CREATE TABLE IF NOT EXISTS memberships (
        customer_cid TEXT PRIMARY KEY,
        tier TEXT,
        dop TEXT
      )
    """)
    # membership history
    c.execute("""
      CREATE TABLE IF NOT EXISTS membership_history (
        customer_cid TEXT,
        tier TEXT,
        dop TEXT,
        expired_at TEXT
      )
    """)

    # migrate employees.rank
    c.execute("PRAGMA table_info(employees)")
    cols = [r[1] for r in c.fetchall()]
    if "rank" not in cols:
        c.execute("ALTER TABLE employees ADD COLUMN rank TEXT DEFAULT 'Trainee'")

    # migrate bills.commission & bills.tax
    c.execute("PRAGMA table_info(bills)")
    cols = [r[1] for r in c.fetchall()]
    if "commission" not in cols:
        c.execute("ALTER TABLE bills ADD COLUMN commission REAL DEFAULT 0")
    if "tax" not in cols:
        c.execute("ALTER TABLE bills ADD COLUMN tax REAL DEFAULT 0")

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
        except:
            dop = cutoff_dt
        expired_at = (dop + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO membership_history (customer_cid, tier, dop, expired_at) VALUES (?,?,?,?)",
            (cid, tier, dop_str, expired_at)
        )

    # delete them from active
    c.execute("DELETE FROM memberships WHERE dop <= ?", (cutoff_str,))
    conn.commit()
    conn.close()

purge_expired_memberships()

# ---------- DATABASE HELPERS -----------
def save_bill(emp, cust, btype, det, amt):
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    # commission & tax
    rank = get_employee_rank(emp)
    comm_rate = COMMISSION_RATES.get(rank, 0)
    commission = amt * comm_rate
    tax = commission * TAX_RATE

    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute(
        """
        INSERT INTO bills
          (employee_cid, customer_cid, billing_type, details, total_amount, timestamp, commission, tax)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (emp, cust, btype, det, amt, now_ist, commission, tax)
    )
    conn.commit()
    conn.close()

def add_employee(cid, name, rank="Trainee"):
    conn = sqlite3.connect("auto_exotic_billing.db")
    try:
        conn.execute(
            "INSERT INTO employees (cid, name, rank) VALUES (?,?,?)",
            (cid, name, rank)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        st.warning("Employee CID already exists.")
    conn.close()

def delete_employee(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM employees WHERE cid = ?", (cid,))
    conn.commit()
    conn.close()

def get_employee_rank(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT rank FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    return row[0] if row else "Trainee"

def add_membership(cust, tier):
    dop_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute(
        "INSERT OR REPLACE INTO memberships (customer_cid, tier, dop) VALUES (?,?,?)",
        (cust, tier, dop_ist)
    )
    conn.commit()
    conn.close()

def remove_membership(cust):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM memberships WHERE customer_cid = ?", (cust,))
    conn.commit()
    conn.close()

def get_membership(cust):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute(
        "SELECT tier, dop FROM memberships WHERE customer_cid = ?", (cust,)
    ).fetchone()
    conn.close()
    return {"tier": row[0], "dop": row[1]} if row else None

def get_all_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT customer_cid, tier, dop FROM memberships").fetchall()
    conn.close()
    return rows

def get_past_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT customer_cid, tier, dop, expired_at FROM membership_history ORDER BY expired_at DESC"
    ).fetchall()
    conn.close()
    return rows

def get_employee_name(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT name FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    return row[0] if row else cid

def get_all_employee_cids():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT cid, name FROM employees").fetchall()
    conn.close()
    return rows

def get_billing_summary_by_cid(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    summary, total = {}, 0.0
    for bt in ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"]:
        amt = conn.execute(
            "SELECT SUM(total_amount) FROM bills WHERE employee_cid = ? AND billing_type = ?",
            (cid, bt)
        ).fetchone()[0] or 0.0
        summary[bt] = amt
        total += amt
    conn.close()
    return summary, total

def get_employee_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT id, customer_cid, billing_type, details, total_amount, timestamp, commission, tax "
        "FROM bills WHERE employee_cid = ?", (cid,)
    ).fetchall()
    conn.close()
    return rows

def delete_bill_by_id(bid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM bills WHERE id = ?", (bid,))
    conn.commit()
    conn.close()

def get_all_customers():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT DISTINCT customer_cid FROM bills").fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_customer_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT employee_cid, billing_type, details, total_amount, timestamp, commission, tax "
        "FROM bills WHERE customer_cid = ?", (cid,)
    ).fetchall()
    conn.close()
    return rows

def get_total_billing():
    conn = sqlite3.connect("auto_exotic_billing.db")
    total = conn.execute("SELECT SUM(total_amount) FROM bills").fetchone()[0] or 0.0
    conn.close()
    return total

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

# ---------- USER PANEL -----------
if st.session_state.role == "user":
    st.title("🧾 Add New Bill")
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ${st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    btype = st.selectbox("Billing Type",
                         ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"],
                         key="btype_user")
    rtype = None
    if btype == "REPAIR":
        rtype = st.radio("Repair Type",
                         ["Normal Repair","Advanced Repair"],
                         key="rtype_user")

    with st.form("bill_form", clear_on_submit=True):
        emp_cid = st.text_input("Your CID (Employee)", key="bill_emp")
        cust_cid = st.text_input("Customer CID", key="bill_cust")
        total, det = 0.0, ""

        if btype == "ITEMS":
            sel = {}
            for item, price in ITEM_PRICES.items():
                q = st.number_input(f"{item} (${price}) – Qty",
                                    min_value=0, step=1,
                                    key=f"qty_{item}")
                if q:
                    sel[item] = q
                    total += price * q
            det = ", ".join(f"{i}×{q}" for i,q in sel.items())

        elif btype == "UPGRADES":
            amt = st.number_input("Base upgrade amount ($)",
                                  min_value=0.0, key="upgrade_amt")
            total = amt * 1.5
            det = f"Upgrade: ${amt}"

        elif btype == "REPAIR":
            if rtype == "Normal Repair":
                b = st.number_input("Base repair charge ($)",
                                     min_value=0.0, key="norm_rep")
                total = b + LABOR
                det = f"Normal Repair: ${b}+${LABOR}"
            else:
                p = st.number_input("Number of parts repaired",
                                     min_value=0, step=1, key="adv_rep")
                total = p * PART_COST
                det = f"Advanced Repair: {p}×${PART_COST}"

        else:  # CUSTOMIZATION
            c_amt = st.number_input("Base customization amount ($)",
                                     min_value=0.0, key="cust_amt")
            total = c_amt * 2
            det = f"Customization: ${c_amt}×2"

        mem = get_membership(cust_cid)
        if mem:
            disc = MEMBERSHIP_DISCOUNTS.get(mem["tier"], {}).get(btype, 0)
            if disc > 0:
                total *= (1 - disc)
                det += f" | {mem['tier']} discount {int(disc*100)}%"

        if st.form_submit_button("💾 Save Bill"):
            if not emp_cid or not cust_cid or total == 0:
                st.warning("Fill all fields.")
            else:
                save_bill(emp_cid, cust_cid, btype, det, total)
                st.session_state.bill_saved = True
                st.session_state.bill_total = total

    st.markdown("---")
    st.subheader("Manage Membership")
    with st.form("mem_form_user", clear_on_submit=True):
        m_cust = st.text_input("Customer CID", key="mem_cust")
        m_tier = st.selectbox("Tier", ["Tier1","Tier2","Tier3","Racer"], key="mem_tier")
        if st.form_submit_button("Add/Update Membership"):
            if m_cust:
                add_membership(m_cust, m_tier)
                st.success("Membership updated!")

    st.subheader("Check Membership")
    lookup = st.text_input("Customer CID to check", key="lookup_user")
    if st.button("Check Membership"):
        mem = get_membership(lookup)
        if mem:
            tier, dop_str = mem["tier"], mem["dop"]
            dop = datetime.strptime(dop_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            expiry = dop + timedelta(days=7)
            rem = expiry - datetime.now(IST)
            st.info(f"{lookup}: {tier}, expires in {rem.days}d {rem.seconds//3600}h")
        else:
            st.info(f"Membership expired for {lookup}")

# ---------- ADMIN PANEL -----------
elif st.session_state.role == "admin":
    st.title("👑 Admin Panel")
    st.subheader("Business Overview")
    st.metric("💵 Total Revenue", f"${get_total_billing():.2f}")

    st.markdown("---")
    st.subheader("Maintenance")
    if st.checkbox("I understand this will erase all billing history", key="confirm_reset"):
        if st.button("⚠️ Reset All Billings"):
            conn = sqlite3.connect("auto_exotic_billing.db")
            conn.execute("DELETE FROM bills")
            conn.commit()
            conn.close()
            st.success("All bills reset.")

    st.markdown("---")
    st.subheader("Add New Employee")
    with st.form("add_emp", clear_on_submit=True):
        ecid = st.text_input("Employee CID", key="add_ecid")
        ename = st.text_input("Name", key="add_ename")
        erank = st.selectbox("Rank", list(COMMISSION_RATES.keys()), key="add_rank")
        if st.form_submit_button("Add"):
            if ecid and ename:
                add_employee(ecid, ename, erank)
                st.success(f"Added {ename} as {erank}")

    st.subheader("Delete Employee")
    emps = get_all_employee_cids()
    if emps:
        opts = {f"{n} ({c})": c for c,n in emps}
        sel = st.selectbox("Select Employee", list(opts.keys()), key="del_emp")
        if st.button("Delete"):
            delete_employee(opts[sel])
            st.success("Deleted.")

    st.markdown("---")
    choice = st.selectbox("Action", [
        "View Employee Billings",
        "View Customer Data",
        "Employee Rankings",
        "Manage Memberships",
        "Employee Performance",
        "Employee Tracking"
    ], key="admin_choice")

    if choice == "View Employee Billings":
        emps = get_all_employee_cids()
        if emps:
            m = {f"{n} ({c})": c for c,n in emps}
            sel = st.selectbox("Select Employee", list(m.keys()), key="view_emp")
            cid = m[sel]; name = get_employee_name(cid)
            mode = st.radio("Mode", ["Overall","Detailed"], key="view_mode")
            if mode == "Overall":
                summ, tot = get_billing_summary_by_cid(cid)
                st.metric(f"{name} Total", f"${tot:.2f}")
                for k,v in summ.items():
                    st.write(f"{k}: ${v:.2f}")
            else:
                rows = get_employee_bills(cid)
                if rows:
                    df = pd.DataFrame(rows, columns=[
                        "Bill ID","Customer CID","Type","Details","Amount","Timestamp","Commission","Tax"
                    ])
                    st.table(df)
                else:
                    st.info("No bills.")
        else:
            st.info("No employees.")

    elif choice == "View Customer Data":
        custs = get_all_customers()
        if custs:
            sc = st.selectbox("Customer CID", custs, key="view_cust")
            rows = get_customer_bills(sc)
            if rows:
                df = pd.DataFrame(rows, columns=[
                    "Employee CID","Type","Details","Amount","Timestamp","Commission","Tax"
                ])
                st.table(df)
            else:
                st.info("No records.")
        else:
            st.info("No customers.")

    elif choice == "Employee Rankings":
        metric = st.selectbox("Rank by", ["Total","ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"], key="rank_metric")
        data = []
        for cid,name in get_all_employee_cids():
            summ,tot = get_billing_summary_by_cid(cid)
            data.append({"Name":name,"CID":cid,**summ,"Total":tot})
        df = pd.DataFrame(data).sort_values(by=metric,ascending=False)
        st.table(df)

    elif choice == "Manage Memberships":
        tab = st.radio("View", ["Active","Past"], key="mem_tab")
        if tab == "Active":
            with st.form("adm_mem", clear_on_submit=True):
                cm = st.text_input("Customer CID", key="adm_mem_cust")
                tr = st.selectbox("Tier", ["Tier1","Tier2","Tier3","Racer"], key="adm_mem_tier")
                if st.form_submit_button("Add/Update"):
                    if cm:
                        add_membership(cm,tr)
                        st.success("Updated.")
            mems = get_all_memberships()
            if mems:
                df = pd.DataFrame(mems,columns=["CID","Tier","DOP"])
                st.table(df)
        else:
            past = get_past_memberships()
            if past:
                df = pd.DataFrame(past,columns=["CID","Tier","DOP","Expired At"])
                st.table(df)
            else:
                st.info("No past memberships.")

    elif choice == "Employee Performance":
        emps = get_all_employee_cids()
        emp_map = {f"{n} ({c})":c for c,n in emps}
        sel = st.selectbox("Employee", list(emp_map.keys()), key="perf_emp")
        cid = emp_map[sel]
        conn = sqlite3.connect("auto_exotic_billing.db"); c = conn.cursor()
        c.execute("""
            SELECT DATE(timestamp) AS date, SUM(total_amount) AS daily_sales
            FROM bills WHERE employee_cid=?
            GROUP BY DATE(timestamp) ORDER BY DATE(timestamp)
        """,(cid,))
        rows = c.fetchall(); conn.close()
        if not rows:
            st.info("No data.")
        else:
            df = pd.DataFrame(rows,columns=["date","daily_sales"])
            df["date"]=pd.to_datetime(df["date"])
            df=df.set_index("date")
            days=st.number_input("Past days",1,365,7,key="perf_days")
            comp=st.selectbox("Compare",["<",">","="],key="perf_comp")
            thresh=st.number_input("Threshold",0.0,step=0.01,key="perf_thresh")
            cutoff=(datetime.now(IST)-timedelta(days=days)).replace(tzinfo=None)
            df_time=df[df.index>=cutoff]
            if comp=="<":
                df_f=df_time[df_time["daily_sales"]<thresh]
            elif comp==">":
                df_f=df_time[df_time["daily_sales"]>thresh]
            else:
                df_f=df_time[df_time["daily_sales"]==thresh]
            st.write("Filtered Sales")
            st.table(df_f.rename_axis("Date").reset_index())
            st.write("Trend")
            st.line_chart(df_time["daily_sales"])

    else:  # Employee Tracking
        days=st.number_input("Past days",1,365,7,key="track_days")
        comp=st.selectbox("Compare",["<",">","="],key="track_comp")
        thresh=st.number_input("Threshold",0.0,step=0.01,key="track_thresh")
        cutoff=(datetime.now(IST)-timedelta(days=days)).strftime("%Y-%m-%d")
        conn=sqlite3.connect("auto_exotic_billing.db"); c=conn.cursor()
        c.execute("""
            SELECT employee_cid, SUM(total_amount) FROM bills
            WHERE DATE(timestamp)>=? GROUP BY employee_cid
        """,(cutoff,))
        sales=c.fetchall(); conn.close()
        sales_map={cid:total for cid,total in sales}
        matches=[]
        for cid,name in get_all_employee_cids():
            total=sales_map.get(cid,0.0)
            if (comp=="<" and total<thresh) or (comp==">" and total>thresh) or (comp=="=" and abs(total-thresh)<1e-6):
                matches.append((cid,name,total))
        if not matches:
            st.info("No matches.")
        else:
            df= pd.DataFrame(matches,columns=["CID","Name","Total Sales"])
            st.table(df)

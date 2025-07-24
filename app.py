import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# --------- CONFIG & SESSION STATE -----------
st.set_page_config(page_title="ExoticBill", page_icon="🧾")
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = ""
if "bill_saved" not in st.session_state:
    st.session_state.bill_saved = False
    st.session_state.bill_total = 0.0

# --------- PRICING & DISCOUNTS -----------
ITEM_PRICES = {
    "Repair Kit": 400,
    "Car Wax": 2000,
    "NOS": 1500,
    "Adv Lockpick": 400,
    "Lockpick": 250,
    "Wash Kit": 300
}
PART_COST = 125
LABOR = 450

MEMBERSHIP_DISCOUNTS = {
    "Tier1": {"REPAIR": 0.20, "CUSTOMIZATION": 0.10},
    "Tier2": {"REPAIR": 0.33, "CUSTOMIZATION": 0.20},
    "Tier3": {"REPAIR": 0.50, "CUSTOMIZATION": 0.30},
    "Racer": {"REPAIR": 0.00, "CUSTOMIZATION": 0.00}
}

# --------- DATABASE INIT & MIGRATION -----------
def init_db():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("""
      CREATE TABLE IF NOT EXISTS bills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_cid TEXT,
        customer_cid TEXT,
        billing_type TEXT,
        details TEXT,
        total_amount REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    """)
    c.execute("""
      CREATE TABLE IF NOT EXISTS employees (
        cid TEXT PRIMARY KEY,
        name TEXT
      )
    """)
    c.execute("""
      CREATE TABLE IF NOT EXISTS memberships (
        customer_cid TEXT PRIMARY KEY,
        tier TEXT
      )
    """)
    # Add dop column if missing
    c.execute("PRAGMA table_info(memberships)")
    cols = [r[1] for r in c.fetchall()]
    if "dop" not in cols:
        c.execute("ALTER TABLE memberships ADD COLUMN dop DATETIME")
    conn.commit()
    conn.close()

init_db()

# Purge expired memberships (older than 7 days)
def purge_expired_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    cutoff = datetime.now() - timedelta(days=7)
    c.execute("DELETE FROM memberships WHERE dop <= ?", (cutoff.strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()

purge_expired_memberships()

# --------- HELPERS -----------
def save_bill(emp, cust, btype, det, amt):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute(
      "INSERT INTO bills (employee_cid, customer_cid, billing_type, details, total_amount) VALUES (?,?,?,?,?)",
      (emp, cust, btype, det, amt)
    )
    conn.commit()
    conn.close()

def add_employee(cid, name):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO employees (cid, name) VALUES (?,?)", (cid, name))
        conn.commit()
    except sqlite3.IntegrityError:
        st.warning("Employee CID already exists.")
    conn.close()

def delete_employee(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM employees WHERE cid = ?", (cid,))
    conn.commit()
    conn.close()

def add_membership(cust, tier):
    conn = sqlite3.connect("auto_exotic_billing.db")
    dop = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
      "INSERT OR REPLACE INTO memberships (customer_cid, tier, dop) VALUES (?,?,?)",
      (cust, tier, dop)
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

def get_employee_name(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT name FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    return row[0] if row else None

def get_all_employee_cids():
    conn = sqlite3.connect("auto_exotic_billing.db")
    data = conn.execute("SELECT cid, name FROM employees").fetchall()
    conn.close()
    return data

def get_billing_summary_by_cid(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    summary, total = {}, 0.0
    for bt in ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"]:
        amt = conn.execute(
            "SELECT SUM(total_amount) FROM bills WHERE employee_cid = ? AND billing_type = ?",
            (cid, bt)
        ).fetchone()[0] or 0.0
        summary[bt], total = amt, total + amt
    conn.close()
    return summary, total

def get_employee_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT id, customer_cid, billing_type, details, total_amount, timestamp FROM bills WHERE employee_cid = ?",
        (cid,)
    ).fetchall()
    conn.close()
    return rows

def delete_bill_by_id(bid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM bills WHERE id = ?", (bid,))
    conn.commit()
    conn.close()
    st.success("Bill deleted.")
    st.experimental_rerun()

def get_all_customers():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT DISTINCT customer_cid FROM bills").fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_customer_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT employee_cid, billing_type, details, total_amount, timestamp FROM bills WHERE customer_cid = ?",
        (cid,)
    ).fetchall()
    conn.close()
    return rows

def get_total_billing():
    conn = sqlite3.connect("auto_exotic_billing.db")
    total = conn.execute("SELECT SUM(total_amount) FROM bills").fetchone()[0] or 0.0
    conn.close()
    return total

# --------- LOGIN -----------
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
        pwd   = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login(uname, pwd)
    st.stop()

# --------- LOGOUT --------
with st.sidebar:
    st.success(f"Logged in as: {st.session_state.username}")
    if st.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()

# --------- USER PANEL -----------
if st.session_state.role == "user":
    st.title("🧾 ExoticBill - Add New Bill")
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ${st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    btype = st.selectbox("Select Billing Type", ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"], key="btype_user")
    if btype == "REPAIR":
        rtype = st.radio("Repair Type", ["Normal Repair","Advanced Repair"], key="rtype_user")
    else:
        rtype = None

    with st.form("bill_form", clear_on_submit=True):
        emp_cid  = st.text_input("Your CID (Employee)", key="bill_emp")
        cust_cid = st.text_input("Customer CID",    key="bill_cust")
        total, det = 0.0, ""

        if btype == "ITEMS":
            sel = {}
            for item, price in ITEM_PRICES.items():
                q = st.number_input(f"{item} (${price}) – Qty", min_value=0, step=1, key=f"qty_{item}")
                if q:
                    sel[item], total = q, total + price*q
            det = ", ".join(f"{i}×{q}" for i,q in sel.items())

        elif btype == "UPGRADES":
            amt = st.number_input("Base upgrade amount ($)", min_value=0.0, key="upgrade_amt")
            total, det = amt*1.5, f"Upgrade: ${amt}"

        elif btype == "REPAIR":
            if rtype == "Normal Repair":
                b = st.number_input("Base repair charge ($)", min_value=0.0, key="norm_rep")
                total, det = b+LABOR, f"Normal Repair: ${b}+${LABOR} labor"
            else:
                p = st.number_input("Number of parts repaired", min_value=0, step=1, key="adv_rep")
                total, det = p*PART_COST, f"Advanced Repair: {p}×${PART_COST}"

        else:  # CUSTOMIZATION
            c_amt = st.number_input("Base customization amount ($)", min_value=0.0, key="cust_amt")
            total, det = c_amt*2, f"Customization: ${c_amt}×2"

        # membership discount
        mem = get_membership(cust_cid)
        if mem:
            disc = MEMBERSHIP_DISCOUNTS.get(mem["tier"], {}).get(btype, 0)
            if disc>0:
                total *= (1-disc)
                det += f" | {mem['tier']} discount {int(disc*100)}%"

        if st.form_submit_button("💾 Save Bill"):
            if not emp_cid or not cust_cid or total==0:
                st.warning("Fill all fields correctly.")
            else:
                save_bill(emp_cid,cust_cid,btype,det,total)
                st.session_state.bill_saved = True
                st.session_state.bill_total = total
elif st.session_state.role == "admin":
    st.title("👑 ExoticBill Admin Panel")

    # Business Overview
    st.subheader("📈 Business Overview")
    st.metric("💵 Total Revenue", f"${get_total_billing():.2f}")

    # Employee Mgmt
    st.markdown("---")
    st.subheader("➕ Add New Employee")
    with st.form("add_emp", clear_on_submit=True):
        ecid = st.text_input("Employee CID", key="add_ecid")
        ename = st.text_input("Name", key="add_ename")
        if st.form_submit_button("Add"):
            if ecid and ename:
                add_employee(ecid,ename)
                st.success("Employee added!")
                st.experimental_rerun()

    st.subheader("➖ Delete Employee")
    emps = get_all_employee_cids()
    if emps:
        opts = {f"{n} ({c})": c for c,n in emps}
        sel_del = st.selectbox("Select Employee to Delete", list(opts.keys()), key="del_emp")
        if st.button("Delete"):
            delete_employee(opts[sel_del])
            st.success(f"Deleted {sel_del}")
            st.experimental_rerun()
    else:
        st.info("No employees.")

    # Action chooser
    st.markdown("---")
    choice = st.radio("Action", [
        "View Employee Billings",
        "View Customer Data",
        "Employee Rankings",
        "Manage Memberships"
    ], key="admin_action")

    # View Employee Billings
    if choice == "View Employee Billings":
        emps = get_all_employee_cids()
        if emps:
            m = {f"{n} ({c})": c for c,n in emps}
            sel_emp = st.selectbox("Select Employee", list(m.keys()), key="view_emp")
            cid = m[sel_emp]; name = get_employee_name(cid)
            vtype = st.radio("View Type", ["Overall","Detailed"], key="view_type")
            if vtype=="Overall":
                summ,tot = get_billing_summary_by_cid(cid)
                st.info(f"{name} (CID: {cid})")
                st.metric("Total Billing",f"${tot:.2f}")
                for k,v in summ.items():
                    st.markdown(f"- {k}: ${v:.2f}")
            else:
                rows = get_employee_bills(cid)
                if rows:
                    df = pd.DataFrame(rows,columns=[
                        "Bill ID","Customer CID","Type","Details","Amount","Timestamp"
                    ])
                    for _,r in df.iterrows():
                        with st.expander(f"#{r['Bill ID']}—${r['Amount']:.2f}"):
                            st.write(r.drop("Bill ID"))
                            if st.button(f"Delete #{r['Bill ID']}", key=f"del_bill_{r['Bill ID']}"):
                                delete_bill_by_id(r['Bill ID'])
                else:
                    st.info("No bills.")
        else:
            st.warning("No employees.")

    # View Customer Data
    elif choice=="View Customer Data":
        st.subheader("Customer Order History")
        custs = get_all_customers()
        if custs:
            sc = st.selectbox("Select Customer", custs, key="view_cust")
            data = get_customer_bills(sc)
            if data:
                df = pd.DataFrame(data,columns=[
                    "Employee CID","Type","Details","Amount","Timestamp"
                ])
                st.table(df)
            else:
                st.info("No records.")
        else:
            st.warning("No data.")

    # Employee Rankings
    elif choice=="Employee Rankings":
        st.subheader("Employee Rankings")
        metric = st.selectbox("Rank by",[
            "Total","ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"
        ], key="rank_metric")
        rows=[]
        for cid,name in get_all_employee_cids():
            summ,tot = get_billing_summary_by_cid(cid)
            rows.append({"Name":name,"CID":cid,**summ,"Total":tot})
        df = pd.DataFrame(rows).sort_values(by=metric,ascending=False).reset_index(drop=True)
        df.index+=1
        st.table(df)

    # Manage Memberships
    else:
        st.subheader("Manage Memberships")
        with st.form("admin_mem", clear_on_submit=True):
            cm = st.text_input("Customer CID", key="admin_mem_cust")
            tr = st.selectbox("Tier",["Tier1","Tier2","Tier3","Racer"], key="admin_mem_tier")
            if st.form_submit_button("Add/Update"):
                if cm:
                    add_membership(cm,tr)
                    st.success(f"{cm} → {tr}")
                

        st.markdown("**Current Memberships**")
        mems = get_all_memberships()
        if mems:
            dfm = pd.DataFrame(mems,columns=["Customer CID","Tier","DOP"])
            dfm["DOP"]=pd.to_datetime(dfm["DOP"])
            dfm["Expiry"]=dfm["DOP"]+timedelta(days=7)
            now=datetime.now()
            dfm["Time Left"]=dfm["Expiry"].apply(lambda e: f"{max((e-now).days,0)}d {max((e-now).seconds//3600,0)}h")
            st.table(dfm)
            rm = st.selectbox("Remove for", [f"{c} ({t})" for c,t,_ in mems], key="rm_mem")
            if st.button("Remove", key="rm_btn"):
                remove_membership(rm.split(" ")[0])
                st.success(f"Removed {rm}")
        else:
            st.info("No memberships.")

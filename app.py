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

# --------- PRICING & MEMBERSHIP CONSTANTS -----------
ITEM_PRICES = {
    "Repair Kit": 400, "Car Wax": 2000, "NOS": 1500,
    "Adv Lockpick": 400, "Lockpick": 250, "Wash Kit": 300
}
PART_COST = 125
LABOR = 450

MEMBERSHIP_DISCOUNTS = {
    "Tier1": {"REPAIR": 0.20, "CUSTOMIZATION": 0.10},
    "Tier2": {"REPAIR": 0.33, "CUSTOMIZATION": 0.20},
    "Tier3": {"REPAIR": 0.50, "CUSTOMIZATION": 0.30},
    "Racer": {"REPAIR": 0.00, "CUSTOMIZATION": 0.00}
}

# --------- DATABASE INITIALIZATION -----------
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
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    """)
    # employees table
    c.execute("""
      CREATE TABLE IF NOT EXISTS employees (
        cid TEXT PRIMARY KEY,
        name TEXT
      )
    """)
    # memberships table with DOP
    c.execute("""
      CREATE TABLE IF NOT EXISTS memberships (
        customer_cid TEXT PRIMARY KEY,
        tier TEXT,
        dop DATETIME
      )
    """)
    conn.commit()
    conn.close()

init_db()

# Purge any expired memberships at app start
def purge_expired_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    cutoff = datetime.now() - timedelta(days=7)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("DELETE FROM memberships WHERE dop <= ?", (cutoff_str,))
    conn.commit()
    conn.close()

purge_expired_memberships()

# --------- DATABASE HELPERS -----------
def save_bill(emp_cid, cust_cid, btype, details, amt):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute(
      "INSERT INTO bills (employee_cid, customer_cid, billing_type, details, total_amount) VALUES (?, ?, ?, ?, ?)",
      (emp_cid, cust_cid, btype, details, amt)
    )
    conn.commit()
    conn.close()

def add_employee(cid, name):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    try:
        c.execute("INSERT INTO employees (cid, name) VALUES (?, ?)", (cid, name))
        conn.commit()
    except sqlite3.IntegrityError:
        st.warning("Employee CID already exists.")
    conn.close()

def delete_employee(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("DELETE FROM employees WHERE cid = ?", (cid,))
    conn.commit()
    conn.close()

def add_membership(cust_cid, tier):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    dop_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
      "INSERT OR REPLACE INTO memberships (customer_cid, tier, dop) VALUES (?, ?, ?)",
      (cust_cid, tier, dop_str)
    )
    conn.commit()
    conn.close()

def remove_membership(cust_cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("DELETE FROM memberships WHERE customer_cid = ?", (cust_cid,))
    conn.commit()
    conn.close()

def get_membership(cust_cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT tier, dop FROM memberships WHERE customer_cid = ?", (cust_cid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"tier": row[0], "dop": row[1]}
    return None

def get_all_memberships():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT customer_cid, tier, dop FROM memberships")
    rows = c.fetchall()
    conn.close()
    return rows

def get_employee_name(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT name FROM employees WHERE cid = ?", (cid,))
    r = c.fetchone()
    conn.close()
    return r[0] if r else None

def get_all_employee_cids():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT cid, name FROM employees")
    data = c.fetchall()
    conn.close()
    return data

def get_billing_summary_by_cid(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    summary, total = {}, 0.0
    for bt in ["ITEMS", "UPGRADES", "REPAIR", "CUSTOMIZATION"]:
        c.execute(
          "SELECT SUM(total_amount) FROM bills WHERE employee_cid = ? AND billing_type = ?",
          (cid, bt)
        )
        amt = c.fetchone()[0] or 0.0
        summary[bt] = amt
        total += amt
    conn.close()
    return summary, total

def get_employee_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("""
      SELECT id, customer_cid, billing_type, details, total_amount, timestamp
      FROM bills WHERE employee_cid = ?
    """, (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_bill_by_id(bill_id):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
    conn.commit()
    conn.close()
    st.success("Bill deleted.")
    st.experimental_rerun()

def get_all_customers():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT DISTINCT customer_cid FROM bills")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_customer_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("""
      SELECT employee_cid, billing_type, details, total_amount, timestamp
      FROM bills WHERE customer_cid = ?
    """, (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_total_billing():
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT SUM(total_amount) FROM bills")
    total = c.fetchone()[0] or 0.0
    conn.close()
    return total

# --------- LOGIN HANDLER & PAGE -----------
def login(u, p):
    if u == "AutoExotic" and p == "AutoExotic123":
        st.session_state.logged_in = True
        st.session_state.role = "admin"
        st.session_state.username = u
    elif u == "User" and p == "User123":
        st.session_state.logged_in = True
        st.session_state.role = "user"
        st.session_state.username = u
    else:
        st.error("Invalid credentials")

if not st.session_state.logged_in:
    st.title("🧾 ExoticBill Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login(username, password)
    st.stop()

# --------- LOGOUT SIDEBAR -----------
with st.sidebar:
    st.success(f"Logged in as: {st.session_state.username}")
    if st.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()

# --------- USER PANEL -----------
if st.session_state.role == "user":
    st.title("🧾 ExoticBill - Add New Bill")

    # Confirmation after save
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ${st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    billing_type = st.selectbox(
        "Select Billing Type",
        ["ITEMS", "UPGRADES", "REPAIR", "CUSTOMIZATION"]
    )
    if billing_type == "REPAIR":
        repair_type = st.radio("Repair Type", ["Normal Repair", "Advanced Repair"])
    else:
        repair_type = None

    with st.form("bill_form", clear_on_submit=True):
        emp_cid = st.text_input("Your CID (Employee)", key="bill_emp")
        cust_cid = st.text_input("Customer CID", key="bill_cust")
        total, details = 0.0, ""

        if billing_type == "ITEMS":
            sel = {}
            for item, price in ITEM_PRICES.items():
                qty = st.number_input(f"{item} (${price}) – Qty", min_value=0, step=1, key=item)
                if qty:
                    sel[item] = qty
                    total += price * qty
            details = ", ".join(f"{i}×{q}" for i, q in sel.items())

        elif billing_type == "UPGRADES":
            amt = st.number_input("Base upgrade amount ($)", min_value=0.0)
            total = amt * 1.5
            details = f"Upgrade: ${amt}"

        elif billing_type == "REPAIR":
            if repair_type == "Normal Repair":
                b = st.number_input("Base repair charge ($)", min_value=0.0)
                total = b + LABOR
                details = f"Normal Repair: ${b} + ${LABOR} labor"
            else:
                parts = st.number_input("Number of parts repaired", min_value=0, step=1)
                total = parts * PART_COST
                details = f"Advanced Repair: {parts}×${PART_COST}"

        else:  # CUSTOMIZATION
            c_amt = st.number_input("Base customization amount ($)", min_value=0.0)
            total = c_amt * 2
            details = f"Customization: ${c_amt}×2"

        # Apply membership discount
        mem_info = get_membership(cust_cid)
        if mem_info:
            tier = mem_info["tier"]
            disc = MEMBERSHIP_DISCOUNTS.get(tier, {}).get(billing_type, 0)
            if disc > 0:
                total *= (1 - disc)
                details += f" | {tier} discount {int(disc*100)}%"

        if st.form_submit_button("💾 Save Bill"):
            if not emp_cid or not cust_cid or total == 0:
                st.warning("Fill all fields correctly.")
            else:
                save_bill(emp_cid, cust_cid, billing_type, details, total)
                st.session_state.bill_saved = True
                st.session_state.bill_total = total

    st.markdown("---")
    # Employees can add/update memberships
    st.subheader("🎟️ Manage Membership (Add/Update)")
    with st.form("membership_form", clear_on_submit=True):
        mem_cust = st.text_input("Customer CID", key="mem_cust")
        mem_tier = st.selectbox("Tier", ["Tier1", "Tier2", "Tier3", "Racer"], key="mem_tier")
        if st.form_submit_button("Add/Update Membership"):
            if mem_cust:
                add_membership(mem_cust, mem_tier)
                st.success(f"Set {mem_cust} → {mem_tier}")
                st.experimental_rerun()

    # Employees can check membership + time left
    st.subheader("🔍 Check Membership")
    lookup_cid = st.text_input("Enter Customer CID to check", key="lookup_cid")
    if st.button("Check Membership"):
        mem_info = get_membership(lookup_cid)
        if mem_info:
            tier = mem_info["tier"]
            dop = datetime.strptime(mem_info["dop"], "%Y-%m-%d %H:%M:%S")
            expiry = dop + timedelta(days=7)
            now = datetime.now()
            remaining = expiry - now
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                st.info(
                    f"{lookup_cid} is in {tier}. "
                    f"Expires in {days} days and {hours} hours "
                    f"on {expiry.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                st.info(f"{lookup_cid}'s membership expired on {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            st.info(f"{lookup_cid} has no membership")
elif st.session_state.role == "admin":
    st.title("👑 ExoticBill Admin Panel")

    # Business Overview
    st.subheader("📈 Business Overview")
    st.metric("💵 Total Revenue", f"${get_total_billing():.2f}")

    # Employee Management
    st.markdown("---")
    st.subheader("➕ Add New Employee")
    with st.form("add_employee", clear_on_submit=True):
        e_cid = st.text_input("Employee CID")
        e_name = st.text_input("Employee Name")
        if st.form_submit_button("Add Employee"):
            if e_cid and e_name:
                add_employee(e_cid, e_name)
                st.success("Employee added!")
                st.experimental_rerun()

    st.subheader("➖ Delete Employee")
    emps = get_all_employee_cids()
    if emps:
        opts = {f"{n} ({c})": c for c, n in emps}
        to_del = st.selectbox("Select Employee to Delete", list(opts.keys()))
        if st.button("Delete Employee"):
            delete_employee(opts[to_del])
            st.success(f"Deleted {to_del}")
            st.experimental_rerun()
    else:
        st.info("No employees to delete.")

    # Action chooser
    st.markdown("---")
    choice = st.radio("Action", [
        "View Employee Billings",
        "View Customer Data",
        "Employee Rankings",
        "Manage Memberships"
    ])

    # View Employee Billings
    if choice == "View Employee Billings":
        emps = get_all_employee_cids()
        if emps:
            cid_map = {f"{n} ({c})": c for c, n in emps}
            sel = st.selectbox("Select Employee", list(cid_map.keys()))
            cid = cid_map[sel]
            name = get_employee_name(cid)
            view = st.radio("View Type", ["Overall Billings", "Detailed Billings"])
            if view == "Overall Billings":
                summ, tot = get_billing_summary_by_cid(cid)
                st.info(f"{name} (CID: {cid})")
                st.metric("💰 Total Billing", f"${tot:.2f}")
                st.markdown(f"- ITEMS: ${summ['ITEMS']:.2f}")
                st.markdown(f"- UPGRADES: ${summ['UPGRADES']:.2f}")
                st.markdown(f"- REPAIR: ${summ['REPAIR']:.2f}")
                st.markdown(f"- CUSTOMIZATION: ${summ['CUSTOMIZATION']:.2f}")
            else:
                rows = get_employee_bills(cid)
                if rows:
                    df = pd.DataFrame(rows, columns=[
                        "Bill ID","Customer CID","Type","Details","Amount","Timestamp"
                    ])
                    for _, r in df.iterrows():
                        with st.expander(f"#{r['Bill ID']} — ${r['Amount']:.2f}"):
                            st.write(r.drop("Bill ID"))
                            if st.button(f"🗑️ Delete #{r['Bill ID']}", key=f"d_{r['Bill ID']}"):
                                delete_bill_by_id(r['Bill ID'])
                else:
                    st.info("No bills found.")
        else:
            st.warning("No employees found.")

    # View Customer Data
    elif choice == "View Customer Data":
        st.subheader("📂 Customer Order History")
        custs = get_all_customers()
        if custs:
            sc = st.selectbox("Select Customer CID", custs)
            data = get_customer_bills(sc)
            if data:
                df = pd.DataFrame(data, columns=[
                    "Employee CID","Type","Details","Amount","Timestamp"
                ])
                st.table(df)
            else:
                st.info("No records for this customer.")
        else:
            st.warning("No customer data found.")

    # Employee Rankings
    elif choice == "Employee Rankings":
        st.subheader("🏆 Employee Rankings")
        metric = st.selectbox("Rank by", [
            "Total","ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"
        ])
        rows = []
        for cid, name in get_all_employee_cids():
            summ, tot = get_billing_summary_by_cid(cid)
            rows.append({
                "Employee Name": name,
                "Employee CID": cid,
                **summ,
                "Total": tot
            })
        df_rank = pd.DataFrame(rows).sort_values(by=metric, ascending=False).reset_index(drop=True)
        df_rank.index += 1
        st.table(df_rank)

    # Manage Memberships (Admin)
    else:
        st.subheader("🎟️ Manage Memberships")
        with st.form("admin_memform", clear_on_submit=True):
            cm = st.text_input("Customer CID", key="adm_cust")
            tr = st.selectbox("Tier", ["Tier1","Tier2","Tier3","Racer"], key="adm_tier")
            if st.form_submit_button("Add/Update Membership"):
                if cm:
                    add_membership(cm, tr)
                    st.success(f"{cm} set to {tr}")
                    st.experimental_rerun()

        st.markdown("**Current Memberships**")
        mems = get_all_memberships()
        if mems:
            # Show CID, Tier, DOP, Expiry, Time Left
            dfm = pd.DataFrame(mems, columns=["Customer CID","Tier","DOP"])
            dfm["DOP"] = pd.to_datetime(dfm["DOP"])
            dfm["Expiry"] = dfm["DOP"] + timedelta(days=7)
            now = datetime.now()
            dfm["Time Left"] = dfm["Expiry"].apply(
                lambda exp: f"{max((exp-now).days,0)}d {max(((exp-now).seconds)//3600,0)}h"
            )
            st.table(dfm)

            to_rm = st.selectbox("Remove membership for", [f"{r[0]} ({r[1]})" for r in mems])
            if st.button("Remove Membership"):
                rem_c = to_rm.split(" ")[0]
                remove_membership(rem_c)
                st.success(f"Removed membership for {rem_c}")
                st.experimental_rerun()
        else:
            st.info("No memberships defined.")

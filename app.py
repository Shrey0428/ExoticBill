import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --------- CONFIG & SESSION STATE -----------
st.set_page_config(page_title="ExoticBill", page_icon="🧾")
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = ""
if "bill_saved" not in st.session_state:
    st.session_state.bill_saved = False

# --------- DATABASE INITIALIZATION -----------
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
    conn.commit()
    conn.close()

init_db()

# --------- DATABASE HELPERS -----------
def save_bill(employee_cid, customer_cid, billing_type, details, total_amount):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO bills (employee_cid, customer_cid, billing_type, details, total_amount) VALUES (?, ?, ?, ?, ?)",
        (employee_cid, customer_cid, billing_type, details, total_amount)
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

def get_employee_name(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("SELECT name FROM employees WHERE cid = ?", (cid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

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
    summary = {}
    total = 0
    for bt in ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"]:
        c.execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid = ? AND billing_type = ?", (cid, bt))
        amt = c.fetchone()[0] or 0
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
    st.success("Bill deleted successfully!")

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

# --------- LOGIN HANDLER -----------
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

# --------- LOGIN PAGE -----------
if not st.session_state.logged_in:
    st.title("🧾 ExoticBill Login")
    with st.form("login_form"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            login(u, p)
    st.stop()

# --------- SIDEBAR LOGOUT -----------
with st.sidebar:
    st.success(f"Logged in as: {st.session_state.username}")
    if st.button("Logout"):
        st.session_state.clear()

# --------- USER PANEL -----------
# --------- USER PANEL -----------
# --------- USER PANEL -----------
if st.session_state.role == "user":
    st.title("🧾 ExoticBill - Add New Bill")

    # Success banner
    if st.session_state.get("bill_saved", False):
        st.success(f"Bill saved! Total: ${st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    # Pricing constants
    ITEM_PRICES = {
        "Repair Kit": 400, "Car Wax": 2000, "NOS": 1500,
        "Adv Lockpick": 400, "Lockpick": 250, "Wash Kit": 300
    }
    PART_COST, LABOR = 125, 450

    # 1) Billing‑type selector outside the form
    billing_type = st.selectbox(
        "Select Billing Type",
        ["ITEMS", "UPGRADES", "REPAIR", "CUSTOMIZATION"]
    )

    # 2) If it's REPAIR, choose repair type outside the form too
    if billing_type == "REPAIR":
        repair_type = st.radio(
            "Repair Type",
            ["Normal Repair", "Advanced Repair"]
        )
    else:
        repair_type = None

    # 3) Now the form itself (clears on submit)
    with st.form("bill_form", clear_on_submit=True):
        emp = st.text_input("Your CID (Employee)")
        cust = st.text_input("Customer CID")
        total = 0.0
        details = ""

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
            # use the repair_type chosen above
            if repair_type == "Normal Repair":
                base = st.number_input("Base repair charge ($)", min_value=0.0)
                total = base + LABOR
                details = f"Normal Repair: ${base} + ${LABOR} labor"
            else:
                parts = st.number_input("Number of parts repaired", min_value=0, step=1)
                total = parts * PART_COST
                details = f"Advanced Repair: {parts}×${PART_COST}"

        else:  # CUSTOMIZATION
            cust_amt = st.number_input("Base customization amount ($)", min_value=0.0)
            total = cust_amt * 2
            details = f"Customization: ${cust_amt}×2"

        submitted = st.form_submit_button("💾 Save Bill")
        if submitted:
            if not emp or not cust or total == 0:
                st.warning("Please fill all fields correctly.")
            else:
                save_bill(emp, cust, billing_type, details, total)
                st.session_state.bill_saved = True
                st.session_state.bill_total = total
                st.experimental_rerun()

# --------- ADMIN PANEL -----------
elif st.session_state.role == "admin":
    st.title("👑 ExoticBill Admin Panel")
    choice = st.radio("Action", ["View Employee Billings","View Customer Data"])

    if choice == "View Employee Billings":
        st.subheader("➕ Add New Employee")
        with st.form("add_employee"):
            nc = st.text_input("New Employee CID")
            nn = st.text_input("Employee Name")
            if st.form_submit_button("Add Employee"):
                if nc and nn:
                    add_employee(nc, nn)
                    st.success("Employee added.")
                else:
                    st.warning("Fill both fields.")

        st.markdown("---")
        emps = get_all_employee_cids()
        if emps:
            opts = {f"{n} ({c})": c for c,n in emps}
            sel = st.selectbox("Select Employee", list(opts.keys()))
            cid = opts[sel]
            name = get_employee_name(cid)
            view = st.radio("View Type", ["Overall Billings","Detailed Billings"])

            if view == "Overall Billings":
                summ, tot = get_billing_summary_by_cid(cid)
                st.info(f"{name} (CID: {cid})")
                st.metric("💰 Total", f"${tot:.2f}")
                st.markdown(f"- ITEMS: ${summ['ITEMS']:.2f}")
                st.markdown(f"- UPGRADES: ${summ['UPGRADES']:.2f}")
                st.markdown(f"- REPAIR: ${summ['REPAIR']:.2f}")
                st.markdown(f"- CUSTOMIZATION: ${summ['CUSTOMIZATION']:.2f}")

            else:
                st.info(f"Detailed for {name} ({cid})")
                bills = get_employee_bills(cid)
                if bills:
                    df = pd.DataFrame(bills, columns=["Bill ID","Customer CID","Type","Details","Amount","Timestamp"])
                    for _, row in df.iterrows():
                        with st.expander(f"#{row['Bill ID']} – ${row['Amount']:.2f}"):
                            st.write(row.drop("Bill ID"))
                            if st.button(f"🗑️ Delete #{row['Bill ID']}", key=f"del_{row['Bill ID']}"):
                                delete_bill_by_id(row['Bill ID'])
                else:
                    st.info("No bills yet.")
        else:
            st.warning("No employees found.")

    else:  # View Customer Data
        st.subheader("📂 Customer Order History")
        custs = get_all_customers()
        if custs:
            selc = st.selectbox("Select Customer CID", custs)
            data = get_customer_bills(selc)
            if data:
                df = pd.DataFrame(data, columns=["Employee CID","Type","Details","Amount","Timestamp"])
                st.table(df)
            else:
                st.info("No records for this customer.")
        else:
            st.warning("No customer data found.")

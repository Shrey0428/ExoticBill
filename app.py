import streamlit as st
import sqlite3
from datetime import datetime

# --------------------- STREAMLIT CONFIG ---------------------
st.set_page_config("ExoticBill", page_icon="🧾")

# --------------------- SESSION STATE INIT ---------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = ""

# --------------------- DATABASE INIT ---------------------
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

# --------------------- DATABASE HELPERS ---------------------
def save_bill(employee_cid, customer_cid, billing_type, details, total_amount):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO bills (employee_cid, customer_cid, billing_type, details, total_amount)
        VALUES (?, ?, ?, ?, ?)
    """, (employee_cid, customer_cid, billing_type, details, total_amount))
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
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

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
    for billing_type in ["ITEMS", "UPGRADES", "REPAIR", "CUSTOMIZATION"]:
        c.execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid = ? AND billing_type = ?", (cid, billing_type))
        amt = c.fetchone()[0]
        summary[billing_type] = amt if amt else 0
        total += summary[billing_type]
    conn.close()
    return summary, total

# --------------------- LOGIN FUNCTION ---------------------
def login(username, password):
    if username == "AutoExotic" and password == "AutoExotic123":
        st.session_state.logged_in = True
        st.session_state.role = "admin"
        st.session_state.username = username
    elif username == "User" and password == "User123":
        st.session_state.logged_in = True
        st.session_state.role = "user"
        st.session_state.username = username
    else:
        st.error("Invalid credentials")

# --------------------- LOGIN FORM ---------------------
if not st.session_state.logged_in:
    st.title("🧾 ExoticBill Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            login(username, password)
    st.stop()

# --------------------- LOGOUT SIDEBAR ---------------------
with st.sidebar:
    st.success(f"Logged in as: {st.session_state.username}")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.username = ""
        st.rerun()

# --------------------- BILLING CONSTANTS ---------------------
ITEM_PRICES = {
    "Repair Kit": 400,
    "Car Wax": 2000,
    "NOS": 1500,
    "Adv Lockpick": 400,
    "Lockpick": 250,
    "Wash Kit": 300
}
PART_REPAIR_COST = 125
NORMAL_REPAIR_LABOR = 450

# --------------------- USER DASHBOARD ---------------------
if st.session_state.role == "user":
    st.title("🧾 ExoticBill - Add New Bill")

    employee_cid = st.text_input("Your CID (Employee)")
    customer_cid = st.text_input("Customer CID")
    billing_type = st.selectbox("Select Billing Type", ["ITEMS", "UPGRADES", "REPAIR", "CUSTOMIZATION"])

    total = 0
    details = ""

    if billing_type == "ITEMS":
        selected_items = {}
        for item, price in ITEM_PRICES.items():
            qty = st.number_input(f"{item} (${price})", min_value=0, step=1)
            if qty > 0:
                selected_items[item] = qty
                total += price * qty
        details = ", ".join([f"{item} × {qty}" for item, qty in selected_items.items()])

    elif billing_type == "UPGRADES":
        amt = st.number_input("Enter base upgrade amount", min_value=0.0)
        total = amt * 1.5
        details = f"Base Upgrade: ${amt}"

    elif billing_type == "REPAIR":
        rtype = st.radio("Select Type", ["Normal Repair", "Advanced Repair"])
        if rtype == "Normal Repair":
            base = st.number_input("Enter base repair charge", min_value=0.0)
            total = base + NORMAL_REPAIR_LABOR
            details = f"Normal Repair: ${base} + ${NORMAL_REPAIR_LABOR} labor"
        else:
            parts = st.number_input("Parts repaired", min_value=0, step=1)
            total = parts * PART_REPAIR_COST
            details = f"Advanced Repair: {parts} × ${PART_REPAIR_COST}"

    elif billing_type == "CUSTOMIZATION":
        amt = st.number_input("Enter base customization amount", min_value=0.0)
        total = amt * 2
        details = f"Customization: Base ${amt} × 2"

    if st.button("💾 Save Bill"):
        if not employee_cid or not customer_cid or total == 0:
            st.warning("Please fill all required fields.")
        else:
            save_bill(employee_cid, customer_cid, billing_type, details, total)
            st.success(f"Bill Saved! Total: ${total:.2f}")

# --------------------- ADMIN DASHBOARD ---------------------
elif st.session_state.role == "admin":
    st.title("👑 ExoticBill Admin Panel")

    st.subheader("➕ Add New Employee")
    with st.form("add_employee"):
        new_cid = st.text_input("New Employee CID")
        new_name = st.text_input("Employee Name")
        submit_emp = st.form_submit_button("Add Employee")
        if submit_emp and new_cid and new_name:
            add_employee(new_cid, new_name)
            st.success("Employee added successfully!")

    st.markdown("---")
    st.subheader("📊 Billing Summary by Employee CID")

    cid_options = get_all_employee_cids()
    if cid_options:
        cid_dict = {f"{name} ({cid})": cid for cid, name in cid_options}
        selected_display = st.selectbox("Select Employee", list(cid_dict.keys()))
        selected_cid = cid_dict[selected_display]
        name = get_employee_name(selected_cid)

        summary, total = get_billing_summary_by_cid(selected_cid)

        st.info(f"Selected: {name} (CID: {selected_cid})")
        st.metric("💰 Total Billing", f"${total:.2f}")
        st.markdown(f"- ITEMS: ${summary['ITEMS']:.2f}")
        st.markdown(f"- UPGRADES: ${summary['UPGRADES']:.2f}")
        st.markdown(f"- REPAIR: ${summary['REPAIR']:.2f}")
        st.markdown(f"- CUSTOMIZATION: ${summary['CUSTOMIZATION']:.2f}")
    else:
        st.warning("No employees found. Please add an employee.")

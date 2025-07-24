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
        )"""
    )
    c.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            cid TEXT PRIMARY KEY,
            name TEXT
        )"""
    )
    conn.commit()
    conn.close()

init_db()

# --------- DB HELPERS -----------
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

def delete_employee(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("DELETE FROM employees WHERE cid = ?", (cid,))
    conn.commit()
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
    summary, total = {}, 0
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
    total = c.fetchone()[0] or 0
    conn.close()
    return total

def delete_bill_by_id(bill_id):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
    conn.commit()
    conn.close()
    st.success("Bill deleted successfully!")

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
        st.experimental_rerun()

# --------- USER PANEL -----------
if st.session_state.role == "user":
    st.title("🧾 ExoticBill - Add New Bill")
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ${st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    ITEM_PRICES = {
        "Repair Kit": 400, "Car Wax": 2000, "NOS": 1500,
        "Adv Lockpick": 400, "Lockpick": 250, "Wash Kit": 300
    }
    PART_COST, LABOR = 125, 450

    billing_type = st.selectbox("Select Billing Type",
        ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"])

    if billing_type == "REPAIR":
        repair_type = st.radio("Repair Type",
            ["Normal Repair","Advanced Repair"])
    else:
        repair_type = None

    with st.form("bill_form", clear_on_submit=True):
        emp = st.text_input("Your CID (Employee)")
        cust = st.text_input("Customer CID")
        total, details = 0.0, ""

        if billing_type == "ITEMS":
            sel = {}
            for item, price in ITEM_PRICES.items():
                qty = st.number_input(f"{item} (${price}) – Qty", min_value=0, step=1, key=item)
                if qty:
                    sel[item] = qty
                    total += price * qty
            details = ", ".join(f"{i}×{q}" for i,q in sel.items())

        elif billing_type == "UPGRADES":
            amt = st.number_input("Base upgrade amount ($)", min_value=0.0)
            total = amt * 1.5
            details = f"Upgrade: ${amt}"

        elif billing_type == "REPAIR":
            if repair_type == "Normal Repair":
                base = st.number_input("Base repair charge ($)", min_value=0.0)
                total = base + LABOR
                details = f"Normal Repair: ${base} + ${LABOR} labor"
            else:
                parts = st.number_input("Number of parts repaired", min_value=0, step=1)
                total = parts * PART_COST
                details = f"Advanced Repair: {parts}×${PART_COST}"

        else:  # CUSTOMIZATION
            c_amt = st.number_input("Base customization amount ($)", min_value=0.0)
            total = c_amt * 2
            details = f"Customization: ${c_amt}×2"

        if st.form_submit_button("💾 Save Bill"):
            if not emp or not cust or total == 0:
                st.warning("Please fill all fields correctly.")
            else:
                save_bill(emp, cust, billing_type, details, total)
                st.session_state.bill_saved = True
                st.session_state.bill_total = total

# --------- ADMIN PANEL -----------
elif st.session_state.role == "admin":
    st.title("👑 ExoticBill Admin Panel")

    # Phase 1: Business Overview
    st.subheader("📈 Business Overview")
    total_biz = get_total_billing()
    st.metric("💵 Total Revenue", f"${total_biz:.2f}")

    # Phase 1: Employee Management
    st.markdown("---")
    st.subheader("➕ Add New Employee")
    with st.form("add_employee"):
        new_cid = st.text_input("New Employee CID")
        new_name = st.text_input("Employee Name")
        if st.form_submit_button("Add Employee"):
            add_employee(new_cid, new_name)
            st.success("Employee added successfully!")
            st.experimental_rerun()

    st.subheader("➖ Delete Employee")
    emps = get_all_employee_cids()
    if emps:
        del_opts = {f"{name} ({cid})": cid for cid,name in emps}
        sel_del = st.selectbox("Select Employee to Delete", list(del_opts.keys()), key="del_emp")
        if st.button("Delete Employee"):
            delete_employee(del_opts[sel_del])
            st.success(f"Deleted {sel_del} from employees.")
            st.experimental_rerun()
    else:
        st.info("No employees to delete.")

    # Continue with existing Employee/Customer views...
    choice = st.radio("Action", ["View Employee Billings","View Customer Data"])

    if choice == "View Employee Billings":
        # … existing code for employee billing summary & details …

    else:
        # … existing code for customer data table …

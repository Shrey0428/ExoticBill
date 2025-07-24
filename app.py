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
    st.session_state.bill_total = 0.0

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
    conn.commit()
    conn.close()

init_db()

# --------- DB HELPERS -----------
def save_bill(employee_cid, customer_cid, billing_type, details, total_amount):
    conn = sqlite3.connect("auto_exotic_billing.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO bills (employee_cid, customer_cid, billing_type, details, total_amount) "
        "VALUES (?, ?, ?, ?, ?)",
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
    summary = {}
    total = 0.0
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
    st.success("Bill deleted successfully!")
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

    # show success if saved
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ${st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

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

    billing_type = st.selectbox(
        "Select Billing Type",
        ["ITEMS", "UPGRADES", "REPAIR", "CUSTOMIZATION"]
    )

    # repair type outside form for dynamic rerun
    if billing_type == "REPAIR":
        repair_type = st.radio("Repair Type", ["Normal Repair", "Advanced Repair"])
    else:
        repair_type = None

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

    # — Phase 1.1: Business Overview —
    st.subheader("📈 Business Overview")
    total_biz = get_total_billing()
    st.metric("💵 Total Revenue", f"${total_biz:.2f}")

    # — Phase 1.2: Employee Management —
    st.markdown("---")
    st.subheader("➕ Add New Employee")
    with st.form("add_employee"):
        new_cid = st.text_input("New Employee CID")
        new_name = st.text_input("Employee Name")
        if st.form_submit_button("Add Employee"):
            if new_cid and new_name:
                add_employee(new_cid, new_name)
                st.success("Employee added successfully!")
                st.experimental_rerun()

    st.subheader("➖ Delete Employee")
    emps = get_all_employee_cids()
    if emps:
        del_opts = {f"{name} ({cid})": cid for cid, name in emps}
        sel_del = st.selectbox("Select Employee to Delete", list(del_opts.keys()))
        if st.button("Delete Employee"):
            delete_employee(del_opts[sel_del])
            st.success(f"Deleted {sel_del}.")
            st.experimental_rerun()
    else:
        st.info("No employees to delete.")

    st.markdown("---")
    choice = st.radio("Action", ["View Employee Billings", "View Customer Data"])

    # — Phase 1.3: View Employee Billings —
    if choice == "View Employee Billings":
        emps = get_all_employee_cids()
        if emps:
            cid_dict = {f"{name} ({cid})": cid for cid, name in emps}
            selected_display = st.selectbox("Select Employee", list(cid_dict.keys()))
            selected_cid = cid_dict[selected_display]
            name = get_employee_name(selected_cid)

            view_type = st.radio("View Type", ["Overall Billings", "Detailed Billings"])
            if view_type == "Overall Billings":
                summary, total = get_billing_summary_by_cid(selected_cid)
                st.info(f"{name} (CID: {selected_cid})")
                st.metric("💰 Total Billing", f"${total:.2f}")
                st.markdown(f"- ITEMS: ${summary['ITEMS']:.2f}")
                st.markdown(f"- UPGRADES: ${summary['UPGRADES']:.2f}")
                st.markdown(f"- REPAIR: ${summary['REPAIR']:.2f}")
                st.markdown(f"- CUSTOMIZATION: ${summary['CUSTOMIZATION']:.2f}")
            else:  # Detailed Billings
                rows = get_employee_bills(selected_cid)
                if rows:
                    df = pd.DataFrame(
                        rows,
                        columns=["Bill ID", "Customer CID", "Type", "Details", "Amount", "Timestamp"]
                    )
                    for _, row in df.iterrows():
                        with st.expander(f"#{row['Bill ID']} — ${row['Amount']:.2f}"):
                            st.write(row.drop("Bill ID"))
                            if st.button(f"🗑️ Delete #{row['Bill ID']}", key=f"del_{row['Bill ID']}"):
                                delete_bill_by_id(row['Bill ID'])
                else:
                    st.info("No bills for this employee.")
        else:
            st.warning("No employees found.")

    # — Phase 1.4: View Customer Data —
    else:
        st.subheader("📂 Customer Order History")
        customers = get_all_customers()
        if customers:
            sel_cust = st.selectbox("Select Customer CID", customers)
            data = get_customer_bills(sel_cust)
            if data:
                df = pd.DataFrame(
                    data,
                    columns=["Employee CID", "Type", "Details", "Amount", "Timestamp"]
                )
                st.table(df)
            else:
                st.info("No records for this customer.")
        else:
            st.warning("No customer data found.")

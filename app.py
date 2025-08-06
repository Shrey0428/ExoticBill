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
    "Trainee": 0.10,
    "Mechanic": 0.15,
    "Senior Mechanic": 0.18,
    "Lead Upgrade Specialist": 0.20,
    "Stock Manager": 0.15,
    "Manager": 0.25,
}
TAX_RATE = 0.05  # 5% on the commission

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
        timestamp TEXT
      )
    """)
    # employees
    c.execute("""
      CREATE TABLE IF NOT EXISTS employees (
        cid TEXT PRIMARY KEY,
        name TEXT
      )
    """)
    # memberships
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
    # hoods
    c.execute("""
      CREATE TABLE IF NOT EXISTS hoods (
        name TEXT PRIMARY KEY,
        location TEXT
      )
    """)

    # migrate employees: rank, hood
    c.execute("PRAGMA table_info(employees)")
    cols = [r[1] for r in c.fetchall()]
    if "rank" not in cols:
        c.execute("ALTER TABLE employees ADD COLUMN rank TEXT DEFAULT 'Trainee'")
    if "hood" not in cols:
        c.execute("ALTER TABLE employees ADD COLUMN hood TEXT DEFAULT 'No Hood'")

    # migrate bills: commission & tax
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
    # archive
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
    # delete
    c.execute("DELETE FROM memberships WHERE dop <= ?", (cutoff_str,))
    conn.commit()
    conn.close()

purge_expired_memberships()

# ---------- DATABASE HELPERS -----------
def save_bill(emp, cust, btype, det, amt):
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    rank = get_employee_rank(emp)
    comm_rate = COMMISSION_RATES.get(rank, 0)
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

def get_employee_rank(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT rank FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    return row[0] if row else "Trainee"

def get_employee_details(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute(
        "SELECT name, rank, hood FROM employees WHERE cid = ?", (cid,)
    ).fetchone()
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
    conn.execute("INSERT OR REPLACE INTO memberships (customer_cid, tier, dop) VALUES (?,?,?)", (cust, tier, dop_ist))
    conn.commit()
    conn.close()

def remove_membership(cust):
    conn = sqlite3.connect("auto_exotic_billing.db")
    conn.execute("DELETE FROM memberships WHERE customer_cid = ?", (cust,))
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
    rows = conn.execute("SELECT customer_cid, tier, dop, expired_at FROM membership_history ORDER BY expired_at DESC").fetchall()
    conn.close()
    return rows

def get_employee_name(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    row = conn.execute("SELECT name FROM employees WHERE cid = ?", (cid,)).fetchone()
    conn.close()
    return row[0] if row else cid

def get_billing_summary_by_cid(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    summary, total = {}, 0.0
    for bt in ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"]:
        amt = conn.execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid=? AND billing_type=?", (cid, bt)).fetchone()[0] or 0.0
        summary[bt] = amt
        total += amt
    conn.close()
    return summary, total

def get_employee_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT id, customer_cid, billing_type, details, total_amount, timestamp, commission, tax"
        " FROM bills WHERE employee_cid=?", (cid,)
    ).fetchall()
    conn.close()
    return rows

def get_all_customers():
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT DISTINCT customer_cid FROM bills").fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_customer_bills(cid):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute(
        "SELECT employee_cid, billing_type, details, total_amount, timestamp, commission, tax"
        " FROM bills WHERE customer_cid=?", (cid,)
    ).fetchall()
    conn.close()
    return rows

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

def assign_employees_to_hood(hood, cids):
    conn = sqlite3.connect("auto_exotic_billing.db")
    for cid in cids:
        conn.execute("UPDATE employees SET hood=? WHERE cid=?", (hood, cid))
    conn.commit()
    conn.close()

def get_employees_by_hood(hood):
    conn = sqlite3.connect("auto_exotic_billing.db")
    rows = conn.execute("SELECT cid, name FROM employees WHERE hood=?", (hood,)).fetchall()
    conn.close()
    return rows

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
    st.title("🧾 ExoticBill - Add New Bill")
    if st.session_state.bill_saved:
        st.success(f"Bill saved! Total: ₹{st.session_state.bill_total:.2f}")
        st.session_state.bill_saved = False

    btype = st.selectbox("Select Billing Type", ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"], key="btype_user")
    rtype = None
    if btype == "REPAIR":
        rtype = st.radio("Repair Type", ["Normal Repair","Advanced Repair"], key="rtype_user")

    with st.form("bill_form", clear_on_submit=True):
        emp_cid = st.text_input("Your CID (Employee)", key="bill_emp")
        cust_cid = st.text_input("Customer CID", key="bill_cust")
        total, det = 0.0, ""

        if btype == "ITEMS":
            sel = {}
            for item, price in ITEM_PRICES.items():
                q = st.number_input(f"{item} (₹{price}) – Qty", min_value=0, step=1, key=f"qty_{item}")
                if q:
                    sel[item] = q
                    total += price * q
            det = ", ".join(f"{i}×{q}" for i,q in sel.items())

        elif btype == "UPGRADES":
            amt = st.number_input("Base upgrade amount (₹)", min_value=0.0, key="upgrade_amt")
            total = amt * 1.5
            det = f"Upgrade: ₹{amt}"

        elif btype == "REPAIR":
            if rtype == "Normal Repair":
                b = st.number_input("Base repair charge (₹)", min_value=0.0, key="norm_rep")
                total = b + LABOR
                det = f"Normal Repair: ₹{b}+₹{LABOR}"
            else:
                p = st.number_input("Number of parts repaired", min_value=0, step=1, key="adv_rep")
                total = p * PART_COST
                det = f"Advanced Repair: {p}×₹{PART_COST}"

        else:
            c_amt = st.number_input("Base customization amount (₹)", min_value=0.0, key="cust_amt")
            total = c_amt * 2
            det = f"Customization: ₹{c_amt}×2"

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
    st.subheader("🎟️ Manage Membership")
    with st.form("mem_form_user", clear_on_submit=True):
        m_cust = st.text_input("Customer CID", key="mem_cust")
        m_tier = st.selectbox("Tier", ["Tier1","Tier2","Tier3","Racer"], key="mem_tier")
        if st.form_submit_button("Add/Update Membership"):
            if m_cust:
                add_membership(m_cust, m_tier)
                st.success("Membership updated!")

    st.subheader("🔍 Check Membership")
    lookup = st.text_input("Customer CID to check", key="lookup_user")
    if st.button("Check Membership", key="check_mem"):
        mem = get_membership(lookup)
        if mem:
            tier, dop_str = mem["tier"], mem["dop"]
            dop = datetime.strptime(dop_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            expiry = dop + timedelta(days=7)
            rem = expiry - datetime.now(IST)
            st.info(
                f"{lookup}: {tier}, expires in {rem.days}d "
                f"{rem.seconds//3600}h on {expiry.strftime('%Y-%m-%d %H:%M:%S')} IST"
            )
        else:
            st.info(f"Membership expired for {lookup}")

# ---------- ADMIN PANEL & MAIN MENU -----------
elif st.session_state.role == "admin":
    st.title("👑 ExoticBill Admin")
    st.metric("💵 Total Revenue", f"₹{get_total_billing():,.2f}")

    st.markdown("---")
    st.subheader("🧹 Maintenance")
    confirm = st.checkbox("I understand this will erase all billing history", key="confirm_reset")
    if confirm and st.button("⚠️ Reset All Billings"):
        conn = sqlite3.connect("auto_exotic_billing.db")
        conn.execute("DELETE FROM bills")
        conn.commit()
        conn.close()
        st.success("All billing records have been reset.")

    menu = st.sidebar.selectbox("Main Menu",
        ["Sales", "Manage Hoods", "Manage Staff", "Tracking"], index=0)

    if menu == "Sales":
        st.header("💹 Sales Overview")
        total_sales = get_total_billing()
        bill_count = get_bill_count()
        avg_sale = total_sales / bill_count if bill_count else 0.0
        sum_comm, sum_tax = get_total_commission_and_tax()
        profit = total_sales - (sum_comm + sum_tax)

        st.metric("Total Sales", f"₹{total_sales:,.2f}")
        st.metric("Average Sale", f"₹{avg_sale:,.2f}")
        st.metric("Total Commission Paid", f"₹{sum_comm:,.2f}")
        st.metric("Total Tax on Commission", f"₹{sum_tax:,.2f}")
        st.metric("Estimated Profit", f"₹{profit:,.2f}")

    elif menu == "Manage Hoods":
        st.header("🏙️ Manage Hoods")
        tabs = st.tabs(["Add Hood", "Edit Hood", "Assign Staff", "View Hoods"])

        with tabs[0]:
            st.subheader("➕ Add New Hood")
            with st.form("add_hood", clear_on_submit=True):
                hname = st.text_input("Hood Name")
                hloc  = st.text_input("Location")
                if st.form_submit_button("Add Hood"):
                    if hname and hloc:
                        add_hood(hname, hloc)
                        st.success(f"Added hood '{hname}'")

        with tabs[1]:
            st.subheader("✏️ Edit / Delete Hood")
            hoods = get_all_hoods()
            if hoods:
                names = [r[0] for r in hoods]
                sel = st.selectbox("Select Hood", names, key="edit_hood_sel")
                old_loc = dict(hoods)[sel]
                new_name    = st.text_input("New Name", sel)
                new_location= st.text_input("New Location", old_loc)
                if st.button("Update Hood"):
                    update_hood(sel, new_name, new_location)
                    st.success("Hood updated.")
                if st.button("Delete Hood"):
                    delete_hood(sel)
                    st.success("Hood deleted.")
            else:
                st.info("No hoods defined yet.")

        with tabs[2]:
            st.subheader("👷 Assign Employees to Hood")
            hoods = get_all_hoods()
            if hoods:
                hood_names = [r[0] for r in hoods]
                sel_hood = st.selectbox("Select Hood", hood_names, key="assign_hood_sel")
                all_emp = get_all_employee_cids()
                choices = {f"{n} ({c})": c for c,n in all_emp}
                sel_list = st.multiselect("Select Employees to assign", list(choices.keys()), key="assign_emp_sel")
                if st.button("Assign"):
                    cids = [choices[k] for k in sel_list]
                    assign_employees_to_hood(sel_hood, cids)
                    st.success("Employees reassigned.")
            else:
                st.info("Define some hoods first.")

        with tabs[3]:
            st.subheader("🔍 View Hoods & Members")
            hoods = get_all_hoods()
            if hoods:
                for name, loc in hoods:
                    with st.expander(f"{name} — {loc}"):
                        emps = get_employees_by_hood(name)
                        if emps:
                            df = pd.DataFrame(emps, columns=["CID","Name"])
                            st.table(df)
                        else:
                            st.write("No employees assigned.")
            else:
                st.info("No hoods to view.")

    elif menu == "Manage Staff":
        st.header("👷 Manage Staff")
        tabs = st.tabs(["➕ Add Employee","🗑️ Remove Employee","✏️ Edit Employee"])

        # Add Employee
        with tabs[0]:
            st.subheader("➕ Add New Employee")
            with st.form("add_emp", clear_on_submit=True):
                new_cid  = st.text_input("Employee CID")
                new_name = st.text_input("Name")
                new_rank = st.selectbox("Rank", list(COMMISSION_RATES.keys()))
                hoods    = [h[0] for h in get_all_hoods()] or []
                new_hood = st.selectbox("Hood", ["No Hood"] + hoods)
                if st.form_submit_button("Add Employee"):
                    if new_cid and new_name:
                        add_employee(new_cid, new_name, new_rank)
                        if new_hood != "No Hood":
                            update_employee(new_cid, hood=new_hood)
                        st.success(f"Added employee {new_name} ({new_cid})")
                    else:
                        st.warning("CID and Name are required.")

        # Remove Employee
        with tabs[1]:
            st.subheader("🗑️ Remove Employee")
            all_emp = get_all_employee_cids()
            options = {f"{n} ({c})": c for c,n in all_emp}
            sel = st.selectbox("Select Employee to Remove", list(options.keys()))
            if st.button("Delete Employee"):
                delete_employee(options[sel])
                st.success(f"Removed {sel}")

        # Edit Employee
        with tabs[2]:
            st.subheader("✏️ Edit Employee")
            all_emp = get_all_employee_cids()
            opts = {f"{n} ({c})": c for c,n in all_emp}
            sel_emp = st.selectbox("Select Employee", list(opts.keys()))
            details = get_employee_details(opts[sel_emp])
            if details:
                with st.form("edit_emp", clear_on_submit=True):
                    name = st.text_input("Name", details["name"])
                    rank = st.selectbox("Rank", list(COMMISSION_RATES.keys()),
                                        index=list(COMMISSION_RATES.keys()).index(details["rank"]))
                    hoods_list = [h[0] for h in get_all_hoods()] or []
                    hood = st.selectbox("Hood", ["No Hood"] + hoods_list,
                                        index=(["No Hood"] + hoods_list).index(details["hood"])
                                              if details["hood"] in hoods_list else 0)
                    if st.form_submit_button("Update Employee"):
                        update_employee(opts[sel_emp], name=name, rank=rank, hood=hood)
                        st.success(f"Updated {sel_emp}")

    else:  # Tracking
        st.header("📊 Tracking")
        tabs = st.tabs(["Employee","Customer","Hood","Membership"])

        # Employee Tracking
       with tabs[0]:
            st.subheader("Employee Billing")
        
            # — filter by rank —
            ranks = ["All"] + list(COMMISSION_RATES.keys())
            sel_rank = st.selectbox("Filter by Rank", ranks)
        
            # build filtered employee list
            all_emps = get_all_employee_cids()
            if sel_rank != "All":
                all_emps = [(cid,name) for cid,name in all_emps if get_employee_rank(cid) == sel_rank]
        
            emp_opts = {f"{name} ({cid})": cid for cid,name in all_emps}
            sel = st.selectbox("Select Employee", list(emp_opts.keys()))
        
            view = st.radio("View", ["Overall","Detailed"], horizontal=True)
            cid = emp_opts[sel]

    if view == "Overall":
        summary, total = get_billing_summary_by_cid(cid)
        for k,v in summary.items():
            st.metric(k, f"₹{v:.2f}")
        st.metric("Total", f"₹{total:.2f}")
    else:
        rows = get_employee_bills(cid)
        df = pd.DataFrame(rows, columns=["ID","Customer","Type","Details","Amount","Time","Commission","Tax"])
        st.dataframe(df)

            if view == "Overall":
                summary, total = get_billing_summary_by_cid(cid)
                for k,v in summary.items():
                    st.metric(k, f"₹{v:.2f}")
                st.metric("Total", f"₹{total:.2f}")
            else:
                rows = get_employee_bills(cid)
                df = pd.DataFrame(rows, columns=["ID","Customer","Type","Details","Amount","Time","Commission","Tax"])
                st.dataframe(df)

        # Customer Tracking
        with tabs[1]:
            st.subheader("Customer Billing History")
            cust = st.selectbox("Select Customer", get_all_customers())
            rows = get_customer_bills(cust)
            df = pd.DataFrame(rows, columns=["Employee","Type","Details","Amount","Time","Commission","Tax"])
            st.dataframe(df)

        # Hood Tracking
        with tabs[2]:
            st.subheader("Hood Summary")
            hood_names = [h[0] for h in get_all_hoods()]
            sel_hood = st.selectbox("Select Hood", hood_names)
            emps = get_employees_by_hood(sel_hood)
            data = []
            for cid, name in emps:
                _, total = get_billing_summary_by_cid(cid)
                data.append({"CID": cid, "Name": name, "Total": total})
            st.table(pd.DataFrame(data))

        # Membership Tracking
        with tabs[3]:
            st.subheader("📋 Memberships")
            view = st.radio("Show", ["Active", "Past"], horizontal=True)

            if view == "Active":
                rows = get_all_memberships()
                data = []
                for cid, tier, dop_str in rows:
                    dop = datetime.strptime(dop_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
                    expiry = dop + timedelta(days=7)
                    rem = expiry - datetime.now(IST)
                    data.append({
                        "Customer CID": cid,
                        "Tier": tier,
                        "Started On": dop.strftime("%Y-%m-%d %H:%M:%S"),
                        "Expires On": expiry.strftime("%Y-%m-%d %H:%M:%S"),
                        "Remaining": f"{rem.days}d {rem.seconds//3600}h"
                    })
                st.table(pd.DataFrame(data))

            else:  # Past
                rows = get_past_memberships()
                data = []
                for cid, tier, dop_str, expired_str in rows:
                    data.append({
                        "Customer CID": cid,
                        "Tier": tier,
                        "Started On": dop_str,
                        "Expired At": expired_str
                    })
                st.table(pd.DataFrame(data))

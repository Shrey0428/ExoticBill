import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
st.set_page_config("ExoticBill", "🧾")
for k, d in [("logged_in", False),("role",None),("username",""),("bill_saved",False),("bill_total",0.0)]:
    st.session_state.setdefault(k, d)

ITEM_PRICES={"Repair Kit":400,"Car Wax":2000,"NOS":1500,"Adv Lockpick":400,"Lockpick":250,"Wash Kit":300}
PART_COST,LABOR=125,450
MEMBERSHIP_DISCOUNTS={"Tier1":{"REPAIR":0.20,"CUSTOMIZATION":0.10},
                      "Tier2":{"REPAIR":0.33,"CUSTOMIZATION":0.20},
                      "Tier3":{"REPAIR":0.50,"CUSTOMIZATION":0.30},
                      "Racer":{"REPAIR":0.00,"CUSTOMIZATION":0.00}}
COMMISSION_RATES={"Trainee":0.10,"Mechanic":0.15,"Senior Mechanic":0.18,
                  "Lead Upgrade Specialist":0.20,"Stock Manager":0.15,"Manager":0.25}
TAX_RATE=0.05

def init_db():
    c=sqlite3.connect("auto_exotic_billing.db").cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS bills(id INTEGER PRIMARY KEY,employee_cid,customer_cid,billing_type,details,total_amount,timestamp,commission DEFAULT 0,tax DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS employees(cid PRIMARY KEY,name,rank DEFAULT 'Trainee',hood DEFAULT 'No Hood')""")
    c.execute("""CREATE TABLE IF NOT EXISTS memberships(customer_cid PRIMARY KEY,tier,dop)""")
    c.execute("""CREATE TABLE IF NOT EXISTS membership_history(customer_cid,tier,dop,expired_at)""")
    c.execute("""CREATE TABLE IF NOT EXISTS hoods(name PRIMARY KEY,location)""")
    c.connection.commit(),c.connection.close()

init_db()

def purge():
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    cutoff=(datetime.now(IST)-timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    exp=c.execute("SELECT customer_cid,tier,dop FROM memberships WHERE dop<=?",(cutoff,)).fetchall()
    for cid,tier,d in exp:
        try: dop=datetime.strptime(d,"%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
        except: dop=datetime.now(IST)-timedelta(days=7)
        exp_at=(dop+timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO membership_history VALUES(?,?,?,?)",(cid,tier,d,exp_at))
    c.execute("DELETE FROM memberships WHERE dop<=?",(cutoff,))
    db.commit(),db.close()

purge()

def save_bill(emp,cust,btype,det,amt):
    now=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    comm=amt*COMMISSION_RATES.get(get_rank(emp),0)
    tax=comm*TAX_RATE
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    c.execute("INSERT INTO bills(employee_cid,customer_cid,billing_type,details,total_amount,timestamp,commission,tax) VALUES(?,?,?,?,?,?,?,?)",
              (emp,cust,btype,det,amt,now,comm,tax))
    db.commit(),db.close()

def add_employee(cid,name,rank="Trainee"):
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    try: c.execute("INSERT INTO employees(cid,name,rank) VALUES(?,?,?)",(cid,name,rank));db.commit()
    except: st.warning("CID exists")
    db.close()

def delete_employee(cid):
    db=sqlite3.connect("auto_exotic_billing.db");db.cursor().execute("DELETE FROM employees WHERE cid=?",(cid,));db.commit();db.close()

def update_employee(cid,name=None,rank=None,hood=None):
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    if name: c.execute("UPDATE employees SET name=? WHERE cid=?",(name,cid))
    if rank: c.execute("UPDATE employees SET rank=? WHERE cid=?",(rank,cid))
    if hood: c.execute("UPDATE employees SET hood=? WHERE cid=?",(hood,cid))
    db.commit(),db.close()

def get_rank(cid):
    row=sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT rank FROM employees WHERE cid=?",(cid,)).fetchone()
    return row[0] if row else "Trainee"

def get_details(cid):
    row=sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT name,rank,hood FROM employees WHERE cid=?",(cid,)).fetchone()
    return {"name":row[0],"rank":row[1],"hood":row[2]} if row else None

def all_cids(): return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT cid,name FROM employees").fetchall()
def add_mem(cust,tier):
    now=datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    c.execute("INSERT OR REPLACE INTO memberships VALUES(?,?,?)",(cust,tier,now));db.commit();db.close()

def get_mem(cust):
    row=sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT tier,dop FROM memberships WHERE customer_cid=?",(cust,)).fetchone()
    return {"tier":row[0],"dop":row[1]} if row else None

def all_mems(): return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT customer_cid,tier,dop FROM memberships").fetchall()
def past_mems(): return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT customer_cid,tier,dop,expired_at FROM membership_history ORDER BY expired_at DESC").fetchall()

def summary(cid):
    c=sqlite3.connect("auto_exotic_billing.db").cursor()
    s,t={},0.0
    for bt in ["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"]:
        v=c.execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid=? AND billing_type=?",(cid,bt)).fetchone()[0] or 0.0
        s[bt]=v; t+=v
    return s,t

def emp_bills(cid):
    return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT id,customer_cid,billing_type,details,total_amount,timestamp,commission,tax FROM bills WHERE employee_cid=?",(cid,)).fetchall()

def all_customers():
    return [r[0] for r in sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT DISTINCT customer_cid FROM bills").fetchall()]

def cust_bills(cid):
    return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT employee_cid,billing_type,details,total_amount,timestamp,commission,tax FROM bills WHERE customer_cid=?",(cid,)).fetchall()

def total_billing():
    return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT SUM(total_amount) FROM bills").fetchone()[0] or 0.0

def bill_count():
    return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT COUNT(*) FROM bills").fetchone()[0] or 0

def comm_tax():
    row=sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT SUM(commission),SUM(tax) FROM bills").fetchone()
    return row[0] or 0.0,row[1] or 0.0

def add_hood(name,loc):
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    try: c.execute("INSERT INTO hoods VALUES(?,?)",(name,loc));db.commit()
    except: st.warning("Exists")
    db.close()

def upd_hood(o,n,l):
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    c.execute("UPDATE hoods SET name=?,location=? WHERE name=?",(n,l,o))
    c.execute("UPDATE employees SET hood=? WHERE hood=?",(n,o))
    db.commit(),db.close()

def del_hood(name):
    db=sqlite3.connect("auto_exotic_billing.db");c=db.cursor()
    c.execute("DELETE FROM hoods WHERE name=?",(name,));c.execute("UPDATE employees SET hood='No Hood' WHERE hood=?",(name,))
    db.commit(),db.close()

def get_hoods():
    return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT name,location FROM hoods").fetchall()

def emp_by_hood(h):
    return sqlite3.connect("auto_exotic_billing.db").cursor().execute("SELECT cid,name FROM employees WHERE hood=?",(h,)).fetchall()

def login(u,p):
    if u=="AutoExotic" and p=="AutoExotic123":
        st.session_state.logged_in,st.session_state.role,st.session_state.username=True,"admin",u
    elif u=="User" and p=="User123":
        st.session_state.logged_in,st.session_state.role,st.session_state.username=True,"user",u
    else: st.error("Invalid")

if not st.session_state.logged_in:
    st.title("Login"); 
    with st.form("login_form",clear_on_submit=True):
        u=st.text_input("User",key="login_u")
        p=st.text_input("Pass",type="password",key="login_p")
        if st.form_submit_button("Login",key="login_btn"): login(u,p)
    st.stop()

with st.sidebar:
    st.success(f"{st.session_state.username}",icon="✅")
    if st.button("Logout",key="logout"): st.session_state.clear(),st.experimental_rerun()

if st.session_state.role=="user":
    st.title("Add Bill")
    if st.session_state.bill_saved:
        st.success(f"Saved ₹{st.session_state.bill_total:.2f}");st.session_state.bill_saved=False
    b=st.selectbox("Type",["ITEMS","UPGRADES","REPAIR","CUSTOMIZATION"],key="u_btype")
    r=st.radio("Repair",["Normal","Advanced"],key="u_rtype") if b=="REPAIR" else None
    with st.form("f1",clear_on_submit=True):
        e=st.text_input("Your CID",key="u_e")
        c=st.text_input("Customer CID",key="u_c")
        tot,det=0.0,""
        if b=="ITEMS":
            sel={}
            for i,p in ITEM_PRICES.items():
                q=st.number_input(f"{i} (₹{p}) qty",key=f"u_q_{i}")
                if q: sel[i]=q;tot+=p*q
            det=", ".join(f"{i}×{q}" for i,q in sel.items())
        elif b=="UPGRADES":
            a=st.number_input("Amt",key="u_upg");tot=a*1.5;det=f"Upg ₹{a}"
        elif b=="REPAIR":
            if r=="Normal":
                a=st.number_input("Base",key="u_nr");tot=a+LABOR;det=f"Norm ₹{a}+₹{LABOR}"
            else:
                a=st.number_input("Parts",key="u_ar");tot=a*PART_COST;det=f"Adv {a}×₹{PART_COST}"
        else:
            a=st.number_input("Amt",key="u_cust");tot=a*2;det=f"Cust ₹{a}×2"
        m=get_mem(c)
        if m:
            d=MEMBERSHIP_DISCOUNTS.get(m["tier"],{}).get(b,0)
            if d>0: tot*=(1-d);det+=f" |{int(d*100)}% off"
        if st.form_submit_button("Save",key="u_save"):
            if e and c and tot>0:
                save_bill(e,c,b,det,tot);st.session_state.bill_saved=True;st.session_state.bill_total=tot
            else: st.warning("Fill all")
    st.markdown("---")
    with st.form("f2",clear_on_submit=True):
        mc=st.text_input("Cust CID",key="u_m_c");mt=st.selectbox("Tier",list(MEMBERSHIP_DISCOUNTS.keys()),key="u_m_t")
        if st.form_submit_button("Add/Upd Mem",key="u_m_btn"): 
            if mc:add_mem(mc,mt);st.success("Mem updated")
    if st.button("Check Mem",key="u_chk"):
        mc=st.text_input("Check CID",key="u_chk_c")
        m=get_mem(mc)
        if m:
            d=datetime.strptime(m["dop"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            ex=d+timedelta(days=7);r=ex-datetime.now(IST)
            st.info(f"{mc}:{m['tier']} expires {r.days}d")
        else: st.info("No mem")

elif st.session_state.role=="admin":
    st.title("Admin")
    st.metric("Revenue",f"₹{total_billing():,.2f}")
    st.markdown("---")
    if st.checkbox("Confirm reset",key="a_rst_c") and st.button("Reset bills",key="a_rst"):
        db=sqlite3.connect("auto_exotic_billing.db");db.cursor().execute("DELETE FROM bills");db.commit();db.close();st.success("Reset")
    menu=st.sidebar.selectbox("Menu",["Sales","Manage Hoods","Manage Staff","Tracking"],key="a_mn")

    if menu=="Sales":
        st.header("Sales")
        tot=total_billing();cnt=bill_count();avg=tot/cnt if cnt else 0
        cm,tx=comm_tax();pf=tot-(cm+tx)
        st.metric("Total",f"₹{tot:,.2f}");st.metric("Avg",f"₹{avg:,.2f}")
        st.metric("Comm",f"₹{cm:,.2f}");st.metric("Tax",f"₹{tx:,.2f}");st.metric("Profit",f"₹{pf:,.2f}")

    elif menu=="Manage Hoods":
        st.header("Hoods")
        ht=st.tabs(["Add","Edit","Assign","View"])
        with ht[0]:
            with st.form("h_add",clear_on_submit=True):
                n=st.text_input("Name",key="h_add_n");l=st.text_input("Loc",key="h_add_l")
                if st.form_submit_button("Add",key="h_add_b") and n and l: add_hood(n,l);st.success("OK")
        with ht[1]:
            hs=get_hoods()
            if hs:
                names=[h[0] for h in hs]
                s=st.selectbox("Sel",names,key="h_ed_s");ol=dict(hs)[s]
                nn=st.text_input("New",s,key="h_ed_n");nl=st.text_input("Loc",ol,key="h_ed_l")
                if st.button("Upd",key="h_ed_u"):upd_hood(s,nn,nl);st.success("OK")
                if st.button("Del",key="h_ed_d"):del_hood(s);st.success("OK")
        with ht[2]:
            hs=get_hoods()
            if hs:
                s=st.selectbox("Sel", [h[0] for h in hs], key="h_as_s")
                es=all_cids();ch={f"{n}({c})":c for c,n in es}
                sl=st.multiselect("Emp",list(ch.keys()),key="h_as_m")
                if st.button("Assign",key="h_as_b"): 
                    for k in sl: update_employee(ch[k],hood=s)
                    st.success("OK")
        with ht[3]:
            for n,l in get_hoods():
                with st.expander(f"{n}-{l}"):
                    df=pd.DataFrame(emp_by_hood(n),columns=["CID","Name"])
                    if df.empty: st.write("None")
                    else: st.table(df)

    elif menu=="Manage Staff":
        st.header("Staff")
        st_tabs=st.tabs(["Add","Rem","Edit"])
        with st_tabs[0]:
            with st.form("s_add",clear_on_submit=True):
                nc=st.text_input("CID",key="s_add_c");nn=st.text_input("Name",key="s_add_n")
                nr=st.selectbox("Rank",list(COMMISSION_RATES.keys()),key="s_add_r")
                hs=[h[0] for h in get_hoods()] or []
                nh=st.selectbox("Hood",["No Hood"]+hs,key="s_add_h")
                if st.form_submit_button("Add",key="s_add_b") and nc and nn:
                    add_employee(nc,nn,nr)
                    if nh!="No Hood": update_employee(nc,hood=nh)
                    st.success("OK")
        with st_tabs[1]:
            es=all_cids();ch={f"{n}({c})":c for c,n in es}
            s=st.selectbox("Sel",list(ch.keys()),key="s_rem_s")
            if st.button("Del",key="s_rem_b"):delete_employee(ch[s]);st.success("OK")
        with st_tabs[2]:
            es=all_cids();ch={f"{n}({c})":c for c,n in es}
            s=st.selectbox("Sel",list(ch.keys()),key="s_ed_s");d=get_details(ch[s])
            if d:
                with st.form("s_ed",clear_on_submit=True):
                    nn=st.text_input("Name",d["name"],key="s_ed_n")
                    nr=st.selectbox("Rank",list(COMMISSION_RATES.keys()),index=list(COMMISSION_RATES.keys()).index(d["rank"]),key="s_ed_r")
                    hs=[h[0] for h in get_hoods()] or []
                    nh=st.selectbox("Hood",["No Hood"]+hs,index=(["No Hood"]+hs).index(d["hood"]) if d["hood"] in hs else 0,key="s_ed_h")
                    if st.form_submit_button("Upd",key="s_ed_b"):
                        update_employee(ch[s],name=nn,rank=nr,hood=nh);st.success("OK")

    else:
        st.header("Tracking")
        tk=st.tabs(["Emp","Cust","Hood","Mem","Rank","Filter"])
        with tk[0]:
            ranks=["All"]+list(COMMISSION_RATES.keys())
            sr=st.selectbox("Rank",ranks,key="t0_rank")
            ems=all_cids()
            if sr!="All": ems=[(c,n) for c,n in ems if get_rank(c)==sr]
            opts=[f"{n}({c})" for c,n in ems]
            if not opts: st.info("None")
            else:
                s=st.selectbox("Sel Emp",opts,key="t0_emp")
                v=st.radio("View",["Overall","Detailed"],key="t0_view")
                cid={lbl:c for (c,n),lbl in zip(ems,opts)}[s]
                if v=="Overall":
                    sm,tt=summary(cid)
                    for k,vv in sm.items(): st.metric(k,f"₹{vv:.2f}")
                    st.metric("Total",f"₹{tt:.2f}")
                else:
                    df=pd.DataFrame(emp_bills(cid),columns=["ID","Cust","Type","Det","Amt","Time","Comm","Tax"])
                    st.dataframe(df)
        with tk[1]:
            cust=st.selectbox("Cust",all_customers(),key="t1_cust")
            df=pd.DataFrame(cust_bills(cust),columns=["Emp","Type","Det","Amt","Time","Comm","Tax"])
            st.dataframe(df)
        with tk[2]:
            hs=[h[0] for h in get_hoods()]
            s=st.selectbox("Hood",hs,key="t2_hood")
            rows=[{"CID":cid,"Name":nm,"Total":summary(cid)[1]} for cid,nm in emp_by_hood(s)]
            st.table(pd.DataFrame(rows))
        with tk[3]:
            vm=st.radio("Show",["Active","Past"],key="t3_view")
            if vm=="Active":
                data=[{"CID":cid,"Tier":t,"Start":d,"Exp":(datetime.strptime(d,"%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)+timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")} for cid,t,d in all_mems()]
                st.table(pd.DataFrame(data))
            else:
                data=[{"CID":cid,"Tier":t,"Start":d,"ExpAt":ea} for cid,t,d,ea in past_mems()]
                st.table(pd.DataFrame(data))
        with tk[4]:
            met=st.selectbox("Metric",["Total Sales"]+list(ITEM_PRICES.keys()),key="t4_met")
            rank=[]
            conn=sqlite3.connect("auto_exotic_billing.db")
            for cid,nm in all_cids():
                if met=="Total Sales":
                    v=conn.cursor().execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid=?",(cid,)).fetchone()[0] or 0.0
                else:
                    v=conn.cursor().execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid=? AND billing_type=?",(cid,met)).fetchone()[0] or 0.0
                rank.append({"Emp":f"{nm}({cid})",met:v})
            conn.close()
            df=pd.DataFrame(rank).sort_values(met,ascending=False)
            st.table(df.head(10))
        with tk[5]:
            days=st.number_input("Days",1,30,7,key="t5_days")
            ms=st.number_input("Min₹",0.0,1000000.0,0.0,key="t5_min")
            if st.button("Apply",key="t5_btn"):
                cut=(datetime.now(IST)-timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                res=[]
                conn=sqlite3.connect("auto_exotic_billing.db")
                for cid,nm in all_cids():
                    v=conn.cursor().execute("SELECT SUM(total_amount) FROM bills WHERE employee_cid=? AND timestamp>=?",(cid,cut)).fetchone()[0] or 0.0
                    if v>=ms: res.append({"Emp":f"{nm}({cid})",f"Sales({days}d)":v})
                conn.close()
                if res: st.table(pd.DataFrame(res))
                else: st.info("No matches")

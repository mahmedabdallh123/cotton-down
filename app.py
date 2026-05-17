import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import requests
import shutil
import re
from datetime import datetime, timedelta
import io
import uuid
from PIL import Image
from github import Github, GithubException

# ------------------------------- الإعدادات الثابتة -------------------------------
APP_CONFIG = {
    "APP_TITLE": "HR System - متابعة الغيابات والبدلات",
    "APP_ICON": "👥",
    "REPO_NAME": "mahmedabdallh123/cotton-down",
    "BRANCH": "main",
    "FILE_PATH": "l9.xlsx",          # تم تغيير اسم الملف
    "LOCAL_FILE": "l9.xlsx",
    "MAX_ACTIVE_USERS": 5,
    "SESSION_DURATION_MINUTES": 60,
    "IMAGES_FOLDER": "hr_images",
    "ALLOWED_IMAGE_TYPES": ["jpg", "jpeg", "png", "gif", "bmp", "webp"],
    "MAX_IMAGE_SIZE_MB": 10,
    # أسماء الأوراق الجديدة
    "EMPLOYEES_SHEET": "الموظفين",
    "ABSENCES_SHEET": "الغيابات",
    "ALLOWANCES_SHEET": "البدلات",
    "ATTENDANCE_SHEET": "الحضور",
    # أعمدة كل ورقة
    "EMPLOYEES_COLUMNS": ["الموظف", "القسم", "الوظيفة", "تاريخ التوظيف", "رقم الهاتف", "ملاحظات", "رابط الصورة"],
    "ABSENCES_COLUMNS": ["الموظف", "القسم", "التاريخ", "نوع الغياب", "عدد الأيام", "سبب الغياب", "موثق", "ملاحظات", "رابط الصورة"],
    "ALLOWANCES_COLUMNS": ["الموظف", "القسم", "التاريخ", "نوع البدل", "المبلغ", "ملاحظات", "رابط الصورة"],
    "ATTENDANCE_COLUMNS": ["الموظف", "القسم", "التاريخ", "وقت الحضور", "وقت الانصراف", "عدد ساعات العمل", "ملاحظات", "رابط الصورة"],
}

# ------------------------------- إعداد الصفحة -------------------------------
st.set_page_config(page_title=APP_CONFIG["APP_TITLE"], layout="wide")

# ------------------------------- استيرادات إضافية مع معالجة الأخطاء -------------------------------
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        plt.rcParams['font.family'] = 'Arial'
        MATPLOTLIB_AVAILABLE = True
    except ImportError:
        MATPLOTLIB_AVAILABLE = False

# ------------------------------- ثوابت إضافية -------------------------------
USERS_FILE = "users.json"
STATE_FILE = "state.json"
SESSION_DURATION = timedelta(minutes=APP_CONFIG["SESSION_DURATION_MINUTES"])
MAX_ACTIVE_USERS = APP_CONFIG["MAX_ACTIVE_USERS"]
IMAGES_FOLDER = APP_CONFIG["IMAGES_FOLDER"]
EQUIPMENT_CONFIG_FILE = "hr_config.json"      # يستخدم الآن لتخزين إعدادات HR بسيطة إن لزم
SUPPORT_CONFIG_FILE = "support_config.json"

GITHUB_EXCEL_URL = f"https://github.com/{APP_CONFIG['REPO_NAME'].split('/')[0]}/{APP_CONFIG['REPO_NAME'].split('/')[1]}/raw/{APP_CONFIG['BRANCH']}/{APP_CONFIG['FILE_PATH']}"
GITHUB_USERS_URL = "https://raw.githubusercontent.com/mahmedabdallh123/cotton-down/refs/heads/main/users.json"
GITHUB_REPO_USERS = "mahmedabdallh123/cotton-down"
GITHUB_TOKEN = st.secrets.get("github", {}).get("token", None)
GITHUB_AVAILABLE = GITHUB_TOKEN is not None
ACTIVITY_LOG_FILE = "activity_log.json"

# ------------------------------- دوال رفع الصور -------------------------------
def upload_image_to_github(image_file, entity_type, entity_id, custom_filename=None):
    if not GITHUB_AVAILABLE:
        st.error("❌ GitHub token غير متوفر، لا يمكن رفع الصور")
        return None
    try:
        img = Image.open(image_file)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85, optimize=True)
        buffer.seek(0)
        if custom_filename:
            filename = custom_filename
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{entity_type}_{entity_id}_{timestamp}.jpg"
        repo_path = f"{IMAGES_FOLDER}/{entity_type}/{filename}"
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(APP_CONFIG["REPO_NAME"])
        try:
            repo.get_contents(f"{IMAGES_FOLDER}/{entity_type}/", ref=APP_CONFIG["BRANCH"])
        except GithubException:
            repo.create_file(f"{IMAGES_FOLDER}/{entity_type}/.gitkeep", f"Create folder for {entity_type} images", "", branch=APP_CONFIG["BRANCH"])
        content = buffer.getvalue()
        result = repo.create_file(path=repo_path, message=f"Add image for {entity_type} {entity_id}", content=content, branch=APP_CONFIG["BRANCH"])
        return f"https://raw.githubusercontent.com/{APP_CONFIG['REPO_NAME']}/{APP_CONFIG['BRANCH']}/{repo_path}"
    except Exception as e:
        st.error(f"❌ خطأ في معالجة الصورة: {e}")
        return None

def get_image_component(image_url, caption=""):
    if not image_url or not isinstance(image_url, str):
        return None
    try:
        return st.image(image_url, caption=caption, use_container_width=True)
    except:
        st.warning(f"⚠️ تعذر عرض الصورة: {image_url}")
        return None

# ------------------------------- دوال إعدادات الدعم الفني -------------------------------
def load_support_config():
    default_config = {"image_url": "", "youtube_link": ""}
    if GITHUB_AVAILABLE:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(APP_CONFIG["REPO_NAME"])
            contents = repo.get_contents(SUPPORT_CONFIG_FILE, ref=APP_CONFIG["BRANCH"])
            import base64
            content = base64.b64decode(contents.content).decode('utf-8')
            config = json.loads(content)
            return config
        except:
            pass
    if os.path.exists(SUPPORT_CONFIG_FILE):
        try:
            with open(SUPPORT_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default_config
    return default_config

def save_support_config(config):
    config_str = json.dumps(config, indent=2, ensure_ascii=False)
    if GITHUB_AVAILABLE:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(APP_CONFIG["REPO_NAME"])
            try:
                contents = repo.get_contents(SUPPORT_CONFIG_FILE, ref=APP_CONFIG["BRANCH"])
                repo.update_file(SUPPORT_CONFIG_FILE, "تحديث إعدادات الدعم الفني", config_str, contents.sha, branch=APP_CONFIG["BRANCH"])
            except:
                repo.create_file(SUPPORT_CONFIG_FILE, "إنشاء إعدادات الدعم الفني", config_str, branch=APP_CONFIG["BRANCH"])
        except:
            pass
    with open(SUPPORT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# ------------------------------- دوال سجل النشاطات -------------------------------
def log_activity(action_type, details, username=None):
    if username is None:
        username = st.session_state.get("username", "غير معروف")
    log_entry = {"timestamp": datetime.now().isoformat(), "username": username, "action_type": action_type, "details": details}
    log = []
    if os.path.exists(ACTIVITY_LOG_FILE):
        try:
            with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except:
            log = []
    log.append(log_entry)
    if len(log) > 100:
        log = log[-100:]
    with open(ACTIVITY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    if GITHUB_AVAILABLE:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(APP_CONFIG["REPO_NAME"])
            content = json.dumps(log, indent=2, ensure_ascii=False)
            try:
                contents = repo.get_contents(ACTIVITY_LOG_FILE, ref=APP_CONFIG["BRANCH"])
                repo.update_file(ACTIVITY_LOG_FILE, "تحديث سجل النشاطات", content, contents.sha, branch=APP_CONFIG["BRANCH"])
            except:
                repo.create_file(ACTIVITY_LOG_FILE, "إنشاء سجل النشاطات", content, branch=APP_CONFIG["BRANCH"])
        except:
            pass

def load_activity_log():
    if GITHUB_AVAILABLE:
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(APP_CONFIG["REPO_NAME"])
            contents = repo.get_contents(ACTIVITY_LOG_FILE, ref=APP_CONFIG["BRANCH"])
            import base64
            content = base64.b64decode(contents.content).decode('utf-8')
            return json.loads(content)
        except:
            pass
    if os.path.exists(ACTIVITY_LOG_FILE):
        with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# ------------------------------- دوال تحميل وحفظ البيانات الرئيسية -------------------------------
def create_empty_hr_sheets():
    """إنشاء أوراق فارغة لنظام HR"""
    sheets = {}
    sheets[APP_CONFIG["EMPLOYEES_SHEET"]] = pd.DataFrame(columns=APP_CONFIG["EMPLOYEES_COLUMNS"])
    sheets[APP_CONFIG["ABSENCES_SHEET"]] = pd.DataFrame(columns=APP_CONFIG["ABSENCES_COLUMNS"])
    sheets[APP_CONFIG["ALLOWANCES_SHEET"]] = pd.DataFrame(columns=APP_CONFIG["ALLOWANCES_COLUMNS"])
    sheets[APP_CONFIG["ATTENDANCE_SHEET"]] = pd.DataFrame(columns=APP_CONFIG["ATTENDANCE_COLUMNS"])
    return sheets

@st.cache_data(show_spinner=False)
def load_all_sheets():
    """تحميل جميع الأوراق من ملف Excel"""
    if not os.path.exists(APP_CONFIG["LOCAL_FILE"]):
        # إنشاء ملف جديد بالأوراق الافتراضية
        empty_sheets = create_empty_hr_sheets()
        with pd.ExcelWriter(APP_CONFIG["LOCAL_FILE"], engine="openpyxl") as writer:
            for name, df in empty_sheets.items():
                df.to_excel(writer, sheet_name=name, index=False)
        return empty_sheets
    try:
        sheets = pd.read_excel(APP_CONFIG["LOCAL_FILE"], sheet_name=None)
        # التأكد من وجود الأوراق المطلوبة، وإنشاء ما ينقص
        required = [APP_CONFIG["EMPLOYEES_SHEET"], APP_CONFIG["ABSENCES_SHEET"],
                    APP_CONFIG["ALLOWANCES_SHEET"], APP_CONFIG["ATTENDANCE_SHEET"]]
        for sheet in required:
            if sheet not in sheets:
                sheets[sheet] = pd.DataFrame(columns=APP_CONFIG[f"{sheet.split('_')[0].upper()}_COLUMNS"] if False else [])
                # إصلاح سريع: استخدام القاموس
                columns_dict = {
                    APP_CONFIG["EMPLOYEES_SHEET"]: APP_CONFIG["EMPLOYEES_COLUMNS"],
                    APP_CONFIG["ABSENCES_SHEET"]: APP_CONFIG["ABSENCES_COLUMNS"],
                    APP_CONFIG["ALLOWANCES_SHEET"]: APP_CONFIG["ALLOWANCES_COLUMNS"],
                    APP_CONFIG["ATTENDANCE_SHEET"]: APP_CONFIG["ATTENDANCE_COLUMNS"]
                }
                sheets[sheet] = pd.DataFrame(columns=columns_dict[sheet])
        # تنظيف الأعمدة
        for name, df in sheets.items():
            df.columns = df.columns.astype(str).str.strip()
            df = df.fillna('')
            sheets[name] = df
        return sheets
    except Exception as e:
        st.error(f"خطأ في تحميل ملف البيانات: {e}")
        return create_empty_hr_sheets()

@st.cache_data(show_spinner=False)
def load_sheets_for_edit():
    """نفس التحميل ولكن بدون معالجة إضافية للتعديل"""
    if not os.path.exists(APP_CONFIG["LOCAL_FILE"]):
        return create_empty_hr_sheets()
    try:
        sheets = pd.read_excel(APP_CONFIG["LOCAL_FILE"], sheet_name=None, dtype=object)
        required = [APP_CONFIG["EMPLOYEES_SHEET"], APP_CONFIG["ABSENCES_SHEET"],
                    APP_CONFIG["ALLOWANCES_SHEET"], APP_CONFIG["ATTENDANCE_SHEET"]]
        for sheet in required:
            if sheet not in sheets:
                sheets[sheet] = pd.DataFrame(columns=APP_CONFIG[f"{sheet.split('_')[0].upper()}_COLUMNS"] if False else [])
        for name, df in sheets.items():
            df.columns = df.columns.astype(str).str.strip()
            df = df.fillna('')
            sheets[name] = df
        return sheets
    except Exception as e:
        st.error(f"خطأ في تحميل ملف البيانات للتعديل: {e}")
        return create_empty_hr_sheets()

def save_excel_locally(sheets_dict):
    try:
        with pd.ExcelWriter(APP_CONFIG["LOCAL_FILE"], engine="openpyxl") as writer:
            for name, sh in sheets_dict.items():
                sh.to_excel(writer, sheet_name=name, index=False)
        return True
    except Exception as e:
        st.error(f"❌ خطأ في الحفظ المحلي: {e}")
        return False

def push_to_github():
    try:
        token = st.secrets.get("github", {}).get("token", None)
        if not token:
            st.error("❌ لم يتم العثور على GitHub token في secrets")
            return False
        g = Github(token)
        repo = g.get_repo(APP_CONFIG["REPO_NAME"])
        with open(APP_CONFIG["LOCAL_FILE"], "rb") as f:
            content = f.read()
        try:
            contents = repo.get_contents(APP_CONFIG["FILE_PATH"], ref=APP_CONFIG["BRANCH"])
            repo.update_file(path=APP_CONFIG["FILE_PATH"], message=f"تحديث بيانات HR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", content=content, sha=contents.sha, branch=APP_CONFIG["BRANCH"])
            st.success("✅ تم رفع التغييرات إلى GitHub")
            return True
        except GithubException as e:
            if e.status == 404:
                repo.create_file(path=APP_CONFIG["FILE_PATH"], message=f"إنشاء ملف HR جديد - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", content=content, branch=APP_CONFIG["BRANCH"])
                st.success("✅ تم إنشاء الملف على GitHub")
                return True
            else:
                st.error(f"❌ خطأ GitHub: {e}")
                return False
    except Exception as e:
        st.error(f"❌ فشل الرفع: {e}")
        return False

def save_and_push_to_github(sheets_dict, operation_name):
    st.info(f"💾 جاري حفظ {operation_name}...")
    if save_excel_locally(sheets_dict):
        st.success("✅ تم الحفظ محلياً")
        if push_to_github():
            st.success("✅ تم الرفع إلى GitHub")
            st.cache_data.clear()
            return True
        else:
            st.warning("⚠️ تم الحفظ محلياً فقط")
            return True
    else:
        st.error("❌ فشل الحفظ المحلي")
        return False

# ------------------------------- دوال الصلاحيات والمستخدمين (بدون تغيير كبير) -------------------------------
def download_users_from_github():
    try:
        response = requests.get(GITHUB_USERS_URL, timeout=10)
        response.raise_for_status()
        users_data = response.json()
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_data, f, indent=4, ensure_ascii=False)
        return users_data
    except:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

def load_users():
    try:
        users_data = download_users_from_github()
        if not users_data or "admin" not in users_data:
            default_users = {
                "admin": {"password": "1234", "role": "admin", "permissions": {"all_sections": True}, "sections_permissions": {}},
                "مدير_موارد_بشرية": {"password": "12345", "role": "admin", "permissions": {"all_sections": True}, "sections_permissions": {}}
            }
            return default_users
        return users_data
    except:
        return {"admin": {"password": "1234", "role": "admin", "permissions": {"all_sections": True}, "sections_permissions": {}}}

def load_state():
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

def cleanup_sessions(state):
    now = datetime.now()
    changed = False
    for user, info in list(state.items()):
        if info.get("active") and "login_time" in info:
            try:
                login_time = datetime.fromisoformat(info["login_time"])
                if now - login_time > SESSION_DURATION:
                    info["active"] = False
                    info.pop("login_time", None)
                    changed = True
            except:
                info["active"] = False
                changed = True
    if changed:
        save_state(state)
    return state

def remaining_time(state, username):
    if not username or username not in state:
        return None
    info = state.get(username)
    if not info or not info.get("active"):
        return None
    try:
        lt = datetime.fromisoformat(info["login_time"])
        remaining = SESSION_DURATION - (datetime.now() - lt)
        if remaining.total_seconds() <= 0:
            return None
        return remaining
    except:
        return None

def logout_action():
    state = load_state()
    username = st.session_state.get("username")
    if username and username in state:
        state[username]["active"] = False
        state[username].pop("login_time", None)
        save_state(state)
    for k in list(st.session_state.keys()):
        st.session_state.pop(k, None)
    st.rerun()

def login_ui():
    users = load_users()
    state = cleanup_sessions(load_state())
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.user_role = None
        st.session_state.user_permissions = []
    st.title(f"{APP_CONFIG['APP_ICON']} تسجيل الدخول - {APP_CONFIG['APP_TITLE']}")
    username_input = st.selectbox("اختر المستخدم", list(users.keys()))
    password = st.text_input("كلمة المرور", type="password")
    active_users = [u for u, v in state.items() if v.get("active")]
    active_count = len(active_users)
    st.caption(f"المستخدمون النشطون: {active_count} / {MAX_ACTIVE_USERS}")
    if not st.session_state.logged_in:
        if st.button("تسجيل الدخول"):
            current_users = load_users()
            if username_input in current_users and current_users[username_input]["password"] == password:
                if username_input != "admin" and username_input in active_users:
                    st.warning("هذا المستخدم مسجل دخول بالفعل.")
                    return False
                elif active_count >= MAX_ACTIVE_USERS and username_input != "admin":
                    st.error("الحد الأقصى للمستخدمين المتصلين.")
                    return False
                state[username_input] = {"active": True, "login_time": datetime.now().isoformat()}
                save_state(state)
                st.session_state.logged_in = True
                st.session_state.username = username_input
                st.session_state.user_role = current_users[username_input].get("role", "viewer")
                st.session_state.user_permissions = current_users[username_input].get("permissions", ["view"])
                st.success(f"تم تسجيل الدخول: {username_input}")
                st.rerun()
            else:
                st.error("كلمة المرور غير صحيحة.")
        return False
    else:
        st.success(f"مسجل الدخول كـ: {st.session_state.username}")
        rem = remaining_time(state, st.session_state.username)
        if rem:
            mins, secs = divmod(int(rem.total_seconds()), 60)
            st.info(f"الوقت المتبقي: {mins:02d}:{secs:02d}")
        if st.button("تسجيل الخروج"):
            logout_action()
        return True

# ------------------------------- دوال HR الأساسية -------------------------------
def get_employees_list(sheets_edit):
    emp_df = sheets_edit[APP_CONFIG["EMPLOYEES_SHEET"]]
    if emp_df.empty:
        return []
    return emp_df["الموظف"].dropna().unique().tolist()

def get_departments(sheets_edit):
    emp_df = sheets_edit[APP_CONFIG["EMPLOYEES_SHEET"]]
    if emp_df.empty:
        return []
    return emp_df["القسم"].dropna().unique().tolist()

def add_employee(sheets_edit, name, department, job_title, hire_date, phone, notes, image_url):
    df = sheets_edit[APP_CONFIG["EMPLOYEES_SHEET"]]
    new_row = pd.DataFrame([{
        "الموظف": name, "القسم": department, "الوظيفة": job_title,
        "تاريخ التوظيف": hire_date.strftime("%Y-%m-%d") if isinstance(hire_date, datetime) else str(hire_date),
        "رقم الهاتف": phone, "ملاحظات": notes, "رابط الصورة": image_url or ""
    }])
    sheets_edit[APP_CONFIG["EMPLOYEES_SHEET"]] = pd.concat([df, new_row], ignore_index=True)
    return sheets_edit

def add_absence_record(sheets_edit, employee, department, date, absence_type, days, reason, documented, notes, image_url):
    df = sheets_edit[APP_CONFIG["ABSENCES_SHEET"]]
    new_row = pd.DataFrame([{
        "الموظف": employee, "القسم": department, "التاريخ": date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date),
        "نوع الغياب": absence_type, "عدد الأيام": days, "سبب الغياب": reason,
        "موثق": "نعم" if documented else "لا", "ملاحظات": notes, "رابط الصورة": image_url or ""
    }])
    sheets_edit[APP_CONFIG["ABSENCES_SHEET"]] = pd.concat([df, new_row], ignore_index=True)
    return sheets_edit

def add_allowance_record(sheets_edit, employee, department, date, allowance_type, amount, notes, image_url):
    df = sheets_edit[APP_CONFIG["ALLOWANCES_SHEET"]]
    new_row = pd.DataFrame([{
        "الموظف": employee, "القسم": department, "التاريخ": date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date),
        "نوع البدل": allowance_type, "المبلغ": amount, "ملاحظات": notes, "رابط الصورة": image_url or ""
    }])
    sheets_edit[APP_CONFIG["ALLOWANCES_SHEET"]] = pd.concat([df, new_row], ignore_index=True)
    return sheets_edit

def add_attendance_record(sheets_edit, employee, department, date, time_in, time_out, hours_worked, notes, image_url):
    df = sheets_edit[APP_CONFIG["ATTENDANCE_SHEET"]]
    new_row = pd.DataFrame([{
        "الموظف": employee, "القسم": department, "التاريخ": date.strftime("%Y-%m-%d") if isinstance(date, datetime) else str(date),
        "وقت الحضور": time_in, "وقت الانصراف": time_out, "عدد ساعات العمل": hours_worked,
        "ملاحظات": notes, "رابط الصورة": image_url or ""
    }])
    sheets_edit[APP_CONFIG["ATTENDANCE_SHEET"]] = pd.concat([df, new_row], ignore_index=True)
    return sheets_edit

# ------------------------------- تحليل HR -------------------------------
def analyze_hr_data(all_sheets):
    st.header("📊 تحليل الموارد البشرية")
    if not all_sheets:
        st.warning("لا توجد بيانات للتحليل")
        return

    # اختيار نوع التحليل
    analysis_type = st.selectbox("نوع التحليل", ["الغيابات", "البدلات", "الحضور والانصراف"])

    if analysis_type == "الغيابات":
        df = all_sheets[APP_CONFIG["ABSENCES_SHEET"]]
        if df.empty:
            st.info("لا توجد سجلات غياب")
            return
        df["عدد الأيام"] = pd.to_numeric(df["عدد الأيام"], errors='coerce').fillna(1)
        # أكثر الموظفين غياباً
        st.subheader("🔝 أكثر الموظفين غياباً (إجمالي الأيام)")
        top_absence = df.groupby("الموظف")["عدد الأيام"].sum().sort_values(ascending=False).head(10)
        st.bar_chart(top_absence)
        # توزيع أنواع الغياب
        st.subheader("📊 توزيع أنواع الغياب")
        type_counts = df["نوع الغياب"].value_counts()
        st.bar_chart(type_counts)
        # تفاصيل الغيابات حسب الشهر
        st.subheader("📅 الغيابات الشهرية")
        df["التاريخ"] = pd.to_datetime(df["التاريخ"], errors='coerce')
        df["الشهر"] = df["التاريخ"].dt.to_period("M")
        monthly = df.groupby("الشهر")["عدد الأيام"].sum()
        st.line_chart(monthly.astype(float))
    elif analysis_type == "البدلات":
        df = all_sheets[APP_CONFIG["ALLOWANCES_SHEET"]]
        if df.empty:
            st.info("لا توجد سجلات بدلات")
            return
        df["المبلغ"] = pd.to_numeric(df["المبلغ"], errors='coerce').fillna(0)
        st.subheader("💰 إجمالي البدلات لكل موظف")
        total_emp = df.groupby("الموظف")["المبلغ"].sum().sort_values(ascending=False)
        st.bar_chart(total_emp)
        st.subheader("📌 أكثر أنواع البدلات صرفاً")
        type_total = df.groupby("نوع البدل")["المبلغ"].sum()
        st.bar_chart(type_total)
        st.subheader("📅 البدلات الشهرية")
        df["التاريخ"] = pd.to_datetime(df["التاريخ"], errors='coerce')
        df["الشهر"] = df["التاريخ"].dt.to_period("M")
        monthly_allow = df.groupby("الشهر")["المبلغ"].sum()
        st.line_chart(monthly_allow.astype(float))
    else:  # الحضور
        df = all_sheets[APP_CONFIG["ATTENDANCE_SHEET"]]
        if df.empty:
            st.info("لا توجد سجلات حضور")
            return
        # تحليل متوسط ساعات العمل
        df["عدد ساعات العمل"] = pd.to_numeric(df["عدد ساعات العمل"], errors='coerce').fillna(0)
        st.subheader("⏱️ متوسط ساعات العمل اليومية لكل موظف")
        avg_hours = df.groupby("الموظف")["عدد ساعات العمل"].mean()
        st.bar_chart(avg_hours)
        st.subheader("📊 توزيع ساعات العمل")
        st.hist(df["عدد ساعات العمل"], bins=20)
        st.subheader("📅 ساعات العمل الشهرية")
        df["التاريخ"] = pd.to_datetime(df["التاريخ"], errors='coerce')
        df["الشهر"] = df["التاريخ"].dt.to_period("M")
        monthly_hours = df.groupby("الشهر")["عدد ساعات العمل"].sum()
        st.line_chart(monthly_hours.astype(float))

# ------------------------------- البحث المتقدم HR -------------------------------
def search_across_sheets_hr(all_sheets):
    st.subheader("🔍 بحث متقدم في السجلات")
    if not all_sheets:
        st.warning("لا توجد بيانات")
        return

    search_type = st.selectbox("نوع السجل المراد البحث فيه:", ["الغيابات", "البدلات", "الحضور", "الموظفين"])

    # إذا كان النوع موظفين، بحث بسيط
    if search_type == "الموظفين":
        df = all_sheets[APP_CONFIG["EMPLOYEES_SHEET"]]
        if df.empty:
            st.info("لا يوجد موظفون مسجلون")
            return
        search_term = st.text_input("ابحث باسم الموظف أو القسم:")
        if search_term:
            mask = df["الموظف"].str.contains(search_term, case=False, na=False) | df["القسم"].str.contains(search_term, case=False, na=False)
            df = df[mask]
        st.dataframe(df, use_container_width=True)
        return

    # اختيار الورقة المناسبة
    sheet_map = {
        "الغيابات": APP_CONFIG["ABSENCES_SHEET"],
        "البدلات": APP_CONFIG["ALLOWANCES_SHEET"],
        "الحضور": APP_CONFIG["ATTENDANCE_SHEET"]
    }
    sheet_name = sheet_map[search_type]
    df = all_sheets[sheet_name].copy()
    if df.empty:
        st.info(f"لا توجد سجلات {search_type}")
        return

    # فلاتر
    col1, col2 = st.columns(2)
    with col1:
        employee_filter = st.selectbox("الموظف", ["الكل"] + get_employees_list(all_sheets))
    with col2:
        departments = get_departments(all_sheets)
        dept_filter = st.selectbox("القسم", ["الكل"] + departments)

    start_date, end_date = None, None
    if st.checkbox("تفعيل بحث بالتاريخ"):
        c1, c2 = st.columns(2)
        with c1:
            start_date = st.date_input("من تاريخ")
        with c2:
            end_date = st.date_input("إلى تاريخ")

    search_text = st.text_input("كلمة بحث عامة (في جميع الأعمدة)")

    if st.button("بحث", type="primary"):
        if employee_filter != "الكل":
            df = df[df["الموظف"] == employee_filter]
        if dept_filter != "الكل":
            df = df[df["القسم"] == dept_filter]
        if start_date and end_date:
            df["التاريخ"] = pd.to_datetime(df["التاريخ"], errors='coerce')
            mask = (df["التاريخ"] >= pd.to_datetime(start_date)) & (df["التاريخ"] <= pd.to_datetime(end_date) + timedelta(days=1))
            df = df[mask]
        if search_text:
            mask = pd.Series(False, index=df.index)
            for col in df.columns:
                if df[col].dtype == object:
                    mask |= df[col].astype(str).str.contains(search_text, case=False, na=False)
            df = df[mask]

        st.success(f"تم العثور على {len(df)} سجل")
        st.dataframe(df, use_container_width=True)
        # زر تحميل
        excel_buffer = export_filtered_results_to_excel(df, search_type)
        st.download_button("📥 تحميل النتائج", excel_buffer, file_name=f"{search_type}_search.xlsx")

# ------------------------------- دوال التصدير (تستخدم في عدة أماكن) -------------------------------
def export_sheet_to_excel(sheets_dict, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = sheets_dict[sheet_name]
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output

def export_all_sheets_to_excel(sheets_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output

def export_filtered_results_to_excel(results_df, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        results_df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output

# ------------------------------- تبويب إدارة البيانات الرئيسي (HR) -------------------------------
def manage_hr_data(sheets_edit):
    st.header("🛠 إدارة بيانات الموارد البشرية")
    if sheets_edit is None:
        st.warning("الملف غير موجود. استخدم زر 'تحديث من GitHub' في الشريط الجانبي أولاً")
        return sheets_edit

    tab_names = ["👥 الموظفين", "📅 إضافة غياب", "💰 إضافة بدل", "⏰ إضافة حضور", "📋 عرض/تحرير السجلات"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        st.subheader("قائمة الموظفين")
        emp_df = sheets_edit[APP_CONFIG["EMPLOYEES_SHEET"]]
        # إضافة موظف جديد
        with st.expander("➕ إضافة موظف جديد"):
            with st.form("add_employee_form"):
                c1, c2 = st.columns(2)
                with c1:
                    name = st.text_input("اسم الموظف")
                    department = st.selectbox("القسم", get_departments(sheets_edit) + ["قسم جديد..."])
                    if department == "قسم جديد...":
                        new_dept = st.text_input("اسم القسم الجديد")
                        department = new_dept
                    job = st.text_input("الوظيفة")
                    hire_date = st.date_input("تاريخ التوظيف", value=datetime.now())
                with c2:
                    phone = st.text_input("رقم الهاتف")
                    notes = st.text_area("ملاحظات")
                    emp_image = st.file_uploader("صورة الموظف", type=APP_CONFIG["ALLOWED_IMAGE_TYPES"])
                if st.form_submit_button("إضافة"):
                    img_url = None
                    if emp_image:
                        img_url = upload_image_to_github(emp_image, "employee", str(uuid.uuid4())[:8])
                    sheets_edit = add_employee(sheets_edit, name, department, job, hire_date, phone, notes, img_url)
                    if save_and_push_to_github(sheets_edit, f"إضافة موظف {name}"):
                        st.success("تمت الإضافة")
                        st.rerun()
        # عرض الموظفين
        if not emp_df.empty:
            st.dataframe(emp_df, use_container_width=True)
            if st.button("🗑️ حذف موظف محدد"):
                st.session_state["delete_emp"] = True
            if st.session_state.get("delete_emp"):
                emp_to_delete = st.selectbox("اختر الموظف للحذف", emp_df["الموظف"].tolist())
                if st.button("تأكيد الحذف"):
                    sheets_edit[APP_CONFIG["EMPLOYEES_SHEET"]] = emp_df[emp_df["الموظف"] != emp_to_delete]
                    if save_and_push_to_github(sheets_edit, f"حذف موظف {emp_to_delete}"):
                        st.success("تم الحذف")
                        st.session_state["delete_emp"] = False
                        st.rerun()
        else:
            st.info("لا يوجد موظفون بعد")

    with tabs[1]:
        st.subheader("تسجيل غياب")
        employees = get_employees_list(sheets_edit)
        if not employees:
            st.warning("يجب إضافة موظفين أولاً")
        else:
            with st.form("add_absence"):
                emp = st.selectbox("الموظف", employees)
                dept = st.selectbox("القسم", get_departments(sheets_edit))
                date = st.date_input("التاريخ", value=datetime.now())
                absence_type = st.selectbox("نوع الغياب", ["مرضي", "عرضي", "بدون إذن", "سنوي", "أمومة", "آخر"])
                days = st.number_input("عدد الأيام", min_value=0.5, step=0.5)
                reason = st.text_area("سبب الغياب")
                documented = st.checkbox("موثق؟")
                notes = st.text_input("ملاحظات إضافية")
                img = st.file_uploader("صورة (إجازة مرضية مثلاً)", type=APP_CONFIG["ALLOWED_IMAGE_TYPES"])
                if st.form_submit_button("تسجيل"):
                    img_url = None
                    if img:
                        img_url = upload_image_to_github(img, "absence", str(uuid.uuid4())[:8])
                    sheets_edit = add_absence_record(sheets_edit, emp, dept, date, absence_type, days, reason, documented, notes, img_url)
                    if save_and_push_to_github(sheets_edit, f"تسجيل غياب {emp}"):
                        st.success("تم تسجيل الغياب")
                        st.rerun()

    with tabs[2]:
        st.subheader("تسجيل بدل")
        employees = get_employees_list(sheets_edit)
        if not employees:
            st.warning("يجب إضافة موظفين أولاً")
        else:
            with st.form("add_allowance"):
                emp = st.selectbox("الموظف", employees)
                dept = st.selectbox("القسم", get_departments(sheets_edit))
                date = st.date_input("التاريخ", value=datetime.now())
                allow_type = st.selectbox("نوع البدل", ["نقل", "سكن", "إضافي", "بدل طبيعة عمل", "آخر"])
                amount = st.number_input("المبلغ", min_value=0.0, step=100.0)
                notes = st.text_input("ملاحظات")
                img = st.file_uploader("صورة", type=APP_CONFIG["ALLOWED_IMAGE_TYPES"])
                if st.form_submit_button("تسجيل"):
                    img_url = None
                    if img:
                        img_url = upload_image_to_github(img, "allowance", str(uuid.uuid4())[:8])
                    sheets_edit = add_allowance_record(sheets_edit, emp, dept, date, allow_type, amount, notes, img_url)
                    if save_and_push_to_github(sheets_edit, f"تسجيل بدل {emp}"):
                        st.success("تم تسجيل البدل")
                        st.rerun()

    with tabs[3]:
        st.subheader("تسجيل حضور وانصراف")
        employees = get_employees_list(sheets_edit)
        if not employees:
            st.warning("يجب إضافة موظفين أولاً")
        else:
            with st.form("add_attendance"):
                emp = st.selectbox("الموظف", employees)
                dept = st.selectbox("القسم", get_departments(sheets_edit))
                date = st.date_input("التاريخ", value=datetime.now())
                time_in = st.time_input("وقت الحضور", value=datetime.strptime("08:00", "%H:%M").time())
                time_out = st.time_input("وقت الانصراف", value=datetime.strptime("16:00", "%H:%M").time())
                # حساب عدد الساعات
                if time_in and time_out:
                    delta = datetime.combine(date, time_out) - datetime.combine(date, time_in)
                    hours = round(delta.total_seconds() / 3600, 2)
                else:
                    hours = 0
                st.write(f"عدد الساعات: {hours}")
                notes = st.text_input("ملاحظات")
                img = st.file_uploader("صورة (مثلاً بصمة)", type=APP_CONFIG["ALLOWED_IMAGE_TYPES"])
                if st.form_submit_button("تسجيل"):
                    img_url = None
                    if img:
                        img_url = upload_image_to_github(img, "attendance", str(uuid.uuid4())[:8])
                    sheets_edit = add_attendance_record(sheets_edit, emp, dept, date, str(time_in), str(time_out), hours, notes, img_url)
                    if save_and_push_to_github(sheets_edit, f"تسجيل حضور {emp}"):
                        st.success("تم تسجيل الحضور")
                        st.rerun()

    with tabs[4]:
        st.subheader("عرض وتحرير السجلات")
        sheet_choice = st.selectbox("اختر نوع السجلات", [APP_CONFIG["EMPLOYEES_SHEET"], APP_CONFIG["ABSENCES_SHEET"], APP_CONFIG["ALLOWANCES_SHEET"], APP_CONFIG["ATTENDANCE_SHEET"]])
        df = sheets_edit[sheet_choice]
        st.dataframe(df, use_container_width=True)
        # تحرير مباشر
        with st.expander("✏️ تعديل مباشر"):
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key=f"editor_{sheet_choice}")
            if st.button("💾 حفظ التعديلات", key=f"save_{sheet_choice}"):
                sheets_edit[sheet_choice] = edited_df
                if save_and_push_to_github(sheets_edit, f"تعديل في {sheet_choice}"):
                    st.success("تم الحفظ")
                    st.rerun()
        # تصدير
        st.download_button("📥 تحميل هذه البيانات", export_sheet_to_excel({sheet_choice: df}, sheet_choice), file_name=f"{sheet_choice}.xlsx")

    return sheets_edit

# ------------------------------- الإشعارات HR -------------------------------
def show_hr_notifications(all_sheets):
    st.header("🔔 الإشعارات")
    # عرض آخر النشاطات للمدير
    if st.session_state.get("username") == "admin":
        st.subheader("📋 آخر النشاطات")
        activity_log = load_activity_log()
        if activity_log:
            for entry in reversed(activity_log[-20:]):
                timestamp = datetime.fromisoformat(entry["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                st.info(f"🕒 {timestamp} - **{entry['username']}**: {entry['details']}")
        else:
            st.info("لا توجد نشاطات")
        st.markdown("---")

    # تنبيهات غياب مفرط
    st.subheader("⚠️ تنبيهات الغياب")
    absences_df = all_sheets[APP_CONFIG["ABSENCES_SHEET"]]
    if not absences_df.empty:
        absences_df["عدد الأيام"] = pd.to_numeric(absences_df["عدد الأيام"], errors='coerce').fillna(0)
        # احتساب مجموع الغياب لكل موظف
        total_abs = absences_df.groupby("الموظف")["عدد الأيام"].sum()
        excessive = total_abs[total_abs > 10]  # حد مثلاً 10 أيام
        if not excessive.empty:
            for emp, days in excessive.items():
                st.warning(f"⚠️ **{emp}** تجاوز عدد أيام الغياب ({days} يوم)")
        else:
            st.success("✅ لا يوجد موظفون تجاوزوا الحد المسموح للغياب")
    else:
        st.info("لا توجد بيانات غياب")

    # ملخص سريع للبدلات هذا الشهر
    st.subheader("💰 إجمالي البدلات هذا الشهر")
    allow_df = all_sheets[APP_CONFIG["ALLOWANCES_SHEET"]]
    if not allow_df.empty:
        allow_df["التاريخ"] = pd.to_datetime(allow_df["التاريخ"], errors='coerce')
        this_month = allow_df[allow_df["التاريخ"].dt.month == datetime.now().month]
        total_allow = pd.to_numeric(this_month["المبلغ"], errors='coerce').sum()
        st.metric("المجموع", f"{total_allow:,.2f} جنيه")
    else:
        st.info("لا توجد بدلات مسجلة")

# ------------------------------- الواجهة الرئيسية -------------------------------
with st.sidebar:
    st.header("الجلسة")
    if not st.session_state.get("logged_in"):
        if not login_ui():
            st.stop()
    else:
        state = cleanup_sessions(load_state())
        username = st.session_state.username
        rem = remaining_time(state, username)
        if rem:
            mins, secs = divmod(int(rem.total_seconds()), 60)
            st.success(f"👋 {username} | ⏳ {mins:02d}:{secs:02d}")
        st.markdown("---")
        if st.button("🔄 تحديث"):
            if fetch_from_github_requests():
                st.rerun()
        if st.button("مسح مهملات"):
            st.cache_data.clear()
            st.rerun()
        if st.button("🚪 تسجيل الخروج"):
            logout_action()

# ------------------------------- تحميل البيانات الرئيسية -------------------------------
all_sheets = load_all_sheets()
sheets_edit = load_sheets_for_edit()
st.title(f"{APP_CONFIG['APP_ICON']} {APP_CONFIG['APP_TITLE']}")
user_role = st.session_state.get("user_role", "viewer")
user_permissions = st.session_state.get("user_permissions", ["view"])
can_edit = (user_role == "admin" or user_role == "editor" or "edit" in user_permissions)

# بناء التبويبات
tabs_list = ["🔍 بحث متقدم", "📊 تحليل البيانات", "🔔 الإشعارات"]
if can_edit:
    tabs_list.append("🛠 إدارة البيانات")
tabs_list.append("📞 الدعم الفني")
tabs = st.tabs(tabs_list)

with tabs[0]:
    search_across_sheets_hr(all_sheets)

with tabs[1]:
    analyze_hr_data(all_sheets)

with tabs[2]:
    show_hr_notifications(all_sheets)

if can_edit and len(tabs) > 3:
    with tabs[3]:
        sheets_edit = manage_hr_data(sheets_edit)

with tabs[-1]:
    st.header("📞 الدعم الفني")
    st.markdown("### تم تنفيذ هذا النظام بواسطه **م. محمد عبدالله** – رئيس قسم")
    st.markdown("---")
    support_config = load_support_config()
    current_image_url = support_config.get("image_url", "")
    current_youtube_link = support_config.get("youtube_link", "")

    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("🖼️ صورة المطور")
        if current_image_url and current_image_url.strip():
            try:
                st.image(current_image_url, use_container_width=True)
            except:
                st.warning("⚠️ تعذر عرض الصورة")
        else:
            st.info("لا توجد صورة")
    with col2:
        st.subheader("🔗 روابط التواصل")
        if current_youtube_link:
            st.markdown(f"[📺 قناة اليوتيوب]({current_youtube_link})")
        else:
            st.info("لم يتم إضافة رابط يوتيوب")
        st.markdown("📧 للتواصل: `01274424062`")
    if st.session_state.get("username") == "admin":
        st.markdown("---")
        with st.expander("⚙️ تعديل الصورة والرابط"):
            new_youtube = st.text_input("رابط اليوتيوب", value=current_youtube_link)
            uploaded_img = st.file_uploader("صورة المطور", type=APP_CONFIG["ALLOWED_IMAGE_TYPES"])
            if st.button("حفظ"):
                new_image_url = current_image_url
                if uploaded_img:
                    new_image_url = upload_image_to_github(uploaded_img, "support", "developer")
                new_config = {"image_url": new_image_url, "youtube_link": new_youtube}
                save_support_config(new_config)
                st.success("تم التحديث")
                st.rerun()

# دالة fetch_from_github_requests (موجودة سابقاً ومعدلة للملف الجديد)
def fetch_from_github_requests():
    try:
        response = requests.get(GITHUB_EXCEL_URL, stream=True, timeout=15)
        response.raise_for_status()
        with open(APP_CONFIG["LOCAL_FILE"], "wb") as f:
            shutil.copyfileobj(response.raw, f)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"فشل التحديث: {e}")
        return False

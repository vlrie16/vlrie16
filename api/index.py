"""
Template Flask Login -> Dashboard
Deploy: Vercel | Database: Supabase (PostgreSQL)
"""
import os
from datetime import datetime, timedelta, time, timezone
from functools import wraps
try:
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    WIB = timezone(timedelta(hours=7))

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import func
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ganti-secret-key-ini")


def to_wib(dt):
    """Konversi datetime objek ke zona waktu WIB (Asia/Jakarta, UTC+7)."""
    if not dt:
        return None
    if dt.tzinfo is None:
        # Anggap naive datetime dari DB/UTC sebagai UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(WIB)


@app.template_filter("wib_format")
def wib_format_filter(dt, fmt="%d %b %Y, %H:%M"):
    """Filter Jinja2 untuk memformat datetime ke zona waktu WIB."""
    if not dt:
        return "-"
    wib_dt = to_wib(dt)
    return wib_dt.strftime(fmt)


# DATABASE_URL diambil dari Environment Variable (Vercel / file .env lokal).
# Gunakan connection string "Transaction pooler" Supabase (port 6543).
db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
# Paksa pakai driver psycopg (versi 3) supaya cocok dengan requirements.txt
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# NullPool: tidak menahan koneksi, cocok untuk serverless (Vercel)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"poolclass": NullPool}

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nama = db.Column(db.String(100))
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), default=datetime.utcnow)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Silakan login terlebih dahulu.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["nama"] = user.nama or user.username
            return redirect(url_for("dashboard"))

        flash("Username atau password salah.", "danger")
    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    total_user = User.query.count()

    # Waktu saat ini dalam WIB
    now_wib = datetime.now(WIB)
    today_wib = now_wib.date()

    # Batas hari ini WIB (diubah ke UTC untuk query database)
    start_of_today_wib = datetime.combine(today_wib, time.min, tzinfo=WIB)
    start_of_today_utc = start_of_today_wib.astimezone(timezone.utc)

    # Batas 7 hari terakhir WIB
    start_of_7_days_wib = now_wib - timedelta(days=7)
    start_of_7_days_utc = start_of_7_days_wib.astimezone(timezone.utc)

    user_hari_ini = User.query.filter(User.created_at >= start_of_today_utc).count()
    user_7_hari = User.query.filter(User.created_at >= start_of_7_days_utc).count()
    user_lama = max(0, total_user - user_7_hari)

    # Hitung pendaftaran per hari selama 7 hari terakhir dalam penanggalan WIB
    chart_line_labels = []
    chart_line_data = []

    for i in range(6, -1, -1):
        target_date_wib = today_wib - timedelta(days=i)
        day_start_wib = datetime.combine(target_date_wib, time.min, tzinfo=WIB)
        day_end_wib = datetime.combine(target_date_wib, time.max, tzinfo=WIB)

        day_start_utc = day_start_wib.astimezone(timezone.utc)
        day_end_utc = day_end_wib.astimezone(timezone.utc)

        count = User.query.filter(User.created_at >= day_start_utc, User.created_at <= day_end_utc).count()

        chart_line_labels.append(target_date_wib.strftime("%d %b"))
        chart_line_data.append(count)

    # Data untuk grafik donut: user baru 7 hari vs user lama
    chart_donut_labels = ["User Baru (7 Hari)", "User Lama"]
    chart_donut_data = [user_7_hari, user_lama]

    tanggal_hari_ini = now_wib.strftime("%d %B %Y")

    # 5 User Terbaru
    users_terbaru = User.query.order_by(User.created_at.desc(), User.id.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        nama=session["nama"],
        total_user=total_user,
        user_hari_ini=user_hari_ini,
        user_7_hari=user_7_hari,
        tanggal_hari_ini=tanggal_hari_ini,
        chart_line_labels=chart_line_labels,
        chart_line_data=chart_line_data,
        chart_donut_labels=chart_donut_labels,
        chart_donut_data=chart_donut_data,
        users_terbaru=users_terbaru,
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("Anda telah logout.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)

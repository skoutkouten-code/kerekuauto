import sys
import subprocess
import importlib

# Если Flask не установлен в этом Python, он поставится сам
try:
    import flask  # noqa: F401
except ImportError:
    print("Устанавливаю Flask, подождите...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
        importlib.invalidate_caches()
    except subprocess.CalledProcessError:
        print()
        print("Не удалось установить Flask в этот Python.")
        print("Запустите сайт двойным щелчком по файлу start.bat")
        sys.exit(1)

import os
import sqlite3
import time
import uuid
import secrets
from functools import wraps

from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, flash, abort)
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "cars.db")
UPLOAD_DIR = os.path.join(BASE, "static", "uploads")
ALLOWED = {"jpg", "jpeg", "png", "webp"}

# ============ НАСТРОЙКИ: логин и пароль админа ============
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "gVbSXY3yehBYn9"
SECRET_KEY = "2680540253d304e9a3f4183d6d900cac0067c365651be5e66f3efe505b91d74e"
# ==========================================================

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024   # фото до 8 МБ
ADMIN_HASH = generate_password_hash(ADMIN_PASSWORD)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------- база данных ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS cars(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand TEXT NOT NULL,
        model TEXT NOT NULL,
        year INTEGER NOT NULL,
        km INTEGER NOT NULL,
        price INTEGER NOT NULL,
        body TEXT DEFAULT '',
        gear TEXT DEFAULT '',
        engine TEXT DEFAULT '',
        photo TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        created TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit()
    con.close()


init_db()


# ---------- защита ----------
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.filters["num"] = lambda n: f"{int(n):,}".replace(",", " ")


@app.before_request
def check_csrf():
    if request.method == "POST":
        if request.form.get("csrf") != session.get("csrf"):
            abort(400)


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return wrapper


# ---------- помощники ----------
def read_form():
    f = request.form
    try:
        data = dict(
            brand=f["brand"].strip(),
            model=f["model"].strip(),
            year=int(f["year"]),
            km=int(f["km"]),
            price=int(f["price"]),
            body=f.get("body", "").strip(),
            gear=f.get("gear", "").strip(),
            engine=f.get("engine", "").strip(),
        )
    except (KeyError, ValueError):
        return None, "Год, пробег и цена должны быть числами."
    if not data["brand"] or not data["model"]:
        return None, "Укажите бренд и название."
    if not (1980 <= data["year"] <= 2100) or data["km"] < 0 or data["price"] < 0:
        return None, "Проверьте год, пробег и цену."
    return data, None


def save_photo(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED:
        raise ValueError("Фото должно быть в формате JPG, PNG или WEBP.")
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(UPLOAD_DIR, name))
    return name


def remove_photo(name):
    if name:
        p = os.path.join(UPLOAD_DIR, os.path.basename(name))
        if os.path.isfile(p):
            os.remove(p)


# ---------- публичный сайт ----------
@app.route("/")
def index():
    rows = db().execute(
        "SELECT * FROM cars WHERE status IN ('active','sold') ORDER BY id DESC"
    ).fetchall()
    cars = []
    for r in rows:
        d = dict(r)
        d["photo"] = url_for("static", filename="uploads/" + r["photo"]) if r["photo"] else ""
        cars.append(d)
    return render_template("index.html", cars=cars)


# ---------- вход и выход ----------
@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ok = (request.form.get("login", "") == ADMIN_LOGIN and
              check_password_hash(ADMIN_HASH, request.form.get("password", "")))
        if ok:
            session.clear()
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin"))
        time.sleep(1)
        flash("Неверный логин или пароль.")
    return render_template("login.html")


@app.route("/admin/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- админка ----------
@app.route("/admin")
@admin_required
def admin():
    st = request.args.get("status", "active")
    if st not in ("active", "sold", "archived", "all"):
        st = "active"
    if st == "all":
        rows = db().execute("SELECT * FROM cars ORDER BY id DESC").fetchall()
    else:
        rows = db().execute("SELECT * FROM cars WHERE status=? ORDER BY id DESC", (st,)).fetchall()
    counts = {r["status"]: r["n"] for r in
              db().execute("SELECT status, COUNT(*) AS n FROM cars GROUP BY status")}
    return render_template("admin.html", cars=rows, st=st, counts=counts)


@app.route("/admin/car/new", methods=["GET", "POST"])
@admin_required
def car_new():
    if request.method == "POST":
        data, err = read_form()
        photo = None
        if not err:
            try:
                photo = save_photo(request.files.get("photo"))
            except ValueError as e:
                err = str(e)
        if err:
            flash(err)
            return render_template("car_form.html", car=request.form.to_dict(), new=True)
        db().execute(
            "INSERT INTO cars(brand,model,year,km,price,body,gear,engine,photo) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (data["brand"], data["model"], data["year"], data["km"], data["price"],
             data["body"], data["gear"], data["engine"], photo or ""))
        db().commit()
        flash("Машина добавлена.")
        return redirect(url_for("admin"))
    return render_template("car_form.html", car={}, new=True)


@app.route("/admin/car/<int:cid>/edit", methods=["GET", "POST"])
@admin_required
def car_edit(cid):
    row = db().execute("SELECT * FROM cars WHERE id=?", (cid,)).fetchone()
    if row is None:
        abort(404)
    car = dict(row)
    if request.method == "POST":
        data, err = read_form()
        photo = None
        if not err:
            try:
                photo = save_photo(request.files.get("photo"))
            except ValueError as e:
                err = str(e)
        if err:
            flash(err)
            car.update(request.form.to_dict())
            return render_template("car_form.html", car=car, new=False)
        if photo:
            remove_photo(car["photo"])
            data["photo"] = photo
        else:
            data["photo"] = car["photo"]
        db().execute(
            "UPDATE cars SET brand=?,model=?,year=?,km=?,price=?,body=?,gear=?,engine=?,photo=? "
            "WHERE id=?",
            (data["brand"], data["model"], data["year"], data["km"], data["price"],
             data["body"], data["gear"], data["engine"], data["photo"], cid))
        db().commit()
        flash("Изменения сохранены.")
        return redirect(url_for("admin", status=car["status"]))
    return render_template("car_form.html", car=car, new=False)


@app.route("/admin/car/<int:cid>/status", methods=["POST"])
@admin_required
def car_status(cid):
    s = request.form.get("status")
    if s not in ("active", "sold", "archived"):
        abort(400)
    db().execute("UPDATE cars SET status=? WHERE id=?", (s, cid))
    db().commit()
    flash({"active": "Машина снова в продаже.",
           "sold": "Машина отмечена как проданная.",
           "archived": "Машина перемещена в архив."}[s])
    return redirect(url_for("admin", status=request.form.get("back", "active")))


if __name__ == "__main__":
    app.run(debug=True)

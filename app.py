"""
Flutterwave License Gate — minimal reference template

Gates a Flask resource behind a one-time Flutterwave payment,
using a license-key system: pay -> get key -> activate key on
a resource -> resource unlocked.

Env vars required: FLW_SECRET_KEY, FLW_PUBLIC_KEY
"""
import os
import uuid
import secrets
import sqlite3
import requests as ext_requests
from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)
DB = "licenses.db"

FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY")
FLW_PUBLIC_KEY = os.environ.get("FLW_PUBLIC_KEY")
LICENSE_PRICE_USD = 5


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS resource (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE,
            email TEXT,
            flw_tx_ref TEXT,
            active INTEGER DEFAULT 0,
            resource_id INTEGER
        )
    """)
    db.commit()
    db.close()


def get_license_for_resource(resource_id):
    db = get_db()
    lic = db.execute(
        "SELECT * FROM licenses WHERE resource_id = ? AND active = 1",
        (resource_id,)
    ).fetchone()
    db.close()
    return lic


def resource_is_licensed(resource_id):
    return get_license_for_resource(resource_id) is not None


# ---------- Example gated resource ----------

@app.route("/")
def home():
    db = get_db()
    rows = db.execute("SELECT * FROM resource ORDER BY id DESC").fetchall()
    db.close()
    return render_template("home.html", resources=rows)


@app.route("/resource/create", methods=["POST"])
def create_resource():
    name = request.form.get("name")
    db = get_db()
    cur = db.execute("INSERT INTO resource (name) VALUES (?)", (name,))
    db.commit()
    new_id = cur.lastrowid
    db.close()
    return redirect(f"/resource/{new_id}/view")


@app.route("/resource/<int:resource_id>/view")
def view_resource(resource_id):
    if not resource_is_licensed(resource_id):
        return redirect(f"/resource/{resource_id}/license_required")
    db = get_db()
    res = db.execute("SELECT * FROM resource WHERE id = ?", (resource_id,)).fetchone()
    db.close()
    return render_template("resource.html", resource=res)


# ---------- License gate ----------

@app.route("/resource/<int:resource_id>/license_required", methods=["GET"])
def license_required(resource_id):
    db = get_db()
    res = db.execute("SELECT * FROM resource WHERE id = ?", (resource_id,)).fetchone()
    db.close()
    return render_template(
        "license_required.html",
        resource_id=resource_id,
        resource_name=res["name"] if res else "Unknown"
    )


@app.route("/resource/<int:resource_id>/activate", methods=["POST"])
def activate_license(resource_id):
    key = request.form.get("license_key", "").strip()
    db = get_db()
    lic = db.execute(
        "SELECT * FROM licenses WHERE license_key = ? AND active = 1",
        (key,)
    ).fetchone()

    if lic and lic["resource_id"] is None:
        db.execute("UPDATE licenses SET resource_id = ? WHERE id = ?", (resource_id, lic["id"]))
        db.commit()
        db.close()
        return redirect(f"/resource/{resource_id}/view")
    elif lic and lic["resource_id"] == resource_id:
        db.close()
        return redirect(f"/resource/{resource_id}/view")
    else:
        db.close()
        return redirect(f"/resource/{resource_id}/license_required?error=invalid")


# ---------- Flutterwave checkout ----------

@app.route("/pricing")
def pricing():
    return render_template("pricing.html", flw_public_key=FLW_PUBLIC_KEY, price=LICENSE_PRICE_USD)


@app.route("/checkout/initiate", methods=["POST"])
def checkout_initiate():
    email = request.form.get("email", "").strip()
    if not email:
        return "Email required", 400
    tx_ref = f"license-{uuid.uuid4().hex[:12]}"
    db = get_db()
    db.execute(
        "INSERT INTO licenses (license_key, email, flw_tx_ref, active) VALUES (?, ?, ?, ?)",
        (f"PENDING-{tx_ref}", email, tx_ref, 0)
    )
    db.commit()
    db.close()
    return redirect(url_for("checkout_pay", tx_ref=tx_ref, email=email))


@app.route("/checkout/pay")
def checkout_pay():
    tx_ref = request.args.get("tx_ref")
    email = request.args.get("email")
    return render_template(
        "checkout_pay.html",
        tx_ref=tx_ref, email=email,
        flw_public_key=FLW_PUBLIC_KEY,
        amount=LICENSE_PRICE_USD,
        redirect_url=url_for("checkout_callback", _external=True)
    )


@app.route("/checkout/callback")
def checkout_callback():
    tx_id = request.args.get("transaction_id")
    tx_ref = request.args.get("tx_ref")
    status = request.args.get("status")

    if status != "successful" or not tx_id:
        return render_template("checkout_failed.html")

    resp = ext_requests.get(
        f"https://api.flutterwave.com/v3/transactions/{tx_id}/verify",
        headers={"Authorization": f"Bearer {FLW_SECRET_KEY}"}
    )
    data = resp.json()

    if data.get("status") != "success":
        return render_template("checkout_failed.html")

    tx_data = data.get("data", {})
    verified_amount = tx_data.get("amount")
    verified_currency = tx_data.get("currency")
    verified_status = tx_data.get("status")
    verified_tx_ref = tx_data.get("tx_ref")

    if (verified_status != "successful"
            or verified_amount < LICENSE_PRICE_USD
            or verified_currency != "USD"
            or verified_tx_ref != tx_ref):
        return render_template("checkout_failed.html")

    db = get_db()
    row = db.execute("SELECT * FROM licenses WHERE flw_tx_ref = ?", (tx_ref,)).fetchone()
    if not row:
        db.close()
        return render_template("checkout_failed.html")

    if row["license_key"].startswith("PENDING-"):
        new_key = "LIC-" + secrets.token_hex(8).upper()
        db.execute(
            "UPDATE licenses SET license_key = ?, active = 1 WHERE flw_tx_ref = ?",
            (new_key, tx_ref)
        )
        db.commit()
    else:
        new_key = row["license_key"]
    db.close()

    return render_template("checkout_success.html", license_key=new_key)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080, debug=True)

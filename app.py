from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = "supersecret"

DB = "friendsbet.db"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# -------- Database helpers --------
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance INTEGER DEFAULT 1000,
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            winner_outcome_id INTEGER,
            approved INTEGER DEFAULT 1,
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS event_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            outcome_name TEXT NOT NULL,
            odds REAL NOT NULL,
            FOREIGN KEY(event_id) REFERENCES events(id)
        );

        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            outcome_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(event_id) REFERENCES events(id),
            FOREIGN KEY(outcome_id) REFERENCES event_outcomes(id)
        );
        """)

    with get_db() as db:
        admin = db.execute("SELECT * FROM users WHERE username=?", (ADMIN_USERNAME,)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users (username, password, balance, is_admin) VALUES (?,?,?,1)",
                (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 0)
            )
            print(f"✅ Admin account created: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
        db.commit()

if not os.path.exists(DB):
    init_db()
else:
    init_db()

# -------- Routes --------
@app.route("/")
def index():
    db = get_db()

    # ✅ Approved & unresolved events (bets allowed)
    events = db.execute("""
        SELECT * FROM events
        WHERE winner_outcome_id IS NULL AND approved = 1
    """).fetchall()

    events_data = []
    for event in events:
        outcomes = db.execute("SELECT * FROM event_outcomes WHERE event_id=?", (event["id"],)).fetchall()
        bets = db.execute("""
            SELECT b.*, u.username, u.is_admin, o.outcome_name
            FROM bets b
            JOIN users u ON b.user_id = u.id
            JOIN event_outcomes o ON b.outcome_id = o.id
            WHERE b.event_id = ? AND b.status = 'pending'
        """, (event["id"],)).fetchall()

        events_data.append({
            "event": event,
            "outcomes": outcomes,
            "bets": bets
        })

    # ⏳ Pending & unresolved events (bets not yet allowed)
    pending_events = db.execute("""
        SELECT * FROM events
        WHERE winner_outcome_id IS NULL AND approved = 0
    """).fetchall()

    pending_events_data = []
    for event in pending_events:
        outcomes = db.execute("SELECT * FROM event_outcomes WHERE event_id=?", (event["id"],)).fetchall()
        pending_events_data.append({
            "event": event,
            "outcomes": outcomes
        })

    # 🎯 Random fun slogan
    slogans = [
        "Bet smart. Win big. Brag always! 😎",
        "Fortune favors the bold… and the silly. 😂",
        "Go on, make that risky bet. What could possibly go wrong? 🙈",
        "Today's hunch could be tomorrow's legend 🎯",
        "Low odds? High odds? It’s all in the fun! 🎲",
        "Bet small, win big, tell great stories 📖",
        "Do it for the glory, not the credits! 🏆",
        "This is where bragging rights are won 🏅",
        "The best way to predict the future? Bet on it! 🔮",
        "Your gut feeling is whispering… are you listening? 😉"
    ]
    slogan = random.choice(slogans)

    return render_template(
        "index.html",
        events_data=events_data,
        pending_events_data=pending_events_data,
        slogan=slogan
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = generate_password_hash(request.form["password"])
        try:
            with get_db() as db:
                db.execute("INSERT INTO users(username,password) VALUES (?,?)", (username, password))
                # Fetch the newly created user (includes balance)
                user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            
            # Auto-login: set session vars
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            session["balance"] = user["balance"]  # ⭐ store balance for navbar

            flash(f"Welcome {session['username']}! You have been registered and logged in.")
            return redirect(url_for("index"))
        except:
            flash("Username already taken.")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute("SELECT * FROM users WHERE username=?", (request.form["username"],)).fetchone()
        if user and check_password_hash(user["password"], request.form["password"]):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            session["balance"] = user["balance"]  # ⭐
            flash(f"Welcome {session['username']}!")
            return redirect(url_for("index"))
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("index"))

@app.route("/place_bet/<int:event_id>", methods=["POST"])
def place_bet(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    outcome_id = int(request.form["outcome_id"])
    amount = int(request.form["amount"])
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if amount > user["balance"]:
        flash("Not enough credits!")
        return redirect(url_for("index"))

    db.execute("INSERT INTO bets(user_id,event_id,outcome_id,amount) VALUES(?,?,?,?)",
               (session["user_id"], event_id, outcome_id, amount))
    db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, session["user_id"]))
    db.commit()
    
    # ⭐ Update session balance
    updated_user = db.execute("SELECT balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
    session["balance"] = updated_user["balance"]

    flash("Bet placed!")
    return redirect(url_for("index"))

@app.route("/admin_add", methods=["GET", "POST"])
def admin_add():
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    if request.method == "POST":
        title = request.form["title"]
        outcomes = request.form.getlist("outcome_name")
        odds_list = request.form.getlist("odds")
        with get_db() as db:
            cur = db.execute("INSERT INTO events (title) VALUES (?)", (title,))
            event_id = cur.lastrowid
            for name, odd in zip(outcomes, odds_list):
                if name.strip():
                    db.execute("INSERT INTO event_outcomes (event_id, outcome_name, odds) VALUES (?,?,?)",
                               (event_id, name.strip(), float(odd)))
            db.commit()
        flash("Event added!")
        return redirect(url_for("index"))
    return render_template("admin_add.html")

@app.route("/activity_log")
def activity_log():
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))

    logs = []
    try:
        logs = get_db().execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT 100"
        ).fetchall()
    except Exception:
        flash("Activity log table not found or empty.")

    return render_template("activity_log.html", logs=logs)

@app.route("/submit_event", methods=["GET", "POST"])
def submit_event():
    if "user_id" not in session:
        flash("You must be logged in to submit an event.")
        return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form["title"]
        outcomes = request.form.getlist("outcome_name")
        odds_list = request.form.getlist("odds")
        with get_db() as db:
            cur = db.execute("INSERT INTO events (title, approved) VALUES (?, 0)", (title,))
            event_id = cur.lastrowid
            for name, odd in zip(outcomes, odds_list):
                if name.strip():
                    db.execute("INSERT INTO event_outcomes (event_id, outcome_name, odds) VALUES (?,?,?)",
                               (event_id, name.strip(), float(odd)))
            db.commit()
        flash("Your event has been submitted and is pending admin approval.")
        return redirect(url_for("index"))
    return render_template("submit_event.html")

@app.route("/admin_approvals")
def admin_approvals():
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    db = get_db()
    pending_events = db.execute("SELECT * FROM events WHERE approved=0").fetchall()
    events_data = []
    for event in pending_events:
        outcomes = db.execute("SELECT * FROM event_outcomes WHERE event_id=?", (event["id"],)).fetchall()
        events_data.append({"event": event, "outcomes": outcomes})
    return render_template("admin_approvals.html", events_data=events_data)

@app.route("/approve_event/<int:event_id>")
def approve_event(event_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    with get_db() as db:
        db.execute("UPDATE events SET approved=1 WHERE id=?", (event_id,))
        db.commit()
    flash("Event approved!")
    return redirect(url_for("admin_approvals"))

@app.route("/delete_event/<int:event_id>")
def delete_event(event_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    with get_db() as db:
        db.execute("DELETE FROM event_outcomes WHERE event_id=?", (event_id,))
        db.execute("DELETE FROM events WHERE id=?", (event_id,))
        db.commit()
    flash("Event deleted!")
    return redirect(url_for("admin_approvals"))

@app.route("/admin_resolve/<int:event_id>", methods=["POST"])
def admin_resolve(event_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))

    winner_outcome_id = int(request.form["winner_outcome_id"])
    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as db:
        # Mark event as resolved
        db.execute("UPDATE events SET winner_outcome_id=?, resolved_at=? WHERE id=?",
                   (winner_outcome_id, resolved_time, event_id))

        # Fetch all bets for the event
        bets = db.execute("SELECT * FROM bets WHERE event_id=?", (event_id,)).fetchall()
        winner = db.execute("SELECT * FROM event_outcomes WHERE id=?", (winner_outcome_id,)).fetchone()

        # Total pot = sum of all stakes
        total_pot = sum(b["amount"] for b in bets)

        # Find winning bets
        winning_bets = [b for b in bets if b["outcome_id"] == winner_outcome_id]

        if winning_bets:
            # Calculate total weight (stake × odds for each winning bet)
            total_weight = sum(b["amount"] * winner["odds"] for b in winning_bets)

            for b in bets:
                if b["outcome_id"] == winner_outcome_id:
                    # Weight for this bet
                    bet_weight = b["amount"] * winner["odds"]
                    # Share of pot
                    payout = (bet_weight / total_weight) * total_pot
                    db.execute("UPDATE bets SET status='won' WHERE id=?", (b["id"],))
                    db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (int(payout), b["user_id"]))
                else:
                    db.execute("UPDATE bets SET status='lost' WHERE id=?", (b["id"],))
        else:
            # No winners — credits vanish (or could refund)
            pass

        db.commit()

        # Update logged-in admin balance in session
        updated_balance = db.execute("SELECT balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
        session["balance"] = updated_balance["balance"]

    flash("Event resolved and credits redistributed to winners!")
    return redirect(url_for("index"))

@app.route("/leaderboard")
def leaderboard():
    db = get_db()
    # Count distinct events where user has won bets
    users = db.execute("""
        SELECT u.username, u.balance, u.is_admin,
               COUNT(DISTINCT b.event_id) AS events_won
        FROM users u
        LEFT JOIN bets b ON u.id = b.user_id AND b.status = 'won'
        GROUP BY u.id
        ORDER BY u.balance DESC
    """).fetchall()
    return render_template("leaderboard.html", leaderboard=users)

@app.route("/manage_users")
def manage_users():
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    users = get_db().execute("SELECT id, username, balance, is_admin FROM users").fetchall()
    return render_template("manage_users.html", users=users)

@app.route("/promote/<int:user_id>")
def promote_user(user_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    with get_db() as db:
        db.execute("UPDATE users SET is_admin=1 WHERE id=?", (user_id,))
        db.commit()
    flash("User promoted to admin!")
    return redirect(url_for("manage_users", target_id=user_id))

@app.route("/demote/<int:user_id>")
def demote_user(user_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    if user_id == session["user_id"]:
        flash("You cannot demote yourself!")
        return redirect(url_for("manage_users"))
    with get_db() as db:
        db.execute("UPDATE users SET is_admin=0 WHERE id=?", (user_id,))
        db.commit()
    flash("User demoted to normal user!")
    return redirect(url_for("manage_users", target_id=user_id))

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))

    if user_id == session["user_id"]:
        flash("You cannot delete your own account while logged in.")
        return redirect(url_for("manage_users"))

    with get_db() as db:
        db.execute("DELETE FROM bets WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()

    flash(f"User ID {user_id} has been deleted.")
    return redirect(url_for("manage_users"))

@app.route("/my_bets")
def my_bets():
    if "user_id" not in session:
        flash("You must be logged in to view bets.")
        return redirect(url_for("login"))
    db = get_db()
    bets = db.execute("""
        SELECT b.id, e.title, o.outcome_name, b.amount, b.status, o.odds, u.username, u.is_admin, e.resolved_at
        FROM bets b
        JOIN events e ON b.event_id = e.id
        JOIN event_outcomes o ON b.outcome_id = o.id
        JOIN users u ON b.user_id = u.id
        WHERE b.user_id = ?
        ORDER BY b.id DESC
    """, (session["user_id"],)).fetchall()
    return render_template("bets.html", bets=bets, title="My Bets")

@app.route("/topup/<int:user_id>", methods=["POST"])
def topup(user_id):
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))
    amount = request.form.get("amount")
    if not amount or not amount.isdigit():
        flash("Invalid amount entered.")
        return redirect(url_for("manage_users"))
    amount = int(amount)
    with get_db() as db:
        db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, user_id))
        db.commit()
        # ⭐ If admin tops up themselves, update their navbar
        if user_id == session["user_id"]:
            updated_user = db.execute("SELECT balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
            session["balance"] = updated_user["balance"]

    flash(f"Top-up successful! Added {amount} credits.")
    return redirect(url_for("manage_users", target_id=user_id))

@app.route("/all_bets")
def all_bets():
    if not session.get("is_admin"):
        flash("Admin access only!")
        return redirect(url_for("index"))

    date_from = request.args.get("from")
    date_to = request.args.get("to")

    query = """
        SELECT b.id, e.title, o.outcome_name, b.amount, b.status, o.odds, 
               u.username, u.is_admin, e.resolved_at
        FROM bets b
        JOIN events e ON b.event_id = e.id
        JOIN event_outcomes o ON b.outcome_id = o.id
        JOIN users u ON b.user_id = u.id
        WHERE 1=1
    """
    params = []

    if date_from:
        query += " AND date(e.resolved_at) >= date(?)"
        params.append(date_from)
    if date_to:
        query += " AND date(e.resolved_at) <= date(?)"
        params.append(date_to)

    query += " ORDER BY 
        CASE WHEN e.resolved_at IS NULL THEN 1 ELSE 0 END,
        datetime(e.resolved_at) DESC,
        b.id DESC"

    bets = get_db().execute(query, params).fetchall()

    return render_template(
        "bets.html",
        bets=bets,
        title="All Bets",
        date_from=date_from or "",
        date_to=date_to or "",
        datetime=datetime,
        timedelta=timedelta
    )

if __name__ == "__main__":
    app.run(debug=True, port=5000)
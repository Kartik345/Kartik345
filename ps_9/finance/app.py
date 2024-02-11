import os
import time

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    session.clear()

    if request.method == "GET":
        return render_template("register.html")

    elif request.method == "POST":
        name = request.form.get("username")
        password = request.form.get("password")
        password2 = request.form.get("confirmation")

        # Verifying the information
        if not name:
            return apology("must provide username")
        elif password != password2:
            return apology("not verified")
        elif not password or not password2:
            return apology("must provide password and confirm it")

        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )
        if len(rows) != 0:
            return apology("username already exists")

        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", name, hash)

        rows = db.execute("SELECT * FROM users WHERE username = ?", name)

        session["user_id"] = rows[0]["id"]
        return redirect("/")  # portfolio page


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("Enter valid stock symbol")
        return render_template("quote.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # fetching data
        shares = request.form.get("shares")
        symbol = request.form.get("symbol").upper()

        if not symbol:
            return apology("must provide a symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("share must be positive integer")

        quote = lookup(symbol)
        if quote is None:
            return apology("Quote not found")
        price = quote["price"]
        gross = int(shares) * price

        cash = db.execute(
            "SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"]
        )[0]["cash"]
        if cash < gross:
            return apology("Sorry to break it to you, but you are broke")

        db.execute(
            "UPDATE users SET cash = cash  - :gross WHERE id = :user_id",
            gross=gross,
            user_id=session["user_id"],
        )

        alpha = db.execute(
            "SELECT * FROM records WHERE id = ? AND name = ?",
            session["user_id"],
            symbol,
        )
        if len(alpha) != 1:
            db.execute(
                "INSERT INTO records (id, name, shares) VALUES (?, ?, ?)",
                session["user_id"],
                symbol,
                shares,
            )
        else:
            db.execute(
                "UPDATE records SET shares = shares + ? WHERE id = ?",
                shares,
                session["user_id"],
            )

        local_time = time.localtime()
        db.execute(
            "INSERT INTO transactions (action, name, price, shares, time, id) VALUES (?, ?, ?, ?, ?, ?)",
            "bought",
            symbol,
            quote["price"],
            shares,
            time.asctime(local_time),
            session["user_id"],
        )

        flash(f"Successfully purchased {shares} shares of {symbol} for {usd(gross)} ")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        limit = db.execute(
            "SELECT shares FROM records WHERE id = ? AND name = ?",
            session["user_id"],
            symbol,
        )[0]["shares"]

        if not symbol:
            return apology("Enter valid symbol")
        elif not shares or int(shares) < 0 or not shares.isdigit():
            return apology("Enter valid share number")

        if limit < int(shares):
            return apology("Not enough shares")

        quote = lookup(symbol)
        gross = int(shares) * quote["price"]

        db.execute(
            "UPDATE users SET cash = cash + ? WHERE id = ?", gross, session["user_id"]
        )
        db.execute(
            "UPDATE records SET shares = shares - ? WHERE name = ?",
            shares,
            session["user_id"],
        )

        local_time = time.localtime()
        db.execute(
            "INSERT INTO transactions (action, name, price, shares, time, id) VALUES (?, ?, ?, ?, ?, ?)",
            "sold",
            symbol,
            quote["price"],
            shares,
            time.asctime(local_time),
            session["user_id"],
        )

        flash(f"Successfully sold {shares} shares of {symbol} for {usd(gross)} ")
        return redirect("/")

    else:
        kell = db.execute("SELECT name FROM records WHERE id = ?", session["user_id"])
        return render_template("sell.html", kell=kell)


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0][
        "cash"
    ]
    kell = db.execute("SELECT name FROM records WHERE id = ?", session["user_id"])
    for i in kell:
        row = db.execute("SELECT * FROM fluid WHERE name = ?", i["name"])
        if len(row) != 1:
            db.execute(
                "INSERT INTO fluid (name, price) VALUES(?, ?)",
                i["name"],
                lookup(i["name"])["price"],
            )
        else:
            db.execute("DELETE FROM fluid WHERE name = ?", i["name"])
            db.execute(
                "INSERT INTO fluid (name, price) VALUES(?, ?)",
                i["name"],
                lookup(i["name"])["price"],
            )

    finn = db.execute(
        "SELECT records.name, shares, fluid.price FROM records JOIN fluid ON records.name = fluid.name WHERE records.id = ?",
        session["user_id"],
    )
    total = 0
    for i in finn:
        total = total + i["shares"] * i["price"]

    total = total + cash
    return render_template("index.html", finn=finn, cash=usd(cash), total=usd(total))


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    ladu = db.execute("SELECT * FROM transactions WHERE id = ?", session["user_id"])
    return render_template("history.html", ladu=ladu)



@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

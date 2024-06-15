import os

from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
# if not os.environ.get("API_KEY"):
#     raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT symbol, SUM(shares) as shares, price, name FROM owned WHERE id = ? GROUP BY symbol", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    for stock in stocks:
        look = lookup(stock["symbol"])
        if look:
            stock["price"] = look["price"]
            stock["symbol"] = stock["symbol"].upper()
        else:
            continue

    return render_template("index.html", stonk=stocks, cash=cash)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        amount = request.form.get("shares")

        if not amount.isdigit() or int(amount) < 1:
            return apology("Incorrect share amount", 400)

        stock = lookup(symbol)
        amount = int(amount)
        if not stock:
            return apology("Incorrect Symbol!", 400)
        rqcash = float(stock["price"]) * amount
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        if cash < rqcash:
            return apology("Insufficient funds!")
        else:
            remaining = cash - rqcash
            now = datetime.now()
            date = now.strftime("%d/%m/%Y %H:%M:%S")
            db.execute("UPDATE users SET cash = ? WHERE id = ?", remaining, session["user_id"])
            db.execute("INSERT INTO owned (symbol, shares, price, date, id, name) VALUES (?, ?, ?, ?, ?, ?)", symbol, amount, stock["price"], date, session["user_id"], stock["name"])

            # Insert into System History
            db.execute("INSERT INTO history (id, action, amount, price, date, symbol) VALUES (?, ?, ?, ?, ?, ?)", session["user_id"], "buy", amount, stock["price"], date, symbol)

            return redirect("/")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    owned = db.execute("SELECT * FROM history WHERE id = ? ORDER BY date DESC", session["user_id"])
    return render_template("history.html", owned=owned)

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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password or user doesn't exist", 403)
        

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        if not symbol or symbol == " ":
            return apology("Need a symbol")

        print(symbol)
        stock = lookup(symbol.upper())
        if stock == None:
            return apology("Wrong symbol")

        name = stock["name"]
        price = stock["price"]
        symb = stock["symbol"]

        return render_template("quoted.html", name=name, price=usd(price), symbol=symb)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        pw = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username or not pw or not confirmation:
            return apology("Missing information")

        # Check if passwords match
        if pw != confirmation:
            return apology("Passwords do not match")

        # Check if username exists
        hashed = generate_password_hash(pw)
        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hashed)
        except:
            return apology("Username already exists!")

        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))

        rows = db.execute("SELECT SUM(shares) as shares FROM owned WHERE id = ? AND symbol = ?", session["user_id"], symbol)[0]["shares"]

        if not rows or not symbol:
            return apology("Not owned")

        if shares > rows:
            return apology("Not enough shares owned")

        stock = lookup(symbol)
        total = stock["price"] * shares
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        

        cash = cash + total
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])

        # Remove ownership of stock and add into system history
        if rows == shares:
            now = datetime.now()
            date = now.strftime("%d/%m/%Y %H:%M:%S")
            db.execute("DELETE FROM owned WHERE id = ? AND symbol = ?", session["user_id"], symbol)
            db.execute("INSERT INTO history (id, action, amount, price, date, symbol) VALUES (?, ?, ?, ?, ?, ?)", session["user_id"], "sell", shares, stock["price"], date, symbol)

        remaining = rows - shares
        now = datetime.now()
        date = now.strftime("%d/%m/%Y %H:%M:%S")
        db.execute("UPDATE owned SET shares = ? WHERE id = ? AND symbol = ?", remaining, session["user_id"], symbol)
        db.execute("INSERT INTO history (id, action, amount, price, date, symbol) VALUES (?, ?, ?, ?, ?, ?)", session["user_id"], "sell", shares, stock["price"], date, symbol)

        return redirect("/")
    else:
        symbols = db.execute("SELECT symbol FROM owned WHERE id = ? GROUP BY symbol", session["user_id"])
        return render_template("sell.html", symbols=symbols)

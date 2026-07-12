import os
import io
import base64
import secrets
from datetime import datetime, timedelta

import qrcode
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

# ---------------------------------------------------------------------------
# PAYMENT PROVIDER CONFIGURATION
#
# Set these as real environment variables to go live with real Stripe billing.
# Until then, DEMO_MODE runs the full billing UI/flow (trial, upgrade, cancel,
# webhooks, failed-payment simulation) without needing a live payment provider
# account - useful for testing everything end-to-end before you have a Stripe/
# Dodo Payments/Paddle account set up.
#
# NOTE for India-based founders (per earlier research): Stripe does not issue
# full accounts to Indian founders directly. Dodo Payments and Paddle both
# expose a very similar API shape (customers, subscriptions, webhooks) and are
# built for exactly this - swapping one of them in later means changing the
# functions in the "PAYMENT PROVIDER INTEGRATION" section below, not your
# database models or business logic.
# ---------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
DEMO_MODE = not bool(STRIPE_SECRET_KEY)

if STRIPE_AVAILABLE and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

# Use a real hosted database (e.g. Render/Railway's free PostgreSQL) if DATABASE_URL
# is provided as an environment variable; otherwise fall back to a local SQLite file
# for easy local testing. Render/Railway sometimes provide the URL in the old
# "postgres://" format, which SQLAlchemy 2.x requires as "postgresql://" instead.
_database_url = os.environ.get('DATABASE_URL', '')
if _database_url.startswith('postgres://'):
    _database_url = _database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = _database_url or (
    'sqlite:///' + os.path.join(basedir, 'tablebell.db')
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False, default="My Restaurant")
    owner_email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    logo_emoji = db.Column(db.String(8), default="🍽️")
    color_theme = db.Column(db.String(16), default="orange")
    plan = db.Column(db.String(20), default="starter")  # starter / growth / pro

    # --- Billing / subscription fields ---
    billing_status = db.Column(db.String(20), default="trialing")
    # trialing / active / past_due / canceled
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(120), nullable=True)
    stripe_subscription_id = db.Column(db.String(120), nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    payment_failed_at = db.Column(db.DateTime, nullable=True)  # when the most recent
    # failed charge happened, used to run the grace-period/dunning countdown

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    menu_items = db.relationship('MenuItem', backref='restaurant', cascade="all, delete-orphan")
    tables = db.relationship('Table', backref='restaurant', cascade="all, delete-orphan")
    orders = db.relationship('Order', backref='restaurant', cascade="all, delete-orphan")
    payments = db.relationship('Payment', backref='restaurant', cascade="all, delete-orphan")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), default="Main Course")
    price = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.String(255), default="")
    available = db.Column(db.Boolean, default=True)
    # If True: a "more of this" request goes through the kitchen (cook prepares it, sets
    # wait time, etc.) just like a fresh order. If False: it's treated as instantly
    # available (e.g. water, fountain soda, bread basket) and goes straight to the runner
    # with no kitchen/wait-time step.
    needs_prep = db.Column(db.Boolean, default=True)



class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    number = db.Column(db.String(10), nullable=False)
    # The waiter permanently responsible for this table during the current shift.
    # When a customer requests a refill, or the kitchen marks food ready, for this
    # table, THIS is the person who should go - no guessing, no racing to claim it.
    assigned_to = db.Column(db.String(60), nullable=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    table_number = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default="received")  # received / preparing / ready / delivered
    wait_minutes = db.Column(db.Integer, nullable=True)
    prepare_started_at = db.Column(db.DateTime, nullable=True)
    ready_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    claimed_by = db.Column(db.String(60), nullable=True)  # runner's name, set once claimed
    claimed_at = db.Column(db.DateTime, nullable=True)
    # "customer" (self-service QR order) or "staff" (a waiter took the order
    # verbally for a customer without a smartphone and entered it on their
    # behalf). Purely informational - the order flows through the exact same
    # kitchen/runner pipeline either way.
    placed_by = db.Column(db.String(20), default="customer")
    placed_by_name = db.Column(db.String(60), nullable=True)  # staff member's name, if placed_by="staff"

    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan")

    def total(self):
        return sum(i.price * i.quantity for i in self.items)

    def to_dict(self):
        remaining_seconds = None
        if self.status == "preparing" and self.wait_minutes and self.prepare_started_at:
            deadline = self.prepare_started_at + timedelta(minutes=self.wait_minutes)
            remaining_seconds = max(0, int((deadline - datetime.utcnow()).total_seconds()))
        return {
            "id": self.id,
            "table_number": self.table_number,
            "status": self.status,
            "wait_minutes": self.wait_minutes,
            "remaining_seconds": remaining_seconds,
            "created_at": self.created_at.isoformat(),
            "seconds_since_order": int((datetime.utcnow() - self.created_at).total_seconds()),
            "items": [
                {"name": i.name, "quantity": i.quantity, "note": i.note, "price": i.price}
                for i in self.items
            ],
            "total": self.total(),
            "claimed_by": self.claimed_by,
            "placed_by": self.placed_by,
            "placed_by_name": self.placed_by_name,
        }



class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.String(255), default="")


class Payment(db.Model):
    """A record of every billing event - successful charges, failed charges,
    refunds - so the owner (and you, the platform operator) have a full history."""
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # succeeded / failed / refunded
    plan = db.Column(db.String(20), nullable=False)
    stripe_event_id = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "amount": self.amount, "status": self.status,
            "plan": self.plan, "created_at": self.created_at.isoformat(),
        }


REQUEST_TYPES = {
    "napkins": {"label": "Napkins / Utensils", "icon": "🧻"},
    "assistance": {"label": "Call for Assistance", "icon": "🙋"},
    "check": {"label": "Get the Check", "icon": "🧾"},
    "item_refill": {"label": "Item Refill", "icon": "🔁"},  # used for instant (no-prep) item reorders
    "custom": {"label": "Something Else", "icon": "💬"},
}


class ServiceRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'), nullable=False)
    table_number = db.Column(db.String(10), nullable=False)
    request_type = db.Column(db.String(20), nullable=False, default="assistance")
    note = db.Column(db.String(255), default="")
    status = db.Column(db.String(20), default="open")  # open / resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    claimed_by = db.Column(db.String(60), nullable=True)  # runner's name, set once claimed
    claimed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        meta = REQUEST_TYPES.get(self.request_type, REQUEST_TYPES["custom"])
        return {
            "id": self.id,
            "table_number": self.table_number,
            "request_type": self.request_type,
            "label": meta["label"],
            "icon": meta["icon"],
            "note": self.note,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "seconds_since": int((datetime.utcnow() - self.created_at).total_seconds()),
            "claimed_by": self.claimed_by,
        }


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def current_restaurant():
    rid = session.get('restaurant_id')
    if not rid:
        return None
    return Restaurant.query.get(rid)


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_restaurant():
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped


TRIAL_DAYS = 14
GRACE_PERIOD_DAYS = 5  # days after a failed charge before service-critical
# screens (kitchen/runner) get locked - gives the owner time to fix a card
# without disrupting an active dinner service.


def get_billing_state(r):
    """
    Central source of truth for a restaurant's billing status. Returns a dict
    the templates and access-control decorators use to decide what to show/allow.
    """
    now = datetime.utcnow()
    state = {
        "status": r.billing_status,
        "is_trial": r.billing_status == "trialing",
        "trial_days_left": None,
        "trial_expired": False,
        "in_grace_period": False,
        "grace_days_left": None,
        "hard_locked": False,  # true once grace period has also run out
    }

    if r.billing_status == "trialing" and r.trial_ends_at:
        delta = r.trial_ends_at - now
        state["trial_days_left"] = max(0, delta.days + (1 if delta.seconds > 0 else 0))
        state["trial_expired"] = now >= r.trial_ends_at

    if r.billing_status == "past_due" and r.payment_failed_at:
        grace_deadline = r.payment_failed_at + timedelta(days=GRACE_PERIOD_DAYS)
        state["in_grace_period"] = now < grace_deadline
        state["grace_days_left"] = max(0, (grace_deadline - now).days)
        state["hard_locked"] = now >= grace_deadline

    return state


def business_features_allowed(r):
    """
    Business/admin features (menu editing, analytics, sections setup) require
    active billing. Kitchen and Runner screens are deliberately NOT gated by
    this, so a lapsed payment never interrupts an active dinner service - see
    service_critical_allowed() below.
    """
    state = get_billing_state(r)
    if state["status"] == "active":
        return True
    if state["status"] == "trialing" and not state["trial_expired"]:
        return True
    if state["status"] == "past_due" and state["in_grace_period"]:
        return True
    return False


def service_critical_allowed(r):
    """
    Kitchen/Runner/customer-ordering screens: only ever locked if billing has
    been broken long enough to exhaust BOTH the trial and the grace period.
    This is intentionally more lenient than business_features_allowed() so
    that a card failure never takes down live service on a busy night.
    """
    state = get_billing_state(r)
    if state["status"] == "canceled":
        return False
    if state["status"] == "trialing":
        # allow a short buffer past trial end before touching live service
        return not state["trial_expired"] or (
            r.trial_ends_at and datetime.utcnow() < r.trial_ends_at + timedelta(days=2)
        )
    if state["status"] == "past_due":
        return not state["hard_locked"]
    return True


def billing_required(view):
    """Gate for business/admin routes (menu, analytics, sections)."""
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        r = current_restaurant()
        if r and not business_features_allowed(r):
            return redirect(url_for('billing'))
        return view(*args, **kwargs)
    return wrapped


def service_critical_required(view):
    """
    Gate for Kitchen/Runner page views only. Deliberately much more lenient
    than billing_required() - only blocks once BOTH the trial and the grace
    period after a failed payment have fully run out, so live dinner service
    is never interrupted by a routine billing hiccup.
    """
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        r = current_restaurant()
        if r and not service_critical_allowed(r):
            flash("Service is paused because billing hasn't been resolved. Please update payment to resume.", "error")
            return redirect(url_for('billing'))
        return view(*args, **kwargs)
    return wrapped


def make_qr_base64(data: str) -> str:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def gen_slug():
    while True:
        slug = secrets.token_hex(4)
        if not Restaurant.query.filter_by(slug=slug).first():
            return slug


PLAN_TABLE_LIMITS = {"starter": 10, "growth": 25, "pro": 9999}
PLAN_PRICES = {"starter": 99, "growth": 199, "pro": 349}
# Map each plan to a Stripe Price ID (create these in your Stripe Dashboard under
# Product Catalog, then set them as environment variables). Falls back to empty
# strings in demo mode, which is fine since demo mode never calls the real API.
PLAN_STRIPE_PRICE_IDS = {
    "starter": os.environ.get('STRIPE_PRICE_STARTER', ''),
    "growth": os.environ.get('STRIPE_PRICE_GROWTH', ''),
    "pro": os.environ.get('STRIPE_PRICE_PRO', ''),
}


def get_table_assignee(restaurant_id, table_number):
    """
    Look up which waiter owns this table (their section) so new orders/requests
    for this table can be auto-assigned to them immediately - no claiming race
    needed. Returns None if the table isn't assigned to anyone yet, in which case
    it falls back to the open "first to claim" system.
    """
    t = Table.query.filter_by(restaurant_id=restaurant_id, number=str(table_number)).first()
    return t.assigned_to if t and t.assigned_to else None


# ---------------------------------------------------------------------------
# PUBLIC / AUTH ROUTES
# ---------------------------------------------------------------------------

@app.route('/')
def landing():
    if current_restaurant():
        return redirect(url_for('admin'))
    return render_template('landing.html', plan_prices=PLAN_PRICES)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        plan = request.form.get('plan', 'starter')

        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template('signup.html', plan_prices=PLAN_PRICES)

        if Restaurant.query.filter_by(owner_email=email).first():
            flash("An account with that email already exists. Please log in.", "error")
            return render_template('signup.html', plan_prices=PLAN_PRICES)

        r = Restaurant(
            slug=gen_slug(), name=name, owner_email=email, plan=plan,
            billing_status="trialing",
            trial_ends_at=datetime.utcnow() + timedelta(days=TRIAL_DAYS),
        )
        r.set_password(password)
        db.session.add(r)
        db.session.commit()

        # seed a couple of demo tables and menu items so the dashboard isn't empty
        for n in ["1", "2", "3"]:
            db.session.add(Table(restaurant_id=r.id, number=n))
        # needs_prep=True -> kitchen must cook/make it (refill goes through kitchen flow)
        # needs_prep=False -> already available/stocked (refill goes straight to runner)
        demo_items = [
            ("Garlic Bread", "Starters", 6.50, "Toasted with garlic butter", True),
            ("Caesar Salad", "Starters", 8.00, "Romaine, parmesan, croutons", True),
            ("Margherita Pizza", "Main Course", 13.50, "Tomato, mozzarella, basil", True),
            ("Grilled Chicken", "Main Course", 15.00, "Served with seasonal veg", True),
            ("Iced Tea", "Beverages", 3.50, "Freshly brewed, served over ice", False),
            ("Water (Still/Sparkling)", "Beverages", 0.00, "Complimentary refill", False),
            ("Chocolate Cake", "Desserts", 7.00, "Warm with vanilla ice cream", True),
        ]
        for nm, cat, price, desc, needs_prep in demo_items:
            db.session.add(MenuItem(
                restaurant_id=r.id, name=nm, category=cat, price=price,
                description=desc, needs_prep=needs_prep,
            ))
        db.session.commit()

        session['restaurant_id'] = r.id
        flash("Account created! This is your dashboard.", "success")
        return redirect(url_for('admin'))

    return render_template('signup.html', plan_prices=PLAN_PRICES)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        r = Restaurant.query.filter_by(owner_email=email).first()
        if r and r.check_password(password):
            session['restaurant_id'] = r.id
            return redirect(url_for('admin'))
        flash("Invalid email or password.", "error")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('restaurant_id', None)
    return redirect(url_for('landing'))


# ---------------------------------------------------------------------------
# ADMIN
# ---------------------------------------------------------------------------

@app.route('/admin')
@login_required
def admin():
    r = current_restaurant()
    items = MenuItem.query.filter_by(restaurant_id=r.id).order_by(MenuItem.category, MenuItem.name).all()
    tables = Table.query.filter_by(restaurant_id=r.id).order_by(Table.number).all()

    today = datetime.utcnow().date()
    today_orders = [o for o in r.orders if o.created_at.date() == today]
    today_revenue = sum(o.total() for o in today_orders)

    table_qrs = []
    base_url = request.url_root.rstrip('/')
    for t in tables:
        order_url = f"{base_url}/order/{r.slug}/{t.number}"
        table_qrs.append({
            "table": t,
            "url": order_url,
            "qr_b64": make_qr_base64(order_url),
        })

    # Quick "top sellers today" widget for the main dashboard
    today_order_ids = [o.id for o in today_orders]
    top_items_today = []
    if today_order_ids:
        today_stats = {}
        for oi in OrderItem.query.filter(OrderItem.order_id.in_(today_order_ids)).all():
            base_name = _normalize_item_name(oi.name)
            s = today_stats.setdefault(base_name, {"name": base_name, "total_quantity": 0})
            s["total_quantity"] += oi.quantity
        top_items_today = sorted(today_stats.values(), key=lambda s: s["total_quantity"], reverse=True)[:5]

    return render_template(
        'admin.html', r=r, items=items, tables=table_qrs,
        today_count=len(today_orders), today_revenue=today_revenue,
        table_limit=PLAN_TABLE_LIMITS.get(r.plan, 10),
        plan_prices=PLAN_PRICES, top_items_today=top_items_today,
        billing_state=get_billing_state(r),
    )


def _normalize_item_name(name):
    """Group 'Margherita Pizza' and 'Margherita Pizza (refill)' together as the
    same menu item for reporting purposes."""
    return name.replace(" (refill)", "").strip()


@app.route('/admin/analytics')
@login_required
def admin_analytics():
    r = current_restaurant()
    period = request.args.get('period', 'today')  # today / week / all
    now = datetime.utcnow()

    if period == 'today':
        cutoff = datetime(now.year, now.month, now.day)
        period_label = "Today"
    elif period == 'week':
        cutoff = now - timedelta(days=7)
        period_label = "Last 7 Days"
    else:
        cutoff = None
        period_label = "All Time"

    order_query = Order.query.filter_by(restaurant_id=r.id)
    if cutoff:
        order_query = order_query.filter(Order.created_at >= cutoff)
    orders_in_period = order_query.all()
    order_ids = [o.id for o in orders_in_period]

    # Aggregate by normalized item name: total quantity ordered, number of separate
    # orders it appeared in, revenue generated, and how many of those were refills.
    stats = {}
    if order_ids:
        order_items = OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).all()
        for oi in order_items:
            base_name = _normalize_item_name(oi.name)
            is_refill = "(refill)" in oi.name
            s = stats.setdefault(base_name, {
                "name": base_name, "total_quantity": 0, "order_count": 0,
                "revenue": 0.0, "refill_quantity": 0,
            })
            s["total_quantity"] += oi.quantity
            s["order_count"] += 1
            s["revenue"] += oi.price * oi.quantity
            if is_refill:
                s["refill_quantity"] += oi.quantity

    ranked = sorted(stats.values(), key=lambda s: s["total_quantity"], reverse=True)
    total_items_sold = sum(s["total_quantity"] for s in ranked)
    total_revenue = sum(s["revenue"] for s in ranked)

    # Menu items that exist but were never ordered in this period - useful for
    # spotting dead weight on the menu.
    all_item_names = {_normalize_item_name(i.name) for i in MenuItem.query.filter_by(restaurant_id=r.id).all()}
    ordered_names = set(stats.keys())
    never_ordered = sorted(all_item_names - ordered_names)

    return render_template(
        'analytics.html', r=r, ranked=ranked, period=period, period_label=period_label,
        total_items_sold=total_items_sold, total_revenue=total_revenue,
        order_count=len(orders_in_period), never_ordered=never_ordered,
    )


@app.route('/api/admin/analytics')
@login_required
def api_admin_analytics():
    """Same aggregation as above, as JSON - useful if you want to pull this into
    a spreadsheet or another tool later."""
    r = current_restaurant()
    period = request.args.get('period', 'today')
    now = datetime.utcnow()
    if period == 'today':
        cutoff = datetime(now.year, now.month, now.day)
    elif period == 'week':
        cutoff = now - timedelta(days=7)
    else:
        cutoff = None

    order_query = Order.query.filter_by(restaurant_id=r.id)
    if cutoff:
        order_query = order_query.filter(Order.created_at >= cutoff)
    order_ids = [o.id for o in order_query.all()]

    stats = {}
    if order_ids:
        order_items = OrderItem.query.filter(OrderItem.order_id.in_(order_ids)).all()
        for oi in order_items:
            base_name = _normalize_item_name(oi.name)
            s = stats.setdefault(base_name, {"name": base_name, "total_quantity": 0, "revenue": 0.0})
            s["total_quantity"] += oi.quantity
            s["revenue"] += oi.price * oi.quantity

    ranked = sorted(stats.values(), key=lambda s: s["total_quantity"], reverse=True)
    return jsonify(ranked)


@app.route('/admin/menu/add', methods=['POST'])
@login_required
@billing_required
def admin_menu_add():
    r = current_restaurant()
    item = MenuItem(
        restaurant_id=r.id,
        name=request.form.get('name', '').strip(),
        category=request.form.get('category', 'Main Course').strip() or "Main Course",
        price=float(request.form.get('price') or 0),
        description=request.form.get('description', '').strip(),
        needs_prep=(request.form.get('needs_prep') == 'yes'),
    )
    db.session.add(item)
    db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/menu/<int:item_id>/toggle_prep', methods=['POST'])
@login_required
def admin_menu_toggle_prep(item_id):
    r = current_restaurant()
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=r.id).first_or_404()
    item.needs_prep = not item.needs_prep
    db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/menu/<int:item_id>/toggle', methods=['POST'])
@login_required
def admin_menu_toggle(item_id):
    r = current_restaurant()
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=r.id).first_or_404()
    item.available = not item.available
    db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/menu/<int:item_id>/delete', methods=['POST'])
@login_required
def admin_menu_delete(item_id):
    r = current_restaurant()
    item = MenuItem.query.filter_by(id=item_id, restaurant_id=r.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/table/add', methods=['POST'])
@login_required
@billing_required
def admin_table_add():
    r = current_restaurant()
    existing = Table.query.filter_by(restaurant_id=r.id).count()
    limit = PLAN_TABLE_LIMITS.get(r.plan, 10)
    if existing >= limit:
        flash(f"Your {r.plan} plan allows up to {limit} tables. Upgrade to add more.", "error")
        return redirect(url_for('admin'))
    number = request.form.get('number', '').strip()
    if number:
        db.session.add(Table(restaurant_id=r.id, number=number))
        db.session.commit()
    return redirect(url_for('admin'))


@app.route('/admin/table/<int:table_id>/delete', methods=['POST'])
@login_required
def admin_table_delete(table_id):
    r = current_restaurant()
    t = Table.query.filter_by(id=table_id, restaurant_id=r.id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for('admin'))


# ---------------------------------------------------------------------------
# TABLE SECTIONS (which waiter owns which tables for this shift)
# ---------------------------------------------------------------------------

@app.route('/sections')
@login_required
def sections():
    r = current_restaurant()
    tables = Table.query.filter_by(restaurant_id=r.id).order_by(Table.number).all()
    return render_template('sections.html', r=r, tables=tables)


@app.route('/api/sections')
@login_required
def api_sections():
    r = current_restaurant()
    tables = Table.query.filter_by(restaurant_id=r.id).order_by(Table.number).all()
    return jsonify([{"id": t.id, "number": t.number, "assigned_to": t.assigned_to} for t in tables])


@app.route('/api/sections/<int:table_id>/assign', methods=['POST'])
@login_required
def api_section_assign(table_id):
    r = current_restaurant()
    t = Table.query.filter_by(id=table_id, restaurant_id=r.id).first_or_404()
    name = (request.json.get('name') or '').strip()[:60]
    t.assigned_to = name if name else None
    db.session.commit()
    return jsonify({"ok": True, "assigned_to": t.assigned_to})


@app.route('/api/sections/bulk_assign', methods=['POST'])
@login_required
def api_section_bulk_assign():
    """
    Assign ALL currently-selected tables to one waiter in a single click - this is
    the normal way sections should be set up (e.g. "Priya covers tables 1-20"),
    since one runner now covers many tables at once instead of the old 1-waiter-
    per-5-tables ratio.
    """
    r = current_restaurant()
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()[:60]
    table_ids = data.get('table_ids', [])
    if not name or not table_ids:
        return jsonify({"error": "Name and at least one table required"}), 400

    updated = Table.query.filter(
        Table.restaurant_id == r.id, Table.id.in_(table_ids)
    ).update({"assigned_to": name}, synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True, "updated_count": updated})


@app.route('/api/sections/clear_all', methods=['POST'])
@login_required
def api_sections_clear_all():
    """End-of-shift reset: clear all table assignments at once."""
    r = current_restaurant()
    Table.query.filter_by(restaurant_id=r.id).update({"assigned_to": None})
    db.session.commit()
    return jsonify({"ok": True})


@app.route('/admin/profile', methods=['POST'])
@login_required
def admin_profile():
    r = current_restaurant()
    r.name = request.form.get('name', r.name).strip() or r.name
    r.logo_emoji = request.form.get('logo_emoji', r.logo_emoji).strip() or r.logo_emoji
    r.color_theme = request.form.get('color_theme', r.color_theme)
    db.session.commit()
    flash("Profile updated.", "success")
    return redirect(url_for('admin'))


@app.route('/admin/plan', methods=['POST'])
@login_required
def admin_plan():
    """
    Kept for backward compatibility with the old plan-selector on the Admin page,
    but now redirects into the real billing flow instead of silently switching
    plans with no payment attached.
    """
    plan = request.form.get('plan')
    return redirect(url_for('billing_checkout', plan=plan))


# ---------------------------------------------------------------------------
# BILLING / SUBSCRIPTIONS
#
# Handles: 14-day free trial, upgrading to a paid plan (via Stripe Checkout in
# live mode, or a simulated instant-activate in demo mode), viewing payment
# history, canceling, and Stripe webhooks that keep billing_status in sync
# automatically when a real payment succeeds, fails, or a subscription ends.
# ---------------------------------------------------------------------------

@app.route('/billing')
@login_required
def billing():
    r = current_restaurant()
    state = get_billing_state(r)
    payments = Payment.query.filter_by(restaurant_id=r.id).order_by(Payment.created_at.desc()).all()
    return render_template(
        'billing.html', r=r, state=state, plan_prices=PLAN_PRICES,
        payments=payments, demo_mode=DEMO_MODE,
    )


def _get_or_create_stripe_customer(r):
    if r.stripe_customer_id:
        return r.stripe_customer_id
    customer = stripe.Customer.create(email=r.owner_email, name=r.name, metadata={"restaurant_id": r.id})
    r.stripe_customer_id = customer.id
    db.session.commit()
    return customer.id


@app.route('/billing/checkout/<plan>')
@login_required
def billing_checkout(plan):
    r = current_restaurant()
    if plan not in PLAN_PRICES:
        flash("Unknown plan selected.", "error")
        return redirect(url_for('billing'))

    if DEMO_MODE:
        # No live payment provider configured - simulate a successful checkout
        # so you can test the full billing lifecycle (trial -> active -> plan
        # changes -> cancel) without a real Stripe/Dodo Payments account yet.
        r.plan = plan
        r.billing_status = "active"
        r.payment_failed_at = None
        r.current_period_end = datetime.utcnow() + timedelta(days=30)
        db.session.add(Payment(
            restaurant_id=r.id, amount=PLAN_PRICES[plan], status="succeeded",
            plan=plan, stripe_event_id="demo_mode",
        ))
        db.session.commit()
        flash(f"[Demo Mode] Subscribed to {plan.title()} (${PLAN_PRICES[plan]}/month). "
              f"No real charge was made - set STRIPE_SECRET_KEY to enable real payments.", "success")
        return redirect(url_for('billing'))

    if not STRIPE_AVAILABLE:
        flash("Payment processing is not available right now. Please try again later.", "error")
        return redirect(url_for('billing'))

    price_id = PLAN_STRIPE_PRICE_IDS.get(plan)
    if not price_id:
        flash(f"The {plan} plan is not fully configured for payments yet.", "error")
        return redirect(url_for('billing'))

    customer_id = _get_or_create_stripe_customer(r)
    base_url = request.url_root.rstrip('/')
    checkout_session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}/billing?checkout=success",
        cancel_url=f"{base_url}/billing?checkout=canceled",
        metadata={"restaurant_id": r.id, "plan": plan},
    )
    return redirect(checkout_session.url, code=303)


@app.route('/billing/cancel', methods=['POST'])
@login_required
def billing_cancel():
    r = current_restaurant()

    if DEMO_MODE or not r.stripe_subscription_id:
        r.billing_status = "canceled"
        db.session.commit()
        flash("Subscription canceled. You can resubscribe anytime.", "success")
        return redirect(url_for('billing'))

    stripe.Subscription.delete(r.stripe_subscription_id)
    r.billing_status = "canceled"
    db.session.commit()
    flash("Subscription canceled. You can resubscribe anytime.", "success")
    return redirect(url_for('billing'))


@app.route('/billing/simulate_failed_payment', methods=['POST'])
@login_required
def billing_simulate_failed_payment():
    """
    Demo-mode-only helper so you can test the grace-period / dunning behavior
    without waiting for a real card to actually fail. Not exposed in live mode.
    """
    if not DEMO_MODE:
        return jsonify({"error": "Only available in demo mode"}), 403
    r = current_restaurant()
    r.billing_status = "past_due"
    r.payment_failed_at = datetime.utcnow()
    db.session.add(Payment(restaurant_id=r.id, amount=PLAN_PRICES.get(r.plan, 0), status="failed", plan=r.plan))
    db.session.commit()
    flash("[Demo Mode] Simulated a failed payment. You now have a "
          f"{GRACE_PERIOD_DAYS}-day grace period before service-critical screens lock.", "error")
    return redirect(url_for('billing'))


@app.route('/billing/simulate_recover_payment', methods=['POST'])
@login_required
def billing_simulate_recover_payment():
    """Demo-mode helper: simulate the customer fixing their card and the retry succeeding."""
    if not DEMO_MODE:
        return jsonify({"error": "Only available in demo mode"}), 403
    r = current_restaurant()
    r.billing_status = "active"
    r.payment_failed_at = None
    r.current_period_end = datetime.utcnow() + timedelta(days=30)
    db.session.add(Payment(restaurant_id=r.id, amount=PLAN_PRICES.get(r.plan, 0), status="succeeded", plan=r.plan))
    db.session.commit()
    flash("[Demo Mode] Payment recovered - subscription is active again.", "success")
    return redirect(url_for('billing'))


@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    """
    Real-time sync point: Stripe calls this URL whenever something happens on
    their side (a charge succeeds, a charge fails, a subscription is canceled,
    etc.) so billing_status always reflects reality even if the customer never
    comes back to the app after paying/failing.
    """
    if not STRIPE_AVAILABLE or DEMO_MODE:
        return jsonify({"error": "Webhooks not active in demo mode"}), 400

    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400

    data = event['data']['object']
    event_type = event['type']

    restaurant_id = None
    if data.get('metadata', {}).get('restaurant_id'):
        restaurant_id = int(data['metadata']['restaurant_id'])
    elif data.get('customer'):
        r_lookup = Restaurant.query.filter_by(stripe_customer_id=data['customer']).first()
        restaurant_id = r_lookup.id if r_lookup else None

    r = Restaurant.query.get(restaurant_id) if restaurant_id else None

    if event_type == 'checkout.session.completed' and r:
        r.stripe_subscription_id = data.get('subscription')
        r.billing_status = "active"
        r.payment_failed_at = None
        plan = data.get('metadata', {}).get('plan')
        if plan in PLAN_PRICES:
            r.plan = plan
        db.session.add(Payment(
            restaurant_id=r.id, amount=(data.get('amount_total') or 0) / 100,
            status="succeeded", plan=r.plan, stripe_event_id=event['id'],
        ))
        db.session.commit()

    elif event_type == 'invoice.payment_succeeded' and r:
        r.billing_status = "active"
        r.payment_failed_at = None
        r.current_period_end = datetime.utcnow() + timedelta(days=30)
        db.session.add(Payment(
            restaurant_id=r.id, amount=(data.get('amount_paid') or 0) / 100,
            status="succeeded", plan=r.plan, stripe_event_id=event['id'],
        ))
        db.session.commit()

    elif event_type == 'invoice.payment_failed' and r:
        r.billing_status = "past_due"
        r.payment_failed_at = datetime.utcnow()
        db.session.add(Payment(
            restaurant_id=r.id, amount=(data.get('amount_due') or 0) / 100,
            status="failed", plan=r.plan, stripe_event_id=event['id'],
        ))
        db.session.commit()

    elif event_type in ('customer.subscription.deleted',) and r:
        r.billing_status = "canceled"
        db.session.commit()

    return jsonify({"received": True})


# ---------------------------------------------------------------------------
# CUSTOMER ORDER FLOW (public, no login)
# ---------------------------------------------------------------------------

@app.route('/order/<slug>/<table_number>')
def customer_order(slug, table_number):
    r = Restaurant.query.filter_by(slug=slug).first_or_404()
    items = MenuItem.query.filter_by(restaurant_id=r.id, available=True).order_by(MenuItem.category, MenuItem.name).all()
    categories = []
    seen = set()
    for i in items:
        if i.category not in seen:
            categories.append(i.category)
            seen.add(i.category)
    return render_template('order.html', r=r, items=items, categories=categories, table_number=table_number)


@app.route('/order/<slug>/<table_number>/place', methods=['POST'])
def place_order(slug, table_number):
    r = Restaurant.query.filter_by(slug=slug).first_or_404()
    data = request.get_json()
    cart = data.get('cart', [])
    if not cart:
        return jsonify({"error": "Cart is empty"}), 400

    assignee = get_table_assignee(r.id, table_number)
    # placed_by_name is only sent by the staff-assisted ordering screen (see
    # /take-order below) - regular customer QR orders never send this field.
    staff_name = (data.get('staff_name') or '').strip()[:60]
    order = Order(
        restaurant_id=r.id, table_number=table_number, status="received",
        claimed_by=assignee, placed_by="staff" if staff_name else "customer",
        placed_by_name=staff_name or None,
    )
    db.session.add(order)
    db.session.flush()

    for line in cart:
        menu_item = MenuItem.query.filter_by(id=line['id'], restaurant_id=r.id).first()
        if not menu_item:
            continue
        db.session.add(OrderItem(
            order_id=order.id,
            name=menu_item.name,
            price=menu_item.price,
            quantity=int(line.get('quantity', 1)),
            note=line.get('note', '')[:255],
        ))
    db.session.commit()
    return jsonify({"order_id": order.id})


@app.route('/order/status/<int:order_id>')
def order_status_page(order_id):
    order = Order.query.get_or_404(order_id)
    r = Restaurant.query.get(order.restaurant_id)
    return render_template(
        'order_status.html', order=order, r=r,
        table_number=order.table_number, request_types=REQUEST_TYPES,
    )


@app.route('/api/order/<int:order_id>')
def api_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    return jsonify(order.to_dict())


# ---------------------------------------------------------------------------
# SERVICE REQUESTS (refills, napkins, assistance, check) - bypasses kitchen,
# goes straight to the runner since these don't need cooking/wait time.
# ---------------------------------------------------------------------------

@app.route('/request/<slug>/<table_number>')
def request_page(slug, table_number):
    r = Restaurant.query.filter_by(slug=slug).first_or_404()
    items = MenuItem.query.filter_by(restaurant_id=r.id, available=True).order_by(MenuItem.category, MenuItem.name).all()
    return render_template(
        'request.html', r=r, table_number=table_number, request_types=REQUEST_TYPES, items=items,
    )


@app.route('/api/reorder/<slug>/<table_number>', methods=['POST'])
def api_reorder_item(slug, table_number):
    """
    Customer wants "more of" a specific menu item they already had (e.g. another
    Coke, another basket of fries). This is the core routing logic:
      - If the item needs kitchen prep (needs_prep=True): create a real Order that
        flows through the normal kitchen -> wait time -> ready -> runner pipeline,
        exactly like a fresh order, because the kitchen genuinely has to make it.
      - If the item does NOT need prep (needs_prep=False, e.g. water, fountain soda,
        bread basket): skip the kitchen entirely and send it straight to the runner
        as an instant service request, since it's already available to grab.
    """
    r = Restaurant.query.filter_by(slug=slug).first_or_404()
    data = request.get_json() or {}
    item_id = data.get('item_id')
    quantity = int(data.get('quantity', 1))

    menu_item = MenuItem.query.filter_by(id=item_id, restaurant_id=r.id).first()
    if not menu_item:
        return jsonify({"error": "Item not found"}), 404

    assignee = get_table_assignee(r.id, table_number)

    if menu_item.needs_prep:
        # Route through the kitchen, same as a normal order
        order = Order(restaurant_id=r.id, table_number=table_number, status="received", claimed_by=assignee)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(
            order_id=order.id, name=f"{menu_item.name} (refill)",
            price=menu_item.price, quantity=quantity, note="Customer requested a refill",
        ))
        db.session.commit()
        return jsonify({"ok": True, "routed_to": "kitchen", "order_id": order.id})
    else:
        # Instant item - skip kitchen, go straight to runner
        req = ServiceRequest(
            restaurant_id=r.id, table_number=table_number, request_type="item_refill",
            note=f"{quantity}x {menu_item.name}", claimed_by=assignee,
        )
        db.session.add(req)
        db.session.commit()
        return jsonify({"ok": True, "routed_to": "runner", "request_id": req.id})


@app.route('/api/request/<slug>/<table_number>/send', methods=['POST'])
def api_send_request(slug, table_number):
    r = Restaurant.query.filter_by(slug=slug).first_or_404()
    data = request.get_json() or {}
    rtype = data.get('type', 'assistance')
    if rtype not in REQUEST_TYPES:
        rtype = 'custom'
    note = (data.get('note') or '').strip()[:255]

    # Avoid spamming duplicate open requests of the same type from the same table
    existing = ServiceRequest.query.filter_by(
        restaurant_id=r.id, table_number=table_number, request_type=rtype, status="open"
    ).first()
    if existing:
        return jsonify({"ok": True, "request_id": existing.id, "duplicate": True})

    assignee = get_table_assignee(r.id, table_number)
    req = ServiceRequest(restaurant_id=r.id, table_number=table_number, request_type=rtype, note=note, claimed_by=assignee)
    db.session.add(req)
    db.session.commit()
    return jsonify({"ok": True, "request_id": req.id})


@app.route('/api/runner/requests')
@login_required
def api_runner_requests():
    r = current_restaurant()
    reqs = ServiceRequest.query.filter_by(restaurant_id=r.id, status="open").order_by(ServiceRequest.created_at.asc()).all()
    return jsonify([q.to_dict() for q in reqs])


@app.route('/api/request/<int:request_id>/resolve', methods=['POST'])
@login_required
def api_resolve_request(request_id):
    r = current_restaurant()
    req = ServiceRequest.query.filter_by(id=request_id, restaurant_id=r.id).first_or_404()
    req.status = "resolved"
    req.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# KITCHEN DASHBOARD
# ---------------------------------------------------------------------------

@app.route('/kitchen')
@login_required
@service_critical_required
def kitchen():
    r = current_restaurant()
    return render_template('kitchen.html', r=r)


@app.route('/api/kitchen/orders')
@login_required
def api_kitchen_orders():
    r = current_restaurant()
    orders = Order.query.filter(
        Order.restaurant_id == r.id,
        Order.status.in_(["received", "preparing"])
    ).order_by(Order.created_at.asc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route('/api/order/<int:order_id>/prepare', methods=['POST'])
@login_required
def api_order_prepare(order_id):
    r = current_restaurant()
    order = Order.query.filter_by(id=order_id, restaurant_id=r.id).first_or_404()
    minutes = int(request.json.get('minutes', 10))
    order.status = "preparing"
    order.wait_minutes = minutes
    order.prepare_started_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@app.route('/api/order/<int:order_id>/ready', methods=['POST'])
@login_required
def api_order_ready(order_id):
    r = current_restaurant()
    order = Order.query.filter_by(id=order_id, restaurant_id=r.id).first_or_404()
    order.status = "ready"
    order.ready_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# RUNNER / WAITER SCREEN
# ---------------------------------------------------------------------------

@app.route('/runner')
@login_required
@service_critical_required
def runner():
    r = current_restaurant()
    return render_template('runner.html', r=r)


# ---------------------------------------------------------------------------
# STAFF-ASSISTED ORDERING
#
# For customers who cannot or do not want to use the QR/phone ordering flow -
# elderly guests, anyone without a smartphone, a dead battery, accessibility
# needs, or simply a preference for human service. A staff member takes the
# order verbally, exactly like traditional table service, and enters it here.
# It then flows through the IDENTICAL kitchen-bell/wait-time/runner pipeline
# as a self-service order - the restaurant never loses the speed/labor
# benefits of the system just because one table needs a human touch.
# ---------------------------------------------------------------------------

@app.route('/take-order')
@login_required
@service_critical_required
def take_order():
    r = current_restaurant()
    tables = Table.query.filter_by(restaurant_id=r.id).order_by(Table.number).all()
    items = MenuItem.query.filter_by(restaurant_id=r.id, available=True).order_by(MenuItem.category, MenuItem.name).all()
    categories = []
    seen = set()
    for i in items:
        if i.category not in seen:
            categories.append(i.category)
            seen.add(i.category)
    return render_template('take_order.html', r=r, tables=tables, items=items, categories=categories)


@app.route('/api/take-order/place', methods=['POST'])
@login_required
def api_take_order_place():
    r = current_restaurant()
    data = request.get_json() or {}
    table_number = (data.get('table_number') or '').strip()
    staff_name = (data.get('staff_name') or '').strip()[:60]
    cart = data.get('cart', [])

    if not table_number:
        return jsonify({"error": "Table number required"}), 400
    if not cart:
        return jsonify({"error": "Cart is empty"}), 400
    if not staff_name:
        return jsonify({"error": "Staff name required"}), 400

    assignee = get_table_assignee(r.id, table_number) or staff_name
    order = Order(
        restaurant_id=r.id, table_number=table_number, status="received",
        claimed_by=assignee, placed_by="staff", placed_by_name=staff_name,
    )
    db.session.add(order)
    db.session.flush()

    for line in cart:
        menu_item = MenuItem.query.filter_by(id=line['id'], restaurant_id=r.id).first()
        if not menu_item:
            continue
        db.session.add(OrderItem(
            order_id=order.id, name=menu_item.name, price=menu_item.price,
            quantity=int(line.get('quantity', 1)), note=line.get('note', '')[:255],
        ))
    db.session.commit()
    return jsonify({"ok": True, "order_id": order.id})


@app.route('/api/runner/orders')
@login_required
def api_runner_orders():
    r = current_restaurant()
    orders = Order.query.filter_by(restaurant_id=r.id, status="ready").order_by(Order.ready_at.asc()).all()
    return jsonify([o.to_dict() for o in orders])


@app.route('/api/order/<int:order_id>/delivered', methods=['POST'])
@login_required
def api_order_delivered(order_id):
    r = current_restaurant()
    order = Order.query.filter_by(id=order_id, restaurant_id=r.id).first_or_404()
    order.status = "delivered"
    db.session.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# CLAIMING (so when multiple waiters/runners get the same alert, only one of
# them handles it - prevents duplicate trips and "who's got table 5?" confusion)
# ---------------------------------------------------------------------------

@app.route('/api/order/<int:order_id>/claim', methods=['POST'])
@login_required
def api_order_claim(order_id):
    r = current_restaurant()
    name = (request.json.get('name') or '').strip()[:60]
    if not name:
        return jsonify({"error": "Name required"}), 400

    # Atomic claim: only succeeds if nobody has claimed it yet (claimed_by IS NULL).
    # This prevents two waiters tapping "Claim" at the same instant from both winning.
    updated = db.session.query(Order).filter(
        Order.id == order_id, Order.restaurant_id == r.id, Order.claimed_by.is_(None)
    ).update({"claimed_by": name, "claimed_at": datetime.utcnow()})
    db.session.commit()

    order = Order.query.filter_by(id=order_id, restaurant_id=r.id).first_or_404()
    return jsonify({"ok": bool(updated), "claimed_by": order.claimed_by})


@app.route('/api/order/<int:order_id>/unclaim', methods=['POST'])
@login_required
def api_order_unclaim(order_id):
    r = current_restaurant()
    order = Order.query.filter_by(id=order_id, restaurant_id=r.id).first_or_404()
    order.claimed_by = None
    order.claimed_at = None
    db.session.commit()
    return jsonify({"ok": True})


@app.route('/api/order/<int:order_id>/takeover', methods=['POST'])
@login_required
def api_order_takeover(order_id):
    """Force-claim even if someone else already has it - for when the first
    person got stuck/busy and someone else needs to pick it up instead."""
    r = current_restaurant()
    name = (request.json.get('name') or '').strip()[:60]
    if not name:
        return jsonify({"error": "Name required"}), 400
    order = Order.query.filter_by(id=order_id, restaurant_id=r.id).first_or_404()
    order.claimed_by = name
    order.claimed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "claimed_by": order.claimed_by})


@app.route('/api/request/<int:request_id>/claim', methods=['POST'])
@login_required
def api_request_claim(request_id):
    r = current_restaurant()
    name = (request.json.get('name') or '').strip()[:60]
    if not name:
        return jsonify({"error": "Name required"}), 400

    updated = db.session.query(ServiceRequest).filter(
        ServiceRequest.id == request_id, ServiceRequest.restaurant_id == r.id,
        ServiceRequest.claimed_by.is_(None)
    ).update({"claimed_by": name, "claimed_at": datetime.utcnow()})
    db.session.commit()

    req = ServiceRequest.query.filter_by(id=request_id, restaurant_id=r.id).first_or_404()
    return jsonify({"ok": bool(updated), "claimed_by": req.claimed_by})


@app.route('/api/request/<int:request_id>/unclaim', methods=['POST'])
@login_required
def api_request_unclaim(request_id):
    r = current_restaurant()
    req = ServiceRequest.query.filter_by(id=request_id, restaurant_id=r.id).first_or_404()
    req.claimed_by = None
    req.claimed_at = None
    db.session.commit()
    return jsonify({"ok": True})


@app.route('/api/request/<int:request_id>/takeover', methods=['POST'])
@login_required
def api_request_takeover(request_id):
    r = current_restaurant()
    name = (request.json.get('name') or '').strip()[:60]
    if not name:
        return jsonify({"error": "Name required"}), 400
    req = ServiceRequest.query.filter_by(id=request_id, restaurant_id=r.id).first_or_404()
    req.claimed_by = name
    req.claimed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "claimed_by": req.claimed_by})


# ---------------------------------------------------------------------------
# DB INIT
# ---------------------------------------------------------------------------

with app.app_context():
    db.create_all()


if __name__ == '__main__':
    # FLASK_DEBUG=1 for local development only. Never enable debug mode on a
    # live/public deployment - it can expose sensitive internals if something
    # crashes. Render/Railway/production should NOT set FLASK_DEBUG.
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

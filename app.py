from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone, timedelta
import random
import string
import hashlib
import os
from functools import wraps
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv

# Load environment variables from .env file (local dev only)
load_dotenv()
from export_reports import (
    export_all_shipments, 
    export_outgoing_shipments, 
    export_incoming_shipments,
    export_delivered_shipments,
    export_pending_shipments,
    export_customers
)

app = Flask(__name__)
app.secret_key = 'deejohnson_super_secret_key_2024'

# ============================================
# DATABASE CONFIGURATION
# ============================================
if os.environ.get('DATABASE_URL'):
    database_url = os.environ.get('DATABASE_URL')
    # Convert old postgres:// to postgresql+psycopg2://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    elif database_url.startswith('postgresql://') and '+psycopg2' not in database_url:
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("=" * 50)
    print("✅ USING POSTGRESQL DATABASE (via psycopg2)")
    print("=" * 50)
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///logistics.db'
    print("=" * 50)
    print("✅ USING SQLITE DATABASE (Local development)")
    print("=" * 50)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ============================================
# DATABASE MODELS
# ============================================

class Shipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_code = db.Column(db.String(20), unique=True, nullable=False)
    customer_name = db.Column(db.String(100))
    customer_email = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    origin = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    package_type = db.Column(db.String(50))
    package_weight = db.Column(db.Float, default=0)
    status = db.Column(db.String(200))
    current_location = db.Column(db.String(100))
    last_update = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    partner_courier = db.Column(db.String(50))
    partner_tracking = db.Column(db.String(50))
    notes = db.Column(db.Text)
    notification_sent = db.Column(db.Boolean, default=False)
    
    # For incoming shipments
    shipment_direction = db.Column(db.String(20), default='outgoing')
    origin_country = db.Column(db.String(50))
    origin_city = db.Column(db.String(100))
    partner_courier_original = db.Column(db.String(50))
    partner_tracking_original = db.Column(db.String(50))
    expected_arrival_date = db.Column(db.String(100))
    customs_status = db.Column(db.String(50), default='pending')
    delivery_address = db.Column(db.String(200))


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    location = db.Column(db.String(50))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_code = db.Column(db.String(20))
    customer_email = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    sent_via = db.Column(db.String(20))


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    city = db.Column(db.String(50))
    state = db.Column(db.String(50))
    total_shipments = db.Column(db.Integer, default=0)
    total_spent = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    first_shipment = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_shipment = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)


class Rider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100))
    password_hash = db.Column(db.String(200), nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    approved_at = db.Column(db.DateTime)
    current_lat = db.Column(db.Float)
    current_lng = db.Column(db.Float)
    last_location_update = db.Column(db.DateTime)

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rider_id = db.Column(db.Integer, db.ForeignKey('rider.id'), nullable=False)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(300), nullable=False)
    auth = db.Column(db.String(100), nullable=False)
    user_agent = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_used_at = db.Column(db.DateTime)

    # Relationship
    rider = db.relationship('Rider', backref='push_subscriptions')    

class DeliveryTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rider_id = db.Column(db.Integer, db.ForeignKey('rider.id'), nullable=False)
    shipment_id = db.Column(db.Integer, db.ForeignKey('shipment.id'), nullable=False)
    status = db.Column(db.String(30), default='assigned')  # assigned, picked_up, in_transit, delivered, failed
    assigned_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    picked_up_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    photo_proof = db.Column(db.String(300))

    # Relationships
    rider = db.relationship('Rider', backref='delivery_tasks')
    shipment = db.relationship('Shipment', backref='delivery_tasks')

# ============================================
# COURIER INTEGRATION FUNCTIONS
# ============================================

def detect_courier(tracking_number):
    if not tracking_number:
        return 'Unknown'
    tracking_number = str(tracking_number).upper().strip()
    if len(tracking_number) >= 12 and len(tracking_number) <= 15 and tracking_number.isdigit():
        return 'FedEx'
    if len(tracking_number) >= 10 and len(tracking_number) <= 11 and tracking_number.isdigit():
        return 'DHL'
    if len(tracking_number) >= 10 and len(tracking_number) <= 12 and tracking_number.isdigit():
        return 'DPD'
    if (len(tracking_number) >= 20 and len(tracking_number) <= 22 and tracking_number.isdigit()) or \
       (len(tracking_number) == 13 and tracking_number.startswith('9')):
        return 'USPS'
    if (len(tracking_number) == 13 and 
        tracking_number[:2].isalpha() and 
        tracking_number[2:11].isdigit() and 
        tracking_number[11:13].isalpha()):
        return 'Royal Mail'
    if len(tracking_number) == 16 and tracking_number.startswith('8') and tracking_number.isdigit():
        return 'Royal Mail'
    if tracking_number.startswith('1Z') and len(tracking_number) == 18:
        return 'UPS'
    return 'Unknown'


def get_tracking_url(courier, tracking_number):
    if not courier or not tracking_number:
        return '#'
    urls = {
        'FedEx': f'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
        'DHL': f'https://www.dhl.com/global-en/home/tracking.html?tracking-id={tracking_number}',
        'DPD': f'https://track.dpd.co.uk/{tracking_number}',
        'USPS': f'https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking_number}',
        'Royal Mail': f'https://www.royalmail.com/track-your-item?trackNumber={tracking_number}',
        'UPS': f'https://www.ups.com/track?tracknum={tracking_number}'
    }
    return urls.get(courier, '#')


def get_courier_icon(courier):
    icons = {
        'FedEx': 'fa-solid fa-box',
        'DHL': 'fa-solid fa-truck-fast',
        'DPD': 'fa-solid fa-truck',
        'USPS': 'fa-solid fa-envelope',
        'Royal Mail': 'fa-solid fa-crown',
        'UPS': 'fa-solid fa-truck'
    }
    return icons.get(courier, 'fa-solid fa-globe')


def get_courier_color(courier):
    colors = {
        'FedEx': '#4B0082',
        'DHL': '#FFCC00',
        'DPD': '#E3000F',
        'USPS': '#004B87',
        'Royal Mail': '#C8102E',
        'UPS': '#351C15'
    }
    return colors.get(courier, '#0F3B5C')


# ============================================
# CREATE DATABASE AND SAMPLE DATA
# ============================================

with app.app_context():
    db.create_all()
    
    admin_exists = Admin.query.filter_by(username="admin").first()
    if not admin_exists:
        default_password = hashlib.sha256("admin123".encode()).hexdigest()
        admin = Admin(username="admin", password_hash=default_password)
        db.session.add(admin)
        db.session.commit()
        print("\n" + "=" * 50)
        print("✅ ADMIN ACCOUNT CREATED SUCCESSFULLY!")
        print("📝 LOGIN: admin / admin123")
        print("=" * 50 + "\n")
    
    if Review.query.count() == 0:
        sample_reviews = [
            Review(customer_name="Mr. Adebayo Ogunlesi", location="Ibadan", rating=5, 
                   comment="Excellent service! My package from Ibadan arrived quickly."),
            Review(customer_name="Mrs. Funmilayo Adeyemi", location="Oyo Town", rating=5, 
                   comment="Best logistics company in Oyo State. Very reliable!"),
            Review(customer_name="Chief Emeka Okonkwo", location="Ibadan", rating=4, 
                   comment="Professional clearing and forwarding. Will recommend."),
            Review(customer_name="Adebayo Emmanuel", location="Ogun State", rating=5, 
                   comment="DeeJohnson Company Logistics are really the best options for shipping."),       
        ]
        db.session.add_all(sample_reviews)
        db.session.commit()
        print("✅ Sample customer reviews added!")


# ============================================
# AUTH DECORATORS
# ============================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Please login to access the admin panel', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# HELPERS
# ============================================

def generate_tracking_code():
    year = datetime.now().year
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"DJL-{year}-{random_chars}"

# ============================================
# PUSH NOTIFICATION HELPERS
# ============================================

def get_vapid_keys():
    """Load VAPID keys from environment"""
    public_key = os.environ.get('VAPID_PUBLIC_KEY')
    private_key = os.environ.get('VAPID_PRIVATE_KEY')
    subject = os.environ.get('VAPID_SUBJECT', 'mailto:deejohnsonnigerialimited@gmail.com')
    return public_key, private_key, subject


def send_push_notification(rider_id, title, body, url='/dispatch_riders/dashboard'):
    """
    Send a push notification to all subscriptions for a given rider.
    Returns (success_count, failure_count).
    """
    public_key, private_key, subject = get_vapid_keys()

    if not public_key or not private_key:
        print("⚠️ VAPID keys missing — skipping push")
        return 0, 0

    subscriptions = PushSubscription.query.filter_by(rider_id=rider_id).all()

    if not subscriptions:
        print(f"⚠️ No push subscriptions for rider {rider_id}")
        return 0, 0

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "icon": "/static/images/icon-192.png",
        "badge": "/static/images/icon-192.png"
    }

    import json
    payload_json = json.dumps(payload)

    success = 0
    failed = 0

    for sub in subscriptions:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth
            }
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload_json,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject}
            )
            sub.last_used_at = datetime.now(timezone.utc)
            success += 1
            print(f"✅ Push sent to rider {rider_id} (sub {sub.id})")

        except WebPushException as e:
            failed += 1
            error_text = str(e)

            # If subscription is dead (404, 410), remove it
            if '410' in error_text or '404' in error_text:
                print(f"🗑️ Removing dead subscription {sub.id}")
                db.session.delete(sub)
            else:
                print(f"❌ Push failed for rider {rider_id}: {error_text}")

        except Exception as e:
            failed += 1
            print(f"❌ Push error for rider {rider_id}: {e}")

    try:
        db.session.commit()
    except Exception as e:
        print(f"⚠️ Could not commit push updates: {e}")
        db.session.rollback()

    return success, failed

# ============================================
# PUBLIC ROUTES
# ============================================

@app.route('/')
def index():
    reviews = Review.query.order_by(Review.id.desc()).limit(6).all()
    return render_template('index.html', reviews=reviews)


@app.route('/track', methods=['GET', 'POST'])
def track():
    shipment = None
    partner_url = None
    courier_icon = None
    courier_color = None
    
    if request.method == 'POST':
        code = request.form.get('tracking_code')
        shipment = Shipment.query.filter_by(tracking_code=code).first()
        
        if shipment and shipment.partner_courier and shipment.partner_tracking:
            partner_url = get_tracking_url(shipment.partner_courier, shipment.partner_tracking)
            courier_icon = get_courier_icon(shipment.partner_courier)
            courier_color = get_courier_color(shipment.partner_courier)
        
        if shipment and shipment.tracking_code.startswith('EXPDJL'):
            return render_template('express_track.html', 
                                 shipment=shipment, 
                                 partner_url=partner_url,
                                 courier_icon=courier_icon,
                                 courier_color=courier_color,
                                 get_tracking_url=get_tracking_url,
                                 get_courier_icon=get_courier_icon,
                                 get_courier_color=get_courier_color)
    
    return render_template('track.html', 
                         shipment=shipment, 
                         partner_url=partner_url,
                         courier_icon=courier_icon,
                         courier_color=courier_color,
                         get_tracking_url=get_tracking_url,
                         get_courier_icon=get_courier_icon,
                         get_courier_color=get_courier_color)


@app.route('/google79bcbfa2d09351d4.html')
def google_verify():
    from flask import send_from_directory
    return send_from_directory('static', 'google79bcbfa2d09351d4.html')


@app.route('/health')
def health():
    return "OK", 200


# ============================================
# ADMIN AUTH ROUTES
# ============================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    with app.app_context():
        if Admin.query.count() == 0:
            default_password = hashlib.sha256("admin123".encode()).hexdigest()
            admin = Admin(username="admin", password_hash=default_password)
            db.session.add(admin)
            db.session.commit()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        admin = Admin.query.filter_by(username=username).first()
        
        if admin:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if admin.password_hash == password_hash:
                session['admin_logged_in'] = True
                session['admin_username'] = username
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('admin'))
            else:
                flash('Invalid password!', 'danger')
        else:
            flash('Username not found!', 'danger')
    
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('admin_login'))


# ============================================
# MAIN ADMIN DASHBOARD
# ============================================

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_shipment':
            tracking_code = generate_tracking_code()
            new_shipment = Shipment(
                tracking_code=tracking_code,
                customer_name=request.form.get('customer_name'),
                customer_email=request.form.get('customer_email'),
                customer_phone=request.form.get('customer_phone'),
                origin=request.form.get('origin'),
                destination=request.form.get('destination'),
                package_type=request.form.get('package_type'),
                package_weight=float(request.form.get('package_weight', 0)),
                status='Package registered - Awaiting pickup',
                current_location=request.form.get('origin')
            )
            db.session.add(new_shipment)
            db.session.commit()
            flash(f'✅ Shipment created! Tracking Code: {tracking_code}', 'success')
            return redirect(url_for('admin'))
        
        elif action == 'update_status':
            tracking_code = request.form.get('tracking_code')
            shipment = Shipment.query.filter_by(tracking_code=tracking_code).first()
            
            if shipment:
                shipment.status = request.form.get('status')
                shipment.current_location = request.form.get('current_location')
                shipment.last_update = datetime.now(timezone.utc)
                shipment.notes = request.form.get('notes')
                
                partner = request.form.get('partner_courier', '')
                partner_code = request.form.get('partner_tracking', '')
                
                if partner and partner_code:
                    shipment.partner_courier = partner
                    shipment.partner_tracking = partner_code
                
                db.session.commit()
                flash(f'✅ Status updated for {tracking_code}', 'success')
            else:
                flash('❌ Tracking code not found!', 'danger')
        
        elif action == 'add_review':
            new_review = Review(
                customer_name=request.form.get('customer_name'),
                location=request.form.get('location'),
                rating=int(request.form.get('rating')),
                comment=request.form.get('comment')
            )
            db.session.add(new_review)
            db.session.commit()
            flash('✅ Customer review added!', 'success')
        
        elif action == 'delete_shipment':
            tracking_code = request.form.get('tracking_code')
            shipment = Shipment.query.filter_by(tracking_code=tracking_code).first()
            if shipment:
                db.session.delete(shipment)
                db.session.commit()
                flash(f'✅ Shipment {tracking_code} deleted!', 'success')
            else:
                flash('❌ Shipment not found!', 'danger')
        
        elif action == 'change_password':
            old_pass = request.form.get('old_password')
            new_pass = request.form.get('new_password')
            confirm_pass = request.form.get('confirm_password')
            admin = Admin.query.filter_by(username=session['admin_username']).first()
            old_hash = hashlib.sha256(old_pass.encode()).hexdigest()
            
            if admin.password_hash == old_hash:
                if new_pass == confirm_pass:
                    admin.password_hash = hashlib.sha256(new_pass.encode()).hexdigest()
                    db.session.commit()
                    flash('✅ Password changed successfully!', 'success')
                else:
                    flash('❌ New passwords do not match!', 'danger')
            else:
                flash('❌ Current password is incorrect!', 'danger')
        
        elif action == 'create_incoming_shipment':
            country_code = request.form.get('origin_country')[:2].upper()
            year = datetime.now().year
            random_chars = ''.join(random.choices(string.digits, k=6))
            tracking_code = f"INT-{country_code}-{year}-{random_chars}"
            
            new_shipment = Shipment(
                tracking_code=tracking_code,
                shipment_direction='incoming',
                customer_name=request.form.get('customer_name'),
                customer_email=request.form.get('customer_email'),
                customer_phone=request.form.get('customer_phone'),
                origin=f"{request.form.get('origin_city')}, {request.form.get('origin_country')}",
                destination=request.form.get('destination'),
                origin_country=request.form.get('origin_country'),
                origin_city=request.form.get('origin_city'),
                package_type=request.form.get('package_type'),
                package_weight=float(request.form.get('package_weight', 0)),
                partner_courier_original=request.form.get('partner_courier_original'),
                partner_tracking_original=request.form.get('partner_tracking_original'),
                expected_arrival_date=request.form.get('expected_arrival_date'),
                delivery_address=request.form.get('delivery_address'),
                status=request.form.get('status'),
                current_location=request.form.get('status'),
                notes=request.form.get('notes')
            )
            db.session.add(new_shipment)
            db.session.commit()
            flash(f'✅ Incoming package registered! Tracking: {tracking_code}', 'success')
    
    shipments = Shipment.query.order_by(Shipment.id.desc()).all()
    total_shipments = Shipment.query.count()
    delivered = Shipment.query.filter(Shipment.status.like('%Delivered%')).count()
    in_transit = total_shipments - delivered
    avg_rating = db.session.query(db.func.avg(Review.rating)).scalar() or 0
    
    stats = {
        'total': total_shipments,
        'delivered': delivered,
        'in_transit': in_transit,
        'avg_rating': round(avg_rating, 1)
    }

    # Riders data for the dashboard tab
    riders = Rider.query.order_by(Rider.created_at.desc()).all()
    rider_counts = {
        'all': Rider.query.count(),
        'pending': Rider.query.filter_by(status='pending').count(),
        'approved': Rider.query.filter_by(status='approved').count(),
        'rejected': Rider.query.filter_by(status='rejected').count(),
    }

    # Approved riders (for the assign dropdown)
    approved_riders = Rider.query.filter_by(status='approved', is_active=True)\
                                 .order_by(Rider.full_name).all()

    # Active delivery tasks (not yet delivered)
    active_tasks = DeliveryTask.query\
        .filter(DeliveryTask.status != 'delivered')\
        .order_by(DeliveryTask.assigned_at.desc()).all()

    return render_template(
        'admin.html',
        shipments=shipments,
        stats=stats,
        riders=riders,
        rider_counts=rider_counts,
        approved_riders=approved_riders,
        active_tasks=active_tasks
    )


@app.route('/admin/riders/<int:rider_id>/approve', methods=['POST'])
@login_required
def admin_approve_rider(rider_id):
    rider = Rider.query.get_or_404(rider_id)
    rider.status = 'approved'
    rider.is_active = True
    rider.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f'✅ {rider.full_name} has been approved.', 'success')
    return redirect(url_for('admin') + '#riders')


@app.route('/admin/riders/<int:rider_id>/reject', methods=['POST'])
@login_required
def admin_reject_rider(rider_id):
    rider = Rider.query.get_or_404(rider_id)
    rider.status = 'rejected'
    db.session.commit()
    flash(f'❌ {rider.full_name} has been rejected.', 'danger')
    return redirect(url_for('admin') + '#riders')


@app.route('/admin/riders/<int:rider_id>/toggle_active', methods=['POST'])
@login_required
def admin_toggle_rider_active(rider_id):
    rider = Rider.query.get_or_404(rider_id)
    rider.is_active = not rider.is_active
    db.session.commit()
    state = "activated" if rider.is_active else "deactivated"
    flash(f'✅ {rider.full_name} has been {state}.', 'success')
    return redirect(url_for('admin') + '#riders')


@app.route('/admin/riders/<int:rider_id>/reset_password', methods=['POST'])
@login_required
def admin_reset_rider_password(rider_id):
    rider = Rider.query.get_or_404(rider_id)
    new_password = request.form.get('new_password', '').strip()

    if not new_password or len(new_password) < 6:
        flash('❌ Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin') + '#riders')

    rider.password_hash = hashlib.sha256(new_password.encode()).hexdigest()
    db.session.commit()
    flash(f'🔑 Password reset for {rider.full_name}.', 'success')
    return redirect(url_for('admin') + '#riders')


@app.route('/admin/riders/<int:rider_id>/delete', methods=['POST'])
@login_required
def admin_delete_rider(rider_id):
    rider = Rider.query.get_or_404(rider_id)
    name = rider.full_name
    db.session.delete(rider)
    db.session.commit()
    flash(f'🗑️ {name} has been deleted.', 'success')
    return redirect(url_for('admin') + '#riders')

# ============================================
# ADMIN — DELIVERY TASK ASSIGNMENT
# ============================================

@app.route('/admin/riders/assign', methods=['POST'])
@login_required
def admin_assign_task():
    tracking_code = request.form.get('tracking_code', '').strip()
    rider_id = request.form.get('rider_id', '').strip()

    if not tracking_code or not rider_id:
        flash('❌ Please provide both tracking code and rider.', 'danger')
        return redirect(url_for('admin') + '#riders')

    shipment = Shipment.query.filter_by(tracking_code=tracking_code).first()
    if not shipment:
        flash(f'❌ Shipment "{tracking_code}" not found.', 'danger')
        return redirect(url_for('admin') + '#riders')

    rider = Rider.query.get(rider_id)
    if not rider or rider.status != 'approved':
        flash('❌ Invalid rider or rider is not approved.', 'danger')
        return redirect(url_for('admin') + '#riders')

    # Check if shipment already has an active task
    existing = DeliveryTask.query.filter_by(shipment_id=shipment.id)\
                                 .filter(DeliveryTask.status != 'delivered').first()
    if existing:
        flash(f'⚠️ This shipment is already assigned to {existing.rider.full_name}.', 'warning')
        return redirect(url_for('admin') + '#riders')

        task = DeliveryTask(
        rider_id=rider.id,
        shipment_id=shipment.id,
        status='assigned'
    )
    db.session.add(task)

    # Update the shipment status
    shipment.status = 'Assigned to rider'
    shipment.current_location = f'With rider - {rider.full_name}'
    shipment.last_update = datetime.now(timezone.utc)

    db.session.commit()

    # Send push notification to the rider
    try:
        send_push_notification(
            rider_id=rider.id,
            title="🚚 New Delivery Assigned",
            body=f"{shipment.tracking_code} → {shipment.customer_name or 'Customer'}",
            url="/dispatch_riders/dashboard"
        )
    except Exception as e:
        print(f"⚠️ Push notification failed: {e}")

    flash(f'✅ {shipment.tracking_code} assigned to {rider.full_name}.', 'success')
    return redirect(url_for('admin') + '#riders')


@app.route('/admin/riders/unassign/<int:task_id>', methods=['POST'])
@login_required
def admin_unassign_task(task_id):
    task = DeliveryTask.query.get_or_404(task_id)
    shipment_code = task.shipment.tracking_code
    rider_name = task.rider.full_name

    # Reset shipment status
    task.shipment.status = 'Awaiting rider assignment'
    task.shipment.current_location = task.shipment.origin
    task.shipment.last_update = datetime.now(timezone.utc)

    db.session.delete(task)
    db.session.commit()

    flash(f'✅ Unassigned {shipment_code} from {rider_name}.', 'success')
    return redirect(url_for('admin') + '#riders')


@app.route('/admin/riders/reassign/<int:task_id>', methods=['POST'])
@login_required
def admin_reassign_task(task_id):
    task = DeliveryTask.query.get_or_404(task_id)
    new_rider_id = request.form.get('new_rider_id', '').strip()

    if not new_rider_id:
        flash('❌ Please select a rider.', 'danger')
        return redirect(url_for('admin') + '#riders')

    new_rider = Rider.query.get(new_rider_id)
    if not new_rider or new_rider.status != 'approved':
        flash('❌ Invalid rider or rider is not approved.', 'danger')
        return redirect(url_for('admin') + '#riders')

    old_rider_name = task.rider.full_name
    task.rider_id = new_rider.id
    task.assigned_at = datetime.now(timezone.utc)

    task.shipment.current_location = f'With rider - {new_rider.full_name}'
    task.shipment.last_update = datetime.now(timezone.utc)

    db.session.commit()

    # Send push notification to the new rider
    try:
        send_push_notification(
            rider_id=new_rider.id,
            title="🚚 Delivery Reassigned to You",
            body=f"{task.shipment.tracking_code} → {task.shipment.customer_name or 'Customer'}",
            url="/dispatch_riders/dashboard"
        )
    except Exception as e:
        print(f"⚠️ Push notification failed: {e}")

    flash(f'✅ Reassigned from {old_rider_name} to {new_rider.full_name}.', 'success')
    return redirect(url_for('admin') + '#riders')

@app.route('/api/admin/rider-locations')
@login_required
def api_admin_rider_locations():
    """Return all approved riders with their latest known location"""
    riders = Rider.query.filter_by(status='approved').all()

    now = datetime.now(timezone.utc)
    result = []

    for rider in riders:
        # Determine freshness
        freshness = 'never'
        minutes_ago = None

        if rider.last_location_update:
            delta = now - rider.last_location_update.replace(tzinfo=timezone.utc) \
                if rider.last_location_update.tzinfo is None \
                else now - rider.last_location_update
            minutes_ago = int(delta.total_seconds() / 60)

            if minutes_ago < 5:
                freshness = 'active'      # green
            elif minutes_ago < 30:
                freshness = 'recent'      # yellow
            else:
                freshness = 'stale'       # red

        # Find rider's current active task (if any)
        active_task = DeliveryTask.query\
            .filter_by(rider_id=rider.id)\
            .filter(DeliveryTask.status.in_(['assigned', 'picked_up', 'in_transit']))\
            .first()

        current_delivery = None
        if active_task:
            current_delivery = {
                'tracking_code': active_task.shipment.tracking_code,
                'customer_name': active_task.shipment.customer_name,
                'destination': active_task.shipment.destination,
                'status': active_task.status
            }

        result.append({
            'id': rider.id,
            'full_name': rider.full_name,
            'phone': rider.phone,
            'vehicle_type': rider.vehicle_type,
            'lat': rider.current_lat,
            'lng': rider.current_lng,
            'last_update': rider.last_location_update.strftime('%Y-%m-%d %H:%M') if rider.last_location_update else None,
            'minutes_ago': minutes_ago,
            'freshness': freshness,
            'current_delivery': current_delivery
        })

    return jsonify({
        'riders': result,
        'count': len(result),
        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S')
    })    

@app.route('/admin/live-map')
@login_required
def admin_live_map():
    return render_template('admin_live_map.html')    

# ============================================
# ADMIN — SHIPMENT EDIT
# ============================================

@app.route('/admin/shipment/edit/<int:shipment_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_shipment(shipment_id):
    shipment = Shipment.query.get_or_404(shipment_id)
    
    if request.method == 'POST':
        shipment.customer_name = request.form.get('customer_name')
        shipment.customer_email = request.form.get('customer_email')
        shipment.customer_phone = request.form.get('customer_phone')
        shipment.origin = request.form.get('origin')
        shipment.destination = request.form.get('destination')
        shipment.package_type = request.form.get('package_type')
        shipment.package_weight = float(request.form.get('package_weight', 0))
        shipment.status = request.form.get('status')
        shipment.current_location = request.form.get('current_location')
        shipment.notes = request.form.get('notes')
        
        shipment.origin_country = request.form.get('origin_country')
        shipment.origin_city = request.form.get('origin_city')
        shipment.delivery_address = request.form.get('delivery_address')
        shipment.partner_courier_original = request.form.get('partner_courier_original')
        shipment.partner_tracking_original = request.form.get('partner_tracking_original')
        shipment.expected_arrival_date = request.form.get('expected_arrival_date')
        shipment.customs_status = request.form.get('customs_status')
        
        partner_courier = request.form.get('partner_courier')
        partner_tracking = request.form.get('partner_tracking')
        if partner_courier and partner_tracking:
            shipment.partner_courier = partner_courier
            shipment.partner_tracking = partner_tracking
        
        shipment.last_update = datetime.now(timezone.utc)
        db.session.commit()
        
        flash(f'✅ Shipment {shipment.tracking_code} updated successfully!', 'success')
        return redirect(url_for('admin'))
    
    return render_template('admin_edit_shipment.html', shipment=shipment)


# ============================================
# EXPRESS ADMIN ROUTES
# ============================================

@app.route('/express-admin', methods=['GET', 'POST'])
@login_required
def express_admin():
    new_tracking_code = None
    new_customer_name = None
    new_destination = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_express_shipment':
            random_numbers = ''.join(random.choices(string.digits, k=6))
            tracking_code = f"EXPDJL{random_numbers}"
            
            new_shipment = Shipment(
                tracking_code=tracking_code,
                customer_name=request.form.get('customer_name'),
                customer_email=request.form.get('customer_email'),
                customer_phone=request.form.get('customer_phone'),
                origin=request.form.get('origin'),
                destination=request.form.get('destination'),
                package_type=request.form.get('package_type'),
                package_weight=float(request.form.get('package_weight', 1.0)),
                status='Express - Package registered',
                current_location=request.form.get('origin'),
                notes=request.form.get('notes'),
                shipment_direction='outgoing'
            )
            db.session.add(new_shipment)
            db.session.commit()
            
            new_tracking_code = tracking_code
            new_customer_name = request.form.get('customer_name')
            new_destination = request.form.get('destination')
            
            flash(f'✅ Express shipment created! Tracking Code: {tracking_code}', 'success')
            
            return render_template('express_admin.html', 
                                  new_tracking_code=new_tracking_code,
                                  new_customer_name=new_customer_name,
                                  new_destination=new_destination)
    
    return render_template('express_admin.html')


# ============================================
# API ROUTES
# ============================================

@app.route('/api/shipment/<code>')
def get_shipment(code):
    shipment = Shipment.query.filter_by(tracking_code=code).first()
    if shipment:
        return jsonify({
            'tracking_code': shipment.tracking_code,
            'status': shipment.status,
            'location': shipment.current_location,
            'last_update': shipment.last_update.strftime('%Y-%m-%d %H:%M'),
            'partner_courier': shipment.partner_courier,
            'partner_tracking': shipment.partner_tracking
        })
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/stats')
def get_stats():
    total = Shipment.query.count()
    delivered = Shipment.query.filter(Shipment.status.like('%Delivered%')).count()
    return jsonify({
        'total': total,
        'delivered': delivered,
        'in_transit': total - delivered
    })


@app.route('/api/detect-courier', methods=['POST'])
def detect_courier_ajax():
    try:
        data = request.get_json()
        tracking_number = data.get('tracking_number', '')
        courier = detect_courier(tracking_number)
        return jsonify({
            'success': True,
            'courier': courier,
            'detected': courier != 'Unknown',
            'url': get_tracking_url(courier, tracking_number) if courier != 'Unknown' else '#'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# DISPATCH RIDER — PUBLIC PAGES
# ============================================

@app.route('/dispatch_riders')
def dispatch_rider_landing():
    return render_template('dispatch_rider_landing.html')


@app.route('/dispatch_riders/signup', methods=['GET', 'POST'])
def dispatch_rider_signup():
    print("=" * 60)
    print(f"🔵 SIGNUP ROUTE HIT — Method: {request.method}")

    if request.method == 'POST':
        print(f"📦 Form data received: {dict(request.form)}")

        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        vehicle = request.form.get('vehicle_type', '')

        print(f"📝 Parsed: name={full_name}, phone={phone}, vehicle={vehicle}")

        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not phone:
            errors.append("Phone number is required.")
        if not password:
            errors.append("Password is required.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not vehicle:
            errors.append("Please select a vehicle type.")

        # Add +234 prefix
        if phone and not phone.startswith('+'):
            phone = '+234' + phone.lstrip('0')

        if phone and Rider.query.filter_by(phone=phone).first():
            errors.append("This phone number is already registered.")

        # Strip +234 for clean display
        display_phone = phone
        if display_phone:
            if display_phone.startswith('+234'):
                display_phone = display_phone[4:]
            elif display_phone.startswith('0'):
                display_phone = display_phone[1:]

        if errors:
            print(f"❌ Validation errors: {errors}")
            return render_template(
                'dispatch_rider_signup.html',
                errors=errors,
                full_name=full_name,
                phone=display_phone,
                email=email,
                vehicle=vehicle
            )

        # Save the rider
        try:
            rider = Rider(
                full_name=full_name,
                phone=phone,
                email=email if email else None,
                password_hash=hashlib.sha256(password.encode()).hexdigest(),
                vehicle_type=vehicle,
                status='pending'
            )
            print(f"💾 About to save rider: {full_name}, {phone}, {vehicle}")
            db.session.add(rider)
            db.session.commit()
            print(f"✅ Rider saved! ID: {rider.id}")
            print("=" * 60)

        except Exception as e:
            db.session.rollback()
            print(f"❌ SAVE ERROR: {e}")
            print("=" * 60)
            errors.append(f"Could not save rider: {str(e)}")
            return render_template(
                'dispatch_rider_signup.html',
                errors=errors,
                full_name=full_name,
                phone=display_phone,
                email=email,
                vehicle=vehicle
            )

        flash(
            "✅ Account submitted! Your account is pending admin approval. "
            "You'll be able to log in once approved.",
            'success'
        )
        return redirect(url_for('dispatch_rider_login'))

    return render_template('dispatch_rider_signup.html')


@app.route('/dispatch_riders/login', methods=['GET', 'POST'])
def dispatch_rider_login():
    if 'rider_id' in session:
        return redirect(url_for('dispatch_rider_coming_soon'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')

        errors = []

        if not phone:
            errors.append("Phone number is required.")
        if not password:
            errors.append("Password is required.")

        if phone and not phone.startswith('+'):
            phone = '+234' + phone.lstrip('0')

        if not errors:
            rider = Rider.query.filter_by(phone=phone).first()

            if not rider:
                errors.append("No account found with this phone number.")
            else:
                password_hash = hashlib.sha256(password.encode()).hexdigest()

                if rider.password_hash != password_hash:
                    errors.append("Incorrect password.")
                elif rider.status == 'pending':
                    errors.append("Your account is pending admin approval. You'll be able to log in once approved.")
                elif rider.status == 'rejected':
                    errors.append("Your account was not approved. Please contact the admin for more information.")
                elif not rider.is_active:
                    errors.append("Your account has been deactivated.")
                else:
                    session['rider_id'] = rider.id
                    session['rider_name'] = rider.full_name
                    session['rider_phone'] = rider.phone
                    return redirect(url_for('dispatch_rider_dashboard'))

        # Strip +234 for clean display
        display_phone = phone
        if display_phone:
            if display_phone.startswith('+234'):
                display_phone = display_phone[4:]
            elif display_phone.startswith('0'):
                display_phone = display_phone[1:]

        return render_template(
            'dispatch_rider_login.html',
            errors=errors,
            phone=display_phone
        )

    return render_template('dispatch_rider_login.html')

@app.route('/dispatch_riders/dashboard')
def dispatch_rider_dashboard():
    if 'rider_id' not in session:
        return redirect(url_for('dispatch_rider_login'))

    rider = Rider.query.get(session['rider_id'])
    if not rider:
        session.clear()
        return redirect(url_for('dispatch_rider_login'))

    return render_template('rider_dashboard.html', rider=rider)    

@app.route('/dispatch_riders/history')
def dispatch_rider_history():
    if 'rider_id' not in session:
        return redirect(url_for('dispatch_rider_login'))

    rider = Rider.query.get(session['rider_id'])
    if not rider:
        session.clear()
        return redirect(url_for('dispatch_rider_login'))

    return render_template('rider_history.html', rider=rider)

@app.route('/dispatch_riders/profile')
def dispatch_rider_profile():
    if 'rider_id' not in session:
        return redirect(url_for('dispatch_rider_login'))

    rider = Rider.query.get(session['rider_id'])
    if not rider:
        session.clear()
        return redirect(url_for('dispatch_rider_login'))

    return render_template('rider_profile.html', rider=rider)    

@app.route('/dispatch_riders/logout')
def dispatch_rider_logout():
    session.pop('rider_id', None)
    session.pop('rider_name', None)
    session.pop('rider_phone', None)
    flash("You have been logged out.", 'success')
    return redirect(url_for('dispatch_rider_login'))


@app.route('/dispatch_riders/coming_soon')
def dispatch_rider_coming_soon():
    if 'rider_id' not in session:
        return redirect(url_for('dispatch_rider_login'))

    rider = Rider.query.get(session['rider_id'])
    if not rider:
        session.clear()
        return redirect(url_for('dispatch_rider_login'))

    return render_template('dispatch_rider_coming_soon.html', rider=rider)


@app.route('/dispatch_riders/forgot_password')
def dispatch_rider_forgot_password():
    return render_template('dispatch_rider_forgot_password.html')


# ============================================
# RIDER API — TASKS & UPDATES
# ============================================

@app.route('/api/rider/tasks')
def api_rider_tasks():
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    rider_id = session['rider_id']

    # Active tasks (not delivered and not failed)
    active_tasks = DeliveryTask.query\
        .filter_by(rider_id=rider_id)\
        .filter(DeliveryTask.status.in_(['assigned', 'picked_up', 'in_transit']))\
        .order_by(DeliveryTask.assigned_at.desc()).all()

    # Recently delivered (last 20)
    completed_tasks = DeliveryTask.query\
        .filter_by(rider_id=rider_id)\
        .filter(DeliveryTask.status == 'delivered')\
        .order_by(DeliveryTask.delivered_at.desc())\
        .limit(20).all()

    def serialize(task):
        s = task.shipment
        return {
            'task_id': task.id,
            'status': task.status,
            'tracking_code': s.tracking_code,
            'customer_name': s.customer_name,
            'customer_phone': s.customer_phone,
            'destination': s.destination,
            'delivery_address': s.delivery_address or s.destination,
            'package_type': s.package_type,
            'weight': s.package_weight,
            'notes': s.notes,
            'assigned_at': task.assigned_at.strftime('%Y-%m-%d %H:%M') if task.assigned_at else None,
            'picked_up_at': task.picked_up_at.strftime('%Y-%m-%d %H:%M') if task.picked_up_at else None,
            'delivered_at': task.delivered_at.strftime('%Y-%m-%d %H:%M') if task.delivered_at else None
        }

    return jsonify({
        'active': [serialize(t) for t in active_tasks],
        'completed': [serialize(t) for t in completed_tasks],
        'counts': {
            'active': len(active_tasks),
            'completed_today': DeliveryTask.query\
                .filter_by(rider_id=rider_id, status='delivered')\
                .filter(DeliveryTask.delivered_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))\
                .count()
        }
    })

# ============================================
# PUSH NOTIFICATION ENDPOINTS
# ============================================

@app.route('/api/rider/vapid-public-key')
def api_vapid_public_key():
    """Return the VAPID public key for the frontend to use when subscribing."""
    public_key, _, _ = get_vapid_keys()
    if not public_key:
        return jsonify({'error': 'VAPID public key not configured'}), 500
    return jsonify({'publicKey': public_key})


@app.route('/api/rider/push-subscribe', methods=['POST'])
def api_push_subscribe():
    """Save a push subscription for the current rider."""
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    endpoint = data.get('endpoint')
    p256dh = data.get('keys', {}).get('p256dh')
    auth = data.get('keys', {}).get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({'error': 'Missing subscription data'}), 400

    rider_id = session['rider_id']

    # Check if this endpoint already exists (for any rider)
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        # Update rider_id in case it's a different rider now (re-login on same device)
        existing.rider_id = rider_id
        existing.p256dh = p256dh
        existing.auth = auth
        existing.user_agent = request.headers.get('User-Agent', '')[:300]
        existing.last_used_at = datetime.now(timezone.utc)
    else:
        sub = PushSubscription(
            rider_id=rider_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=request.headers.get('User-Agent', '')[:300]
        )
        db.session.add(sub)

    db.session.commit()
    print(f"✅ Push subscription saved for rider {rider_id}")

    return jsonify({'success': True})


@app.route('/api/rider/push-unsubscribe', methods=['POST'])
def api_push_unsubscribe():
    """Remove a push subscription."""
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    endpoint = data.get('endpoint')

    if not endpoint:
        return jsonify({'error': 'Missing endpoint'}), 400

    sub = PushSubscription.query.filter_by(
        endpoint=endpoint,
        rider_id=session['rider_id']
    ).first()

    if sub:
        db.session.delete(sub)
        db.session.commit()
        print(f"🗑️ Push subscription removed for rider {session['rider_id']}")

    return jsonify({'success': True})

@app.route('/api/rider/history')
def api_rider_history():
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    rider_id = session['rider_id']

    # Get all delivered and failed tasks (last 50)
    tasks = DeliveryTask.query\
        .filter_by(rider_id=rider_id)\
        .filter(DeliveryTask.status.in_(['delivered', 'failed']))\
        .order_by(DeliveryTask.delivered_at.desc().nullslast(), DeliveryTask.assigned_at.desc())\
        .limit(50).all()

    def serialize(task):
        s = task.shipment
        return {
            'task_id': task.id,
            'status': task.status,
            'tracking_code': s.tracking_code,
            'customer_name': s.customer_name,
            'customer_phone': s.customer_phone,
            'destination': s.destination,
            'delivery_address': s.delivery_address or s.destination,
            'package_type': s.package_type,
            'weight': s.package_weight,
            'notes': task.notes,
            'photo_proof': task.photo_proof,
            'assigned_at': task.assigned_at.strftime('%Y-%m-%d %H:%M') if task.assigned_at else None,
            'delivered_at': task.delivered_at.strftime('%Y-%m-%d %H:%M') if task.delivered_at else None
        }

    return jsonify({
        'tasks': [serialize(t) for t in tasks]
    })

@app.route('/api/rider/stats')
def api_rider_stats():
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    rider_id = session['rider_id']

    # Calculate start-of-day, start-of-week, start-of-month
    now = datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = start_of_today - timedelta(days=now.weekday())
    start_of_month = start_of_today.replace(day=1)

    def count_since(since):
        return DeliveryTask.query\
            .filter_by(rider_id=rider_id, status='delivered')\
            .filter(DeliveryTask.delivered_at >= since)\
            .count()

    total_delivered = DeliveryTask.query\
        .filter_by(rider_id=rider_id, status='delivered').count()

    total_failed = DeliveryTask.query\
        .filter_by(rider_id=rider_id, status='failed').count()

    return jsonify({
        'today': count_since(start_of_today),
        'this_week': count_since(start_of_week),
        'this_month': count_since(start_of_month),
        'total_delivered': total_delivered,
        'total_failed': total_failed
    })    

@app.route('/api/rider/task/<int:task_id>/update', methods=['POST'])
def api_rider_update_task(task_id):
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    task = DeliveryTask.query.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    if task.rider_id != session['rider_id']:
        return jsonify({'error': 'Forbidden'}), 403

    data = request.get_json() or {}
    new_status = data.get('status')
    notes = data.get('notes', '').strip()
    photo_data = data.get('photo_data')  # Base64 encoded image

    # Validate status
    valid_statuses = ['assigned', 'picked_up', 'in_transit', 'delivered', 'failed']
    if new_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400

    # Update task
    task.status = new_status
    if notes:
        task.notes = notes

    # Update timestamps
    now = datetime.now(timezone.utc)
    if new_status == 'picked_up' and not task.picked_up_at:
        task.picked_up_at = now
    elif new_status == 'delivered':
        task.delivered_at = now

    # Save photo if provided (base64)
    if photo_data:
        try:
            import base64
            # Strip header if present
            if ',' in photo_data:
                photo_data = photo_data.split(',')[1]
            img_bytes = base64.b64decode(photo_data)

            # Save to static/uploads/delivery_proofs/
            upload_dir = os.path.join('static', 'uploads', 'delivery_proofs')
            os.makedirs(upload_dir, exist_ok=True)

            filename = f"task_{task_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(upload_dir, filename)

            with open(filepath, 'wb') as f:
                f.write(img_bytes)

            task.photo_proof = f"/static/uploads/delivery_proofs/{filename}"
        except Exception as e:
            print(f"⚠️ Photo upload failed: {e}")
            # Continue anyway — photo is optional

    # Sync the shipment status
    shipment = task.shipment
    if new_status == 'picked_up':
        shipment.status = 'Picked up from customer'
        shipment.current_location = 'With rider'
    elif new_status == 'in_transit':
        shipment.status = 'In transit to destination'
        shipment.current_location = 'In transit'
    elif new_status == 'delivered':
        shipment.status = 'Delivered successfully'
        shipment.current_location = shipment.destination
    elif new_status == 'failed':
        shipment.status = 'Delivery failed - Will retry'
        shipment.current_location = 'Returning to hub'

    shipment.last_update = now

    db.session.commit()

    return jsonify({
        'success': True,
        'task_id': task.id,
        'status': task.status,
        'photo_proof': task.photo_proof
    })

@app.route('/api/rider/location', methods=['POST'])
def api_rider_location():
    if 'rider_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        return jsonify({'error': 'Missing coordinates'}), 400

    rider = Rider.query.get(session['rider_id'])
    if not rider:
        return jsonify({'error': 'Rider not found'}), 404

    rider.current_lat = float(lat)
    rider.current_lng = float(lng)
    rider.last_location_update = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'received': {'lat': lat, 'lng': lng}
    })

# ============================================
# EXPORT ROUTES
# ============================================

@app.route('/admin/export/all')
@login_required
def export_all():
    shipments = Shipment.query.order_by(Shipment.id.desc()).all()
    return export_all_shipments(shipments)


@app.route('/admin/export/outgoing')
@login_required
def export_outgoing():
    shipments = Shipment.query.all()
    return export_outgoing_shipments(shipments)


@app.route('/admin/export/incoming')
@login_required
def export_incoming():
    shipments = Shipment.query.all()
    return export_incoming_shipments(shipments)


@app.route('/admin/export/delivered')
@login_required
def export_delivered():
    shipments = Shipment.query.all()
    return export_delivered_shipments(shipments)


@app.route('/admin/export/pending')
@login_required
def export_pending():
    shipments = Shipment.query.all()
    return export_pending_shipments(shipments)


@app.route('/admin/export/customers')
@login_required
def export_customers_list():
    customers = Customer.query.order_by(Customer.last_shipment.desc()).all()
    return export_customers(customers)


# ============================================
# UTILITY ROUTES
# ============================================

@app.route('/reset-database')
def reset_database():
    db.drop_all()
    db.create_all()
    
    password_hash = hashlib.sha256("admin123".encode()).hexdigest()
    admin = Admin(username="admin", password_hash=password_hash)
    db.session.add(admin)
    
    sample_reviews = [
        Review(customer_name="Mr. Adebayo Ogunlesi", location="Ibadan", rating=5, 
               comment="Excellent service! My package from Ibadan arrived quickly."),
        Review(customer_name="Mrs. Funmilayo Adeyemi", location="Oyo Town", rating=5, 
               comment="Best logistics company in Oyo State. Very reliable!"),
    ]
    db.session.add_all(sample_reviews)
    db.session.commit()
    
    return "✅ Database reset successful! <br><br>Login: admin / admin123 <br><br><a href='/admin/login'>Go to Admin Login</a>"


@app.route('/restore-shipment')
def restore_shipment():
    existing = Shipment.query.filter_by(tracking_code="DJL-2026-HXESB").first()
    if existing:
        return "✅ Shipment DJL-2026-HXESB already exists in database!"
    
    new_shipment = Shipment(
        tracking_code="DJL-2026-HXESB",
        customer_name="Areo Tolulope B",
        customer_email="toluare123@gmail.com",
        customer_phone="+447833889142",
        origin="Ibadan",
        destination="Wolverhampton, United Kingdom",
        package_type="Parcel",
        package_weight=10.0,
        status="Picked up from customer",
        current_location="Ibadan",
        last_update=datetime.now(timezone.utc)
    )
    db.session.add(new_shipment)
    db.session.commit()
    
    return """
    <h2>✅ Shipment Restored Successfully!</h2>
    <p><strong>Tracking Code:</strong> DJL-2026-HXESB</p>
    <p><strong>Customer:</strong> Areo Tolulope B</p>
    <p><strong>Destination:</strong> Wolverhampton, United Kingdom</p>
    <p><strong>Status:</strong> Picked up from customer</p>
    <br>
    <a href='/track'>Track this package</a><br>
    <a href='/admin/login'>Go to Admin Panel</a>
    """


@app.route('/restore-all-shipments')
def restore_all_shipments():
    shipments_data = [
        {'tracking_code': 'DJL-2026-ZOEAY', 'shipment_direction': 'outgoing', 'customer_name': 'Iyabo Odueyingbo', 'customer_email': 'emmanueltee@hotmail.com', 'customer_phone': '+447943004101', 'origin': 'Ibadan', 'destination': 'United Kingdom', 'package_type': 'Parcel', 'package_weight': 14.0, 'status': 'Customs clearance in progress', 'current_location': 'Lagos Hub', 'last_update': datetime(2026, 6, 29, 13, 58, 0)},
        {'tracking_code': 'DJL-2026-6URUQ', 'shipment_direction': 'outgoing', 'customer_name': 'Oluwadamilare Oloyede', 'customer_email': 'kolapastor62@yahoo.co.uk', 'customer_phone': '+447950711976', 'origin': 'Ibadan', 'destination': 'United Kingdom', 'package_type': 'Parcel', 'package_weight': 14.0, 'status': 'Handed over to partner courier', 'current_location': 'In transit to United kingdom', 'last_update': datetime(2026, 6, 23, 9, 29, 0)},
        {'tracking_code': 'DJL-2026-BBZTG', 'shipment_direction': 'outgoing', 'customer_name': 'Olumide Adejumo', 'customer_email': 'molumide74@yahoo.com', 'customer_phone': '+447445921438', 'origin': 'Ibadan', 'destination': 'United Kingdom', 'package_type': 'Parcel', 'package_weight': 24.4, 'status': 'Delivered successfully', 'current_location': 'United Kingdom', 'last_update': datetime(2026, 6, 26, 12, 4, 0)},
        {'tracking_code': 'DJL-2026-3CHNJ', 'shipment_direction': 'outgoing', 'customer_name': 'Favour Ibirogba Taiwo', 'customer_email': 'favouribirogba0@gmail.com', 'customer_phone': '+447809162523', 'origin': '-', 'destination': 'United Kingdom', 'package_type': 'Parcel', 'package_weight': 10.0, 'status': 'Delivered successfully', 'current_location': 'United Kingdom', 'last_update': datetime(2026, 6, 26, 12, 5, 0)},
        {'tracking_code': 'DJL-2026-Z1J5Q', 'shipment_direction': 'outgoing', 'customer_name': 'Ezekiel Rhoda', 'customer_email': 'ezekielrhoda@gmail.com', 'customer_phone': '+447908030466', 'origin': 'Ibadan', 'destination': 'United Kingdom', 'package_type': 'Parcel', 'package_weight': 20.0, 'status': 'Delivered successfully', 'current_location': 'United Kingdom', 'last_update': datetime(2026, 6, 26, 15, 35, 0)},
        {'tracking_code': 'INT-CA-2026-457520', 'shipment_direction': 'incoming', 'customer_name': 'Joseph Loseyi', 'customer_email': '-', 'customer_phone': '+1 (204) 558-9160', 'origin': 'Canada', 'destination': 'Lagos', 'package_type': 'Parcel', 'package_weight': 2.0, 'status': 'Shipped from origin country', 'current_location': 'Shipped from origin country', 'last_update': datetime(2026, 6, 11, 10, 33, 0), 'origin_country': 'Canada'},
        {'tracking_code': 'INT-UK-2026-479432', 'shipment_direction': 'incoming', 'customer_name': 'Mr. Chris', 'customer_email': '-', 'customer_phone': '+447570149032', 'origin': 'United Kingdom', 'destination': 'Lagos', 'package_type': 'Parcel', 'package_weight': 24.0, 'status': 'Delivered successfully', 'current_location': 'Lagos', 'last_update': datetime(2026, 6, 23, 9, 16, 0), 'origin_country': 'UK', 'partner_courier_original': 'Royal Mail'},
        {'tracking_code': 'DJL-2026-HXESB', 'shipment_direction': 'outgoing', 'customer_name': 'Areo Tolulope B', 'customer_email': 'toluare123@gmail.com', 'customer_phone': '+447833889142', 'origin': 'Ibadan', 'destination': 'Wolverhampton, United Kingdom', 'package_type': 'Parcel', 'package_weight': 10.0, 'status': 'Delivered successfully', 'current_location': 'Wolverhampton, United Kingdom', 'last_update': datetime(2026, 6, 23, 9, 19, 0), 'partner_courier': 'FedEx'}
    ]
    
    count_added = 0
    skipped = 0
    
    for data in shipments_data:
        existing = Shipment.query.filter_by(tracking_code=data['tracking_code']).first()
        if existing:
            skipped += 1
            continue
        
        shipment = Shipment(
            tracking_code=data['tracking_code'],
            shipment_direction=data.get('shipment_direction', 'outgoing'),
            customer_name=data['customer_name'],
            customer_email=data.get('customer_email'),
            customer_phone=data.get('customer_phone'),
            origin=data['origin'],
            destination=data['destination'],
            package_type=data['package_type'],
            package_weight=data['package_weight'],
            status=data['status'],
            current_location=data['current_location'],
            last_update=data['last_update'],
            partner_courier=data.get('partner_courier'),
            partner_tracking=data.get('partner_tracking'),
            origin_country=data.get('origin_country'),
            partner_courier_original=data.get('partner_courier_original'),
            partner_tracking_original=data.get('partner_tracking_original')
        )
        db.session.add(shipment)
        count_added += 1
    
    db.session.commit()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Restore Shipments</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ background: linear-gradient(135deg, #0A192F, #0F3B5C); min-height: 100vh; display: flex; align-items: center; justify-content: center; color: white; font-family: 'Segoe UI', sans-serif; }}
            .card {{ background: white; border-radius: 20px; padding: 40px; max-width: 600px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); color: #333; text-align: center; }}
            .btn-primary {{ background-color: #0F3B5C; border: none; padding: 12px 30px; border-radius: 10px; color: white; text-decoration: none; display: inline-block; margin: 5px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h2 class="mb-3">✅ {count_added} Shipments Restored!</h2>
            <p>Skipped {skipped} existing shipments.</p>
            <a href="/admin" class="btn-primary">Go to Admin Dashboard</a>
            <a href="/track" class="btn-primary">Track a Package</a>
        </div>
    </body>
    </html>
    """


# For Render deployment
application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
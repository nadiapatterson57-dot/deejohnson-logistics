from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import random
import string
import hashlib
import os
from functools import wraps
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
# DATABASE CONFIGURATION - FIXED FOR RENDER
# ============================================
import os

# Check if we're on Render (PostgreSQL) or local (SQLite)
if os.environ.get('DATABASE_URL'):
    # Production on Render - Use PostgreSQL (PERSISTENT)
    database_url = os.environ.get('DATABASE_URL')
    # Fix for Render's postgres:// vs postgresql://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    print("=" * 50)
    print("✅ USING POSTGRESQL DATABASE (Data will persist!)")
    print("=" * 50)
else:
    # Local development - Use SQLite
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
    
    # NEW FIELDS FOR INCOMING SHIPMENTS
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

# ============================================
# COURIER INTEGRATION FUNCTIONS
# ============================================

def detect_courier(tracking_number):
    """Detect which courier a tracking number belongs to"""
    if not tracking_number:
        return 'Unknown'
    
    tracking_number = str(tracking_number).upper().strip()
    
    # FedEx: usually 12-15 digits
    if len(tracking_number) >= 12 and len(tracking_number) <= 15 and tracking_number.isdigit():
        return 'FedEx'
    
    # DHL: 10-11 digits
    if len(tracking_number) >= 10 and len(tracking_number) <= 11 and tracking_number.isdigit():
        return 'DHL'
    
    # DPD: starts with 10-12 digits, often starts with 0
    if len(tracking_number) >= 10 and len(tracking_number) <= 12 and tracking_number.isdigit():
        return 'DPD'
    
    # USPS: 20-22 digits, or 13 chars starting with 9
    if (len(tracking_number) >= 20 and len(tracking_number) <= 22 and tracking_number.isdigit()) or \
       (len(tracking_number) == 13 and tracking_number.startswith('9')):
        return 'USPS'
    
    # Royal Mail: XX123456789GB format (2 letters, 9 digits, 2 letters)
    if (len(tracking_number) == 13 and 
        tracking_number[:2].isalpha() and 
        tracking_number[2:11].isdigit() and 
        tracking_number[11:13].isalpha()):
        return 'Royal Mail'
    
    # Royal Mail alternative: 16 digits starting with 8
    if len(tracking_number) == 16 and tracking_number.startswith('8') and tracking_number.isdigit():
        return 'Royal Mail'
    
    # UPS: starts with 1Z and total 18 characters
    if tracking_number.startswith('1Z') and len(tracking_number) == 18:
        return 'UPS'
    
    return 'Unknown'

def get_tracking_url(courier, tracking_number):
    """Return the direct tracking URL for a courier"""
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
    """Return icon class for each courier"""
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
    """Return color for each courier"""
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
    
    # Create default admin account if none exists
    admin_exists = Admin.query.filter_by(username="admin").first()
    if not admin_exists:
        default_password = hashlib.sha256("admin123".encode()).hexdigest()
        admin = Admin(username="admin", password_hash=default_password)
        db.session.add(admin)
        db.session.commit()
        print("\n" + "=" * 50)
        print("✅ ADMIN ACCOUNT CREATED SUCCESSFULLY!")
        print("📝 LOGIN CREDENTIALS:")
        print("   Username: admin")
        print("   Password: admin123")
        print("=" * 50 + "\n")
    
    # Add sample reviews if none exist
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
# AUTHENTICATION DECORATOR
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
# HELPER FUNCTIONS
# ============================================

def generate_tracking_code():
    """Generate unique tracking code like DJL-2024-XXXXX"""
    year = datetime.now().year
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"DJL-{year}-{random_chars}"

# ============================================
# ROUTES
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
        
        # Check if this is an Express shipment (starts with EXPDJL)
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
                
                # Get partner courier fields from form
                partner = request.form.get('partner_courier', '')
                partner_code = request.form.get('partner_tracking', '')

                print(f"🔍 Partner from form: '{partner}'")
                print(f"🔍 Tracking from form: '{partner_code}'")

                if partner and partner_code:
                    shipment.partner_courier = partner
                    shipment.partner_tracking = partner_code
                    print(f"✅ Saved partner: {partner} - {partner_code}")
                else:
                    print("⚠️ No partner courier data received")
                
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
        
        # INCOMING SHIPMENT ACTION
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
    
    return render_template('admin.html', shipments=shipments, stats=stats)

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
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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

@app.route('/reset-database')
def reset_database():
    import hashlib
    from datetime import datetime
    
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
    from datetime import datetime
    
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

# ============================================
# RESTORE ALL SHIPMENTS ROUTE (NEW)
# ============================================

@app.route('/restore-all-shipments')
def restore_all_shipments():
    """Restore all 8 shipments from the Excel data"""
    from datetime import datetime
    
    # List of all shipments from your Excel file
    shipments_data = [
        # 1. Iyabo Odueyingbo
        {
            'tracking_code': 'DJL-2026-ZOEAY',
            'shipment_direction': 'outgoing',
            'customer_name': 'Iyabo Odueyingbo',
            'customer_email': 'emmanueltee@hotmail.com',
            'customer_phone': '+447943004101',
            'origin': 'Ibadan',
            'destination': 'United Kingdom',
            'package_type': 'Parcel',
            'package_weight': 14.0,
            'status': 'Customs clearance in progress',
            'current_location': 'Lagos Hub',
            'last_update': datetime(2026, 6, 29, 13, 58, 0),
            'partner_courier': None,
            'partner_tracking': None
        },
        
        # 2. Oluwadamilare Oloyede
        {
            'tracking_code': 'DJL-2026-6URUQ',
            'shipment_direction': 'outgoing',
            'customer_name': 'Oluwadamilare Oloyede',
            'customer_email': 'kolapastor62@yahoo.co.uk',
            'customer_phone': '+447950711976',
            'origin': 'Ibadan',
            'destination': 'United Kingdom',
            'package_type': 'Parcel',
            'package_weight': 14.0,
            'status': 'Handed over to partner courier',
            'current_location': 'In transit to United kingdom',
            'last_update': datetime(2026, 6, 23, 9, 29, 0),
            'partner_courier': None,
            'partner_tracking': None
        },
        
        # 3. Olumide Adejumo
        {
            'tracking_code': 'DJL-2026-BBZTG',
            'shipment_direction': 'outgoing',
            'customer_name': 'Olumide Adejumo',
            'customer_email': 'molumide74@yahoo.com',
            'customer_phone': '+447445921438',
            'origin': 'Ibadan',
            'destination': 'United Kingdom',
            'package_type': 'Parcel',
            'package_weight': 24.4,
            'status': 'Delivered successfully',
            'current_location': 'United Kingdom',
            'last_update': datetime(2026, 6, 26, 12, 4, 0),
            'partner_courier': None,
            'partner_tracking': None
        },
        
        # 4. Favour Ibirogba Taiwo
        {
            'tracking_code': 'DJL-2026-3CHNJ',
            'shipment_direction': 'outgoing',
            'customer_name': 'Favour Ibirogba Taiwo',
            'customer_email': 'favouribirogba0@gmail.com',
            'customer_phone': '+447809162523',
            'origin': '-',
            'destination': 'United Kingdom',
            'package_type': 'Parcel',
            'package_weight': 10.0,
            'status': 'Delivered successfully',
            'current_location': 'United Kingdom',
            'last_update': datetime(2026, 6, 26, 12, 5, 0),
            'partner_courier': None,
            'partner_tracking': None
        },
        
        # 5. Ezekiel Rhoda
        {
            'tracking_code': 'DJL-2026-Z1J5Q',
            'shipment_direction': 'outgoing',
            'customer_name': 'Ezekiel Rhoda',
            'customer_email': 'ezekielrhoda@gmail.com',
            'customer_phone': '+447908030466',
            'origin': 'Ibadan',
            'destination': 'United Kingdom',
            'package_type': 'Parcel',
            'package_weight': 20.0,
            'status': 'Delivered successfully',
            'current_location': 'United Kingdom',
            'last_update': datetime(2026, 6, 26, 15, 35, 0),
            'partner_courier': None,
            'partner_tracking': None
        },
        
        # 6. Joseph Loseyi (Incoming from Canada)
        {
            'tracking_code': 'INT-CA-2026-457520',
            'shipment_direction': 'incoming',
            'customer_name': 'Joseph Loseyi',
            'customer_email': '-',
            'customer_phone': '+1 (204) 558-9160',
            'origin': 'Canada',
            'destination': 'Lagos',
            'package_type': 'Parcel',
            'package_weight': 2.0,
            'status': 'Shipped from origin country',
            'current_location': 'Shipped from origin country',
            'last_update': datetime(2026, 6, 11, 10, 33, 0),
            'partner_courier': None,
            'partner_tracking': None,
            'origin_country': 'Canada',
            'partner_courier_original': None,
            'partner_tracking_original': None
        },
        
        # 7. Mr. Chris (Incoming from UK)
        {
            'tracking_code': 'INT-UK-2026-479432',
            'shipment_direction': 'incoming',
            'customer_name': 'Mr. Chris',
            'customer_email': '-',
            'customer_phone': '+447570149032',
            'origin': 'United Kingdom',
            'destination': 'Lagos',
            'package_type': 'Parcel',
            'package_weight': 24.0,
            'status': 'Delivered successfully',
            'current_location': 'Lagos',
            'last_update': datetime(2026, 6, 23, 9, 16, 0),
            'partner_courier': None,
            'partner_tracking': None,
            'origin_country': 'UK',
            'partner_courier_original': 'Royal Mail',
            'partner_tracking_original': None
        },
        
        # 8. Areo Tolulope B
        {
            'tracking_code': 'DJL-2026-HXESB',
            'shipment_direction': 'outgoing',
            'customer_name': 'Areo Tolulope B',
            'customer_email': 'toluare123@gmail.com',
            'customer_phone': '+447833889142',
            'origin': 'Ibadan',
            'destination': 'Wolverhampton, United Kingdom',
            'package_type': 'Parcel',
            'package_weight': 10.0,
            'status': 'Delivered successfully',
            'current_location': 'Wolverhampton, United Kingdom',
            'last_update': datetime(2026, 6, 23, 9, 19, 0),
            'partner_courier': 'FedEx',
            'partner_tracking': None
        }
    ]
    
    count_added = 0
    skipped = 0
    
    for data in shipments_data:
        # Check if tracking code already exists
        existing = Shipment.query.filter_by(tracking_code=data['tracking_code']).first()
        if existing:
            skipped += 1
            continue
        
        # Create shipment with all available fields
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
    
    # Commit all changes
    db.session.commit()
    
    # Generate HTML response
    html_response = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Restore Shipments</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{ 
                background: linear-gradient(135deg, #0A192F, #0F3B5C); 
                min-height: 100vh; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                color: white;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }}
            .card {{
                background: rgba(255, 255, 255, 0.95);
                border-radius: 20px;
                padding: 40px;
                max-width: 600px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                color: #333;
            }}
            .success-icon {{
                font-size: 4rem;
                color: #28a745;
                margin-bottom: 20px;
            }}
            .btn-primary {{ 
                background-color: #0F3B5C; 
                border: none; 
                padding: 12px 30px;
                border-radius: 10px;
            }}
            .btn-primary:hover {{ background-color: #0A192F; }}
        </style>
    </head>
    <body>
        <div class="card text-center">
            <div class="success-icon">
                <i class="fas fa-check-circle"></i>
            </div>
            <h2 class="mb-3">✅ {count_added} Shipments Restored!</h2>
            <p class="lead">All shipments have been added to the database successfully.</p>
            
            <div class="alert alert-success mb-4">
                <strong>📦 {count_added} new shipments added</strong><br>
                <small class="text-muted">Skipped {skipped} existing shipments</small>
            </div>
            
            <div class="d-grid gap-2">
                <a href="/admin" class="btn btn-primary">
                    <i class="fas fa-tachometer-alt"></i> Go to Admin Dashboard
                </a>
                <a href="/track" class="btn btn-outline-primary">
                    <i class="fas fa-search"></i> Track a Package
                </a>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </body>
    </html>
    """
    
    return html_response

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
            # Generate EXPDJL + 6 random numbers
            random_numbers = ''.join(random.choices(string.digits, k=6))
            tracking_code = f"EXPDJL{random_numbers}"
            
            # Calculate delivery date (3-5 days from now)
            from datetime import timedelta
            delivery_date = datetime.now(timezone.utc) + timedelta(days=5)
            formatted_delivery = delivery_date.strftime("%B %d, %Y")
            
            # Create the shipment
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
                # Express shipments are outgoing by default
                shipment_direction='outgoing'
            )
            
            db.session.add(new_shipment)
            db.session.commit()
            
            # Store values to display in the template
            new_tracking_code = tracking_code
            new_customer_name = request.form.get('customer_name')
            new_destination = request.form.get('destination')
            
            flash(f'✅ Express shipment created! Tracking Code: {tracking_code}', 'success')
            
            # Return the template with the new tracking code
            return render_template('express_admin.html', 
                                  new_tracking_code=new_tracking_code,
                                  new_customer_name=new_customer_name,
                                  new_destination=new_destination)
    
    return render_template('express_admin.html')

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

# For Render deployment
application = app

@app.route('/health')
def health():
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
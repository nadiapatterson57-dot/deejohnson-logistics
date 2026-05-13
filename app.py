from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import random
import string
import hashlib
import os
from functools import wraps

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
    estimated_delivery = db.Column(db.String(100))
    status = db.Column(db.String(200))
    current_location = db.Column(db.String(100))
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    partner_courier = db.Column(db.String(50))
    partner_tracking = db.Column(db.String(50))
    notes = db.Column(db.Text)
    notification_sent = db.Column(db.Boolean, default=False)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    location = db.Column(db.String(50))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_code = db.Column(db.String(20))
    customer_email = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_via = db.Column(db.String(20))

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
    
    # USPS: 20-22 digits, or 13 chars starting with 9
    if (len(tracking_number) >= 20 and len(tracking_number) <= 22 and tracking_number.isdigit()) or \
       (len(tracking_number) == 13 and tracking_number.startswith('9')):
        return 'USPS'
    
    # Royal Mail: XX123456789GB format
    if (len(tracking_number) == 13 and 
        tracking_number[:2].isalpha() and 
        tracking_number[2:11].isdigit() and 
        tracking_number[11:13].isalpha()):
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

def calculate_estimated_delivery(origin, destination):
    """Calculate estimated delivery date based on route"""
    base_days = 3
    if "international" in destination.lower() or "usa" in destination.lower() or "uk" in destination.lower():
        days = 7
    else:
        days = base_days
    
    from datetime import timedelta
    est_date = datetime.now() + timedelta(days=days)
    return est_date.strftime("%B %d, %Y")

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
        
        # Get partner tracking info if available
        if shipment and shipment.partner_courier and shipment.partner_tracking:
            partner_url = get_tracking_url(shipment.partner_courier, shipment.partner_tracking)
            courier_icon = get_courier_icon(shipment.partner_courier)
            courier_color = get_courier_color(shipment.partner_courier)
    
    return render_template('track.html', 
                         shipment=shipment, 
                         partner_url=partner_url,
                         courier_icon=courier_icon,
                         courier_color=courier_color,
                         get_tracking_url=get_tracking_url,
                         get_courier_icon=get_courier_icon,
                         get_courier_color=get_courier_color)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # Check if admin exists, if not create one
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
            estimated_date = calculate_estimated_delivery(
                request.form.get('origin'), 
                request.form.get('destination')
            )
            
            new_shipment = Shipment(
                tracking_code=tracking_code,
                customer_name=request.form.get('customer_name'),
                customer_email=request.form.get('customer_email'),
                customer_phone=request.form.get('customer_phone'),
                origin=request.form.get('origin'),
                destination=request.form.get('destination'),
                package_type=request.form.get('package_type'),
                package_weight=float(request.form.get('package_weight', 0)),
                estimated_delivery=estimated_date,
                status='Package registered - Awaiting pickup',
                current_location=request.form.get('origin')
            )
            db.session.add(new_shipment)
            db.session.commit()
            
            flash(f'✅ Shipment created! Tracking Code: {tracking_code}', 'success')
            
        elif action == 'update_status':
            tracking_code = request.form.get('tracking_code')
            shipment = Shipment.query.filter_by(tracking_code=tracking_code).first()
            if shipment:
                shipment.status = request.form.get('status')
                shipment.current_location = request.form.get('current_location')
                shipment.last_update = datetime.utcnow()
                shipment.notes = request.form.get('notes')
                
                partner = request.form.get('partner_courier')
                partner_code = request.form.get('partner_tracking')
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
    
    shipments = Shipment.query.order_by(Shipment.id.desc()).all()
    
    # Get statistics
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
            'partner_tracking': shipment.partner_tracking,
            'estimated_delivery': shipment.estimated_delivery
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
    """AJAX endpoint to detect courier from tracking number"""
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

# For Render deployment
application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
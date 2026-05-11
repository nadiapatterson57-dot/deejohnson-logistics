from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Shipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tracking_code = db.Column(db.String(20), unique=True, nullable=False)
    origin = db.Column(db.String(100))
    destination = db.Column(db.String(100))
    customer_name = db.Column(db.String(100))
    status = db.Column(db.String(200))
    current_location = db.Column(db.String(100))
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    partner_courier_code = db.Column(db.String(50), nullable=True)
    partner_courier_name = db.Column(db.String(50), nullable=True)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    location = db.Column(db.String(50))
    rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.utcnow)
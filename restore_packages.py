from app import app, db
from app import Shipment
from datetime import datetime

with app.app_context():
    
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
            'package_weight': 7.0,
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
            'status': 'In transit internationally',
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
    for data in shipments_data:
        # Check if tracking code already exists
        existing = Shipment.query.filter_by(tracking_code=data['tracking_code']).first()
        if existing:
            print(f"⚠️ Shipment {data['tracking_code']} already exists, skipping...")
            continue
        
        # Create shipment
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
        print(f"✅ Added {data['tracking_code']} - {data['customer_name']}")
    
    # SAVE TO DATABASE
    db.session.commit()
    print("-" * 50)
    print(f"🎉 {count_added} SHIPMENTS RESTORED SUCCESSFULLY!")
    print("-" * 50)
    
    # Verify
    count = Shipment.query.count()
    print(f"Total shipments in database: {count}")
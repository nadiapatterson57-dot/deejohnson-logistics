import random
import string

def generate_tracking_code():
    prefix = "DJL"
    numbers = ''.join(random.choices(string.digits, k=8))
    return f"{prefix}-{numbers}"

def add_partner_tracking(our_code, partner_code, partner_name="FedEx"):
    # This would update the shipment with partner tracking info
    return {
        'our_tracking': our_code,
        'partner_tracking': partner_code,
        'partner': partner_name,
        'message': f'Package handed over to {partner_name}. Use code: {partner_code}'
    }
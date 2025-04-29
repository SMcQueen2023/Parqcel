import hashlib
import random
import string
import json
from datetime import datetime, timedelta

def generate_license_key():
    # Random key generator
    key_parts = [''.join(random.choices(string.ascii_lowercase + string.digits, k=16)) for _ in range(4)]
    return '-'.join(key_parts)

def save_key_to_file(key_info, filename="valid_keys.json"):
    try:
        # Read existing keys from file (if exists)
        with open(filename, 'r') as f:
            keys = json.load(f)
    except FileNotFoundError:
        keys = []

    # Append new key info and save to file
    keys.append(key_info)
    
    with open(filename, 'w') as f:
        json.dump(keys, f, indent=4)

def create_license(license_type="permanent", duration_days=None):
    new_key = generate_license_key()
    license_data = {
        "key": new_key,
        "type": license_type,
    }
    
    if license_type == "temporary":
        if duration_days is None:
            raise ValueError("Temporary licenses require 'duration_days'.")
        expiration_date = datetime.utcnow() + timedelta(days=duration_days)
        license_data["expires_at"] = expiration_date.isoformat() + "Z"  # ISO 8601 format

    return license_data

def main():
    print("License Generator")
    license_type = input("Enter license type ('permanent' or 'temporary'): ").strip().lower()
    
    if license_type not in ["permanent", "temporary"]:
        print("Invalid license type. Must be 'permanent' or 'temporary'.")
        return

    if license_type == "temporary":
        try:
            duration_days = int(input("Enter number of valid days: "))
        except ValueError:
            print("Invalid number for duration.")
            return
        license_info = create_license(license_type, duration_days)
    else:
        license_info = create_license(license_type)
    
    print(f"Generated License:\n{json.dumps(license_info, indent=4)}")
    save_key_to_file(license_info)

if __name__ == "__main__":
    main()

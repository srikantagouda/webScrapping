import requests
import mysql.connector
import json
import time
from datetime import datetime
from mysql.connector import errorcode
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import random
import string

# MySQL Database Connection with Database Creation
def connect_db():
    try:
        initial_conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="1234"
        )
        cursor = initial_conn.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS loadboard")
        print("Database 'loadboard' ensured.")
        cursor.close()
        initial_conn.close()
    except mysql.connector.Error as e:
        print(f"Failed to connect or create database: {e}")
        return None

    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="1234",
            database="loadboard"
        )
        return conn
    except mysql.connector.Error as e:
        print(f"Database connection failed: {e}")
        return None

def generate_ref_id():
    """Generate a unique 6-character alphanumeric ID"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def drop_and_create_table(cursor):
    """Drop existing table and create new one with length column"""
    try:
        cursor.execute("DROP TABLE IF EXISTS load_details")
        print("Existing 'load_details' table dropped.")
        
        create_table_sql = """
        CREATE TABLE load_details (
            ref_id VARCHAR(6) PRIMARY KEY,
            shipmentId INT,
            origin_city VARCHAR(255),
            origin_state VARCHAR(255),
            origin_zip VARCHAR(10),
            pickup_date VARCHAR(10),  -- MM-DD-YYYY
            pick_up_hours VARCHAR(255),
            destination_city VARCHAR(255),
            destination_state VARCHAR(255),
            destination_zip VARCHAR(10),
            drop_off_date VARCHAR(10),  -- MM-DD-YYYY
            drop_off_hours VARCHAR(255),
            price VARCHAR(255),
            permile VARCHAR(255),
            total_trip_mileage VARCHAR(255),
            full_partial VARCHAR(255),
            size VARCHAR(255),
            length VARCHAR(255),  -- New column for length
            height VARCHAR(255),
            commodity VARCHAR(255),
            comments TEXT,
            company VARCHAR(255),
            dot VARCHAR(255),
            docket VARCHAR(255),
            contact VARCHAR(255),
            phone VARCHAR(255),
            fax VARCHAR(255),
            email VARCHAR(255),
            website VARCHAR(255),
            truck_type VARCHAR(255),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        cursor.execute(create_table_sql)
        print("New 'load_details' table created with ref_id and length.")
    except mysql.connector.Error as e:
        print(f"Error dropping/creating table: {e}")

def parse_date(date_str, default_date="01-01-1970"):
    """Parse date and return as MM-DD-YYYY string"""
    try:
        if " - " in date_str:
            date_part = date_str.split(" - ")[0]
            dt = datetime.strptime(date_part, "%m/%d/%Y")
        else:
            dt = datetime.strptime(date_str, "%m/%d/%Y") if date_str else datetime.strptime(default_date, "%m-%d-%Y")
        return dt.strftime("%m-%d-%Y")  # Return as MM-DD-YYYY string
    except ValueError:
        return default_date  # Return default as MM-DD-YYYY string

def clean_html(text):
    if not text or text == "N/A":
        return "N/A"
    return re.sub(r'<[^>]+>', '', text).strip()

def extract_website(text):
    if not text or text == "N/A":
        return ""
    match = re.search(r'href=["\'](.*?)["\']', text)
    return match.group(1) if match else clean_html(text)

def extract_truck_types(text):
    if not text or text == "N/A":
        return "N/A"
    matches = re.findall(r'title=["\'](.*?)["\']', text)
    return ", ".join(matches) if matches else clean_html(text)

def extract_comments(text):
    if not text or text == "N/A":
        return "N/A"
    plain_text = clean_html(text)
    email = re.search(r'[\w\.-]+@[\w\.-]+', plain_text)
    phone = re.search(r'\d{3}[.-]\d{3}[.-]\d{4}', plain_text)
    if email:
        plain_text = plain_text.replace(email.group(0), "").strip()
    if phone:
        plain_text = plain_text.replace(phone.group(0), "").strip()
    details = plain_text
    if email or phone:
        details += f" ({email.group(0) if email else ''}{' / ' if email and phone else ''}{phone.group(0) if phone else ''})"
    return details.strip()

cookies = {
    "_fbp": "fb.1.1742407804636.661179603847395479",
    "version_number_1": "3.14",
    "__stripe_mid": "f6f749f1-8c7d-4aad-abeb-db57a17d725b82f07a",
    "__stripe_sid": "f4da6124-82f2-4b2f-a573-aaa8b87c66989275fb",
    "_ga_FMF1WBPBE4": "GS1.3.1742407804.1.1.1742410141.60.0.0",
    "_ga": "GA1.3.931376093.1742407799",
    "_gid": "GA1.3.2127480244.1742407799",
    "_gcl_au": "1.1.923807342.1742407804",
    "_ga_YMCPPWFZSL": "GS1.2.1742407799.1.1.1742408729.0.0.0",
    "last-login-date": "2025-03-19%2013%3A13%3A41",
    "login-cnt": "1",
    "doftlb_sessionKey": "F3sAIs7tSxFwtmsD",
    "doftlb_user": "963435",
    "JSESSIONID": "dy3QzXwHH0P1rN1t1xfKpIseyfHUyvv3-F35znky.ip-172-31-39-254"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 Safari/605.1.15",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://loadboard.doft.com",
    "Referer": "https://loadboard.doft.com/panel",
    "X-Requested-With": "XMLHttpRequest"
}

loads_url = "https://loadboard.doft.com/ajax/driver/get-loads"
load_detail_url = "https://loadboard.doft.com/ajax/getloadpage"

def fetch_shipment_uids_and_details():
    payload_loads = {
        "hash": "",
        "lastID": "",
        "lastValue": "",
        "zoneOffset": "300",
        "fid": "667061"
    }
    
    try:
        response = requests.post(loads_url, headers=headers, cookies=cookies, data=payload_loads)
        response.raise_for_status()
        data = response.json()
        
        if "loads" not in data:
            print("No 'loads' key in response:", data)
            return []
        
        shipment_data = [(load.get("shipmentUid", ""), 
                          load.get("equipment", "N/A"), 
                          load.get("loadSizeTtl", "N/A"), 
                          load.get("length", "N/A")) 
                         for load in data["loads"] if load.get("shipmentUid")]
        shipment_uids = [item[0] for item in shipment_data]
        truck_types = [item[1] for item in shipment_data]
        sizes = [item[2] for item in shipment_data]
        lengths = [item[3] for item in shipment_data]
        print(f"Fetched {len(shipment_uids)} shipment UIDs from {loads_url}")
        
        results = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_uid = {
                executor.submit(fetch_load_details, uid, truck_type, size, length): uid 
                for uid, truck_type, size, length in zip(shipment_uids, truck_types, sizes, lengths)
            }
            for future in as_completed(future_to_uid):
                uid = future_to_uid[future]
                try:
                    fields = future.result()
                    if fields:
                        results.append(fields)
                except Exception as e:
                    print(f"Error processing {uid}: {e}")
        
        return results
    
    except json.JSONDecodeError as e:
        print(f"Invalid JSON response from loads API: {e}")
        return []
    except requests.RequestException as e:
        print(f"HTTP Request failed for loads API: {e}")
        return []
    except Exception as e:
        print(f"Error fetching load UIDs: {e}")
        return []

def extractime(wp_arr):
    """
    Extracts the time portion from pickup_date within wpArr.
    Returns 'N/A' if wpArr is invalid or no time is found.
    """
    if wp_arr == 'N/A' or not isinstance(wp_arr, list) or not wp_arr:
        return 'N/A'
    
    try:
        pickup_info = wp_arr[0]  # First object in the array
        pickup_date = pickup_info.get('pickup_date', 'N/A')
        
        if pickup_date == 'N/A' or not pickup_date:
            return 'N/A'
        
        date_time_parts = pickup_date.split(' - ')
        if len(date_time_parts) < 2:
            return 'N/A'
        
        time_str = date_time_parts[1].strip()
        return time_str  # e.g., "12:00 AM"
    
    except (IndexError, AttributeError, KeyError) as e:
        print(f"[⚠️] Error extracting time from wpArr: {e}")
        return 'N/A'

def extractime1(wp_arr):
    """
    Extracts the time portion from drop_off_date within wpArr.
    Returns 'N/A' if wpArr is invalid or no time is found.
    """
    if wp_arr == 'N/A' or not isinstance(wp_arr, list) or not wp_arr:
        return 'N/A'
    
    try:
        pickup_info = wp_arr[1]  # Second object in the array
        pickup_date = pickup_info.get('pickup_date', 'N/A')
        
        if pickup_date == 'N/A' or not pickup_date:
            return 'N/A'
        
        date_time_parts = pickup_date.split(' - ')
        if len(date_time_parts) < 2:
            return 'N/A'
        
        time_str = date_time_parts[1].strip()
        return time_str  # e.g., "12:00 AM"
    
    except (IndexError, AttributeError, KeyError) as e:
        print(f"[⚠️] Error extracting time from wpArr: {e}")
        return 'N/A'

def extract_zip(location_str):
    """Extract the 5-digit zip code from a location string"""
    if not location_str or location_str == "N/A":
        return "N/A"
    match = re.search(r'\b\d{5}\b$', location_str)
    return match.group(0) if match else "N/A"
def format_per_mile(permile):
    """Format price per mile as '$X.XX/mi' or 'N/A'"""
    if not permile or permile == "N/A":
        return ""
    try:
        # Convert to float to ensure it's a number, then format with 2 decimals
        amount = float(str(permile).replace("$", "").replace("/mi", "").strip())
        return f"${amount:.2f}/Mi."
    except (ValueError, TypeError):
        print(f"[⚠️] Invalid permile value: {permile}, defaulting to 'N/A'")
        return ""
def fetch_load_details(load_uid, truck_type, size, length):
    payload_details = {
        "loadUid": load_uid,
        "showTitle": "false",
        "sk": "",
        "isLoadPostPreview": "false",
        "queryParameters": ""
    }
    

    try:
        response = requests.post(load_detail_url, headers=headers, cookies=cookies, data=payload_details)
        response.raise_for_status()
        data = response.json()
        
        load = data.get("load")
        if not load:
            print(f"No 'load' key in response for {load_uid}")
            return None
        
        load_detail = data.get("loadDetail", {})
        
        # Extract zip codes from origin and destination
        origin_zip = extract_zip(load.get("origin", "N/A"))
        destination_zip = extract_zip(load.get("destination", "N/A"))
        
        # Format weight to "X Lbs"
        raw_weight = load.get("weight", "N/A")
        if raw_weight != "N/A" and raw_weight:
            weight_value = re.sub(r'[^\d,]', '', str(raw_weight))  # Extract digits and commas
            if weight_value:
                weight = f"{weight_value} Lbs"
            else:
                weight = "N/A"
        else:
            weight = "N/A"
        
        # Parse drop_off_date and replace "01-01-1970" with "N/A"
        drop_off_date = parse_date(load.get("dropoffDate", ""))
        if drop_off_date == "01-01-1970":
            drop_off_date = "N/A"
        
        fields = {
            "ref_id": generate_ref_id(),
            "shipmentId": load.get("shipmentId", None),
            "origin_city": load.get("originCity", "N/A"),
            "origin_state": load.get("originState", "N/A"),
            "origin_zip": origin_zip,
            "pickup_date": parse_date(load.get("pickupDate", "")),
            "pick_up_hours": extractime(load_detail.get("wpArr", "N/A")),
            "drop_off_hours": extractime1(load_detail.get("wpArr", "N/A")),
            "destination_city": load.get("destinationCity", "N/A"),
            "destination_state": load.get("destinationState", "N/A"),
            "destination_zip": destination_zip,
            "drop_off_date": drop_off_date,  # Use the adjusted value
            "price": load.get("price", "N/A"),
            "permile": format_per_mile(load.get("permile","N/A")),
            "total_trip_mileage": load.get("distance", "N/A"),
            "full_partial": load.get("loadSizeTtl", "N/A"),
            "size": size,
            "length": length,
            "height": weight,
            "commodity": load.get("commodity", "N/A"),
            "comments": extract_comments(load_detail.get("commentRaw", "N/A")),
            "company": load.get("broker", "N/A"),
            "dot": load_detail.get("dot", "N/A"),
            "docket": load_detail.get("mc", "N/A"),
            "contact": load_detail.get("contact", "N/A"),
            "phone": load.get("phoneNum"),
            "fax": load_detail.get("fax", "N/A"),
            "email": load_detail.get("email"),
            "website": extract_website(load_detail.get("website", "N/A")),
            "truck_type": extract_truck_types(truck_type),
            "timestamp": datetime.now()
        }
        
        return fields
    except json.JSONDecodeError as e:
        print(f"Invalid JSON response for {load_uid}: {e}")
        return None
    except requests.RequestException as e:
        print(f"HTTP Request failed for {load_uid}: {e}")
        return None
    except Exception as e:
        print(f"Error fetching data for {load_uid}: {e}")
        return None

def store_load_details(fields, cursor, db):
    if not fields:
        return
    
    try:
        columns = ", ".join(fields.keys())
        placeholders = ", ".join(["%s"] * len(fields))
        sql = f"INSERT INTO load_details ({columns}) VALUES ({placeholders})"
        
        values = list(fields.values())
        cursor.execute(sql, values)
        db.commit()
        print(f"Inserted Ref ID: {fields['ref_id']} (Shipment ID: {fields['shipmentId']})")
    except mysql.connector.Error as e:
        print(f"Database error for Ref ID {fields.get('ref_id', 'Unknown')}: {e}")
    except Exception as e:
        print(f"Error storing data for Ref ID {fields.get('ref_id', 'Unknown')}: {e}")

def fetch_and_store_data():
    db = connect_db()
    if not db:
        return

    cursor = db.cursor()
    drop_and_create_table(cursor)

    while True:
        load_details_list = fetch_shipment_uids_and_details()

        if load_details_list:
            start_time = time.time()
            processed_count = 0
            for fields in load_details_list:
                cursor.execute("SELECT shipmentId FROM load_details WHERE shipmentId = %s", (fields["shipmentId"],))
                if not cursor.fetchone():
                    store_load_details(fields, cursor, db)
                    processed_count += 1

            elapsed_time = time.time() - start_time
            print(f"Processed {processed_count} new loads.")
        else:
            print("No new loads.")

        time.sleep(1)  # now every second

if __name__ == "__main__":
    fetch_and_store_data()
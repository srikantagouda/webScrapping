import imaplib
import email
import smtplib
import time
import mysql.connector
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import pytz

# Database connection
def connect_db():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="1234",
            database="loadboard"
        )
        return conn
    except Exception as e:
        print(f"[❌] Database Error: {e}")
        return None

# Load authorized receivers
def load_receivers():
    try:
        with open("receivers.txt", "r") as file:
            receivers_list = [line.strip() for line in file.readlines() if line.strip()]
        print(f"[ℹ️] Loaded Receivers: {receivers_list}")
        return receivers_list
    except Exception as e:
        print(f"[❌] Error loading receivers: {e}")
        return []

# Load sender accounts
def load_senders():
    try:
        with open("senders.txt", "r") as file:
            senders_list = [tuple(line.strip().split(", ")) for line in file.readlines() if line.strip()]
        print(f"[ℹ️] Loaded Senders: {[s[0] for s in senders_list]}")
        return senders_list
    except Exception as e:
        print(f"[❌] Error loading senders: {e}")
        return []

receivers = load_receivers()
senders = load_senders()

sender_index = 0
send_limit = 500
send_count = {sender[0]: 0 for sender in senders}
processed_emails = set()
requests = {}  # Format: {(truck, origin_state, destination_state): (to_email, original_message_id, last_no_match_sent, request_time)}
sent_loads = {}  # Format: {original_message_id: set(shipmentIds)}
NO_MATCH_INTERVAL = 1800  # 30 minutes in seconds
CHECK_INTERVAL = 5  # 5 seconds

# Load changer email
def load_changer_email():
    try:
        with open("email_changer.txt", "r") as file:
            return file.read().strip()
    except:
        return ""

changer_email = load_changer_email()

# Extract email details
def extract_request(body):
    request = {}
    patterns = {
        "Truck": r"Truck:\s*(.*)",
        "Origin": r"Origin:\s*(.*)",
        "Destination": r"Destination:\s*(.*)",
        "Pick Up Date": r"Pick Up Date:\s*([\d-]+)",
        "Drop Off Date": r"Drop Off Date:\s*([\d-]+)",
        "Full / Partial": r"Full / Partial:\s*(\w)",
        "Weight": r"Weight:\s*([\d,]+[\s\w]*)"
    }

    print(f"[📩] Extracting data from email:\n{body}\n")

    # Extract all fields
    for key, pattern in patterns.items():
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            if key in ["Origin", "Destination"]:
                value = match.group(1).strip()
                if not value:  # Check if the value is empty after stripping
                    print(f"[❌] Empty {key} field")
                    request[key] = None
                else:
                    request[key] = (None, value)
            else:
                value = match.group(1).strip()
                if not value:  # Check if the value is empty after stripping
                    print(f"[❌] Empty {key} field")
                    request[key] = None
                else:
                    request[key] = value

    # Validate mandatory fields
    mandatory_fields = ["Truck", "Origin", "Destination"]
    missing_fields = [field for field in mandatory_fields if field not in request or request[field] is None]
    
    if missing_fields:
        print(f"[❌] Missing mandatory fields: {', '.join(missing_fields)}")
        return None
    
    return request

# Fetch matching loads from load_details table, including zip codes
def fetch_loads(truck, origin_state=None, destination_state=None):
    conn = connect_db()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    query = """
    SELECT ref_id, shipmentId, origin_city, origin_state, origin_zip, pickup_date, destination_city, 
           destination_state, destination_zip, drop_off_date, price, permile, total_trip_mileage, full_partial, 
           height AS weight, length, commodity, truck_type, comments, company, phone, email, dot, docket, 
           contact, website, timestamp, pick_up_hours, drop_off_hours
    FROM load_details 
    WHERE truck_type LIKE %s
    """
    params = [f"%{truck}%"]

    # Add conditions based on provided origin or destination
    if origin_state:
        query += " AND origin_state LIKE %s"
        params.append(f"%{origin_state}%")
    if destination_state:
        query += " AND destination_state LIKE %s"
        params.append(f"%{destination_state}%")

    try:
        print(f"[🔍] Querying load_details with parameters: {params}")
        cursor.execute(query, tuple(params))
        loads = cursor.fetchall()
        if not loads:
            print("[ℹ️] No loads found matching truck_type and specified state(s).")
            return []

        current_time = datetime.now()
        recent_loads = [
            load for load in loads
            if (current_time - load['timestamp']).total_seconds() < 1800  # Loads within 5 minutes
        ]
        if not recent_loads:
            print("[ℹ️] No loads found within 30 minutes in load_details.")
        else:
            print(f"[✅] Found {len(recent_loads)} loads within 30 minutes in load_details.")
        return recent_loads
    except Exception as e:
        print(f"[❌] Query Error: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

# Format individual load response with zip codes in parentheses
def format_load_response(load, contact_email=None, contact_phone=None):
    ref_id = str(load.get('ref_id', 'N/A'))
    shipmentId = str(load.get('shipmentId', 'N/A'))
    origin_city = str(load.get('origin_city', 'N/A'))
    origin_state = str(load.get('origin_state', 'N/A'))
    origin_zip = str(load.get('origin_zip', 'N/A'))  # New field
    destination_city = str(load.get('destination_city', 'N/A'))
    destination_state = str(load.get('destination_state', 'N/A'))
    destination_zip = str(load.get('destination_zip', 'N/A'))  # New field
    pickup_hour = str(load.get('pick_up_hours', 'N/A'))
    drop_off_hours = str(load.get('drop_off_hours', 'N/A'))
    distance = str(load.get('total_trip_mileage', 'N/A'))
    weight = str(load.get('weight', 'N/A'))
    length = str(load.get('length', 'N/A'))
    loadSize = str(load.get('full_partial', 'N/A'))
    equipment = str(load.get('truck_type', 'N/A'))
    broker = str(load.get('company', 'N/A'))
    phoneNum = str(load.get('phone', 'N/A'))
    email = str(load.get('email', 'N/A'))
    price = str(load.get('price', 'N/A'))
    permile = str(load.get('permile', 'N/A'))
    comments = str(load.get('comments', 'N/A'))
    dot = str(load.get('dot', 'N/A'))
    docket = str(load.get('docket', 'N/A'))
    contact = str(load.get('contact', 'N/A'))
    website = str(load.get('website', 'N/A'))
    pickup_date = str(load.get('pickup_date', 'N/A'))
    dropoff_date = str(load.get('drop_off_date', 'N/A'))

    cst = pytz.timezone('America/Chicago')
    current_time_cst = datetime.now(cst)
    age_posted = current_time_cst.strftime("%I:%M %p (C.S.T.)").lstrip('0')

    # Comments formatting
    if comments != 'N/A':
        comments_list = [comment.strip() for comment in comments.split('.') if comment.strip()]
        formatted_comments = []
        for comment in comments_list:
            if ':' in comment:
                key, value = [part.strip() for part in comment.split(':', 1)]
                formatted_line = f"🟢 {key}: {value} {'🟢' if value in ['N', 'Y'] else ''}"
            else:
                formatted_line = f"🟢 {comment}"
            formatted_comments.append(formatted_line)
        formatted_comments = '\n'.join(formatted_comments)
    else:
        formatted_comments = 'N/A'

    # Contact info
    contact_parts = []
    if phoneNum != '':
        contact_parts.append(phoneNum)
    if email != '':
        contact_parts.append(email)
    if website != '':
        contact_parts.append(website)
    contact_info = " / ".join(contact_parts) if contact_parts else contact

    company_parts = []
    if broker != 'N/A': company_parts.append(broker)
    if contact != 'N/A': company_parts.append(contact)
    company = " / ".join(company_parts).rstrip(" / ") if company_parts else company

    # Docket / D.O.T formatting
    doc = "/"
    if docket != "":
        doc = f"{docket[2:] if docket.startswith('MC') else docket} /"
    if dot != "":
        doc = f"{doc} {dot}" if docket != "" else f"/ {dot}"
    if doc == "/":
        doc = "/ "

    # Emoji logic
    emoji = "🟩" if email and phoneNum else "📧" if email else "☎️" if phoneNum else ""

    # Price handling with permile
    invalid_price_values = ["N/A", "", " ", "$", "s"]
    display_price = "Bid" if price in invalid_price_values else price
    price_line = display_price
    if permile != "":
        price_line += f" ({permile})"
        
    subject_distance = distance.replace(' mi', '') if distance != '' else ''
    if length!='':
        sub_len=f"({length})"
    else:
        sub_len=''

    origin_line = f"{origin_city}, {origin_state}"
    if origin_zip != "N/A":
        origin_line += f" ({origin_zip})"
    
    destination_line = f"{destination_city}, {destination_state}"
    if destination_zip != "N/A":
        destination_line += f" ({destination_zip})"
  
    subject = (
        f"{emoji} - Truck: {equipment} {sub_len} - Pickup: {pickup_date} / {origin_line} - "
        f"Drop: {destination_state} - {subject_distance} Mi. - {weight}. - Ref #: {ref_id}"
    )

    body = f"""
Age Posted: {age_posted}

Truck Type: {equipment}

Length: {length}

Origin: {origin_line}
Pickup Date: {pickup_date}
Pick Up Hours: {pickup_hour}
 
Destination: {destination_line}
Drop off date: {dropoff_date}
Drop Off Hours: {drop_off_hours}

Price: {price_line}

Trip: {subject_distance} Mi.
Full / Partial: {loadSize}
Weight: {weight}.

Comments: {formatted_comments}

Company: {company}
Docket / D.O.T: {doc}
Contact: {contact_info}
"""
    # Return subject, body, and contact email for Reply-To
    return subject, body, email if emoji in ["🟩", "📧"] else None

# Format no matches found response
def format_no_matches_response(truck, state):
    cst = pytz.timezone('America/Chicago')
    current_time_cst = datetime.now(cst)
    timestamp = current_time_cst.strftime("%I:%M %p (C.S.T.)").lstrip('0')
    
    subject = f"❌ No Matching Loads Found - Truck: {truck} - State: {state}"
    body = f"""
Timestamp: {timestamp}

We couldn't find any matching loads for your request:
Truck Type: {truck}
State: {state}

We'll keep searching and notify you if any matching loads become available within the next 30 minutes.
"""
    return subject, body

# Send reply email with retry logic
def send_reply(to_email, body, sender_email, sender_password, original_message_id, subject, shipment_id=None, contact_email=None):
    global sender_index, send_count
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = to_email
            msg["Subject"] = subject
            if original_message_id:
                msg["In-Reply-To"] = original_message_id
                msg["References"] = original_message_id
            # Set Reply-To to contact_email if it exists, otherwise to_email
            msg["Reply-To"] = contact_email if contact_email else to_email
            msg.attach(MIMEText(body, "plain"))

            # Determine SMTP settings based on sender's email domain
            if "@gmail.com" in sender_email.lower():
                smtp_host = "smtp.gmail.com"
                smtp_port = 465
                use_ssl = True
            elif "@icloud.com" in sender_email.lower():
                smtp_host = "smtp.mail.me.com"
                smtp_port = 587
                use_ssl = False
            else:
                print(f"[❌] Unsupported email provider for {sender_email}")
                return False

            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port)
                server.starttls()

            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
            server.quit()

            send_count[sender_email] += 1
            if send_count[sender_email] >= send_limit:
                sender_index = (sender_index + 1) % len(senders)
                print(f"[ℹ️] Switching to next sender: {senders[sender_index][0]}")
            
            print(f"[✅] Sent response to {to_email} from {sender_email} {'for Shipment ID ' + str(shipment_id) if shipment_id else 'with no matches'} as reply to {original_message_id} with Reply-To: {msg['Reply-To']}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"[❌] Authentication Error: {e}. Check sender credentials in senders.txt (use App Password if 2FA is enabled).")
            return False
        except smtplib.SMTPException as e:
            print(f"[❌] SMTP Error on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return False
        except Exception as e:
            print(f"[❌] Send Error: {e}")
            return False
    return False

# Check for New Emails and Process Them
def check_email():
    global sender_index, send_count, requests, sent_loads
    if not senders:
        print("[❌] No senders available")
        return
    
    email_user, email_pass = senders[sender_index]
    
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, email_pass)
        mail.select("inbox")

        since_date = datetime.today().strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(UNSEEN SINCE "{since_date}")')
        email_ids = messages[0].split()

        for num in email_ids:
            if num in processed_emails:
                continue

            status, msg_data = mail.fetch(num, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    sender_email = email.utils.parseaddr(msg["From"])[1]
                    original_message_id = msg.get("Message-ID", "")
                    original_subject = msg.get("Subject", "Load Request")

                    print(f"[📧] Email received from: {sender_email}")

                    if msg.get("Subject", "").lower().strip() == "change receivers":
                        if sender_email != changer_email:
                            print(f"[⛔] Unauthorized changer: {sender_email}")
                            continue

                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode(errors="ignore")
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode(errors="ignore")

                        new_receiver = body.strip()
                        if new_receiver in receivers:
                            print(f"[ℹ️] {new_receiver} is already in receivers.")
                        else:
                            with open("receivers.txt", "a") as f:
                                f.write(f"\n{new_receiver}")
                            print(f"[✅] Added new receiver: {new_receiver}")
                        continue

                    if sender_email not in receivers:
                        print(f"[⚠️] Unauthorized sender: {sender_email}")
                        continue
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")
                    
                    request = extract_request(body)
                    if request:
                        print(f"[✅] Extracted Request: {request}")
                        truck = request["Truck"]
                        origin = request["Origin"][1] if request["Origin"] else None
                        destination = request["Destination"][1] if request["Destination"] else None
                        origin_state = re.search(r'\b[A-Z]{2}\b', origin).group(0) if origin and re.search(r'\b[A-Z]{2}\b', origin) else None
                        destination_state = re.search(r'\b[A-Z]{2}\b', destination).group(0) if destination and re.search(r'\b[A-Z]{2}\b', destination) else None
                        request_key = (truck, origin_state, destination_state)
                        requests[request_key] = (sender_email, original_message_id, None, datetime.now())

                        if original_message_id not in sent_loads:
                            sent_loads[original_message_id] = set()

                        loads = fetch_loads(truck, origin_state, destination_state)
                        if loads:
                            for load in loads:
                                shipment_id = str(load.get('shipmentId', 'N/A'))
                                if shipment_id not in sent_loads[original_message_id]:
                                    subject, response_body, contact_email = format_load_response(load)
                                    if send_reply(sender_email, response_body, email_user, email_pass, 
                                                original_message_id, subject, shipment_id, contact_email):
                                        sent_loads[original_message_id].add(shipment_id)
                        processed_emails.add(num)
        
        mail.logout()
    except Exception as e:
        print(f"[❌] Email Error: {e}")

# Check Database for New Loads Matching Stored Requests
def check_database():
    global sender_index, send_count, requests, sent_loads
    if not senders:
        print("[❌] No senders available")
        return
    
    email_user, email_pass = senders[sender_index]
    current_time = datetime.now()
    
    for (truck, origin_state, destination_state), (to_email, original_message_id, last_no_match_sent, request_time) in list(requests.items()):
        if original_message_id not in sent_loads:
            sent_loads[original_message_id] = set()
        
        loads = fetch_loads(truck, origin_state, destination_state)
        if loads:
            for load in loads:
                shipment_id = str(load.get('shipmentId', 'N/A'))
                if shipment_id not in sent_loads[original_message_id]:
                    subject, response_body, contact_email = format_load_response(load)
                    if send_reply(to_email, response_body, email_user, email_pass, 
                                original_message_id, subject, shipment_id, contact_email):
                        sent_loads[original_message_id].add(shipment_id)
        elif last_no_match_sent is None and (current_time - request_time).total_seconds() >= NO_MATCH_INTERVAL:
            subject, response_body = format_no_matches_response(truck, origin_state or destination_state)
            if send_reply(to_email, response_body, email_user, email_pass, 
                        original_message_id, subject):
                requests[(truck, origin_state, destination_state)] = (to_email, original_message_id, current_time, request_time)

# Run Continuously
while True:
    try:
        print("[🔄] Checking emails...")
        check_email()
        print("[🔍] Checking database for new loads...")
        check_database()
        print("[⏳] Waiting 5 seconds...")
        time.sleep(CHECK_INTERVAL)  # Check every 5 seconds
    except Exception as e:
        print(f"[❌] Main loop error: {e}")
        time.sleep(60)
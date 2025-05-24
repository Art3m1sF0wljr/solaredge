import ftplib
import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import io
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables from a .env file
load_dotenv()

# Configuration
LOG_FILE = '/home/pi/program/solaredge/solar_edge_data.log'  # Path to your local log file
FTP_HOST = os.getenv('FTP_HOST')
FTP_USER = os.getenv('FTP_USER')
FTP_PASS = os.getenv('FTP_PASS')
REMOTE_PATH = '/solaredge/'  # Change this to your desired remote path
UPLOAD_INTERVAL = 600  # 10 minutes in seconds
DAYS_TO_KEEP = 3  # Number of days to keep in the uploaded file

# Function to filter and keep only the last 3 days of data
def filter_last_days(log_content):
    cutoff = datetime.now() - timedelta(days=DAYS_TO_KEEP)
    filtered_lines = []
    
    for line in log_content.split('\n'):
        if not line.strip():
            continue
            
        try:
            # Extract timestamp from the line
            timestamp_str = line.split(',')[0]
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%f')
            
            if timestamp >= cutoff:
                filtered_lines.append(line)
        except (IndexError, ValueError) as e:
            logging.warning(f"Error parsing line: {line} - {str(e)}")
            continue
            
    return '\n'.join(filtered_lines)

# Function to connect securely to the FTPS server
def connect_ftps():
    try:
        ftps = ftplib.FTP_TLS(FTP_HOST)
        ftps.login(FTP_USER, FTP_PASS)
        ftps.prot_p()  # Secure data connection (Explicit TLS)
        ftps.set_pasv(True)  # Enable passive mode
        logging.info("Successfully connected to the FTPS server.")
        return ftps
    except ftplib.all_errors as e:
        logging.error(f"FTPS connection error: {e}")
        return None

# Function to upload the filtered log file
def upload_log_file():
    # Read the local log file
    try:
        with open(LOG_FILE, 'r') as f:
            log_content = f.read()
    except IOError as e:
        logging.error(f"Error reading log file: {e}")
        return False

    # Filter to keep only last 3 days
    filtered_content = filter_last_days(log_content)
    
    # Connect to FTPS server
    ftps = connect_ftps()
    if not ftps:
        return False

    try:
        # Ensure remote directory exists
        try:
            ftps.cwd(REMOTE_PATH)
        except ftplib.error_perm:
            try:
                ftps.mkd(REMOTE_PATH)
                ftps.cwd(REMOTE_PATH)
            except ftplib.error_perm as e:
                logging.error(f"Could not create remote directory: {e}")
                return False

        # Upload the filtered content
        remote_filename = f"solar_edge_data.log"
        ftps.storbinary(f'STOR {remote_filename}', io.BytesIO(filtered_content.encode('utf-8')))
        logging.info(f"Successfully uploaded {remote_filename} with {filtered_content.count('\n')} lines")
        return True

    except ftplib.all_errors as e:
        logging.error(f"Error uploading file: {e}")
        return False
    finally:
        try:
            ftps.quit()
        except ftplib.all_errors:
            pass

# Main loop
if __name__ == "__main__":
    logging.info("Starting SolarEdge log uploader")
    logging.info(f"Will upload last {DAYS_TO_KEEP} days of data every {UPLOAD_INTERVAL//60} minutes")
    
    while True:
        try:
            upload_log_file()
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
        
        time.sleep(UPLOAD_INTERVAL)

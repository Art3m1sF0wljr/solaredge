import ftplib
import time
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import io
import logging
import subprocess
import threading

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables from a .env file
load_dotenv()

# Configuration
LOG_FILE = '/home/pi/program/solaredge/solar_edge_data.log'
FTP_HOST = os.getenv('FTP_HOST')
FTP_USER = os.getenv('FTP_USER')
FTP_PASS = os.getenv('FTP_PASS')
REMOTE_PATH = '/solaredge/'
UPLOAD_INTERVAL = 600  # 10 minutes
DAYS_TO_KEEP = 3
MAX_UPLOAD_FAILURE_TIME = 1800  # 30 minutes

# Global variables
last_successful_upload = time.time()
upload_lock = threading.Lock()

def reboot_device():
    logging.warning("No successful uploads in 30 minutes. Rebooting device...")
    try:
        subprocess.run(['sudo', 'reboot'], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to reboot device: {e}")

def watchdog_timer():
    """Independent thread that checks for upload failures"""
    while True:
        time.sleep(605)  # Check every 10 minutes &5 seconds
        with upload_lock:
            time_since_last_success = time.time() - last_successful_upload
            if time_since_last_success > MAX_UPLOAD_FAILURE_TIME:
                logging.error(f"Watchdog triggered: {time_since_last_success//60} minutes since last upload")
                reboot_device()

def filter_last_days(log_content):
    cutoff = datetime.now() - timedelta(days=DAYS_TO_KEEP)
    filtered_lines = []
    
    for line in log_content.split('\n'):
        if not line.strip():
            continue
            
        try:
            timestamp_str = line.split(',')[0]
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%f')
            
            if timestamp >= cutoff:
                filtered_lines.append(line)
        except (IndexError, ValueError) as e:
            logging.warning(f"Error parsing line: {line} - {str(e)}")
            continue
            
    return '\n'.join(filtered_lines)

def connect_ftps():
    try:
        ftps = ftplib.FTP_TLS(FTP_HOST)
        ftps.login(FTP_USER, FTP_PASS)
        ftps.prot_p()
        ftps.set_pasv(True)
        logging.info("Successfully connected to the FTPS server.")
        return ftps
    except ftplib.all_errors as e:
        logging.error(f"FTPS connection error: {e}")
        return None

def upload_log_file():
    global last_successful_upload
    
    try:
        with open(LOG_FILE, 'r') as f:
            log_content = f.read()
    except IOError as e:
        logging.error(f"Error reading log file: {e}")
        return False

    filtered_content = filter_last_days(log_content)
    
    ftps = connect_ftps()
    if not ftps:
        return False

    try:
        try:
            ftps.cwd(REMOTE_PATH)
        except ftplib.error_perm:
            try:
                ftps.mkd(REMOTE_PATH)
                ftps.cwd(REMOTE_PATH)
            except ftplib.error_perm as e:
                logging.error(f"Could not create remote directory: {e}")
                return False

        remote_filename = f"solar_edge_data.log"
        ftps.storbinary(f'STOR {remote_filename}', io.BytesIO(filtered_content.encode('utf-8')))
        logging.info(f"Successfully uploaded {remote_filename} with some lines")
        
        with upload_lock:
            last_successful_upload = time.time()
        return True

    except ftplib.all_errors as e:
        logging.error(f"Error uploading file: {e}")
        return False
    finally:
        try:
            ftps.quit()
        except ftplib.all_errors:
            pass

def main_loop():
    """Main upload loop with exception handling"""
    while True:
        try:
            success = upload_log_file()
            
            # Additional check after each upload
            with upload_lock:
                time_since_last_success = time.time() - last_successful_upload
                if time_since_last_success > MAX_UPLOAD_FAILURE_TIME:
                    logging.error(f"Main loop detected failure: {time_since_last_success//60} minutes since last upload")
                    reboot_device()
                    
        except Exception as e:
            logging.error(f"Unexpected error in main loop: {e}")
            # Check time since last success on exception
            with upload_lock:
                time_since_last_success = time.time() - last_successful_upload
                if time_since_last_success > MAX_UPLOAD_FAILURE_TIME:
                    logging.error(f"Exception triggered reboot check: {time_since_last_success//60} minutes since last upload")
                    reboot_device()
        
        time.sleep(UPLOAD_INTERVAL)

if __name__ == "__main__":
    logging.info("Starting SolarEdge log uploader")
    logging.info(f"Will upload last {DAYS_TO_KEEP} days of data every {UPLOAD_INTERVAL//60} minutes")
    
    # Start watchdog thread
    watchdog_thread = threading.Thread(target=watchdog_timer, daemon=True)
    watchdog_thread.start()
    
    # Start main loop
    main_loop()

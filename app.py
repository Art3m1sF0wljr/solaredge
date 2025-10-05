import socket
import struct
import time
from datetime import datetime
from collections import OrderedDict

# Database configuration
DB_FILE = "/home/pi/program/solaredge/solar_edge_data.log"
LOG_INTERVAL = 60  # seconds

class SolarEdgeModbusReader:
    def __init__(self, host, port=1502, timeout=20, unit_id=1):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.unit_id = unit_id
        self.delay_between_requests = 0.5  # seconds

        # Register definitions with scale factors - updated with correct types
        self.registers = OrderedDict([
            # Identification
            (40000, {'name': 'C_SunSpec_ID', 'type': 'string', 'length': 2}),
            (40004, {'name': 'C_Manufacturer', 'type': 'string', 'length': 16}),
            (40020, {'name': 'C_Model', 'type': 'string', 'length': 16}),
            (40044, {'name': 'C_Version', 'type': 'string', 'length': 8}),
            (40052, {'name': 'C_SerialNumber', 'type': 'string', 'length': 16}),

            # AC Measurements
            (40071, {'name': 'I_AC_Current', 'type': 'uint16', 'sf': 40075, 'invalid': 0xFFFF}),
            (40072, {'name': 'I_AC_CurrentA', 'type': 'uint16', 'sf': 40075, 'invalid': 0xFFFF}),
            (40075, {'name': 'I_AC_Current_SF', 'type': 'int16'}),
            (40076, {'name': 'I_AC_VoltageAB', 'type': 'uint16', 'sf': 40082, 'invalid': 0xFFFF}),
            (40079, {'name': 'I_AC_VoltageAN', 'type': 'uint16', 'sf': 40082, 'invalid': 0xFFFF}),
            (40082, {'name': 'I_AC_Voltage_SF', 'type': 'int16'}),
            (40083, {'name': 'I_AC_Power', 'type': 'int16', 'sf': 40084, 'invalid': 0x8000}),
            (40084, {'name': 'I_AC_Power_SF', 'type': 'int16'}),
            (40085, {'name': 'I_AC_Frequency', 'type': 'uint16', 'sf': 40086, 'invalid': 0xFFFF}),
            (40086, {'name': 'I_AC_Frequency_SF', 'type': 'int16'}),
            (40093, {'name': 'I_AC_Energy_WH', 'type': 'acc32', 'sf': 40095}),
            (40095, {'name': 'I_AC_Energy_WH_SF', 'type': 'uint16'}),

            # DC Measurements
            (40096, {'name': 'I_DC_Current', 'type': 'uint16', 'sf': 40097, 'invalid': 0xFFFF}),
            (40097, {'name': 'I_DC_Current_SF', 'type': 'int16'}),
            (40098, {'name': 'I_DC_Voltage', 'type': 'uint16', 'sf': 40099, 'invalid': 0xFFFF}),
            (40099, {'name': 'I_DC_Voltage_SF', 'type': 'int16'}),
            (40100, {'name': 'I_DC_Power', 'type': 'int16', 'sf': 40101, 'invalid': 0x8000}),
            (40101, {'name': 'I_DC_Power_SF', 'type': 'int16'}),

            # Status
            (40107, {'name': 'I_Status', 'type': 'uint16'}),
            (40103, {'name': 'I_Temp_Sink', 'type': 'int16', 'sf': 40106, 'invalid': 0x8000}),
            (40106, {'name': 'I_Temp_SF', 'type': 'int16'}),
        ])

        self.status_descriptions = {
            1: "Off", 2: "Sleeping (Night)", 3: "Grid Monitoring",
            4: "Producing Power", 5: "Production Curtailed", 6: "Shutting Down",
            7: "Fault", 8: "Maintenance"
        }

    def _create_connection(self):
        """Create a new connection for each request"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            return sock
        except Exception as e:
            raise Exception(f"Connection failed: {str(e)}")

    def _read_registers(self, start_addr, count):
        """Read registers with a fresh connection each time"""
        sock = None
        try:
            sock = self._create_connection()

            # Create request
            transaction_id = 1
            protocol_id = 0
            length = 6
            reg_addr = start_addr - 40000

            request = struct.pack('>HHHBBHH',
                                transaction_id,
                                protocol_id,
                                length,
                                self.unit_id,
                                0x03,
                                reg_addr,
                                count)

            # Send request
            sock.sendall(request)

            # Wait briefly before reading
            time.sleep(0.1)

            # Read response
            response = sock.recv(1024)

            if not response:
                raise ValueError("Empty response")

            # Basic validation
            if len(response) < 8:
                raise ValueError(f"Response too short ({len(response)} bytes)")

            # Check for Modbus error response
            if response[7] == 0x83:
                error_code = response[8]
                raise ValueError(f"Modbus error {error_code}")

            # Verify length matches expected
            expected_length = 9 + count * 2
            if len(response) < expected_length:
                raise ValueError(f"Response too short for {count} registers")

            # Extract data
            data = response[9:9 + count*2]
            values = [struct.unpack('>H', data[i*2:i*2+2])[0] for i in range(count)]

            return values

        except struct.error as e:
            raise ValueError(f"Invalid response format: {str(e)}")
        except socket.timeout:
            raise Exception("Timeout waiting for response")
        finally:
            if sock:
                sock.close()
            time.sleep(self.delay_between_requests)

    def _read_string(self, start_addr, length):
        """Read a string from registers"""
        reg_count = (length + 1) // 2  # Each register holds 2 chars
        values = self._read_registers(start_addr, reg_count)
        bytes_data = b''.join(struct.pack('>H', val) for val in values)
        return bytes_data[:length].decode('ascii', errors='ignore').strip('\x00')

    def _validate_scale_factor(self, sf):
        """Validate scale factor is within reasonable bounds"""
        if sf is None:
            return 0
        if sf < -5 or sf > 5:  # SolarEdge typically uses -3 to +3
            print(f"Warning: Unusual scale factor {sf}, defaulting to 0")
            return 0
        return sf

    def _apply_scale_factor(self, value, scale_factor):
        """Apply scale factor to raw value with validation"""
        sf = self._validate_scale_factor(scale_factor)
        return value * (10 ** sf)

    def _is_valid_value(self, reg_info, value):
        """Check if value is valid (not the 'invalid' marker)"""
        if 'invalid' in reg_info:
            if reg_info['type'] == 'int16' and value == reg_info['invalid'] - 65536:
                return False
            elif value == reg_info['invalid']:
                return False
        return True

    def _get_scale_factor(self, reg_info):
        """Get the current scale factor for a register"""
        if 'sf' not in reg_info:
            return None
            
        sf_addr = reg_info['sf']
        sf_reg = self.registers.get(sf_addr)
        if not sf_reg:
            return None
            
        try:
            values = self._read_registers(sf_addr, 1)
            sf = values[0]
            
            # Handle signed scale factors
            if sf_reg['type'] == 'int16' and sf > 32767:
                sf = sf - 65536
                
            return sf
        except Exception as e:
            print(f"Warning: Could not read scale factor {sf_reg['name']}: {str(e)}")
            return None

    def read_all(self):
        """Read all registers with proper scaling and error handling"""
        results = {}

        for addr, reg_info in self.registers.items():
            if reg_info['type'].endswith('_SF'):
                continue  # Skip scale factor registers - we'll read them when needed

            try:
                if reg_info['type'] == 'string':
                    value = self._read_string(addr, reg_info['length'])
                    results[reg_info['name']] = value

                elif reg_info['type'] == 'acc32':
                    # Read 2 registers for 32-bit value
                    values = self._read_registers(addr, 2)
                    raw_value = (values[0] << 16) | values[1]
                    
                    # Get fresh scale factor for this reading
                    sf = self._get_scale_factor(reg_info)
                    value = self._apply_scale_factor(raw_value, sf)
                    results[reg_info['name']] = value

                else:
                    # Read single register
                    values = self._read_registers(addr, 1)
                    raw_value = values[0]
                    
                    # Handle signed values
                    if reg_info['type'] == 'int16' and raw_value > 32767:
                        raw_value = raw_value - 65536

                    # Check for invalid values
                    if not self._is_valid_value(reg_info, raw_value):
                        results[reg_info['name']] = None
                        continue

                    # Get fresh scale factor for this reading
                    sf = self._get_scale_factor(reg_info)
                    value = self._apply_scale_factor(raw_value, sf)
                    results[reg_info['name']] = value

                    # Special handling for status
                    if reg_info['name'] == 'I_Status':
                        results['I_Status_Description'] = self.status_descriptions.get(
                            values[0], f"Unknown status ({values[0]})")

            except Exception as e:
                print(f"Warning: Could not read {reg_info['name']} at {addr}: {str(e)}")
                results[reg_info['name']] = None

        return results

def format_value(name, value, unit=None):
    """Format values for nice display with improved validation"""
    if value is None:
        return "N/A"

    # Handle special cases for invalid values
    if name == 'I_AC_VoltageAN' and (value > 1000 or value < 0):  # Unrealistic voltage
        return "N/A"
    if name == 'I_AC_Frequency' and (value < 45 or value > 55):  # Invalid frequency
        return "N/A"
    if name == 'I_Temp_Sink' and (value < -20 or value > 100):  # Impossible temp
        return "N/A"

    if 'Energy' in name:
        if value >= 1000000:
            return f"{value/1000000:.3f} MWh"
        return f"{value/1000:.3f} kWh"
    elif 'Power' in name:
        if abs(value) >= 1000:
            return f"{value/1000:.3f} kW"
        return f"{value:.1f} W"
    elif 'Current' in name:
        return f"{value:.3f} A"
    elif 'Voltage' in name:
        return f"{value:.2f} V"
    elif 'Frequency' in name:
        return f"{value:.3f} Hz"
    elif 'Temp' in name:
        return f"{value:.1f} Â°C"
    elif unit:
        return f"{value} {unit}"
    return f"{value:.3f}"

def save_to_database(data):
    """Append data to the database text file with improved formatting"""
    try:
        # Safely format all values, handling None cases
        timestamp = data.get('timestamp', 'N/A')
        ac_power = data.get('ac_power', 0.0) or 0.0
        dc_power = data.get('dc_power', 0.0) or 0.0
        state = data.get('state', 'Unknown')
        energy = data.get('energy', 0.0) or 0.0
        ac_current = data.get('ac_current', 0.0) or 0.0
        dc_current = data.get('dc_current', 0.0) or 0.0
        ac_voltage = data.get('ac_voltage', 0.0) or 0.0
        temp_sink = data.get('temp_sink', 0.0) or 0.0
        
        with open(DB_FILE, 'a') as f:
            f.write(f"{timestamp}, "
                    f"AC Power: {ac_power:.1f} W, "
                    f"DC Power: {dc_power:.1f} W, "
                    f"State: {state}, "  # No formatting on string
                    f"Energy: {energy:.6f} MWh, "
                    f"AC Current: {ac_current:.3f} A, "
                    f"DC Current: {dc_current:.3f} A, "
                    f"AC Voltage: {ac_voltage:.2f} V, "
                    f"Heat Sink Temp: {temp_sink:.1f} Â°C\n")
    except Exception as e:
        print(f"Error saving to database: {str(e)}")

def main():
    print("SolarEdge Modbus Reader with Improved Scaling")
    print("-------------------------------------------")
    print(f"Data will be logged to {DB_FILE} every {LOG_INTERVAL} seconds\n")

    # Configuration
    inverter_ip = "192.168.8.231"
    modbus_port = 1502
    unit_id = 1

    reader = SolarEdgeModbusReader(inverter_ip, port=modbus_port, unit_id=unit_id)

    try:
        while True:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Reading data...")
            start_time = time.time()
            data = reader.read_all()
            elapsed = time.time() - start_time

            # Display results
            print("\n=== Inverter Information ===")
            print(f"Manufacturer: {data.get('C_Manufacturer', 'N/A')}")
            print(f"Model:        {data.get('C_Model', 'N/A')}")
            print(f"Version:      {data.get('C_Version', 'N/A')}")
            print(f"Serial:       {data.get('C_SerialNumber', 'N/A')}")

            print("\n=== AC Measurements ===")
            ac_power = data.get('I_AC_Power')
            print(f"Power:        {format_value('I_AC_Power', ac_power)}")
            print(f"Voltage (A-N): {format_value('I_AC_VoltageAN', data.get('I_AC_VoltageAN'))}")
            print(f"Voltage (A-B): {format_value('I_AC_VoltageAB', data.get('I_AC_VoltageAB'))}")
            print(f"Current:      {format_value('I_AC_Current', data.get('I_AC_Current'))}")
            print(f"Frequency:    {format_value('I_AC_Frequency', data.get('I_AC_Frequency'))}")
            energy = data.get('I_AC_Energy_WH')
            print(f"Energy:       {format_value('I_AC_Energy_WH', energy)}")

            print("\n=== DC Measurements ===")
            dc_power = data.get('I_DC_Power')
            print(f"Power:        {format_value('I_DC_Power', dc_power)}")
            print(f"Voltage:      {format_value('I_DC_Voltage', data.get('I_DC_Voltage'))}")
            print(f"Current:      {format_value('I_DC_Current', data.get('I_DC_Current'))}")

            print("\n=== Status ===")
            state = data.get('I_Status_Description', 'N/A')
            print(f"State:        {state}")
            print(f"Heat Sink:    {format_value('I_Temp_Sink', data.get('I_Temp_Sink'))}")

            print(f"\nData read completed in {elapsed:.2f} seconds")

            # Prepare data for logging
                        # Prepare data for logging
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'ac_power': ac_power if ac_power is not None else 0.0,
                'dc_power': dc_power if dc_power is not None else 0.0,
                'state': state,
                'energy': energy / 1000000 if energy is not None else 0.0,  # Convert to MWh
                'ac_current': data.get('I_AC_Current', 0.0),
                'dc_current': data.get('I_DC_Current', 0.0),
                'ac_voltage': data.get('I_AC_VoltageAN', 0.0),
                'temp_sink': data.get('I_Temp_Sink', 0.0)
            }

            # Save to database
            save_to_database(log_data)
            print(f"\n[{log_data['timestamp']}] Data logged successfully")

            # Wait for next reading
            if LOG_INTERVAL > elapsed:
                remaining = LOG_INTERVAL - elapsed
                print(f"\nWaiting for next reading in {remaining:.1f} seconds...")
                time.sleep(remaining)

    except KeyboardInterrupt:
        print("\n\nSolarEdge Modbus Reader stopped.")
    except Exception as e:
        print(f"\nFatal error: {str(e)}")

if __name__ == "__main__":
    main()

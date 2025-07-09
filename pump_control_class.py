from pymodbus.client.sync import ModbusSerialClient as ModbusClient
import time
import serial.tools.list_ports

class PumpController:
    """
    A class to control pumps via Modbus RTU communication.
    
    Attributes:
        sn (str): Serial number of the pump
        baudrate (int): Baud rate for serial communication
        unit_id (int): Modbus slave address (check DIP switches on pump)
        max_rpm (int): Maximum allowed RPM for the pump
        client: Modbus client instance
    """
    
    # Modbus register addresses
    COIL_START_STOP = 0
    REG_TARGET_RPM = 2
    REG_MAX_RPM = 4
    REG_OPERATION_MODE = 9
    REG_TARGET_ANGLE = 10
    REG_DIRECTION = 12
    REG_COMMUNICATION = 14
    
    # Constants
    OPERATION_MODE_CONTINUOUS = 0
    OPERATION_MODE_ANGLE = 1
    DIRECTION_CW = 1
    DIRECTION_CCW = 0
    COMM_RS485 = 1
    COMM_IO = 0
    
    def __init__(self, sn, baudrate=9600, unit_id=1, max_rpm=600):
        """
        Initialize the pump controller.
        
        Args:
            sn (str): Serial number of the pump
            baudrate (int): Baud rate for serial communication
            unit_id (int): Modbus slave address
            max_rpm (int): Maximum allowed RPM for the pump
        """
        self.sn = sn
        self.baudrate = baudrate
        self.unit_id = unit_id
        self.max_rpm = max_rpm
        self.client = None
        self.connected = False

    @staticmethod
    def _find_port_by_sn(sn):
        """
        Find the port of the pump by its serial number.
        
        Args:
            sn (str): Serial number of the pump
        """
        for port in serial.tools.list_ports.comports():
            if sn in port.description:
                return port.device
        return None

    def connect(self):
        """
        Establish connection to the pump via Modbus RTU.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.client = ModbusClient(
                method='rtu',
                port=PumpController._find_port_by_sn(self.sn),
                baudrate=self.baudrate,
                stopbits=1,
                bytesize=8,
                parity='N',
                timeout=1
            )
            
            if self.client.connect():
                self.connected = True
                print(f"Connected to pump {self.sn} (Unit ID: {self.unit_id})")
                
                # Initialize pump settings
                self._initialize_pump()
                return True
            else:
                print(f"Failed to connect to pump {self.sn}")
                return False
                
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def set_client(self, client):
        self.client = client
        self.connected = True
        self._initialize_pump()
    
    def _initialize_pump(self):
        """Initialize pump with default settings."""
        try:
            # Set communication mode to RS485
            self.client.write_register(
                self.REG_COMMUNICATION, 
                self.COMM_RS485, 
                unit=self.unit_id
            )
            
            # Set operation mode to continuous
            self.client.write_register(
                self.REG_OPERATION_MODE, 
                self.OPERATION_MODE_CONTINUOUS, 
                unit=self.unit_id
            )
            
            # Set max RPM
            self.client.write_registers(
                self.REG_MAX_RPM, 
                [0, self.max_rpm * 100], 
                unit=self.unit_id
            )
            
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Error initializing pump: {e}")
    
    def run(self, rpm, duration=None, reverse=False):
        """
        Run the pump at specified RPM for a given duration.
        
        Args:
            rpm (int): Desired speed in RPM
            duration (float): Duration to run in seconds, if None, run continuously without stopping
            reverse (bool): If True, run counterclockwise; if False, run clockwise
            
        Returns:
            bool: True if operation successful, False otherwise
        """
        if not self.connected:
            print("Not connected to pump. Call connect() first.")
            return False
        
        if rpm > self.max_rpm:
            print(f"Requested RPM ({rpm}) exceeds max RPM ({self.max_rpm}). Setting to max.")
            rpm = self.max_rpm
        
        if rpm < 0:
            print("RPM must be positive")
            return False
        
        try:
            # Set direction
            direction = self.DIRECTION_CCW if reverse else self.DIRECTION_CW
            self.client.write_register(
                self.REG_DIRECTION, 
                direction, 
                unit=self.unit_id
            )
            
            # Set target RPM (multiply by 100 as per protocol)
            self.client.write_registers(
                self.REG_TARGET_RPM, 
                [0, rpm * 100], 
                unit=self.unit_id
            )
            
            time.sleep(0.1)
            
            # Start pump
            self.client.write_coil(
                self.COIL_START_STOP, 
                True, 
                unit=self.unit_id
            )
            
            direction_str = "CCW" if reverse else "CW"
            print(f"Pump started: {rpm} RPM, {direction_str}, {duration}s duration")
            
            # Run for specified duration
            if duration is not None:
                time.sleep(duration)
            
                # Stop pump
                self.client.write_coil(
                    self.COIL_START_STOP, 
                    False, 
                    unit=self.unit_id
                )
                
            print("Pump stopped")
            return True
            
        except Exception as e:
            print(f"Error during pump operation: {e}")
            # Try to stop pump in case of error
            try:
                self.client.write_coil(self.COIL_START_STOP, False, unit=self.unit_id)
            except:
                pass
            return False
    
    def stop(self):
        """Emergency stop the pump."""
        if self.connected and self.client:
            try:
                self.client.write_coil(
                    self.COIL_START_STOP, 
                    False, 
                    unit=self.unit_id
                )
                print("Pump stopped")
            except Exception as e:
                print(f"Error stopping pump: {e}")
    
    def disconnect(self):
        """Disconnect from the pump."""
        if self.client:
            try:
                # Ensure pump is stopped before disconnecting
                self.stop()
                self.client.close()
                self.connected = False
                print("Disconnected from pump")
            except Exception as e:
                print(f"Error during disconnect: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


class SimulatedPumpController:
    """
    A simulated pump controller for testing and development purposes.
    Provides the same interface as PumpController but without requiring actual hardware.
    
    Attributes:
        port (str): Simulated serial port
        baudrate (int): Simulated baud rate
        unit_id (int): Simulated Modbus slave address
        max_rpm (int): Maximum allowed RPM for the simulated pump
        current_rpm (int): Current RPM of the simulated pump
        is_running (bool): Whether the simulated pump is currently running
        direction (str): Current direction ('CW' or 'CCW')
    """
    
    def __init__(self, sn, baudrate=9600, unit_id=1, max_rpm=600):
        """
        Initialize the simulated pump controller.
        
        Args:
            port (str): Simulated serial port
            baudrate (int): Simulated baud rate
            unit_id (int): Simulated Modbus slave address
            max_rpm (int): Maximum allowed RPM for the simulated pump
        """
        self.sn = sn
        self.baudrate = baudrate
        self.unit_id = unit_id
        self.max_rpm = max_rpm
        self.connected = False
        self.current_rpm = 0
        self.is_running = False
        self.direction = 'CW'
        self.start_time = None
        self.client = None
    
    def connect(self):
        """
        Simulate connection to the pump.
        
        Returns:
            bool: Always True for simulation
        """
        self.connected = True
        print(f"[SIMULATED] Connected to pump on {self.sn} (Unit ID: {self.unit_id})")
        return True
    
    def set_client(self, client):
        self.client = client
        self.connected = True
    
    def run(self, rpm, duration=None, reverse=False):
        """
        Simulate running the pump at specified RPM for a given duration.
        
        Args:
            rpm (int): Desired speed in RPM
            duration (float): Duration to run in seconds, if None, run continuously
            reverse (bool): If True, simulate counterclockwise; if False, simulate clockwise
            
        Returns:
            bool: True if operation successful, False otherwise
        """
        if not self.connected:
            print("[SIMULATED] Not connected to pump. Call connect() first.")
            return False
        
        if rpm > self.max_rpm:
            print(f"[SIMULATED] Requested RPM ({rpm}) exceeds max RPM ({self.max_rpm}). Setting to max.")
            rpm = self.max_rpm
        
        if rpm < 0:
            print("[SIMULATED] RPM must be positive")
            return False
        
        try:
            # Simulate pump startup
            self.current_rpm = rpm
            self.is_running = True
            self.direction = "CCW" if reverse else "CW"
            self.start_time = time.time()
            
            direction_str = "CCW" if reverse else "CW"
            duration_str = f"{duration}s" if duration is not None else "continuous"
            print(f"[SIMULATED] Pump started: {rpm} RPM, {direction_str}, {duration_str} duration")
            
            # Simulate running for specified duration
            if duration is not None:
                time.sleep(duration)
                
                # Simulate stopping
                self.current_rpm = 0
                self.is_running = False
                print("[SIMULATED] Pump stopped")
            else:
                print("[SIMULATED] Pump running continuously (call stop() to stop)")
            
            return True
            
        except Exception as e:
            print(f"[SIMULATED] Error during pump operation: {e}")
            self.current_rpm = 0
            self.is_running = False
            return False
    
    def stop(self):
        """Emergency stop the simulated pump."""
        if self.connected:
            self.current_rpm = 0
            self.is_running = False
            print("[SIMULATED] Pump stopped")
        else:
            print("[SIMULATED] Cannot stop pump - not connected")
    
    def get_status(self):
        """
        Get current status of the simulated pump.
        
        Returns:
            dict: Dictionary containing current pump status
        """
        runtime = time.time() - self.start_time if self.start_time and self.is_running else 0
        return {
            'connected': self.connected,
            'running': self.is_running,
            'rpm': self.current_rpm,
            'direction': self.direction,
            'max_rpm': self.max_rpm,
            'runtime_seconds': runtime,
            'sn': self.sn,
            'unit_id': self.unit_id
        }
    
    def disconnect(self):
        """Disconnect from the simulated pump."""
        if self.is_running:
            self.stop()
        
        self.connected = False
        self.current_rpm = 0
        self.is_running = False
        self.start_time = None
        print("[SIMULATED] Disconnected from pump")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()


import sys
import time
import configparser
import os
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

from pump_control_class import PumpController, SimulatedPumpController


class PumpControlGUI(QWidget):
    def __init__(self, pump_dispenser, pump_retractor, config):
        super().__init__()

        self.pump_dispenser = pump_dispenser
        self.pump_retractor = pump_retractor
        self.config = config

        self.setWindowTitle("Pump Control")
        self.setGeometry(100, 100, 300, 200)

        # Create buttons
        self.fill_button = QPushButton("Fill Tubing")
        self.dispense_button = QPushButton("Dispense Water")
        self.retract_button = QPushButton("Drain Water")

        # Connect buttons to functions
        self.fill_button.clicked.connect(self.fill)
        self.dispense_button.clicked.connect(self.dispense)
        self.retract_button.clicked.connect(self.drain)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.fill_button)
        layout.addWidget(self.dispense_button)
        layout.addWidget(self.retract_button)

        self.setLayout(layout)

    def fill(self):
        retractor_rpm = self.config.getint('operation_settings', 'retractor_rpm')
        dispenser_rpm = self.config.getint('operation_settings', 'fill_dispenser_rpm')
        duration = self.config.getint('operation_settings', 'fill_duration')
        sleep_time = self.config.getint('operation_settings', 'operation_sleep')
        
        self.pump_retractor.run(rpm=retractor_rpm, reverse=True)
        self.pump_dispenser.run(rpm=dispenser_rpm, duration=duration, reverse=False)
        time.sleep(sleep_time)
        self.pump_retractor.stop()

    def dispense(self):
        retractor_rpm = self.config.getint('operation_settings', 'retractor_rpm')
        dispenser_rpm = self.config.getint('operation_settings', 'dispense_dispenser_rpm')
        duration = self.config.getint('operation_settings', 'dispense_duration')
        sleep_time = self.config.getint('operation_settings', 'operation_sleep')
        
        self.pump_retractor.run(rpm=retractor_rpm, reverse=True)
        self.pump_dispenser.run(rpm=dispenser_rpm, duration=duration, reverse=False)
        time.sleep(sleep_time)
        self.pump_retractor.stop()

    def drain(self):
        retractor_rpm = self.config.getint('operation_settings', 'retractor_rpm')
        dispenser_rpm = self.config.getint('operation_settings', 'drain_dispenser_rpm')
        duration = self.config.getint('operation_settings', 'drain_duration')
        
        self.pump_retractor.run(rpm=retractor_rpm, reverse=True)
        self.pump_dispenser.run(rpm=dispenser_rpm, duration=duration, reverse=True)
        self.pump_retractor.stop()
        self.pump_dispenser.stop()


def load_config():
    """Load configuration from config.ini file."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    config.read(config_path)
    return config


if __name__ == "__main__":
    # Load configuration
    config = load_config()
    
    # Get pump settings from config
    serial_number = config.get('pump_hardware', 'serial_number')
    baudrate = config.getint('pump_hardware', 'baudrate')
    max_rpm = config.getint('pump_hardware', 'max_rpm')
    dispenser_unit_id = config.getint('pump_dispenser', 'unit_id')
    retractor_unit_id = config.getint('pump_retractor', 'unit_id')
    
    app = QApplication(sys.argv)
    
    # Initialize pumps with config values
    pump_dispenser = PumpController(
        sn=serial_number, 
        baudrate=baudrate, 
        unit_id=dispenser_unit_id, 
        max_rpm=max_rpm
    )
    pump_dispenser.connect()
    
    pump_retractor = PumpController(
        sn=serial_number, 
        baudrate=baudrate, 
        unit_id=retractor_unit_id, 
        max_rpm=max_rpm
    )
    pump_retractor.set_client(pump_dispenser.client)
    
    window = PumpControlGUI(pump_dispenser, pump_retractor, config)
    window.show()
    sys.exit(app.exec_())

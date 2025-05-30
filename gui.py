import sys
import time
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

from pump_control_class import PumpController, SimulatedPumpController


class PumpControlGUI(QWidget):
    def __init__(self, pump_dispenser, pump_retractor):
        super().__init__()

        self.pump_dispenser = pump_dispenser
        self.pump_retractor = pump_retractor

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
        self.pump_retractor.run(rpm=200, reverse=False)
        self.pump_dispenser.run(rpm=20, duration=10, reverse=False)
        time.sleep(1)
        self.pump_retractor.stop()

    def dispense(self):
        self.pump_retractor.run(rpm=200, reverse=False)
        self.pump_dispenser.run(rpm=20, duration=5, reverse=False)
        time.sleep(1)
        self.pump_retractor.stop()

    def drain(self):
        self.pump_retractor.run(rpm=200, reverse=True)
        self.pump_dispenser.run(rpm=200, duration=10, reverse=True)
        self.pump_retractor.stop()
        self.pump_dispenser.stop()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pump_dispenser = PumpController(port='/dev/ttyUSB0', baudrate=9600, unit_id=1, max_rpm=600)
    pump_dispenser.connect()
    pump_retractor = PumpController(port='/dev/ttyUSB0', baudrate=9600, unit_id=2, max_rpm=600)
    pump_retractor.set_client(pump_dispenser.client)
    window = PumpControlGUI(pump_dispenser, pump_retractor)
    window.show()
    sys.exit(app.exec_())

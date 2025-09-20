import sys
import time
import configparser
import os
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QProgressBar,
    QLabel,
    QGroupBox,
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

from pump_control_class import PumpController, SimulatedPumpController


class PumpOperationThread(QThread):
    """Thread for running pump operations without blocking the GUI."""

    operation_completed = pyqtSignal(str, bool)  # operation_name, success
    progress_update = pyqtSignal(int, int)  # current_time, total_time

    def __init__(self, pump_dispenser, pump_retractor, operation_name, config):
        super().__init__()
        self.pump_dispenser = pump_dispenser
        self.pump_retractor = pump_retractor
        self.operation_name = operation_name
        self.config = config
        self.is_running = False

    def run_fill(self):
        """Run fill operation with progress updates."""
        retractor_rpm = self.config.getint("operation_settings", "retractor_rpm")
        dispenser_rpm = self.config.getint("operation_settings", "fill_dispenser_rpm")
        duration = self.config.getint("operation_settings", "fill_duration")
        sleep_time = self.config.getint("operation_settings", "operation_sleep")

        total_time = duration + sleep_time
        start_time = time.time()

        # Start pumps (without duration parameter to avoid blocking)
        self.pump_retractor.run(rpm=retractor_rpm, reverse=True)
        self.pump_dispenser.run(rpm=dispenser_rpm, reverse=False)

        # Run dispenser for specified duration with progress updates
        dispenser_end_time = start_time + duration
        while self.is_running and time.time() < dispenser_end_time:
            elapsed = time.time() - start_time
            self.progress_update.emit(int(elapsed), total_time)
            time.sleep(0.1)  # Small sleep to prevent excessive CPU usage

        # Stop dispenser after duration
        if self.is_running:
            self.pump_dispenser.stop()

            # Continue with sleep time
            sleep_end_time = dispenser_end_time + sleep_time
            while self.is_running and time.time() < sleep_end_time:
                elapsed = time.time() - start_time
                self.progress_update.emit(int(elapsed), total_time)
                time.sleep(0.1)

            # Stop retractor
            self.pump_retractor.stop()
            self.operation_completed.emit(self.operation_name, True)
        else:
            self.pump_dispenser.stop()
            self.pump_retractor.stop()
            self.operation_completed.emit(self.operation_name, False)

    def run_dispense(self):
        """Run dispense operation with progress updates."""
        retractor_rpm = self.config.getint("operation_settings", "retractor_rpm")
        dispenser_rpm = self.config.getint(
            "operation_settings", "dispense_dispenser_rpm"
        )
        duration = self.config.getint("operation_settings", "dispense_duration")
        sleep_time = self.config.getint("operation_settings", "operation_sleep")

        total_time = duration + sleep_time
        start_time = time.time()

        # Start pumps (without duration parameter to avoid blocking)
        self.pump_retractor.run(rpm=retractor_rpm, reverse=True)
        self.pump_dispenser.run(rpm=dispenser_rpm, reverse=False)

        # Run dispenser for specified duration with progress updates
        dispenser_end_time = start_time + duration
        while self.is_running and time.time() < dispenser_end_time:
            elapsed = time.time() - start_time
            self.progress_update.emit(int(elapsed), total_time)
            time.sleep(0.1)

        # Stop dispenser after duration
        if self.is_running:
            self.pump_dispenser.stop()

            # Continue with sleep time
            sleep_end_time = dispenser_end_time + sleep_time
            while self.is_running and time.time() < sleep_end_time:
                elapsed = time.time() - start_time
                self.progress_update.emit(int(elapsed), total_time)
                time.sleep(0.1)

            # Stop retractor
            self.pump_retractor.stop()
            self.operation_completed.emit(self.operation_name, True)
        else:
            self.pump_dispenser.stop()
            self.pump_retractor.stop()
            self.operation_completed.emit(self.operation_name, False)

    def run_drain(self):
        """Run drain operation with progress updates."""
        retractor_rpm = self.config.getint("operation_settings", "retractor_rpm")
        dispenser_rpm = self.config.getint("operation_settings", "drain_dispenser_rpm")
        duration = self.config.getint("operation_settings", "drain_duration")

        total_time = duration
        start_time = time.time()

        # Start pumps (without duration parameter to avoid blocking)
        self.pump_retractor.run(rpm=retractor_rpm, reverse=True)
        self.pump_dispenser.run(rpm=dispenser_rpm, reverse=True)

        # Run pumps for specified duration with progress updates
        end_time = start_time + duration
        while self.is_running and time.time() < end_time:
            elapsed = time.time() - start_time
            self.progress_update.emit(int(elapsed), total_time)
            time.sleep(0.1)

        # Stop pumps
        if self.is_running:
            self.pump_retractor.stop()
            self.pump_dispenser.stop()
            self.operation_completed.emit(self.operation_name, True)
        else:
            self.pump_retractor.stop()
            self.pump_dispenser.stop()
            self.operation_completed.emit(self.operation_name, False)

    def run(self):
        """Main thread execution."""
        self.is_running = True
        if self.operation_name == "Fill":
            self.run_fill()
        elif self.operation_name == "Dispense":
            self.run_dispense()
        elif self.operation_name == "Drain":
            self.run_drain()

    def stop_operation(self):
        """Stop the current operation."""
        self.is_running = False
        self.wait()  # Wait for thread to finish


class PumpControlGUI(QWidget):
    def __init__(self, pump_dispenser, pump_retractor, config):
        super().__init__()

        self.pump_dispenser = pump_dispenser
        self.pump_retractor = pump_retractor
        self.config = config
        self.current_operation = None
        self.operation_thread = None

        self.setWindowTitle("Pump Control")
        self.setGeometry(100, 100, 400, 300)

        self.setup_ui()

    def setup_ui(self):
        """Setup the user interface."""
        # Create main layout
        main_layout = QVBoxLayout()

        # Create operation buttons group
        buttons_group = QGroupBox("Operations")
        buttons_layout = QVBoxLayout()

        self.fill_button = QPushButton("Fill Dispenser Tubing")
        self.dispense_button = QPushButton("Dispense Water")
        self.retract_button = QPushButton("Drain Water From Both Tubings")
        self.stop_button = QPushButton("Stop Operation")

        # Connect buttons to functions
        self.fill_button.clicked.connect(self.fill)
        self.dispense_button.clicked.connect(self.dispense)
        self.retract_button.clicked.connect(self.drain)
        self.stop_button.clicked.connect(self.stop_operation)

        # Initially disable stop button
        self.stop_button.setEnabled(False)

        buttons_layout.addWidget(self.fill_button)
        buttons_layout.addWidget(self.dispense_button)
        buttons_layout.addWidget(self.retract_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_group.setLayout(buttons_layout)

        # Create progress group
        progress_group = QGroupBox("Status")
        progress_layout = QVBoxLayout()

        self.operation_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.countdown_label = QLabel("")
        self.status_label = QLabel("")

        progress_layout.addWidget(self.operation_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.countdown_label)
        progress_layout.addWidget(self.status_label)
        progress_group.setLayout(progress_layout)

        # Add groups to main layout
        main_layout.addWidget(buttons_group)
        main_layout.addWidget(progress_group)

        self.setLayout(main_layout)

    def start_operation(self, operation_name):
        """Start a pump operation in a separate thread."""
        if self.current_operation is not None:
            self.status_label.setText("Another operation is already running!")
            return

        self.current_operation = operation_name
        self.operation_label.setText(f"Running: {operation_name}")
        self.status_label.setText("Operation in progress...")
        self.progress_bar.setValue(0)
        self.countdown_label.setText("")

        # Disable operation buttons, enable stop button
        self.fill_button.setEnabled(False)
        self.dispense_button.setEnabled(False)
        self.retract_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        # Create and start operation thread
        self.operation_thread = PumpOperationThread(
            self.pump_dispenser, self.pump_retractor, operation_name, self.config
        )
        self.operation_thread.operation_completed.connect(self.operation_finished)
        self.operation_thread.progress_update.connect(self.update_progress)
        self.operation_thread.start()

    def update_progress(self, current_time, total_time):
        """Update progress bar and countdown."""
        if total_time > 0:
            progress = int((current_time / total_time) * 100)
            self.progress_bar.setValue(progress)

            remaining_time = total_time - current_time
            if remaining_time > 0:
                self.countdown_label.setText(f"Time remaining: {remaining_time:.1f}s")
            else:
                self.countdown_label.setText("Finishing...")

    def operation_finished(self, operation_name, success):
        """Handle operation completion."""
        self.current_operation = None
        self.operation_thread = None

        if success:
            self.status_label.setText(f"{operation_name} completed successfully")
            self.operation_label.setText("Ready")
        else:
            self.status_label.setText(f"{operation_name} was stopped")
            self.operation_label.setText("Ready")

        self.progress_bar.setValue(100)
        self.countdown_label.setText("")

        # Re-enable operation buttons, disable stop button
        self.fill_button.setEnabled(True)
        self.dispense_button.setEnabled(True)
        self.retract_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def stop_operation(self):
        """Stop the current operation."""
        if self.operation_thread is not None:
            self.status_label.setText("Stopping operation...")
            self.operation_thread.stop_operation()

    def fill(self):
        """Start fill operation."""
        self.start_operation("Fill")

    def dispense(self):
        """Start dispense operation."""
        self.start_operation("Dispense")

    def drain(self):
        """Start drain operation."""
        self.start_operation("Drain")


def load_config():
    """Load configuration from config.ini file."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config.ini")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    config.read(config_path)
    return config


if __name__ == "__main__":
    # Load configuration
    config = load_config()

    # Get pump settings from config
    serial_number = config.get("pump_hardware", "serial_number")
    baudrate = config.getint("pump_hardware", "baudrate")
    max_rpm = config.getint("pump_hardware", "max_rpm")
    dispenser_unit_id = config.getint("pump_dispenser", "unit_id")
    retractor_unit_id = config.getint("pump_retractor", "unit_id")

    app = QApplication(sys.argv)

    # Initialize pumps with config values
    pump_dispenser = PumpController(
        sn=serial_number, baudrate=baudrate, unit_id=dispenser_unit_id, max_rpm=max_rpm
    )
    pump_dispenser.connect()

    pump_retractor = PumpController(
        sn=serial_number, baudrate=baudrate, unit_id=retractor_unit_id, max_rpm=max_rpm
    )
    pump_retractor.set_client(pump_dispenser.client)

    window = PumpControlGUI(pump_dispenser, pump_retractor, config)
    window.show()
    sys.exit(app.exec_())

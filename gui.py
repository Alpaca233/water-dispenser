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
    QSpinBox,
    QTimeEdit,
    QFormLayout,
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QTime, QDateTime
from pymodbus.client.sync import ModbusSerialClient as ModbusClient

from pump_control_class import PumpController, SimulatedPumpController


class PumpOperationThread(QThread):
    """Thread for running pump operations without blocking the GUI."""

    operation_completed = pyqtSignal(str, bool)  # operation_name, success
    progress_update = pyqtSignal(int, int)  # current_time, total_time

    def __init__(
        self,
        pump_dispenser,
        pump_retractor,
        operation_name,
        config,
        custom_duration=None,
    ):
        super().__init__()
        self.pump_dispenser = pump_dispenser
        self.pump_retractor = pump_retractor
        self.operation_name = operation_name
        self.config = config
        self.custom_duration = custom_duration
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
        # Use custom duration if provided, otherwise use config value
        duration = (
            self.custom_duration
            if self.custom_duration is not None
            else self.config.getint("operation_settings", "dispense_duration")
        )
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
        # Immediately stop both pumps
        self.pump_dispenser.stop()
        self.pump_retractor.stop()
        # Don't call self.wait() here as it blocks the GUI thread


class PumpControlGUI(QWidget):
    def __init__(self, pump_dispenser, pump_retractor, config):
        super().__init__()

        self.pump_dispenser = pump_dispenser
        self.pump_retractor = pump_retractor
        self.config = config
        self.current_operation = None
        self.operation_thread = None
        self.stop_timer = None

        # Scheduled dispensing variables
        self.scheduled_dispense_active = False
        self.scheduled_timer = QTimer()
        self.countdown_timer = QTimer()
        self.next_dispense_time = None
        self.dispense_interval_minutes = 0
        self.dispense_duration_seconds = 0

        self.setWindowTitle("Pump Control")
        self.setGeometry(100, 100, 500, 600)

        self.setup_ui()
        self.setup_scheduled_dispensing()

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

        # Create scheduled dispensing group
        scheduled_group = QGroupBox("Scheduled Dispensing")
        scheduled_layout = QVBoxLayout()

        # Form layout for settings
        settings_layout = QFormLayout()

        # Dispense interval (minutes)
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 1440)  # 1 minute to 24 hours
        self.interval_spinbox.setValue(30)  # Default 30 minutes
        self.interval_spinbox.setSuffix(" minutes")
        settings_layout.addRow("Dispense Interval:", self.interval_spinbox)

        # Dispense time (duration in seconds)
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setRange(1, 300)  # 1 second to 5 minutes
        self.duration_spinbox.setValue(5)  # Default 5 seconds
        self.duration_spinbox.setSuffix(" seconds")
        settings_layout.addRow("Dispense Duration:", self.duration_spinbox)

        settings_layout.addRow("", QLabel(""))  # Spacer

        # Control buttons
        button_layout = QHBoxLayout()
        self.start_scheduled_button = QPushButton("Start Scheduled Dispensing")
        self.stop_scheduled_button = QPushButton("Stop Scheduled Dispensing")
        self.stop_scheduled_button.setEnabled(False)

        button_layout.addWidget(self.start_scheduled_button)
        button_layout.addWidget(self.stop_scheduled_button)

        # Status labels
        self.scheduled_status_label = QLabel("Scheduled dispensing: Inactive")
        self.next_dispense_label = QLabel("Next dispense: Not scheduled")
        self.countdown_label_scheduled = QLabel("")

        # Connect buttons
        self.start_scheduled_button.clicked.connect(self.start_scheduled_dispensing)
        self.stop_scheduled_button.clicked.connect(self.stop_scheduled_dispensing)

        scheduled_layout.addLayout(settings_layout)
        scheduled_layout.addLayout(button_layout)
        scheduled_layout.addWidget(self.scheduled_status_label)
        scheduled_layout.addWidget(self.next_dispense_label)
        scheduled_layout.addWidget(self.countdown_label_scheduled)
        scheduled_group.setLayout(scheduled_layout)

        # Add groups to main layout
        main_layout.addWidget(buttons_group)
        main_layout.addWidget(progress_group)
        main_layout.addWidget(scheduled_group)

        self.setLayout(main_layout)

    def setup_scheduled_dispensing(self):
        """Setup scheduled dispensing timers and connections."""
        # Connect scheduled timer to dispense function
        self.scheduled_timer.timeout.connect(self.execute_scheduled_dispense)

        # Connect countdown timer to update countdown display
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_timer.start(1000)  # Update every second

        # Load settings from config
        self.load_scheduled_settings()

    def load_scheduled_settings(self):
        """Load scheduled dispensing settings from config."""
        try:
            # Load from config if available, otherwise use defaults
            interval = self.config.getint(
                "scheduled_settings", "default_interval_minutes", fallback=30
            )
            duration = self.config.getint(
                "scheduled_settings", "default_duration_seconds", fallback=5
            )

            self.interval_spinbox.setValue(interval)
            self.duration_spinbox.setValue(duration)
        except:
            # Use defaults if config section doesn't exist
            pass

    def start_scheduled_dispensing(self):
        """Start scheduled dispensing."""
        if self.current_operation is not None:
            self.status_label.setText(
                "Cannot start scheduled dispensing - another operation is running!"
            )
            return

        if self.scheduled_dispense_active:
            self.status_label.setText("Scheduled dispensing is already active!")
            return

        # Get settings from UI
        self.dispense_interval_minutes = self.interval_spinbox.value()
        self.dispense_duration_seconds = self.duration_spinbox.value()

        # Calculate next dispense time
        self.next_dispense_time = QDateTime.currentDateTime().addSecs(
            self.dispense_interval_minutes * 60
        )

        # Start the scheduled timer
        interval_ms = (
            self.dispense_interval_minutes * 60 * 1000
        )  # Convert to milliseconds
        self.scheduled_timer.start(interval_ms)

        # Update UI state
        self.scheduled_dispense_active = True
        self.scheduled_status_label.setText("Scheduled dispensing: Active")
        self.start_scheduled_button.setEnabled(False)
        self.stop_scheduled_button.setEnabled(True)

        # Disable settings controls
        self.interval_spinbox.setEnabled(False)
        self.duration_spinbox.setEnabled(False)

        # Disable other operation buttons
        self.fill_button.setEnabled(False)
        self.retract_button.setEnabled(False)

        self.status_label.setText(
            f"Scheduled dispensing started - interval: {self.dispense_interval_minutes} minutes"
        )
        self.update_next_dispense_display()

    def stop_scheduled_dispensing(self):
        """Stop scheduled dispensing."""
        if not self.scheduled_dispense_active:
            return

        # Stop timers
        self.scheduled_timer.stop()

        # Update UI state
        self.scheduled_dispense_active = False
        self.scheduled_status_label.setText("Scheduled dispensing: Inactive")
        self.start_scheduled_button.setEnabled(True)
        self.stop_scheduled_button.setEnabled(False)

        # Re-enable settings controls
        self.interval_spinbox.setEnabled(True)
        self.duration_spinbox.setEnabled(True)

        # Re-enable other operation buttons
        self.fill_button.setEnabled(True)
        self.retract_button.setEnabled(True)

        # Clear displays
        self.next_dispense_label.setText("Next dispense: Not scheduled")
        self.countdown_label_scheduled.setText("")

        self.status_label.setText("Scheduled dispensing stopped")

    def execute_scheduled_dispense(self):
        """Execute a scheduled dispense operation."""
        if not self.scheduled_dispense_active:
            return

        # Start dispense operation with custom duration
        self.start_operation("Dispense", custom_duration=self.dispense_duration_seconds)

        # Schedule next dispense
        self.next_dispense_time = QDateTime.currentDateTime().addSecs(
            self.dispense_interval_minutes * 60
        )
        self.update_next_dispense_display()

    def update_countdown(self):
        """Update countdown display for next scheduled dispense."""
        if not self.scheduled_dispense_active or self.next_dispense_time is None:
            self.countdown_label_scheduled.setText("")
            return

        current_time = QDateTime.currentDateTime()
        time_until_dispense = current_time.secsTo(self.next_dispense_time)

        if time_until_dispense > 0:
            hours = time_until_dispense // 3600
            minutes = (time_until_dispense % 3600) // 60
            seconds = time_until_dispense % 60

            if hours > 0:
                countdown_text = (
                    f"Next dispense in: {hours:02d}:{minutes:02d}:{seconds:02d}"
                )
            else:
                countdown_text = f"Next dispense in: {minutes:02d}:{seconds:02d}"

            self.countdown_label_scheduled.setText(countdown_text)
        else:
            self.countdown_label_scheduled.setText("Dispensing now...")

    def update_next_dispense_display(self):
        """Update the next dispense time display."""
        if self.next_dispense_time is not None:
            time_str = self.next_dispense_time.toString("yyyy-MM-dd hh:mm:ss")
            self.next_dispense_label.setText(f"Next dispense: {time_str}")
        else:
            self.next_dispense_label.setText("Next dispense: Not scheduled")

    def start_operation(self, operation_name, custom_duration=None):
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

        # Disable scheduled dispensing controls during operation
        self.start_scheduled_button.setEnabled(False)
        self.stop_scheduled_button.setEnabled(False)

        # Create and start operation thread
        self.operation_thread = PumpOperationThread(
            self.pump_dispenser,
            self.pump_retractor,
            operation_name,
            self.config,
            custom_duration,
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
        # Cancel stop timer if running
        if self.stop_timer is not None:
            self.stop_timer.stop()
            self.stop_timer = None

        # Clean up thread
        if self.operation_thread is not None:
            self.operation_thread.quit()
            self.operation_thread.wait()  # Wait for thread to finish
            self.operation_thread = None

        self.current_operation = None

        if success:
            self.status_label.setText(f"{operation_name} completed successfully")
            self.operation_label.setText("Ready")
        else:
            self.status_label.setText(f"{operation_name} was stopped")
            self.operation_label.setText("Ready")

        self.progress_bar.setValue(100)
        self.countdown_label.setText("")

        # Re-enable operation buttons based on scheduled dispensing state
        if self.scheduled_dispense_active:
            # During scheduled dispensing, keep Fill and Drain disabled
            self.fill_button.setEnabled(False)
            self.dispense_button.setEnabled(True)  # Allow manual dispense
            self.retract_button.setEnabled(False)
            self.stop_scheduled_button.setEnabled(True)
            # Keep start button disabled and settings disabled during scheduled dispensing
        else:
            # No scheduled dispensing active, enable all operation buttons
            self.fill_button.setEnabled(True)
            self.dispense_button.setEnabled(True)
            self.retract_button.setEnabled(True)
            self.start_scheduled_button.setEnabled(True)
            self.stop_scheduled_button.setEnabled(False)

        # Always disable stop button when operation finishes
        self.stop_button.setEnabled(False)

    def stop_operation(self):
        """Stop the current operation."""
        if self.operation_thread is not None and self.operation_thread.isRunning():
            self.status_label.setText("Stopping operation...")
            self.operation_thread.stop_operation()
            # Disable stop button immediately to prevent multiple clicks
            self.stop_button.setEnabled(False)

            # Set up a timer to force cleanup if thread doesn't stop gracefully
            self.stop_timer = QTimer()
            self.stop_timer.timeout.connect(self._force_stop_cleanup)
            self.stop_timer.setSingleShot(True)
            self.stop_timer.start(5000)  # 5 second timeout
        else:
            self.status_label.setText("No operation running to stop")

    def _force_stop_cleanup(self):
        """Force cleanup if thread doesn't stop gracefully."""
        if self.operation_thread is not None and self.operation_thread.isRunning():
            self.status_label.setText("Force stopping operation...")
            self.operation_thread.terminate()  # Force terminate the thread
            self.operation_thread.wait(1000)  # Wait up to 1 second
            self.operation_finished("Unknown", False)  # Reset GUI state

        if self.stop_timer is not None:
            self.stop_timer.stop()
            self.stop_timer = None

    def fill(self):
        """Start fill operation."""
        self.start_operation("Fill")

    def dispense(self):
        """Start dispense operation."""
        self.start_operation("Dispense")

    def drain(self):
        """Start drain operation."""
        self.start_operation("Drain")

    def closeEvent(self, event):
        """Handle GUI close event to ensure proper cleanup."""
        # Stop scheduled dispensing
        if self.scheduled_dispense_active:
            self.stop_scheduled_dispensing()

        # Stop any running operation
        if self.operation_thread is not None and self.operation_thread.isRunning():
            self.stop_operation()
            # Give the thread a moment to stop
            self.operation_thread.wait(3000)  # Wait up to 3 seconds

        # Stop timers
        self.scheduled_timer.stop()
        self.countdown_timer.stop()

        # Ensure pumps are stopped
        self.pump_dispenser.stop()
        self.pump_retractor.stop()

        event.accept()


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
    pump_dispenser = SimulatedPumpController(
        sn=serial_number, baudrate=baudrate, unit_id=dispenser_unit_id, max_rpm=max_rpm
    )
    pump_dispenser.connect()

    pump_retractor = SimulatedPumpController(
        sn=serial_number, baudrate=baudrate, unit_id=retractor_unit_id, max_rpm=max_rpm
    )
    pump_retractor.set_client(pump_dispenser.client)

    window = PumpControlGUI(pump_dispenser, pump_retractor, config)
    window.show()
    sys.exit(app.exec_())

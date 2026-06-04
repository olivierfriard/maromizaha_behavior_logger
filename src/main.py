"""
Maromizaha Behavior Logger

- Creates a structured JSON file named with the timestamp of the first save.
- Records scan/session parameters every 5 minutes, storing the actual save time.
- Reuses previous scan values so the operator can validate or correct them.
- Records behavior, GPS, and alimentation events with timestamped saves.
- Lets the operator reopen scan records and correct their values.
- Displays all saved JSON information in a separate screen.
"""

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

from config import *
from translations import (
    current_language,
    language_from_label,
    language_label,
    language_labels,
    set_language,
    tr,
    trf,
)

__version__ = "0.1.0"

DATA_DIR = Path("behavior_logs")
CONFIG_PATH = Path("config.json")
NUMERIC_TEXT_FIELDS = {
    "UTM_north",
    "UTM_south",
    "UTM_east",
}
INTEGER_TEXT_FIELDS = {"UTM S", "UTM E", "Altitude"}
GPS_REQUIRED_INTEGER_FIELDS = ["UTM S", "UTM E", "Altitude"]
GPS_SPINNER_FIELDS = {
    "Z ZD": ["-", "Z", "ZD"],
    ">10 <10 P": ["-", ">10", "<10", "P"],
    "SPV": ["-", "Sommet (S)", "Pente (P)", "Vallée (V)"],
}
TIME_FIELD_NAMES = {"time_start", "time_end", "time start", "time end"}


def current_date_value() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def current_time_values() -> Tuple[str, str]:
    now = datetime.now()
    rounded_minute = (now.minute // 5) * 5
    return now.strftime("%H"), f"{rounded_minute:02d}"


def split_time_value(value: str) -> Tuple[str, str]:
    parts = (value or "").split(":")
    if len(parts) >= 2 and parts[0] in HOUR_VALUES and parts[1] in MINUTE_VALUES:
        return parts[0], parts[1]
    return current_time_values()


def make_text_input(
    text: str = "",
    input_filter: Optional[str] = None,
    readonly: bool = False,
) -> TextInput:
    kwargs: Dict[str, Any] = {
        "text": text,
        "multiline": False,
        "size_hint_y": None,
        "height": dp(42),
        "readonly": readonly,
    }
    if input_filter is not None:
        kwargs["input_filter"] = input_filter
    return TextInput(**kwargs)


def make_spinner(values: List[str], text: str = "") -> Spinner:
    default = text if text in values else values[0]
    return Spinner(text=default, values=values, size_hint_y=None, height=dp(42))


def make_field_widget(field: str, value: str = "") -> Widget:
    if field == "UTM_zone":
        return make_text_input(value or DEFAULT_UTM_ZONE, readonly=True)
    if field in NUMERIC_1_TO_20_FIELDS:
        return make_spinner(NUMERIC_1_TO_20_VALUES, value or "1")
    if field in INTEGER_TEXT_FIELDS:
        return make_text_input(value, input_filter="int")
    if field in GPS_SPINNER_FIELDS:
        return make_spinner(GPS_SPINNER_FIELDS[field], value)
    if field in LIST_FIELDS:
        return make_spinner(LIST_FIELDS[field], value)
    if field in NUMERIC_TEXT_FIELDS:
        return make_text_input(value, input_filter="float")
    return make_text_input(value)


def get_widget_text(widget: Widget) -> str:
    get_value = getattr(widget, "get_value", None)
    if callable(get_value):
        return get_value()
    text = getattr(widget, "text", "")
    if isinstance(widget, TextInput):
        return text.strip()
    return text


def set_widget_text(widget: Widget, value: str) -> None:
    set_value = getattr(widget, "set_value", None)
    if callable(set_value):
        set_value(value)
        return
    if hasattr(widget, "text"):
        widget.text = value


def set_i18n_text(widget: Widget, text: str) -> Widget:
    widget.i18n_text = text
    widget.text = tr(text)
    return widget


def i18n_label(text: str, **kwargs: Any) -> Label:
    return set_i18n_text(Label(**kwargs), text)


def i18n_button(text: str, **kwargs: Any) -> Button:
    return set_i18n_text(Button(**kwargs), text)


def refresh_i18n_tree(widget: Widget) -> None:
    text = getattr(widget, "i18n_text", None)
    if text is not None and hasattr(widget, "text"):
        widget.text = tr(text)
    for child in getattr(widget, "children", []):
        refresh_i18n_tree(child)


class TimeSelector(BoxLayout):
    """Hour/minute selector backed by two dropdowns."""

    def __init__(self, value: str = "", **kwargs: Any) -> None:
        super().__init__(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(42),
            **kwargs,
        )
        hour, minute = split_time_value(value)
        self.hour = make_spinner(HOUR_VALUES, hour)
        self.minute = make_spinner(MINUTE_VALUES, minute)
        separator = Label(
            text=":", size_hint_x=None, width=dp(12), size_hint_y=None, height=dp(42)
        )

        self.add_widget(self.hour)
        self.add_widget(separator)
        self.add_widget(self.minute)

    def get_value(self) -> str:
        return f"{self.hour.text}:{self.minute.text}"

    def set_value(self, value: str) -> None:
        hour, minute = split_time_value(value)
        self.hour.text = hour
        self.minute.text = minute

    def set_now(self) -> None:
        hour, minute = current_time_values()
        self.hour.text = hour
        self.minute.text = minute


class DateTimeInput(BoxLayout):
    """
    Date input and hour/minute dropdowns on one row.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(42),
            **kwargs,
        )
        self.date_input = make_text_input(current_date_value())
        self.time_input = TimeSelector()

        self.add_widget(self.date_input)
        self.add_widget(self.time_input)

    def set_now(self) -> None:
        self.date_input.text = current_date_value()
        self.time_input.set_now()

    def set_values(self, date_value: str, time_value: str) -> None:
        self.date_input.text = date_value or current_date_value()
        self.time_input.set_value(time_value)

    def get_date(self) -> str:
        return self.date_input.text.strip()

    def get_time(self) -> str:
        return self.time_input.get_value()


class MemberCheckboxSelector(BoxLayout):
    """
    Group-dependent member selector.
    """

    def __init__(self, single: bool, **kwargs: Any) -> None:
        super().__init__(
            orientation="vertical",
            spacing=dp(2),
            size_hint_y=None,
            height=dp(42),
            **kwargs,
        )
        self.single = single
        self.members: List[str] = []
        self.checkboxes: Dict[str, CheckBox] = {}
        self._updating = False
        self.set_members([])

    def set_members(self, members: List[str]) -> None:
        previous = set(self.get_selected_members())
        self.members = members
        self.checkboxes = {}
        self.clear_widgets()

        if not members:
            self.height = dp(42)
            self.add_widget(
                i18n_label(
                    "Select a group",
                    size_hint_y=None,
                    height=dp(42),
                    halign="left",
                    valign="middle",
                )
            )
            return

        self.height = dp(max(42, len(members) * 34))
        self._updating = True
        for member in members:
            row = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(34),
                spacing=dp(4),
            )
            checkbox = CheckBox(size_hint_x=None, width=dp(42))
            checkbox.active = member in previous
            checkbox.bind(
                active=lambda checkbox_widget, active, name=member: (
                    self._on_checkbox_active(name, checkbox_widget, active)
                )
            )
            self.checkboxes[member] = checkbox
            row.add_widget(checkbox)
            row.add_widget(
                Label(
                    text=member,
                    halign="left",
                    valign="middle",
                    text_size=(None, dp(34)),
                )
            )
            self.add_widget(row)
        self._updating = False

        if self.single:
            selected = self.get_selected_members()
            for member in selected[1:]:
                self.checkboxes[member].active = False

    def _on_checkbox_active(
        self, member: str, checkbox: CheckBox, active: bool
    ) -> None:
        if self._updating or not self.single or not active:
            return

        for other_member, other_checkbox in self.checkboxes.items():
            if other_member != member:
                other_checkbox.active = False

    def get_selected_members(self) -> List[str]:
        return [
            member for member, checkbox in self.checkboxes.items() if checkbox.active
        ]

    def get_value(self) -> str:
        return ", ".join(self.get_selected_members())

    def set_value(self, value: str) -> None:
        selected = {item.strip() for item in (value or "").split(",") if item.strip()}
        self._updating = True
        for member, checkbox in self.checkboxes.items():
            checkbox.active = member in selected
        self._updating = False

        if self.single:
            active_members = self.get_selected_members()
            for member in active_members[1:]:
                self.checkboxes[member].active = False


class LedIndicator(Widget):
    """
    Small LED used by every screen header.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(size_hint=(None, None), size=(dp(18), dp(18)), **kwargs)
        with self.canvas:
            self._color = Color(0.1, 0.55, 0.2, 1)
            self._ellipse = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_shape, size=self._sync_shape)

    def _sync_shape(self, *_args: Any) -> None:
        self._ellipse.pos = self.pos
        self._ellipse.size = self.size

    def set_due(self, due: bool, visible: bool) -> None:
        if due:
            alpha = 1 if visible else 0.15
            self._color.rgba = (1, 0.05, 0.05, alpha)
        else:
            self._color.rgba = (0.1, 0.55, 0.2, 1)


class DataStore:
    """
    Keeps application data in memory and writes every change to JSON.
    """

    def __init__(self) -> None:
        self.file_path: Optional[Path] = None
        self.data: Dict[str, Any] = self._empty_data()
        self.undo_stack: List[Dict[str, Any]] = []
        self._load_today_session()

    def _empty_data(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "first_save_time": None,
                "created_file": None,
                "last_modified": None,
            },
            "scan_records": [],
            "behavior_events": [],
            "gps_records": [],
            "alimentation_records": [],
            "behavior_sequence_start_index": 0,
            "notes": "",
        }

    def _normalize_data(self) -> None:
        defaults = self._empty_data()
        for key, value in defaults.items():
            if key == "behavior_sequence_start_index":
                continue
            if key not in self.data:
                self.data[key] = value
        for key, value in defaults["metadata"].items():
            if key not in self.data["metadata"]:
                self.data["metadata"][key] = value
        if "behavior_sequence_start_index" not in self.data:
            self.data["behavior_sequence_start_index"] = (
                self._behavior_index_after_last_scan()
            )

    def _behavior_index_after_last_scan(self) -> int:
        scan_records = self.data.get("scan_records", [])
        behavior_events = self.data.get("behavior_events", [])
        if not scan_records:
            return 0

        last_scan_time = scan_records[-1].get("recorded_at", "")
        for index, event in enumerate(behavior_events):
            if event.get("recorded_at", "") > last_scan_time:
                return index
        return len(behavior_events)

    def _load_today_session(self) -> None:
        if not DATA_DIR.exists():
            return

        today_prefix = datetime.now().strftime("%Y-%m-%d")
        candidates = sorted(DATA_DIR.glob(f"{today_prefix}_*.json"))
        if not candidates:
            return

        path = candidates[-1]
        try:
            with path.open("r", encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self.data = self._empty_data()
            return

        self.file_path = path
        self._normalize_data()
        self.data["metadata"]["created_file"] = str(self.file_path)

    def _now_iso(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _ensure_file(self) -> None:
        """Create the JSON filename at the first save only."""
        if self.file_path is not None:
            return

        DATA_DIR.mkdir(exist_ok=True)
        first_save = datetime.now()
        stem = first_save.strftime("%Y-%m-%d_%H-%M-%S")
        self.file_path = DATA_DIR / f"{stem}.json"
        suffix = 1
        while self.file_path.exists():
            self.file_path = DATA_DIR / f"{stem}_{suffix}.json"
            suffix += 1
        self.data["metadata"]["first_save_time"] = first_save.isoformat(
            timespec="seconds"
        )
        self.data["metadata"]["created_file"] = str(self.file_path)

    def _save(self) -> None:
        self._ensure_file()
        self.data["metadata"]["last_modified"] = self._now_iso()
        assert self.file_path is not None
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _append_record(
        self, collection: str, record_type: str, values: Dict[str, str]
    ) -> None:
        record = {
            "recorded_at": self._now_iso(),
            "values": values,
        }
        self.data[collection].append(record)
        self.undo_stack.append({"type": record_type, "record": deepcopy(record)})
        self._save()

    def add_scan_record(self, values: Dict[str, str]) -> None:
        record = {
            "recorded_at": self._now_iso(),
            "values": values,
        }
        self._append_scan_record(record)

    def _append_scan_record(self, record: Dict[str, Any]) -> None:
        previous_sequence_start = self.data.get("behavior_sequence_start_index", 0)
        self.data["scan_records"].append(record)
        self.data["behavior_sequence_start_index"] = len(self.data["behavior_events"])
        self.undo_stack.append(
            {
                "type": "scan",
                "record": deepcopy(record),
                "previous_behavior_sequence_start_index": previous_sequence_start,
            }
        )
        self._save()

    def delete_scan_record(self, index: int) -> bool:
        if index < 0 or index >= len(self.data["scan_records"]):
            return False
        record = self.data["scan_records"].pop(index)
        self.undo_stack.append(
            {"type": "scan_delete", "index": index, "record": record}
        )
        self.data["behavior_sequence_start_index"] = (
            self._behavior_index_after_last_scan()
        )
        self._save()
        return True

    def create_intermediate_scans(self) -> int:
        if not self.data["scan_records"]:
            return 0

        last_record = self.data["scan_records"][-1]
        last_time_text = last_record.get("recorded_at", "")
        try:
            next_time = datetime.fromisoformat(last_time_text) + timedelta(
                seconds=SCAN_INTERVAL_SECONDS
            )
        except ValueError:
            return 0

        now = datetime.now()
        created = 0
        while next_time <= now:
            values = deepcopy(last_record.get("values", {}))
            values["date"] = next_time.strftime("%Y-%m-%d")
            values["time"] = next_time.strftime("%H:%M")
            record = {
                "recorded_at": next_time.isoformat(timespec="seconds"),
                "values": values,
                "generated": True,
            }
            self.data["scan_records"].append(record)
            last_record = record
            next_time += timedelta(seconds=SCAN_INTERVAL_SECONDS)
            created += 1

        if created:
            self.data["behavior_sequence_start_index"] = len(
                self.data["behavior_events"]
            )
            self.undo_stack.append({"type": "intermediate_scans", "count": created})
            self._save()
        return created

    def reset_session(self) -> Path:
        self.file_path = None
        self.data = self._empty_data()
        self.undo_stack = []
        self._save()
        assert self.file_path is not None
        return self.file_path

    def update_scan_record(self, index: int, values: Dict[str, str]) -> bool:
        if index < 0 or index >= len(self.data["scan_records"]):
            return False

        previous_record = deepcopy(self.data["scan_records"][index])
        self.data["scan_records"][index]["values"] = values
        self.data["scan_records"][index]["edited_at"] = self._now_iso()
        self.undo_stack.append(
            {
                "type": "scan_update",
                "index": index,
                "record": previous_record,
            }
        )
        self._save()
        return True

    def add_behavior_event(self, behavior: str, target: str = "") -> None:
        event = {
            "recorded_at": self._now_iso(),
            "behavior": behavior,
        }
        if target:
            event["target"] = target
        self.data["behavior_events"].append(event)
        self.undo_stack.append({"type": "behavior", "record": deepcopy(event)})
        self._save()

    def add_gps_record(self, values: Dict[str, str]) -> None:
        self._append_record("gps_records", "gps", values)

    def add_alimentation_record(self, values: Dict[str, str]) -> None:
        self._append_record("alimentation_records", "alimentation", values)

    def _update_record(
        self, collection: str, record_type: str, index: int, values: Dict[str, str]
    ) -> bool:
        if index < 0 or index >= len(self.data[collection]):
            return False

        previous_record = deepcopy(self.data[collection][index])
        self.data[collection][index]["values"] = values
        self.data[collection][index]["edited_at"] = self._now_iso()
        self.undo_stack.append(
            {
                "type": f"{record_type}_update",
                "collection": collection,
                "index": index,
                "record": previous_record,
            }
        )
        self._save()
        return True

    def update_gps_record(self, index: int, values: Dict[str, str]) -> bool:
        return self._update_record("gps_records", "gps", index, values)

    def update_alimentation_record(self, index: int, values: Dict[str, str]) -> bool:
        return self._update_record(
            "alimentation_records", "alimentation", index, values
        )

    def set_notes(self, text: str) -> None:
        if self.data.get("notes", "") == text:
            return
        self.data["notes"] = text
        self._save()

    def last_scan_time(self) -> Optional[datetime]:
        if not self.data["scan_records"]:
            return None

        recorded_at = self.data["scan_records"][-1].get("recorded_at")
        if not recorded_at:
            return None

        try:
            return datetime.fromisoformat(recorded_at)
        except ValueError:
            return None

    def seconds_until_next_scan(self) -> Optional[int]:
        last_scan = self.last_scan_time()
        if last_scan is None:
            return None

        elapsed = int((datetime.now() - last_scan).total_seconds())
        return max(0, SCAN_INTERVAL_SECONDS - elapsed)

    def is_scan_due(self) -> bool:
        seconds_left = self.seconds_until_next_scan()
        return seconds_left == 0

    def undo_last(self) -> Optional[str]:
        """Undo the last saved entry. Returns a user-readable message."""
        if not self.undo_stack:
            return None

        last = self.undo_stack.pop()
        record_type = last["type"]
        record = last.get("record")

        if record_type == "scan" and self.data["scan_records"]:
            self.data["scan_records"].pop()
            if "previous_behavior_sequence_start_index" in last:
                self.data["behavior_sequence_start_index"] = last[
                    "previous_behavior_sequence_start_index"
                ]
            else:
                self.data["behavior_sequence_start_index"] = (
                    self._behavior_index_after_last_scan()
                )
            self._save()
            return tr("Last scan record removed.")

        if record_type == "scan_update":
            index = last["index"]
            if 0 <= index < len(self.data["scan_records"]):
                self.data["scan_records"][index] = record
                self._save()
                return trf("Scan #{number} restored.", number=index + 1)
            return tr("Scan correction could not be restored.")

        if record_type == "scan_delete":
            index = min(last["index"], len(self.data["scan_records"]))
            self.data["scan_records"].insert(index, record)
            self.data["behavior_sequence_start_index"] = (
                self._behavior_index_after_last_scan()
            )
            self._save()
            return tr("Deleted scan restored.")

        if record_type == "intermediate_scans":
            count = last["count"]
            if count > 0:
                del self.data["scan_records"][-count:]
                self.data["behavior_sequence_start_index"] = (
                    self._behavior_index_after_last_scan()
                )
                self._save()
                return trf("{count} intermediate scans removed.", count=count)
            return tr("Nothing was removed.")

        if record_type == "behavior" and self.data["behavior_events"]:
            self.data["behavior_events"].pop()
            self._save()
            return trf(
                "Last behavior event removed: {behavior}",
                behavior=record.get("behavior", ""),
            )

        if record_type == "gps" and self.data["gps_records"]:
            self.data["gps_records"].pop()
            self._save()
            return tr("Last GPS record removed.")

        if record_type == "alimentation" and self.data["alimentation_records"]:
            self.data["alimentation_records"].pop()
            self._save()
            return tr("Last alimentation record removed.")

        if record_type in ("gps_update", "alimentation_update"):
            collection = last["collection"]
            index = last["index"]
            if 0 <= index < len(self.data[collection]):
                self.data[collection][index] = record
                self._save()
                return trf(
                    "{record_type} record restored.",
                    record_type=record_type.replace("_update", ""),
                )
            return tr("Record correction could not be restored.")

        return tr("Nothing was removed.")

    def to_pretty_json(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)


class HomeScreen(Screen):
    """Initial session screen."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="home", **kwargs)
        root = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
            padding=dp(24),
        )
        root.add_widget(Label(text="Maromizaha behaviors logger", font_size="24sp"))
        self.date_label = Label(
            font_size="18sp",
            size_hint_y=None,
            height=dp(44),
        )
        root.add_widget(self.date_label)

        language_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        language_row.add_widget(i18n_label("Language", size_hint_x=None, width=dp(120)))
        self.language_spinner = Spinner(
            text=language_label(current_language()),
            values=language_labels(),
            size_hint_y=None,
            height=dp(42),
        )
        self.language_spinner.bind(text=self.change_language)
        language_row.add_widget(self.language_spinner)
        root.add_widget(language_row)

        buttons = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(10))
        start_button = i18n_button("Start session")
        quit_button = i18n_button("Quit session")
        start_button.bind(on_press=lambda _button: App.get_running_app().go_to("scan"))
        quit_button.bind(on_press=lambda _button: App.get_running_app().stop())
        buttons.add_widget(start_button)
        buttons.add_widget(quit_button)
        root.add_widget(buttons)
        self.add_widget(root)
        self.refresh_language()

    def change_language(self, _spinner: Spinner, label: str) -> None:
        app = App.get_running_app()
        if app is not None and hasattr(app, "set_ui_language"):
            app.set_ui_language(language_from_label(label))

    def refresh_language(self) -> None:
        self.date_label.text = f"{tr('Date')}: {current_date_value()}"
        self.language_spinner.values = language_labels()
        self.language_spinner.text = language_label(current_language())


class Header(BoxLayout):
    """
    Reusable navigation header with the five-minute scan LED.
    """

    def __init__(self, title: str, **kwargs: Any) -> None:
        super().__init__(
            orientation="vertical", size_hint_y=None, height=dp(104), **kwargs
        )
        self._blink_visible = True

        title_row = BoxLayout(
            size_hint_y=None, height=dp(44), spacing=dp(8), padding=(dp(6), 0)
        )
        title_row.add_widget(i18n_label(title, font_size="22sp"))

        led_box = BoxLayout(
            size_hint_x=None,
            width=dp(78),
            spacing=dp(6),
            padding=(0, dp(13), 0, dp(13)),
        )
        led_box.add_widget(
            i18n_label("5 min", font_size="12sp", size_hint_x=None, width=dp(46))
        )
        self.led = LedIndicator()
        led_box.add_widget(self.led)
        title_row.add_widget(led_box)
        self.add_widget(title_row)

        nav_scroll = ScrollView(
            size_hint_y=None,
            height=dp(54),
            do_scroll_x=True,
            do_scroll_y=False,
            bar_width=dp(2),
        )
        nav = BoxLayout(
            size_hint_x=None, height=dp(48), spacing=dp(6), padding=(dp(6), 0)
        )
        self.nav_buttons: Dict[str, Button] = {}
        nav.bind(minimum_width=nav.setter("width"))
        buttons = [
            ("New 5 min scan", "new_scan"),
            ("Scans", "scan_list"),
            ("Behaviors", "behaviors"),
            ("GPS", "gps"),
            ("Alimentation", "alimentation"),
            ("Groups", "group_management"),
            ("Settings", "settings"),
            ("JSON", "viewer"),
            ("Reset session", "reset_session"),
            ("Notes", "notes"),
        ]
        widths = {
            "New 5 min scan": dp(150),
            "Alimentation": dp(130),
            "Behaviors": dp(112),
            "Groups": dp(100),
            "Reset session": dp(142),
        }
        for label, screen_name in buttons:
            if screen_name == "settings":
                btn = Button(
                    text=label, size_hint_x=None, width=widths.get(label, dp(96))
                )
            else:
                btn = i18n_button(
                    label, size_hint_x=None, width=widths.get(label, dp(96))
                )
            if screen_name == "new_scan":
                btn.bind(on_press=lambda _btn: App.get_running_app().start_new_scan())
            elif screen_name == "reset_session":
                btn.bind(
                    on_press=lambda _btn: App.get_running_app().confirm_reset_session()
                )
            else:
                btn.bind(
                    on_press=lambda _btn, name=screen_name: App.get_running_app().go_to(
                        name
                    )
                )
            nav.add_widget(btn)
            self.nav_buttons[screen_name] = btn
        nav_scroll.add_widget(nav)
        self.add_widget(nav_scroll)
        self.refresh_navigation_visibility()

        Clock.schedule_interval(self.refresh_led, 0.5)
        self.refresh_led(0)

    def refresh_navigation_visibility(self) -> None:
        json_button = self.nav_buttons.get("viewer")
        if json_button is None:
            return

        app = App.get_running_app()
        visible = bool(getattr(app, "show_json_tab", False))
        json_button.opacity = 1 if visible else 0
        json_button.disabled = not visible
        json_button.width = dp(96) if visible else 0

    def refresh_led(self, _dt: float) -> None:
        app = App.get_running_app()
        due = bool(app and hasattr(app, "is_scan_due") and app.is_scan_due())
        if due:
            self._blink_visible = not self._blink_visible
        else:
            self._blink_visible = True
        self.led.set_due(due, self._blink_visible)


class ScanScreen(Screen):
    """
    Screen used to record scan parameters every five minutes.
    """

    def __init__(self, store: DataStore, **kwargs: Any) -> None:
        super().__init__(name="scan", **kwargs)
        self.store = store
        self.inputs: Dict[str, Widget] = {}
        self.editing_index: Optional[int] = None

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("New 5 min scan"))

        self.status = i18n_label(
            "Ready for the first scan.",
            size_hint_y=None,
            height=dp(38),
        )
        root.add_widget(self.status)

        scroll = ScrollView()
        form = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(8),
            size_hint_y=None,
        )
        form.bind(minimum_height=form.setter("height"))

        self.date_time_input = DateTimeInput()
        self._add_scan_row(
            form,
            [("date / time", "date"), ("climate", "climate")],
        )
        self._add_scan_row(
            form,
            [("group", "group"), ("CA", "CA")],
        )
        self._add_scan_row(
            form,
            [("presence", "presence")],
            height=dp(160),
        )
        self._add_scan_row(
            form,
            [("GPS point name", "GPS point name"), ("arbre", "arbre")],
        )
        self._add_scan_row(
            form,
            [
                ("h_CA", "h_CA"),
                ("h_arbre", "h_arbre"),
                ("dist_CA", "dist_CA"),
                ("dist_CACB", "dist_CACB"),
                ("pos_CACB", "pos_CACB"),
            ],
        )

        self._refresh_member_selectors(get_widget_text(self.inputs.get("group")))
        scroll.add_widget(form)
        root.add_widget(scroll)

        controls = BoxLayout(
            size_hint_y=None, height=dp(52), spacing=dp(6), padding=dp(6)
        )
        self.save_button = i18n_button("Save scan")
        self.save_button.bind(on_press=self.save_scan)
        undo_button = i18n_button("Undo last")
        undo_button.bind(on_press=self.undo_last)
        controls.add_widget(self.save_button)
        controls.add_widget(undo_button)
        root.add_widget(controls)

        self.add_widget(root)
        Clock.schedule_interval(self._tick, 1)

    def _add_scan_row(
        self,
        form: BoxLayout,
        fields: List[Tuple[str, str]],
        height: float = dp(72),
    ) -> None:
        row = GridLayout(
            cols=len(fields),
            spacing=dp(6),
            size_hint_y=None,
            height=height,
        )
        for label_text, field in fields:
            cell = BoxLayout(
                orientation="vertical",
                spacing=dp(2),
                size_hint_y=None,
                height=height,
            )
            label = Label(
                text=label_text,
                size_hint_y=None,
                height=dp(24),
                halign="left",
                valign="middle",
            )
            label.bind(
                size=lambda label_widget, _size: setattr(
                    label_widget, "text_size", label_widget.size
                )
            )
            cell.add_widget(label)
            cell.add_widget(self._scan_field_widget(field))
            row.add_widget(cell)
        form.add_widget(row)

    def _scan_field_widget(self, field: str) -> Widget:
        if field == "date":
            return self.date_time_input
        if field == "CA":
            widget = make_spinner(["-"])
        elif field == "presence":
            widget = MemberCheckboxSelector(single=False)
        else:
            widget = make_field_widget(field)
            if field == "group" and isinstance(widget, Spinner):
                widget.bind(text=self._on_group_changed)

        self.inputs[field] = widget
        return widget

    def _tick(self, _dt: float) -> None:
        if self.editing_index is not None:
            return

        seconds_left = self.store.seconds_until_next_scan()
        if seconds_left is None:
            self.status.text = tr("Ready for the first scan.")
            return

        if seconds_left <= 0:
            self.status.text = tr(
                "Five minutes passed. Validate or correct values, then save the next scan."
            )
            return

        minutes = seconds_left // 60
        seconds = seconds_left % 60
        self.status.text = trf(
            "Next scan reminder in {minutes:02d}:{seconds:02d}. Previous values remain editable.",
            minutes=minutes,
            seconds=seconds,
        )

    def update_date_time_fields(
        self, _button: Optional[Button], show_status: bool = True
    ) -> None:
        self.date_time_input.set_now()
        if show_status:
            self.status.text = tr("Date and time fields updated.")

    def _on_group_changed(self, _spinner: Spinner, group: str) -> None:
        self._refresh_member_selectors(group)

    def _refresh_member_selectors(self, group: str) -> None:
        members = GROUPS_COMPOSITION.get(group, [])
        ca_values = ["-"] + members
        ca_widget = self.inputs.get("CA")
        if isinstance(ca_widget, Spinner):
            ca_widget.values = ca_values
            if ca_widget.text not in ca_values:
                ca_widget.text = ca_values[0]

        presence_widget = self.inputs.get("presence")
        if isinstance(presence_widget, MemberCheckboxSelector):
            presence_widget.set_members(members)

    def refresh_group_options(self) -> None:
        group_widget = self.inputs.get("group")
        if isinstance(group_widget, Spinner):
            group_widget.values = LIST_FIELDS["group"]
            if group_widget.text not in LIST_FIELDS["group"]:
                group_widget.text = LIST_FIELDS["group"][0]
            self._refresh_member_selectors(group_widget.text)

    def _collect_values(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for field in SCAN_FIELDS:
            if field == "date":
                values[field] = self.date_time_input.get_date()
            elif field == "time":
                values[field] = self.date_time_input.get_time()
            else:
                values[field] = get_widget_text(self.inputs[field])
        return values

    def _validate_scan_values(self, values: Dict[str, str]) -> bool:
        missing_fields = [
            field for field in ("group", "CA") if values.get(field, "") in ("", "-")
        ]
        if missing_fields:
            self.status.text = tr("Select group and CA before saving the scan.")
            return False
        return True

    def _set_values(self, values: Dict[str, str]) -> None:
        self.date_time_input.set_values(values.get("date", ""), values.get("time", ""))
        for field in SCAN_FIELDS:
            if field in ("date", "time"):
                continue

            value = values.get(field, "")
            if not value and field == "UTM_zone":
                value = DEFAULT_UTM_ZONE
            elif not value and field in NUMERIC_1_TO_20_FIELDS:
                value = "1"
            elif not value and field in LIST_FIELDS:
                value = LIST_FIELDS[field][0]
            set_widget_text(self.inputs[field], value)

    def start_new_scan(self) -> None:
        if self.store.data["scan_records"]:
            self._set_values(self.store.data["scan_records"][-1].get("values", {}))
        self.editing_index = None
        set_i18n_text(self.save_button, "Save scan")
        self.update_date_time_fields(None, show_status=False)
        self.status.text = tr(
            "Validate previous values or correct them, then press Save scan."
        )

    def load_scan_for_edit(self, index: int) -> bool:
        if index < 0 or index >= len(self.store.data["scan_records"]):
            self.status.text = tr("Scan not found.")
            return False

        record = self.store.data["scan_records"][index]
        self._set_values(record.get("values", {}))
        self.editing_index = index
        set_i18n_text(self.save_button, "Update")
        self.status.text = trf(
            "Editing scan #{number}. Save to apply corrections.",
            number=index + 1,
        )
        return True

    def reset_form(self) -> None:
        self._set_values({})
        self.editing_index = None
        set_i18n_text(self.save_button, "Save scan")
        self.status.text = tr("New session created.")

    def save_scan(self, _button: Button) -> None:
        values = self._collect_values()
        if not self._validate_scan_values(values):
            return

        if self.editing_index is not None:
            updated = self.store.update_scan_record(self.editing_index, values)
            if updated:
                edited_number = self.editing_index + 1
                self.editing_index = None
                set_i18n_text(self.save_button, "Save scan")
                self.status.text = trf("Scan #{number} updated.", number=edited_number)
                App.get_running_app().go_to("scan_list")
            else:
                self.status.text = tr("Scan could not be updated.")
            return

        self.store.add_scan_record(values)
        app = App.get_running_app()
        if hasattr(app, "refresh_behavior_sequence"):
            app.refresh_behavior_sequence()
        if hasattr(app, "behavior_screen"):
            app.behavior_screen.reset_for_new_scan()
        self.update_date_time_fields(None, show_status=False)
        self.status.text = tr(
            "Scan saved. Values are kept for the next validation/correction."
        )

    def undo_last(self, _button: Button) -> None:
        message = self.store.undo_last()
        self.status.text = message or tr("Nothing to undo.")


class ScanListScreen(Screen):
    """Table-like view of scan records with edit buttons."""

    def __init__(self, store: DataStore, **kwargs: Any) -> None:
        super().__init__(name="scan_list", **kwargs)
        self.store = store
        self.show_all = False

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Scan records"))

        controls = BoxLayout(
            size_hint_y=None, height=dp(48), spacing=dp(6), padding=dp(6)
        )
        refresh_button = i18n_button("Refresh")
        refresh_button.bind(on_press=self.refresh)
        self.show_all_button = i18n_button("Show all scans")
        self.show_all_button.bind(on_press=self.toggle_show_all)
        generate_button = i18n_button("Create missing scans")
        generate_button.bind(on_press=self.create_missing_scans)
        controls.add_widget(refresh_button)
        controls.add_widget(self.show_all_button)
        controls.add_widget(generate_button)
        root.add_widget(controls)

        self.status = Label(text="", size_hint_y=None, height=dp(28))
        root.add_widget(self.status)

        self.scroll = ScrollView(do_scroll_x=True, do_scroll_y=True)
        self.table = GridLayout(
            cols=1, spacing=dp(1), padding=dp(4), size_hint=(None, None)
        )
        self.table.bind(minimum_height=self.table.setter("height"))
        self.scroll.add_widget(self.table)
        root.add_widget(self.scroll)

        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.refresh(None)

    def _table_label(self, text: str, width: int = 110, bold: bool = False) -> Label:
        return Label(
            text=str(text),
            bold=bold,
            font_size="12sp",
            size_hint=(None, None),
            width=dp(width),
            height=dp(42),
            text_size=(dp(width - 8), dp(40)),
            halign="left",
            valign="middle",
        )

    def refresh(self, _button: Optional[Button]) -> None:
        records = self.store.data["scan_records"]
        indexed_records = list(enumerate(records))
        indexed_records.reverse()
        if not self.show_all:
            indexed_records = indexed_records[:10]

        headers = ["edit", "delete", "#", "recorded_at"] + SCAN_FIELDS
        widths = {
            "#": 46,
            "recorded_at": 150,
            "time": 70,
            "edit": 74,
            "delete": 74,
            "UTM_zone": 80,
            "UTM_north": 110,
            "UTM_east": 110,
        }

        self.table.clear_widgets()
        self.table.cols = len(headers)
        self.table.width = sum(dp(widths.get(header, 104)) for header in headers)

        for header in headers:
            self.table.add_widget(
                self._table_label(
                    self._header_text(header),
                    widths.get(header, 104),
                    bold=True,
                )
            )

        for index, record in indexed_records:
            edit_button = i18n_button(
                "Edit",
                size_hint=(None, None),
                width=dp(widths["edit"]),
                height=dp(42),
            )
            edit_button.bind(
                on_press=lambda _btn, idx=index: (
                    App.get_running_app().load_scan_for_edit(idx)
                )
            )
            self.table.add_widget(edit_button)

            delete_button = i18n_button(
                "Delete",
                size_hint=(None, None),
                width=dp(widths["delete"]),
                height=dp(42),
            )
            delete_button.bind(on_press=lambda _btn, idx=index: self.delete_scan(idx))
            self.table.add_widget(delete_button)

            values = record.get("values", {})
            row_values = [str(index + 1), record.get("recorded_at", "")]
            row_values.extend(values.get(field, "") for field in SCAN_FIELDS)

            for header, value in zip(headers[2:], row_values):
                self.table.add_widget(self._table_label(value, widths.get(header, 104)))

        set_i18n_text(
            self.show_all_button,
            "Show latest 10 scans" if self.show_all else "Show all scans",
        )
        self.status.text = trf(
            "{shown} of {count} scan records shown.",
            shown=len(indexed_records),
            count=len(records),
        )

    def _header_text(self, header: str) -> str:
        if header == "edit":
            return tr("Edit")
        if header == "delete":
            return tr("Delete")
        return header

    def toggle_show_all(self, _button: Button) -> None:
        self.show_all = not self.show_all
        self.refresh(None)

    def delete_scan(self, index: int) -> None:
        if self.store.delete_scan_record(index):
            self.refresh(None)
            app = App.get_running_app()
            if hasattr(app, "refresh_behavior_sequence"):
                app.refresh_behavior_sequence()

    def create_missing_scans(self, _button: Button) -> None:
        created = self.store.create_intermediate_scans()
        self.refresh(None)
        app = App.get_running_app()
        if hasattr(app, "refresh_behavior_sequence"):
            app.refresh_behavior_sequence()
        self.status.text = trf("{count} intermediate scans created.", count=created)


class BehaviorScreen(Screen):
    """Screen with behavior buttons. Each press is timestamped and saved."""

    def __init__(self, store: DataStore, **kwargs: Any) -> None:
        super().__init__(name="behaviors", **kwargs)
        self.store = store

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Behavior event recorder"))

        self.status = i18n_label(
            "Press a behavior button to record an event with the current time.",
            size_hint_y=None,
            height=dp(40),
        )
        root.add_widget(self.status)
        self.scan_window = Label(
            text="",
            size_hint_y=None,
            height=dp(32),
            halign="left",
            valign="middle",
        )
        self.scan_window.bind(
            size=lambda widget, _size: setattr(widget, "text_size", widget.size)
        )
        root.add_widget(self.scan_window)

        self.sequence = Label(
            text="",
            size_hint_y=None,
            height=dp(82),
            font_size="14sp",
            halign="left",
            valign="top",
        )
        self.sequence.bind(size=self._update_sequence_text_size)
        root.add_widget(self.sequence)

        scroll = ScrollView()
        grid = GridLayout(cols=3, spacing=dp(6), padding=dp(8), size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        for behavior in BEHAVIOR_FIELDS:
            btn = Button(text=behavior, size_hint_y=None, height=dp(54))
            btn.bind(on_press=lambda _btn, code=behavior: self.record_behavior(code))
            grid.add_widget(btn)

        scroll.add_widget(grid)
        root.add_widget(scroll)

        controls = BoxLayout(
            size_hint_y=None, height=dp(52), spacing=dp(6), padding=dp(6)
        )
        undo_button = i18n_button("Undo last")
        undo_button.bind(on_press=self.undo_last)
        controls.add_widget(undo_button)
        root.add_widget(controls)

        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.refresh_sequence()
        self.refresh_scan_window()

    def _update_sequence_text_size(self, *_args: Any) -> None:
        self.sequence.text_size = (self.sequence.width - dp(12), self.sequence.height)

    def _behavior_label(self, event: Dict[str, str]) -> str:
        behavior = event.get("behavior", "")
        target = event.get("target", "")
        if target:
            return f"{behavior}({target})"
        return behavior

    def refresh_sequence(self) -> None:
        events = self.store.data["behavior_events"]
        start_index = self.store.data.get("behavior_sequence_start_index", 0)
        if start_index > len(events):
            start_index = len(events)
        sequence = [self._behavior_label(event) for event in events[start_index:]]
        self.sequence.text = " ".join(sequence)

    def refresh_scan_window(self) -> None:
        record = (
            self.store.data["scan_records"][-1]
            if self.store.data["scan_records"]
            else None
        )
        if not record:
            self.scan_window.text = tr("Current scan time window: none")
            return
        recorded_at = record.get("recorded_at", "")
        try:
            start = datetime.fromisoformat(recorded_at)
        except ValueError:
            values = record.get("values", {})
            self.scan_window.text = trf(
                "Current scan time window: {start} - {end}",
                start=values.get("time", "-"),
                end="-",
            )
            return
        end = start + timedelta(seconds=SCAN_INTERVAL_SECONDS)
        self.scan_window.text = trf(
            "Current scan time window: {start} - {end}",
            start=start.strftime("%H:%M"),
            end=end.strftime("%H:%M"),
        )

    def reset_for_new_scan(self) -> None:
        self.status.text = tr(
            "Press a behavior button to record an event with the current time."
        )
        self.refresh_sequence()
        self.refresh_scan_window()

    def record_behavior(self, behavior: str) -> None:
        if behavior in ("G", "J"):
            self._prompt_behavior_target(behavior)
            return

        self._save_behavior_event(behavior)

    def _prompt_behavior_target(self, behavior: str) -> None:
        label_text = "Groomed individual" if behavior == "G" else "Play partner or self"
        app = App.get_running_app()
        group, members = app.get_current_group_members()
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        content.add_widget(i18n_label(label_text, size_hint_y=None, height=dp(30)))
        content.add_widget(
            Label(
                text=trf("Group: {group}", group=group or "-"),
                size_hint_y=None,
                height=dp(28),
            )
        )

        selector = MemberCheckboxSelector(single=True)
        selector.set_members(members)
        selector_scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        selector_scroll.add_widget(selector)
        content.add_widget(selector_scroll)

        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        cancel_button = i18n_button("Cancel")
        save_button = i18n_button("Save")
        buttons.add_widget(cancel_button)
        buttons.add_widget(save_button)
        content.add_widget(buttons)

        popup = Popup(
            title=trf("{behavior} individual", behavior=behavior),
            content=content,
            size_hint=(0.82, 0.58),
            auto_dismiss=False,
        )

        def save_with_target(_button: Button) -> None:
            target = selector.get_value()
            popup.dismiss()
            self._save_behavior_event(behavior, target)

        cancel_button.bind(on_press=lambda _button: popup.dismiss())
        save_button.bind(on_press=save_with_target)
        popup.open()

    def _save_behavior_event(self, behavior: str, target: str = "") -> None:
        self.store.add_behavior_event(behavior, target)
        if target:
            self.status.text = trf(
                "Recorded: {behavior} ({target})",
                behavior=behavior,
                target=target,
            )
        else:
            self.status.text = trf("Recorded: {behavior}", behavior=behavior)

        self.refresh_sequence()

    def undo_last(self, _button: Button) -> None:
        message = self.store.undo_last()
        self.status.text = message or tr("Nothing to undo.")
        self.refresh_sequence()


class RecordFormScreen(Screen):
    """Reusable form screen for GPS and alimentation records."""

    def __init__(
        self,
        store: DataStore,
        screen_name: str,
        title: str,
        fields: List[str],
        add_method_name: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(name=screen_name, **kwargs)
        self.store = store
        self.fields = fields
        self.add_method_name = add_method_name
        self.inputs: Dict[str, Widget] = {}
        self.editing_index: Optional[int] = None
        self.collection_name = (
            "gps_records" if screen_name == "gps" else "alimentation_records"
        )
        self.update_method_name = (
            "update_gps_record"
            if screen_name == "gps"
            else "update_alimentation_record"
        )

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header(title))

        self.status = i18n_label(
            "Fill values and save.", size_hint_y=None, height=dp(36)
        )
        root.add_widget(self.status)

        scroll = ScrollView(size_hint_y=0.55)
        form = GridLayout(cols=2, spacing=dp(6), padding=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        for field in fields:
            form.add_widget(Label(text=field, size_hint_y=None, height=dp(42)))
            if field in TIME_FIELD_NAMES:
                widget = TimeSelector()
            else:
                widget = make_field_widget(field)
            self.inputs[field] = widget
            form.add_widget(widget)

        scroll.add_widget(form)
        root.add_widget(scroll)

        controls = BoxLayout(
            size_hint_y=None, height=dp(52), spacing=dp(6), padding=dp(6)
        )
        self.save_button = i18n_button("Save")
        self.save_button.bind(on_press=self.save_record)
        undo_button = i18n_button("Undo last")
        undo_button.bind(on_press=self.undo_last)
        controls.add_widget(self.save_button)
        controls.add_widget(undo_button)
        root.add_widget(controls)

        root.add_widget(i18n_label("Saved records", size_hint_y=None, height=dp(28)))
        self.table_scroll = ScrollView(
            do_scroll_x=True, do_scroll_y=True, size_hint_y=0.45
        )
        self.table = GridLayout(
            cols=1, spacing=dp(1), padding=dp(4), size_hint=(None, None)
        )
        self.table.bind(minimum_height=self.table.setter("height"))
        self.table_scroll.add_widget(self.table)
        root.add_widget(self.table_scroll)

        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.refresh_table()

    def _collect_values(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for field, widget in self.inputs.items():
            if isinstance(widget, TimeSelector):
                values[field] = widget.get_value()
            else:
                values[field] = get_widget_text(widget)
        return values

    def _validate_values(self, values: Dict[str, str]) -> bool:
        if self.name != "gps":
            return True

        for field in GPS_REQUIRED_INTEGER_FIELDS:
            value = values.get(field, "")
            if not value or not value.isdigit():
                self.status.text = trf(
                    "{field} must be an integer value.",
                    field=field,
                )
                return False
        return True

    def save_record(self, _button: Button) -> None:
        values = self._collect_values()
        if not self._validate_values(values):
            return

        if self.editing_index is not None:
            update_method = getattr(self.store, self.update_method_name)
            updated = update_method(self.editing_index, values)
            if updated:
                self.editing_index = None
                set_i18n_text(self.save_button, "Save")
                if self.name != "alimentation":
                    self.status.text = tr("Record updated.")
                else:
                    self.status.text = ""
                self.refresh_table()
            else:
                self.status.text = tr("Record could not be updated.")
            return

        add_method = getattr(self.store, self.add_method_name)
        add_method(values)
        if self.name != "alimentation":
            self.status.text = tr("Record saved.")
        else:
            self.status.text = ""
        self.refresh_table()

    def undo_last(self, _button: Button) -> None:
        message = self.store.undo_last()
        self.status.text = message or tr("Nothing to undo.")
        self.refresh_table()

    def _table_label(self, text: str, width: int = 110, bold: bool = False) -> Label:
        return Label(
            text=str(text),
            bold=bold,
            font_size="12sp",
            size_hint=(None, None),
            width=dp(width),
            height=dp(42),
            text_size=(dp(width - 8), dp(40)),
            halign="left",
            valign="middle",
        )

    def refresh_table(self) -> None:
        records = self.store.data[self.collection_name]
        headers = ["edit", "recorded_at"] + self.fields
        widths = {"edit": 74, "recorded_at": 150}

        self.table.clear_widgets()
        self.table.cols = len(headers)
        self.table.width = sum(dp(widths.get(header, 116)) for header in headers)

        for header in headers:
            self.table.add_widget(
                self._table_label(
                    tr("Edit") if header == "edit" else header,
                    widths.get(header, 116),
                    bold=True,
                )
            )

        for index, record in enumerate(records):
            edit_button = i18n_button(
                "Edit",
                size_hint=(None, None),
                width=dp(widths["edit"]),
                height=dp(42),
            )
            edit_button.bind(
                on_press=lambda _button, idx=index: self.load_record_for_edit(idx)
            )
            self.table.add_widget(edit_button)
            self.table.add_widget(
                self._table_label(record.get("recorded_at", ""), widths["recorded_at"])
            )
            values = record.get("values", {})
            for field in self.fields:
                self.table.add_widget(
                    self._table_label(values.get(field, ""), widths.get(field, 116))
                )

    def load_record_for_edit(self, index: int) -> None:
        records = self.store.data[self.collection_name]
        if index < 0 or index >= len(records):
            self.status.text = tr("Record not found.")
            return

        values = records[index].get("values", {})
        for field, widget in self.inputs.items():
            set_widget_text(widget, values.get(field, ""))
        self.editing_index = index
        set_i18n_text(self.save_button, "Update")
        self.status.text = trf("Editing record #{number}.", number=index + 1)


class NotesScreen(Screen):
    """Open notes saved when leaving the screen."""

    def __init__(self, store: DataStore, **kwargs: Any) -> None:
        super().__init__(name="notes", **kwargs)
        self.store = store

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Notes"))

        self.status = i18n_label(
            "Notes are saved when changing screen.",
            size_hint_y=None,
            height=dp(36),
        )
        root.add_widget(self.status)

        self.text = TextInput(
            text="",
            multiline=True,
            font_size="16sp",
        )
        root.add_widget(self.text)
        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.text.text = self.store.data.get("notes", "")

    def on_pre_leave(self, *args: Any) -> None:
        self.store.set_notes(self.text.text)
        self.status.text = tr("Notes saved.")


class GroupManagementScreen(Screen):
    """Edit group names and compositions in config.json."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="group_management", **kwargs)

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Group management"))

        self.status = Label(text="", size_hint_y=None, height=dp(34))
        root.add_widget(self.status)

        form = GridLayout(cols=2, spacing=dp(6), padding=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        form.add_widget(i18n_label("Select group", size_hint_y=None, height=dp(42)))
        self.group_spinner = make_spinner(LIST_FIELDS["group"])
        self.group_spinner.bind(text=lambda _spinner, value: self.load_group(value))
        form.add_widget(self.group_spinner)

        form.add_widget(i18n_label("Group name", size_hint_y=None, height=dp(42)))
        self.group_name = make_text_input()
        form.add_widget(self.group_name)

        form.add_widget(i18n_label("Members", size_hint_y=None, height=dp(160)))
        self.members = TextInput(multiline=True, size_hint_y=None, height=dp(160))
        form.add_widget(self.members)

        controls = BoxLayout(
            size_hint_y=None, height=dp(52), spacing=dp(6), padding=dp(6)
        )
        new_button = i18n_button("New group")
        save_button = i18n_button("Save group")
        delete_button = i18n_button("Delete group")
        reload_button = i18n_button("Reload config")
        new_button.bind(on_press=self.new_group)
        save_button.bind(on_press=self.save_group)
        delete_button.bind(on_press=self.delete_group)
        reload_button.bind(on_press=self.reload_config)
        controls.add_widget(new_button)
        controls.add_widget(save_button)
        controls.add_widget(delete_button)
        controls.add_widget(reload_button)

        scroll = ScrollView()
        scroll.add_widget(form)
        root.add_widget(scroll)
        root.add_widget(controls)
        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.refresh_groups()

    def refresh_groups(self) -> None:
        self.group_spinner.values = LIST_FIELDS["group"]
        if self.group_spinner.text not in LIST_FIELDS["group"]:
            self.group_spinner.text = LIST_FIELDS["group"][0]
        self.load_group(self.group_spinner.text)

    def load_group(self, group: str) -> None:
        if not hasattr(self, "group_name"):
            return
        if group == "-":
            self.group_name.text = ""
            self.members.text = ""
            return
        self.group_name.text = group
        self.members.text = "\n".join(GROUPS_COMPOSITION.get(group, []))

    def new_group(self, _button: Button) -> None:
        self.group_spinner.text = "-"
        self.group_name.text = ""
        self.members.text = ""
        self.status.text = tr("Enter a new group name and members, then save.")
        Clock.schedule_once(lambda _dt: setattr(self.group_name, "focus", True), 0.1)

    def _read_config(self) -> Dict[str, Any]:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write_config(self, config_data: Dict[str, Any]) -> None:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

    def _members_from_text(self) -> List[str]:
        members: List[str] = []
        for line in self.members.text.replace(",", "\n").splitlines():
            member = line.strip()
            if member and member not in members:
                members.append(member)
        return members

    def save_group(self, _button: Button) -> None:
        group = self.group_name.text.strip()
        if not group or group == "-":
            self.status.text = tr("Enter a group name.")
            return

        config_data = self._read_config()
        groups = config_data.setdefault("GROUPS_LIST", [])
        if group not in groups:
            groups.append(group)
        config_data.setdefault("GROUPS_COMPOSITION", {})[group] = (
            self._members_from_text()
        )
        self._write_config(config_data)
        App.get_running_app().reload_group_config()
        self.group_spinner.text = group
        self.refresh_groups()
        self.status.text = tr("Group saved and reloaded.")

    def delete_group(self, _button: Button) -> None:
        group = self.group_name.text.strip() or self.group_spinner.text
        if not group or group == "-":
            self.status.text = tr("Select a group to delete.")
            return

        config_data = self._read_config()
        groups = config_data.setdefault("GROUPS_LIST", [])
        if group in groups:
            groups.remove(group)
        config_data.setdefault("GROUPS_COMPOSITION", {}).pop(group, None)
        self._write_config(config_data)
        App.get_running_app().reload_group_config()
        self.group_spinner.text = "-"
        self.refresh_groups()
        self.status.text = tr("Group deleted and reloaded.")

    def reload_config(self, _button: Button) -> None:
        App.get_running_app().reload_group_config()
        self.refresh_groups()
        self.status.text = tr("Config reloaded.")


class SettingsScreen(Screen):
    """Application settings."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="settings", **kwargs)
        self._refreshing = False
        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Settings"))

        self.status = Label(text="", size_hint_y=None, height=dp(34))
        root.add_widget(self.status)

        form = GridLayout(cols=2, spacing=dp(6), padding=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        form.add_widget(i18n_label("Language", size_hint_y=None, height=dp(42)))
        self.language_spinner = Spinner(
            text=language_label(current_language()),
            values=language_labels(),
            size_hint_y=None,
            height=dp(42),
        )
        self.language_spinner.bind(text=self.change_language)
        form.add_widget(self.language_spinner)

        form.add_widget(
            i18n_label("Screen orientation", size_hint_y=None, height=dp(42))
        )
        self.orientation_spinner = Spinner(
            text=tr("Landscape"),
            values=[tr("Landscape"), tr("Portrait")],
            size_hint_y=None,
            height=dp(42),
        )
        self.orientation_spinner.bind(text=self.change_orientation)
        form.add_widget(self.orientation_spinner)

        form.add_widget(i18n_label("Show JSON tab", size_hint_y=None, height=dp(42)))
        self.show_json_checkbox = CheckBox(size_hint_y=None, height=dp(42))
        self.show_json_checkbox.bind(active=self.change_json_visibility)
        form.add_widget(self.show_json_checkbox)

        scroll = ScrollView()
        scroll.add_widget(form)
        root.add_widget(scroll)
        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.refresh_settings()

    def change_language(self, _spinner: Spinner, label: str) -> None:
        app = App.get_running_app()
        if app is not None and hasattr(app, "set_ui_language"):
            app.set_ui_language(language_from_label(label))

    def change_orientation(self, _spinner: Spinner, label: str) -> None:
        app = App.get_running_app()
        if app is not None and hasattr(app, "set_screen_orientation"):
            orientation = "portrait" if label == tr("Portrait") else "landscape"
            app.set_screen_orientation(orientation)
            self.status.text = trf(
                "Screen orientation set to {orientation}.", orientation=label
            )

    def change_json_visibility(self, _checkbox: CheckBox, active: bool) -> None:
        if self._refreshing:
            return
        app = App.get_running_app()
        if app is not None and hasattr(app, "set_json_tab_visible"):
            app.set_json_tab_visible(active)
            self.status.text = tr("JSON tab shown." if active else "JSON tab hidden.")

    def refresh_settings(self) -> None:
        app = App.get_running_app()
        self._refreshing = True
        self.show_json_checkbox.active = bool(getattr(app, "show_json_tab", False))
        self._refreshing = False

    def refresh_language(self) -> None:
        self.language_spinner.values = language_labels()
        self.language_spinner.text = language_label(current_language())
        current_orientation = getattr(
            App.get_running_app(), "screen_orientation", "landscape"
        )
        self.orientation_spinner.values = [tr("Landscape"), tr("Portrait")]
        self.orientation_spinner.text = tr(
            "Portrait" if current_orientation == "portrait" else "Landscape"
        )
        self.refresh_settings()


class ViewerScreen(Screen):
    """
    Screen that displays the current JSON data.
    """

    def __init__(self, store: DataStore, **kwargs: Any) -> None:
        super().__init__(name="viewer", **kwargs)
        self.store = store

        root = BoxLayout(orientation="vertical")
        root.add_widget(Header("Saved JSON viewer"))

        self.scroll = ScrollView(
            do_scroll_x=True,
            do_scroll_y=True,
            bar_width=dp(8),
        )
        self.text = Label(
            text=tr("No data saved yet."),
            font_name="RobotoMono-Regular",
            font_size="13sp",
            halign="left",
            valign="top",
            padding=(dp(8), dp(8)),
            size_hint=(None, None),
        )
        self.text.bind(texture_size=self._resize_text)
        self.scroll.bind(size=self._resize_text)
        self.scroll.add_widget(self.text)
        root.add_widget(self.scroll)
        self.add_widget(root)

    def on_pre_enter(self, *args: Any) -> None:
        self.refresh(None)

    def _resize_text(self, *_args: Any) -> None:
        self.text.width = max(self.text.texture_size[0] + dp(16), self.scroll.width)
        self.text.height = max(self.text.texture_size[1] + dp(16), self.scroll.height)

    def refresh(self, _button: Optional[Button]) -> None:
        file_info = self.store.file_path or tr("File will be created at first save.")
        self.text.text = trf(
            "File: {file_info}\n\n{json_data}",
            file_info=file_info,
            json_data=self.store.to_pretty_json(),
        )
        self.scroll.scroll_x = 0
        self.scroll.scroll_y = 1


class BehaviorLoggerApp(App):
    """
    Main application.
    """

    title = "Maromizaha behaviors logger"

    def build(self) -> ScreenManager:
        self.store = DataStore()
        self.screen_manager = ScreenManager()
        self.show_json_tab = False
        self.screen_orientation = "landscape"
        self.home_screen = HomeScreen()
        self.scan_screen = ScanScreen(self.store)
        self.scan_list_screen = ScanListScreen(self.store)
        self.behavior_screen = BehaviorScreen(self.store)
        self.viewer_screen = ViewerScreen(self.store)
        self.notes_screen = NotesScreen(self.store)
        self.group_management_screen = GroupManagementScreen()
        self.settings_screen = SettingsScreen()

        self.screen_manager.add_widget(self.home_screen)
        self.screen_manager.add_widget(self.scan_screen)
        self.screen_manager.add_widget(self.scan_list_screen)
        self.screen_manager.add_widget(self.behavior_screen)

        self.screen_manager.add_widget(
            RecordFormScreen(
                self.store,
                "gps",
                "GPS record",
                GPS_FIELDS,
                "add_gps_record",
            )
        )
        self.screen_manager.add_widget(
            RecordFormScreen(
                self.store,
                "alimentation",
                "Alimentation record",
                ALIMENTATION_FIELDS,
                "add_alimentation_record",
            )
        )
        self.screen_manager.add_widget(self.group_management_screen)
        self.screen_manager.add_widget(self.settings_screen)
        self.screen_manager.add_widget(self.viewer_screen)
        self.screen_manager.add_widget(self.notes_screen)
        self.refresh_navigation_visibility()
        return self.screen_manager

    def is_scan_due(self) -> bool:
        return self.store.is_scan_due()

    def refresh_behavior_sequence(self) -> None:
        self.behavior_screen.refresh_sequence()
        self.behavior_screen.refresh_scan_window()

    def set_ui_language(self, language: str) -> None:
        set_language(language)
        for screen in self.screen_manager.screens:
            refresh_i18n_tree(screen)
            refresh_language = getattr(screen, "refresh_language", None)
            if callable(refresh_language):
                refresh_language()
        self.refresh_behavior_sequence()

    def set_screen_orientation(self, orientation: str) -> None:
        self.screen_orientation = orientation
        if platform == "android":
            try:
                from jnius import autoclass

                activity = autoclass("org.kivy.android.PythonActivity").mActivity
                requested = 1 if orientation == "portrait" else 0
                activity.setRequestedOrientation(requested)
            except Exception:
                pass
        else:
            if orientation == "portrait" and Window.width > Window.height:
                Window.size = (Window.height, Window.width)
            elif orientation == "landscape" and Window.height > Window.width:
                Window.size = (Window.height, Window.width)

    def set_json_tab_visible(self, visible: bool) -> None:
        self.show_json_tab = visible
        self.refresh_navigation_visibility()
        if not visible and self.screen_manager.current == "viewer":
            self.screen_manager.current = "settings"

    def refresh_navigation_visibility(self) -> None:
        for screen in self.screen_manager.screens:
            self._refresh_navigation_visibility(screen)

    def _refresh_navigation_visibility(self, widget: Widget) -> None:
        if isinstance(widget, Header):
            widget.refresh_navigation_visibility()
        for child in getattr(widget, "children", []):
            self._refresh_navigation_visibility(child)

    def reload_group_config(self) -> None:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            config_data = json.load(f)

        LIST_FIELDS["group"] = ["-"] + config_data.get("GROUPS_LIST", [])
        GROUPS_COMPOSITION.clear()
        GROUPS_COMPOSITION.update(config_data.get("GROUPS_COMPOSITION", {}))
        self.scan_screen.refresh_group_options()

    def get_current_group_members(self) -> Tuple[str, List[str]]:
        group = ""
        group_widget = self.scan_screen.inputs.get("group")
        if group_widget is not None:
            group = get_widget_text(group_widget)

        if (not group or group == "-") and self.store.data["scan_records"]:
            group = (
                self.store.data["scan_records"][-1].get("values", {}).get("group", "")
            )

        if group == "-":
            group = ""
        return group, GROUPS_COMPOSITION.get(group, [])

    def confirm_reset_session(self) -> None:
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        content.add_widget(
            i18n_label(
                "Create a new JSON file for a new session?",
                halign="center",
                valign="middle",
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        cancel_button = i18n_button("Cancel")
        reset_button = i18n_button("RESET SESSION")
        buttons.add_widget(cancel_button)
        buttons.add_widget(reset_button)
        content.add_widget(buttons)

        popup = Popup(
            title=tr("Confirm reset"),
            content=content,
            size_hint=(0.82, 0.36),
            auto_dismiss=False,
        )
        cancel_button.bind(on_press=lambda _btn: popup.dismiss())
        reset_button.bind(on_press=lambda _btn: self._reset_session(popup))
        popup.open()

    def _reset_session(self, popup: Popup) -> None:
        self.store.reset_session()
        self.scan_screen.reset_form()
        self.behavior_screen.refresh_sequence()
        self.notes_screen.text.text = ""
        popup.dismiss()
        self.screen_manager.current = "scan"

    def start_new_scan(self) -> None:
        self.scan_screen.start_new_scan()
        self.screen_manager.current = "scan"

    def load_scan_for_edit(self, index: int) -> None:
        if self.scan_screen.load_scan_for_edit(index):
            self.screen_manager.current = "scan"

    def go_to(self, screen_name: str) -> None:
        if screen_name == "viewer" and not self.show_json_tab:
            return
        self.screen_manager.current = screen_name


if __name__ == "__main__":
    BehaviorLoggerApp().run()

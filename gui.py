import os
import time
import threading
import ctypes
from datetime import datetime
from PIL import Image, ImageGrab, ImageChops, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox
import math

CAPTURE_DIR = "screen_captures"
DEFAULT_THRES = 10


class ScreenMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Screen Area Monitor")
        self.geometry("450x700")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- State variables ---
        self.bbox = None
        self.monitoring = False
        self.monitor_thread = None
        self.image_references = []
        self.capture_frames = []  # To hold the GUI frames for sorting
        self.sensitivity_var = tk.IntVar(value=DEFAULT_THRES)
        self.capture_session_dir = None

        # --- UI Setup ---
        self.create_widgets()

    def create_widgets(self):
        # --- Main Frame ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_rowconfigure(3, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # --- Controls Frame ---
        controls_frame = ttk.Frame(main_frame)
        controls_frame.grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(1, weight=1)
        controls_frame.grid_columnconfigure(2, weight=1)

        self.select_button = ttk.Button(
            controls_frame, text="1. Select Area", command=self.select_area
        )
        self.select_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.start_button = ttk.Button(
            controls_frame,
            text="2. Start Monitoring",
            command=self.start_monitoring,
            state=tk.DISABLED,
        )
        self.start_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.stop_button = ttk.Button(
            controls_frame,
            text="Stop",
            command=self.stop_monitoring,
            state=tk.DISABLED,
        )
        self.stop_button.grid(row=0, column=2, padx=5, sticky="ew")

        # --- Status Label ---
        self.status_label = ttk.Label(
            main_frame, text="Status: Ready. Please select an area.", anchor="center"
        )
        self.status_label.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )

        # --- Sensitivity Slider ---
        sensitivity_frame = ttk.Frame(main_frame)
        sensitivity_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        sensitivity_frame.grid_columnconfigure(1, weight=1)

        sensitivity_label = ttk.Label(sensitivity_frame, text="Change Threshold:")
        sensitivity_label.grid(row=0, column=0, padx=(0, 5))

        sensitivity_slider = ttk.Scale(
            sensitivity_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.sensitivity_var,
            command=self.update_sensitivity_label,
        )
        sensitivity_slider.grid(row=0, column=1, sticky="ew")

        self.sensitivity_value_label = ttk.Label(
            sensitivity_frame, text=f"{DEFAULT_THRES}", width=3
        )
        self.sensitivity_value_label.grid(row=0, column=2, padx=(5, 0))

        # --- Scrolling Image Display ---
        canvas_frame = ttk.Frame(main_frame, relief="sunken", borderwidth=1)
        canvas_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame)
        self.scrollbar = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.canvas.yview
        )
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def update_sensitivity_label(self, value):
        """Updates the label next to the slider with the current value."""
        self.sensitivity_value_label.config(text=f"{int(float(value))}")

    def _on_mousewheel(self, event):
        """Allows scrolling with the mouse wheel."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def select_area(self):
        """Initiates the screen area selection process."""
        self.withdraw()
        time.sleep(0.2)

        selector = AreaSelector(self)
        self.wait_window(selector)

        self.deiconify()

        if selector.bbox:
            self.bbox = selector.bbox
            self.status_label.config(
                text=f"Area Selected: {self.bbox}. Ready to monitor."
            )
            self.start_button.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="Status: Area selection cancelled.")

    def start_monitoring(self):
        """Starts the background thread for monitoring the screen area."""
        if not self.bbox:
            messagebox.showerror("Error", "Please select an area first.")
            return

        timestamp = datetime.now().strftime("capture_%Y-%m-%d_%H-%M-%S")
        self.capture_session_dir = os.path.join(CAPTURE_DIR, timestamp)
        os.makedirs(self.capture_session_dir, exist_ok=True)

        self.monitoring = True
        self.start_button.config(state=tk.DISABLED)
        self.select_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Status: Monitoring for changes...")

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stops the monitoring thread."""
        self.monitoring = False
        self.start_button.config(state=tk.NORMAL)
        self.select_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"Status: Monitoring stopped. Area: {self.bbox}")

    def calc_pct_diff(self, img1, img2):
        """Calculates the root mean square difference between two images."""
        if img1.size != img2.size or img1.mode != img2.mode:
            return 100.0  # Treat as a massive change

        diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
        hist = diff.histogram()
        sum_of_squares = sum(value * ((idx % 256) ** 2) for idx, value in enumerate(hist))
        rms = math.sqrt(sum_of_squares / float(img1.width * img1.height * 3))
        return (rms / 255) * 100

    def _monitor_loop(self):
        """The core logic that runs in a separate thread to watch for changes."""
        try:
            last_capture = ImageGrab.grab(bbox=self.bbox)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            filename = f"capture_{timestamp}.png"
            filepath = os.path.join(self.capture_session_dir, filename)
            last_capture.save(filepath)
            self.after(0, self.add_capture_to_gui, filepath, 0.0)
        except Exception as e:
            self.after(0, self.handle_monitoring_error, str(e))
            return

        while self.monitoring:
            time.sleep(0.5)
            try:
                current_capture = ImageGrab.grab(bbox=self.bbox)
                
                diff_percent = self.calc_pct_diff(last_capture, current_capture)
                threshold = self.sensitivity_var.get()

                if diff_percent > threshold:
                    last_capture = current_capture
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
                    filename = f"capture_{timestamp}.png"
                    filepath = os.path.join(self.capture_session_dir, filename)
                    last_capture.save(filepath)

                    self.after(0, self.add_capture_to_gui, filepath, diff_percent)
            except Exception as e:
                self.after(0, self.handle_monitoring_error, str(e))
                break

    def handle_monitoring_error(self, error_msg):
        """Shows monitoring errors in the GUI and stops."""
        messagebox.showerror("Monitoring Error", f"An error occurred: {error_msg}")
        self.stop_monitoring()

    def add_capture_to_gui(self, filepath, diff_percent):
        """Loads a captured image and adds it to the scrollable display."""
        try:
            img = Image.open(filepath)
            img.thumbnail((380, 380))
            photo = ImageTk.PhotoImage(img)

            self.image_references.append(photo)

            capture_frame = ttk.Frame(self.scrollable_frame, padding=5)
            capture_frame.filepath = filepath # Store filepath for sorting

            img_label = ttk.Label(capture_frame, image=photo)
            img_label.image = photo
            img_label.pack()

            info_frame = ttk.Frame(capture_frame)
            info_frame.pack(fill=tk.X, expand=True)

            filename_label = ttk.Label(
                info_frame,
                text=f"{os.path.basename(filepath)} (% Change: {diff_percent:.2f})",
                wraplength=300,
            )
            filename_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            delete_button = ttk.Button(
                info_frame,
                text="Delete",
                command=lambda f=filepath: self.delete_capture(f),
            )
            delete_button.pack(side=tk.RIGHT)

            # --- FIX: Re-grid all frames to maintain order ---
            self.capture_frames.insert(0, capture_frame) # Add new frame to the top of the list
            self.redraw_captures()

            self.canvas.update_idletasks()
            self.canvas.yview_moveto(0.0)

        except Exception as e:
            print(f"Failed to display image {filepath}: {e}")
    
    def redraw_captures(self):
        """Clears and redraws all capture frames in the correct order."""
        for widget in self.scrollable_frame.winfo_children():
            widget.grid_forget()
        
        for i, frame in enumerate(self.capture_frames):
            frame.grid(row=i, column=0, pady=5, padx=5, sticky="ew")

    def delete_capture(self, filepath):
        """Deletes a captured image file and removes it from the GUI."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            
            # Find and remove the correct frame from the list
            self.capture_frames = [
                frame for frame in self.capture_frames if frame.filepath != filepath
            ]
            self.redraw_captures()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete {filepath}: {e}")

    def on_closing(self):
        """Handles the window close event to ensure clean shutdown."""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=1)
        self.destroy()


class AreaSelector(tk.Toplevel):
    """A transparent window for selecting a screen area by dragging a rectangle."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.bbox = None
        self.start_x = None
        self.start_y = None
        self.rect = None

        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.configure(bg="grey")
        self.wait_visibility()
        self.grab_set()

        self.canvas = tk.Canvas(
            self, cursor="cross", bg=self.cget("bg"), highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.bind("<Escape>", lambda e: self.close_selector())

    def on_button_press(self, event):
        self.start_x = self.winfo_pointerx()
        self.start_y = self.winfo_pointery()
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2
        )

    def on_mouse_drag(self, event):
        cur_x = self.winfo_pointerx()
        cur_y = self.winfo_pointery()
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        end_x = self.winfo_pointerx()
        end_y = self.winfo_pointery()

        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        right = max(self.start_x, end_x)
        bottom = max(self.start_y, end_y)

        if right - left > 10 and bottom - top > 10:
            self.bbox = (int(left), int(top), int(right), int(bottom))

        self.close_selector()

    def close_selector(self):
        self.grab_release()
        self.destroy()


def set_dpi_awareness():
    """Sets the application to be DPI aware on Windows."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            print("Warning: Could not set DPI awareness.")

def main():
    if not os.path.exists(CAPTURE_DIR):
        os.makedirs(CAPTURE_DIR)
    
    set_dpi_awareness()
    app = ScreenMonitorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
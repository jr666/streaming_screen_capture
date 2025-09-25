import os
import time
import threading
from datetime import datetime
# FIX: Import the 'Image' module from PIL
from PIL import Image, ImageGrab, ImageChops, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

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
        self.sensitivity_var = tk.IntVar(value=DEFAULT_THRES)

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
        controls_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(1, weight=1)
        controls_frame.grid_columnconfigure(2, weight=1)

        self.select_button = ttk.Button(controls_frame, text="1. Select Area", command=self.select_area)
        self.select_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.start_button = ttk.Button(controls_frame, text="2. Start Monitoring", command=self.start_monitoring, state=tk.DISABLED)
        self.start_button.grid(row=0, column=1, padx=5, sticky="ew")

        self.stop_button = ttk.Button(controls_frame, text="Stop", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=2, padx=5, sticky="ew")
        
        # --- Status Label ---
        self.status_label = ttk.Label(main_frame, text="Status: Ready. Please select an area.", anchor="center")
        self.status_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # --- Sensitivity Slider ---
        sensitivity_frame = ttk.Frame(main_frame)
        sensitivity_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        sensitivity_frame.grid_columnconfigure(1, weight=1)
        
        sensitivity_label = ttk.Label(sensitivity_frame, text="Change Threshold:")
        sensitivity_label.grid(row=0, column=0, padx=(0, 5))
        
        sensitivity_slider = ttk.Scale(sensitivity_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.sensitivity_var, command=self.update_sensitivity_label)
        sensitivity_slider.grid(row=0, column=1, sticky="ew")
        #sensitivity_slider.set(DEFAULT_THRES)

        self.sensitivity_value_label = ttk.Label(sensitivity_frame, text=f"{DEFAULT_THRES}", width=3)
        self.sensitivity_value_label.grid(row=0, column=2, padx=(5, 0))

        # --- Scrolling Image Display ---
        canvas_frame = ttk.Frame(main_frame, relief="sunken", borderwidth=1)
        canvas_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        self.canvas = tk.Canvas(canvas_frame)
        self.scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        # Configure the grid for the scrollable frame
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
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
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")


    def select_area(self):
        """Initiates the screen area selection process."""
        self.withdraw() # Hide main window
        time.sleep(0.2) # Give time for window to hide
        
        selector = AreaSelector(self)
        self.wait_window(selector) # Wait until selector is closed
        
        self.deiconify() # Show main window again

        if selector.bbox:
            self.bbox = selector.bbox
            self.status_label.config(text=f"Area Selected: {self.bbox}. Ready to monitor.")
            self.start_button.config(state=tk.NORMAL)
        else:
            self.status_label.config(text="Status: Area selection cancelled.")

    def start_monitoring(self):
        """Starts the background thread for monitoring the screen area."""
        if not self.bbox:
            messagebox.showerror("Error", "Please select an area first.")
            return

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
        """Calculates the percentage difference between two images."""
        diff = ImageChops.difference(img1, img2)
        h = diff.convert('1').histogram()
        #sq = (value*(idx**2) for idx, value in enumerate(h))
        sq = h[:-1]
        sum_of_squares = sum(sq)
        rms = (sum_of_squares/float(diff.width * diff.height))
        #return (100-(rms**0.5))
        return (100-(rms*100))


    def _monitor_loop(self):
        """The core logic that runs in a separate thread to watch for changes."""
        capture_dir = CAPTURE_DIR
        if not os.path.exists(capture_dir):
            os.makedirs(capture_dir)

        try:
            last_capture = ImageGrab.grab(bbox=self.bbox)
            # --- FEATURE 1: Take an immediate first capture ---
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
            filename = f"capture_{timestamp}.png"
            filepath = os.path.join(capture_dir, filename)
            last_capture.save(filepath)
            self.after(0, self.add_capture_to_gui, filepath)
        except Exception as e:
            self.after(0, self.handle_monitoring_error, str(e))
            return
            
        while self.monitoring:
            time.sleep(0.5)
            try:
                current_capture = ImageGrab.grab(bbox=self.bbox)
                diff = ImageChops.difference(last_capture, current_capture)

                # --- FEATURE 2: Use sensitivity slider to check for change ---
                if diff.getbbox(): # Check for any change first to be efficient
                    threshold = self.sensitivity_var.get()
                    # Convert diff to grayscale and get the brightest pixel value
                    #max_diff = diff.convert('L').getextrema()[1]
                    max_diff = self.calc_pct_diff(last_capture, current_capture)
                    if max_diff > threshold:
                        last_capture = current_capture
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
                        filename = f"capture_{timestamp}.png"
                        filepath = os.path.join(capture_dir, filename)
                        last_capture.save(filepath)
                        
                        # Schedule GUI update on the main thread
                        self.after(0, self.add_capture_to_gui, filepath)
            except Exception as e:
                self.after(0, self.handle_monitoring_error, str(e))
                break # Exit loop on error

    def handle_monitoring_error(self, error_msg):
        """Shows monitoring errors in the GUI and stops."""
        messagebox.showerror("Monitoring Error", f"An error occurred: {error_msg}")
        self.stop_monitoring()

    def add_capture_to_gui(self, filepath):
        """Loads a captured image and adds it to the scrollable display."""
        try:
            # FIX: Use the correct Image.open() method
            img = Image.open(filepath)
            # Resize image for thumbnail view
            img.thumbnail((380, 380))
            
            photo = ImageTk.PhotoImage(img)
            self.image_references.append(photo)

            # Create a frame for each capture (image + label)
            capture_frame = ttk.Frame(self.scrollable_frame, padding=5)
            
            img_label = ttk.Label(capture_frame, image=photo)
            img_label.image = photo # Keep reference attached to widget
            img_label.pack()
            
            filename_label = ttk.Label(capture_frame, text=os.path.basename(filepath), wraplength=400)
            filename_label.pack()

            # --- ERROR FIX: Use grid instead of pack to avoid ordering issues ---
            # Move all existing children down by one row
            for child in self.scrollable_frame.winfo_children():
                row = child.grid_info().get("row", 0)
                child.grid(row=row + 1, column=0, pady=5, padx=5, sticky="ew")
            
            # Place the new frame at the top (row 0)
            capture_frame.grid(row=0, column=0, pady=5, padx=5, sticky="ew")

            # Auto-scroll to the top to see the latest image
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(0.0)

        except Exception as e:
            print(f"Failed to display image {filepath}: {e}")

    def on_closing(self):
        """Handles the window close event to ensure clean shutdown."""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=1) # Wait for thread to finish
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

        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3) # Make window semi-transparent
        self.attributes("-topmost", True)
        self.configure(bg='grey')
        self.wait_visibility() # Ensures attributes are applied
        self.grab_set() # Capture all events

        self.canvas = tk.Canvas(self, cursor="cross", bg=self.cget('bg'), highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.bind("<Escape>", lambda e: self.close_selector())

    def on_button_press(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=2)

    def on_mouse_drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        
        left = min(self.start_x, end_x)
        top = min(self.start_y, end_y)
        right = max(self.start_x, end_x)
        bottom = max(self.start_y, end_y)

        if right - left > 10 and bottom - top > 10: # Minimum size check
            self.bbox = (int(left), int(top), int(right), int(bottom))
        
        self.close_selector()

    def close_selector(self):
        self.grab_release()
        self.destroy()

def main():
    app = ScreenMonitorApp()
    app.mainloop()
    
if __name__ == "__main__":
    main()



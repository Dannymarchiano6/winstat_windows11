import json
import os
import sys
import time
import threading
import queue
import psutil
import tkinter as tk
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item
import customtkinter as ctk

# --- KONFIGURASI TRAY IKON ---
ICON_DIR = "icons"
if not os.path.exists(ICON_DIR):
    os.makedirs(ICON_DIR)

def generate_default_icon():
    path = os.path.join(ICON_DIR, "icon_default.ico")
    if not os.path.exists(path):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([4, 4, 60, 60], fill=(0, 229, 255, 255))
        image.save(path, format='ICO')
    return path

detail_window_open = False

def show_detail_window():
    global detail_window_open
    if detail_window_open: return
    detail_window_open = True
    
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    
    BG_ROOT = "#18181b"    # Warna dasar gelap
    BG_CARD = "#212830"    # Warna kartu metrik
    COLOR_CYAN = "#00e5ff"
    COLOR_YELLOW = "#facc15"
    COLOR_GREY = "#3b4d61"
    
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    w = min(340, screen_w)
    h = min(520, max(1, screen_h - 48))
    
    # Rata kanan sempurna dan persis di atas Taskbar Windows 11 (tinggi 48px)
    x = screen_w - w
    y = max(0, screen_h - h - 48)
    
    root.geometry(f"{w}x{h}+{x}+{y}")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    
    # EFEK TRANSPARAN KACA (MICA STYLE)
    root.attributes("-alpha", 0.93) 
    root.configure(bg=BG_ROOT)
    
    # FRAME UTAMA (SUDUT SIKU-SIKU AGAR MENEMPEL RAPI DI POJOK LAYAR)
    main_frame = ctk.CTkFrame(root, fg_color=BG_ROOT, corner_radius=0)
    main_frame.pack(fill="both", expand=True)

    def start_move(event): root.x, root.y = event.x, event.y
    def stop_move(event): root.x, root.y = None, None
    def do_move(event):
        deltax, deltay = event.x - root.x, event.y - root.y
        new_x, new_y = root.winfo_x() + deltax, root.winfo_y() + deltay
        root.geometry(f"+{new_x}+{new_y}")

    main_frame.bind("<ButtonPress-1>", start_move)
    main_frame.bind("<ButtonRelease-1>", stop_move)
    main_frame.bind("<B1-Motion>", do_move)
    main_frame.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
    stop_event = threading.Event()
    metrics_queue = queue.Queue(maxsize=1)

    def stop_updates(event):
        global detail_window_open
        if event.widget is root:
            stop_event.set()
            detail_window_open = False

    root.bind("<Destroy>", stop_updates)

    def publish_metrics(metrics):
        try:
            metrics_queue.put_nowait(metrics)
        except queue.Full:
            try:
                metrics_queue.get_nowait()
            except queue.Empty:
                pass
            metrics_queue.put_nowait(metrics)

    # SCROLL FRAME DENGAN SCROLLBAR TERSEMBUNYI (TAPI TETAP BISA DI-SCROLL)
    scroll_frame = ctk.CTkScrollableFrame(
        main_frame, 
        fg_color="transparent", 
        bg_color="transparent", 
        corner_radius=0,
        scrollbar_button_color=BG_ROOT,        # Menyembunyikan warna scrollbar
        scrollbar_button_hover_color=BG_CARD   # Hanya terlihat samar saat disorot
    )
    scroll_frame.pack(fill="both", expand=True, padx=2, pady=5)
    scroll_frame.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))

    # CANVAS RING
    canvas = tk.Canvas(scroll_frame, width=w-20, height=110, bg=BG_ROOT, highlightthickness=0)
    canvas.pack(pady=(10, 5))
    canvas.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
    
    def draw_ring(cvs, x, y, radius, thickness, percent, color, bg_color):
        cvs.create_oval(x-radius, y-radius, x+radius, y+radius, outline=bg_color, width=thickness)
        extent = -(percent / 100.0) * 360
        return cvs.create_arc(x-radius, y-radius, x+radius, y+radius, start=90, extent=extent, outline=color, width=thickness, style="arc")

    disk_arc = draw_ring(canvas, 85, 55, 38, 7, 0, COLOR_YELLOW, COLOR_GREY)
    disk_pct_text = canvas.create_text(85, 48, text="0%", fill="white", font=("Segoe UI", 12, "bold"))
    canvas.create_text(85, 68, text="Disk", fill="#a1b0c0", font=("Segoe UI", 8))
    
    ram_arc = draw_ring(canvas, 215, 55, 38, 7, 0, COLOR_CYAN, COLOR_GREY)
    ram_pct_text = canvas.create_text(215, 48, text="0%", fill="white", font=("Segoe UI", 12, "bold"))
    canvas.create_text(215, 68, text="RAM", fill="#a1b0c0", font=("Segoe UI", 8))
    status_var = ctk.StringVar(value="Memuat metrik...")
    ctk.CTkLabel(scroll_frame, textvariable=status_var, text_color="#a1b0c0", font=("Segoe UI", 9)).pack(pady=(0, 4))

    # HELPER KARTU DENGAN SUDUT MELENGKUNG DI DALAMNYA
    def create_card(parent):
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        frame.pack(fill="x", padx=10, pady=5) 
        frame.columnconfigure(1, weight=1)
        frame.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
        return frame

    def add_row(parent, row_idx, label_text, value_text_var, dot_color=None, is_title=False):
        lbl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        lbl_frame.grid(row=row_idx, column=0, sticky="w", padx=(10, 5), pady=2)
        
        if dot_color:
            ctk.CTkLabel(lbl_frame, text="●", text_color=dot_color, font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
            
        color = COLOR_CYAN if is_title else "white"
        font = ("Segoe UI", 9, "bold") if is_title else ("Segoe UI", 10)
        lbl = ctk.CTkLabel(lbl_frame, text=label_text, text_color=color, font=font)
        lbl.pack(side="left")
        
        val_lbl = ctk.CTkLabel(parent, textvariable=value_text_var, text_color="white", font=("Segoe UI", 10, "bold" if not is_title else "normal"))
        val_lbl.grid(row=row_idx, column=1, sticky="e", padx=(5, 10), pady=2)
        
        lbl.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
        val_lbl.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))

    # KARTU DISK
    card_disk = create_card(scroll_frame)
    title_disk = ctk.CTkLabel(card_disk, text="DISK", text_color=COLOR_CYAN, font=("Segoe UI", 9, "bold"))
    title_disk.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 1))
    title_disk.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
    
    disk_free_var, disk_read_var, disk_write_var = ctk.StringVar(), ctk.StringVar(), ctk.StringVar()
    add_row(card_disk, 1, "Free", disk_free_var)
    add_row(card_disk, 2, "Read", disk_read_var)
    add_row(card_disk, 3, "Write", disk_write_var)
    ctk.CTkFrame(card_disk, height=4, fg_color="transparent").grid(row=4, column=0)

    # KARTU RAM
    card_ram = create_card(scroll_frame)
    ctk.CTkFrame(card_ram, height=4, fg_color="transparent").grid(row=0, column=0)
    ram_inuse_var, ram_cached_var, ram_free_var = ctk.StringVar(), ctk.StringVar(), ctk.StringVar()
    add_row(card_ram, 1, "In use", ram_inuse_var, dot_color=COLOR_CYAN)
    add_row(card_ram, 2, "Cached / standby", ram_cached_var, dot_color=COLOR_YELLOW)
    add_row(card_ram, 3, "Free", ram_free_var, dot_color="#8899aa")
    ctk.CTkFrame(card_ram, height=4, fg_color="transparent").grid(row=4, column=0)

    # KARTU PROCESSES
    card_proc = create_card(scroll_frame)
    title_proc = ctk.CTkLabel(card_proc, text="PROCESSES", text_color=COLOR_CYAN, font=("Segoe UI", 9, "bold"))
    title_proc.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 1))
    title_proc.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
    
    proc_vars = [(ctk.StringVar(), ctk.StringVar()) for _ in range(7)]
    for i in range(7):
        lbl = ctk.CTkLabel(card_proc, textvariable=proc_vars[i][0], text_color="white", font=("Segoe UI", 10, "bold"))
        lbl.grid(row=i+1, column=0, sticky="w", padx=10, pady=0)
        lbl.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
        
        val = ctk.CTkLabel(card_proc, textvariable=proc_vars[i][1], text_color="white", font=("Segoe UI", 10))
        val.grid(row=i+1, column=1, sticky="e", padx=10, pady=0)
        val.bind("<Button-3>", lambda e: (setattr(sys.modules[__name__], 'detail_window_open', False), root.destroy()))
    ctk.CTkFrame(card_proc, height=4, fg_color="transparent").grid(row=8, column=0)

    # KARTU COMMITTED
    card_commit = create_card(scroll_frame)
    ctk.CTkFrame(card_commit, height=4, fg_color="transparent").grid(row=0, column=0)
    commit_var, faults_var, pagefile_var = ctk.StringVar(), ctk.StringVar(), ctk.StringVar()
    add_row(card_commit, 1, "Committed", commit_var)
    add_row(card_commit, 2, "Page faults / s", faults_var)
    add_row(card_commit, 3, "Page file", pagefile_var)
    ctk.CTkFrame(card_commit, height=4, fg_color="transparent").grid(row=4, column=0)

    def collect_data():
        previous_disk_io = psutil.disk_io_counters()
        previous_time = time.monotonic()
        previous_page_faults = None

        while not stop_event.is_set():
            try:
                current_time = time.monotonic()
                time_diff = max(current_time - previous_time, 1)
                disk = psutil.disk_usage('/')
                current_disk_io = psutil.disk_io_counters()
                ram = psutil.virtual_memory()
                swap = psutil.swap_memory()

                processes = []
                current_page_faults = 0
                for process in psutil.process_iter(['name', 'memory_info']):
                    try:
                        info = process.info
                        memory = info['memory_info']
                        if memory is None:
                            continue
                        current_page_faults += memory.num_page_faults
                        name = info['name']
                        if name:
                            processes.append((name, memory.rss))
                    except (psutil.Error, OSError, AttributeError):
                        continue

                processes.sort(key=lambda process: process[1], reverse=True)
                unique_processes = []
                seen = set()
                for name, memory in processes:
                    normalized_name = name.lower()
                    if normalized_name not in seen and normalized_name not in ('system idle process', 'system'):
                        seen.add(normalized_name)
                        unique_processes.append((name.replace(".exe", "").lower(), memory))
                    if len(unique_processes) == 7:
                        break

                if previous_disk_io is None or current_disk_io is None:
                    disk_read = disk_write = "N/A"
                else:
                    disk_read = f"{max(0, current_disk_io.read_bytes - previous_disk_io.read_bytes) / time_diff / 1024:.1f} KB/s"
                    disk_write = f"{max(0, current_disk_io.write_bytes - previous_disk_io.write_bytes) / time_diff / 1024:.1f} KB/s"

                metrics = {
                    "disk_percent": disk.percent,
                    "disk_free": f"{disk.free / (1024**3):.1f} GB / {disk.total / (1024**3):.0f} GB",
                    "disk_read": disk_read,
                    "disk_write": disk_write,
                    "ram_percent": ram.percent,
                    "ram_in_use": f"{ram.used / (1024**3):.1f} GB",
                    "ram_cached": f"{(ram.available - ram.free) / (1024**2):.1f} MB",
                    "ram_free": f"{ram.free / (1024**2):.1f} MB" if ram.free < 1024**3 else f"{ram.free / (1024**3):.1f} GB",
                    "processes": [(name, f"{memory / (1024**2):.1f} MB") for name, memory in unique_processes],
                    "commit": f"{swap.used / (1024**3):.1f} GB / {swap.total / (1024**3):.1f} GB",
                    "pagefile": f"{swap.percent}% used",
                    "faults": f"{int((current_page_faults - previous_page_faults) / time_diff):,}" if previous_page_faults is not None else "0",
                }
                previous_disk_io = current_disk_io
                previous_time = current_time
                previous_page_faults = current_page_faults
                publish_metrics(metrics)
            except (psutil.Error, OSError) as error:
                publish_metrics({"error": str(error)})

            stop_event.wait(1)

    def update_data():
        if stop_event.is_set():
            return
        try:
            metrics = metrics_queue.get_nowait()
        except queue.Empty:
            root.after(100, update_data)
            return

        if "error" in metrics:
            status_var.set(f"Metrik tidak tersedia: {metrics['error']}")
        else:
            status_var.set("Metrik diperbarui")
            disk_free_var.set(metrics["disk_free"])
            disk_read_var.set(metrics["disk_read"])
            disk_write_var.set(metrics["disk_write"])
            canvas.itemconfig(disk_arc, extent=-(metrics["disk_percent"] / 100.0) * 360)
            canvas.itemconfig(disk_pct_text, text=f"{int(metrics['disk_percent'])}%")
            ram_inuse_var.set(metrics["ram_in_use"])
            ram_cached_var.set(metrics["ram_cached"])
            ram_free_var.set(metrics["ram_free"])
            canvas.itemconfig(ram_arc, extent=-(metrics["ram_percent"] / 100.0) * 360)
            canvas.itemconfig(ram_pct_text, text=f"{int(metrics['ram_percent'])}%")
            for index, (name, memory) in enumerate(metrics["processes"]):
                proc_vars[index][0].set(name)
                proc_vars[index][1].set(memory)
            for index in range(len(metrics["processes"]), 7):
                proc_vars[index][0].set("")
                proc_vars[index][1].set("")
            commit_var.set(metrics["commit"])
            pagefile_var.set(metrics["pagefile"])
            faults_var.set(metrics["faults"])

        root.after(100, update_data)

    threading.Thread(target=collect_data, daemon=True).start()
    update_data()
    root.mainloop()

def on_show_details(icon, item):
    threading.Thread(target=show_detail_window, daemon=True).start()

def on_exit(icon, item):
    icon.stop()

def main():
    icon_path = generate_default_icon()
    menu = pystray.Menu(item('Tampilkan Detail', on_show_details, default=True), item('Keluar', on_exit))
    try:
        from PIL import Image
        icon_image = Image.open(icon_path)
        icon_instance = pystray.Icon("WinstatCustom", icon_image, "Winstat Pro", menu)
        print("Winstat Pro siap. Klik kanan pada jendela untuk menutupnya.")
        icon_instance.run()
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__": main()
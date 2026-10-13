import json
import os
import sys
import time
import threading
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

last_disk_io = psutil.disk_io_counters()
last_time = time.time()
last_page_faults = 0

def get_total_page_faults():
    faults = 0
    for p in psutil.process_iter(['memory_info']):
        try:
            if p.info['memory_info']:
                faults += p.info['memory_info'].num_page_faults
        except: pass
    return faults

detail_window_open = False

def show_detail_window():
    global detail_window_open, last_disk_io, last_time, last_page_faults
    if detail_window_open: return
    detail_window_open = True
    
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    
    BG_ROOT = "#18181b"    # Warna dasar gelap
    BG_CARD = "#212830"    # Warna kartu metrik
    COLOR_CYAN = "#00e5ff"
    COLOR_YELLOW = "#facc15"
    COLOR_GREY = "#3b4d61"
    
    w, h = 340, 520 
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    
    # Rata kanan sempurna dan persis di atas Taskbar Windows 11 (tinggi 48px)
    x = screen_w - w
    y = screen_h - h - 48 
    
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

    last_page_faults = get_total_page_faults()

    def update_data():
        global last_disk_io, last_time, last_page_faults
        if not detail_window_open: return
            
        current_time = time.time()
        time_diff = current_time - last_time if current_time - last_time > 0 else 1
        
        # DISK
        disk = psutil.disk_usage('/')
        disk_pct = disk.percent
        disk_free_gb = disk.free / (1024**3)
        disk_total_gb = disk.total / (1024**3)
        disk_free_var.set(f"{disk_free_gb:.1f} GB / {disk_total_gb:.0f} GB")
        
        current_disk_io = psutil.disk_io_counters()
        read_bps = (current_disk_io.read_bytes - last_disk_io.read_bytes) / time_diff
        write_bps = (current_disk_io.write_bytes - last_disk_io.write_bytes) / time_diff
        
        disk_read_var.set(f"{read_bps / 1024:.1f} KB/s")
        disk_write_var.set(f"{write_bps / 1024:.1f} KB/s")
        
        canvas.itemconfig(disk_arc, extent=-(disk_pct / 100.0) * 360)
        canvas.itemconfig(disk_pct_text, text=f"{int(disk_pct)}%")
        
        # RAM
        ram = psutil.virtual_memory()
        ram_pct = ram.percent
        ram_inuse_gb = ram.used / (1024**3)
        ram_free_mb = ram.free / (1024**2)
        ram_cached_mb = (ram.available - ram.free) / (1024**2)
        
        ram_inuse_var.set(f"{ram_inuse_gb:.1f} GB")
        ram_cached_var.set(f"{ram_cached_mb:.1f} MB")
        ram_free_var.set(f"{ram_free_mb:.1f} MB" if ram_free_mb < 1024 else f"{ram_free_mb/1024:.1f} GB")
        
        canvas.itemconfig(ram_arc, extent=-(ram_pct / 100.0) * 360)
        canvas.itemconfig(ram_pct_text, text=f"{int(ram_pct)}%")
        
        # PROCESSES
        procs = []
        for p in psutil.process_iter(['name', 'memory_info']):
            try:
                mem = p.info['memory_info'].rss
                procs.append((p.info['name'], mem))
            except: pass
        procs.sort(key=lambda x: x[1], reverse=True)
        
        unique_procs = []
        seen = set()
        for name, mem in procs:
            if name.lower() not in seen and name.lower() not in ['system idle process', 'system']:
                seen.add(name.lower())
                unique_procs.append((name.replace(".exe", ""), mem))
            if len(unique_procs) >= 7: break
            
        for i in range(7):
            if i < len(unique_procs):
                name, mem = unique_procs[i]
                mem_mb = mem / (1024**2)
                proc_vars[i][0].set(name.lower())
                proc_vars[i][1].set(f"{mem_mb:.1f} MB")
            else:
                proc_vars[i][0].set("")
                proc_vars[i][1].set("")
                
        # COMMITTED
        swap = psutil.swap_memory()
        commit_used_gb = swap.used / (1024**3)
        commit_total_gb = swap.total / (1024**3)
        commit_var.set(f"{commit_used_gb:.1f} GB / {commit_total_gb:.1f} GB")
        pagefile_var.set(f"{swap.percent}% used")
        
        current_faults = get_total_page_faults()
        faults_diff = current_faults - last_page_faults
        faults_var.set(f"{int(faults_diff / time_diff):,}")
        
        last_disk_io = current_disk_io
        last_time = current_time
        last_page_faults = current_faults
        
        root.after(1000, update_data)

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
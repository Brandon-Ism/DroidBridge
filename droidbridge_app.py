import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
import pathlib
import tempfile
from datetime import datetime
from PIL import Image

# Technical IDE Appearance
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

def format_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_name[i]}"

class ADBManager:
    """Handles all ADB operations."""
    def __init__(self):
        self.start_server()

    def start_server(self):
        try:
            subprocess.run(["adb", "start-server"], check=True, capture_output=True)
        except FileNotFoundError:
            messagebox.showerror("ADB Error", "ADB is not installed or not in PATH.")
        except subprocess.CalledProcessError as e:
            messagebox.showerror("ADB Error", f"Failed to start ADB server: {e}")

    def run_command(self, args, timeout=10):
        cmd = ["adb"] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Command timed out", -1
        except Exception as e:
            return "", str(e), -1

    def ls(self, path):
        quoted_path = f'"{path}"'
        stdout, stderr, code = self.run_command(["shell", "ls", "-l", quoted_path])
        if code != 0:
            if "device unauthorized" in stderr.lower():
                raise Exception("ADB: Device unauthorized. Please accept the RSA key prompt on your Android screen.")
            if "No such file or directory" in stderr:
                return []
            raise Exception(f"Failed to list directory: {stderr}")

        files = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue
            
            parts = line.split(maxsplit=7)
            if len(parts) >= 8:
                perms = parts[0]
                is_dir = perms.startswith('d')
                
                try:
                    size = format_size(int(parts[4])) if not is_dir else "--"
                except ValueError:
                    size = "--"
                    
                date = f"{parts[5]} {parts[6]}"
                name = parts[7].split(" -> ")[0]
                
                if name == "." or name == "..":
                    continue
                    
                files.append({
                    'name': name, 
                    'is_dir': is_dir,
                    'size': size,
                    'date': date
                })
                
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return files

    def pull(self, remote_paths, local_dest):
        if not isinstance(remote_paths, list):
            remote_paths = [remote_paths]
        for rp in remote_paths:
            stdout, stderr, code = self.run_command(["pull", rp, local_dest], timeout=3600)
            if code != 0:
                raise Exception(f"Pull failed for {rp}: {stderr}")

    def push(self, local_paths, remote_dest):
        if not isinstance(local_paths, list):
            local_paths = [local_paths]
        for lp in local_paths:
            stdout, stderr, code = self.run_command(["push", lp, remote_dest], timeout=3600)
            if code != 0:
                raise Exception(f"Push failed for {lp}: {stderr}")

class LocalManager:
    """Handles local macOS filesystem operations."""
    def ls(self, path):
        files = []
        try:
            p = pathlib.Path(path)
            for entry in p.iterdir():
                if entry.name.startswith('.'):
                    continue
                    
                is_dir = entry.is_dir()
                try:
                    stat = entry.stat()
                    size = format_size(stat.st_size) if not is_dir else "--"
                    date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                except (PermissionError, FileNotFoundError):
                    size = "--"
                    date = "--"
                    
                files.append({
                    'name': entry.name, 
                    'is_dir': is_dir, 
                    'path': str(entry),
                    'size': size,
                    'date': date
                })
        except PermissionError:
            raise Exception(f"Permission denied: {path}")
        except FileNotFoundError:
            raise Exception(f"Path not found: {path}")
            
        files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return files

class MacDroidApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("DroidBridge")
        self.geometry("1400x800")
        self.minsize(1000, 600)
        
        self.adb = ADBManager()
        self.local_fs = LocalManager()
        
        self.local_path = str(pathlib.Path.home()) + "/"
        self.remote_path = "/sdcard/"
        
        self.drag_data = {"items": [], "source": None}
        self.drag_window = None
        
        self.active_pane = "local" 
        self.current_preview_image = None
        
        self._configure_treeview_style()
        self._build_ui()
        
        # Bindings for transfers and quick look
        self.bind("<F5>", self.on_f5_press)
        self.bind("<space>", lambda e: self.quick_look())
        
        self.load_local_directory(self.local_path)
        self.load_remote_directory(self.remote_path)

    def _configure_treeview_style(self):
        style = ttk.Style(self)
        style.theme_use("default")
        
        bg_color = "#1e1e1e"
        fg_color = "#d4d4d4"
        sel_bg = "#264f78"
        header_bg = "#2d2d2d"
        font = ("Menlo", 12)
        
        style.configure("Treeview", background=bg_color, foreground=fg_color, rowheight=24,
                        fieldbackground=bg_color, bordercolor="#3e3e42", borderwidth=0, font=font)
        style.map('Treeview', background=[('selected', sel_bg)])
        
        style.configure("Treeview.Heading", background=header_bg, foreground=fg_color,
                        relief="flat", font=("Menlo", 12, "bold"))
        style.map("Treeview.Heading", background=[('active', '#3e3e42')])

    def _build_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3) # Local
        self.grid_columnconfigure(1, weight=3) # Remote
        self.grid_columnconfigure(2, weight=1) # Preview
        
        # Left Pane: Local Mac
        self.left_pane = ctk.CTkFrame(self, corner_radius=0, fg_color="#1e1e1e")
        self.left_pane.grid(row=0, column=0, sticky="nsew", padx=(5,2), pady=5)
        self._build_pane(self.left_pane, "Local Mac", is_local=True)
        
        # Middle Pane: Android
        self.right_pane = ctk.CTkFrame(self, corner_radius=0, fg_color="#1e1e1e")
        self.right_pane.grid(row=0, column=1, sticky="nsew", padx=(2,2), pady=5)
        self._build_pane(self.right_pane, "Android Device", is_local=False)
        
        # Right Pane: Preview
        self.preview_pane = ctk.CTkFrame(self, corner_radius=0, fg_color="#252526")
        self.preview_pane.grid(row=0, column=2, sticky="nsew", padx=(2,5), pady=5)
        self._build_preview_pane()
        
        # Bottom F-Key Bar
        self._build_fkey_bar()

    def _build_pane(self, parent, title, is_local):
        parent.grid_rowconfigure(2, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(parent, text=f" [{title}] ", font=("Menlo", 13, "bold"), text_color="#569cd6")
        lbl.grid(row=0, column=0, sticky="w", pady=(5, 5), padx=5)
        
        nav_frame = ctk.CTkFrame(parent, height=30, fg_color="transparent")
        nav_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5), padx=5)
        nav_frame.grid_columnconfigure(1, weight=1)
        
        up_cmd = self.go_up_local if is_local else self.go_up_remote
        up_btn = ctk.CTkButton(nav_frame, text="..", width=30, height=24, font=("Menlo", 12), command=up_cmd)
        up_btn.grid(row=0, column=0, padx=(0, 5))
        
        addr_var = tk.StringVar()
        if is_local:
            self.local_addr_var = addr_var
        else:
            self.remote_addr_var = addr_var
            
        addr_entry = ctk.CTkEntry(nav_frame, textvariable=addr_var, height=24, font=("Menlo", 12), fg_color="#2d2d2d", border_width=0)
        addr_entry.grid(row=0, column=1, sticky="ew")
        
        go_cmd = self.go_local_address if is_local else self.go_remote_address
        addr_entry.bind("<Return>", lambda e: go_cmd())

        columns = ("name", "size", "date")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="extended")
        
        tree.heading("name", text="Name", anchor="w")
        tree.heading("size", text="Size", anchor="e")
        tree.heading("date", text="Date", anchor="w")
        
        tree.column("name", width=250, anchor="w")
        tree.column("size", width=80, anchor="e")
        tree.column("date", width=120, anchor="w")
        
        tree.tag_configure("dir", foreground="#569cd6")
        tree.tag_configure("file", foreground="#d4d4d4")
        
        tree.grid(row=2, column=0, sticky="nsew", padx=(5,0), pady=(0,5))
        
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=(0,5), padx=(0,5))
        tree.configure(yscrollcommand=scrollbar.set)
        
        if is_local:
            self.local_tree = tree
            tree.bind("<FocusIn>", lambda e: self.set_active_pane("local"))
        else:
            self.remote_tree = tree
            tree.bind("<FocusIn>", lambda e: self.set_active_pane("remote"))
            
        tree.bind("<<TreeviewSelect>>", lambda e: self.on_select(is_local))
        tree.bind("<Double-1>", lambda e: self.on_double_click(is_local))
        tree.bind("<ButtonPress-1>", lambda e: self.on_drag_start(e, is_local))
        tree.bind("<B1-Motion>", self.on_drag_motion)
        tree.bind("<ButtonRelease-1>", lambda e: self.on_drag_release(e, is_local))

    def _build_preview_pane(self):
        self.preview_pane.grid_rowconfigure(1, weight=1)
        self.preview_pane.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(self.preview_pane, text=" [Preview] ", font=("Menlo", 13, "bold"), text_color="#569cd6")
        lbl.grid(row=0, column=0, sticky="w", pady=(5, 5), padx=5)
        
        self.preview_image_label = ctk.CTkLabel(self.preview_pane, text="No Image Selected", font=("Menlo", 12))
        self.preview_image_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        self.preview_info_label = ctk.CTkLabel(self.preview_pane, text="", font=("Menlo", 11), justify="left")
        self.preview_info_label.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _build_fkey_bar(self):
        fkey_frame = ctk.CTkFrame(self, height=30, corner_radius=0, fg_color="#007acc")
        fkey_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        
        keys = [("F3 View (Space)", self.quick_look), ("F4 Edit", None), 
                ("F5 Copy", self.on_f5_press), ("F6 Move", None), ("F8 Delete", None)]
        
        for i, (text, cmd) in enumerate(keys):
            fkey_frame.grid_columnconfigure(i, weight=1)
            btn = ctk.CTkButton(fkey_frame, text=text, fg_color="transparent", 
                                font=("Menlo", 12, "bold"), text_color="white", hover_color="#005999", corner_radius=0, command=cmd)
            btn.grid(row=0, column=i, sticky="ew", padx=1)
            if 'F3' in text:
                self.bind("<F3>", lambda e: self.quick_look())
            
        self.status_var = tk.StringVar(value="Ready")
        status_lbl = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w", fg_color="#007acc", font=("Menlo", 12), text_color="white")
        status_lbl.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10)

    def set_active_pane(self, pane):
        self.active_pane = pane

    # --- Previews and Thumbnails ---

    def on_select(self, is_local):
        tree = self.local_tree if is_local else self.remote_tree
        selected = tree.selection()
        
        if len(selected) != 1:
            self.clear_preview()
            return
            
        item = selected[0]
        tags = tree.item(item, "tags")
        name = tags[0]
        is_dir = tags[1] == 'dir'
        
        if is_dir:
            self.clear_preview()
            return
            
        ext = name.lower().split('.')[-1] if '.' in name else ''
        if ext in ['jpg', 'jpeg', 'png', 'webp', 'bmp']:
            path = self.local_path + name if is_local else self.remote_path + name
            self.generate_thumbnail(path, is_local)
        else:
            self.clear_preview()
            self.preview_image_label.configure(text=f"File: {name}")

    def clear_preview(self):
        self.preview_image_label.configure(image=None, text="No Image Selected")
        self.preview_info_label.configure(text="")
        self.current_preview_image = None

    def generate_thumbnail(self, path, is_local, for_quicklook=False):
        if not for_quicklook:
            self.preview_image_label.configure(image=None, text="Loading...")
            self.preview_info_label.configure(text="")
            
        def fetch():
            tmp_path = None
            try:
                if is_local:
                    img_path = path
                else:
                    tmp_dir = tempfile.gettempdir()
                    filename = os.path.basename(path)
                    tmp_path = os.path.join(tmp_dir, filename)
                    # Silently pull
                    self.adb.pull(path, tmp_dir)
                    img_path = tmp_path
                    
                with Image.open(img_path) as img:
                    info_text = f"Name: {os.path.basename(path)}\nFormat: {img.format}\nSize: {img.size[0]}x{img.size[1]}"
                    
                    if for_quicklook:
                        # Max size for quicklook
                        img.thumbnail((800, 800))
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        self.after(0, self.show_quicklook_window, ctk_img, info_text)
                    else:
                        # Thumbnail size for sidebar
                        # we need to be careful with CTkImage scaling, max width is roughly 250
                        img.thumbnail((250, 250))
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        self.after(0, self.update_preview_ui, ctk_img, info_text)
                        
            except Exception as e:
                if not for_quicklook:
                    self.after(0, self.preview_image_label.configure, {"text": "Preview Error"})
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except: pass
                    
        threading.Thread(target=fetch, daemon=True).start()

    def update_preview_ui(self, image, info_text):
        self.current_preview_image = image
        self.preview_image_label.configure(image=image, text="")
        self.preview_info_label.configure(text=info_text)

    def quick_look(self):
        tree = self.local_tree if self.active_pane == "local" else self.remote_tree
        selected = tree.selection()
        if len(selected) != 1: return
        
        item = selected[0]
        tags = tree.item(item, "tags")
        name = tags[0]
        is_dir = tags[1] == 'dir'
        if is_dir: return
        
        ext = name.lower().split('.')[-1] if '.' in name else ''
        if ext in ['jpg', 'jpeg', 'png', 'webp', 'bmp']:
            path = self.local_path + name if self.active_pane == "local" else self.remote_path + name
            self.generate_thumbnail(path, self.active_pane == "local", for_quicklook=True)

    def show_quicklook_window(self, image, info_text):
        ql = tk.Toplevel(self)
        ql.title("QuickLook")
        ql.geometry(f"{image.cget('size')[0] + 40}x{image.cget('size')[1] + 40}")
        ql.configure(bg="#1e1e1e")
        ql.attributes("-topmost", True)
        
        lbl = ctk.CTkLabel(ql, image=image, text="")
        lbl.pack(expand=True, fill="both", padx=20, pady=20)
        
        # Bind escape and space to close
        ql.bind("<Escape>", lambda e: ql.destroy())
        ql.bind("<space>", lambda e: ql.destroy())

    # --- Navigation Logic ---
    
    def go_up_local(self):
        if self.local_path == "/": return
        new_path = str(pathlib.Path(self.local_path).parent)
        if not new_path.endswith('/'): new_path += '/'
        self.load_local_directory(new_path)
        
    def go_up_remote(self):
        if self.remote_path == "/": return
        parts = self.remote_path.rstrip('/').split('/')
        if len(parts) <= 1: new_path = "/"
        else: new_path = "/".join(parts[:-1]) + "/"
        self.load_remote_directory(new_path)

    def go_local_address(self):
        new_path = self.local_addr_var.get().strip()
        if not new_path.endswith('/'): new_path += '/'
        self.load_local_directory(new_path)

    def go_remote_address(self):
        new_path = self.remote_addr_var.get().strip()
        if not new_path.endswith('/'): new_path += '/'
        self.load_remote_directory(new_path)

    def load_local_directory(self, path):
        self.local_path = path
        self.local_addr_var.set(path)
        for item in self.local_tree.get_children(): self.local_tree.delete(item)
            
        try:
            files = self.local_fs.ls(path)
            for f in files:
                tag = 'dir' if f['is_dir'] else 'file'
                iid = self.local_tree.insert("", "end", values=(f['name'], f['size'], f['date']))
                self.local_tree.item(iid, tags=(f['name'], tag))
        except Exception as e:
            messagebox.showerror("Local Error", str(e))

    def load_remote_directory(self, path):
        self.status_var.set(f"Loading {path}...")
        self.remote_path = path
        self.remote_addr_var.set(path)
        for item in self.remote_tree.get_children(): self.remote_tree.delete(item)
            
        def fetch():
            try:
                files = self.adb.ls(path)
                self.after(0, self._render_remote_files, files)
            except Exception as e:
                self.after(0, self.status_var.set, f"Error: {e}")
                self.after(0, messagebox.showerror, "ADB Error", str(e))
                
        threading.Thread(target=fetch, daemon=True).start()

    def _render_remote_files(self, files):
        for f in files:
            tag = 'dir' if f['is_dir'] else 'file'
            iid = self.remote_tree.insert("", "end", values=(f['name'], f['size'], f['date']))
            self.remote_tree.item(iid, tags=(f['name'], tag))
        self.status_var.set("Ready")

    def on_double_click(self, is_local):
        tree = self.local_tree if is_local else self.remote_tree
        selected = tree.selection()
        if not selected: return
        item = selected[0]
        tags = tree.item(item, "tags")
        if tags[1] == 'dir':
            if is_local: self.load_local_directory(self.local_path + tags[0] + '/')
            else: self.load_remote_directory(self.remote_path + tags[0] + '/')

    # --- F-Keys & Drag Drop ---
    
    def on_f5_press(self, event=None):
        if self.active_pane == "local":
            selected = self.local_tree.selection()
            if not selected: return
            filenames = [self.local_tree.item(i, "tags")[0] for i in selected]
            self.transfer_push(filenames)
        elif self.active_pane == "remote":
            selected = self.remote_tree.selection()
            if not selected: return
            filenames = [self.remote_tree.item(i, "tags")[0] for i in selected]
            self.transfer_pull(filenames)

    def on_drag_start(self, event, is_local):
        tree = self.local_tree if is_local else self.remote_tree
        item_under_cursor = tree.identify_row(event.y)
        if item_under_cursor not in tree.selection():
            self.drag_data["items"] = []
            return
            
        selected = tree.selection()
        if not selected: return
            
        self.drag_data["source"] = "local" if is_local else "remote"
        self.drag_data["items"] = []
        
        for item in selected:
            self.drag_data["items"].append(tree.item(item, "tags")[0])
            
        if self.drag_data["items"]:
            if self.drag_window: self.drag_window.destroy()
            self.drag_window = tk.Toplevel(self)
            self.drag_window.overrideredirect(True)
            self.drag_window.attributes("-alpha", 0.85)
            self.drag_window.attributes("-topmost", True)
            
            count = len(self.drag_data["items"])
            text = f" {self.drag_data['items'][0]} " if count == 1 else f" {count} items "
            
            lbl = ctk.CTkLabel(self.drag_window, text=text, fg_color="#264f78", 
                               text_color="white", corner_radius=2, height=24, font=("Menlo", 12))
            lbl.pack(padx=1, pady=1)
            self.drag_window.geometry(f"+{event.x_root + 15}+{event.y_root + 15}")

    def on_drag_motion(self, event):
        if not self.drag_data["items"]: return
        if self.drag_window:
            self.drag_window.geometry(f"+{event.x_root + 15}+{event.y_root + 15}")

    def on_drag_release(self, event, is_local):
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None
            
        self.config(cursor="")
        if not self.drag_data["items"]: return
            
        source = self.drag_data["source"]
        target_widget = self.winfo_containing(event.x_root, event.y_root)
        if not target_widget: return
            
        dropped_on_local = (target_widget == self.local_tree)
        dropped_on_remote = (target_widget == self.remote_tree)
        
        if source == "local" and dropped_on_remote:
            self.transfer_push(self.drag_data["items"])
        elif source == "remote" and dropped_on_local:
            self.transfer_pull(self.drag_data["items"])
            
        self.drag_data["items"] = []

    # --- File Transfers ---
    
    def transfer_push(self, filenames):
        local_paths = [self.local_path + name for name in filenames]
        remote_dest = self.remote_path
        self.status_var.set(f"Pushing {len(filenames)} items to Android...")
        
        def do_push():
            try:
                self.adb.push(local_paths, remote_dest)
                self.after(0, self.status_var.set, f"Successfully pushed {len(filenames)} items")
                self.after(0, self.load_remote_directory, self.remote_path)
            except Exception as e:
                self.after(0, self.status_var.set, f"Push failed: {e}")
                self.after(0, messagebox.showerror, "Error", str(e))
                
        threading.Thread(target=do_push, daemon=True).start()

    def transfer_pull(self, filenames):
        remote_paths = [self.remote_path + name for name in filenames]
        local_dest = self.local_path
        self.status_var.set(f"Pulling {len(filenames)} items to Mac...")
        
        def do_pull():
            try:
                self.adb.pull(remote_paths, local_dest)
                self.after(0, self.status_var.set, f"Successfully pulled {len(filenames)} items")
                self.after(0, self.load_local_directory, self.local_path)
            except Exception as e:
                self.after(0, self.status_var.set, f"Pull failed: {e}")
                self.after(0, messagebox.showerror, "Error", str(e))
                
        threading.Thread(target=do_pull, daemon=True).start()

if __name__ == "__main__":
    app = MacDroidApp()
    app.mainloop()

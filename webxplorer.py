# VERSION 1.1a
# --- CONFIGURATION INITIALE (NE PAS SUPPRIMER) ---
# PREFERENCES_JSON = {
#     "start_url": "https://www.mesdarons.fr",
#     "max_pages": 250,
#     "url_filter": "",
#     "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
#     "blacklist_file": "",
#     "output_file": "audit.json"
# }
# --- FIN CONFIGURATION ---

import urllib.request
import urllib.parse
import urllib.error
import time
import json
import ssl
import sys
import re 
import os
import csv
import math
import httpx 
from bs4 import BeautifulSoup 
import random 
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- Chargement Dynamique des Préférences depuis le code source ---
def load_self_preferences():
    default_prefs = {
        "start_url": "https://",
        "max_pages": 100,
        "url_filter": "",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "blacklist_file": "",
        "output_file": "audit.json"
    }
    try:
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        match = re.search(r'# PREFERENCES_JSON = (\{.*?\}\s*?)^# --- FIN CONFIGURATION ---', content, re.DOTALL | re.MULTILINE)
        if match:
            json_str = match.group(1)
            clean_json = "\n".join([line.lstrip('#').strip() for line in json_str.splitlines()])
            return json.loads(clean_json)
    except Exception:
        pass
    return default_prefs

def save_self_preferences(new_prefs):
    try:
        script_path = os.path.abspath(__file__)
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        formatted_json = json.dumps(new_prefs, indent=4, ensure_ascii=False)
        commented_lines = "\n".join([f"# {line}" for line in formatted_json.splitlines()])
        new_block = f"# PREFERENCES_JSON = {commented_lines[2:]}\n"
        
        pattern = r'# PREFERENCES_JSON = \{.*?\}\s*?^# --- FIN CONFIGURATION ---'
        updated_content = re.sub(pattern, f"{new_block}# --- FIN CONFIGURATION ---", content, flags=re.DOTALL | re.MULTILINE)
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        return True
    except Exception as e:
        print(f"Auto-save error: {e}")
        return False


# --- Classes de Crawling ---

class WebCrawler:
    def __init__(self, start_url, max_pages, url_filter="", user_agent="", blacklist_fragments=None, progress_callback=None, control_flags=None):
        self.start_url = start_url.rstrip('/')
        self.base_domain = urllib.parse.urlparse(self.start_url).netloc
        self.max_pages = max_pages
        self.url_filter = url_filter.strip()
        self.user_agent = user_agent
        self.visited = set()
        self.to_visit = [(self.start_url, 0)] 
        self.crawled_pages = []
        self.internal_link_audit = {} 
        self.page_count = 0
        self.blacklist_fragments = blacklist_fragments if blacklist_fragments else []
        self.progress_callback = progress_callback
        self.control_flags = control_flags if control_flags else {"pause": False, "stop": False}
        
        self.client = httpx.Client(http2=False, verify=False, timeout=30.0)
        
        if hasattr(ssl, '_create_unverified_context'):
            ssl._create_default_https_context = ssl._create_unverified_context

    def is_internal(self, url):
        try:
            domain = urllib.parse.urlparse(url).netloc
            return domain == self.base_domain
        except Exception:
            return False

    def is_blacklisted(self, url):
        return any(fragment in url for fragment in self.blacklist_fragments)

    def matches_url_filter(self, url):
        if not self.url_filter:
            return True
        return self.url_filter in url

    def crawl_page(self, url, depth):
        while self.control_flags.get("pause", False):
            if self.control_flags.get("stop", False):
                return
            time.sleep(0.5)

        if self.control_flags.get("stop", False):
            return

        if url in self.visited or self.page_count >= self.max_pages or self.is_blacklisted(url):
            return

        if url != self.start_url and not self.matches_url_filter(url):
            return

        self.visited.add(url)
        print(f"[{self.page_count + 1}/{self.max_pages}] Crawling (Depth {depth}): {url}")
        
        selected_ua = self.user_agent if self.user_agent else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
        page_data = {
            "url": url,
            "title": "",
            "meta_description": "",
            "h1": [],
            "h2": [],
            "h3": [],
            "http_status": 0,
            "links_count": 0,
            "inbound_links_count": 0,
            "crawl_depth": depth,
            "body_text": "",
            "user_agent_used": selected_ua
        }

        try:
            headers = {'User-Agent': selected_ua} 
            response = self.client.get(url, headers=headers)
            
            status = response.status_code
            page_data['http_status'] = status
            self.internal_link_audit[url] = status

            if status >= 400:
                 raise Exception(f"HTTP Error {status}")

            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            if soup.title and soup.title.string:
                page_data['title'] = soup.title.string.strip()
            
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                page_data['meta_description'] = meta_desc['content'].strip()
                
            for tag_name in ['h1', 'h2', 'h3']:
                for header in soup.find_all(tag_name):
                    text = header.get_text().strip()
                    if text:
                        page_data[tag_name].append(text)
            
            links = set()
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                full_url = urllib.parse.urljoin(url, href)
                clean_url = full_url.split('#')[0] 
                if clean_url:
                    links.add(clean_url)
            
            page_data['links_count'] = len(links)
            
            body = soup.find('body')
            if body:
                temp_body = BeautifulSoup(str(body), 'html.parser') 
                text_ignore_tags = ['script', 'style', 'header', 'footer', 'nav', 'aside', 'form', 'button', 'input', 'select', 'textarea', 'a']
                for script_or_style in temp_body(text_ignore_tags):
                    script_or_style.decompose()
                text = temp_body.get_text()
                page_data['body_text'] = re.sub(r'\s+', ' ', text).strip() 
            
            for link in links:
                if self.is_internal(link) and link not in self.visited and not self.is_blacklisted(link):
                    if not self.url_filter or self.matches_url_filter(link):
                        self.to_visit.append((link, depth + 1))
                    
            self.crawled_pages.append(page_data)
            self.page_count += 1
            
            if self.progress_callback:
                self.progress_callback(self.page_count, self.max_pages)

        except Exception as e:
            self.internal_link_audit[url] = page_data['http_status']
            self.crawled_pages.append(page_data)
            print(f"Error on {url}: {e}")

    def run(self):
        try:
            while self.to_visit and self.page_count < self.max_pages:
                if self.control_flags.get("stop", False):
                    print("\n🛑 Audit aborted by user.")
                    break
                while self.control_flags.get("pause", False):
                    if self.control_flags.get("stop", False):
                        break
                    time.sleep(0.5)

                current_url, current_depth = self.to_visit.pop(0)
                self.crawl_page(current_url, current_depth)
                time.sleep(0.1)
                
            url_map = {page['url']: page for page in self.crawled_pages}
            
            if not self.control_flags.get("stop", False):
                for page_data in self.crawled_pages:
                    url_crawled = page_data['url']
                    if page_data['http_status'] >= 400 or page_data['http_status'] == 0:
                         continue
                         
                    try:
                        headers = {'User-Agent': page_data['user_agent_used']} 
                        response = self.client.get(url_crawled, headers=headers)
                        
                        if response.status_code < 400:
                            soup = BeautifulSoup(response.text, 'html.parser')
                            for a_tag in soup.find_all('a', href=True):
                                 href = a_tag['href']
                                 full_url = urllib.parse.urljoin(url_crawled, href)
                                 clean_url = full_url.split('#')[0] 
                                 if clean_url in url_map:
                                      url_map[clean_url]['inbound_links_count'] += 1
                    except Exception:
                         pass
        finally:
            self.client.close()
        
        final_result = {
            "crawled_pages_count": self.page_count,
            "start_url": self.start_url,
            "url_filter": self.url_filter,
            "user_agent": self.user_agent,
            "crawled_pages": self.crawled_pages,
            "internal_link_audit": self.internal_link_audit
        }
        return final_result


# --- Redirection des prints vers la GUI ---

class TextRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, str_val):
        self.text_widget.insert(tk.END, str_val)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


# --- Interface Graphique (GUI) & Splash Screen ---

class SplashScreen:
    def __init__(self, root):
        self.root = root
        self.root.overrideredirect(True)
        self.root.geometry("450x250")
        
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
        frame = tk.Frame(self.root, bg="#1e1e2f")
        frame.pack(fill=tk.BOTH, expand=True)
        
        lbl_title = tk.Label(frame, text="CRAWL XPLORER", font=("Helvetica", 22, "bold"), fg="#ffffff", bg="#1e1e2f")
        lbl_title.pack(pady=(70, 5))
        
        lbl_version = tk.Label(frame, text="version 1.1a", font=("Helvetica", 11, "italic"), fg="#aaaaaa", bg="#1e1e2f")
        lbl_version.pack()
        
        self.root.after(4000, self.launch_main_app)

    def launch_main_app(self):
        self.root.destroy()
        main_app_window = tk.Tk()
        CrawlerGUI(main_app_window)
        main_app_window.mainloop()


class CrawlerGUI:
    USER_AGENTS_LIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)",
        "Mozilla/5.0 (compatible; Yahoo! Slurp; http://help.yahoo.com/help/us/ysearch/slurp)",
        "Mozilla/5.0 (compatible; DuckDuckBot/1.0; (+http://duckduckgo.com/duckduckbot.html))",
        "Mozilla/5.0 (compatible; Applebot/1.6; +http://www.apple.com/go/applebot)",
        "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("HIGHUP - Web Crawler Audit")
        self.root.geometry("1280x680")
        
        self.prefs = load_self_preferences()
        self.control_flags = {"pause": False, "stop": False}
        self.current_audit_data = None
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        self.tab_audit = ttk.Frame(self.notebook, padding="7")
        self.tab_viewer = ttk.Frame(self.notebook, padding="7")
        self.tab_charts = ttk.Frame(self.notebook, padding="7")
        self.tab_json_raw = ttk.Frame(self.notebook, padding="7")
        
        self.notebook.add(self.tab_audit, text=" ⚙️ Run Audit ")
        self.notebook.add(self.tab_viewer, text=" 📊 Table Viewer ")
        self.notebook.add(self.tab_charts, text=" 📈 Charts & Stats ")
        self.notebook.add(self.tab_json_raw, text=" 📄 Raw JSON Viewer ")
        
        self.create_audit_widgets()
        self.create_viewer_widgets()
        self.create_charts_widgets()
        self.create_json_raw_widgets()
        
        sys.stdout = TextRedirector(self.log_text)

    def create_audit_widgets(self):
        config_frame = ttk.LabelFrame(self.tab_audit, text=" Configuration ", padding="7")
        config_frame.pack(fill=tk.X, pady=(0, 7))
        
        ttk.Label(config_frame, text="URL:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.url_entry = ttk.Entry(config_frame, width=40)
        self.url_entry.insert(0, self.prefs.get("start_url", "https://"))
        self.url_entry.grid(row=0, column=1, sticky=tk.EW, pady=4, padx=5)
        
        ttk.Label(config_frame, text="Max pages:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.max_pages_spin = ttk.Spinbox(config_frame, from_=1, to=10000, width=8)
        self.max_pages_spin.set(self.prefs.get("max_pages", 100))
        self.max_pages_spin.grid(row=1, column=1, sticky=tk.W, pady=4, padx=5)
        
        ttk.Label(config_frame, text="URL Filter (optional):").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.filter_entry = ttk.Entry(config_frame, width=40)
        self.filter_entry.insert(0, self.prefs.get("url_filter", ""))
        self.filter_entry.grid(row=2, column=1, sticky=tk.EW, pady=4, padx=5)

        ttk.Label(config_frame, text="User-Agent:").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ua_combobox = ttk.Combobox(config_frame, values=self.USER_AGENTS_LIST, width=60)
        saved_ua = self.prefs.get("user_agent", self.USER_AGENTS_LIST[0])
        self.ua_combobox.set(saved_ua)
        self.ua_combobox.grid(row=3, column=1, sticky=tk.EW, pady=4, padx=5)
        
        ttk.Label(config_frame, text="Output file:").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.output_entry = ttk.Entry(config_frame, width=30)
        self.output_entry.insert(0, self.prefs.get("output_file", "audit.json"))
        self.output_entry.grid(row=4, column=1, sticky=tk.EW, pady=4, padx=5)
        
        config_frame.columnconfigure(1, weight=1)
        
        action_frame = ttk.Frame(self.tab_audit)
        action_frame.pack(fill=tk.X, pady=4)
        
        self.btn_start = ttk.Button(action_frame, text="Run Audit", command=self.start_crawl_thread)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 7))

        self.btn_pause = ttk.Button(action_frame, text="⏸️ Pause", command=self.toggle_pause, state=tk.DISABLED)
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 7))

        self.btn_stop = ttk.Button(action_frame, text="⏹️ Stop", command=self.stop_crawl, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 7))
        
        self.progress_bar = ttk.Progressbar(action_frame, orient='horizontal', mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(7, 0))
        
        log_frame = ttk.LabelFrame(self.tab_audit, text=" Console ", padding="4")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(7, 0))
        
        self.log_text = tk.Text(log_frame, height=9, font=('Consolas', 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def create_viewer_widgets(self):
        top_panel = ttk.Frame(self.tab_viewer)
        top_panel.pack(fill=tk.X, pady=(0, 7))
        
        btn_load_json = ttk.Button(top_panel, text="📁 Load Audit File (JSON)", command=self.load_and_display_json)
        btn_load_json.pack(side=tk.LEFT, padx=(0, 7))

        btn_export_csv = ttk.Button(top_panel, text="📥 Export CSV", command=self.export_to_csv)
        btn_export_csv.pack(side=tk.LEFT, padx=(0, 7))
        
        self.lbl_loaded_info = ttk.Label(top_panel, text="No file loaded.", font=('Helvetica', 10, 'italic'))
        self.lbl_loaded_info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        table_frame = ttk.Frame(self.tab_viewer)
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("url", "status", "title", "meta_desc", "h1", "h2", "h3", "depth", "links_count", "inbound", "ua", "body_text")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        self.tree.heading("url", text="Analyzed URL")
        self.tree.heading("status", text="HTTP")
        self.tree.heading("title", text="Title")
        self.tree.heading("meta_desc", text="Meta Description")
        self.tree.heading("h1", text="H1")
        self.tree.heading("h2", text="H2")
        self.tree.heading("h3", text="H3")
        self.tree.heading("depth", text="Depth")
        self.tree.heading("links_count", text="Outbound")
        self.tree.heading("inbound", text="Inbound")
        self.tree.heading("ua", text="User-Agent")
        self.tree.heading("body_text", text="Raw Text (Snippet)")
        
        self.tree.column("url", width=220, anchor=tk.W)
        self.tree.column("status", width=55, anchor=tk.CENTER)
        self.tree.column("title", width=180, anchor=tk.W)
        self.tree.column("meta_desc", width=180, anchor=tk.W)
        self.tree.column("h1", width=130, anchor=tk.W)
        self.tree.column("h2", width=130, anchor=tk.W)
        self.tree.column("h3", width=130, anchor=tk.W)
        self.tree.column("depth", width=65, anchor=tk.CENTER)
        self.tree.column("links_count", width=70, anchor=tk.CENTER)
        self.tree.column("inbound", width=70, anchor=tk.CENTER)
        self.tree.column("ua", width=150, anchor=tk.W)
        self.tree.column("body_text", width=250, anchor=tk.W)
        
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

    def create_charts_widgets(self):
        charts_top_panel = ttk.Frame(self.tab_charts)
        charts_top_panel.pack(fill=tk.X, pady=(0, 7))
        
        self.lbl_charts_info = ttk.Label(charts_top_panel, text="No data to display. Run an audit or load a JSON file.", font=('Helvetica', 10, 'italic'))
        self.lbl_charts_info.pack(side=tk.LEFT, fill=tk.X, expand=True)

        container_frame = ttk.Frame(self.tab_charts)
        container_frame.pack(fill=tk.BOTH, expand=True)

        # Cadre Camembert (Status HTTP)
        frame_pie = ttk.LabelFrame(container_frame, text=" Server Response Types (HTTP Status) ", padding="7")
        frame_pie.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.canvas_pie = tk.Canvas(frame_pie, bg="#ffffff", highlightthickness=0)
        self.canvas_pie.pack(fill=tk.BOTH, expand=True)

        # Cadre Barres (Profondeur des pages)
        frame_bar = ttk.LabelFrame(container_frame, text=" Page Depth (Number of pages per level) ", padding="7")
        frame_bar.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.canvas_bar = tk.Canvas(frame_bar, bg="#ffffff", highlightthickness=0)
        self.canvas_bar.pack(fill=tk.BOTH, expand=True)

        self.canvas_pie.bind("<Configure>", lambda e: self.draw_charts())
        self.canvas_bar.bind("<Configure>", lambda e: self.draw_charts())

    def create_json_raw_widgets(self):
        top_panel = ttk.Frame(self.tab_json_raw)
        top_panel.pack(fill=tk.X, pady=(0, 7))
        
        btn_load_raw = ttk.Button(top_panel, text="📁 Open and format a JSON", command=self.load_raw_json_file)
        btn_load_raw.pack(side=tk.LEFT, padx=(0, 7))
        
        self.lbl_json_info = ttk.Label(top_panel, text="No raw file displayed.", font=('Helvetica', 10, 'italic'))
        self.lbl_json_info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        text_frame = ttk.Frame(self.tab_json_raw)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.json_text_widget = tk.Text(text_frame, wrap=tk.NONE, font=('Consolas', 10), background="#f8f9fa", foreground="#212529")
        self.json_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        vsb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.json_text_widget.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        hsb = ttk.Scrollbar(self.tab_json_raw, orient=tk.HORIZONTAL, command=self.json_text_widget.xview)
        hsb.pack(fill=tk.X)
        
        self.json_text_widget.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    def update_progress(self, current, max_val):
        if max_val > 0:
            percentage = (current / max_val) * 100
            self.progress_bar['value'] = percentage
            self.root.update_idletasks()

    def start_crawl_thread(self):
        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL, text="⏸️ Pause")
        self.btn_stop.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        self.log_text.delete('1.0', tk.END)
        
        self.control_flags["pause"] = False
        self.control_flags["stop"] = False
        
        threading.Thread(target=self.run_crawl, daemon=True).start()

    def toggle_pause(self):
        if not self.control_flags["pause"]:
            self.control_flags["pause"] = True
            self.btn_pause.config(text="▶️ Resume")
            print("\n⏸️ Audit paused.")
        else:
            self.control_flags["pause"] = False
            self.btn_pause.config(text="⏸️ Pause")
            print("\n▶️ Resuming audit...")

    def stop_crawl(self):
        self.control_flags["stop"] = True
        self.control_flags["pause"] = False
        print("\n⏹️ Stop request sent...")

    def run_crawl(self):
        start_url = self.url_entry.get()
        try:
            max_pages = int(self.max_pages_spin.get())
        except ValueError:
            max_pages = 100
        url_filter = self.filter_entry.get()
        user_agent = self.ua_combobox.get()
        output_file = self.output_entry.get()

        new_prefs = {
            "start_url": start_url,
            "max_pages": max_pages,
            "url_filter": url_filter,
            "user_agent": user_agent,
            "blacklist_file": self.prefs.get("blacklist_file", ""),
            "output_file": output_file
        }
        save_self_preferences(new_prefs)
        
        try:
            crawler = WebCrawler(
                start_url, max_pages, 
                url_filter=url_filter, 
                user_agent=user_agent, 
                progress_callback=self.update_progress,
                control_flags=self.control_flags
            )
            self.current_audit_data = crawler.run()
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_audit_data, f, indent=4, ensure_ascii=False)
            
            print(f"\n✅ Audit completed and saved to {output_file}.")
            messagebox.showinfo("Success", f"Audit is complete!\nThe file has been saved to:\n{output_file}")
            
            self.display_data_in_tree(self.current_audit_data, output_file)
            self.draw_charts()
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            messagebox.showerror("Error", f"An error occurred:\n{e}")
        finally:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_pause.config(state=tk.DISABLED, text="⏸️ Pause")
            self.btn_stop.config(state=tk.DISABLED)

    def load_and_display_json(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.current_audit_data = json.load(f)
            self.display_data_in_tree(self.current_audit_data, filename)
            self.draw_charts()
        except Exception as e:
            messagebox.showerror("Read Error", f"Unable to read file:\n{e}")

    def export_to_csv(self):
        if not self.current_audit_data or not self.current_audit_data.get("crawled_pages"):
            messagebox.showwarning("Warning", "No data to export. Please run an audit or load a JSON file first.")
            return

        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv"), ("All files", "*.*")])
        if not filename:
            return

        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ["url", "http_status", "title", "meta_description", "h1", "h2", "h3", "crawl_depth", "links_count", "inbound_links_count", "user_agent_used", "body_text"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
                
                writer.writeheader()
                for page in self.current_audit_data.get("crawled_pages", []):
                    row = page.copy()
                    row["h1"] = " | ".join(row.get("h1", []))
                    row["h2"] = " | ".join(row.get("h2", []))
                    row["h3"] = " | ".join(row.get("h3", []))
                    writer.writerow(row)

            messagebox.showinfo("Success", f"CSV export successful!\nSaved to:\n{filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Unable to export CSV file:\n{e}")

    def display_data_in_tree(self, data, filename):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        crawled_pages = data.get("crawled_pages", [])
        for page in crawled_pages:
            h1_str = " | ".join(page.get("h1", []))
            h2_str = " | ".join(page.get("h2", []))
            h3_str = " | ".join(page.get("h3", []))
            
            self.tree.insert("", tk.END, values=(
                page.get("url", ""),
                page.get("http_status", 0),
                page.get("title", ""),
                page.get("meta_description", ""),
                h1_str,
                h2_str,
                h3_str,
                page.get("crawl_depth", 0),
                page.get("links_count", 0),
                page.get("inbound_links_count", 0),
                page.get("user_agent_used", ""),
                page.get("body_text", "")
            ))
        
        self.lbl_loaded_info.config(
            text=f"File: {filename.split('/')[-1]} | {len(crawled_pages)} pages displayed.",
            foreground="#28a745"
        )

    def draw_charts(self):
        self.canvas_pie.delete("all")
        self.canvas_bar.delete("all")

        if not self.current_audit_data or not self.current_audit_data.get("crawled_pages"):
            self.lbl_charts_info.config(text="No data available for charts.", foreground="#dc3545")
            return

        pages = self.current_audit_data.get("crawled_pages", [])
        self.lbl_charts_info.config(text=f"Charts generated from {len(pages)} analyzed pages.", foreground="#28a745")

        # --- 1. HTTP Status Pie Chart ---
        status_counts = {}
        for p in pages:
            st = str(p.get("http_status", 0))
            status_counts[st] = status_counts.get(st, 0) + 1

        total_pages = len(pages)
        palette = ["#28a745", "#007bff", "#ffc107", "#dc3545", "#17a2b8", "#6c757d", "#6610f2", "#fd7e14"]

        w_pie = self.canvas_pie.winfo_width()
        h_pie = self.canvas_pie.winfo_height()
        if w_pie > 10 and h_pie > 10:
            cx, cy = w_pie // 2 - 60, h_pie // 2
            radius = min(cx, cy) - 30
            if radius > 20:
                start_angle = 0
                idx = 0
                legend_y = 30

                for st, count in status_counts.items():
                    extent = (count / total_pages) * 360
                    color = palette[idx % len(palette)]
                    idx += 1

                    self.canvas_pie.create_arc(
                        cx - radius, cy - radius, cx + radius, cy + radius,
                        start=start_angle, extent=extent, fill=color, outline="white", width=2
                    )
                    start_angle += extent

                    leg_x = cx + radius + 35
                    if leg_x + 100 < w_pie:
                        self.canvas_pie.create_rectangle(leg_x, legend_y - 8, leg_x + 12, legend_y + 4, fill=color, outline="")
                        pct = (count / total_pages) * 100
                        self.canvas_pie.create_text(leg_x + 20, legend_y - 2, anchor=tk.W, text=f"HTTP {st}: {count} ({pct:.1f}%)", font=('Helvetica', 9, 'bold'), fill="#333333")
                        legend_y += 22

        # --- 2. Page Depth Bar Chart ---
        depth_counts = {}
        for p in pages:
            d = p.get("crawl_depth", 0)
            depth_counts[d] = depth_counts.get(d, 0) + 1

        sorted_depths = sorted(depth_counts.keys())
        max_count = max(depth_counts.values()) if depth_counts else 1

        w_bar = self.canvas_bar.winfo_width()
        h_bar = self.canvas_bar.winfo_height()
        if w_bar > 50 and h_bar > 50 and sorted_depths:
            margin_x = 50
            margin_y = 40
            chart_w = w_bar - (2 * margin_x)
            chart_h = h_bar - (2 * margin_y)

            base_y = h_bar - margin_y
            self.canvas_bar.create_line(margin_x, base_y, w_bar - margin_x, base_y, fill="#cccccc", width=2)

            num_bars = len(sorted_depths)
            slot_w = chart_w / max(num_bars, 1)
            bar_w = min(slot_w * 0.6, 50)

            for i, d in enumerate(sorted_depths):
                cnt = depth_counts[d]
                bar_h = (cnt / max_count) * (chart_h - 20) if max_count > 0 else 0

                x1 = margin_x + (i * slot_w) + (slot_w - bar_w) / 2
                y1 = base_y - bar_h
                x2 = x1 + bar_w
                y2 = base_y

                self.canvas_bar.create_rectangle(x1, y1, x2, y2, fill="#007bff", outline="#0056b3", width=1)
                self.canvas_bar.create_text((x1 + x2) / 2, y1 - 12, text=str(cnt), font=('Helvetica', 9, 'bold'), fill="#333333")
                self.canvas_bar.create_text((x1 + x2) / 2, base_y + 15, text=f"Depth {d}", font=('Helvetica', 9), fill="#555555")

    def load_raw_json_file(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All files", "*.*")])
        if not filename:
            return
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            pretty_json_str = json.dumps(data, indent=4, ensure_ascii=False)
            self.json_text_widget.delete("1.0", tk.END)
            self.json_text_widget.insert(tk.END, pretty_json_str)
            self.lbl_json_info.config(
                text=f"Displayed file: {filename.split('/')[-1]} (Formatted and readable)",
                foreground="#28a745"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load raw JSON file:\n{e}")

def main():
    splash_root = tk.Tk()
    SplashScreen(splash_root)
    splash_root.mainloop()

if __name__ == "__main__":
    main()

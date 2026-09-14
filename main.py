import tkinter as tk
from tkinter import ttk
import ctypes

# ProbLog imports for exact inference
from problog.program import PrologString
from problog import get_evaluatable

# --- HIGH-DPI FIX FOR WINDOWS ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# =========================================================================
# PART 1: THE CAUSAL LOGIC (Moderated Buffer + Noisy-OR Base Risk)
# =========================================================================
class CausalRiskEngine:
    def calculate(self, choices):
        problog_model = """
        % --- 1. CONFOUNDER PRIORS ---
        0.4 :: weather_Clear ; 0.3 :: weather_Rain ; 0.2 :: weather_Snow ; 0.1 :: weather_Storm.
        
        % --- 2. INDEPENDENT CAUSAL RULES ---
        0.01 :: base_miss.
        miss_flight :- base_miss.
        
        0.03 :: luggage_risk.
        miss_flight :- luggage_Checked, luggage_risk.
        
        0.05 :: security_risk.
        miss_flight :- security_Long, security_risk.
        
        0.04 :: connecting_risk.
        miss_flight :- flight_Connecting, connecting_risk.
        
        % --- 3. THE CAUSAL CHAIN: Weather + Transport -> Traffic Delay ---
        0.03 :: delay_taxi_clear.
        0.10 :: delay_taxi_rain.
        0.25 :: delay_taxi_snow.
        0.40 :: delay_taxi_storm.
        
        traffic_delay :- transport_Taxi, weather_Clear, delay_taxi_clear.
        traffic_delay :- transport_Taxi, weather_Rain, delay_taxi_rain.
        traffic_delay :- transport_Taxi, weather_Snow, delay_taxi_snow.
        traffic_delay :- transport_Taxi, weather_Storm, delay_taxi_storm.
        
        0.06 :: delay_bus_clear.
        0.18 :: delay_bus_rain.
        0.35 :: delay_bus_snow.
        0.50 :: delay_bus_storm.
        
        traffic_delay :- transport_Bus, weather_Clear, delay_bus_clear.
        traffic_delay :- transport_Bus, weather_Rain, delay_bus_rain.
        traffic_delay :- transport_Bus, weather_Snow, delay_bus_snow.
        traffic_delay :- transport_Bus, weather_Storm, delay_bus_storm.
        
        % --- 4. BUFFER MODERATOR ---
        % BASE RISK: Risk of being late purely due to airport logistics (no traffic delay)
        0.22 :: late_short_base.
        0.03 :: late_normal_base.
        
        late :- buffer_Short, late_short_base.
        late :- buffer_Normal, late_normal_base.
        % Long buffer (> 120 min) has virtually 0 base risk of being late without traffic.
        
        % DELAY RISK: Additional risk added IF there is a traffic delay
        0.45 :: late_short_delay.
        0.10 :: late_normal_delay.
        0.03 :: late_long_delay.
        
        late :- traffic_delay, buffer_Short, late_short_delay.
        late :- traffic_delay, buffer_Normal, late_normal_delay.
        late :- traffic_delay, buffer_Long, late_long_delay.
        
        % --- 5. LATE -> MISS FLIGHT ---
        0.55 :: miss_from_late.
        miss_flight :- late, miss_from_late.
        
        query(miss_flight).
        """
        
        problog_model += "\nflight_Connecting." if choices["Flight"] == "Connecting" else "\nflight_Connecting :- fail."
        problog_model += "\nluggage_Checked." if choices["Luggage"] == "Checked" else "\nluggage_Checked :- fail."
        problog_model += "\nsecurity_Long." if choices["Security"] == "Long" else "\nsecurity_Long :- fail."
        
        problog_model += "\nbuffer_Short." if choices["Buffer"] == "< 60 Min" else "\nbuffer_Short :- fail."
        problog_model += "\nbuffer_Normal." if choices["Buffer"] == "60-120 Min" else "\nbuffer_Normal :- fail."
        problog_model += "\nbuffer_Long." if choices["Buffer"] == "> 120 Min" else "\nbuffer_Long :- fail."
        
        weather = choices["Weather"]
        problog_model += f"\nevidence(weather_{weather})."
        
        f_val, b_val, s_val, l_val = choices['Flight'], choices['Buffer'], choices['Security'], choices['Luggage']
        base_vars = f"F={f_val}, L={l_val}, B={b_val}, S={s_val}"
        
        if choices["Transport"] == "Hotel":
            problog_model += "\ntransport_Taxi :- fail.\ntransport_Bus :- fail.\ntransport_Hotel."
            is_do_calculus = True
            formula = f"P( Risk | Weather, do(Trans=Hotel), {base_vars} )"
            desc = "Causal Intervention: The path Weather -> Delay is physically removed from the ProbLog structure."
        else:
            trans = choices["Transport"]
            if trans == "Taxi":
                problog_model += "\ntransport_Taxi.\ntransport_Bus :- fail.\ntransport_Hotel :- fail."
            elif trans == "Bus":
                problog_model += "\ntransport_Bus.\ntransport_Taxi :- fail.\ntransport_Hotel :- fail."
                
            is_do_calculus = False
            formula = f"P( Risk | W={weather}, Trans={trans}, {base_vars} )"
            desc = "Pure Observation: ProbLog computes exact conditional probability through the traffic_delay node."

        try:
            p = PrologString(problog_model)
            result = get_evaluatable().create_from(p).evaluate()
            
            risk_val = list(result.values())[0] if result else 0.01
            final_risk = round(risk_val * 100, 1)
            final_risk = max(1.0, min(99.9, final_risk))
            return final_risk, formula, desc, is_do_calculus
        except Exception as e:
            print(f"ProbLog Error: {e}")
            return "ERR", "System Error", f"ProbLog inference failed: {str(e)}", False

# =========================================================================
# PART 2: THE USER INTERFACE 
# =========================================================================
class CausalFlightApp:
    def __init__(self, root):
        self.root = root
        self.root.title("✈️ Causal AI: Will you miss your flight?")
        self.root.geometry("1280x850")
        self.root.configure(bg="#0D1117")

        self.engine = CausalRiskEngine()

        self.target_risk = 1.0
        self.current_risk = 1.0
        self.current_step = 0
        self.current_formula = ""
        self.is_do_calculus = False
        self._resize_timer = None

        self.choices = {
            "Flight": "Direct", "Luggage": "Carry-on", "Weather": "Clear",
            "Transport": "Taxi", "Buffer": "60-120 Min", "Security": "Short"
        }
        self.option_cards = []

        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.style.configure('TButton', font=("Segoe UI", 11, "bold"), padding=10, background="#21262D", foreground="#C9D1D9", borderwidth=0)
        self.style.map('TButton', background=[('active', '#30363D')])

        self.top_frame = tk.Frame(root, bg="#0D1117", pady=10, bd=0)
        self.top_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=(20, 10))
        tk.Label(self.top_frame, text="Will you miss the flight?", font=("Segoe UI", 24, "bold"), bg="#0D1117", fg="#E6EDF3").pack(anchor="w")

        self.risk_label = tk.Label(self.top_frame, text="Risk: 1.0 %", font=("Segoe UI", 48, "bold"), bg="#0D1117", fg="#3FB950")
        self.risk_label.place(relx=1.0, rely=0.5, anchor="e")

        self.main_frame = tk.Frame(root, bg="#0D1117")
        self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        self.left_frame = tk.Frame(self.main_frame, bg="#161B22", bd=1, highlightbackground="#30363D", highlightthickness=1)
        self.left_frame.place(relx=0, rely=0, relwidth=0.42, relheight=1)

        self.right_frame = tk.Frame(self.main_frame, bg="#161B22", bd=1, highlightbackground="#30363D", highlightthickness=1)
        self.right_frame.place(relx=0.45, rely=0, relwidth=0.55, relheight=1)

        tk.Label(self.right_frame, text="Causal graph", font=("Segoe UI", 12, "bold"), bg="#161B22", fg="#E6EDF3", pady=10).pack(anchor="w", padx=20)
        self.canvas = tk.Canvas(self.right_frame, bg="#161B22", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=0)
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        self.math_frame = tk.Frame(root, bg="#161B22", pady=15, padx=20, highlightbackground="#30363D", highlightthickness=1)
        self.math_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 20))

        tk.Label(self.math_frame, text="Posterior", font=("Segoe UI", 10, "bold"), bg="#1F2E4D", fg="#58A6FF", padx=8, pady=2).pack(anchor="w", pady=(0,10))
        self.math_formula_label = tk.Label(self.math_frame, text="", font=("Consolas", 12, "bold"), bg="#161B22", fg="#3FB950")
        self.math_formula_label.pack(anchor="w")
        self.math_desc_label = tk.Label(self.math_frame, text="", font=("Segoe UI", 10), bg="#161B22", fg="#8B949E")
        self.math_desc_label.pack(anchor="w", pady=(5,0))

        self.slides = []
        self.build_slides()

        self.nav_frame = tk.Frame(self.left_frame, bg="#161B22")
        self.nav_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20, padx=20)
        self.btn_prev = ttk.Button(self.nav_frame, text="◀ Back", command=self.prev_slide)

        self.show_slide(0)
        self.calc_risk()

    def on_canvas_resize(self, event):
        if self._resize_timer:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(50, self.update_network)

    def create_card(self, parent, text, category, value, row, col, colspan=1):
        card = tk.Frame(parent, bg="#1C2128", highlightthickness=1, highlightbackground="#30363D", padx=10, pady=15, cursor="hand2")
        card.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=8, pady=8)

        lbl = tk.Label(card, text=text, font=("Segoe UI", 12, "bold"), bg="#1C2128", fg="#C9D1D9", cursor="hand2")
        lbl.pack(expand=True)

        def on_click(e):
            self.choices[category] = value
            self.calc_risk()
            self.root.after(350, self.next_slide)

        card.bind("<Button-1>", on_click)
        lbl.bind("<Button-1>", on_click)
        self.option_cards.append((card, lbl, category, value))

    def update_card_styles(self):
        for card, lbl, category, value in self.option_cards:
            if self.choices[category] == value:
                card.config(bg="#1F2E4D", highlightbackground="#58A6FF")
                lbl.config(bg="#1F2E4D", fg="#FFFFFF")
            else:
                card.config(bg="#1C2128", highlightbackground="#30363D")
                lbl.config(bg="#1C2128", fg="#C9D1D9")

    def build_slides(self):
        f0 = self.make_step_frame("Flight type", "What kind of flight are you taking?")
        self.create_card(f0, "Direct", "Flight", "Direct", 2, 0)
        self.create_card(f0, "Connecting", "Flight", "Connecting", 2, 1)
        self.slides.append(f0)

        f1 = self.make_step_frame("Luggage", "Are you checking a bag?")
        self.create_card(f1, "Carry-on Only", "Luggage", "Carry-on", 2, 0)
        self.create_card(f1, "Checked Bag", "Luggage", "Checked", 2, 1)
        self.slides.append(f1)

        f2 = self.make_step_frame("Weather Forecast", "What is the weather (Confounder)?")
        self.create_card(f2, "Clear", "Weather", "Clear", 2, 0)
        self.create_card(f2, "Rain", "Weather", "Rain", 2, 1)
        self.create_card(f2, "Snow", "Weather", "Snow", 3, 0)
        self.create_card(f2, "Storm", "Weather", "Storm", 3, 1)
        self.slides.append(f2)

        f3 = self.make_step_frame("Transport", "How will you get to the airport?")
        self.create_card(f3, "Taxi", "Transport", "Taxi", 2, 0)
        self.create_card(f3, "Bus", "Transport", "Bus", 2, 1)
        self.create_card(f3, "Hotel (Day before)", "Transport", "Hotel", 3, 0, colspan=2)
        self.slides.append(f3)

        f4 = self.make_step_frame("Time Buffer", "How early will you arrive before boarding?")
        self.create_card(f4, "< 60 Min", "Buffer", "< 60 Min", 2, 0)
        self.create_card(f4, "60-120 Min", "Buffer", "60-120 Min", 2, 1)
        self.create_card(f4, "> 120 Min", "Buffer", "> 120 Min", 3, 0, colspan=2)
        self.slides.append(f4)

        f5 = self.make_step_frame("Security Line", "How long is the queue?")
        self.create_card(f5, "Short Queue", "Security", "Short", 2, 0)
        self.create_card(f5, "Long Queue", "Security", "Long", 2, 1)
        self.slides.append(f5)

    def make_step_frame(self, title, subtitle):
        f = tk.Frame(self.left_frame, bg="#161B22", padx=30, pady=30)
        f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=1)
        tk.Label(f, text=title, font=("Segoe UI", 24, "bold"), bg="#161B22", fg="#E6EDF3").grid(row=0, column=0, columnspan=2, sticky="nw")
        tk.Label(f, text=subtitle, font=("Segoe UI", 12), bg="#161B22", fg="#8B949E", justify="left").grid(row=1, column=0, columnspan=2, sticky="nw", pady=(5, 25))
        return f

    def show_slide(self, index):
        if index >= len(self.slides):
            self.show_final_screen()
            return

        if hasattr(self, 'final_frame') and self.final_frame.winfo_ismapped():
            self.final_frame.pack_forget()
            self.top_frame.pack(side=tk.TOP, fill=tk.X, padx=20, pady=(20, 10))
            self.main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
            self.math_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 20))

        for slide in self.slides:
            slide.pack_forget()
        self.slides[index].pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        if index > 0:
            self.btn_prev.pack(side=tk.LEFT, ipadx=10)
        else:
            self.btn_prev.pack_forget()

        self.current_step = index
        self.update_network()

    def show_final_screen(self):
        self.top_frame.pack_forget()
        self.main_frame.pack_forget()
        self.math_frame.pack_forget()

        if hasattr(self, 'final_frame'):
            self.final_frame.destroy()

        self.final_frame = tk.Frame(self.root, bg="#161B22", highlightthickness=1, highlightbackground="#30363D")
        self.final_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        tk.Label(self.final_frame, text="Your Final Flight Risk", font=("Segoe UI", 28, "bold"), bg="#161B22", fg="#E6EDF3").pack(pady=(60, 10))
        
        if self.current_risk == "ERR":
            color = "#F85149"
            risk_text = "ERROR"
        else:
            color = "#3FB950" if self.current_risk < 15 else "#F85149"
            risk_text = f"{self.current_risk:.1f} %"
            
        tk.Label(self.final_frame, text=risk_text, font=("Segoe UI", 96, "bold"), bg="#161B22", fg=color).pack(pady=10)

        tk.Label(self.final_frame, text="Final Mathematical State:", font=("Segoe UI", 12, "bold"), bg="#161B22", fg="#8B949E").pack(pady=(40, 5))
        form_color = "#3FB950" if self.is_do_calculus else "#58A6FF"
        if self.current_risk == "ERR": form_color = "#F85149"
        
        tk.Label(self.final_frame, text=self.current_formula, font=("Consolas", 14, "bold"), bg="#161B22", fg=form_color).pack(pady=5)

        btn_restart = tk.Button(self.final_frame, text="Restart Simulation", font=("Segoe UI", 12, "bold"), bg="#21262D", fg="#C9D1D9", bd=0, padx=20, pady=10, cursor="hand2", command=self.restart_simulation)
        btn_restart.pack(pady=30)

    def restart_simulation(self):
        self.choices = {"Flight": "Direct", "Luggage": "Carry-on", "Weather": "Clear", "Transport": "Taxi", "Buffer": "60-120 Min", "Security": "Short"}
        self.calc_risk()
        self.show_slide(0)

    def next_slide(self):
        self.show_slide(self.current_step + 1)
    def prev_slide(self):
        if self.current_step > 0: self.show_slide(self.current_step - 1)

    def calc_risk(self):
        self.update_card_styles()
        self.target_risk, self.current_formula, desc, self.is_do_calculus = self.engine.calculate(self.choices)

        if self.target_risk == "ERR":
            self.math_formula_label.config(text=self.current_formula, fg="#F85149")
            self.math_desc_label.config(text=desc, fg="#F85149")
            self.risk_label.config(text="Risk: ERROR", fg="#F85149")
            self.current_risk = "ERR"
        else:
            form_color = "#3FB950" if self.is_do_calculus else "#58A6FF"
            self.math_formula_label.config(text=self.current_formula, fg=form_color)
            self.math_desc_label.config(text=desc, fg="#8B949E")
            
            if self.current_risk == "ERR":
                self.current_risk = 1.0
                
            self.animate_number()

        if self.current_step < len(self.slides):
            self.update_network()

    def animate_number(self):
        if self.target_risk == "ERR" or self.current_risk == "ERR":
            return
            
        if self.current_risk != self.target_risk:
            diff = self.target_risk - self.current_risk
            
            if abs(diff) < 0.15:
                self.current_risk = self.target_risk
            else:
                step = 0.5 if abs(diff) > 3.0 else 0.1
                self.current_risk += step if diff > 0 else -step
                self.current_risk = round(self.current_risk, 1)

            color = "#3FB950" if self.current_risk < 15 else "#F85149"
            self.risk_label.config(text=f"Risk: {self.current_risk:.1f} %", fg=color)
            self.root.after(25, self.animate_number)
        else:
            color = "#3FB950" if self.current_risk < 15 else "#F85149"
            self.risk_label.config(text=f"Risk: {self.current_risk:.1f} %", fg=color)

    def round_rectangle(self, x1, y1, x2, y2, radius=12, **kwargs):
        points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1, x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
        return self.canvas.create_polygon(points, **kwargs, smooth=True)

    def edge_point(self, x1, y1, x2, y2, hw, hh, gap=6):
        dx, dy = x2 - x1, y2 - y1
        if not dx and not dy:
            return x1, y1
        t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        t += gap / ((dx * dx + dy * dy) ** 0.5)
        return x1 + dx * t, y1 + dy * t

    def update_network(self):
        self.canvas.update_idletasks()
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 100: w = 640
        if h < 100: h = 500
        self.canvas.delete("all")

        hw = max(62, min(85, w * 0.115))
        hh = max(26, min(34, h * 0.062))

        risk_display = "ERROR" if self.target_risk == "ERR" else f"{self.target_risk:.1f}%"

        layout = {
            "Weather":   (0.13, 0.13, "Weather", 2),
            "Flight":    (0.44, 0.13, "Flight type", 0),
            "Luggage":   (0.75, 0.13, "Luggage", 1),
            "Transport": (0.13, 0.42, "Transport", 3),
            "Security":  (0.87, 0.42, "Security line", 5),
            "Buffer":    (0.13, 0.68, "Time buffer", 4),
            "Result":    (0.50, 0.89, f"Missed flight\n{risk_display}", -1),
        }
        nodes = {k: (rx * w, ry * h, txt, s) for k, (rx, ry, txt, s) in layout.items()}

        edges = [("Flight", "Result"), ("Luggage", "Result"), ("Security", "Result"),
                 ("Transport", "Result"), ("Buffer", "Result")]
        
        if self.choices["Transport"] != "Hotel":
            edges.append(("Weather", "Transport"))

        for start, end in edges:
            x1, y1, _, step_idx = nodes[start]
            x2, y2 = nodes[end][0], nodes[end][1]
            color = "#F85149" if start == "Weather" else "#484F58"
            width = 2
            if step_idx == self.current_step:
                color, width = "#58A6FF", 3
            sx, sy = self.edge_point(x1, y1, x2, y2, hw, hh)
            ex, ey = self.edge_point(x2, y2, x1, y1, hw, hh)
            self.canvas.create_line(sx, sy, ex, ey, arrow=tk.LAST,
                                    fill=color, width=width, arrowshape=(12, 14, 5))

        for key, (x, y, text, step_idx) in nodes.items():
            active = (step_idx == self.current_step)
            bg = "#1F2E4D" if active else "#161B22"
            outline = "#58A6FF" if active else "#30363D"
            fg = "#FFFFFF" if active else "#8B949E"
            if key == "Result":
                bg, outline, fg = "#161B22", "#3FB950", "#E6EDF3"
                if self.target_risk == "ERR":
                    outline = "#F85149"
                    fg = "#F85149"
            self.round_rectangle(x - hw, y - hh, x + hw, y + hh, radius=10,
                                 fill=bg, outline=outline, width=2)
            self.canvas.create_text(x, y, text=text, justify=tk.CENTER,
                                    font=("Segoe UI", 10, "bold"), fill=fg)

if __name__ == "__main__":
    root = tk.Tk()
    app = CausalFlightApp(root)
    root.mainloop()
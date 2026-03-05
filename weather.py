import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request
import urllib.parse
import json
import threading
import datetime

# Uses Open-Meteo (free, no API key) + geocoding via Open-Meteo geocoding API
# DJIA via Yahoo Finance (no API key)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search?name={}&count=1&language=en&format=json"
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
    "wind_speed_10m,weathercode,precipitation"
    "&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum"
    "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
    "&timezone=auto&forecast_days=7"
)

WMO_CODES = {
    0: ("Clear Sky", "☀"),
    1: ("Mainly Clear", "🌤"),
    2: ("Partly Cloudy", "⛅"),
    3: ("Overcast", "☁"),
    45: ("Foggy", "🌫"),
    48: ("Icy Fog", "🌫"),
    51: ("Light Drizzle", "🌦"),
    53: ("Drizzle", "🌦"),
    55: ("Heavy Drizzle", "🌧"),
    61: ("Light Rain", "🌧"),
    63: ("Rain", "🌧"),
    65: ("Heavy Rain", "🌧"),
    71: ("Light Snow", "🌨"),
    73: ("Snow", "❄"),
    75: ("Heavy Snow", "❄"),
    77: ("Snow Grains", "❄"),
    80: ("Light Showers", "🌦"),
    81: ("Showers", "🌧"),
    82: ("Heavy Showers", "⛈"),
    85: ("Snow Showers", "🌨"),
    86: ("Heavy Snow Showers", "❄"),
    95: ("Thunderstorm", "⛈"),
    96: ("Thunderstorm w/ Hail", "⛈"),
    99: ("Thunderstorm w/ Heavy Hail", "⛈"),
}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DJIA_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1d&range=2d"
DJIA_REFRESH_MS = 60_000  # refresh every 60 seconds


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "weather-desktop-app/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def wmo_label(code):
    entry = WMO_CODES.get(code, ("Unknown", "?"))
    return entry[1], entry[0]


class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Weather")
        self.resizable(False, False)
        self.configure(bg="#1e2a3a")
        self._build_ui()

    def _build_ui(self):
        pad = dict(padx=12, pady=6)

        # Search bar
        top = tk.Frame(self, bg="#1e2a3a")
        top.pack(fill="x", **pad)

        self.city_var = tk.StringVar(value="New York")
        entry = tk.Entry(top, textvariable=self.city_var, font=("Segoe UI", 13),
                         bg="#2e3f54", fg="white", insertbackground="white",
                         relief="flat", bd=4, width=22)
        entry.pack(side="left", ipady=4)
        entry.bind("<Return>", lambda _: self._search())

        btn = tk.Button(top, text="Search", font=("Segoe UI", 11), bg="#3a7bd5",
                        fg="white", activebackground="#2a5fa8", activeforeground="white",
                        relief="flat", bd=0, cursor="hand2", padx=10,
                        command=self._search)
        btn.pack(side="left", padx=(8, 0))

        self.status_lbl = tk.Label(top, text="", font=("Segoe UI", 9),
                                   bg="#1e2a3a", fg="#aaa")
        self.status_lbl.pack(side="left", padx=8)

        # Current weather panel
        cur = tk.Frame(self, bg="#26374a", padx=16, pady=12)
        cur.pack(fill="x", padx=12, pady=(0, 6))

        self.icon_lbl = tk.Label(cur, text="", font=("Segoe UI Emoji", 52),
                                 bg="#26374a", fg="white")
        self.icon_lbl.pack(side="left")

        info = tk.Frame(cur, bg="#26374a")
        info.pack(side="left", padx=16)

        self.city_lbl = tk.Label(info, text="—", font=("Segoe UI", 18, "bold"),
                                 bg="#26374a", fg="white")
        self.city_lbl.pack(anchor="w")

        self.desc_lbl = tk.Label(info, text="", font=("Segoe UI", 11),
                                 bg="#26374a", fg="#8ab4d8")
        self.desc_lbl.pack(anchor="w")

        self.temp_lbl = tk.Label(info, text="", font=("Segoe UI", 36, "bold"),
                                 bg="#26374a", fg="white")
        self.temp_lbl.pack(anchor="w")

        extras = tk.Frame(cur, bg="#26374a")
        extras.pack(side="left", padx=24)

        self.feels_lbl = tk.Label(extras, text="", font=("Segoe UI", 10),
                                  bg="#26374a", fg="#ccc")
        self.feels_lbl.pack(anchor="w")
        self.humid_lbl = tk.Label(extras, text="", font=("Segoe UI", 10),
                                  bg="#26374a", fg="#ccc")
        self.humid_lbl.pack(anchor="w")
        self.wind_lbl = tk.Label(extras, text="", font=("Segoe UI", 10),
                                 bg="#26374a", fg="#ccc")
        self.wind_lbl.pack(anchor="w")
        self.precip_lbl = tk.Label(extras, text="", font=("Segoe UI", 10),
                                   bg="#26374a", fg="#ccc")
        self.precip_lbl.pack(anchor="w")

        # 7-day forecast
        fc_frame = tk.Frame(self, bg="#1e2a3a")
        fc_frame.pack(fill="x", padx=12, pady=(0, 12))

        self.day_frames = []
        for i in range(7):
            df = tk.Frame(fc_frame, bg="#26374a", padx=8, pady=6)
            df.grid(row=0, column=i, padx=3)
            fc_frame.columnconfigure(i, weight=1)

            day_lbl = tk.Label(df, text="", font=("Segoe UI", 9, "bold"),
                               bg="#26374a", fg="#8ab4d8")
            day_lbl.pack()
            icon_lbl = tk.Label(df, text="", font=("Segoe UI Emoji", 20),
                                bg="#26374a")
            icon_lbl.pack()
            hi_lbl = tk.Label(df, text="", font=("Segoe UI", 10, "bold"),
                              bg="#26374a", fg="white")
            hi_lbl.pack()
            lo_lbl = tk.Label(df, text="", font=("Segoe UI", 9),
                              bg="#26374a", fg="#888")
            lo_lbl.pack()
            self.day_frames.append((day_lbl, icon_lbl, hi_lbl, lo_lbl))

        # DJIA ticker panel
        dji_frame = tk.Frame(self, bg="#1a2535", padx=14, pady=8)
        dji_frame.pack(fill="x", padx=12, pady=(0, 12))

        tk.Label(dji_frame, text="DOW JONES  (DJIA)", font=("Segoe UI", 9, "bold"),
                 bg="#1a2535", fg="#8ab4d8").pack(side="left")

        self.dji_price_lbl = tk.Label(dji_frame, text="—", font=("Segoe UI", 14, "bold"),
                                      bg="#1a2535", fg="white")
        self.dji_price_lbl.pack(side="left", padx=(12, 4))

        self.dji_change_lbl = tk.Label(dji_frame, text="", font=("Segoe UI", 11),
                                       bg="#1a2535", fg="#aaa")
        self.dji_change_lbl.pack(side="left")

        self.dji_time_lbl = tk.Label(dji_frame, text="", font=("Segoe UI", 8),
                                     bg="#1a2535", fg="#555")
        self.dji_time_lbl.pack(side="right")

        self._refresh_djia()
        self._search()

    def _refresh_djia(self):
        threading.Thread(target=self._fetch_djia, daemon=True).start()
        self.after(DJIA_REFRESH_MS, self._refresh_djia)

    def _fetch_djia(self):
        try:
            data = fetch_json(DJIA_URL)
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            prev_close = meta["chartPreviousClose"]
            change = price - prev_close
            pct = (change / prev_close) * 100
            ts = meta.get("regularMarketTime")
            if ts:
                t = datetime.datetime.fromtimestamp(ts).strftime("%b %d %I:%M %p")
            else:
                t = ""
            self.after(0, lambda: self._update_djia(price, change, pct, t))
        except Exception:
            pass  # silently skip on network error

    def _update_djia(self, price, change, pct, timestamp):
        self.dji_price_lbl.config(text=f"{price:,.2f}")
        sign = "+" if change >= 0 else ""
        color = "#4caf50" if change >= 0 else "#f44336"
        self.dji_change_lbl.config(
            text=f"{sign}{change:,.2f}  ({sign}{pct:.2f}%)", fg=color)
        self.dji_time_lbl.config(text=timestamp)

    def _search(self):
        city = self.city_var.get().strip()
        if not city:
            return
        self.status_lbl.config(text="Loading…")
        threading.Thread(target=self._fetch, args=(city,), daemon=True).start()

    def _fetch(self, city):
        try:
            geo = fetch_json(GEOCODE_URL.format(urllib.parse.quote(city)))
            if not geo.get("results"):
                self.after(0, lambda: messagebox.showerror("Not Found",
                    f"City '{city}' not found."))
                self.after(0, lambda: self.status_lbl.config(text=""))
                return
            r = geo["results"][0]
            lat, lon = r["latitude"], r["longitude"]
            name = r.get("name", city)
            country = r.get("country_code", "")

            data = fetch_json(WEATHER_URL.format(lat=lat, lon=lon))
            self.after(0, lambda: self._update_ui(name, country, data))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.status_lbl.config(text=""))

    def _update_ui(self, city, country, data):
        cur = data["current"]
        daily = data["daily"]

        icon, desc = wmo_label(cur["weathercode"])
        self.icon_lbl.config(text=icon)
        self.city_lbl.config(text=f"{city}, {country}" if country else city)
        self.desc_lbl.config(text=desc)
        self.temp_lbl.config(text=f"{cur['temperature_2m']:.0f}°F")
        self.feels_lbl.config(text=f"Feels like  {cur['apparent_temperature']:.0f}°F")
        self.humid_lbl.config(text=f"Humidity     {cur['relative_humidity_2m']}%")
        self.wind_lbl.config(text=f"Wind          {cur['wind_speed_10m']:.0f} mph")
        self.precip_lbl.config(text=f"Precip         {cur['precipitation']:.2f} in")

        today_wd = datetime.date.today().weekday()  # 0=Mon

        for i, (day_lbl, icon_lbl, hi_lbl, lo_lbl) in enumerate(self.day_frames):
            wd = (today_wd + i) % 7
            label = "Today" if i == 0 else DAYS[wd]
            d_icon, _ = wmo_label(daily["weathercode"][i])
            hi = daily["temperature_2m_max"][i]
            lo = daily["temperature_2m_min"][i]
            day_lbl.config(text=label)
            icon_lbl.config(text=d_icon)
            hi_lbl.config(text=f"{hi:.0f}°")
            lo_lbl.config(text=f"{lo:.0f}°")

        self.status_lbl.config(text="")


if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()

#!/usr/bin/env python3
"""Big RSSI of TELLO-62A593 on the Pi desktop. Reads /run/go2-rssi."""
import tkinter as tk
from pathlib import Path

PATH = Path("/run/go2-rssi")

root = tk.Tk()
root.title("TELLO-62A593")
root.configure(bg="#111111")
root.attributes("-topmost", True)
root.geometry("820x260+40+40")
tk.Label(root, text="TELLO-62A593", fg="#dddddd", bg="#111111", font=("Sans", 22)).pack(pady=(36, 0))
value = tk.Label(root, text="…", fg="#f2d230", bg="#111111", font=("Sans", 64, "bold"))
value.pack(fill="x", expand=True)


def tick():
    try:
        text = PATH.read_text().strip() + " dBm"
    except OSError:
        text = "n/a"
    value.config(text=text)
    root.after(1000, tick)


tick()
root.mainloop()

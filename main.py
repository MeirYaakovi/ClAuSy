import customtkinter as ctk
from app import ClausyApp
import storage


def main():
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    data = storage.load()
    if data.get("window_maximized", True):
        root.geometry("1100x720")
        root.state("zoomed")
    else:
        root.geometry(data.get("window_geometry") or "1100x720")
    ClausyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

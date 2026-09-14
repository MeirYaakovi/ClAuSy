import customtkinter as ctk
from app import ClausyApp


def main():
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.geometry("1100x720")
    root.state("zoomed")
    ClausyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

import tkinter as tk
from app import ClausyApp


def main():
    root = tk.Tk()
    root.geometry("960x640")
    ClausyApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

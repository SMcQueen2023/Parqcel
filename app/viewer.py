import os
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox

class ParquetViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Parquet File Viewer")
        self.df = None
        self.parquet_file_path = None
        
        # Create a button to load a Parquet file
        self.load_button = tk.Button(root, text="Load Parquet File", command=self.load_parquet)
        self.load_button.pack(pady=10)
        
        # Create a button to save over the Parquet file
        self.save_button = tk.Button(root, text="Save Changes", command=self.save_over_parquet, state=tk.DISABLED)
        self.save_button.pack(pady=10)
    
    def load_parquet(self):
        """Load a Parquet file and display its content."""
        file_path = filedialog.askopenfilename(filetypes=[("Parquet Files", "*.parquet")])
        if file_path:
            self.parquet_file_path = file_path
            self.df = pd.read_parquet(self.parquet_file_path)
            # Here you could display the DataFrame in a table widget, e.g., a Treeview
            print(self.df)
            self.save_button.config(state=tk.NORMAL)  # Enable the Save button
    
    def save_over_parquet(self):
        """Save the changes to the original Parquet file."""
        if self.df is not None and self.parquet_file_path:
            # You can modify the DataFrame here if needed
            # For example, let's say you want to add 1 to the "age" column
            self.df['age'] = self.df['age'] + 1  # Example modification
            
            # Save over the original Parquet file
            self.df.to_parquet(self.parquet_file_path)
            
            messagebox.showinfo("Success", f"Parquet file saved and overwritten at: {self.parquet_file_path}")
        else:
            messagebox.showerror("Error", "No Parquet file loaded.")

if __name__ == "__main__":
    root = tk.Tk()
    viewer = ParquetViewer(root)  # Pass root to the ParquetViewer class
    root.mainloop()  # Start the Tkinter event loop

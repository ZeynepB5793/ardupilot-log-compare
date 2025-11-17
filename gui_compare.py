import customtkinter as ctk
from tkinter import filedialog
import subprocess
import pandas as pd
import threading
import tempfile
import os
import datetime

# Imports for plotting and the toolbar
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# --- Main Application Class ---
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Log Comparator")
        self.geometry("1300x1000")
        ctk.set_appearance_mode("System")
        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- File & Action Frame ---
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.grid(row=0, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.top_frame.grid_columnconfigure(1, weight=1)

        self.file1_path = ""
        self.file2_path = ""

        self.file1_button = ctk.CTkButton(self.top_frame, text="Select Original Log (.bin)", command=lambda: self.select_file(1))
        self.file1_button.grid(row=0, column=0, padx=10, pady=5)
        self.file1_label = ctk.CTkLabel(self.top_frame, text="No file selected")
        self.file1_label.grid(row=0, column=1, padx=10, sticky="w")

        self.file2_button = ctk.CTkButton(self.top_frame, text="Select New Log (.bin)", command=lambda: self.select_file(2))
        self.file2_button.grid(row=1, column=0, padx=10, pady=5)
        self.file2_label = ctk.CTkLabel(self.top_frame, text="No file selected")
        self.file2_label.grid(row=1, column=1, padx=10, sticky="w")
        
        self.compare_button = ctk.CTkButton(self, text="Compare and Plot", command=self.start_comparison_thread)
        self.compare_button.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        
        # --- Plot Frames (Side-by-side) ---
        self.left_plot_frame = ctk.CTkFrame(self)
        self.left_plot_frame.grid(row=2, column=0, padx=(10, 5), pady=5, sticky="nsew")
        self.right_plot_frame = ctk.CTkFrame(self)
        self.right_plot_frame.grid(row=2, column=1, padx=(5, 10), pady=5, sticky="nsew")
        
        # --- Toolbar Frames ---
        self.left_toolbar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.left_toolbar_frame.grid(row=3, column=0, padx=(10, 5), pady=0, sticky="ew")
        self.right_toolbar_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.right_toolbar_frame.grid(row=3, column=1, padx=(5, 10), pady=0, sticky="ew")

        # --- Message Frames ---
        self.message_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.message_frame.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.message_frame.grid_columnconfigure((0, 1), weight=1)
        
        ctk.CTkLabel(self.message_frame, text="Log 1 Messages", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0)
        self.msg_box1 = ctk.CTkTextbox(self.message_frame, height=100, font=("Courier", 12))
        self.msg_box1.grid(row=1, column=0, padx=(0, 5), sticky="ew")

        ctk.CTkLabel(self.message_frame, text="Log 2 Messages", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1)
        self.msg_box2 = ctk.CTkTextbox(self.message_frame, height=100, font=("Courier", 12))
        self.msg_box2.grid(row=1, column=1, padx=(5, 0), sticky="ew")

        # --- Results Display (Bottom) ---
        self.results_textbox = ctk.CTkTextbox(self, height=150, font=("Courier", 13))
        self.results_textbox.grid(row=5, column=0, columnspan=2, padx=10, pady=10, sticky="ew")
        self.results_textbox.insert("1.0", "Parameter changes will be shown here.")

        # --- Canvas and Toolbar Placeholders ---
        self.left_canvas = self.right_canvas = self.left_toolbar = self.right_toolbar = None


    def select_file(self, file_num):
        filepath = filedialog.askopenfilename(title="Select a .bin file", filetypes=(("ArduPilot Log", "*.bin"),))
        if not filepath: return
        
        filename = os.path.basename(filepath)
        if file_num == 1:
            self.file1_path = filepath
            self.file1_label.configure(text=filename)
        else:
            self.file2_path = filepath
            self.file2_label.configure(text=filename)

    def start_comparison_thread(self):
        if not self.file1_path or not self.file2_path:
            self.update_results("Error: Please select both log files first.")
            return

        self.update_results("Processing... This may take a moment.")
        
        if self.left_canvas: self.left_canvas.get_tk_widget().destroy()
        if self.right_canvas: self.right_canvas.get_tk_widget().destroy()
        if self.left_toolbar: self.left_toolbar.destroy()
        if self.right_toolbar: self.right_toolbar.destroy()
        self.update_messages("", "")

        thread = threading.Thread(target=self.run_analysis)
        thread.start()
        
    def run_analysis(self):
        try:
            matplotlib.use("Agg")

            # --- Extract Data ---
            param_text = self.get_param_diff()
            
            df1 = self.get_log_data(self.file1_path, ['ATT'])
            df2 = self.get_log_data(self.file2_path, ['ATT'])

            df1_ctun = self.get_log_data(self.file1_path, ['CTUN'])
            if not df1_ctun.empty and not df1.empty:
                df1 = pd.merge_asof(df1.sort_values('TimeUS'), df1_ctun.sort_values('TimeUS'), on='TimeUS', direction='nearest')
                if 'TimeS_x' in df1.columns:
                    df1 = df1.rename(columns={'TimeS_x': 'TimeS'})

            df2_ctun = self.get_log_data(self.file2_path, ['CTUN'])
            if not df2_ctun.empty and not df2.empty:
                df2 = pd.merge_asof(df2.sort_values('TimeUS'), df2_ctun.sort_values('TimeUS'), on='TimeUS', direction='nearest')
                if 'TimeS_x' in df2.columns:
                    df2 = df2.rename(columns={'TimeS_x': 'TimeS'})

            df1_msg = self.get_log_data(self.file1_path, ['MSG'])
            df2_msg = self.get_log_data(self.file2_path, ['MSG'])
            
            msg1_text = self.format_messages(df1_msg)
            msg2_text = self.format_messages(df2_msg)

            # --- Define Plotting Columns ---
            PITCH_COL, DES_PITCH_COL = 'Pitch', 'DesPitch'
            ROLL_COL, DES_ROLL_COL = 'Roll', 'DesRoll'
            YAW_COL, DES_YAW_COL = 'Yaw', 'DesYaw'
            TIME_COL = 'TimeS'
            
            # --- Corrected Altitude Column Names ---
            ALT_COL, DES_ALT_COL = 'Alt', 'DAlt'
            # ------------------------------------

            plt.style.use('seaborn-v0_8-darkgrid')
            
            # --- Create Figure for Log 1 ---
            fig_log1, axs1 = plt.subplots(4, 1, figsize=(6, 10), sharex=True)
            fig_log1.suptitle('Log 1 Performance', fontsize=14)
            self.create_subplot(axs1[0], df1, [TIME_COL, PITCH_COL, DES_PITCH_COL], TIME_COL, PITCH_COL, DES_PITCH_COL, 'Pitch vs. Desired Pitch', 'Degrees')
            self.create_subplot(axs1[1], df1, [TIME_COL, ROLL_COL, DES_ROLL_COL], TIME_COL, ROLL_COL, DES_ROLL_COL, 'Roll vs. Desired Roll', 'Degrees')
            self.create_subplot(axs1[2], df1, [TIME_COL, YAW_COL, DES_YAW_COL], TIME_COL, YAW_COL, DES_YAW_COL, 'Yaw vs. Desired Yaw', 'Degrees')
            self.create_subplot(axs1[3], df1, [TIME_COL, ALT_COL, DES_ALT_COL], TIME_COL, ALT_COL, DES_ALT_COL, 'Altitude vs. Desired Altitude', 'Meters')
            axs1[3].set_xlabel('Time (s)')
            fig_log1.tight_layout(rect=[0, 0, 1, 0.96])

            # --- Create Figure for Log 2 ---
            fig_log2, axs2 = plt.subplots(4, 1, figsize=(6, 10), sharex=True)
            fig_log2.suptitle('Log 2 Performance', fontsize=14)
            self.create_subplot(axs2[0], df2, [TIME_COL, PITCH_COL, DES_PITCH_COL], TIME_COL, PITCH_COL, DES_PITCH_COL, 'Pitch vs. Desired Pitch', 'Degrees')
            self.create_subplot(axs2[1], df2, [TIME_COL, ROLL_COL, DES_ROLL_COL], TIME_COL, ROLL_COL, DES_ROLL_COL, 'Roll vs. Desired Roll', 'Degrees')
            self.create_subplot(axs2[2], df2, [TIME_COL, YAW_COL, DES_YAW_COL], TIME_COL, YAW_COL, DES_YAW_COL, 'Yaw vs. Desired Yaw', 'Degrees')
            self.create_subplot(axs2[3], df2, [TIME_COL, ALT_COL, DES_ALT_COL], TIME_COL, ALT_COL, DES_ALT_COL, 'Altitude vs. Desired Altitude', 'Meters')
            axs2[3].set_xlabel('Time (s)')
            fig_log2.tight_layout(rect=[0, 0, 1, 0.96])

            self.after(0, self.update_gui, param_text, msg1_text, msg2_text, fig_log1, fig_log2)

        except Exception as e:
            print(f"BACKGROUND ERROR: {e}")
            error_message = f"An error occurred:\n{str(e)}"
            self.after(0, self.update_results, error_message)
    
    def create_subplot(self, ax, df, cols, time_col, val_col, des_val_col, title, unit):
        """Helper function to create a single subplot."""
        ax.set_title(title)
        if not df.empty and all(c in df.columns for c in cols):
            ax.plot(df[time_col], df[val_col], label='Actual')
            ax.plot(df[time_col], df[des_val_col], '--', label='Desired')
            ax.set_ylabel(unit)
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'Data not found in log.', ha='center', va='center')

    def format_messages(self, df_msg):
        """Formats message dataframe into a displayable string."""
        if df_msg.empty or 'Message' not in df_msg.columns:
            return "No messages found in log."
        
        text = ""
        for _, row in df_msg.iterrows():
            time_str = str(datetime.timedelta(microseconds=row['TimeUS'])).split('.')[0]
            text += f"[{time_str}] {row['Message']}\n"
        return text

    def get_log_data(self, log_path, types):
        """Runs mavlogdump, returns a pandas DataFrame."""
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".csv") as temp_csv:
            subprocess.run(['mavlogdump.py', '--format', 'csv', '--types', ','.join(types), log_path], stdout=temp_csv, check=True)
            temp_name = temp_csv.name
        try:
            df = pd.read_csv(temp_name, quotechar='"', quoting=1, on_bad_lines='warn')
        except pd.errors.EmptyDataError:
            df = pd.DataFrame()
        os.remove(temp_name)
        if 'TimeUS' in df.columns:
            df['TimeS'] = df['TimeUS'] / 1_000_000
        return df

    def get_param_diff(self):
        """Compares parameter files, returns a formatted string."""
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".csv") as temp_csv1, \
             tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".csv") as temp_csv2:
            subprocess.run(['mavlogdump.py', '--format', 'csv', '--types', 'PARM', self.file1_path], stdout=temp_csv1, check=True)
            subprocess.run(['mavlogdump.py', '--format', 'csv', '--types', 'PARM', self.file2_path], stdout=temp_csv2, check=True)
            name1, name2 = temp_csv1.name, temp_csv2.name

        params1 = pd.read_csv(name1).set_index('Name')
        params2 = pd.read_csv(name2).set_index('Name')
        os.remove(name1); os.remove(name2)
        
        combined = params1.join(params2, lsuffix='_log1', rsuffix='_log2', how='outer')
        changed = combined[combined['Value_log1'].fillna(-9999) != combined['Value_log2'].fillna(-9999)]

        result_text = "--- Changed Parameters ---\n\n"
        if changed.empty:
            result_text += "No differences found."
        else:
            for name, row in changed.iterrows():
                v1, v2 = row['Value_log1'], row['Value_log2']
                if pd.isna(v1): result_text += f"ADDED:   {name} = {v2}\n"
                elif pd.isna(v2): result_text += f"REMOVED: {name} (was {v1})\n"
                else: result_text += f"CHANGED: {name}: {v1} -> {v2}\n"
        return result_text

    def update_gui(self, param_text, msg1_text, msg2_text, fig_log1, fig_log2):
        """Updates all GUI elements with new data."""
        self.update_results(param_text)
        self.update_messages(msg1_text, msg2_text)
        
        self.left_canvas = FigureCanvasTkAgg(fig_log1, master=self.left_plot_frame)
        self.left_canvas.draw()
        self.left_canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.left_toolbar = NavigationToolbar2Tk(self.left_canvas, self.left_toolbar_frame)
        self.left_toolbar.update()
        
        self.right_canvas = FigureCanvasTkAgg(fig_log2, master=self.right_plot_frame)
        self.right_canvas.draw()
        self.right_canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.right_toolbar = NavigationToolbar2Tk(self.right_canvas, self.right_toolbar_frame)
        self.right_toolbar.update()

    def update_results(self, text):
        """Safely updates the parameter results text box."""
        self.results_textbox.delete("1.0", "end")
        self.results_textbox.insert("1.0", text)

    def update_messages(self, text1, text2):
        """Safely updates the message text boxes."""
        self.msg_box1.delete("1.0", "end"); self.msg_box1.insert("1.0", text1)
        self.msg_box2.delete("1.0", "end"); self.msg_box2.insert("1.0", text2)

# --- Run the Application ---
if __name__ == "__main__":
    app = App()
    app.mainloop()

import subprocess

def run_script(script_name):
    print(f"Starting {script_name}...")
    subprocess.Popen(["python", script_name], creationflags=subprocess.CREATE_NEW_CONSOLE)

if __name__ == "__main__":
    print("123 LoadBoard Automation")
    
    run_script("123loadboard.py")
    run_script("data_fetcher.py")
    run_script("email_processor.py")
    
    print("All scripts launched. Press any key to exit this window...")
    input("Press Enter to exit...")

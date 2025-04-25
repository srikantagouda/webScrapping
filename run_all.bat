@echo off
title 123 LoadBoard Automation
echo Starting 123loadboard.py...
start cmd /k "python 123loadboard.py"

echo Starting data_fetcher.py...
start cmd /k "python data_fetcher.py"

echo Starting email_processor.py...
start cmd /k "python email_processor.py"

echo All scripts launched. Press any key to exit this window...
pause
exit 
# MAKE VIRTUAL ENVIRONMENT AND INSTALL LIBRARIES
bash
virtualenv venv -p $(which python3) 
source ./venv/bin/activate
pip3 install -r requirements.txt

# INSTALL CHROMEDRIVER IN SAME DIRECTORY; NAME IT chromedriver.exe
### select version that matches your own Chrome browser's version, e.g. 83, 81, etc.
https://sites.google.com/a/chromium.org/chromedriver/downloads

# run server locally with gunicorn
gunicorn main:app

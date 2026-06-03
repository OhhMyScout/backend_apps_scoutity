# main.py
import os
from flask import Flask
from flask_cors import CORS
from flask_mail import Mail
from dotenv import load_dotenv
from app.module.login.login import login_blueprint
from app.module.register.register import init_register_blueprint
# --- IMPORT BLUEPRINT LOGOUT KAMU BRAY ---
from app.module.logout.logout import logout_bp 

load_dotenv()

app = Flask(__name__)
CORS(app)

# Konfigurasi Flask-Mail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('Scoutify Team', os.getenv('MAIL_DEFAULT_SENDER'))

# Buat objek mail hanya di main bray!
mail = Mail(app)

# Panggil fungsinya dan masukkan objek mail ke dalamnya
register_blueprint = init_register_blueprint(mail)

# Registrasi blueprint ke Flask
app.register_blueprint(login_blueprint, url_prefix='/api')
app.register_blueprint(register_blueprint, url_prefix='/api')
# --- REGISTRASI BLUEPRINT LOGOUT KE FLASK BRAY ---
app.register_blueprint(logout_bp, url_prefix='/api')

@app.route('/')
def index():
    return "Backend Scoutify is Running!"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
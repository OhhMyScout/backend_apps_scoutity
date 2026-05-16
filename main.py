# main.py
from flask import Flask
from flask_cors import CORS
from app.module.login.login import login_blueprint
from app.module.register.register import register_blueprint # Import ini

app = Flask(__name__)
CORS(app)

# Registrasi semua blueprint
app.register_blueprint(login_blueprint, url_prefix='/api')
app.register_blueprint(register_blueprint, url_prefix='/api')

@app.route('/')
def index():
    return "Backend Scoutify is Running!"

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
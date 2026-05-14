from flask import Blueprint

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/')
def auth_index():
    return {"message": "Authentication routes coming soon!"}

@auth_bp.route('/login')
def login():
    return {"message": "login coming soon dont hack me!"}

@auth_bp.route('/logout')
def logout():
    return {"message": "Logout coming soon brother!"}

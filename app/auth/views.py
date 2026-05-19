from flask_smorest import Blueprint

auth_bp = Blueprint('auth', 'auth', url_prefix='/auth', description="Authentication routes")

@auth_bp.route('/')
def auth_index():
    return {"message": "Authentication routes coming soon!"}

@auth_bp.route('/login')
def login():
    return {"message": "login coming soon dont hack me!"}

@auth_bp.route('/logout')
def logout():
    return {"message": "Logout coming soon brother!"}

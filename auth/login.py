# auth/login.py

from data.database import login_user

def login(username, password):
    """사용자 인증을 수행합니다."""
    success, message, user_id = login_user(username, password)
    return success, message, user_id

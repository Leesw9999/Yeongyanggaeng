# data/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User, Meal
import bcrypt

# 데이터베이스 엔진 생성
engine = create_engine('sqlite:///meals.db', echo=True)
Session = sessionmaker(bind=engine)

def initialize_database():
    Base.metadata.create_all(engine)

def get_session():
    return Session()

def create_user(username, password):
    session = get_session()
    try:
        existing_user = session.query(User).filter_by(username=username).first()
        if existing_user:
            return False  # 이미 존재하는 사용자
        
        # 비밀번호 해싱
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        new_user = User(
            username=username,
            password=hashed_password.decode('utf-8')
        )
        session.add(new_user)
        session.commit()
        return True
    except Exception as e:
        print(f"Error creating user: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def login_user(username, password):
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if not user:
            return False, "사용자가 존재하지 않습니다.", None
        
        if bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return True, "로그인 성공!", user.id
        else:
            return False, "비밀번호가 올바르지 않습니다.", None
    except Exception as e:
        print(f"Error logging in: {e}")
        return False, "로그인 중 오류가 발생했습니다.", None
    finally:
        session.close()

def get_user(user_id):
    session = get_session()
    try:
        return session.query(User).filter_by(id=user_id).first()
    finally:
        session.close()

def verify_password(stored_password, provided_password):
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))

def add_diet(user_id, meal):
    session = get_session()
    try:
        new_meal = Meal(
            user_id=user_id,
            name=meal['name'],
            calories=meal['calories'],
            proteins=meal['proteins'],
            carbs=meal['carbs'],
            fats=meal['fats']
        )
        session.add(new_meal)
        session.commit()
        return True
    except Exception as e:
        print(f"Error adding diet: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_diets(user_id):
    session = get_session()
    try:
        return session.query(Meal).filter_by(user_id=user_id).all()
    finally:
        session.close()

def delete_meal(user_id, meal_id):
    session = get_session()
    try:
        meal = session.query(Meal).filter_by(user_id=user_id, id=meal_id).first()
        if meal:
            session.delete(meal)
            session.commit()
            return True
        else:
            return False
    except Exception as e:
        print(f"Error deleting meal: {e}")
        session.rollback()
        return False
    finally:
        session.close()

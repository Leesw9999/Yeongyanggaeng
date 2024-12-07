import streamlit as st
import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, asc, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import pandas as pd
import requests
import openai
from openai.error import RateLimitError, OpenAIError
from datetime import datetime
import json
import io
from googletrans import Translator
import time
import logging
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy 기본 설정
Base = declarative_base()

# Meal 모델 정의 (식단 관리용)
class Meal(Base):
    __tablename__ = 'meals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    calories = Column(Float, default=0.0)
    proteins = Column(Float, default=0.0)
    carbs = Column(Float, default=0.0)
    fats = Column(Float, default=0.0)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)

# ManualMeal 모델 정의 (식단 입력용)
class ManualMeal(Base):
    __tablename__ = 'manual_meals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    name = Column(String, nullable=False)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)

# User 모델 정의
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    meals = relationship('Meal', backref='user', cascade="all, delete-orphan")
    manual_meals = relationship('ManualMeal', backref='user', cascade="all, delete-orphan")

# ProductTranslation 모델 정의 (번역 캐시용)
class ProductTranslation(Base):
    __tablename__ = 'product_translations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    barcode = Column(String, unique=True, nullable=False)
    translated_name = Column(String, nullable=False)

# 데이터베이스 초기화 함수
def initialize_database():
    engine = create_engine('sqlite:///meals.db', echo=False)
    Base.metadata.create_all(engine)
    return engine

# 데이터베이스 세션 생성
engine = initialize_database()
Session_db = sessionmaker(bind=engine)

# 사용자 생성 함수
def create_user(username, password):
    session = Session_db()
    try:
        if session.query(User).filter_by(username=username).first():
            return False  # 사용자 이미 존재
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        new_user = User(username=username, password=hashed_pw.decode('utf-8'))
        session.add(new_user)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        st.error(f"사용자 생성 중 오류 발생: {e}")
        return False
    finally:
        session.close()

# 사용자 로그인 함수
def login_user(username, password):
    session = Session_db()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return True, "로그인 성공", user.id
        else:
            return False, "사용자 이름 또는 비밀번호가 올바르지 않습니다.", None
    except Exception as e:
        st.error(f"로그인 중 오류 발생: {e}")
        return False, "로그인 중 오류가 발생했습니다.", None
    finally:
        session.close()

# 음식 추가 함수 (식단 관리용)
def add_diet(user_id, meal):
    session = Session_db()
    try:
        new_meal = Meal(
            user_id=user_id,
            name=meal['name'],
            calories=meal.get('calories', 0.0),
            proteins=meal.get('proteins', 0.0),
            carbs=meal.get('carbs', 0.0),
            fats=meal.get('fats', 0.0)
            # date는 자동으로 설정됩니다.
        )
        session.add(new_meal)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        st.error(f"데이터베이스에 저장 중 오류 발생: {e}")
        return False
    finally:
        session.close()

# 수동 식단 추가 함수 (식단 입력용)
def add_manual_meal(user_id, meal):
    session = Session_db()
    try:
        new_manual_meal = ManualMeal(
            user_id=user_id,
            name=meal['name']
            # date는 자동으로 설정됩니다.
        )
        session.add(new_manual_meal)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        st.error(f"데이터베이스에 저장 중 오류 발생: {e}")
        return False
    finally:
        session.close()

# 식단 가져오기 함수 (식단 관리용)
def get_diets(user_id):
    session = Session_db()
    try:
        meals = session.query(Meal).filter_by(user_id=user_id).all()
        return meals
    except Exception as e:
        st.error(f"식단을 불러오는 중 오류 발생: {e}")
        return []
    finally:
        session.close()

# 수동 식단 가져오기 함수 (식단 입력용)
def get_manual_meals(user_id):
    session = Session_db()
    try:
        manual_meals = session.query(ManualMeal).filter_by(user_id=user_id).all()
        return manual_meals
    except Exception as e:
        st.error(f"수동 식단을 불러오는 중 오류 발생: {e}")
        return []
    finally:
        session.close()

# 음식 삭제 함수 (식단 관리용)
def delete_meal(user_id, meal_id):
    session = Session_db()
    try:
        meal = session.query(Meal).filter_by(id=meal_id, user_id=user_id).first()
        if meal:
            session.delete(meal)
            session.commit()
            return True
        else:
            return False
    except Exception as e:
        session.rollback()
        st.error(f"음식 삭제 중 오류 발생: {e}")
        return False
    finally:
        session.close()

# 수동 식단 삭제 함수 (식단 입력용)
def delete_manual_meal(user_id, meal_id):
    session = Session_db()
    try:
        manual_meal = session.query(ManualMeal).filter_by(id=meal_id, user_id=user_id).first()
        if manual_meal:
            session.delete(manual_meal)
            session.commit()
            return True
        else:
            return False
    except Exception as e:
        session.rollback()
        st.error(f"수동 식단 삭제 중 오류 발생: {e}")
        return False
    finally:
        session.close()

# 사용자 가져오기 함수
def get_user(user_id):
    session = Session_db()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        return user
    except Exception as e:
        st.error(f"사용자를 가져오는 중 오류 발생: {e}")
        return None
    finally:
        session.close()

# 비밀번호 검증 함수
def verify_password(stored_password, provided_password):
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password.encode('utf-8'))

# OpenAI API 키 설정
API_KEY = st.secrets["OPENAI_API_KEY"]
openai.api_key = API_KEY

# Chatbot 클래스 정의
class Chatbot:
    def __init__(self, counseling_data, model="gpt-3.5-turbo"):
        self.counseling_data = counseling_data
        self.current_session = [{"role": "system", "content": "You are a helpful counseling assistant."}]
        self.initial_question = "Hello! I am a Chatbot."
        self.model = model

    def get_openai_response(self, conversation):
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=conversation
            )
            return response.choices[0].message["content"]
        except RateLimitError:
            return "현재 서비스 이용량이 초과되었습니다. 잠시 후 다시 시도해주세요."
        except OpenAIError as e:
            return f"오류가 발생했습니다: {e}"

    def chat(self, user_input=None):
        if user_input:
            self.current_session.append({"role": "user", "content": user_input})
        conversation = self.current_session
        response = self.get_openai_response(conversation)
        self.current_session.append({"role": "assistant", "content": response})
        return response

    def provide_feedback(self, statistics_summary):
        self.current_session.append({"role": "system", "content": f"Here is today's nutrition summary: {statistics_summary}"})
        user_input = "오늘 섭취량에 대해 어떻게 생각하나요?"
        self.current_session.append({"role": "user", "content": user_input})
        response = self.get_openai_response(self.current_session)
        self.current_session.append({"role": "assistant", "content": response})
        return response

# 번역기 초기화
translator = Translator()

# 캐시된 번역 함수
@st.cache_data(ttl=86400)  # 24시간 동안 캐시
def translate_to_korean_cached(text, barcode=None):
    session = Session_db()
    try:
        if barcode:
            translation = session.query(ProductTranslation).filter_by(barcode=barcode).first()
            if translation:
                return translation.translated_name

        translation = translator.translate(text, dest='ko').text

        if barcode:
            new_translation = ProductTranslation(barcode=barcode, translated_name=translation)
            session.add(new_translation)
            session.commit()

        return translation
    except Exception as e:
        st.error(f"번역 중 오류 발생: {e}")
        return text  # 번역 실패 시 원본 텍스트 반환
    finally:
        session.close()

@st.cache_data(ttl=86400)  # 24시간 동안 캐시
def translate_to_english_cached(text):
    try:
        translation = translator.translate(text, dest='en').text
        return translation
    except Exception as e:
        st.error(f"영어로 번역 중 오류 발생: {e}")
        return text  # 번역 실패 시 원본 텍스트 반환

# 세션 사용을 통한 성능 향상
session_requests = requests.Session()

# 캐시된 get_api_foods 함수
@st.cache_data(ttl=3600)  # 1시간 동안 캐시
def get_api_foods_cached(page=1, page_size=10):  # 기본 page_size를 10으로 변경
    search_query = "food"
    url = 'https://world.openfoodfacts.org/cgi/search.pl'
    params = {
        'search_terms': search_query,
        'search_simple': 1,
        'action': 'process',
        'json': 1,
        'page': page,
        'page_size': page_size,
        'fields': 'product_name,product_name_KR,code,brands,categories'  # 필요한 필드만 요청
    }
    try:
        start_time = time.time()
        response = session_requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        products = data.get('products', [])
        translated_products = []
        for product in products:
            barcode = product.get('code', '바코드 없음')
            if barcode != '바코드 없음':
                product_name_korean = product.get('product_name_KR')
                if product_name_korean:
                    name = product_name_korean
                else:
                    product_name = product.get('product_name')
                    if (product_name):
                        name = translate_to_korean_cached(product_name, barcode=barcode)
                    else:
                        name = '이름 없음'
            else:
                product_name = product.get('product_name')
                if product_name:
                    name = translate_to_korean_cached(product_name)
                else:
                    name = '이름 없음'
            translated_products.append({
                '제품 이름': name,
                '바코드': barcode,
                '제조사': ", ".join(product.get('brands', '제조사 없음').split(',')),
                '카테고리': ", ".join(product.get('categories', '카테고리 없음').split(','))
            })
        end_time = time.time()
        logger.info(f"get_api_foods_cached 실행 시간: {end_time - start_time}초")
        return translated_products
    except (ChunkedEncodingError, ConnectionError, Timeout) as e:
        logger.error(f"API 요청 중 오류 발생: {e}")
        st.error(f"API 요청 중 오류 발생: {e}")
        return []
    except requests.HTTPError as e:
        logger.error(f"HTTP 오류 발생: {e}")
        st.error(f"HTTP 오류 발생: {e}")
        return []
    except Exception as e:
        logger.error(f"예기치 않은 오류 발생: {e}")
        st.error(f"예기치 않은 오류 발생: {e}")
        return []

# 음식 검색 함수 (식단 관리용) - 재시도 로직 포함
def search_food(query, max_retries=3, backoff_factor=0.3):
    """
    주어진 검색어를 영어로 번역한 후 OpenFoodFacts API에 검색 요청을 보냅니다.

    Args:
        query (str): 검색어 (한국어).
        max_retries (int): 최대 재시도 횟수.
        backoff_factor (float): 재시도 대기 시간 계수.

    Returns:
        list: 검색 결과 음식 목록.
    """
    # 검색어를 영어로 번역
    translated_query = translate_to_english_cached(query)
    if translated_query != query:
        st.info(f"검색어가 영어로 번역되었습니다: {translated_query}")

    url = 'https://world.openfoodfacts.org/cgi/search.pl'
    params = {
        'search_terms': translated_query,
        'search_simple': 1,
        'action': 'process',
        'json': 1,
        'fields': 'product_name,product_name_KR,code,brands,categories'  # 필요한 필드만 요청
    }

    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = session_requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            end_time = time.time()
            logger.info(f"search_food API 요청 시간: {end_time - start_time}초")
            return data.get('products', [])
        except (ChunkedEncodingError, ConnectionError, Timeout) as e:
            logger.error(f"API 요청 중 오류 발생: {e}. 재시도 {attempt + 1}/{max_retries} 중...")
            st.error(f"API 요청 중 오류 발생: {e}. 재시도 {attempt + 1}/{max_retries} 중...")
            time.sleep(backoff_factor * (2 ** attempt))  # 지수 백오프
        except requests.HTTPError as e:
            logger.error(f"HTTP 오류 발생: {e}")
            st.error(f"HTTP 오류 발생: {e}")
            break
        except Exception as e:
            logger.error(f"예기치 않은 오류 발생: {e}")
            st.error(f"예기치 않은 오류 발생: {e}")
            break
    st.error("음식 검색에 실패했습니다. 나중에 다시 시도해주세요.")
    return []

# 영양 정보 가져오기 함수 (식단 관리용)
def get_nutrition_info(barcode):
    url = f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json'
    try:
        response = session_requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('status') == 1:
            product = data.get('product', {})
            nutriments = product.get('nutriments', {})
            return {
                'name': product.get('product_name', '이름 없음'),
                'calories': float(nutriments.get('energy-kcal_100g', 0)),
                'proteins': float(nutriments.get('proteins_100g', 0)),
                'carbs': float(nutriments.get('carbohydrates_100g', 0)),
                'fats': float(nutriments.get('fat_100g', 0)),
            }
    except (ChunkedEncodingError, ConnectionError, Timeout) as e:
        logger.error(f"영양 정보 요청 중 오류 발생: {e}")
        st.error(f"영양 정보 요청 중 오류 발생: {e}")
    except requests.HTTPError as e:
        logger.error(f"HTTP 오류 발생: {e}")
        st.error(f"HTTP 오류 발생: {e}")
    except Exception as e:
        logger.error(f"예기치 않은 오류 발생: {e}")
        st.error(f"예기치 않은 오류 발생: {e}")
    return {}

# 로그인 처리 함수
def handle_login(username, password):
    success, message, user_id = login_user(username, password)
    if success:
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.user_id = user_id
        st.session_state.page = 'main'
        st.success(message)
        st.stop()  # 페이지 새로 고침 대신 중지
    else:
        st.error(message)

# 회원가입 처리 함수
def handle_signup(username, password):
    success = create_user(username, password)
    if success:
        st.success("회원가입이 완료되었습니다. 로그인 해주세요.")
        st.session_state.page = 'login'
        st.rerun()
    else:
        st.error("이미 존재하는 사용자 이름입니다.")

# 로그인 폼
def login_form():
    st.header("로그인")
    with st.form(key='login_form'):
        username = st.text_input("사용자 이름")
        password = st.text_input("비밀번호", type="password")
        submit_button = st.form_submit_button("로그인")
        if submit_button:
            if username.strip() == "" or password.strip() == "":
                st.error("모든 필드를 입력해주세요.")
            else:
                handle_login(username, password)
    st.markdown("**회원가입이 필요하신가요?**")
    if st.button("회원가입"):
        st.session_state.page = 'signup'
        st.rerun()

# 회원가입 페이지
def signup_page():
    st.header("회원가입")
    with st.form(key='signup_form'):
        username = st.text_input("사용자 이름")
        password = st.text_input("비밀번호", type="password")
        confirm_password = st.text_input("비밀번호 확인", type="password")
        submit_button = st.form_submit_button("회원가입")
        if submit_button:
            if username.strip() == "" or password.strip() == "" or confirm_password.strip() == "":
                st.error("모든 필드를 입력해주세요.")
            elif password != confirm_password:
                st.error("비밀번호가 일치하지 않습니다.")
            else:
                handle_signup(username, password)

# 세션 상태 초기화 함수
def reset_session_state():
    # 사용자 관련 상태는 유지하고, 다른 상태만 초기화
    keys_to_remove = [key for key in st.session_state.keys() if key not in ['logged_in', 'username', 'user_id', 'page']]
    for key in keys_to_remove:
        del st.session_state[key]

# 데이터베이스 테이블 초기화 함수
def reset_database_tables():
    session = Session_db()
    try:
        # 특정 사용자에 대한 모든 Meal 데이터 삭제
        deleted_meals = session.query(Meal).filter_by(user_id=st.session_state.user_id).delete()
        # 특정 사용자에 대한 모든 ManualMeal 데이터 삭제
        deleted_manual_meals = session.query(ManualMeal).filter_by(user_id=st.session_state.user_id).delete()
        # 모든 ProductTranslation 데이터 삭제 (필요에 따라 조건 추가 가능)
        deleted_translations = session.query(ProductTranslation).delete()
        session.commit()
        st.success("모든 식단 데이터가 삭제되었습니다.")
        st.rerun()
    except Exception as e:
        session.rollback()
        st.error(f"데이터 삭제 중 오류가 발생했습니다: {e}")
    finally:
        session.close()

# 데이터 백업 함수 (JSON 형식만 지원)
def backup_data(user_id, format='json'):
    session = Session_db()
    try:
        # Meals 데이터
        meals = session.query(Meal).filter_by(user_id=user_id).all()
        meals_data = [{
            'id': meal.id,
            'name': meal.name,
            'calories': meal.calories,
            'proteins': meal.proteins,
            'carbs': meal.carbs,
            'fats': meal.fats,
            'date': meal.date.strftime('%Y-%m-%d %H:%M:%S')
        } for meal in meals]

        # ManualMeals 데이터
        manual_meals = session.query(ManualMeal).filter_by(user_id=user_id).all()
        manual_meals_data = [{
            'id': manual_meal.id,
            'name': manual_meal.name,
            'date': manual_meal.date.strftime('%Y-%m-%d %H:%M:%S')
        } for manual_meal in manual_meals]

        backup = {
            'meals': meals_data,
            'manual_meals': manual_meals_data
        }

        if format == 'json':
            backup_json = json.dumps(backup, ensure_ascii=False, indent=4)
            return backup_json.encode('utf-8')
    except Exception as e:
        st.error(f"백업 중 오류 발생: {e}")
        return None
    finally:
        session.close()

# 데이터 복원 함수 (JSON 형식만 지원)
def restore_data(user_id, file, format='json'):
    session = Session_db()
    try:
        if format == 'json':
            data = json.load(io.StringIO(file.getvalue().decode("utf-8")))
        else:
            st.error("지원하지 않는 파일 형식입니다.")
            return False

        # 복원할 데이터
        meals = data.get('meals', [])
        manual_meals = data.get('manual_meals', [])

        # Meals 데이터 삽입
        for meal in meals:
            new_meal = Meal(
                user_id=user_id,
                name=meal['name'],
                calories=meal.get('calories', 0.0),
                proteins=meal.get('proteins', 0.0),
                carbs=meal.get('carbs', 0.0),
                fats=meal.get('fats', 0.0),
                date=datetime.strptime(meal['date'], '%Y-%m-%d %H:%M:%S')
            )
            session.add(new_meal)

        # ManualMeals 데이터 삽입
        for manual_meal in manual_meals:
            new_manual_meal = ManualMeal(
                user_id=user_id,
                name=manual_meal['name'],
                date=datetime.strptime(manual_meal['date'], '%Y-%m-%d %H:%M:%S')
            )
            session.add(new_manual_meal)

        session.commit()
        st.success("데이터 복원이 완료되었습니다.")
        st.rerun()
        return True
    except json.JSONDecodeError:
        st.error("업로드한 파일이 유효한 JSON 파일이 아닙니다.")
        return False
    except Exception as e:
        session.rollback()
        st.error(f"복원 중 오류 발생: {e}")
        return False
    finally:
        session.close()

# 음식 삭제 UI (식단 입력과 관리에서 별도로 구현)
def delete_meal_ui(meals_sorted):
    st.markdown("---")
    st.subheader("음식 삭제")

    # 삭제할 음식 ID 선택
    meal_ids = [meal.id for meal in meals_sorted]
    meal_names = [meal.name for meal in meals_sorted]
    meal_options = [f"ID {id_} - {name}" for id_, name in zip(meal_ids, meal_names)]
    selected_meal = st.selectbox("삭제할 음식을 선택하세요:", options=meal_options, key='selected_meal_delete')

    if selected_meal:
        # 선택된 문자열에서 ID 추출
        try:
            selected_id = int(selected_meal.split(" - ")[0].replace("ID ", ""))
        except ValueError:
            st.error("잘못된 선택입니다.")
            return

        if st.button("삭제 실행"):
            success = delete_meal(st.session_state.user_id, selected_id)
            if success:
                st.success(f"ID {selected_id} 음식이 삭제되었습니다.")
                # 삭제 후 페이지를 새로 고침하거나 상태를 업데이트할 필요가 있을 수 있습니다.
                st.rerun()
            else:
                st.error("해당 ID의 음식을 찾을 수 없습니다.")

# 데이터 백업 및 복원 UI 함수 (사이드바로 이동, JSON만 지원)
def backup_restore_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.header("📦 데이터 백업 및 복원")

    # 데이터 백업 섹션
    st.sidebar.markdown("### 데이터 백업")
    backup_format = "JSON"  # JSON만 지원하므로 고정
    st.sidebar.write(f"**백업 형식:** {backup_format}")
    if st.sidebar.button("데이터 백업 실행"):
        backup_bytes = backup_data(st.session_state.user_id, format='json')
        if backup_bytes:
            # 현재 날짜와 시간을 가져와서 파일 이름에 추가
            current_datetime = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_name = f"backup_{current_datetime}.json"
            st.sidebar.download_button(
                label="백업 파일 다운로드",
                data=backup_bytes,
                file_name=file_name,
                mime="application/json"
            )
            st.sidebar.success("데이터 백업이 완료되었습니다.")

    st.sidebar.markdown("---")

    # 데이터 복원 섹션
    st.sidebar.markdown("### 데이터 복원")
    restore_format = "JSON"  # JSON만 지원하므로 고정
    st.sidebar.write(f"**복원 형식:** {restore_format}")
    uploaded_file = st.sidebar.file_uploader("복원할 백업 파일을 업로드하세요.", type=["json"], key='uploaded_file_sidebar')

    if uploaded_file:
        if st.sidebar.button("데이터 복원 실행"):
            success = restore_data(st.session_state.user_id, uploaded_file, format='json')
            if success:
                st.sidebar.success("데이터 복원이 완료되었습니다.")
            else:
                st.sidebar.error("데이터 복원에 실패했습니다.")

# 기존 식단 관리 페이지를 업데이트하여 섭취 기록을 DataFrame으로 표시하고 삭제 기능 추가
def manage_meals():
    # user_id가 존재하는지 확인
    if not st.session_state.get('user_id'):
        st.error("사용자 정보가 누락되었습니다. 다시 로그인 해주세요.")
        return

    st.header("건강 식단 관리 플랫폼")
    st.subheader("API를 통한 음식 검색 및 추가")

    # API를 통한 음식 검색 및 추가 섹션
    with st.form(key='api_search_form'):
        search_query = st.text_input("음식 이름을 입력하고 검색하세요:")
        search_submit = st.form_submit_button("검색")
        
        if search_submit:
            if search_query.strip() == "":
                st.error("검색어를 입력해주세요.")
            else:
                with st.spinner("음식 검색 중..."):
                    products = search_food(search_query.strip())
                    if products:
                        # 음식 이름과 관련 정보를 추출
                        products_filtered = [
                            {
                                '제품 이름': product.get('product_name_KR') or translate_to_korean_cached(product.get('product_name', '이름 없음'), barcode=product.get('code', None)),
                                '바코드': product.get('code', '바코드 없음'),
                                '제조사': ", ".join(product.get('brands', '제조사 없음').split(',')),
                                '카테고리': ", ".join(product.get('categories', '카테고리 없음').split(','))
                            }
                            for product in products if product.get('product_name') or product.get('product_name_KR')
                        ]
                        if products_filtered:
                            # 검색 결과를 세션 상태에 저장
                            st.session_state['search_results_manage'] = products_filtered
                            st.success(f"{len(products_filtered)}개의 검색 결과를 찾았습니다.")
                        else:
                            st.info("검색 결과에 음식 이름이 없습니다.")
                    else:
                        st.info("검색 결과가 없습니다.")

    # 검색 결과를 표시하지 않고 선택 기능만 유지
    if 'search_results_manage' in st.session_state and st.session_state['search_results_manage']:
        st.subheader("검색 결과에서 음식을 선택하여 추가하세요.")

        products = st.session_state['search_results_manage']
        product_names = [product['제품 이름'] for product in products]
        selected_product = st.selectbox("검색 결과에서 선택하세요:", options=product_names, key='selected_product_manage')

        if selected_product:
            # 선택된 제품의 정보 가져오기
            selected_product_info = next((item for item in products if item["제품 이름"] == selected_product), None)
            if selected_product_info:
                barcode = selected_product_info.get('바코드', '')
                
                if (barcode and barcode != '바코드 없음'):
                    nutrition = get_nutrition_info(barcode)
                    if nutrition:
                        st.write(f"**제품 이름:** {nutrition.get('name', '이름 없음')}")
                        st.write(f"**칼로리:** {nutrition.get('calories', 0)} kcal")
                        st.write(f"**단백질:** {nutrition.get('proteins', 0)} g")
                        st.write(f"**탄수화물:** {nutrition.get('carbs', 0)} g")
                        st.write(f"**지방:** {nutrition.get('fats', 0)} g")
                        st.session_state['selected_nutrition_manage'] = nutrition
                    else:
                        st.error("영양 정보를 가져올 수 없습니다.")
                else:
                    st.error("선택한 제품의 바코드를 찾을 수 없습니다.")

    # 선택된 영양 정보를 저장하는 섹션
    if st.session_state.get('selected_nutrition_manage'):
        if st.button("저장"):
            meal = st.session_state['selected_nutrition_manage']
            success = add_diet(st.session_state.user_id, meal)
            if success:
                st.success(f"{meal.get('name', '이름 없음')}이(가) 저장되었습니다.")
                # 저장 후 선택된 영양 정보와 검색 결과를 초기화
                st.session_state['selected_nutrition_manage'] = None
                st.session_state['search_results_manage'] = []
                st.rerun()
            else:
                st.error("음식 저장에 실패했습니다.")

    st.markdown("---")
    st.subheader("전체 API 음식 보기")

    # 전체 API 음식 보기 버튼
    if st.button("전체 API 음식 보기"):
        st.session_state.api_foods_page = 1  # 페이지 초기화
        st.rerun()

    # 페이지 크기 조절 슬라이더 추가
    st.sidebar.markdown("---")
    st.sidebar.subheader("페이지 설정")
    st.session_state.api_foods_page_size = st.sidebar.slider(
        "페이지 당 음식 수",
        min_value=10,
        max_value=100,
        value=10,  # 기본 값을 10으로 변경
        step=10,
        key='api_foods_page_size_slider'
    )

    # 현재 페이지의 API 음식 가져오기
    with st.spinner("API 음식 불러오는 중..."):
        api_foods = get_api_foods_cached(page=st.session_state.api_foods_page, page_size=st.session_state.api_foods_page_size)

    if api_foods:
        st.subheader(f"전체 API 음식 목록 (페이지 {st.session_state.api_foods_page})")
        df_api = pd.DataFrame(api_foods)
        st.dataframe(df_api)

        # 페이지네이션 버튼
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("이전 페이지", key='prev_page'):
                if st.session_state.api_foods_page > 1:
                    st.session_state.api_foods_page -= 1
                    st.rerun()
        with col3:
            if st.button("다음 페이지", key='next_page'):
                st.session_state.api_foods_page += 1
                st.rerun()
    else:
        st.info("더 이상 표시할 API 음식이 없습니다.")

    st.markdown("---")
    st.subheader("섭취 기록 관리")

    # 섭취 기록 보기
    st.header("섭취 기록")
    
    # 정렬 기준 선택
    sort_options = {
        "ID": Meal.id,
        "이름": Meal.name,
        "칼로리": Meal.calories,
        "단백질": Meal.proteins,
        "탄수화물": Meal.carbs,
        "지방": Meal.fats
    }
    sort_by = st.selectbox("정렬 기준 선택", options=list(sort_options.keys()), key='sort_by_manage')
    sort_order = st.radio("정렬 순서", options=["오름차순", "내림차순"], key='sort_order_manage')

    # 데이터베이스 세션 설정
    session_db = Session_db()

    # 검색어 입력
    search_query_record = st.text_input("검색할 음식 이름을 입력하세요:", key='search_query_record')

    # 선택된 기준에 따라 정렬 및 검색어에 따라 필터링
    query = session_db.query(Meal).filter_by(user_id=st.session_state.user_id)
    if search_query_record:
        query = query.filter(Meal.name.contains(search_query_record))

    if sort_order == "오름차순":
        meals_sorted = query.order_by(asc(sort_options[sort_by])).all()
    else:
        meals_sorted = query.order_by(desc(sort_options[sort_by])).all()

    if meals_sorted:
        # 데이터프레임 생성
        data = {
            'ID': [meal.id for meal in meals_sorted],
            '이름': [meal.name for meal in meals_sorted],
            '칼로리': [meal.calories for meal in meals_sorted],
            '단백질 (g)': [meal.proteins for meal in meals_sorted],
            '탄수화물 (g)': [meal.carbs for meal in meals_sorted],
            '지방 (g)': [meal.fats for meal in meals_sorted]
            # '날짜': [meal.date.strftime('%Y-%m-%d %H:%M:%S') for meal in meals_sorted]  # 삭제
        }
        df = pd.DataFrame(data)
        st.dataframe(df)

        # 삭제할 음식 선택
        delete_meal_ui(meals_sorted)

    else:
        st.info("섭취 기록이 없습니다.")

    session_db.close()

# 새로운 식단 입력 페이지
def meal_input_page():
    # user_id가 존재하는지 확인
    if not st.session_state.get('user_id'):
        st.error("사용자 정보가 누락되었습니다. 다시 로그인 해주세요.")
        return

    st.header("식단 입력")

    # 음식 입력 폼
    with st.form(key='manual_meal_form'):
        st.subheader("음식 추가")
        meal_name = st.text_input("음식 이름", key='meal_name_input')
        submit_meal = st.form_submit_button("추가")
        
        if submit_meal:
            if meal_name.strip() == "":
                st.error("음식 이름을 입력해주세요.")
            else:
                manual_meal = {
                    'name': meal_name.strip()
                }
                success = add_manual_meal(st.session_state.user_id, manual_meal)
                if success:
                    st.success(f"{manual_meal.get('name')}이(가) 저장되었습니다.")
                    st.rerun()
                else:
                    st.error("음식 저장에 실패했습니다.")

    st.markdown("---")
    st.subheader("저장된 식단")

    # 저장된 수동 식단 표시 및 삭제
    manual_meals = get_manual_meals(st.session_state.user_id)
    if manual_meals:
        for manual_meal in manual_meals:
            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"### **이름:** {manual_meal.name}")
                with col2:
                    delete_button = st.button("삭제", key=f"delete_manual_{manual_meal.id}")
                    if delete_button:
                        success = delete_manual_meal(st.session_state.user_id, manual_meal.id)
                        if success:
                            st.success(f"{manual_meal.name} 음식이 삭제되었습니다.")
                            st.rerun()
                        else:
                            st.error("해당 음식을 찾을 수 없습니다.")
    else:
        st.info("저장된 식단이 없습니다.")

# 하루 통계 및 챗봇 피드백
def show_statistics_with_chatbot(chatbot):
    # 목표 설정 (예시 값)
    target_carbs = 130
    target_proteins = 60
    target_fats = 51
    total_calories = 2200

    # user_id가 존재하는지 확인
    if not st.session_state.get('user_id'):
        st.error("사용자 정보가 누락되었습니다. 다시 로그인 해주세요.")
        return

    # 식단 관리용 데이터
    meals = get_diets(st.session_state.user_id)
    current_carbs = sum([meal.carbs or 0 for meal in meals])
    current_proteins = sum([meal.proteins or 0 for meal in meals])
    current_fats = sum([meal.fats or 0 for meal in meals])
    current_calories = sum([meal.calories or 0 for meal in meals])

    # 통계 요약에서 수동 식단 개수 제거
    statistics_summary = (
        f"현재 칼로리는 {current_calories} kcal입니다. 목표는 {total_calories} kcal입니다.\n"
        f"단백질: {current_proteins}g / {target_proteins}g\n"
        f"탄수화물: {current_carbs}g / {target_carbs}g\n"
        f"지방: {current_fats}g / {target_fats}g"
    )

    st.title("하루 통계")
    st.metric(label="칼로리", value=f"{current_calories} / {total_calories} kcal")

    st.write("탄수화물")
    progress_carbs = current_carbs / target_carbs if target_carbs else 0
    st.progress(progress_carbs if progress_carbs <= 1 else 1)
    st.write(f"{current_carbs}g / {target_carbs}g")

    st.write("단백질")
    progress_proteins = current_proteins / target_proteins if target_proteins else 0
    st.progress(progress_proteins if progress_proteins <= 1 else 1)
    st.write(f"{current_proteins}g / {target_proteins}g")

    st.write("지방")
    progress_fats = current_fats / target_fats if target_fats else 0
    st.progress(progress_fats if progress_fats <= 1 else 1)
    st.write(f"{current_fats}g / {target_fats}g")

    st.markdown("---")

    st.chat_message("assistant").write("다음은 오늘의 통계입니다:")
    st.chat_message("assistant").write(statistics_summary)

    response = chatbot.provide_feedback(statistics_summary)
    st.chat_message("assistant").write(response)

# 챗봇 탭
def chatbot_tab(chatbot):
    st.header("🛜 영양 상담 챗봇 🤖")
    st.write("챗봇과 대화를 통해 영양 정보에 대해 물어보세요!")

    if "chatbot_messages" not in st.session_state:
        st.session_state.chatbot_messages = [
            {"role": "assistant", "content": "안녕하세요! 저는 영양 상담 챗봇입니다. 무엇을 도와드릴까요?"}
        ]

    for msg in st.session_state.chatbot_messages:
        st.chat_message(msg["role"]).write(msg["content"])

    user_input = st.chat_input("질문을 입력하세요")
    if user_input:
        st.session_state.chatbot_messages.append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)

        response = chatbot.chat(user_input=user_input)
        st.session_state.chatbot_messages.append({"role": "assistant", "content": response})
        st.chat_message("assistant").write(response)

# 로그아웃 함수
def logout():
    st.session_state.logged_in = False
    st.session_state.username = ''
    st.session_state.user_id = None
    st.session_state.page = 'start'
    st.session_state.chatbot_messages = []
    st.sidebar.success("로그아웃 되었습니다.")
    st.rerun()

# 시작 페이지
def show_start_page():
    st.markdown(
        """
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh;">
            <h1 style="text-align: center;">🍔영양갱🍲</h1>
            <h2 style="text-align: center;">당신의 식단을 책임져 드립니다.</h2>
        </div>
        """,
        unsafe_allow_html=True
    )
    if st.button("시작"):
        st.session_state['page'] = 'login'
        st.rerun()

# 메인 애플리케이션 함수
def main_app(chatbot):
    st.sidebar.header(f"{st.session_state.username}님")
    # 메뉴 선택에서 "식단 입력"을 먼저, "식단 관리"를 나중으로 변경
    choice = st.sidebar.selectbox("메뉴 선택", ["식단 입력", "식단 관리", "하루 통계", "챗봇", "로그아웃"])

    st.sidebar.markdown("---")
    st.sidebar.header("⚠️ 데이터 초기화")

    # 초기화 확인 상태를 관리
    if 'confirm_reset' not in st.session_state:
        st.session_state.confirm_reset = False

    if not st.session_state.confirm_reset:
        if st.sidebar.button("데이터 초기화"):
            st.session_state.confirm_reset = True
            st.sidebar.write("⚠️ 모든 식단 데이터를 초기화하시겠습니까?")
    else:
        st.sidebar.warning("⚠️ 모든 식단 데이터를 초기화하려면 아래 버튼을 클릭하세요. 이 작업은 되돌릴 수 없습니다.")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.sidebar.button("초기화 취소"):
                st.session_state.confirm_reset = False
                st.sidebar.write("초기화가 취소되었습니다.")
        with col2:
            if st.sidebar.button("초기화 실행"):
                reset_session_state()
                reset_database_tables()  # 모든 식단 데이터 삭제
                st.sidebar.success("모든 식단 데이터가 초기화되었습니다.")
                st.rerun()

    # 사이드바에 백업 및 복원 UI 추가
    backup_restore_sidebar()

    if choice == "식단 관리":
        manage_meals()
    elif choice == "식단 입력":
        meal_input_page()
    elif choice == "하루 통계":
        show_statistics_with_chatbot(chatbot)
    elif choice == "챗봇":
        chatbot_tab(chatbot)
    elif choice == "로그아웃":
        logout()

# 메인 함수
def main():
    initialize_app()  # 세션 상태 초기화
    counseling_data = []
    chatbot = Chatbot(counseling_data)

    if not st.session_state.get('logged_in', False):
        if st.session_state.get('page', 'start') == 'login':
            login_form()
        elif st.session_state.get('page') == 'signup':
            signup_page()
        elif st.session_state.get('page') == 'start':
            show_start_page()
    else:
        main_app(chatbot)

# 초기화 함수
def initialize_app():
    initialize_database()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'page' not in st.session_state:
        st.session_state.page = 'start'
    if 'username' not in st.session_state:
        st.session_state.username = ''
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'selected_nutrition_manage' not in st.session_state:
        st.session_state.selected_nutrition_manage = None
    if 'selected_nutrition_input' not in st.session_state:
        st.session_state.selected_nutrition_input = None
    if 'search_results_manage' not in st.session_state:
        st.session_state.search_results_manage = []
    if 'api_foods_page' not in st.session_state:
        st.session_state.api_foods_page = 1
    if 'api_foods_page_size' not in st.session_state:
        st.session_state.api_foods_page_size = 10  # 페이지 당 음식 수를 10으로
    if 'chatbot_messages' not in st.session_state:
        st.session_state.chatbot_messages = []

# 애플리케이션 실행
main()

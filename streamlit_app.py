import streamlit as st
import pandas as pd
import requests
import pydeck as pdk
import time

# -----------------------------
# 0. 기본 설정 & 상수
# -----------------------------
st.set_page_config(page_title="Berlin Trip Planner", layout="wide")

GOOGLE_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
FX_API_BASE_URL = st.secrets.get("FX_API_BASE_URL", "https://api.frankfurter.app/latest")
HOME_CURRENCY = st.secrets.get("HOME_CURRENCY", "KRW")

BERLIN_CENTER = {"lat": 52.5200, "lon": 13.4050}


# -----------------------------
# 1. 유틸 함수들
# -----------------------------
@st.cache_data(show_spinner=False)
def get_exchange_rate(base="EUR", target=HOME_CURRENCY):
    """EUR -> KRW 같은 환율 가져오기 (단순 예시)"""
    try:
        url = f"{FX_API_BASE_URL}?from={base}&to={target}"
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        rate = data["rates"][target]
        return rate
    except Exception as e:
        st.error(f"환율 API 에러: {e}")
        return None


@st.cache_data(show_spinner=False)
def get_weather_berlin():
    """
    Google Maps Weather API - currentConditions 사용해서
    베를린 현재 날씨 가져오기.
    https://weather.googleapis.com/v1/currentConditions:lookup 
    """
    try:
        url = "https://weather.googleapis.com/v1/currentConditions:lookup"
        params = {
            "key": GOOGLE_API_KEY,
            "location.latitude": BERLIN_CENTER["lat"],
            "location.longitude": BERLIN_CENTER["lon"],
            "unitsSystem": "METRIC",  # 섭씨 기준
        }
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        # currentConditions 객체 하나가 온다고 가정
        current = data.get("currentConditions", {})
        return current, data  # 요약용 + 원본 JSON 같이 반환
    except Exception as e:
        st.error(f"날씨 API 에러: {e}")
        return None, None


@st.cache_data(show_spinner=False)
def google_places_text_search(query, api_key=GOOGLE_API_KEY):
    """
    Google Places Text Search API 호출.
    query 예: 'restaurants in Berlin, Germany'
    """
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "key": api_key,
    }
    all_results = []

    while True:
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        results = data.get("results", [])
        all_results.extend(results)

        next_token = data.get("next_page_token")
        if not next_token:
            break

        # 다음 페이지 토큰 활성화까지 약간 딜레이 필요
        time.sleep(2)
        params = {"pagetoken": next_token, "key": api_key}

    return all_results


def places_to_df(places, category_label):
    """Google Places 결과를 위도/경도 DataFrame으로 변환"""
    rows = []
    for p in places:
        loc = p["geometry"]["location"]
        rating = p.get("rating", 0)
        rows.append(
            {
                "name": p.get("name"),
                "lat": loc["lat"],
                "lon": loc["lng"],
                "rating": rating,
                "address": p.get("formatted_address"),
                "category": category_label,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def geocode_location(location_name):
    """
    지명(예: 범죄 데이터 Location)을 lat/lon으로 지오코딩.
    Google Geocoding API 사용.
    """
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": f"{location_name}, Berlin, Germany",
        "key": GOOGLE_API_KEY,
    }
    res = requests.get(url, params=params)
    res.raise_for_status()
    data = res.json()
    if data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    else:
        return None, None


@st.cache_data(show_spinner=False)
def load_and_prepare_crime_data():
    """
    Berlin_crimes.csv 사용해서
    - 최신 Year만 사용
    - Location을 지오코딩해서 lat/lon 추가
    - crime_total, risk_norm(0~1) 계산
    """
    df = pd.read_csv("Berlin_crimes.csv")

    # Year, District, Code, Location 제외 나머지를 범죄 건수로 보고 합산
    crime_columns = [
        c for c in df.columns
        if c not in ["Year", "District", "Code", "Location"]
    ]
    df["crime_total"] = df[crime_columns].sum(axis=1)

    latest_year = df["Year"].max()
    df_latest = df[df["Year"] == latest_year].copy()

    lats = []
    lons = []
    for loc_name in df_latest["Location"]:
        lat, lon = geocode_location(loc_name)
        lats.append(lat)
        lons.append(lon)

    df_latest["lat"] = lats
    df_latest["lon"] = lons

    # 지오코딩 실패한 행 제거
    df_latest = df_latest.dropna(subset=["lat", "lon"])

    # 범죄 위험도 정규화 (0~1)
    max_crime = df_latest["crime_total"].max()
    if max_crime > 0:
        df_latest["risk_norm"] = df_latest["crime_total"] / max_crime
    else:
        df_latest["risk_norm"] = 0.0

    return df_latest


# -----------------------------
# 2. 사이드바 & 페이지 선택
# -----------------------------
st.sidebar.title("Berlin Trip Planner")
page = st.sidebar.radio("페이지 선택", ["환율 & 날씨", "지도"])


# -----------------------------
# 3. 환율 & 날씨 페이지
# -----------------------------
if page == "환율 & 날씨":
    st.title("베를린 여행 준비: 환율 & 날씨")

    # 환율
    st.subheader("환율 정보")
    rate = get_exchange_rate("EUR", HOME_CURRENCY)
    if rate:
        st.write(f"1 EUR ≈ **{rate:.2f} {HOME_CURRENCY}**")
    else:
        st.write("환율 정보를 불러올 수 없습니다 😢")

    # 날씨 (Google Weather API)
    st.subheader("베를린 현재 날씨 (Google Weather API)")

    weather, weather_raw = get_weather_berlin()
    if weather:
        # temperature, apparentTemperature, relativeHumidity 정도만 사용
        temp = weather.get("temperature")
        feels = weather.get("apparentTemperature")
        humidity = weather.get("relativeHumidity")
        # 설명 텍스트 필드는 실제 응답 구조 보고 조정 필요
        # (conditionCode, weatherCondition 등)
        condition_code = weather.get("weatherCondition", {}).get("text") \
            if isinstance(weather.get("weatherCondition"), dict) else None

        if condition_code:
            st.write(f"날씨: **{condition_code}**")
        st.write(f"현재 기온: **{temp}°C**")
        if feels is not None:
            st.write(f"체감 기온: **{feels}°C**")
        if humidity is not None:
            st.write(f"습도: **{humidity}%**")

        with st.expander("원시 날씨 JSON 보기 (필드 구조 확인용)"):
            st.json(weather_raw)
    else:
        st.write("날씨 정보를 불러올 수 없습니다 😢")


# -----------------------------
# 4. 지도 페이지
# -----------------------------
else:
    st.title("베를린 여행 지도 (맛집/숙소/관광지 + 범죄 히트맵)")

    # --- 유저가 직접 추가한 장소를 저장하기 위한 session_state ---
    if "user_places" not in st.session_state:
        st.session_state["user_places"] = []

    with st.sidebar.expander("지도 옵션", expanded=True):
        show_restaurants = st.checkbox("음식점 보기", value=True)
        show_hotels = st.checkbox("숙박시설 보기", value=True)
        show_attractions = st.checkbox("관광지 보기", value=True)
        show_crime = st.checkbox("범죄 위험도 히트맵 보기", value=True)

    st.markdown("### 1) 구글 맵에서 베를린 장소 가져오기 (평점 4.5 이상 음식점)")

    if st.button("데이터 불러오기 / 새로고침"):
        with st.spinner("Google Places 에서 장소를 불러오는 중입니다..."):
            # 음식점 (rating 4.5 이상 필터)
            places_rest = google_places_text_search("restaurants in Berlin, Germany")
            df_rest = places_to_df(places_rest, "restaurant")
            df_rest = df_rest[df_rest["rating"] >= 4.5]

            # 숙박시설
            places_hotels = google_places_text_search("hotels in Berlin, Germany")
            df_hotels = places_to_df(places_hotels, "hotel")

            # 관광지
            places_attr = google_places_text_search("tourist attractions in Berlin, Germany")
            df_attr = places_to_df(places_attr, "attraction")

            st.session_state["df_rest"] = df_rest
            st.session_state["df_hotels"] = df_hotels
            st.session_state["df_attr"] = df_attr

            st.success("장소 데이터를 불러왔습니다!")

    # session_state 에서 데이터 가져오기
    df_rest = st.session_state.get("df_rest", pd.DataFrame())
    df_hotels = st.session_state.get("df_hotels", pd.DataFrame())
    df_attr = st.session_state.get("df_attr", pd.DataFrame())

    # 간단한 표로 확인
    with st.expander("가져온 데이터 미리보기"):
        st.write("🍽 음식점 (rating 4.5+)", df_rest.head())
        st.write("🏨 숙박시설", df_hotels.head())
        st.write("🎡 관광지", df_attr.head())

    st.markdown("### 2) 나만의 장소 추가하기 (주소 직접 입력)")

    with st.form("user_place_form"):
        place_name = st.text_input("장소 이름 (예: 나만의 맛집)")
        place_category = st.selectbox("카테고리", ["restaurant", "hotel", "attraction"])
        place_address = st.text_input("주소 (영어로 입력하면 지오코딩이 잘 됩니다)")
        submitted = st.form_submit_button("지도에 추가")

        if submitted and place_name and place_address:
            try:
                url = "https://maps.googleapis.com/maps/api/geocode/json"
                params = {
                    "address": place_address,
                    "key": GOOGLE_API_KEY,
                }
                res = requests.get(url, params=params)
                res.raise_for_status()
                data = res.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    new_place = {
                        "name": place_name,
                        "lat": loc["lat"],
                        "lon": loc["lng"],
                        "rating": None,
                        "address": place_address,
                        "category": place_category,
                    }
                    st.session_state["user_places"].append(new_place)
                    st.success("나만의 장소가 지도에 추가되었습니다!")
                else:
                    st.error("지오코딩에 실패했습니다. 주소를 다시 확인해주세요.")
            except Exception as e:
                st.error(f"지오코딩 에러: {e}")

    user_places_df = pd.DataFrame(st.session_state["user_places"])

    # -----------------------------
    # 3) 범죄 데이터 준비 (히트맵용)
    # -----------------------------
    crime_df = load_and_prepare_crime_data()

    with st.expander("범죄 데이터 미리보기"):
        st.write(crime_df.head())

    # -----------------------------
    # 4) pydeck 레이어 구성
    # -----------------------------
    layers = []

    # 음식점 레이어
    if show_restaurants and not df_rest.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_rest,
                get_position=["lon", "lat"],
                get_radius=50,
                get_fill_color=[0, 0, 255, 160],  # 파란색
                pickable=True,
            )
        )

    # 숙박시설 레이어
    if show_hotels and not df_hotels.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_hotels,
                get_position=["lon", "lat"],
                get_radius=60,
                get_fill_color=[255, 165, 0, 160],  # 주황색
                pickable=True,
            )
        )

    # 관광지 레이어
    if show_attractions and not df_attr.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=df_attr,
                get_position=["lon", "lat"],
                get_radius=70,
                get_fill_color=[0, 255, 255, 160],  # 청록색
                pickable=True,
            )
        )

    # 유저 추가 장소 레이어
    if not user_places_df.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=user_places_df,
                get_position=["lon", "lat"],
                get_radius=80,
                get_fill_color=[255, 0, 255, 200],  # 보라색
                pickable=True,
            )
        )

    # 🔥 범죄 히트맵 레이어 (HeatmapLayer)
    if show_crime and not crime_df.empty:
        layers.append(
            pdk.Layer(
                "HeatmapLayer",
                data=crime_df,
                get_position=["lon", "lat"],
                get_weight="crime_total",   # 또는 "risk_norm"
                radiusPixels=60,            # 값 키워가면서 느낌 보기
            )
        )

    # 뷰 설정
    view_state = pdk.ViewState(
        latitude=BERLIN_CENTER["lat"],
        longitude=BERLIN_CENTER["lon"],
        zoom=11,
        pitch=45,
    )

    tooltip = {
        "html": "<b>{name}</b><br/>{address}",
        "style": {"backgroundColor": "steelblue", "color": "white"},
    }

    st.markdown("### 3) 지도")

    st.pydeck_chart(
        pdk.Deck(
            initial_view_state=view_state,
            layers=layers,
            tooltip=tooltip,
        )
    )

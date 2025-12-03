import streamlit as st
import pandas as pd
import requests
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

# ==============================
# 🔴 여기만 네 API 키로 바꾸면 됨
# ==============================
API_KEY = "여기에_당신의_구글_API_키_붙여넣기"


# ------------------------------
# Google Places API로 장소 가져오기
# ------------------------------
def get_places(query, min_rating=None):
    """
    query 예시:
     - 'restaurants in Berlin'
     - 'tourist attractions in Berlin'
     - 'hotels in Berlin'
    """
    url = (
        "https://maps.googleapis.com/maps/api/place/textsearch/json"
        f"?query={query}&key={API_KEY}"
    )
    response = requests.get(url).json()

    results = []
    for place in response.get("results", []):
        geometry = place.get("geometry", {})
        location = geometry.get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")
        rating = place.get("rating")

        # 평점 필터 (예: 4.5 이상)
        if min_rating is not None:
            if rating is None or rating < min_rating:
                continue

        if lat is None or lng is None:
            continue

        results.append(
            {
                "name": place.get("name"),
                "address": place.get("formatted_address"),
                "lat": lat,
                "lng": lng,
                "rating": rating,
            }
        )

    return pd.DataFrame(results)


# ------------------------------
# Geocoding (주소 → 위도/경도)
# ------------------------------
@st.cache_data
def geocode(address: str):
    params = {"address": address, "key": API_KEY}
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    res = requests.get(url, params=params).json()
    if res.get("status") == "OK":
        loc = res["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    else:
        return None, None


# ------------------------------
# 범죄 데이터 불러오기
# ------------------------------
@st.cache_data
def load_crime_data():
    # 같은 폴더에 있는 Berlin_crimes.csv 사용
    df = pd.read_csv("Berlin_crimes.csv")
    return df


# ------------------------------
# 범죄 Heatmap 만들기 (Location 컬럼 이용해서 Geocoding)
# ------------------------------
def add_crime_heatmap(fmap, crime_df):
    heat_data = []

    # Location 단위로 그룹화 (같은 지역 여러 행 -> 합치기)
    grouped = crime_df.groupby("Location")

    for location_name, group in grouped:
        # 예: "Alexanderplatz, Berlin, Germany"
        query = f"{location_name}, Berlin, Germany"
        lat, lng = geocode(query)
        if lat is None or lng is None:
            continue

        # 범죄 정도를 weight로 사용 (여기서는 Local 컬럼 합)
        if "Local" in group.columns:
            weight = group["Local"].sum()
        else:
            # Local이 없으면 1로 두고 단순 위치만 표시
            weight = 1

        heat_data.append([lat, lng, float(weight)])

    if heat_data:
        HeatMap(heat_data, radius=25, blur=15, max_zoom=13).add_to(fmap)


# ------------------------------
# Streamlit 앱 시작
# ------------------------------
def main():
    st.set_page_config(page_title="베를린 여행 & 범죄 위험도 지도", layout="wide")
    st.title("🇩🇪 베를린 여행 지도 + 범죄 위험도")

    st.write("구글 지도 + 범죄 데이터 + 나만의 맛집을 표시하는 대시보드입니다.")

    # 사이드바 필터
    st.sidebar.header("필터")
    show_restaurants = st.sidebar.checkbox("🍽️ 음식점 (4.5★ 이상)", value=True)
    show_hotels = st.sidebar.checkbox("🏨 숙박 시설(호텔)", value=True)
    show_attractions = st.sidebar.checkbox("📍 관광지 (4.5★ 이상)", value=True)
    show_crime = st.sidebar.checkbox("🚨 범죄 위험도 Heatmap", value=True)

    # 데이터 로드 (API 호출)
    st.sidebar.write("데이터 불러오는 중...")

    # 평점 조건:
    # - 음식점: 4.5 이상
    # - 관광지: 4.5 이상
    # - 호텔: 평점 필터 X 또는 4.0 이상 등으로 자유롭게 조정 가능
    restaurants = pd.DataFrame()
    hotels = pd.DataFrame()
    attractions = pd.DataFrame()

    if show_restaurants:
        restaurants = get_places("restaurants in Berlin, Germany", min_rating=4.5)

    if show_hotels:
        hotels = get_places("hotels in Berlin, Germany", min_rating=None)

    if show_attractions:
        attractions = get_places("tourist attractions in Berlin, Germany", min_rating=4.5)

    crime_df = load_crime_data()

    # 사용자 커스텀 장소 저장용
    if "custom_places" not in st.session_state:
        st.session_state["custom_places"] = []

    # --------------------------
    # 사용자 직접 장소 추가 폼
    # --------------------------
    st.subheader("📝 나만의 맛집 / 장소 추가하기")

    with st.form("add_place_form"):
        custom_name = st.text_input("장소 이름 (예: 나만의 맛집)")
        custom_address = st.text_input("주소 (Google Maps에 나오는 형태로)")
        submitted = st.form_submit_button("지도에 추가")

    if submitted:
        if custom_address.strip() == "":
            st.error("주소를 입력해주세요.")
        else:
            # 주소를 베를린 기준으로 해석하고 싶다면 ", Berlin, Germany"를 뒤에 붙여도 됨
            full_address = custom_address  # + ", Berlin, Germany"
            lat, lng = geocode(full_address)
            if lat is None:
                st.error("주소를 찾을 수 없습니다. 구글 지도에 있는 정확한 주소를 넣어보세요.")
            else:
                st.success(f"'{custom_name or custom_address}' 을(를) 지도에 추가했습니다.")
                st.session_state["custom_places"].append(
                    {
                        "name": custom_name or custom_address,
                        "lat": lat,
                        "lng": lng,
                    }
                )

    # --------------------------
    # 지도 생성
    # --------------------------
    berlin_center = [52.5200, 13.4050]
    fmap = folium.Map(location=berlin_center, zoom_start=12)

    # 음식점 마커 (파란색)
    if not restaurants.empty:
        for _, row in restaurants.iterrows():
            folium.Marker(
                [row["lat"], row["lng"]],
                popup=f"{row['name']} ⭐{row.get('rating', '')}",
                icon=folium.Icon(color="blue", icon="cutlery", prefix="fa"),
            ).add_to(fmap)

    # 호텔 마커 (초록색)
    if not hotels.empty:
        for _, row in hotels.iterrows():
            folium.Marker(
                [row["lat"], row["lng"]],
                popup=f"{row['name']} ⭐{row.get('rating', '')}",
                icon=folium.Icon(color="green", icon="bed", prefix="fa"),
            ).add_to(fmap)

    # 관광지 마커 (보라색)
    if not attractions.empty:
        for _, row in attractions.iterrows():
            folium.Marker(
                [row["lat"], row["lng"]],
                popup=f"{row['name']} ⭐{row.get('rating', '')}",
                icon=folium.Icon(color="purple", icon="info-sign"),
            ).add_to(fmap)

    # 커스텀 장소 마커 (빨간색)
    for place in st.session_state["custom_places"]:
        folium.Marker(
            [place["lat"], place["lng"]],
            popup=f"⭐ {place['name']} (사용자 추가)",
            icon=folium.Icon(color="red", icon="star"),
        ).add_to(fmap)

    # 범죄 Heatmap
    if show_crime:
        add_crime_heatmap(fmap, crime_df)

    # --------------------------
    # 지도 화면에 표시
    # --------------------------
    st.subheader("🗺️ 지도")
    st_data = st_folium(fmap, width=900, height=600)


if __name__ == "__main__":
    main()

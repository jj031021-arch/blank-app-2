import requests
import pandas as pd
import streamlit as st

API_KEY = st.secrets["google"]["api_key"]

def get_places(query, min_rating=4.5):
    url = (
        f"https://maps.googleapis.com/maps/api/place/textsearch/json?"
        f"query={query}&location=52.5200,13.4050&radius=5000&key={API_KEY}"
    )
    response = requests.get(url).json()

    results = []
    for place in response["results"]:
        rating = place.get("rating", 0)
        if rating >= min_rating:
            results.append({
                "name": place["name"],
                "address": place.get("formatted_address"),
                "lat": place["geometry"]["location"]["lat"],
                "lng": place["geometry"]["location"]["lng"],
                "rating": rating
            })

    return pd.DataFrame(results)

restaurants = get_places("Berlin restaurants")
attractions = get_places("Berlin tourist attractions")

import folium
from folium.plugins import HeatMap
import pandas as pd

def add_crime_heatmap(map_object):
    crime = pd.read_csv("Berlin_crimes.csv")
    heat_data = crime[['lat', 'lng']].values.tolist()
    HeatMap(heat_data, radius=15).add_to(map_object)

from streamlit_folium import st_folium

def create_map(restaurants, hotels, attractions, show_crime=False):
    fmap = folium.Map(location=[52.5200, 13.4050], zoom_start=12)

    # 음식점 마커
    for _, r in restaurants.iterrows():
        folium.Marker(
            [r.lat, r.lng],
            popup=f"{r.name} ⭐{r.rating}",
            icon=folium.Icon(color="blue")
        ).add_to(fmap)

    # 호텔
    for _, h in hotels.iterrows():
        folium.Marker(
            [h.lat, h.lng],
            popup=f"{h.name}",
            icon=folium.Icon(color="green")
        ).add_to(fmap)

    # 관광지
    for _, a in attractions.iterrows():
        folium.Marker(
            [a.lat, a.lng],
            popup=a.name,
            icon=folium.Icon(color="purple")
        ).add_to(fmap)

    # 범죄 히트맵
    if show_crime:
        add_crime_heatmap(fmap)

    return fmap

def geocode_address(address):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={API_KEY}"
    response = requests.get(url).json()
    if response["status"] == "OK":
        loc = response["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, Nonest.header("직접 장소 추가하기")
address = st.text_input("주소를 입력하세요")

if st.button("지도에 추가"):
    lat, lng = geocode_address(address)
    if lat:
        st.session_state["custom_places"].append([lat, lng])
    else:
        st.error("주소를 찾을 수 없습니다")

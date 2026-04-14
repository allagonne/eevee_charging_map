import streamlit as st
import pandas as pd
from api import get_chargers, get_charger_details
import math
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import requests

# Add this function
def geocode_city(city_name):
    """Convert city name to coordinates using Nominatim"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': city_name,
        'format': 'json',
        'limit': 1
    }
    headers = {'User-Agent': 'EeveeChargerSearchApp/1.0'}
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        results = response.json()
        
        if results:
            return float(results[0]['lat']), float(results[0]['lon']), results[0]['display_name']
        return None, None, None
    except Exception as e:
        st.error(f"Geocoding error: {e}")
        return None, None, None

# Force light theme
st.set_page_config(page_title="Eevee Charger Search", layout="wide", initial_sidebar_state="collapsed")

# Display logo
st.image("assets/logo1.png", width=200)

st.title("Eevee Charger Search App")

# Simple login (credentials in Streamlit Secrets)
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Sign in"):
        if (
            username == st.secrets["auth"]["USER"]
            and password == st.secrets["auth"]["PWD"]
        ):
            st.session_state.authenticated = True
            st.success("Logged in.")
            st.rerun()
        else:
            st.error("Invalid credentials.")
    st.stop()

# ---- Location button ----
if "geo" not in st.session_state:
    st.session_state.geo = None

if "request_location" not in st.session_state:
    st.session_state.request_location = False
    
st.subheader("🏙️ Get your location...")

col1, col2 = st.columns(2)

with col1:
    if st.button("📍 Get my location"):
        st.session_state.request_location = True

with col2:
    if st.button("❌ Clear"):
        st.session_state.geo = None
        st.session_state.request_location = False


# Call get_geolocation outside of button callback for proper handling
if st.session_state.request_location:
    loc = get_geolocation()
    if loc and "coords" in loc:
        st.session_state.geo = {
            "lat": loc["coords"]["latitude"],
            "lon": loc["coords"]["longitude"],
            "accuracy_m": loc["coords"].get("accuracy"),
            "source": "geolocation"
        }
        st.session_state.request_location = False
        st.rerun()
    elif loc is not None:
        # Location request was denied or failed
        st.warning("Could not get your location. Please allow location access in your browser settings and try again.")
        st.session_state.request_location = False

# ---- Show and use latitude/longitude ----
geo = st.session_state.geo
default_lat, default_lon, default_dist = 49.44, 6.11, 1.0

# Initialize coordinate inputs in session state if not present
if 'input_lat' not in st.session_state:
    st.session_state.input_lat = default_lat
if 'input_lon' not in st.session_state:
    st.session_state.input_lon = default_lon
if 'geo_version' not in st.session_state:
    st.session_state.geo_version = 0

# Update input fields when geo location changes
if geo:
    # Force update by incrementing version when geo changes
    if (geo['lat'] != st.session_state.input_lat or 
        geo['lon'] != st.session_state.input_lon):
        st.session_state.input_lat = geo['lat']
        st.session_state.input_lon = geo['lon']
        st.session_state.geo_version += 1
    
    if geo.get('source') == 'geolocation':
        st.success(f"Latitude: {geo['lat']:.6f}, Longitude: {geo['lon']:.6f} (±{geo.get('accuracy_m', '–')} m)")
    elif geo.get('source') == 'map_click':
        st.success(f"🗺️ Location from map click: {geo['lat']:.6f}, {geo['lon']:.6f}")
        st.info("👆 Coordinates updated below! Click 'Search' to find chargers at this location.")
    lat, lon = geo['lat'], geo['lon']
else:
    lat, lon = st.session_state.input_lat, st.session_state.input_lon
st.subheader("🏙️ ...Or Search by City...")
col_city1, col_city2 = st.columns([3, 1])

with col_city1:
    city_search = st.text_input("City name", placeholder="e.g., Paris, London, Luxembourg")

with col_city2:
    st.write("")  # Spacer
    if st.button("🔍 Find"):
        if city_search:
            lat_result, lon_result, display = geocode_city(city_search)
            if lat_result and lon_result:
                st.session_state.geo = {
                    "lat": lat_result,
                    "lon": lon_result,
                    "accuracy_m": "City center",
                    "source": "city",
                    "city_name": display
                }
                st.rerun()
            else:
                st.error("City not found. Try a different name.")

# Display city location info if set from city search
if geo and geo.get('source') == 'city':
    st.info(f"📍 **{geo.get('city_name')}**\n\nLatitude: {geo['lat']:.2f}, Longitude: {geo['lon']:.2f}")

st.subheader("🏙️ ...Or Directly Search by Coordinates")
# Input fields for central point and distance - key includes version to force update
latitude = st.number_input("Latitude", value=st.session_state.input_lat, format="%.6f", 
                           key=f"lat_input_{st.session_state.geo_version}")
longitude = st.number_input("Longitude", value=st.session_state.input_lon, format="%.6f", 
                            key=f"lon_input_{st.session_state.geo_version}")
distance_km = st.number_input("Distance (km)", value=default_dist, min_value=1.0, max_value=10.0, step=0.5)
only_fast_charge = st.checkbox("⚡ Only fast charge (≥100 kW)", value=False)

# Update session state from manual coordinate changes
st.session_state.input_lat = latitude
st.session_state.input_lon = longitude

def get_bounding_box(latitude, longitude, distance_km):
    """
    Calculates a bounding box given a central point and a distance.
    """
    lat_change = distance_km / 111.1
    lon_change = distance_km / (111.1 * math.cos(math.radians(latitude)))

    top_left_latitude = latitude + lat_change
    top_left_longitude = longitude - lon_change
    bottom_right_latitude = latitude - lat_change
    bottom_right_longitude = longitude + lon_change

    return top_left_latitude, top_left_longitude, bottom_right_latitude, bottom_right_longitude

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculates the distance between two points using the Haversine formula.
    Returns distance in kilometers.
    """
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c

# Extract price information (adjust based on your API structure)
# Assuming price is in chargers list
def get_price_display(chargers):
    if not isinstance(chargers, list) or not chargers:
        return None
    
    prices = [c.get('tariff', {}).get('energy_price') for c in chargers if c.get('tariff', {}).get('energy_price') is not None]
    
    if not prices:
        return None
    
    min_price = min(prices)
    max_price = max(prices)
    
    if min_price == max_price:
        return f"{min_price:.2f}"
    else:
        return f"{min_price:.2f} < price < {max_price:.2f}"
    
def get_address(location):
    if not isinstance(location, dict):
        return None
    
    street = location.get('street', '')
    zipcode = location.get('zipcode', '')
    city = location.get('city', '')
    country = location.get('country', '')
    
    return f"{street}, {zipcode} {city}, {country}"

def highlight_unavailable(row):
    """Apply light red background if no stations are available"""
    if pd.notna(row['parking_spaces']) and row['parking_spaces'].startswith('0/'):
        return ['background-color: #ffcccc'] * len(row)  # Light red
    return [''] * len(row)

def get_charger_specs(chargers):
    if not isinstance(chargers, list) or not chargers:
        return None
    
    # Group by power and connector type
    specs = {}
    for c in chargers:
        power = c.get('power')
        connector = c.get('connector', {}).get('label')
        
        if power and connector:
            key = f"{power} kW {connector}"
            specs[key] = specs.get(key, 0) + 1
    
    # Format as "n*power kW connector, m*power kW connector..."
    result = ", ".join([f"{count}*{spec}" for spec, count in specs.items()])
    return result if result else None

def get_parking_availability(chargers):
    if not isinstance(chargers, list) or not chargers:
        return None
    
    total = len(chargers)
    available = sum(1 for c in chargers if c.get('status') == 'available')
    
    return f"{available}/{total}"

def has_fast_charging(chargers, min_power=100):
    """Check if any charger has power >= min_power kW"""
    if not isinstance(chargers, list) or not chargers:
        return False
    
    return any(c.get('power', 0) >= min_power for c in chargers)

# Initialize search results in session state
if "search_results" not in st.session_state:
    st.session_state.search_results = None

if st.button("Search"):
    with st.spinner("Searching for chargers..."):
        try:
            top_left_lat, top_left_lon, bottom_right_lat, bottom_right_lon = get_bounding_box(latitude, longitude, distance_km)

            chargers = get_chargers(
                top_left_lat,
                top_left_lon,
                bottom_right_lat,
                bottom_right_lon,
            )

            if not chargers:
                st.warning("No chargers found in the specified area.")
            else:
                st.success(f"{len(chargers)} chargers found! Fetching details and filtering out...")

                detailed_chargers = []
                for charger in chargers:
                    details = get_charger_details(charger['id'])
                    
                    # If only fast charge is selected, skip chargers without fast charging
                    if only_fast_charge:
                        if not has_fast_charging(details.get('chargers', []), min_power=100):
                            continue  # Skip this charger, don't add to list
                    
                    detailed_chargers.append(details)

                # Check if we have any chargers after filtering
                if not detailed_chargers:
                    st.warning("No chargers match your criteria.")
                    st.session_state.search_results = None
                else:
                    st.success(f"{len(detailed_chargers)} chargers match your criteria!")
                    
                    # Store results in session state along with search params
                    st.session_state.search_results = {
                        'data': detailed_chargers,
                        'latitude': latitude,
                        'longitude': longitude,
                        'distance_km': distance_km
                    }

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.session_state.search_results = None

    # Display search results if they exist
    if st.session_state.search_results:
        try:
            detailed_chargers = st.session_state.search_results['data']
            search_lat = st.session_state.search_results['latitude']
            search_lon = st.session_state.search_results['longitude']
            search_dist = st.session_state.search_results['distance_km']
            
            df = pd.DataFrame(detailed_chargers)
            
            # Extract latitude and longitude from nested location dict
            df['latitude'] = df['location'].apply(lambda x: x.get('latitude') if isinstance(x, dict) else None)
            df['longitude'] = df['location'].apply(lambda x: x.get('longitude') if isinstance(x, dict) else None)

            # Add address column
            df['address'] = df['location'].apply(get_address)

            # Add charger specs column
            df['chargers_specs'] = df['chargers'].apply(get_charger_specs)

            # Google Maps navigation link
            df['navigation'] = df.apply(
                lambda row: (
                    f"https://www.google.com/maps/dir/?api=1&destination={row['latitude']},{row['longitude']}"
                    if pd.notna(row['latitude']) and pd.notna(row['longitude']) else None
                ),
                axis=1
            )
            df['navigation_waze'] = df.apply(
                lambda row: (
                    f"https://waze.com/ul?ll={row['latitude']},{row['longitude']}&navigate=yes"
                    if pd.notna(row['latitude']) and pd.notna(row['longitude']) else None
                ),
                axis=1
            )
            # Calculate distance from central point
            df['distance_km'] = df.apply(
                lambda row: calculate_distance(search_lat, search_lon, row['latitude'], row['longitude']) 
                if pd.notna(row['latitude']) and pd.notna(row['longitude']) else None, 
                axis=1
            )

            # Filter by actual distance (not just bounding box)
            df = df[df['distance_km'] <= search_dist]

            if not df.empty:
                df['price'] = df['chargers'].apply(get_price_display)
                
                # Update parking_spaces to show availability
                df['parking_spaces'] = df['chargers'].apply(get_parking_availability)
                
                # For sorting, extract min price as numeric value
                df['price_numeric'] = df['chargers'].apply(
                    lambda x: min([c.get('tariff', {}).get('energy_price', float('inf')) for c in x]) if isinstance(x, list) and x else None
                )

            # Sort options
            sort_by = st.selectbox("Sort by", ["Distance", "Price"])
            
            if sort_by == "Distance":
                df = df.sort_values('distance_km')
            elif sort_by == "Price":
                df = df.sort_values('price_numeric')

            # drop some columns
            df.drop(['chargers', 'location','operator', 'opening_times', 'allowed', 'price_numeric'], axis = 1, inplace=True)
            
            # Apply the styling before displaying
            styled_df = df.style.apply(highlight_unavailable, axis=1)

            # Display the styled dataframe
            st.dataframe(
                styled_df,
                column_config={
                    "navigation": st.column_config.LinkColumn(
                        "Navigation",
                        display_text="Open in Google Maps"
                    ),
                    "navigation_waze": st.column_config.LinkColumn(
                        "Navigation (Waze)",
                        display_text="Open in Waze"
                    ),
                },
            )

            # Display map
            st.subheader("📍 Interactive Map View")
            st.info("💡 Click anywhere on the map to update search coordinates (this will scroll you back to the top)")
            
            # Debug: Check if coordinates exist
            if df[['latitude', 'longitude']].isnull().any().any():
                st.warning("Some chargers have missing coordinates and won't appear on the map.")
            
            # Create Folium map centered on search location
            m = folium.Map(
                location=[search_lat, search_lon],
                zoom_start=13,
                tiles='OpenStreetMap'
            )
            
            # Add search radius circle
            folium.Circle(
                location=[search_lat, search_lon],
                radius=search_dist * 1000,  # Convert km to meters
                color='blue',
                fill=True,
                fillColor='blue',
                fillOpacity=0.1,
                popup=f'Search area ({search_dist} km)',
                tooltip='Current search center'
            ).add_to(m)
            
            # Add center marker
            folium.Marker(
                location=[search_lat, search_lon],
                popup='Search Center',
                tooltip='Current search center',
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(m)
            
            # Add markers for each charger with fixed-size icons
            for idx, row in df.iterrows():
                # Color based on availability
                if row['parking_spaces'].startswith('0/'):
                    color = 'red'
                    icon = 'remove'
                else:
                    color = 'green'
                    icon = 'flash'
                
                # Create popup with charger info
                popup_html = f"""
                <div style="font-family: Arial; width: 250px;">
                    <h4 style="margin: 0 0 10px 0;">{row['address']}</h4>
                    <p style="margin: 5px 0;"><b>🔋 Available:</b> {row['parking_spaces']}</p>
                    <p style="margin: 5px 0;"><b>⚡ Specs:</b> {row['chargers_specs']}</p>
                    <p style="margin: 5px 0;"><b>📍 Distance:</b> {row['distance_km']:.2f} km</p>
                    <p style="margin: 10px 0 0 0;">
                        <a href="{row['navigation']}" target="_blank">📍 Google Maps</a> | 
                        <a href="{row['navigation_waze']}" target="_blank">🚗 Waze</a>
                    </p>
                </div>
                """
                
                folium.Marker(
                    location=[row['latitude'], row['longitude']],
                    popup=folium.Popup(popup_html, max_width=300),
                    icon=folium.Icon(color=color, icon=icon, prefix='fa'),
                    tooltip=f"{row['parking_spaces']} available - Click for details"
                ).add_to(m)
            
            # Enable click events and capture the last click
            # Dynamic key changes with each new click so Streamlit always picks up changes
            if 'map_click_count' not in st.session_state:
                st.session_state.map_click_count = 0

            map_data = st_folium(
                m, 
                width=700, 
                height=500,
                key=f"folium_map_{st.session_state.map_click_count}",
                returned_objects=["last_clicked"]
            )
            
            # If map was clicked, update search coordinates
            if map_data and map_data.get('last_clicked'):
                clicked_lat = map_data['last_clicked']['lat']
                clicked_lng = map_data['last_clicked']['lng']
                
                # Only process if it's a genuinely new location
                is_new_click = True
                if geo and geo.get('source') == 'map_click':
                    if (abs(clicked_lat - geo['lat']) < 0.00001 and
                            abs(clicked_lng - geo['lon']) < 0.00001):
                        is_new_click = False
                
                if is_new_click:
                    st.session_state.map_click_count += 1
                    st.session_state.geo = {
                        "lat": clicked_lat,
                        "lon": clicked_lng,
                        "accuracy_m": "Map click",
                        "source": "map_click"
                    }
                    st.rerun()

        except Exception as e:
            st.error(f"An error occurred displaying results: {e}")

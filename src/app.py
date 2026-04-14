import streamlit as st
import pandas as pd
from api import get_chargers, get_charger_details
import math

from streamlit_js_eval import get_geolocation

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
if geo:
    st.success(f"Latitude: {geo['lat']:.6f}, Longitude: {geo['lon']:.6f} (±{geo.get('accuracy_m', '–')} m)")
    lat, lon = geo['lat'], geo['lon']
else:
    lat, lon = default_lat, default_lon


# Input fields for central point and distance
latitude = st.number_input("Latitude", value=lat)
longitude = st.number_input("Longitude", value=lon)
distance_km = st.number_input("Distance (km)", value=default_dist, min_value=1.0, max_value=10.0, step=0.5)
only_fast_charge = st.checkbox("⚡ Only fast charge (≥100 kW)", value=False)

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
                    st.stop()
                
                st.success(f"{len(detailed_chargers)} chargers match your criteria!")
                
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
                    lambda row: calculate_distance(latitude, longitude, row['latitude'], row['longitude']) 
                    if pd.notna(row['latitude']) and pd.notna(row['longitude']) else None, 
                    axis=1
                )

                # Filter by actual distance (not just bounding box)
                df = df[df['distance_km'] <= distance_km]

                if df.empty:
                    st.warning("No chargers found within the specified distance.")
                else:
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
                st.map(df)

        except Exception as e:
            st.error(f"An error occurred: {e}")

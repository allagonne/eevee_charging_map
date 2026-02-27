import streamlit as st
import pandas as pd
from api import get_chargers, get_charger_details
import math

# Display logo
st.image("assets/logo1.png", width='stretch')

st.title("Eevee Charger Search")

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

# Input fields for central point and distance
latitude = st.number_input("Latitude", value=49.44)
longitude = st.number_input("Longitude", value=6.11)
distance_km = st.number_input("Distance (km)", value=1.0)

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
                st.success(f"{len(chargers)} chargers found!")

                detailed_chargers = []
                for charger in chargers:
                    details = get_charger_details(charger['id'])
                    detailed_chargers.append(details)

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
                
                # Display data (with clickable navigation links)
                st.dataframe(
                    df,
                    column_config={
                        "navigation": st.column_config.LinkColumn(
                            "Navigation",
                            display_text="Open in Google Maps"
                        )
                    },
                )

                # Display map
                st.map(df)

        except Exception as e:
            st.error(f"An error occurred: {e}")

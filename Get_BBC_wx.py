import json
import requests
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import re  # Import regular expression module

# Load the airport lookup table from a JSON file
def load_airport_codes(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

# Function to convert UTC to local time
def convert_utc_to_local(utc_time, offset):
    return utc_time + timedelta(hours=offset)

# Function to convert local time to UTC
def convert_local_to_utc(local_time, offset):
    return local_time - timedelta(hours=offset)

# Function to get weather data for a specific airport code
def get_weather_data(airport_code, airport_lookup):
    for entry in airport_lookup:
        if entry['airport'] == airport_code:
            location_code = entry['code']
            url = f"https://weather-broker-cdn.api.bbci.co.uk/en/forecast/aggregated/{location_code}"
            response = requests.get(url)
            return response.json(), entry['UTC_to_LTC']
    return None, None

# Function to get TAF for a specific airport code
def get_taf(airport_code):
    url = f"https://aviationweather.gov/api/data/taf?ids={airport_code}&time=valid"
    response = requests.get(url)
    taf = response.text
    if taf:
        return taf
    else:
        return f"No TAF found for {airport_code}"

def find_surrounding_weather_reports(weather_data, target_time):
    previous_reports = []
    nearest_report = None
    next_reports = []

    for report in weather_data['forecasts']:
        for detailed_report in report['detailed']['reports']:
            report_time = datetime.fromisoformat(detailed_report['localDate'] + 'T' + detailed_report['timeslot'])
            
            # Stop processing if we have enough next reports
            if len(next_reports) >= 5:
                break

            if report_time < target_time:
                previous_reports.append(detailed_report)
            elif report_time >= target_time:
                if nearest_report is None:
                    nearest_report = detailed_report
                next_reports.append(detailed_report)

        # Break the outer loop if we have enough next reports
        if len(next_reports) >= 5:
            break

    previous_reports = previous_reports[-5:]  # Last 5 previous reports
    next_reports = next_reports[:5]  # First 5 next reports

    return previous_reports, nearest_report, next_reports

# Main Streamlit Application
def main():
    st.title("Weather Dashboard")

    # Sidebar for user input
    st.sidebar.header("Input Parameters")
    airport_lookup = load_airport_codes('./airport_codes.json')  # Updated path
    
    # Input for airport code
    airport_code = st.sidebar.text_input("Enter Airport Code", "").upper()  # Convert to uppercase
    utc_input = st.sidebar.text_input("Enter time in UTC (HHMM)", "")
    
    if st.sidebar.button("Get Weather Data"):
        if utc_input and airport_code:
            # Validate input format for HHMM
            if not re.match(r'^\d{4}$', utc_input):
                st.warning("Please enter the time in the format HHMM (e.g., 1530 for 3:30 PM).")
                return
            
            try:
                # Determine the current UTC date
                current_utc_time = datetime.utcnow()
                
                # Parse the input time
                input_time = datetime.strptime(utc_input, "%H%M")

                # Create the full UTC datetime
                if (input_time.hour < current_utc_time.hour) or \
                   (input_time.hour == current_utc_time.hour and input_time.minute <= current_utc_time.minute):
                    # Input time has already passed today
                    target_time = datetime(current_utc_time.year, current_utc_time.month, current_utc_time.day + 1,
                                           input_time.hour, input_time.minute)
                else:
                    # Input time is still available today
                    target_time = datetime(current_utc_time.year, current_utc_time.month, current_utc_time.day,
                                           input_time.hour, input_time.minute)

                weather_data, utc_offset = get_weather_data(airport_code, airport_lookup)

                if weather_data:
                    # Convert UTC to local time
                    local_time = convert_utc_to_local(target_time, utc_offset)

                    # Extract location name and last update
                    location_name = weather_data['location']['name']
                    last_update = weather_data['lastUpdated']

                    # Handle different formats for last update time
                    try:
                        last_update_time_local = datetime.fromisoformat(last_update[:-1])  # Remove 'Z'
                    except ValueError:
                        last_update_time_local = datetime.strptime(last_update, "%Y-%m-%dT%H:%M:%S.%f%z")

                    # Convert last update time to UTC
                    last_update_time_utc = convert_local_to_utc(last_update_time_local, utc_offset)

                    # Find surrounding weather reports
                    previous_reports, nearest_report, next_reports = find_surrounding_weather_reports(weather_data, local_time)

                    # Prepare data for plotting
                    all_reports = previous_reports + [nearest_report] + next_reports
                    times = []
                    pressures = []
                    temperatures = []
                    
                    for report in all_reports:
                        report_time = datetime.fromisoformat(report['localDate'] + 'T' + report['timeslot'])
                        times.append(report_time.strftime('%Y-%m-%d %H:%M'))
                        pressures.append(report['pressure'])
                        temperatures.append(report['temperatureC'])

                    # Create a DataFrame for filtering
                    df = pd.DataFrame({
                        'Time': times,
                        'Pressure (hPa)': pressures,
                        'Temperature (°C)': temperatures
                    })

                    # Display header information
                    st.write(f"**Airport Code:** {airport_code} | **Location:** {location_name} | **Time (UTC):** {target_time.strftime('%Y-%m-%d %H:%M')}Z (Local: {local_time.strftime('%Y-%m-%d %H:%M')}L)")

                    # Fetch and display TAF
                    taf_info = get_taf(airport_code)
                    st.subheader("TAF Information:")
                    st.text(taf_info)

                    # Check if input time exists in the data
                    input_time_str = local_time.strftime('%Y-%m-%d %H:%M')
                    if input_time_str in df['Time'].values:
                        # If found, print values
                        idx = df[df['Time'] == input_time_str].index[0]
                        pressure_value = df.at[idx, 'Pressure (hPa)']
                        temperature_value = df.at[idx, 'Temperature (°C)']
                        st.write(f"**Temperature:** {temperature_value} °C | **Pressure:** {pressure_value} hPa")
                    else:
                        # If not found, check the available data range
                        if previous_reports and next_reports:
                            highest_pressure = max(previous_reports[-1]['pressure'], next_reports[0]['pressure'])
                            highest_temperature = max(previous_reports[-1]['temperatureC'], next_reports[0]['temperatureC'])
                            st.write(f"**Nearest Temperature:** {highest_temperature} °C | **Nearest Pressure:** {highest_pressure} hPa")
                        else:
                            earliest_time = df['Time'].min() if not df.empty else None
                            if earliest_time:
                                st.warning(f"The selected time is outside the available data range. Data is available since {earliest_time}.")
                            else:
                                st.write("Not enough data to determine nearest values.")
                            # Prevent plot display if the input time is outside the earliest available time
                            return

                    # Create time range for ±3 hours
                    time_range_start = local_time - timedelta(hours=3)
                    time_range_end = local_time + timedelta(hours=3)

                    # Filter data for the ±3 hour range
                    filtered_df = df[(pd.to_datetime(df['Time']) >= time_range_start) & 
                                     (pd.to_datetime(df['Time']) <= time_range_end)]

                    # Check if the input time is earlier than the earliest available time
                    earliest_time = df['Time'].min() if not df.empty else None
                    if earliest_time and local_time < datetime.strptime(earliest_time, "%Y-%m-%d %H:%M"):
                        st.warning(f"The input time is earlier than the earliest available data time: {earliest_time}.")
                    else:
                        # Create two columns for side-by-side charts
                        col1, col2 = st.columns([1, 1])  # Equal width for both columns

                        # Plotting Pressure
                        with col1:
                            fig, ax1 = plt.subplots(figsize=(6, 3))  # Increased size
                            ax1.plot(filtered_df['Time'], filtered_df['Pressure (hPa)'], marker='o', label='Pressure (hPa)', color='blue')

                            ax1.set_xlabel('Time')
                            ax1.set_ylabel('Pressure (hPa)', color='blue')
                            ax1.tick_params(axis='y', labelcolor='blue')

                            # Set x-ticks with rotation
                            plt.xticks(rotation=45)
                            ax1.set_xticks(filtered_df['Time'])
                            ax1.set_xticklabels(filtered_df['Time'], rotation=45, ha='right')
                            
                            plt.title('Pressure Over Time')
                            plt.legend()
                            st.pyplot(fig)

                        # Plotting Temperature
                        with col2:
                            fig, ax2 = plt.subplots(figsize=(6, 3))  # Increased size
                            ax2.plot(filtered_df['Time'], filtered_df['Temperature (°C)'], marker='o', label='Temperature (°C)', color='orange')

                            ax2.set_xlabel('Time')
                            ax2.set_ylabel('Temperature (°C)', color='orange')
                            ax2.tick_params(axis='y', labelcolor='orange')

                            # Set x-ticks with rotation
                            plt.xticks(rotation=45)
                            ax2.set_xticks(filtered_df['Time'])
                            ax2.set_xticklabels(filtered_df['Time'], rotation=45, ha='right')
                            
                            plt.title('Temperature Over Time')
                            plt.legend()
                            st.pyplot(fig)

                    # Display last update information at the bottom right
                    st.markdown(f"<div style='text-align: right;'>**Last Updated (UTC):** {last_update_time_utc.strftime('%Y-%m-%d %H:%M')}</div>", unsafe_allow_html=True)

                else:
                    st.error("Invalid airport code.")
            except ValueError as e:
                st.error(f"Invalid time format. Please use HHMM. Error: {e}")

if __name__ == "__main__":
    main()

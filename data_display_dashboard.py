import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

# Set page layout to wide and add a favicon
st.set_page_config(layout="wide", page_title="F1 Dashboard", page_icon="config/Logo.png")

# Custom CSS for text colors and alignment
st.markdown("""
    <style>
        /* Main page headers */
        .main-header {
            color: #3498db;
        }
        /* Sidebar text */
        .sidebar-text {
            color: #2ecc71;
        }
        /* Center align Circuit Location text */
        .center-align {
            text-align: center;
        }
        /* Smaller text for Circuit Details link */
        .small-text {
            font-size: 12px;
            color: #888;
        }
    </style>
""", unsafe_allow_html=True)

def get_circuits():
    conn = sqlite3.connect('f1_database.db')
    query = "SELECT circuitId, circuitRef, name, url FROM circuits_table"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_circuit_details(circuit_id):
    conn = sqlite3.connect('f1_database.db')
    query = f"SELECT * FROM circuits_table WHERE circuitId = {circuit_id}"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_last_n_races(circuit_id, n):
    conn = sqlite3.connect('f1_database.db')
    try:
        query = f"""
        SELECT year, raceId
        FROM races_table
        WHERE circuitId = {circuit_id}
        ORDER BY year DESC
        LIMIT {n}
        """
        last_n_races = pd.read_sql_query(query, conn)
        winners = []

        for _, race in last_n_races.iterrows():
            race_id = race['raceId']

            query_max_lap = f"""
            SELECT MAX(lap) as max_lap
            FROM lap_times
            WHERE raceId = {race_id}
            """
            max_lap_df = pd.read_sql_query(query_max_lap, conn)
            if max_lap_df.empty or max_lap_df['max_lap'].isnull().values.any():
                continue
            max_lap = max_lap_df.iloc[0]['max_lap']

            query_winner = f"""
            SELECT drivers_table.forename || ' ' || drivers_table.surname as winner_name, lap_times.driverId, lap_times.time
            FROM lap_times
            JOIN driver_standing_table ON lap_times.raceId = driver_standing_table.raceId AND lap_times.driverId = driver_standing_table.driverId
            JOIN drivers_table ON lap_times.driverId = drivers_table.driverId
            WHERE lap_times.raceId = {race_id} AND lap_times.lap = {max_lap} AND lap_times.position = 1
            LIMIT 1
            """
            winner = pd.read_sql_query(query_winner, conn)

            query_pole_position = f"""
            SELECT drivers_table.forename || ' ' || drivers_table.surname as pole_name, lap_times.driverId as pole_driverId
            FROM lap_times
            JOIN drivers_table ON lap_times.driverId = drivers_table.driverId
            WHERE lap_times.raceId = {race_id} AND lap_times.lap = 1 AND lap_times.position = 1
            LIMIT 1
            """
            pole_position = pd.read_sql_query(query_pole_position, conn)

            query_fastest_lap = f"""
            SELECT drivers_table.forename || ' ' || drivers_table.surname as fastest_name, lap_times.driverId as fastest_driverId, MIN(lap_times.milliseconds) as fastest_time
            FROM lap_times
            JOIN drivers_table ON lap_times.driverId = drivers_table.driverId
            WHERE lap_times.raceId = {race_id}
            GROUP BY lap_times.driverId
            ORDER BY fastest_time ASC
            LIMIT 1
            """
            fastest_lap = pd.read_sql_query(query_fastest_lap, conn)

            if not winner.empty:
                winner['year'] = race['year']
                winner['raceId'] = race_id

                if not pole_position.empty:
                    winner['pole_name'] = pole_position['pole_name'].values[0]
                    winner['pole_driverId'] = pole_position['pole_driverId'].values[0]
                else:
                    winner['pole_name'] = 'N/A'
                    winner['pole_driverId'] = 'N/A'
                
                if not fastest_lap.empty:
                    fastest_time_ms = fastest_lap['fastest_time'].values[0]
                    fastest_minutes = int(fastest_time_ms / 60000)
                    fastest_seconds = (fastest_time_ms % 60000) / 1000
                    fastest_time_formatted = f"{fastest_minutes}m {fastest_seconds:.3f}s"
                    winner['fastest_name'] = fastest_lap['fastest_name'].values[0]
                    winner['fastest_time'] = fastest_time_formatted
                    winner['fastest_time_ms'] = fastest_time_ms
                else:
                    winner['fastest_name'] = 'N/A'
                    winner['fastest_time'] = 'N/A'
                    winner['fastest_time_ms'] = None
                
                winners.append(winner)

        if winners:
            result_df = pd.concat(winners, ignore_index=True)
        else:
            result_df = pd.DataFrame(columns=['winner_name', 'driverId', 'time', 'year', 'raceId', 'pole_name', 'pole_driverId', 'fastest_name', 'fastest_time', 'fastest_time_ms'])

    except Exception as e:
        result_df = pd.DataFrame(columns=['winner_name', 'driverId', 'time', 'year', 'raceId', 'pole_name', 'pole_driverId', 'fastest_name', 'fastest_time', 'fastest_time_ms'])
        st.error(f"An error occurred: {e}")

    finally:
        conn.close()

    result_df.fillna('N/A', inplace=True)
    return result_df

def get_drivers():
    conn = sqlite3.connect('f1_database.db')
    query = "SELECT driverId, surname, forename FROM drivers_table ORDER BY surname"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_driver_details(driver_id):
    conn = sqlite3.connect('f1_database.db')
    query = f"SELECT forename, surname, dob as 'Date of Birth', nationality as 'Nationality', url as 'Details' FROM drivers_table WHERE driverId = {driver_id}"
    df = pd.read_sql_query(query, conn)
    df['Details'] = df['Details'].apply(lambda x: f'<a href="{x}" target="_blank">Profile</a>')
    df['Nationality'] = df['Nationality'].str.title()
    conn.close()
    return df

def get_races_for_driver(driver_id, start_year, end_year):
    conn = sqlite3.connect('f1_database.db')
    query = f"""
    SELECT races_table.raceId, races_table.name as 'Race Name', races_table.date as 'Date', races_table.year
    FROM races_table
    JOIN lap_times ON races_table.raceId = lap_times.raceId
    WHERE lap_times.driverId = {driver_id} AND races_table.year BETWEEN {start_year} AND {end_year}
    GROUP BY races_table.raceId
    ORDER BY races_table.year DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_fastest_lap_times(driver_id, race_ids):
    conn = sqlite3.connect('f1_database.db')
    query = f"""
    SELECT raceId, MIN(milliseconds) as fastest_time_ms
    FROM lap_times
    WHERE driverId = {driver_id} AND raceId IN ({','.join(map(str, race_ids))})
    GROUP BY raceId
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_fastest_lap_times_all(race_ids):
    conn = sqlite3.connect('f1_database.db')
    query = f"""
    SELECT raceId, MIN(milliseconds) as fastest_time_ms
    FROM lap_times
    WHERE raceId IN ({','.join(map(str, race_ids))})
    GROUP BY raceId
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_finishing_positions(driver_id, race_ids):
    conn = sqlite3.connect('f1_database.db')
    finishing_positions = []
    
    for race_id in race_ids:
        query_max_lap = f"""
        SELECT MAX(lap) as max_lap
        FROM lap_times
        WHERE raceId = {race_id} AND driverId = {driver_id}
        """
        max_lap_df = pd.read_sql_query(query_max_lap, conn)
        if max_lap_df.empty or max_lap_df['max_lap'].isnull().values.any():
            continue
        max_lap = max_lap_df.iloc[0]['max_lap']

        query_position = f"""
        SELECT position
        FROM lap_times
        WHERE raceId = {race_id} AND driverId = {driver_id} AND lap = {max_lap}
        """
        position_df = pd.read_sql_query(query_position, conn)
        if not position_df.empty:
            finishing_positions.append({
                'raceId': race_id,
                'Finish Position': position_df.iloc[0]['position']
            })

    conn.close()
    return pd.DataFrame(finishing_positions)

def generate_pdf(circuit_name, last_n_races_renamed, n_years):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.drawString(100, height - 40, f"{circuit_name} - Last {n_years} Races and Winners")
    text = c.beginText(40, height - 80)
    text.setFont("Helvetica", 12)
    
    table_data = last_n_races_renamed[['Year', 'Winner', 'Pole Position', 'Fastest Lap Driver', 'Fastest Lap Time', 'Article']].to_string(index=False)
    text.textLines(table_data)
    c.drawText(text)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def generate_driver_pdf(driver_name, driver_details, merged_df):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.drawString(100, height - 40, f"{driver_name} - Driver Details")
    text = c.beginText(40, height - 80)
    text.setFont("Helvetica", 12)
    
    details_data = driver_details[['Date of Birth', 'Nationality', 'Details']].to_string(index=False, header=False)
    text.textLines(details_data)
    c.drawText(text)

    c.drawString(100, height - 120, f"Races and Fastest Lap Times")
    text = c.beginText(40, height - 140)
    text.setFont("Helvetica", 12)
    
    races_data = merged_df[['Race Name', 'Date', 'Fastest Lap Time', 'Finish Position']].to_string(index=False)
    text.textLines(races_data)
    c.drawText(text)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def add_wikipedia_links(df, race_id_column):
    conn = sqlite3.connect('f1_database.db')
    query = f"SELECT raceId, url FROM races_table WHERE raceId IN ({','.join(map(str, df[race_id_column].tolist()))})"
    urls = pd.read_sql_query(query, conn)
    conn.close()
    url_dict = dict(zip(urls['raceId'], urls['url']))
    df['Details'] = df[race_id_column].apply(lambda x: f'<a href="{url_dict[x]}" target="_blank">Article</a>' if x in url_dict else 'N/A')
    return df

# Streamlit app
banner_image_path = "config/Logo.png"  
st.sidebar.image(banner_image_path, use_column_width=True)
st.sidebar.title('F1 Data Explorer')

# Sidebar radio button to select view mode
view_mode = st.sidebar.radio('Select View Mode', ('Circuits View', 'Drivers View'))

if view_mode == 'Circuits View':
    with st.spinner('Loading data...'):
        circuits_df = get_circuits()
        circuit_id = st.sidebar.selectbox('Select a Circuit', circuits_df['circuitId'], format_func=lambda x: circuits_df.loc[circuits_df['circuitId'] == x, 'circuitRef'].values[0])
        n_years = st.sidebar.slider('Select number of years to display', 1, 20, 5)

        if circuit_id:
            circuit_details = get_circuit_details(circuit_id)
            circuit_name = circuit_details['name'].values[0]
            circuit_url = circuit_details['url'].values[0]
            last_n_races = get_last_n_races(circuit_id, n_years)
            last_n_races['year'] = last_n_races['year'].astype(str)

            last_n_races_renamed = last_n_races.rename(columns={
                'year': 'Year',
                'winner_name': 'Winner',
                'pole_name': 'Pole Position',
                'fastest_name': 'Fastest Lap Driver',
                'fastest_time': 'Fastest Lap Time'
            })
            last_n_races_renamed = add_wikipedia_links(last_n_races_renamed, 'raceId')

            with st.sidebar.expander("Circuit Details"):
                st.write(circuit_details)

            st.markdown(f"<h1 class='main-header'>{circuit_name}</h1>", unsafe_allow_html=True)

            
            col1, col2 = st.columns([5, 3])
            with col1:
                st.write(last_n_races_renamed[['Year', 'Winner', 'Pole Position', 'Fastest Lap Driver', 'Fastest Lap Time', 'Details']].to_html(index=False, escape=False), unsafe_allow_html=True)

                fastest_lap_times = last_n_races_renamed[['Year', 'fastest_time_ms']].dropna()
                if not fastest_lap_times.empty:
                    fastest_lap_times['Fastest Time (minutes)'] = fastest_lap_times['fastest_time_ms'] / 60000
                    median_time = fastest_lap_times['Fastest Time (minutes)'].median()
                    fig = px.line(fastest_lap_times, x='Year', y='Fastest Time (minutes)', title='Fastest Lap Times Over the Last {} Years'.format(n_years), labels={'Fastest Time (minutes)': 'Fastest Time (minutes)'})
                    fig.add_hline(y=median_time, line_dash="dot", annotation_text="Median Fastest Time", annotation_position="bottom right", line_color="red")
                    st.plotly_chart(fig)

            with col2:
                if 'lat' in circuit_details.columns and 'lng' in circuit_details.columns:
                    circuit_location = circuit_details[['lat', 'lng']]
                    st.write('<div class="center-align"><h2>Circuit Location</h2></div>', unsafe_allow_html=True)
                    st.map(circuit_location, latitude='lat', longitude='lng', zoom=3, size=50000, color='#0044ff')
                    st.write(f'<div class="small-text"><a href="{circuit_url}" target="_blank">Circuit Details</a></div>', unsafe_allow_html=True)

            if st.sidebar.button('Generate PDF'):
                pdf_buffer = generate_pdf(circuit_name, last_n_races_renamed, n_years)
                st.sidebar.success("PDF generated successfully. You can now download it below.")
                st.sidebar.download_button(label="Download PDF", data=pdf_buffer, file_name="report.pdf", mime="application/pdf")

else:
    with st.spinner('Loading data...'):
        drivers_df = get_drivers()
        default_driver_id = drivers_df.loc[drivers_df['surname'] == 'Massa', 'driverId'].values[0]
        driver_id = st.sidebar.selectbox('Select a Driver', drivers_df['driverId'], index=int(drivers_df[drivers_df['driverId'] == default_driver_id].index[0]), format_func=lambda x: f"{drivers_df.loc[drivers_df['driverId'] == x, 'forename'].values[0]} {drivers_df.loc[drivers_df['driverId'] == x, 'surname'].values[0]}")
        
        start_year, end_year = st.sidebar.slider('Select year range', min_value=2010, max_value=2023, value=(2010, 2017))

        driver_details = get_driver_details(driver_id)
        driver_name = f"{driver_details['forename'].values[0]} {driver_details['surname'].values[0]}"
        st.markdown(f"<h1 class='main-header'>{driver_name}</h1>", unsafe_allow_html=True)

        st.write(driver_details[['Date of Birth', 'Nationality', 'Details']].to_html(index=False, escape=False), unsafe_allow_html=True)

        races = get_races_for_driver(driver_id, start_year, end_year)
        
        if not races.empty:
            race_ids = races['raceId'].tolist()
            fastest_lap_times = get_fastest_lap_times(driver_id, race_ids)
            fastest_lap_times_all = get_fastest_lap_times_all(race_ids)
            finishing_positions = get_finishing_positions(driver_id, race_ids)
            
            merged_df = races.merge(fastest_lap_times, on='raceId').merge(finishing_positions, on='raceId')
            merged_df['Fastest Lap Time'] = merged_df['fastest_time_ms'].apply(lambda x: f"{int(x // 60000)}m {((x % 60000) / 1000):.3f}s")
            merged_df = merged_df.rename(columns={'name': 'Race Name', 'date': 'Date', 'position': 'Finish Position'})
            
            st.markdown(f"<h1 class='main-header'>Races and Fastest Lap Times</h1>", unsafe_allow_html=True)

            
            seasons = merged_df['year'].unique()
            
            selected_season = st.selectbox('Select Season', seasons)
            
            season_df = merged_df[merged_df['year'] == selected_season]
            fastest_lap_df = fastest_lap_times_all[fastest_lap_times_all['raceId'].isin(season_df['raceId'])]
            
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"### Progression by Season: {selected_season}")
                fig1 = px.line(season_df, x='Date', y='Finish Position', labels={'Date': 'Race Date', 'Finish Position': 'Finishing Position'}, markers=True)
                fig1.update_yaxes(autorange="reversed")
                st.plotly_chart(fig1)
            
            with col2:
                st.write(f"### Fastest Lap Times by Season: {selected_season}")
                season_df['Fastest Lap Time (minutes)'] = season_df['fastest_time_ms'] / 60000
                fig2 = px.line(season_df, x='Date', y='Fastest Lap Time (minutes)', labels={'Date': 'Race Date', 'Fastest Lap Time (minutes)': 'Fastest Lap Time (minutes)'}, markers=True)
                st.plotly_chart(fig2)
            
            for season in seasons:
                with st.expander(f"Season {season}"):
                    season_df = merged_df[merged_df['year'] == season]
                    st.write(season_df[['Race Name', 'Date', 'Fastest Lap Time', 'Finish Position']].to_html(index=False), unsafe_allow_html=True)

            if st.sidebar.button('Generate PDF'):
                pdf_buffer = generate_driver_pdf(driver_name, driver_details, merged_df)
                st.sidebar.success("PDF generated successfully. You can now download it below.")
                st.sidebar.download_button(label="Download PDF", data=pdf_buffer, file_name="driver_report.pdf", mime="application/pdf")

        else:
            st.write("No races found for the selected driver in the given year range.")


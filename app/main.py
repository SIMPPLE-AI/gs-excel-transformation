from datetime import datetime
import streamlit as st

# uncomment the following line if you want to use the SQLAlchemy engine for database operations
# from sqlalchemy import create_engine

from src.utils import (
    calculate_adjusted_datetime,
    display_time,
    process_uploaded_file,
)

from src.ui_components import (
    copy_content_to_clipboard,
    download_processed_data,
)

# Streamlit App Setup
st.title("Data Processing and Transformation with Streamlit")
st.markdown("#### This web app performs data processing and transformation to fit the database input format.")

# Display times
sg_time = display_time()

# Sidebar options
servers = ["GS SGV1", "GS SGV2", "GS AUS", "GS QA", "GS CA"]
selected_server = st.sidebar.selectbox("Select Server", servers)

# Determine task type and adjusted datetime
adjusted_datetime = calculate_adjusted_datetime(selected_server)

# File upload section
uploaded_file_label = " ##### Please upload a CSV or XLSX file for processing."
uploaded_file = st.file_uploader(uploaded_file_label, type=["csv", "xlsx"])

# Input for dynamic exclusion of 'S/N' values
exclude_sn = st.checkbox("Exclude Specific S/N Values (Check to Expand the Text Field)", value=False)
exclude_values = None

if exclude_sn:  # Show text field when toggle is ON
    st.markdown("#### Exclude S/N Values (comma-separated):")
    exclude_values_input = st.text_area("", value="", placeholder="e.g., ABC123, EFG456, HIJ789")
    if exclude_values_input:
        exclude_values = [value.strip() for value in exclude_values_input.split(",")]

# Checkbox to add two null columns: lat and lon
add_lat_lon = st.checkbox("Add Extra Columns for Latitude (lat) and Longitude (lon)")

# Datetime input
selected_datetime_str = st.text_input(
    "Please Enter the [Receive Task Report Time]",
    value="",
    max_chars=19,
    key="selected_datetime",
)

# Initialize df_processed in session state
if "df_processed" not in st.session_state:
    st.session_state.df_processed = None

# Process button
if st.button("Process"):
    try:
        # Parse the input datetime
        selected_datetime = datetime.strptime(selected_datetime_str, "%Y-%m-%d %H:%M:%S")

        # Prepare arguments for process_uploaded_file
        process_args = {
            "uploaded_file": uploaded_file,
            "selected_datetime": selected_datetime_str,
            "adjusted_datetime": adjusted_datetime,
            "selected_server": selected_server,
        }

        # Add 'exclude_values' to arguments if toggle is ON and input is provided
        if exclude_sn and exclude_values:
            process_args["exclude_values"] = exclude_values

        # Process the uploaded file
        df_processed = process_uploaded_file(**process_args)

        # Optionally add 'lat' and 'lon' columns if the checkbox is checked
        if add_lat_lon:
            df_processed["lat"] = "NULL"
            df_processed["lng"] = "NULL"

        # Store result in session state
        st.session_state.df_processed = df_processed
        st.success("File processed successfully!")

    except ValueError:
        st.error("Invalid datetime format.")
    except Exception as e:
        st.error(f"An error occurred: {e}")

# Load processed DataFrame from session state
df_processed = st.session_state.get("df_processed", None)

# Display processed data and metadata
if df_processed is not None:
    st.markdown("### Processed DataFrame:")
    st.dataframe(df_processed)

    num_rows, num_cols = df_processed.shape
    st.markdown(f"Processed DataFrame Size: {num_cols} columns and {num_rows} rows")

    # Add Copy Content Button
    st.markdown("### Copy Content Without Headers:")
    copy_text = df_processed.to_csv(index=False, header=False)

    # Collapsible section for content preview
    with st.expander("Preview Copied Content"):
        st.text_area("Content Preview (excluding headers):", copy_text, height=200)

    # Buttons for Copy Content and Download
    col1, col2 = st.columns(2)

    with col1:
        copy_content_to_clipboard(df_processed)

    with col2:
        download_processed_data(df_processed, uploaded_file.name, selected_server)

    # # Optional: Insert into MySQL database (commented out for now)
    # # Insert into MySQL section (stays visible after processing)
    # with st.expander("Insert into MySQL Database (Temporary Credentials)"):
    #     st.markdown("##### Enter MySQL database credentials:")

    #     host = st.text_input("Host", placeholder="e.g., localhost or mysql.example.com")
    #     port = st.text_input("Port", value="3306")
    #     username = st.text_input("Username")
    #     password = st.text_input("Password", type="password")
    #     db_name = st.text_input("Database Name")
    #     table_name = st.text_input("Target Table Name")

    #     if st.button("Insert into MySQL"):
    #         if not all([host, port, username, password, db_name, table_name]):
    #             st.error("All fields are required.")
    #         else:
    #             try:
    #                 conn_str = f"mysql+pymysql://{username}:{password}@{host}:{port}/{db_name}"
    #                 engine = create_engine(conn_str)

    #                 df_to_insert = df_processed.replace("NULL", None)
    #                 df_to_insert.to_sql(table_name, engine, index=False, if_exists="append")

    #                 st.success(f"Data inserted into `{table_name}` successfully!")

    #             except Exception as e:
    #                 st.error(f"Failed to insert data: {e}")

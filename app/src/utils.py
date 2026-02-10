import io
from typing import Optional, List
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import pytz
import streamlit as st

# Constant unit
gallon = 3.785411784
feet_squared = 0.09290304

# Rename columns
cols_to_rename = {
    "Id": "id",
    "Robot name": "robot_name",
    "S/N": "serial_number",
    "Map name": "map_name",
    "Cleaning plan": "task_name",
    "User": "user",
    "Task start time": "start_time",
    "End time": "end_time",
    "Task completion (%)": "task_completion",
    "Actual cleaning area(㎡)": "cleaning_area",
    "Actual cleaning area(ft²)": "cleaning_area",
    "Total time (h)": "total_time",
    "Water usage (L)": "water_usage",
    "Water usage (gal)": "water_usage",
    "Brush (%)": "brush",
    "Filter (%)": "filter_element",
    "Squeegee(%)": "squeegee",
    "Planned crystallization area (㎡)": "created_at",
    "Planned crystallization area (ft²)": "created_at",
    "Actual crystallization area (㎡)": "updated_at",
    "Actual crystallization area (ft²)": "updated_at",
    "Cleaning plan area (㎡)": "area_planned",
    "Cleaning plan area (ft²)": "area_planned",
    "Start battery level (%)": "start_battery_level",
    "End battery level (%)": "end_battery_level",
    "Receive task report time": "task_report_received",
    "Task type": "cleaning_mode",
    "Download link": "report_link",
    "Work efficiency (㎡/h)": "performance",
    "Work efficiency (ft²/h)": "performance",
}


# Function to read files dynamically based on file type
def read_file(file: io.BytesIO) -> pd.DataFrame:
    """
    Reads a file and returns a pandas DataFrame.
    Supports CSV and Excel (.xlsx) files.

    Args:
        file (io.BytesIO): The uploaded file.

    Returns:
        pd.DataFrame: DataFrame containing the file's data.

    Raises:
        ValueError: If the file extension is not supported.
    """
    try:
        # Check the file extension
        if file.name.endswith(".csv"):
            return pd.read_csv(file)
        elif file.name.endswith(".xls") or file.name.endswith(".xlsx"):
            return pd.read_excel(file)
        else:
            raise ValueError(f"Unsupported file type: {file.name}")
    except Exception as e:
        raise RuntimeError(f"An error occurred while reading the file: {e}")


# Function to process data
def process_data(
    file: io.BytesIO, selected_datetime_str: str, adjusted_datetime: datetime, exclude_values: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Process data from an Excel file for the selected datetime.

    Parameters:
        file (io.BytesIO): The uploaded Excel file containing the data.
        selected_datetime_str (str): The selected datetime in the format "YYYY-MM-DD HH:MM:SS".
        adjusted_datetime (datetime.datetime): The adjusted datetime to be used for updates.

    Returns:
        pandas.DataFrame: Processed DataFrame with cleaned and transformed data.

    Notes:
        This function performs the following steps:
        1. Reads data from the Excel file, dropping unnecessary columns.
        2. Filters and sorts the DataFrame based on the selected datetime.
        3. Reorders columns in the desired order.
        4. Updates specified columns with the adjusted_datetime.
        5. Cleans and transforms data, handling commas and percentage values.
        6. Returns the processed DataFrame.

    Example:
        df_processed = process_data(uploaded_file, "2023-08-25 14:00:00", datetime.now())
    """
    df = read_file(file)

    if exclude_values:
        df = df[~df["S/N"].isin(exclude_values)]

    # Drop unnecessary columns
    drop_columns = [
        "Total time",
        "Task status",
        "Plan running time (s)",
        "Uncleaned area (㎡)",
        "Task start mode",
        "Remarks",
    ]
    df.drop(columns=drop_columns, inplace=True)
    df.insert(0, "Id", np.nan)

    selected_datetime = datetime.strptime(selected_datetime_str, "%Y-%m-%d %H:%M:%S")

    # Filter and sort DataFrame
    df["Receive task report time"] = pd.to_datetime(df["Receive task report time"])
    df_filtered = df[df["Receive task report time"] > selected_datetime]

    # Exclude values from 'S/N' if exclude_values is provided
    if exclude_values:
        df_filtered = df_filtered[~df_filtered["S/N"].isin(exclude_values)]

    df_filtered = df_filtered.sort_values(by="Receive task report time", ascending=False)
    df_filtered.reset_index(drop=True, inplace=True)

    # Create column order
    column_order = [
        "Id",
        "Robot name",
        "S/N",
        "Map name",
        "Cleaning plan",
        "User",
        "Task start time",
        "End time",
        "Task completion (%)",
        "Actual cleaning area(㎡)",
        "Total time (h)",
        "Water usage (L)",
        "Brush (%)",
        "Filter (%)",
        "Squeegee(%)",
        "Planned crystallization area (㎡)",
        "Actual crystallization area (㎡)",
        "Cleaning plan area (㎡)",
        "Start battery level (%)",
        "End battery level (%)",
        "Receive task report time",
        "Task type",
        "Download link",
        "Work efficiency (㎡/h)",
    ]

    # Ensure all required columns exist
    for col in column_order:
        if col not in df_filtered.columns:
            df_filtered[col] = "NULL"

    df_reorder = df_filtered[column_order]

    df_test = df_reorder.copy()

    # Update columns with adjusted_datetime
    columns_to_update = [
        "Planned crystallization area (㎡)",
        "Actual crystallization area (㎡)",
    ]
    df_test[columns_to_update] = df_test[columns_to_update].astype("object")
    df_test.loc[:, columns_to_update] = adjusted_datetime

    df_replaced = df_test.replace("-", 0)
    df_replaced = df_replaced.fillna("NULL")

    # Remove commas and replace values in specified columns
    columns_with_comma_or_pct = [
        "Work efficiency (㎡/h)",
        "Actual cleaning area(㎡)",
        "Cleaning plan area (㎡)",
        "Brush (%)",
        "Filter (%)",
        "Squeegee(%)",
    ]

    # For loop to handle multiple dtypes
    for column in columns_with_comma_or_pct:
        if df_replaced[column].dtype in ["object", "float64"]:
            df_replaced[column] = (
                df_replaced[column]
                .astype(str)
                .str.replace(",", "", regex=False)
                .replace("0.00", "0")
                .replace("100.00", "100")
                .astype(float)
            )

    return df_replaced


def process_ca_data(
    file: io.BytesIO, selected_datetime_str: str, adjusted_datetime: datetime, exclude_values: Optional[List[str]] = None
) -> pd.DataFrame:
    """
    Process data from an Excel file (Canada data) for the selected datetime.

    Parameters:
        file (io.BytesIO): The uploaded Excel file containing the data.
        selected_datetime_str (str): The selected datetime in the format "YYYY-MM-DD HH:MM:SS".
        adjusted_datetime (datetime.datetime): The adjusted datetime to be used for updates.

    Returns:
        pandas.DataFrame: Processed DataFrame with cleaned and transformed data.

    Notes:
        This function performs the following steps:
        1. Reads data from the Excel file, dropping unnecessary columns.
        2. Filters and sorts the DataFrame based on the selected datetime.
        3. Reorders columns in the desired order.
        4. Updates specified columns with the adjusted_datetime.
        5. Cleans and transforms data, handling commas and percentage values.
        6. Returns the processed DataFrame.

    Example:
        df_processed = process_ca_data(uploaded_file, "2023-08-25 14:00:00", datetime.now())
    """
    df = read_file(file)

    if exclude_values:
        df = df[~df["S/N"].isin(exclude_values)]

    # Drop unnecessary columns
    drop_columns = [
        "Total time",
        "Task status",
        "Plan running time (s)",
        "Uncleaned area (ft²)",
        "Task start mode",
        "Remarks",
    ]
    df.drop(columns=drop_columns, inplace=True)
    df.insert(0, "Id", np.nan)

    selected_datetime = datetime.strptime(selected_datetime_str, "%Y-%m-%d %H:%M:%S")

    # Filter and sort DataFrame
    df["Receive task report time"] = pd.to_datetime(df["Receive task report time"])
    df_filtered = df[df["Receive task report time"] > selected_datetime]

    # Exclude values from 'S/N' if exclude_values is provided
    if exclude_values:
        df_filtered = df_filtered[~df_filtered["S/N"].isin(exclude_values)]

    df_filtered = df_filtered.sort_values(by="Receive task report time", ascending=False)
    df_filtered.reset_index(drop=True, inplace=True)

    # Create column order
    column_order = [
        "Id",
        "Robot name",
        "S/N",
        "Map name",
        "Cleaning plan",
        "User",
        "Task start time",
        "End time",
        "Task completion (%)",
        "Actual cleaning area(ft²)",
        "Total time (h)",
        "Water usage (gal)",
        "Brush (%)",
        "Filter (%)",
        "Squeegee(%)",
        "Planned crystallization area (ft²)",
        "Actual crystallization area (ft²)",
        "Cleaning plan area (ft²)",
        "Start battery level (%)",
        "End battery level (%)",
        "Receive task report time",
        "Task type",
        "Download link",
        "Work efficiency (ft²/h)",
    ]
    df_reorder = df_filtered[column_order]

    df_test = df_reorder.copy()

    # Update columns with adjusted_datetime
    columns_to_update = [
        "Planned crystallization area (ft²)",
        "Actual crystallization area (ft²)",
    ]
    df_test[columns_to_update] = df_test[columns_to_update].astype("object")
    df_test.loc[:, columns_to_update] = adjusted_datetime

    df_replaced = df_test.replace("-", 0)
    df_replaced = df_replaced.fillna("NULL")

    columns_with_comma = [
        "Work efficiency (ft²/h)",
        "Actual cleaning area(ft²)",
        "Cleaning plan area (ft²)",
    ]
    columns_with_pct = ["Brush (%)", "Filter (%)", "Squeegee(%)"]
    df_replaced[columns_with_comma] = df_replaced[columns_with_comma].apply(
        lambda col: col.astype(str).str.replace(",", "", regex=False)
    )

    # Convert gallon and feet_squared to appropriate values
    df_replaced["Water usage (gal)"] = (df_replaced["Water usage (gal)"] * gallon).apply(pd.to_numeric).round(4)
    df_replaced[columns_with_comma] = df_replaced[columns_with_comma].apply(pd.to_numeric) * feet_squared
    df_replaced[columns_with_comma] = df_replaced[columns_with_comma].astype(str).replace(",", "")
    df_replaced[columns_with_comma] = df_replaced[columns_with_comma].apply(pd.to_numeric).round(3)
    df_replaced[columns_with_pct] = df_replaced[columns_with_pct].replace("0.0", "0").replace("100.00", "100").astype(float)

    return df_replaced


def addPauseTimeNullCol(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a new column 'pause_time' with 'NULL' values between 'total_time' and 'water_usage'.

    Parameters:
        df (pandas.DataFrame): The DataFrame to which the new column will be added.

    Returns:
        pandas.DataFrame: DataFrame with the 'pause_time' column inserted in the correct position.
    """
    if "total_time" in df.columns and "water_usage" in df.columns:
        df["pause_time"] = "NULL"
        cols = list(df.columns)
        # Remove 'pause_time' first
        cols.remove("pause_time")
        # Insert it after 'total_time'
        idx = cols.index("total_time") + 1
        cols.insert(idx, "pause_time")
        df = df[cols]
    return df


def addTwoNullCols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add two new columns 'Job Id' and 'Vendor' with NaN values to the DataFrame.

    Parameters:
        df (pandas.DataFrame): The DataFrame to which the new columns will be added.

    Returns:
        pandas.DataFrame: DataFrame with the two new columns added and NaN values filled with 'NULL'.
    """
    df["job_id"] = "NULL"
    df["vendor"] = "NULL"

    return df


def convert_to_sg_time(utc_time: datetime) -> datetime:
    """
    Converts a UTC datetime object to Singapore timezone.

    Args:
        utc_time (datetime): A naive or timezone-aware UTC datetime object.

    Returns:
        datetime: Time converted to Asia/Singapore timezone.
    """
    utc = pytz.utc.localize(utc_time)
    sg_time = utc.astimezone(pytz.timezone("Asia/Singapore"))
    return sg_time


def display_time() -> str:
    """
    Displays the current Singapore time in Streamlit and returns it as a formatted string.

    Returns:
        str: Singapore time formatted as "YYYY-MM-DD HH:MM:SS".
    """
    utc_time = datetime.utcnow()
    sg_time = convert_to_sg_time(utc_time).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"##### Singapore Time: {sg_time}")
    return sg_time


def calculate_adjusted_datetime(server: str) -> str:
    """
    Calculates adjusted datetime based on the server name.

    Args:
        server (str): The name of the server (e.g., "GS SGV1").

    Returns:
        str: Adjusted datetime formatted as "YYYY-MM-DD HH:MM:SS".
    """
    # Production logic
    time_diff = timedelta(hours=9) if server == "GS SGV1" else timedelta(hours=8)

    # For local testing, use this instead:
    # time_diff = timedelta(hours=1) if server == "GS SGV1" else timedelta(hours=0)

    adjusted_datetime = (datetime.now() + time_diff).strftime("%Y-%m-%d %H:%M:%S")
    return adjusted_datetime


def process_uploaded_file(
    uploaded_file: io.BytesIO,
    selected_datetime: str,
    adjusted_datetime: datetime,
    selected_server: str,
    exclude_values: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Processes the uploaded file based on the task type, datetime, and server.

    Args:
        uploaded_file (io.BytesIO): The file uploaded by the user.
        selected_datetime (str): The user-selected datetime (e.g., "2024-01-01 12:00:00").
        adjusted_datetime (datetime): The adjusted datetime based on the server.
        selected_server (str): The selected server identifier.
        exclude_values (Optional[List[str]]): List of serial numbers to exclude.

    Returns:
        A processed DataFrame.
    """
    # Select the appropriate processing function
    task_function = process_ca_data if selected_server == "GS CA" else process_data
    df_processed = task_function(
        uploaded_file,
        selected_datetime,
        adjusted_datetime,
        exclude_values=exclude_values,
    )

    # Rename columns
    df_processed = df_processed.rename(columns=cols_to_rename)

    # Add pause_time column for "GS SGV2"
    if selected_server in ["GS SGV2", "GS AUS"]:
        df_processed = addPauseTimeNullCol(df_processed)

    # Add null columns for servers other than "GS SGV1"
    if selected_server != "GS SGV1":
        df_processed = addTwoNullCols(df_processed)

    return df_processed

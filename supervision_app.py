import pandas as pd
import streamlit as st
from datetime import datetime
import re

# Define username and password
USERNAME = "admin"
PASSWORD = "Autism123!"

# Streamlit UI
st.title("Supervision Report Processor")

# Authentication
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

def login():
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username == USERNAME and password == PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect username or password")

if not st.session_state["authenticated"]:
    login()
else:
    uploaded_file = st.file_uploader("Upload your supervision report (Excel file)", type=["xlsx"])

    if uploaded_file:
        df = pd.read_excel(uploaded_file, sheet_name='AppointmentList', header=1)

        if 'Staff Status' in df.columns:
            df = df[df['Staff Status'] != 'Archived']

        df = df[df['Status'].str.lower() != 'cancelled']
        df['Service'] = df['Service'].str.lower()
        df['Appointment Tag'] = df['Appointment Tag'].str.lower()

        df[['Start Time', 'End Time']] = df['Time'].str.extract(r'(\d{1,2}:\d{2}\s?[APMapm]{2})\s?[-to]+\s?(\d{1,2}:\d{2}\s?[APMapm]{2})')
        df['Start Time'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Start Time'], errors='coerce')
        df['End Time'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['End Time'], errors='coerce')
        df['Duration'] = pd.to_numeric(df['Duration'], errors='coerce')

        df_bt = df[df['PayCode Name'] == 'Billable (BT)']
        df_bcba = df[df['PayCode Name'] == 'Billable (LABA/BCBA)']
        df_tagged = df[df['Appointment Tag'].str.contains("bt supervision", case=False, na=False)]

        total_hours = df_bt.groupby("Client")["Duration"].sum().reset_index(name="Total Hours")
        tagged_supervision = df_tagged.groupby("Client")["Duration"].sum().reset_index(name="Tagged Supervised Hours")

        overlap_minutes = []
        for client in df_bcba["Client"].unique():
            bt_sessions = df_bt[df_bt["Client"] == client][["Date", "Start Time", "End Time"]]
            for _, bcba_row in df_bcba[df_bcba["Client"] == client].iterrows():
                for _, bt_row in bt_sessions[bt_sessions["Date"] == bcba_row["Date"]].iterrows():
                    latest_start = max(bcba_row["Start Time"], bt_row["Start Time"])
                    earliest_end = min(bcba_row["End Time"], bt_row["End Time"])
                    overlap = (earliest_end - latest_start).total_seconds() / 3600
                    if overlap > 0:
                        overlap_minutes.append({"Client": client, "Overlap Hours": overlap})

        overlap_df = pd.DataFrame(overlap_minutes)
        overlap_supervision = overlap_df.groupby("Client")["Overlap Hours"].sum().reset_index(name="Overlap Supervised Hours")

        combined = pd.merge(tagged_supervision, overlap_supervision, on="Client", how="outer").fillna(0)
        combined["Total Supervised Hours"] = combined[["Tagged Supervised Hours", "Overlap Supervised Hours"]].sum(axis=1)

        patient_report = pd.merge(total_hours, combined, on="Client", how="left").fillna(0)
        patient_report["% Supervised"] = (patient_report["Overlap Supervised Hours"] / patient_report["Total Hours"]) * 100
        patient_report["% Supervised"] = patient_report["% Supervised"].map("{:.2f}%".format)

        st.subheader("Patient Supervision")
        st.dataframe(patient_report)

        # --- BT Supervision Report ---
        bt_total = df_bt.groupby("Staff Member")["Duration"].sum().reset_index(name="Total Hours")
        bt_tagged = df_tagged.groupby("Staff Member")["Duration"].sum().reset_index(name="Tagged Supervised Hours")

        bt_overlap_minutes = []
        for staff in df_bt["Staff Member"].unique():
            bt_sessions = df_bt[df_bt["Staff Member"] == staff][["Date", "Client", "Start Time", "End Time"]]
            for _, bt_row in bt_sessions.iterrows():
                bcba_matches = df_bcba[(df_bcba["Date"] == bt_row["Date"]) & (df_bcba["Client"] == bt_row["Client"])]
                for _, bcba_row in bcba_matches.iterrows():
                    latest_start = max(bt_row["Start Time"], bcba_row["Start Time"])
                    earliest_end = min(bt_row["End Time"], bcba_row["End Time"])
                    overlap = (earliest_end - latest_start).total_seconds() / 3600
                    if overlap > 0:
                        bt_overlap_minutes.append({"Staff Member": staff, "Overlap Hours": overlap})

        bt_overlap_df = pd.DataFrame(bt_overlap_minutes)
        bt_overlap_summary = bt_overlap_df.groupby("Staff Member")["Overlap Hours"].sum().reset_index(name="Overlap Supervised Hours")

        bt_combined = pd.merge(bt_tagged, bt_overlap_summary, on="Staff Member", how="outer").fillna(0)
        bt_combined["Total Supervised Hours"] = bt_combined[["Tagged Supervised Hours", "Overlap Supervised Hours"]].sum(axis=1)

        bt_report = pd.merge(bt_total, bt_combined, on="Staff Member", how="left").fillna(0)

        # Remove LABA/BCBA staff from BT supervision report
        bcba_staff = df_bcba["Staff Member"].unique()
        bt_report = bt_report[~bt_report["Staff Member"].isin(bcba_staff)]
        bt_report["% Supervised"] = (bt_report["Overlap Supervised Hours"] / bt_report["Total Hours"]) * 100
        bt_report["% Supervised"] = bt_report["% Supervised"].map("{:.2f}%".format)

        st.subheader("BT Supervision")
        st.dataframe(bt_report)

        # Export BT Supervision Report
        bt_excel_file = "bt_supervision_report.xlsx"
        bt_report.to_excel(bt_excel_file, index=False)
        with open(bt_excel_file, "rb") as file:
            st.download_button(
                label="Download BT Supervision Report (.xlsx)",
                data=file,
                file_name=bt_excel_file,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

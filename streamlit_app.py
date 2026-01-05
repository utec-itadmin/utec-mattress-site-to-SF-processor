#!/usr/bin/env python3
"""
UTEC Data Processor - Streamlit Web Interface
Processes WooCommerce exports for Salesforce import
"""

import streamlit as st
import pandas as pd
import os
import io
import zipfile
from datetime import datetime
from process_new_data_file import (
    clean_unicode,
    fix_zip_code,
    is_valid_street_address,
    correct_address
)
import csv
import tempfile

# Page configuration
st.set_page_config(
    page_title="UTEC Mattress Site to SF Processor",
    page_icon="🛏️",
    layout="wide",
    initial_sidebar_state="collapsed"
)


# ============================================================
# PASSWORD PROTECTION
# ============================================================

def check_password():
    """
    Returns True if the user has entered the correct password.
    Displays a login form if not authenticated.
    """
    def password_entered():
        """Checks whether the password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password in session
        else:
            st.session_state["password_correct"] = False

    # Return True if already authenticated
    if st.session_state.get("password_correct", False):
        return True

    # Show login form
    st.markdown("""
        <div style='text-align: center; padding: 2rem;'>
            <h1>🔒 UTEC Mattress Site to SF Processor</h1>
            <p style='color: #666; font-size: 1.2rem;'>Please enter the password to continue</p>
        </div>
    """, unsafe_allow_html=True)

    # Center the password input
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.text_input(
            "Password",
            type="password",
            key="password",
            on_change=password_entered,
            label_visibility="collapsed",
            placeholder="Enter password..."
        )

        # Show error message if password was wrong
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("❌ Incorrect password. Please try again.")

    # Add some spacing and info
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.info("💡 **Note**: This app processes mattress recycling customer data from the website for Salesforce import. All data is secure and private.")

    return False


# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        margin: 1rem 0;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)


def process_uploaded_file(uploaded_file):
    """
    Process the uploaded WooCommerce CSV file through the pipeline.
    Returns statistics and paths to output files.
    """
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()

    # Save uploaded file
    input_path = os.path.join(temp_dir, uploaded_file.name)
    with open(input_path, 'wb') as f:
        f.write(uploaded_file.getbuffer())

    # Process the file
    stats = run_pipeline(input_path, temp_dir)

    # Generate output file paths
    base_filename = os.path.basename(uploaded_file.name)
    output_files = {
        'all_records': os.path.join(temp_dir, f"Processed-allrecords-corrected-{base_filename}"),
        'clean_records': os.path.join(temp_dir, f"Processed-cleanrecords-{base_filename}"),
        'address_fixes': os.path.join(temp_dir, f"Processed-addressfixes-{base_filename}"),
        'invalid_records': os.path.join(temp_dir, f"Processed-invalidrecords-{base_filename}")
    }

    return stats, output_files, temp_dir


def run_pipeline(input_filename, output_dir):
    """
    Run the processing pipeline on the input file.
    Modified version of process_new_data_file.py that works with Streamlit.
    """
    import csv
    import re

    base_filename = os.path.basename(input_filename)

    # Track transformations
    mattress_replacements = 0
    boxspring_replacements = 0

    # Step 1: Apply transformations
    output_all_records = os.path.join(output_dir, f"Processed-allrecords-{base_filename}")

    with open(input_filename, 'r', encoding='utf-8') as infile, \
         open(output_all_records, 'w', encoding='utf-8', newline='') as outfile:

        reader = csv.DictReader(infile)

        # Rename "Order #" to "Donation Transaction ID"
        original_fieldnames = list(reader.fieldnames)
        renamed_fieldnames = ['Donation Transaction ID' if f == 'Order #' else f for f in original_fieldnames]

        # Add new fields
        fieldnames = ['Export Index'] + renamed_fieldnames + [
            'Donation Name',
            'Donation Record Type Name',
            'Donation Stage',
            'Campaign Name',
            'Donation Donor',
            'Contact1 Mattress Customer',
            'Donation Share with non-development'
        ]

        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        export_index = 1
        for row in reader:
            # Rename field
            if 'Order #' in row:
                row['Donation Transaction ID'] = row.pop('Order #')

            row['Export Index'] = export_index
            export_index += 1

            # Clean unicode
            for key in row:
                if row[key]:
                    row[key] = clean_unicode(row[key])

            # Fix zip codes
            if 'Home Zip/Postal Code' in row:
                row['Home Zip/Postal Code'] = fix_zip_code(row['Home Zip/Postal Code'])
            if 'Donation Pick up Zip' in row:
                row['Donation Pick up Zip'] = fix_zip_code(row['Donation Pick up Zip'])

            # Replace mattress and boxspring types
            if 'Donation Type(s) of Mattresses' in row:
                if row['Donation Type(s) of Mattresses'] == 'Crib or Toddler Bed':
                    row['Donation Type(s) of Mattresses'] = 'Other'
                    mattress_replacements += 1

            if 'Donation Types of Boxspring(s)' in row:
                if row['Donation Types of Boxspring(s)'] == 'King  (split 2pcs)':
                    row['Donation Types of Boxspring(s)'] = 'King'
                    boxspring_replacements += 1

            # Update pickup location
            pickup_location = row.get('Pickup Location', '')
            if pickup_location:
                row['Donation Pick up/Drop Off'] = f"{pickup_location} Pick Up"

            # Add fixed fields
            row['Donation Name'] = 'Mattress'
            row['Donation Record Type Name'] = 'Curbside Mattress Process'
            row['Donation Stage'] = 'Received'
            row['Campaign Name'] = 'Mattress Recycling'
            row['Donation Donor'] = 'Contact1'
            row['Contact1 Mattress Customer'] = 'TRUE'
            row['Donation Share with non-development'] = 'TRUE'

            writer.writerow(row)

    total_records = export_index - 1

    # Step 2: Validate and correct addresses
    invalid_records = []
    valid_records = []
    still_invalid_records = []

    temp_corrected_file = os.path.join(output_dir, f"temp-corrected-{base_filename}")

    with open(output_all_records, 'r', encoding='utf-8') as infile, \
         open(temp_corrected_file, 'w', encoding='utf-8', newline='') as outfile:

        reader = csv.DictReader(infile)
        fieldnames = list(reader.fieldnames) + ['home street invalid', 'pickup street invalid']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            home_street = row.get('Home Street', '')
            pickup_street = row.get('Donation Pick up Address', '')

            home_originally_invalid = not is_valid_street_address(home_street)
            pickup_originally_invalid = not is_valid_street_address(pickup_street)
            originally_invalid = home_originally_invalid or pickup_originally_invalid

            original_home = home_street
            original_pickup = pickup_street

            corrected_home, home_was_corrected = correct_address(home_street)
            corrected_pickup, pickup_was_corrected = correct_address(pickup_street)

            row['Home Street'] = corrected_home
            row['Donation Pick up Address'] = corrected_pickup

            home_valid_after = is_valid_street_address(corrected_home)
            pickup_valid_after = is_valid_street_address(corrected_pickup)

            row['home street invalid'] = '' if home_valid_after else '1'
            row['pickup street invalid'] = '' if pickup_valid_after else '1'

            if originally_invalid:
                record_info = {
                    'Export Index': row['Export Index'],
                    'Home Street (Before)': original_home,
                    'Donation Pick up Address (Before)': original_pickup,
                    'Donation Transaction ID': row.get('Donation Transaction ID', ''),
                    'Home Street (After)': corrected_home,
                    'Donation Pick up Address (After)': corrected_pickup,
                    'Address Corrected': 'Yes' if (home_valid_after and pickup_valid_after) else 'No'
                }
                invalid_records.append(record_info)

            if home_valid_after and pickup_valid_after:
                valid_records.append(row.copy())
            else:
                still_invalid_records.append(row.copy())

            writer.writerow(row)

    # Step 3: Create output files
    output_addressfixes = os.path.join(output_dir, f"Processed-addressfixes-{base_filename}")
    if invalid_records:
        with open(output_addressfixes, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=invalid_records[0].keys())
            writer.writeheader()
            writer.writerows(invalid_records)

    output_cleanrecords = os.path.join(output_dir, f"Processed-cleanrecords-{base_filename}")
    if valid_records:
        with open(output_cleanrecords, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(valid_records)

    output_invalidrecords = os.path.join(output_dir, f"Processed-invalidrecords-{base_filename}")
    if still_invalid_records:
        with open(output_invalidrecords, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(still_invalid_records)

    final_all_records = os.path.join(output_dir, f"Processed-allrecords-corrected-{base_filename}")
    os.rename(temp_corrected_file, final_all_records)

    # Calculate statistics
    corrected_count = len([r for r in invalid_records if r['Address Corrected'] == 'Yes'])

    return {
        'total_records': total_records,
        'invalid_count': len(invalid_records),
        'corrected_count': corrected_count,
        'valid_count': len(valid_records),
        'still_invalid_count': len(still_invalid_records),
        'mattress_replacements': mattress_replacements,
        'boxspring_replacements': boxspring_replacements
    }


def create_zip_file(file_paths):
    """Create a ZIP file containing all output files."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for name, path in file_paths.items():
            if os.path.exists(path):
                zip_file.write(path, os.path.basename(path))
    zip_buffer.seek(0)
    return zip_buffer


# Main App UI
def main():
    # Header
    st.markdown('<div class="main-header">🛏️ UTEC Mattress Site to SF Processor</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Process mattress recycling website exports for Salesforce import</div>', unsafe_allow_html=True)

    # Instructions
    with st.expander("ℹ️ How to Use", expanded=False):
        st.markdown("""
        ### Instructions:
        1. **Upload** your WooCommerce export CSV file
        2. **Click** the "Process File" button
        3. **Review** the processing statistics
        4. **Download** the clean records file for Salesforce import
        5. **Review** any invalid records that need manual correction

        ### Output Files:
        - **Clean Records**: Ready for Salesforce import (use this file!)
        - **Address Fixes**: Shows what addresses were corrected
        - **Invalid Records**: Needs manual review (send to Sarah)
        - **All Records**: Complete archive with all transformations
        """)

    # File Upload
    st.markdown("### 📁 Step 1: Upload File")
    uploaded_file = st.file_uploader(
        "Choose your WooCommerce CSV export file",
        type=['csv'],
        help="Select the CSV file exported from WooCommerce"
    )

    if uploaded_file is not None:
        # Show file info
        st.success(f"✓ File uploaded: **{uploaded_file.name}** ({uploaded_file.size:,} bytes)")

        # Process button
        st.markdown("### ⚙️ Step 2: Process Data")
        if st.button("🚀 Process File", type="primary", use_container_width=True):

            # Progress indicator
            with st.spinner("Processing data... This may take a minute."):
                try:
                    # Run processing
                    stats, output_files, temp_dir = process_uploaded_file(uploaded_file)

                    # Store in session state
                    st.session_state['stats'] = stats
                    st.session_state['output_files'] = output_files
                    st.session_state['temp_dir'] = temp_dir
                    st.session_state['processed'] = True

                except Exception as e:
                    st.error(f"❌ Error processing file: {str(e)}")
                    st.exception(e)
                    return

    # Display results if processed
    if st.session_state.get('processed', False):
        stats = st.session_state['stats']
        output_files = st.session_state['output_files']

        st.markdown("---")
        st.markdown("### ✅ Processing Complete!")

        # Statistics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Records", f"{stats['total_records']:,}")

        with col2:
            st.metric("Valid Records", f"{stats['valid_count']:,}",
                     delta=f"{(stats['valid_count']/stats['total_records']*100):.1f}%")

        with col3:
            st.metric("Addresses Fixed", stats['corrected_count'])

        with col4:
            st.metric("Need Review", stats['still_invalid_count'])

        # Value Replacements
        if stats['mattress_replacements'] > 0 or stats['boxspring_replacements'] > 0:
            st.markdown("#### 🔄 Value Replacements")
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**{stats['mattress_replacements']}** mattress types standardized\n\n(Crib or Toddler Bed → Other)")
            with col2:
                st.info(f"**{stats['boxspring_replacements']}** boxspring types standardized\n\n(King (split 2pcs) → King)")

        # Downloads Section
        st.markdown("---")
        st.markdown("### 📥 Step 3: Download Files")

        # Primary download - Clean Records
        st.markdown("#### 🎯 Primary File for Salesforce")
        if os.path.exists(output_files['clean_records']):
            with open(output_files['clean_records'], 'rb') as f:
                st.download_button(
                    label=f"⬇️ Download Clean Records ({stats['valid_count']:,} records)",
                    data=f,
                    file_name=os.path.basename(output_files['clean_records']),
                    mime='text/csv',
                    type="primary",
                    use_container_width=True,
                    help="Use this file for Salesforce import"
                )

        st.markdown("#### 📊 Quality Assurance Files")
        col1, col2 = st.columns(2)

        # Address Fixes
        with col1:
            if os.path.exists(output_files['address_fixes']):
                with open(output_files['address_fixes'], 'rb') as f:
                    st.download_button(
                        label=f"📋 Address Fixes Report ({stats['invalid_count']} records)",
                        data=f,
                        file_name=os.path.basename(output_files['address_fixes']),
                        mime='text/csv',
                        use_container_width=True,
                        help="Shows before/after for corrected addresses"
                    )

        # Invalid Records
        with col2:
            if os.path.exists(output_files['invalid_records']) and stats['still_invalid_count'] > 0:
                with open(output_files['invalid_records'], 'rb') as f:
                    st.download_button(
                        label=f"⚠️ Invalid Records ({stats['still_invalid_count']} records)",
                        data=f,
                        file_name=os.path.basename(output_files['invalid_records']),
                        mime='text/csv',
                        use_container_width=True,
                        help="Needs manual review - send to Sarah"
                    )

        # All Records Archive
        st.markdown("#### 📁 Archive")
        if os.path.exists(output_files['all_records']):
            with open(output_files['all_records'], 'rb') as f:
                st.download_button(
                    label=f"📦 All Records (Complete Archive)",
                    data=f,
                    file_name=os.path.basename(output_files['all_records']),
                    mime='text/csv',
                    use_container_width=True,
                    help="Complete processing results with all transformations"
                )

        # Download All as ZIP
        st.markdown("#### 📦 Download All Files")
        zip_data = create_zip_file(output_files)
        st.download_button(
            label="⬇️ Download All Files (ZIP)",
            data=zip_data,
            file_name=f"UTEC-Processed-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
            mime='application/zip',
            use_container_width=True
        )

        # Invalid Records Preview
        if stats['still_invalid_count'] > 0:
            st.markdown("---")
            st.markdown("### ⚠️ Invalid Records Requiring Manual Review")
            st.warning(f"**{stats['still_invalid_count']} records** have address issues that couldn't be auto-corrected. Download the Invalid Records file and send to Sarah for cleanup.")

            # Show preview
            with st.expander("Preview Invalid Records"):
                df = pd.read_csv(output_files['invalid_records'])
                st.dataframe(
                    df[['Export Index', 'Contact1 First Name', 'Contact1 Last Name',
                        'Home Street', 'Donation Pick up Address', 'Donation Transaction ID']].head(10),
                    use_container_width=True
                )

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; font-size: 0.9rem;'>
    UTEC Mattress Site to SF Processor v1.0 | Processes mattress recycling website exports for Salesforce import
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    # Check password before running the app
    if check_password():
        main()

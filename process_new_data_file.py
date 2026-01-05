#!/usr/bin/env python3
"""
Reusable pipeline script for processing new UTEC donation data files.
Applies data cleaning, validation, and correction steps.

Usage:
    python3 process_new_data_file.py <input_filename>
"""

import csv
import re
import sys
import os
from typing import Tuple, List, Dict


def clean_unicode(text) -> str:
    """Clean unicode characters from text."""
    if not text:
        return text

    # If not a string, return as-is
    if not isinstance(text, str):
        return text

    cleaned = text
    # Replace smart quotes with regular quotes
    cleaned = cleaned.replace('\u2018', "'").replace('\u2019', "'")
    cleaned = cleaned.replace('\u201C', '"').replace('\u201D', '"')
    # Replace non-breaking spaces with regular spaces
    cleaned = cleaned.replace('\xa0', ' ')
    # Replace unicode dashes with regular hyphens
    cleaned = cleaned.replace('\u2013', '-').replace('\u2014', '-')

    return cleaned


def fix_zip_code(zip_code: str) -> str:
    """Fix zip code format - add leading 0 if only 4 digits."""
    if not zip_code or not isinstance(zip_code, str):
        return zip_code

    # Remove whitespace and tabs
    cleaned = zip_code.strip()

    # If exactly 4 digits, add leading 0
    if re.match(r'^\d{4}$', cleaned):
        return f"0{cleaned}"

    return zip_code


def is_valid_street_address(address: str) -> bool:
    """Validate if a street address follows common US address formats."""
    if not address or address.strip() == '':
        return True

    address = address.strip()

    # PO Box pattern
    if re.match(r'^P\.?\s*O\.?\s*Box\s+\d+$', address, re.IGNORECASE):
        return True

    # Standard address pattern
    standard_pattern = r'^\d+[a-zA-Z]?[\s\.\,\-]+\w'
    if re.match(standard_pattern, address):
        if len(address) >= 5:
            has_letters = bool(re.search(r'[a-zA-Z]', address[re.search(r'\d+', address).end():]))
            return has_letters

    return False


def correct_address(address: str) -> Tuple[str, bool]:
    """Attempt to correct common address formatting issues."""
    if not address or address.strip() == '':
        return address, False

    original = address.strip()
    corrected = original
    was_corrected = False

    # Rule 1: Remove duplicate text
    words = corrected.split()
    if len(words) >= 4:
        mid = len(words) // 2
        first_half = ' '.join(words[:mid]).lower()
        second_half = ' '.join(words[mid:mid*2]).lower()
        if first_half == second_half:
            corrected = ' '.join(words[:mid])
            was_corrected = True

    # Rule 2: Replace common typos and special characters
    if '!' in corrected:
        corrected = corrected.replace('!', '')
        was_corrected = True

    # Rule 3: Fix "Roaf" -> "Road"
    if 'Roaf' in corrected:
        corrected = corrected.replace('Roaf', 'Road')
        was_corrected = True

    # Rule 4: Handle "I" at start that should be "1"
    match = re.match(r'^I\s+([A-Z][a-z]+.*)', corrected)
    if match:
        corrected = f"1 {match.group(1)}"
        was_corrected = True

    # Rule 5: Fix missing space between number and street name
    match = re.match(r'^(\d+)([A-Za-z][a-zA-Z]+.*)$', corrected)
    if match:
        corrected = f"{match.group(1)} {match.group(2)}"
        was_corrected = True

    # Rule 6: Handle street numbers with slashes
    match = re.match(r'^(\d+/\d+)([A-Za-z].*)$', corrected)
    if match:
        corrected = f"{match.group(1)} {match.group(2)}"
        was_corrected = True

    # Rule 7: Clean up extra spaces
    if '  ' in corrected:
        corrected = re.sub(r'\s+', ' ', corrected)
        was_corrected = True

    # Rule 8: Flag incomplete addresses (just a number)
    if re.match(r'^\d+\s*$', corrected):
        corrected = f"{corrected} [INCOMPLETE ADDRESS]"
        was_corrected = True

    # Rule 9: Flag addresses missing street numbers
    if re.match(r'^[A-Za-z]', corrected) and not re.match(r'^P\.?O\.?\s*Box', corrected, re.IGNORECASE):
        corrected = f"[MISSING NUMBER] {corrected}"
        was_corrected = True

    return corrected.strip(), was_corrected


def process_data_file(input_filename: str) -> Dict:
    """
    Main processing function that applies all transformations.
    Returns statistics about the processing.
    """
    print(f"Processing file: {input_filename}")
    print("=" * 80)

    base_filename = os.path.basename(input_filename)

    # Step 1: Read input file and apply initial transformations
    print("\nStep 1: Reading input file and applying transformations...")

    output_all_records = f"Processed-allrecords-{base_filename}"

    # Track value replacements
    mattress_replacements = 0
    boxspring_replacements = 0

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
            # Rename "Order #" to "Donation Transaction ID"
            if 'Order #' in row:
                row['Donation Transaction ID'] = row.pop('Order #')

            # Add Export Index
            row['Export Index'] = export_index
            export_index += 1

            # Clean unicode in all fields
            for key in row:
                if row[key]:
                    row[key] = clean_unicode(row[key])

            # Fix zip codes - add leading 0 if 4 digits
            if 'Home Zip/Postal Code' in row:
                row['Home Zip/Postal Code'] = fix_zip_code(row['Home Zip/Postal Code'])
            if 'Donation Pick up Zip' in row:
                row['Donation Pick up Zip'] = fix_zip_code(row['Donation Pick up Zip'])

            # Replace mattress and boxspring type values
            if 'Donation Type(s) of Mattresses' in row:
                if row['Donation Type(s) of Mattresses'] == 'Crib or Toddler Bed':
                    row['Donation Type(s) of Mattresses'] = 'Other'
                    mattress_replacements += 1

            if 'Donation Types of Boxspring(s)' in row:
                if row['Donation Types of Boxspring(s)'] == 'King  (split 2pcs)':
                    row['Donation Types of Boxspring(s)'] = 'King'
                    boxspring_replacements += 1

            # Update Donation Pick up/Drop Off field
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
    print(f"✓ Processed {total_records:,} records")
    print(f"✓ Value replacements: {mattress_replacements} mattress types, {boxspring_replacements} boxspring types")
    print(f"✓ Saved to: {output_all_records}")

    # Step 2: Validate and correct addresses
    print("\nStep 2: Validating and correcting addresses...")

    invalid_records = []
    valid_records = []  # Changed from corrected_records to valid_records (ALL valid)
    still_invalid_records = []

    temp_corrected_file = f"temp-corrected-{base_filename}"

    with open(output_all_records, 'r', encoding='utf-8') as infile, \
         open(temp_corrected_file, 'w', encoding='utf-8', newline='') as outfile:

        reader = csv.DictReader(infile)
        fieldnames = list(reader.fieldnames) + ['home street invalid', 'pickup street invalid']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            home_street = row.get('Home Street', '')
            pickup_street = row.get('Donation Pick up Address', '')

            # Check if originally invalid
            home_originally_invalid = not is_valid_street_address(home_street)
            pickup_originally_invalid = not is_valid_street_address(pickup_street)
            originally_invalid = home_originally_invalid or pickup_originally_invalid

            # Store original values
            original_home = home_street
            original_pickup = pickup_street

            # Attempt corrections
            corrected_home, home_was_corrected = correct_address(home_street)
            corrected_pickup, pickup_was_corrected = correct_address(pickup_street)

            # Update row with corrected values
            row['Home Street'] = corrected_home
            row['Donation Pick up Address'] = corrected_pickup

            # Validate after correction
            home_valid_after = is_valid_street_address(corrected_home)
            pickup_valid_after = is_valid_street_address(corrected_pickup)

            row['home street invalid'] = '' if home_valid_after else '1'
            row['pickup street invalid'] = '' if pickup_valid_after else '1'

            # Track records that were originally invalid for the address fixes report
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

            # Track ALL valid records (both originally valid AND successfully corrected)
            if home_valid_after and pickup_valid_after:
                valid_records.append(row.copy())
            else:
                still_invalid_records.append(row.copy())

            writer.writerow(row)

    # Step 3: Create output files
    print("\nStep 3: Creating output files...")

    # Address fixes file
    output_addressfixes = f"Processed-addressfixes-{base_filename}"
    with open(output_addressfixes, 'w', encoding='utf-8', newline='') as f:
        if invalid_records:
            writer = csv.DictWriter(f, fieldnames=invalid_records[0].keys())
            writer.writeheader()
            writer.writerows(invalid_records)
    print(f"✓ Created: {output_addressfixes} ({len(invalid_records)} records)")

    # Clean records file - ALL valid records (originally valid + successfully corrected)
    output_cleanrecords = f"Processed-cleanrecords-{base_filename}"
    if valid_records:
        with open(output_cleanrecords, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(valid_records)
    print(f"✓ Created: {output_cleanrecords} ({len(valid_records)} records)")

    # Invalid records file
    output_invalidrecords = f"Processed-invalidrecords-{base_filename}"
    if still_invalid_records:
        with open(output_invalidrecords, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(still_invalid_records)
    print(f"✓ Created: {output_invalidrecords} ({len(still_invalid_records)} records)")

    # Rename temp file to final name (all records with corrections)
    final_all_records = f"Processed-allrecords-corrected-{base_filename}"
    os.rename(temp_corrected_file, final_all_records)
    print(f"✓ Created: {final_all_records} (all {total_records:,} records with corrections)")

    # Calculate statistics
    # How many originally invalid records were successfully corrected
    corrected_count = len([r for r in invalid_records if r['Address Corrected'] == 'Yes'])

    # Return statistics
    return {
        'total_records': total_records,
        'invalid_count': len(invalid_records),
        'corrected_count': corrected_count,
        'valid_count': len(valid_records),
        'still_invalid_count': len(still_invalid_records),
        'mattress_replacements': mattress_replacements,
        'boxspring_replacements': boxspring_replacements
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 process_new_data_file.py <input_filename>")
        sys.exit(1)

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found")
        sys.exit(1)

    # Run the processing
    stats = process_data_file(input_file)

    # Display summary
    print("\n" + "=" * 80)
    print("PROCESSING SUMMARY")
    print("=" * 80)
    print(f"Total records processed: {stats['total_records']:,}")
    print(f"\nValue Replacements:")
    print(f"  Mattress types replaced: {stats['mattress_replacements']} ('Crib or Toddler Bed' → 'Other')")
    print(f"  Boxspring types replaced: {stats['boxspring_replacements']} ('King  (split 2pcs)' → 'King')")
    print(f"\nAddress Validation:")
    print(f"  Records with invalid addresses: {stats['invalid_count']:,}")
    print(f"  Records successfully corrected: {stats['corrected_count']:,}")
    print(f"  Records still invalid: {stats['still_invalid_count']:,}")
    print(f"\nClean Records (valid data):")
    print(f"  Total valid records: {stats['valid_count']:,}")
    print(f"  Originally valid: {stats['valid_count'] - stats['corrected_count']:,}")
    print(f"  Fixed from invalid: {stats['corrected_count']:,}")
    print(f"\nCorrection success rate: {(stats['corrected_count'] / stats['invalid_count'] * 100) if stats['invalid_count'] > 0 else 0:.1f}%")
    print("=" * 80)

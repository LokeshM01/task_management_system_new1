import csv
from django.contrib.auth.hashers import make_password
import os
import django

# Set up Django settings (required to use Django's hashers)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "task_manage.settings")
django.setup()

# Define the input CSV and output CSV file names
input_csv_file = 'users_with_credentials.csv'  # CSV containing 'username' and 'password'
output_csv_file = 'output_file.csv'  # CSV to save hashed passwords

# Open the input CSV file and the output CSV file
with open(input_csv_file, mode='r', newline='', encoding='utf-8') as infile:
    reader = csv.DictReader(infile)
    
    # Open the output CSV file to write the results
    with open(output_csv_file, mode='w', newline='', encoding='utf-8') as outfile:
        fieldnames = reader.fieldnames + ['hashed_password']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # Process each row from the input CSV
        for row in reader:
            username = row['username']
            plain_password = row['password']
            
            # Hash the password using Django's hashing system
            hashed_password = make_password(plain_password)
            
            # Write the username and hashed password to the output CSV
            row['hashed_password'] = hashed_password
            writer.writerow(row)

print(f"CSV file with hashed passwords has been created: {output_csv_file}")

import pandas as pd
import csv
import re

# Read the CSV file
df = pd.read_csv('jobs.csv')

# Clean and format the data
def clean_text(text):
    """Clean and normalize text data"""
    if pd.isna(text):
        return ''
    text = str(text).strip()
    # Remove extra whitespace and newlines
    text = ' '.join(text.split())
    # Remove duplicate info
    text = re.sub(r'Berlin, Berlin', 'Berlin', text)
    return text

# Apply cleaning to all columns
for col in df.columns:
    df[col] = df[col].apply(clean_text)

# Remove rows where title or company are empty/unknown
df = df[~((df['title'].str.contains('Unknown', case=False, na=False)) | 
          (df['company'].str.contains('Unknown', case=False, na=False)))]

# Remove duplicates
df = df.drop_duplicates(subset=['title', 'company'], keep='first')

# Shorten descriptions to first sentence or 150 chars
def truncate_description(desc):
    if pd.isna(desc) or desc == '':
        return 'No description available'
    # Try to find first sentence
    sentences = desc.split('·')
    if sentences:
        first_part = sentences[0].strip()
        if len(first_part) > 150:
            return first_part[:150] + '...'
        return first_part
    return desc[:150] + '...' if len(desc) > 150 else desc

df['description'] = df['description'].apply(truncate_description)

# Reorder columns
df = df[['title', 'company', 'location', 'description']]

# Save as properly formatted CSV
df.to_csv('jobs_formatted.csv', index=False, quoting=csv.QUOTE_MINIMAL)

print("✅ CSV formatted successfully!")
print(f"📊 Total jobs: {len(df)}")
print("\n📋 Preview of formatted data:\n")
print(df.to_string(index=False))

# Also save as nicely formatted text table
print("\n\n" + "="*150)
print("FORMATTED JOB LISTINGS TABLE".center(150))
print("="*150)

for idx, row in df.iterrows():
    print(f"\n{'─'*150}")
    print(f"Job #{idx + 1} - {row['company'].upper()}")
    print(f"{'─'*150}")
    print(f"Title:       {row['title']}")
    print(f"Company:     {row['company']}")
    print(f"Location:    {row['location']}")
    print(f"Description: {row['description']}")

print(f"\n{'='*150}\n")

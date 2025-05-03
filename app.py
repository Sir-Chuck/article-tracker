import streamlit as st
from datetime import date, timedelta, datetime
import requests
from bs4 import BeautifulSoup
import csv
import time
import pandas as pd
from io import StringIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
from googleapiclient.http import MediaIoBaseUpload

SHEETS_FOLDER_ID = '1HyRPfL6ziPQ-MHt8amJLhm9G5MSeIk6b'

st.set_page_config(page_title="New Yorker Scraper", layout="centered")
st.title("📰 New Yorker Article Scraper")
st.write("Select a date range and click 'Run Scraper' to generate a Google Sheet.")

start_date = st.date_input("Start Date", value=date(2025, 1, 1))
end_date = st.date_input("End Date", value=date.today())
run = st.button("▶️ Run Scraper")

def fetch_sitemap(year, month, week):
    url = f"https://www.newyorker.com/sitemap.xml?month={month}&week={week}&year={year}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    return None

def parse_sitemap(xml_content):
    soup = BeautifulSoup(xml_content, 'xml')
    return [url.loc.text for url in soup.find_all('url')]

def extract_article_details(article_url):
    try:
        res = requests.get(article_url, timeout=10)
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.content, 'html.parser')

        title = soup.find('h1').get_text(strip=True) if soup.find('h1') else 'No title'
        author_tag = soup.find('span', class_='RiverByline-name') or soup.find('a', class_='byline__name') or soup.find('p', class_='ContributorBio-name')
        author = author_tag.get_text(strip=True) if author_tag else soup.find('meta', {'name': 'author'}).get('content', 'Unknown') if soup.find('meta', {'name': 'author'}) else 'Unknown'
        date_tag = soup.find('meta', {'property': 'article:published_time'})
        pub_date = date_tag['content'].split('T')[0] if date_tag and 'content' in date_tag.attrs else 'Unknown'

        return {
            'title': title,
            'author': author,
            'publication_date': pub_date,
            'url': article_url
        }
    except:
        return None

def collect_articles(start_date, end_date):
    delta = timedelta(weeks=1)
    current = start_date
    articles = []
    total_weeks = (end_date - start_date).days // 7 + 1
    bar = st.progress(0)

    for week_idx in range(total_weeks):
        year, month = current.year, current.month
        week = (current.day - 1) // 7 + 1
        xml = fetch_sitemap(year, month, week)
        if xml:
            urls = parse_sitemap(xml)
            for url in urls:
                details = extract_article_details(url)
                if details:
                    articles.append(details)
        current += delta
        bar.progress((week_idx + 1) / total_weeks)

    return articles

def upload_to_gdrive(df, filename):
    # Convert DataFrame to CSV in UTF-8 bytes
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False, encoding="utf-8")
    csv_buffer.seek(0)

    # Build Google Drive service
    credentials = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    service = build("drive", "v3", credentials=credentials)

    # Metadata for Google Drive upload
    file_metadata = {
        "name": filename,
        "mimeType": "application/vnd.google-apps.spreadsheet"
    }

    # Upload the CSV from memory
    media = MediaIoBaseUpload(csv_buffer, mimetype="text/csv")
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="webViewLink"
    ).execute()

    return uploaded_file["webViewLink"]
if run:
    if end_date < start_date:
        st.error("End date must be after start date.")
    else:
        st.info(f"Scraping articles from {start_date} to {end_date}...")
        t0 = time.time()
        articles = collect_articles(start_date, end_date)
        runtime = round((time.time() - t0) / 60, 2)

        if not articles:
            st.warning("No articles found.")
        else:
            df = pd.DataFrame(articles)
            st.success(f"✅ {len(df)} articles scraped in {runtime} minutes.")
            st.dataframe(df.head())
            link = upload_to_gdrive(df, "newyorker_articles.csv")
            st.markdown(f"📄 [View Google Sheet]({link})")

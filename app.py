import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pandas as pd
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from dateutil.rrule import rrule, WEEKLY

st.set_page_config(page_title="New Yorker Article Tracker")
st.title("📰 New Yorker Article Tracker")

# 📅 Date inputs
col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", datetime(2025, 1, 1))
with col2:
    end_date = st.date_input("End date", datetime.today())

# 📝 Persistent filename input
if "default_filename" not in st.session_state:
    st.session_state.default_filename = f"newyorker_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

filename = st.text_input("File name to upload to Drive:", key="default_filename")

# 🔁 Generate weekly sitemap URLs across the full date range
def get_weekly_sitemap_urls(start_date, end_date):
    sitemap_urls = []
    for dt in rrule(WEEKLY, dtstart=start_date, until=end_date):
        year = dt.year
        month = dt.month
        week = (dt.day - 1) // 7 + 1
        url = f"https://www.newyorker.com/sitemap.xml?year={year}&month={month}&week={week}"
        sitemap_urls.append(url)
    return sitemap_urls

# ☁️ Upload CSV to Google Drive
def upload_to_gdrive(df, filename):
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False, encoding="utf-8")
    buffer.seek(0)

    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    drive_service = build("drive", "v3", credentials=credentials)

    folder_id = "1HyRPfL6ziPQ-MHt8amJLhm9G5MSeIk6b"  # 🔁 Replace if needed
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(buffer, mimetype="text/csv")

    uploaded_file = drive_service.files().create(
        body=file_metadata, media_body=media, fields="webViewLink"
    ).execute()

    return uploaded_file["webViewLink"]

# ▶️ Main tracker logic
if st.button("Track Articles"):
    if end_date < start_date:
        st.warning("⚠️ End date must be after start date.")
    else:
        with st.status("🔎 Tracking articles..."):
            all_articles = []
            seen_urls = set()

            for sitemap_url in get_weekly_sitemap_urls(start_date, end_date):
                try:
                    response = requests.get(sitemap_url)
                    soup = BeautifulSoup(response.content, "xml")
                    urls = soup.find_all("url")
                    
                    for url in urls:
                        loc = url.find("loc").text
                        lastmod = url.find("lastmod").text[:10]
                        pub_date = datetime.strptime(lastmod, "%Y-%m-%d").date()

                        if start_date <= pub_date <= end_date and loc not in seen_urls:
                            article_resp = requests.get(loc)
                            article_soup = BeautifulSoup(article_resp.content, "html.parser")
                            title_tag = article_soup.find("h1")
                            author_tag = article_soup.find("a", attrs={"data-testid": "BylineName"})

                            title = title_tag.text.strip() if title_tag else "Unknown"
                            author = author_tag.text.strip() if author_tag else "Unknown"

                            all_articles.append({
                                "Title": title,
                                "Author": author,
                                "Publication Date": pub_date.isoformat(),
                                "URL": loc
                            })
                            seen_urls.add(loc)

                except Exception as e:
                    st.warning(f"⚠️ Failed to load or parse {sitemap_url}: {e}")

            if not all_articles:
                st.info("No articles found in that date range.")
            else:
                df = pd.DataFrame(all_articles)
                st.success(f"✅ Found {len(df)} articles.")
                st.dataframe(df, use_container_width=True)

                if filename:
                    link = upload_to_gdrive(df, filename)
                    st.success("✅ File uploaded to Google Drive!")
                    st.markdown(f"[📂 Open File]({link})")
                else:
                    st.warning("⚠️ Please enter a file name before uploading.")

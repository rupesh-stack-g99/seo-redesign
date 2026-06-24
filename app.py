import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
import bs4
import pandas as pd
import requests
import streamlit as st

# --- Helper Functions ---


def get_slug_from_url(url):
    """Extracts purely the path slug from a URL, ignoring the domain."""
    parsed_url = urlparse(url)
    path = parsed_url.path
    slug = path.strip("/").lower()
    return slug if slug else "homepage"


def extract_urls_from_sitemap_url(sitemap_url):
    """Fetches and reads a user-provided sitemap link directly."""
    urls = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(sitemap_url, headers=headers, timeout=15)
        if response.status_code != 200:
            st.error(
                f"Could not read sitemap. Status code: {response.status_code}"
            )
            return []

        # Parse XML Content
        root = ET.fromstring(response.content)
        namespaces = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Look for nested sitemaps (Sitemap Index)
        sub_sitemaps = root.findall(".//ns:sitemap/ns:loc", namespaces)
        if sub_sitemaps:
            for sub in sub_sitemaps:
                sub_res = requests.get(sub.text.strip(), headers=headers, timeout=15)
                if sub_res.status_code == 200:
                    sub_root = ET.fromstring(sub_res.content)
                    for loc_tag in sub_root.findall(
                        ".//ns:url/ns:loc", namespaces
                    ):
                        urls.add(loc_tag.text.strip())
        else:
            # Regular Single Sitemap
            for loc_tag in root.findall(".//ns:url/ns:loc", namespaces):
                urls.add(loc_tag.text.strip())

        return list(urls)

    except Exception as e:
        st.error(f"Error reading XML from sitemap link: {e}")
        return []


def scrape_website_1_seo(url):
    """Scrapes the live production site's metadata."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            return None

        soup = bs4.BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title else ""
        desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_desc = desc_tag["content"].strip() if desc_tag else ""
        canonical_tag = soup.find("link", rel="canonical")
        canonical = canonical_tag["href"].strip() if canonical_tag else ""

        og_tags = {}
        for tag in soup.find_all("meta", property=re.compile(r"^og:")):
            og_tags[tag["property"]] = tag.get("content", "").strip()

        schemas = []
        schema_tags = soup.find_all("script", type="application/ld+json")
        for tag in schema_tags:
            try:
                if tag.string:
                    schemas.append(json.loads(tag.string.strip()))
            except Exception:
                schemas.append(tag.string.strip() if tag.string else "")

        return {
            "title": title,
            "meta_description": meta_desc,
            "canonical": canonical,
            "og_tags": json.dumps(og_tags, ensure_ascii=False),
            "schema_json_ld": json.dumps(schemas, ensure_ascii=False),
        }
    except Exception:
        return None


# --- Streamlit UI Layout ---
st.set_page_config(
    page_title="Sitemap SEO Migration Mapper", page_icon="🗺️", layout="wide"
)

st.title("🗺️ Sitemap-to-Sitemap SEO Migration Mapper")
st.write(
    "Paste the direct **Sitemap XML URLs** for both your Live and Beta sites. The app will fetch all paths, crawl the live site, and map matching data by slug."
)

col1, col2 = st.columns(2)
with col1:
    sitemap_1_input = st.text_input(
        "Website 1 (Main Live Sitemap XML URL)",
        "https://youthfulmedicine.com/sitemap.xml",
    )
with col2:
    sitemap_2_input = st.text_input(
        "Website 2 (Beta Website Sitemap XML URL)",
        "https://youthfulmedicine.gogroth.com/sitemap.xml",
    )

if st.button("Generate Migration Sheet from Sitemaps", type="primary"):
    if not sitemap_1_input or not sitemap_2_input:
        st.error("Please enter both sitemap link endpoints.")
    else:
        with st.spinner("Extracting index URLs from sitemaps..."):
            w1_urls = extract_urls_from_sitemap_url(sitemap_1_input.strip())
            w2_urls = extract_urls_from_sitemap_url(sitemap_2_input.strip())

        if not w1_urls or not w2_urls:
            st.warning(
                "Could not extract URLs. Please double-check that the sitemap XML addresses are correct and accessible."
            )
        else:
            st.info(
                f"Successfully parsed {len(w1_urls)} items from Live Sitemap and {len(w2_urls)} items from Beta Sitemap."
            )

            # Process Website 1 data indexed by slug
            w1_data_store = {}
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, url in enumerate(w1_urls):
                slug = get_slug_from_url(url)
                status_text.text(f"Scraping Live SEO content for: /{slug}")

                seo_info = scrape_website_1_seo(url)
                if seo_info:
                    w1_data_store[slug] = {"w1_url": url, **seo_info}
                progress_bar.progress((i + 1) / len(w1_urls))

            status_text.text("Cross-matching structures...")

            # Map to Website 2 items using the extracted slug
            final_rows = []
            for w2_url in w2_urls:
                slug = get_slug_from_url(w2_url)

                if slug in w1_data_store:
                    w1_info = w1_data_store[slug]
                    final_rows.append(
                        {
                            "Match Status": "MATCHED",
                            "Slug": f"/{slug}" if slug != "homepage" else "/",
                            "Website 2 New URL (Beta)": w2_url,
                            "Website 1 Old URL (Live)": w1_info["w1_url"],
                            "Meta Title": w1_info["title"],
                            "Meta Description": w1_info["meta_description"],
                            "Canonical (Old)": w1_info["canonical"],
                            "Open Graph Tags": w1_info["og_tags"],
                            "Schema JSON-LD": w1_info["schema_json_ld"],
                        }
                    )
                else:
                    final_rows.append(
                        {
                            "Match Status": "NO MATCH FOUND",
                            "Slug": f"/{slug}" if slug != "homepage" else "/",
                            "Website 2 New URL (Beta)": w2_url,
                            "Website 1 Old URL (Live)": "N/A",
                            "Meta Title": "",
                            "Meta Description": "",
                            "Canonical (Old)": "",
                            "Open Graph Tags": "",
                            "Schema JSON-LD": "",
                        }
                    )

            df = pd.DataFrame(final_rows)
            progress_bar.empty()
            status_text.empty()

            st.success("🎉 Cross-Matching Sheet Compiled Successfully!")
            st.dataframe(df)

            csv_data = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 Download Complete CSV Sheet",
                data=csv_data,
                file_name="seo_migration_mapping.csv",
                mime="text/csv",
            )

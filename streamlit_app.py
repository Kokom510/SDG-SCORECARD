import io
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from pypdf import PdfReader


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Company PDF Report Explorer",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Company PDF Report Explorer")
st.caption(
    "Find company sustainability/ESG reports, read the actual PDFs page by page, "
    "and extract explicit SDGs, targets, evidence and page references."
)


# ============================================================
# CONSTANTS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152 Safari/537.36"
    )
}

SDGS = {
    1: "No Poverty",
    2: "Zero Hunger",
    3: "Good Health and Well-being",
    4: "Quality Education",
    5: "Gender Equality",
    6: "Clean Water and Sanitation",
    7: "Affordable and Clean Energy",
    8: "Decent Work and Economic Growth",
    9: "Industry, Innovation and Infrastructure",
    10: "Reduced Inequalities",
    11: "Sustainable Cities and Communities",
    12: "Responsible Consumption and Production",
    13: "Climate Action",
    14: "Life Below Water",
    15: "Life on Land",
    16: "Peace, Justice and Strong Institutions",
    17: "Partnerships for the Goals",
}

SDG_PATTERNS = {
    n: [
        rf"\bSDG\s*{n}\b",
        rf"\bGoal\s*{n}\b",
        rf"\bSustainable Development Goal\s*{n}\b",
        rf"\b{re.escape(name)}\b",
    ]
    for n, name in SDGS.items()
}

PRIORITY_TERMS = [
    "priority sdg", "priority sdgs", "prioritised sdg", "prioritised sdgs",
    "prioritized sdg", "prioritized sdgs", "our sdgs", "focus sdg",
    "focus sdgs", "key sdgs", "relevant sdgs", "identified sdgs",
    "selected sdgs", "strategic sdgs", "aligned with the sdgs",
    "aligned to the sdgs", "aligned with sdg", "aligned to sdg",
    "support the sdgs", "support sdg", "contribute to the sdgs",
    "contribute to sdg", "contribution to the sdgs", "contribution to sdg",
    "commitment to the sdgs", "commitment to sdg", "mapped to the sdgs",
    "mapped to sdg", "linked to the sdgs", "linked to sdg",
    "sdg alignment", "sdg contribution", "sustainable development goals",
]

TARGET_TERMS = [
    "target", "targets", "commitment", "commitments", "ambition", "ambitions",
    "goal", "goals", "net zero", "carbon neutral", "reduce", "reduction",
    "increase", "achieve", "achieving", "reach", "reaching", "maintain",
    "eliminate", "phase out", "by 2025", "by 2026", "by 2027", "by 2028",
    "by 2029", "by 2030", "by 2035", "by 2040", "by 2050",
]

REPORT_WORDS = [
    "sustainability", "esg", "integrated report", "annual report",
    "climate report", "climate", "sustainable development", "impact report",
]


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalise_company(company):
    company = clean_text(company)
    return re.sub(
        r"\b(limited|ltd|plc|inc|incorporated|corp|corporation)\b",
        "",
        company,
        flags=re.IGNORECASE,
    ).strip()


def split_sentences(text):
    text = clean_text(text)
    return [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) >= 20
    ]


def get_domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def looks_like_company_domain(url, company):
    domain = get_domain(url)
    words = re.findall(r"[a-z0-9]+", normalise_company(company).lower())
    useful = [w for w in words if len(w) > 3]
    return bool(domain and any(w in domain for w in useful))


def unwrap_duckduckgo_url(url):
    if not url:
        return ""
    if "duckduckgo.com/l/?" in url:
        try:
            value = parse_qs(urlparse(url).query).get("uddg", [""])[0]
            return unquote(value) or url
        except Exception:
            return url
    return url


def is_pdf_url(url):
    return ".pdf" in url.lower()


def infer_year(text):
    years = re.findall(r"\b20(?:1\d|2\d)\b", text or "")
    return max((int(y) for y in years), default=0)


# ============================================================
# REPORT DISCOVERY
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def search_web(query, max_results=8):
    endpoints = [
        "https://html.duckduckgo.com/html/",
        "https://lite.duckduckgo.com/lite/",
    ]

    for endpoint in endpoints:
        try:
            response = requests.get(
                endpoint,
                params={"q": query},
                headers=HEADERS,
                timeout=12,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            # HTML endpoint
            for result in soup.select(".result"):
                link = result.select_one(".result__a")
                if not link:
                    continue
                snippet = result.select_one(".result__snippet")
                url = unwrap_duckduckgo_url(link.get("href", ""))
                title = clean_text(link.get_text(" ", strip=True))
                snippet_text = clean_text(
                    snippet.get_text(" ", strip=True) if snippet else ""
                )
                if url and title:
                    results.append(
                        {"title": title, "url": url, "snippet": snippet_text}
                    )

            # Lite fallback
            if not results:
                for link in soup.select("a.result-link"):
                    url = unwrap_duckduckgo_url(link.get("href", ""))
                    title = clean_text(link.get_text(" ", strip=True))
                    if url and title:
                        results.append(
                            {"title": title, "url": url, "snippet": ""}
                        )

            if results:
                return results[:max_results]

        except requests.RequestException:
            continue

    return []


def score_report(result, company):
    title = result["title"].lower()
    url = result["url"]
    year = infer_year(result["title"] + " " + result.get("snippet", ""))
    current_year = datetime.now().year
    score = 0

    if is_pdf_url(url):
        score += 25

    if looks_like_company_domain(url, company):
        score += 25

    if "sustainability" in title:
        score += 18
    if "esg" in title:
        score += 16
    if "climate" in title:
        score += 12
    if "integrated report" in title:
        score += 12
    if "annual report" in title:
        score += 7
    if "report" in title:
        score += 4

    if year:
        distance = max(0, current_year - year)
        score += max(0, 15 - distance * 3)

    return score, year


@st.cache_data(ttl=3600, show_spinner=False)
def find_pdf_reports(company, max_reports=6):
    company = normalise_company(company)
    current_year = datetime.now().year

    queries = [
        f'"{company}" sustainability report {current_year} filetype:pdf',
        f'"{company}" sustainability report {current_year - 1} filetype:pdf',
        f'"{company}" ESG report filetype:pdf',
        f'"{company}" climate report filetype:pdf',
        f'"{company}" integrated report filetype:pdf',
        f'"{company}" annual report sustainability filetype:pdf',
    ]

    candidates = {}
    for query in queries:
        for result in search_web(query, max_results=8):
            url = result["url"]
            if not url:
                continue

            combined = (
                result["title"] + " " + result.get("snippet", "") + " " + url
            ).lower()

            if not any(word in combined for word in REPORT_WORDS):
                continue

            score, year = score_report(result, company)
            item = dict(result)
            item["score"] = score
            item["year"] = year

            previous = candidates.get(url)
            if previous is None or score > previous["score"]:
                candidates[url] = item

    ranked = sorted(
        candidates.values(),
        key=lambda x: (x["score"], x["year"]),
        reverse=True,
    )

    return ranked[:max_reports]


# ============================================================
# PDF DOWNLOAD + READING
# ============================================================

@st.cache_data(ttl=86400, show_spinner=False, max_entries=40)
def download_pdf(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").lower()
        content = response.content

        # Validate using content type OR PDF magic bytes.
        if "pdf" not in content_type and not content.startswith(b"%PDF"):
            return None, "The URL did not return a PDF."

        return content, ""

    except requests.RequestException as exc:
        return None, f"Could not download PDF: {exc}"


def read_pdf_pages(pdf_bytes):
    if not pdf_bytes:
        return [], "No PDF data received."

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        return [], f"Could not open PDF: {exc}"

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return [], "The PDF is encrypted and could not be read."

    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = clean_text(page.extract_text() or "")
        except Exception:
            text = ""

        if text:
            pages.append({"page": page_number, "text": text})

    if not pages:
        return [], (
            "No readable text was extracted. The report may be image/scanned PDF "
            "and may require OCR."
        )

    return pages, ""


# ============================================================
# SDG + TARGET EXTRACTION FROM PDF TEXT
# ============================================================

def sdgs_in_text(text):
    found = []
    for number, patterns in SDG_PATTERNS.items():
        if any(re.search(p, text, flags=re.IGNORECASE) for p in patterns):
            found.append(number)
    return found


def has_priority_language(text):
    lower = text.lower()
    return any(term in lower for term in PRIORITY_TERMS)


def looks_like_target(text):
    lower = text.lower()
    language = any(term in lower for term in TARGET_TERMS)
    quantitative = bool(
        re.search(
            r"\b20[2-5]\d\b|\b\d{1,3}(?:\.\d+)?\s?%|"
            r"\b\d+(?:\.\d+)?\s?(?:MW|GW|MWh|GWh|kWh|tCO2e|tCO₂e|"
            r"tonnes|tons|kg|litres|liters)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    return language and quantitative


def target_year(text):
    years = re.findall(r"\b20(?:2[5-9]|3\d|4\d|50)\b", text)
    return max(years, key=int) if years else ""


def quantitative_target(text):
    patterns = [
        r"\b\d{1,3}(?:\.\d+)?\s?%",
        r"\b\d+(?:\.\d+)?\s?(?:MW|GW|MWh|GWh|kWh|tCO2e|tCO₂e|tonnes|tons|kg|litres|liters)\b",
        r"\bnet zero\b.{0,80}?\b20\d{2}\b",
        r"\bcarbon neutral\b.{0,80}?\b20\d{2}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_text(match.group(0))
    return ""


def extract_report_findings(company, report, pages):
    findings = []

    for page_data in pages:
        page_number = page_data["page"]
        sentences = split_sentences(page_data["text"])

        for i, sentence in enumerate(sentences):
            detected = sdgs_in_text(sentence)
            if not detected:
                continue

            # Context is important: a PDF often lists the SDG in one sentence
            # and describes alignment/target in the surrounding sentences.
            start = max(0, i - 2)
            end = min(len(sentences), i + 4)
            context_sentences = sentences[start:end]
            context = " ".join(context_sentences)

            # Require explicit alignment/support language in the local context.
            if not has_priority_language(context):
                continue

            target_candidates = [
                candidate
                for candidate in context_sentences
                if looks_like_target(candidate)
            ]

            target_text = target_candidates[0] if target_candidates else ""
            all_target_text = " ".join(target_candidates)

            for number in detected:
                findings.append(
                    {
                        "Company": company,
                        "SDG": f"SDG {number}",
                        "SDG Name": SDGS[number],
                        "Target / Commitment": target_text,
                        "Target Year": target_year(all_target_text),
                        "Quantitative Target": quantitative_target(all_target_text),
                        "Evidence": sentence,
                        "Page": page_number,
                        "Report": report["title"],
                        "Reporting Year": report.get("year") or "",
                        "Source PDF": report["url"],
                        "Analyst Review": "Required",
                        "Analyst Comment": "",
                    }
                )

    # Deduplicate repeated headers / repeated SDG references.
    unique = []
    seen = set()
    for item in findings:
        key = (
            item["SDG"],
            item["Evidence"].lower(),
            item["Report"].lower(),
            item["Page"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def merge_findings(findings):
    """Keep evidence rows, but remove exact duplicates across reports/pages."""
    unique = []
    seen = set()
    for item in findings:
        key = (
            item["SDG"],
            item["Target / Commitment"].lower(),
            item["Evidence"].lower(),
            item["Source PDF"],
            item["Page"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Company")

    company = st.text_input(
        "Company name",
        value="Nedbank",
        help="Enter the company whose reports you want to analyse.",
    )

    max_reports = st.slider(
        "Maximum PDFs to analyse",
        min_value=1,
        max_value=6,
        value=3,
    )

    st.subheader("Optional PDF URLs")
    manual_urls_text = st.text_area(
        "Paste one or more direct PDF URLs",
        placeholder="https://company.com/report.pdf\nhttps://company.com/climate-report.pdf",
        help="One URL per line. These PDFs are analysed in addition to discovered reports.",
    )

    run = st.button(
        "Find and read PDF reports",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    st.markdown(
        """
### PDF-first methodology

The search engine is used only to **discover report links**.

The SDG analysis is performed on text extracted from the **actual PDF pages**.

An SDG is returned only when local report context indicates explicit company
alignment, prioritisation, support or contribution. Results should still be
reviewed by an analyst before formal reporting.
"""
    )


# ============================================================
# MAIN APP
# ============================================================

if not run:
    st.info("Enter a company and click **Find and read PDF reports**.")
    st.markdown(
        """
### What the app does

1. Searches for recent sustainability, ESG, climate, integrated and annual-report PDFs.
2. Prioritises recent reports and company-domain sources.
3. Downloads the actual PDF files.
4. Reads the PDFs page by page using `pypdf`.
5. Looks for explicit company SDG alignment/support.
6. Extracts nearby targets, target years and quantitative commitments.
7. Returns the source PDF and page number for analyst validation.
8. Exports the evidence dataset to CSV.

**Note:** scanned/image-only PDFs may require OCR and cannot always be read by `pypdf`.
"""
    )
    st.stop()


if not company.strip():
    st.error("Please enter a company name.")
    st.stop()

company_clean = normalise_company(company)

manual_urls = [
    line.strip()
    for line in manual_urls_text.splitlines()
    if line.strip()
]

with st.spinner("Finding candidate PDF reports..."):
    discovered = find_pdf_reports(company_clean, max_reports=max_reports)

manual_reports = []
for url in manual_urls:
    manual_reports.append(
        {
            "title": f"Manually supplied PDF — {get_domain(url) or 'source'}",
            "url": url,
            "snippet": "",
            "score": 999,
            "year": infer_year(url),
        }
    )

# Manual URLs first, then discovered reports; deduplicate URLs.
reports = []
seen_urls = set()
for report in manual_reports + discovered:
    if report["url"] not in seen_urls:
        seen_urls.add(report["url"])
        reports.append(report)

reports = reports[: max_reports + len(manual_reports)]

if not reports:
    st.error(
        "No candidate reports were found. Try pasting a direct official PDF URL "
        "in the sidebar."
    )
    st.stop()

st.success(f"Found {len(reports)} candidate report(s) to inspect.")

all_findings = []
read_reports = []
failed_reports = []

progress = st.progress(0)
status = st.empty()

for index, report in enumerate(reports, start=1):
    status.write(f"Reading PDF {index} of {len(reports)}: **{report['title']}**")

    pdf_bytes, download_error = download_pdf(report["url"])
    if download_error:
        failed_reports.append(
            {"Report": report["title"], "URL": report["url"], "Reason": download_error}
        )
        progress.progress(index / len(reports))
        continue

    pages, read_error = read_pdf_pages(pdf_bytes)
    if read_error:
        failed_reports.append(
            {"Report": report["title"], "URL": report["url"], "Reason": read_error}
        )
        progress.progress(index / len(reports))
        continue

    findings = extract_report_findings(company_clean, report, pages)
    all_findings.extend(findings)

    read_reports.append(
        {
            "Report": report["title"],
            "Year": report.get("year") or "Unknown",
            "Pages with readable text": len(pages),
            "SDG evidence rows": len(findings),
            "URL": report["url"],
        }
    )

    progress.progress(index / len(reports))

status.empty()
progress.empty()

all_findings = merge_findings(all_findings)


# ============================================================
# REPORT STATUS
# ============================================================

st.divider()
st.subheader("PDF reports read")

if read_reports:
    for report in read_reports:
        with st.container(border=True):
            st.markdown(f"**{report['Report']}**")
            st.write(
                f"Year: {report['Year']} · "
                f"Readable pages: {report['Pages with readable text']} · "
                f"Evidence rows: {report['SDG evidence rows']}"
            )
            st.link_button("Open PDF", report["URL"])
else:
    st.warning("None of the candidate PDFs could be read.")

if failed_reports:
    with st.expander("PDFs that could not be read"):
        for failure in failed_reports:
            st.markdown(f"**{failure['Report']}**")
            st.write(failure["Reason"])
            st.caption(failure["URL"])


# ============================================================
# RESULTS
# ============================================================

st.divider()
st.subheader(f"Extracted SDG evidence — {company_clean}")

if not all_findings:
    st.warning(
        "The PDFs were read, but no SDGs met the app's explicit-alignment rule. "
        "This does not necessarily mean the company has no SDG activity."
    )
    st.stop()

unique_sdgs = sorted(
    {int(item["SDG"].replace("SDG ", "")) for item in all_findings}
)

metric1, metric2, metric3 = st.columns(3)
metric1.metric("SDGs identified", len(unique_sdgs))
metric2.metric("Evidence rows", len(all_findings))
metric3.metric("PDFs successfully read", len(read_reports))

for number in unique_sdgs:
    rows = [r for r in all_findings if r["SDG"] == f"SDG {number}"]

    with st.expander(
        f"SDG {number} — {SDGS[number]} ({len(rows)} evidence row(s))",
        expanded=True,
    ):
        for row in rows[:8]:
            st.markdown(f"**{row['Report']} — page {row['Page']}**")
            st.info(row["Evidence"])

            if row["Target / Commitment"]:
                st.markdown("**Target / commitment**")
                st.write(row["Target / Commitment"])

            c1, c2 = st.columns(2)
            c1.write(
                "**Target year:** "
                + (row["Target Year"] or "Not identified")
            )
            c2.write(
                "**Quantitative target:** "
                + (row["Quantitative Target"] or "Not identified")
            )

            st.link_button(
                f"Open source PDF — page reference {row['Page']}",
                row["Source PDF"],
            )
            st.divider()


# ============================================================
# EXPORT
# ============================================================

st.subheader("Export-ready evidence dataset")

df = pd.DataFrame(all_findings)
st.dataframe(df, use_container_width=True, hide_index=True)

csv = df.to_csv(index=False).encode("utf-8")
safe_company = re.sub(r"[^A-Za-z0-9_-]+", "_", company_clean).strip("_")

st.download_button(
    "Download SDG evidence as CSV",
    data=csv,
    file_name=f"{safe_company}_PDF_SDG_Evidence.csv",
    mime="text/csv",
    use_container_width=True,
)

st.caption(
    "Analyst review remains required. PDF extraction can miss information in "
    "charts, images, icons, scanned pages and complex layouts."
)

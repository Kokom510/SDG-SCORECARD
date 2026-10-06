# Company PDF Report Explorer

A Streamlit app that discovers company sustainability-related PDF reports, downloads the actual PDFs, reads them page by page, and extracts explicit SDG evidence and associated targets.

## What it does

- Searches for Sustainability, ESG, Climate, Integrated and Annual Report PDFs
- Prioritises recent reports and company-domain sources
- Supports direct PDF URLs
- Downloads and reads actual PDFs using `pypdf`
- Extracts explicit SDG alignment/support evidence
- Extracts nearby targets, target years and quantitative commitments
- Preserves report names, source links and PDF page references
- Analyses multiple reports for one company
- Exports the extracted evidence to CSV

## Repository structure

```text
company-pdf-report-explorer/
├── streamlit_app.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Run locally

```bash
python -m venv .venv
```

Activate the environment, then install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run streamlit_app.py
```

## Deploy on Streamlit Community Cloud

1. Create a new GitHub repository.
2. Upload all files from this repository package.
3. Commit the files.
4. In Streamlit Community Cloud, create a new app from the repository.
5. Set the main file path to `streamlit_app.py`.
6. Deploy.

## PDF support

The app uses `pypdf` for text extraction. Text-based PDFs work best. Scanned/image-only PDFs may require OCR and can return no readable text.

## Important

The extracted SDG evidence and targets are intended to support analysis. Analyst review is required before using results in formal ESG, investment or client reporting.

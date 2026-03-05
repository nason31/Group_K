# Group_K
Code for the group assignment in Advanced Programming 2026

## Team Members
<!-- 🚨 IMPORTANT: Add your email addresses below (one per line for easy copy-paste to Outlook) -->
- member1@example.com
- member2@example.com
- member3@example.com
- member4@example.com

---

## Project: Okavango Environmental Dashboard

A Streamlit-based data analysis tool for environmental protection using the **most recent data available** from Our World in Data.

### Features
- ✅ Automatically downloads and processes environmental datasets
- ✅ Visualizes global forest and land protection metrics on interactive maps
- ✅ Displays top 5 and bottom 5 countries for each metric
- ✅ Uses the most recent available data for all indicators
- ✅ Idempotent downloads (won't re-download existing files)
- ✅ PEP8 compliant, type-hinted, and Pydantic-validated code

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Group_K

# Install dependencies
pip install pandas geopandas streamlit matplotlib requests pydantic shapely

# Run tests to verify installation
pytest

# Launch the app
python main.py
```

### Quick Start

**Option 1: Using main.py (Recommended)**
```bash
python main.py
```

**Option 2: Using Streamlit directly**
```bash
streamlit run app/streamlit_app.py
```

The dashboard will open in your default web browser at `http://localhost:8501`

### Project Structure
```
Group_K/
├── downloads/              # Downloaded datasets (auto-generated)
├── app/                    # Application code
│   ├── __init__.py
│   ├── data_handler.py     # Data models and processing logic
│   └── streamlit_app.py    # Streamlit dashboard UI
├── tests/                  # Test files
│   └── okavango_test.py
├── notebooks/              # Prototyping notebooks (if any)
├── main.py                 # Entry point
├── README.md
├── LICENSE
├── .gitignore
└── pytest.ini
```

### Datasets Used
1. **Annual Change in Forest Area** - Forest area changes over time
2. **Annual Deforestation** - Deforestation rates by country
3. **Share of Protected Land (Terrestrial)** - Protected area coverage
4. **Share of Degraded Land** - Land degradation indicators
5. **Forest Area as Share of Land** - Forest coverage percentage
6. **Natural Earth Countries Map (110m)** - World country boundaries

All data sources: [Our World in Data](https://ourworldindata.org) & [Natural Earth Data](https://www.naturalearthdata.com)

### Development

**Running Tests**
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test
pytest tests/okavango_test.py::test_download
```

**Code Quality**
- All code follows PEP8 naming conventions
- Type hints used throughout
- Pydantic models for data validation
- Comprehensive docstrings in NumPy style

### How It Works

1. **Data Download** (`download_project_data`)
   - Downloads CSV and shapefile data from OWID and Natural Earth
   - Implements idempotent downloads (skips if files exist)

2. **Data Cleaning** (`_load_and_clean_dataframes`)
   - Normalizes country code columns to "Code"
   - Filters to most recent year per country
   - Removes unnecessary columns

3. **Geospatial Merge** (`merge_geospatial_layers`)
   - Joins metrics to world map geometry
   - Uses left join to preserve all countries

4. **Visualization** (Streamlit App)
   - Interactive metric selection
   - Choropleth world map
   - Top 5 vs Bottom 5 bar chart

### License
MIT License - see [LICENSE](LICENSE) for details

---

**Note:** Remember to add your actual team email addresses in the Team Members section above!

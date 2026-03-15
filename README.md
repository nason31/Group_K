# Group_K
Code for the group assignment in Advanced Programming 2026

## Team Members
| Name | Student Number | Email |
|------|---------------|-------|
| Justus Jonas Nau | 70106 | 70106@novasbe.pt |
| Konstantin Titze | 74539 | 74539@novasbe.pt |
| Lenn Louis Schneidewind | 67548 | 67548@novasbe.pt |
| Nick Christopher Hammerschmid | 70159 | 70159@novasbe.pt |

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
pip install pandas geopandas streamlit matplotlib requests pydantic shapely pyyaml ollama

# Install Ollama (required for AI workflow)
# macOS/Linux: https://ollama.com/download
# The app will automatically pull required models on first run

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
│   ├── ai_backend.py       # AI pipeline: image fetch, vision model, risk assessment
│   ├── data_handler.py     # Data models and processing logic
│   ├── db.py               # Database cache logic (images.csv)
│   └── streamlit_app.py    # Streamlit dashboard UI
├── database/               # Pipeline run history
│   └── images.csv          # Cached pipeline results
├── images/                 # Downloaded satellite images (auto-generated)
├── tests/                  # Test files
│   └── okavango_test.py
├── models.yaml             # AI model configuration
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

### Page 1: Data Dashboard

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

### Page 2: AI Workflow

1. **Coordinate Selection** — User selects latitude, longitude, and zoom level (or picks a preset region)
2. **Satellite Image Fetch** — Downloads a tile from ESRI World Imagery
3. **Image Description** — A vision model (via Ollama) describes the land cover and visible conditions
4. **Risk Assessment** — A text model evaluates the description for signs of environmental danger
5. **Result Display** — The image, description, and a visual risk badge (🟢 SAFE / 🔴 DANGER) are shown
6. **Caching** — Results are stored in `database/images.csv`; repeated queries load from cache instantly

### AI Model Configuration (`models.yaml`)

The models and prompts used by the AI workflow are fully configurable in `models.yaml` without touching any code:

```yaml
image_model:
  name: "llava:7b"
  prompt: "Describe this satellite image focusing on land use and environmental conditions."
  max_tokens: 512

text_model:
  name: "qwen3.5:4b"
  prompt: "Assess environmental risk based on the following description. Conclude with DANGER or SAFE."
  max_tokens: 512
```

---

## Example: Environmental Danger Detection

### Example 1: Amazon Basin Deforestation
![Amazon Basin](images/example_amazon.png)

The AI workflow flagged this area of the Amazon Basin as **⚠️ High Environmental Risk**. The vision model detected large-scale forest clearing and exposed soil, consistent with active deforestation. The risk model identified signs of habitat destruction and land degradation.

---

### Example 2: Borneo Rainforest Encroachment
![Borneo](images/example_borneo.png)

This image of Borneo was flagged as **⚠️ High Environmental Risk**. The model identified a mosaic of palm oil plantation and degraded forest edges, indicating ongoing conversion of primary rainforest to agricultural land.

---

### Example 3: Okavango Delta
![Okavango Delta](images/example_okavango.png)

The Okavango Delta was assessed as **✅ Low Environmental Risk**. The vision model described intact wetland vegetation, healthy water channels, and no visible signs of human encroachment or burning.

---

## How This Project Supports the UN Sustainable Development Goals (SDGs)

This project was built with environmental protection as its core purpose. It directly contributes to several of the United Nations' Sustainable Development Goals:

### SDG 15 — Life on Land
The dashboard tracks deforestation, land degradation, and protected area coverage globally. By visualizing which countries are losing forest cover fastest and which regions are most degraded, the tool helps researchers and policymakers identify where intervention is most urgently needed. The AI workflow goes further by enabling on-demand satellite analysis of any location on Earth, making it possible to detect deforestation or land degradation at the local level in near real-time.

### SDG 13 — Climate Action
Forests are critical carbon sinks. Deforestation is one of the leading drivers of greenhouse gas emissions. By making forest loss data immediately accessible and visually interpretable, this project supports climate monitoring efforts. The annual change in forest area dataset allows users to track whether countries are meeting reforestation commitments or accelerating forest loss, directly informing climate action policy.

### SDG 17 — Partnerships for the Goals
The project is built entirely on open data (Our World in Data, Natural Earth) and open-source tools (Streamlit, GeoPandas, Ollama). This reflects the SDG 17 principle of using open knowledge and technology to strengthen global capacity for sustainable development. The tool is lightweight and reproducible, meaning it can be deployed by NGOs, governments, or researchers anywhere in the world without commercial licensing.

### Conclusion
Project Okavango demonstrates how data science and AI can be combined to support environmental monitoring at both the global and local scale. As satellite imagery becomes increasingly available and language models become more capable, tools like this have the potential to serve as early warning systems for environmental degradation — helping protect the ecosystems that all life on Earth depends on.

---

### License
MIT License - see [LICENSE](LICENSE) for details

---
import os
import json
import time
import requests
import wikipediaapi
from bs4 import BeautifulSoup
from datetime import datetime, UTC, timezone
from pathlib import Path, PurePath
import re

GVP_BASE = "https://volcano.si.edu"
WIKI_API = wikipediaapi.Wikipedia(user_agent = "volcanoz-bot/0.1 (https://yourdomain.com; contact@example.com)", language='en' )

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '../dataset/volcanoes.json')


HEADERS = {"User-Agent": "volcanoz-bot/0.1 (https://yourdomain.com; contact@example.com)"}

def init_data():
    return {
        "name": "",
        "gvp_id": "",
        "elevation_m": None,
        "last_known_eruption": "",
        "location": {
            "coordinates": [None, None],  # [latitude, longitude]
            "country": "",
            "region": ""
        },
        "population": {
            "within_5km": "",
            "within_10km": "",
            "within_30km": "",
            "within_100km": ""
        },
        "rock_types": {
            "major": [],
            "minor": []
        },
        "volcano_types": [],
        "volcano_landform": "",
        "alternate_names": [],
        "summary": "",
        "features": {
            "Cones": [],
            "Craters": [],
            "Domes": [],
            "Thermal Features": []
        },
        "eruption_history": [],
        "source": ""
    }

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat() + "Z"
        return super().default(o)

def get_volcano_list() -> list:
    volcanoes = []
    url = f"{GVP_BASE}/volcanolist_holocene.cfm?sortnum=4"
    resp = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    table = soup.find('div', attrs={'class':'TableSearchResults'})
    if not table:
        print("Could not find volcano table")
        return []
    
    for row in table.find_all('tr')[1:]:
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        
        link = cells[0].find('a')
        if not link or 'href' not in link.attrs:
            continue
        href = link['href']
        name = link.text.strip()
        # Extract the volcano number (vn=xxxx)
        if "vn" in href:
            vn = href.split("vn=")[1]
        else:
            continue
        volcano = {}
        volcano["name"] = name
        volcano["gvp_id"] = vn
        volcanoes.append(volcano)
        
    print(f"Found {len(volcanoes)} volcanoes.")
    return volcanoes

def parse_basic_data(fact_table, data):
    """Extracts elevation_m, last_known_eruption, latitude, longitude, population."""
    for row in fact_table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                label_cell, value_cell = cells
                labels = [strong.get_text(strip=True) for strong in label_cell.find_all("strong") if strong.get_text(strip=True)]
                values = [v.strip() for v in value_cell.get_text().split("\n") if v.strip()]
                
                # Map labels to values for Basic Data
                if labels and values and len(labels) == len(values):
                    for label, value in zip(labels, values):
                        if label == "Elevation":
                            data["elevation_m"] = _parse_elevation(value)
                        elif label == "Last Known Eruption":
                            data["last_known_eruption"] = value
                        elif label == "Latitude":
                            lat = _parse_coordinate(value)
                            if lat is not None:
                                data["location"]["coordinates"][0] = lat
                        elif label == "Longitude":
                            lon = _parse_coordinate(value)
                            if lon is not None:
                                data["location"]["coordinates"][1] = lon
                        elif label == "Within 5 km":
                            data["population"]["within_5km"] = value
                        elif label == "Within 10 km":
                            data["population"]["within_10km"] = value 
                        elif label == "Within 30 km":
                            data["population"]["within_30km"] = value
                        elif label == "Within 100 km":
                            data["population"]["within_100km"] = value
                    
    
def parse_geological_summary(fact_table, data):
    """Extracts summary from Geological Summary."""
    rows = fact_table.select("tbody tr")
    for i, row in enumerate(rows):
        if row.find("h5", string=lambda x: x and "Geological Summary" in x):
            # Check the next row for the summary
            if i + 1 < len(rows):
                next_row = rows[i + 1]
                cell = next_row.find("td")
                if cell:
                    p_tag = cell.find("p")
                    if p_tag:
                        data["summary"]= p_tag.get_text(strip=True)
            

def parse_rock_types(fact_table, data):
    """Extracts major and minor rock types from Rock Types section."""
    rows = fact_table.select("tbody tr")
    for i, row in enumerate(rows):
        if row.find("h5", string=lambda x: x and "Rock Types" in x):
            # Check next rows for Major and Minor
            for j in range(i + 1, min(i + 3, len(rows))):  # Look at next 2 rows
                next_row = rows[j]
                cell = next_row.find("td", attrs={"colspan": "2"})
                if cell:
                    strong = cell.find("strong")
                    if strong:
                        label = strong.get_text(strip=True)
                        text = cell.get_text(strip=True).replace(label, "").strip()
                        if label == "Major":
                            data["rock_types"]["major"] = [t.strip() for t in text.split("\n") if t.strip()]
                        elif label == "Minor":
                            data["rock_types"]["minor"] = [t.strip() for t in text.split("\n") if t.strip()]
    
def parse_morphology(fact_table, data):
    """Extracts volcano_landform and volcano_types from Morphology section."""
    rows = fact_table.select("tbody tr")
    for i, row in enumerate(rows):
        if row.find("h5", string=lambda x: x and "Morphology" in x):
            # Check next rows for Volcano Landform and Volcano Types
            for j in range(i + 1, min(i + 3, len(rows))):  # Look at next 2 rows
                next_row = rows[j]
                cell = next_row.find("td", attrs={"colspan": "2"})
                if cell:
                    strong = cell.find("strong")
                    if strong:
                        label = strong.get_text(strip=True)
                        text = cell.get_text(strip=True).replace(label, "").strip()
                        if label == "Volcano Landform":
                            data["volcano_landform"] = text
                        elif label == "Volcano Types":
                            types = [t.strip() for t in text.split("\n") if t.strip()]
                            data["volcano_types"] = types
 
def parse_synonyms(soup, data):
    """Extracts alternate_names from Synonyms section."""
    synonyms_table = soup.find("table", class_="DivTable", attrs={"title": "Synonyms and Subfeatures table for this volcano"})
    if not synonyms_table:
        return

    synonyms_header = synonyms_table.find("h5", string="Synonyms")
    if synonyms_header:
        synonyms_row = synonyms_header.find_parent("tr").find_next_sibling("tr")
        if synonyms_row:
            cell = synonyms_row.find("td", colspan="5")
            if cell:
                synonyms_text = cell.get_text(strip=True)
                synonyms = [name.strip() for name in synonyms_text.split("|") if name.strip()]
                if synonyms:
                    data["alternate_names"] = synonyms


def parse_features(soup, data):
    """Extracts features (Cones, Craters, Domes, Thermal Features) from Subfeatures section."""
    data["features"] = {"Cones": [], "Craters": [], "Domes": [], "Thermal Features": []}
    synonyms_table = soup.find("table", class_="DivTable", attrs={"title": "Synonyms and Subfeatures table for this volcano"})
    if not synonyms_table:
        return

    current_category = None
    header_found = False

    for row in synonyms_table.find_all("tr"):
        h5 = row.find("h5")
        if h5:
            category = h5.get_text(strip=True)
            if category in data["features"]:
                current_category = category
                header_found = False
            else:
                current_category = None
            continue

        if row.find("td", string="Feature Name"):
            header_found = True
            continue

        if current_category and header_found:
            cells = row.find_all("td")
            if len(cells) == 5:
                feature = {
                    "name": cells[0].get_text(strip=True),
                    "type": cells[1].get_text(strip=True),
                    "elevation": cells[2].get_text(strip=True) or None,
                    "latitude": cells[3].get_text(strip=True) or None,
                    "longitude": cells[4].get_text(strip=True) or None
                }
                data["features"][current_category].append(feature)


def parse_volcano_info_table(soup, data):
    """Extracts country and volcanic_region from volcano-info-table."""
    info_table = soup.find("div", class_="volcano-info-table")
    if info_table:
        shaded_items = info_table.find("ul").find_all("li", class_="shaded")
        if len(shaded_items) >= 2:
            country = shaded_items[0].get_text(strip=True)
            volcanic_region = shaded_items[1].get_text(strip=True)
            if country:
                data["location"]["country"] = country
            if volcanic_region:
                data["location"]["region"] = volcanic_region

def parse_eruption_history(volcano, data):
    """Extracts detailed eruption history from Eruptive History section."""
    history_url = f"{GVP_BASE}/volcano.cfm?vn={volcano['gvp_id']}&tab=1"
    time.sleep(1)
    resp = requests.get(history_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    eruption_accordion = soup.find("div", class_="eruption-accordion")
    if not eruption_accordion:
        return

    for header in eruption_accordion.find_all("p", class_="EruptionAccordionHeader"):
        period = {
            "date_range": "",
            "eruption_type": "",
            "vei": None,
            "episodes": []
        }
        impact = None
        event_types = set()

        # Extract period details
        period_text = header.get_text(strip=True)
        spans = header.find_all("span")

        if spans:
            eruption_type_raw = spans[0].get_text(strip=True)
            if eruption_type_raw:
                # Safe split using non-empty separator
                date_range = period_text.split(eruption_type_raw)[0].strip()
                period["eruption_type"] = eruption_type_raw.replace("Confirmed Eruption ", "").strip("()")
            else:
                # Fallback: treat the whole text as date range
                date_range = period_text.strip()
                period["eruption_type"] = ""
        else:
            # No spans found: fallback again
            date_range = period_text.strip()
            period["eruption_type"] = ""

        period["date_range"] = date_range

        # VEI
        vei_text = spans[1].get_text(strip=True) if len(spans) > 1 else ""
        vei_match = re.search(r"VEI: (\d+)", vei_text)
        if vei_match:
            period["vei"] = int(vei_match.group(1))

        # Find corresponding content
        content = header.find_next_sibling("div", class_="EruptionAccordionContent")
        if not content:
            continue

        # Extract episodes
        for episode_table in content.find_all("div", class_="EpisodeTable"):
            episode = {
                "episode_number": "",
                "date_range": "",
                "location": "",
                "evidence": "",
                "events": []
            }

            # Extract episode details from thead
            thead = episode_table.find("thead")
            if thead:
                rows = thead.find_all("tr")
                if len(rows) >= 2:
                    # Episode number and location
                    th = rows[0].find("th", colspan="4")
                    location_th = rows[0].find("th", colspan="1")
                    if th:
                        episode["episode_number"] = th.get_text(strip=True).split("|")[0].strip()
                    if location_th:
                        episode["location"] = location_th.get_text(strip=True)
                    
                    # Date range and evidence
                    date_th = rows[1].find("th", colspan="4")
                    evidence_th = rows[1].find("th", colspan="1")
                    if date_th:
                        episode["date_range"] = date_th.get_text(strip=True)
                    if evidence_th:
                        episode["evidence"] = evidence_th.get_text(strip=True).replace("Evidence from ", "")

            # Extract events
            events_table = episode_table.find("div", class_="EventsTable")
            if events_table:
                for row in events_table.find("tbody").find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) >= 5:
                        event = {
                            "start_date": cells[1].get_text(strip=True),
                            "end_date": cells[2].get_text(strip=True) if cells[2].get_text(strip=True) != "----" else None,
                            "event_type": cells[3].get_text(strip=True),
                            "remarks": cells[4].get_text(strip=True)
                        }
                        episode["events"].append(event)
                        event_types.add(event["event_type"])

            period["episodes"].append({
                "summary": episode_table.get_text(strip=True)
            })

        # Infer impact
        if "Ashfall" in event_types:
            impact = "Ashfall affecting nearby areas"
        elif "Property Damage" in event_types:
            impact = "Property damage reported"
        elif "Evacuation" in event_types:
            impact = "Evacuations reported"
        elif any(t in event_types for t in ["Lava flow", "Lava fountains"]):
            impact = "Lava flows impacting local areas"
        elif "Explosion" in event_types:
            impact = "Explosive activity reported"

        data["eruption_history"].append({
            "period": period,
            "impact": impact,
            "sources": [history_url]
        })
        
def get_gvp_data(volcano):
    gvp_url = f"{GVP_BASE}/volcano.cfm?vn={volcano['gvp_id']}"
    resp = requests.get(gvp_url, headers=HEADERS)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    data = init_data()
    data["name"] = volcano.get("name")
    data["gvp_id"] = volcano.get("gvp_id")
    data["source"] = gvp_url

    parse_volcano_info_table(soup, data)
    # Find all tabbed-content divs
    content_areas = soup.find_all("div", class_="tabbed-content")
    if not content_areas:
        print(f"No tabbed-content found for {volcano["name"]}")
        return data
    
    basic_table = get_fact_table_by_heading(content_areas, "Basic Data")
    if basic_table:
        parse_basic_data(basic_table, data)
        parse_rock_types(basic_table, data)
        parse_morphology(basic_table, data)
    
    summary_table = get_fact_table_by_heading(content_areas, "Geological Summary")
    if summary_table:
        parse_geological_summary(summary_table, data)
    
    parse_synonyms(soup, data)
    parse_features(soup, data)
    parse_eruption_history(volcano, data)
    
    return data

def get_fact_table_by_heading(content_areas, heading: str):
    """
    Finds a table with a specific <h5> heading within tabbed-content areas.
    Returns the matching <table> or None if not found.
    """
    for content_area in content_areas:
        tables = content_area.find_all("table", class_="DivTable", attrs={'role':'presentation'})
        for table in tables:
            h5 = table.find("h5")
            if h5 and heading.lower() in h5.text.strip().lower():
                return table
    return None    
            
def get_wikipedia_data(volcano_name):
    page = WIKI_API.page(volcano_name)
    if not page.exists():
        return {"summary": "", "volcano_type": "unknown", "status": "unknown", "location": {"coordinates": [0.0, 0.0]}, "elevation_m": None}
    
    infobox = {}
    wikitext = page.text
    infobox_start = wikitext.find("{{Infobox")
    if infobox_start != -1:
        infobox_end = wikitext.find("}}", infobox_start)
        infobox_text = wikitext[infobox_start:infobox_end + 2]
        for line in infobox_text.split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip().replace("|", "").lower()
                value = value.strip()
                infobox[key] = value
    
    coordinates = [0.0, 0.0]
    if "coordinates" in infobox:
        coord_match = re.search(r"(\d+\.\d+)°([NS]).*?(\d+\.\d+)°([EW])", infobox["coordinates"])
        if coord_match:
            lat = float(coord_match.group(1))
            lat_dir = coord_match.group(2)
            lon = float(coord_match.group(3))
            lon_dir = coord_match.group(4)
            coordinates[0] = -lat if lat_dir == "S" else lat
            coordinates[1] = -lon if lon_dir == "W" else lon
    
    elevation_m = None
    if "elevation_m" in infobox or "elevation" in infobox:
        elev_text = infobox.get("elevation_m", infobox.get("elevation", ""))
        elev_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*m", elev_text)
        if elev_match:
            elevation_m = float(elev_match.group(1).replace(",", ""))
    
    volcano_type = infobox.get("type", "unknown")
    
    status = "unknown"
    if "last_eruption" in infobox:
        last_eruption = infobox["last_eruption"]
        try:
            year = int(re.search(r"\d{4}", last_eruption).group(0))
            status = "active" if year > 1900 else "dormant"
        except:
            pass
    
    return {
        "summary": page.summary,
        "volcano_type": volcano_type,
        "status": status,
        "location": {"coordinates": coordinates},
        "elevation_m": elevation_m
    }
    
def scrape_all():
    volcanoes = []
    volcano_list = get_volcano_list()

    for volcano in volcano_list:
        print(f"scraping {volcano["name"]}...")
        
        gvp = get_gvp_data(volcano)
        wiki = get_wikipedia_data(volcano["name"])
        
        volcano_data = {
            "id" : volcano["gvp_id"],
            "name": volcano["name"],
            "alternate_names": gvp["alternate_names"],
            "summary": wiki["summary"] or gvp["summary"],
            "location": {
                "country": gvp["location"]["country"],
                "region": gvp["location"]["region"],
                "coordinates": wiki["location"]["coordinates"] if wiki["location"]["coordinates"] != [0.0, 0.0] else gvp["location"]["coordinates"]
            },
            "elevation_m": wiki["elevation_m"] if wiki["elevation_m"] is not None else gvp["elevation_m"],
            "status": wiki["status"],
            "last_known_eruption": gvp["last_known_eruption"],
            "population": gvp["population"],
            "rock_types": gvp["rock_types"],
            "volcano_types": gvp["volcano_types"],
            "volcano_landform": gvp["volcano_landform"],
            "features": gvp["features"],
            "eruption_history": gvp["eruption_history"],
            "sources": [gvp["source"]],
            "scraped_at": datetime.now(timezone.utc).isoformat() + "Z"
            }
        def check_serializable(obj, path=""):
            if isinstance(obj, (datetime, set, bytes)):
                print(f"Found non-serializable {type(obj).__name__} at {path}: {obj}")
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    check_serializable(value, f"{path}.{key}" if path else key)
            elif isinstance(obj, list):
                for i, value in enumerate(obj):
                    check_serializable(value, f"{path}[{i}]" if path else f"[{i}]")
        
        check_serializable(volcano_data)
        
        volcanoes.append(volcano_data)
        time.sleep(1)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(volcanoes, f, indent=2)
    
    print(f"Saved {len(volcanoes)} volcanoes to {OUTPUT_FILE}")
 
 
 
def _parse_coordinate(coor_str):
    """
    Converts a coordinate like '37.748°N' to float 37.748, or '14.999°E' to 14.999
    """
    coor_str = coor_str.replace("°", "").strip()
    direction = coor_str[-1]
    try:   
        value = float(coor_str[:-1])
        return -value if direction in ["S", "W"] else value
    except (ValueError, IndexError):
        return 0.0
    
def _parse_elevation(ele_str):
    """
    Converts an elevation string like '3,357 m / 11,014 ft' to 3357.0.
    Returns None on parsing failure.
    """
    # Extract the metric part before the slash
    metric_part = ele_str.split("/")[0].strip() if "/" in ele_str else ele_str.strip()
    # Remove 'm' and commas
    metric_part = metric_part.replace("m", "").replace(",", "").strip()

    try:
        value = float(metric_part)
        return value
    except ValueError:
        return None
        
if __name__ == "__main__":
    scrape_all()
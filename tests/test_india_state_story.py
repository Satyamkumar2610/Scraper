import os
import json
import pytest
import pandas as pd
import networkx as nx
from scrapers.india_state_story_scraper import IndiaStateStoryScraper
from lineage.lineage_builder import LineageBuilder

@pytest.fixture
def setup_dirs(tmp_path):
    os.makedirs(tmp_path / "data/raw/india_state_story", exist_ok=True)
    os.makedirs(tmp_path / "data/processed/lineage", exist_ok=True)
    os.makedirs(tmp_path / "lineage", exist_ok=True)
    
    # Mock alias file
    alias_path = tmp_path / "lineage/district_aliases.json"
    with open(alias_path, "w") as f:
        json.dump({"Oldname": "NewName"}, f)
    
    return tmp_path

def test_clean_district_name(monkeypatch, setup_dirs):
    monkeypatch.setattr("lineage.lineage_builder.ALIASES_FILE", str(setup_dirs / "lineage/district_aliases.json"))
    builder = LineageBuilder()
    
    # Title casing & stripping
    assert builder.clean_district_name("  some district  ") == "Some District"
    # Alias mapping
    assert builder.clean_district_name("OldName") == "NewName"
    # NaN handling
    assert builder.clean_district_name(None) == ""

def test_lineage_edge_generation():
    builder = LineageBuilder()
    # Mock some events
    builder.events = pd.DataFrame([
        {
            "state": "StateA", 
            "parent_district": "Dist1", 
            "child_district": "Dist2", 
            "event_type": "SPLIT", 
            "effective_year": 2000, 
            "source_document": "test.csv"
        },
        {
            "state": "StateA", 
            "parent_district": "Dist3,Dist4", 
            "child_district": "Dist5", 
            "event_type": "MERGER", 
            "effective_year": 2005, 
            "source_document": "test.csv"
        }
    ])
    
    edges_df = builder.generate_lineage_edges()
    
    assert len(edges_df) == 3
    
    # Check split
    split_edge = edges_df[(edges_df["source_district"] == "Dist1") & (edges_df["target_district"] == "Dist2")]
    assert not split_edge.empty
    
    # Check merger
    merger_edge1 = edges_df[(edges_df["source_district"] == "Dist3") & (edges_df["target_district"] == "Dist5")]
    merger_edge2 = edges_df[(edges_df["source_district"] == "Dist4") & (edges_df["target_district"] == "Dist5")]
    assert not merger_edge1.empty
    assert not merger_edge2.empty

def test_build_lineage_graph(setup_dirs, monkeypatch):
    monkeypatch.setattr("lineage.lineage_builder.PROCESSED_DIR", str(setup_dirs / "data/processed/lineage"))
    
    builder = LineageBuilder()
    edges_df = pd.DataFrame([
        {"source_district": "A", "target_district": "B", "event_type": "SPLIT", "effective_year": 2000, "state": "S", "source": "src"}
    ])
    
    G = builder.build_lineage_graph(edges_df)
    
    assert G.has_node("A")
    assert G.has_node("B")
    assert G.has_edge("A", "B")
    
    # Check if files were created
    assert os.path.exists(setup_dirs / "data/processed/lineage/district_lineage_graph.gpickle")
    assert os.path.exists(setup_dirs / "data/processed/lineage/district_lineage_graph.json")

def test_circular_dependency_check(setup_dirs, monkeypatch):
    monkeypatch.setattr("lineage.lineage_builder.PROCESSED_DIR", str(setup_dirs / "data/processed/lineage"))
    builder = LineageBuilder()
    
    edges_df = pd.DataFrame([
        {"source_district": "A", "target_district": "B", "event_type": "RENAME", "effective_year": 2000, "state": "S", "source": "src"},
        {"source_district": "B", "target_district": "A", "event_type": "RENAME", "effective_year": 2001, "state": "S", "source": "src"}
    ])
    
    G = builder.build_lineage_graph(edges_df)
    builder.check_data_quality(edges_df, G)
    
    quality_file = setup_dirs / "data/processed/lineage/lineage_quality_report.csv"
    assert os.path.exists(quality_file)
    df = pd.read_csv(quality_file)
    assert not df.empty
    assert "CIRCULAR_LINEAGE" in df["issue_type"].values

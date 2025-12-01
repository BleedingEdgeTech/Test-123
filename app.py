#!/usr/bin/env python3
"""
MTG Card Recognition - Streamlit Web App

Starte mit: streamlit run app.py
"""

import streamlit as st
import requests
from PIL import Image
import io
import numpy as np
import cv2
from typing import Optional, Dict, List

# Page Config
st.set_page_config(
    page_title="MTG Card Recognition",
    page_icon="🃏",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1a1a2e;
        text-align: center;
        margin-bottom: 2rem;
    }
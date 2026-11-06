import sys
import os

# إضافة المجلد الرئيسي للمشروع لمسار البحث لكي يتمكن من قراءة server.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app

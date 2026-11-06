import sys
import os

# إضافة المجلد الرئيسي لمسار البحث لكي يتمكن من استيراد server.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app

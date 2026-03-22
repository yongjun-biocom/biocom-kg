# Streamlit Cloud 진입점 — src/app.py 실행
import runpy, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
runpy.run_path(os.path.join(os.path.dirname(__file__), "src", "app.py"), run_name="__main__")

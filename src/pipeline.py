import time
from src.stage_01_fetch_data import run_stage_fetch
from src.stage_02_prepare_data import run_stage_prepare
from src.stage_03_spatial_analysis import run_stage_analysis


class GNSSSelectionPipeline:
    def __init__(self):
        pass

    def run(self):
        start_time = time.time()
        print("==================================================")
        print(" Starting GNSS CORS Site Selection Pipeline ")
        print("==================================================")

        run_stage_fetch()
        run_stage_prepare()
        run_stage_analysis()

        elapsed = round(time.time() - start_time, 2)
        print("==================================================")
        print(f" Pipeline execution finished in {elapsed} seconds.")
        print("==================================================")
# ShanghaiT2DM / ShanghaiT1DM (real CGM)

`shanghai_t1dm_t2dm_figshare.zip` is the original, unmodified file from figshare.

- **Citation:** Zhao Q, Zhu J, Shen X, et al. Chinese diabetes datasets for data-driven machine learning.
  *Scientific Data* 10, 35 (2023). https://doi.org/10.1038/s41597-023-01940-7
- **Data:** https://doi.org/10.6084/m9.figshare.20444397
- **Licence:** Creative Commons Attribution 4.0 (CC BY 4.0). Redistributed here unchanged, with credit.

What GlycoRenal Twin uses: the `Shanghai_T2DM/` folder (100 people with type 2 diabetes, 15-minute CGM,
meal times, medicines) and `Shanghai_T2DM_Summary.xlsx`. The reader `src/pipeline/shanghai.py` unpacks the
zip into `extracted/` (git-ignored) on first use.

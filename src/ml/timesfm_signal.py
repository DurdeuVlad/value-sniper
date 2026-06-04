import numpy as np

_MODEL_INSTANCE = None  # module-level singleton to avoid repeated loading


def is_available() -> bool:
    try:
        import timesfm  # noqa: F401
        import torch    # noqa: F401
        return True
    except ImportError:
        return False


def _get_device(preferred: str = "auto") -> str:
    try:
        import torch
        if preferred == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return preferred
    except ImportError:
        return "cpu"


class TimesFMSignal:
    """
    Wraps Google TimesFM 2.5-200M for probabilistic price forecasting.
    Produces support zone estimates via lower quantile bands.
    """

    def __init__(self, device: str = "auto"):
        self.device = _get_device(device)
        self._model = None

    def _load_model(self):
        global _MODEL_INSTANCE
        if _MODEL_INSTANCE is not None:
            self._model = _MODEL_INSTANCE
            return

        import torch
        import timesfm

        torch.set_float32_matmul_precision("high")
        print(f"[TIMESFM] Loading model on {self.device.upper()} (first run downloads ~1GB)...")

        # Workaround: from_pretrained passes 'proxies' kwarg which __init__ rejects.
        # Manually download weights and load via the internal checkpoint loader.
        from huggingface_hub import hf_hub_download
        weights_path = hf_hub_download(
            repo_id="google/timesfm-2.5-200m-pytorch",
            filename=timesfm.TimesFM_2p5_200M_torch.WEIGHTS_FILENAME,
        )
        model = timesfm.TimesFM_2p5_200M_torch()
        model.model.load_checkpoint(weights_path, torch_compile=model.torch_compile)

        model.compile(
            timesfm.ForecastConfig(
                max_context=512,
                max_horizon=20,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )

        _MODEL_INSTANCE = model
        self._model = model
        print(f"[TIMESFM] Model ready on {self.device.upper()}")

    def forecast(self, prices: np.ndarray, horizon: int = 20) -> dict:
        """
        Run inference on a 1-D price array.

        Returns dict with keys:
          - 'q10_floor': min of 10th-percentile forecast band (strong support)
          - 'q25_floor': min of 25th-percentile forecast band (moderate support)
          - 'point_mean': mean of point forecast
          - 'device': device used
        """
        self._load_model()

        prices_f32 = prices.astype(np.float32)
        context = prices_f32[-512:]  # cap at max_context

        point, quantiles = self._model.forecast(
            horizon=horizon,
            inputs=[context],
        )
        # quantiles shape: (1, horizon, 10) — indices 0..9 = 10th..90th pct
        q10 = quantiles[0, :, 0]  # 10th percentile over horizon
        q25 = quantiles[0, :, 2]  # 30th percentile (index 2)

        return {
            "q10_floor": float(np.min(q10)),
            "q25_floor": float(np.min(q25)),
            "point_mean": float(np.mean(point[0])),
            "device": self.device,
        }

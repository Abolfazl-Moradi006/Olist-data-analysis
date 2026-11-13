"""Plot style and chart export."""
import matplotlib.pyplot as plt

from .config import CHARTS_DIR

BLUE = "#4C78A8"
LIGHT_BLUE = "#9ECAE9"
ORANGE = "#F58518"
RED = "#E45756"
GREEN = "#2E9E6B"
GRAY = "#7A7A7A"


def set_style() -> None:
    plt.rcParams.update({
        "figure.dpi": 100,
        "savefig.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "axes.titlesize": 13,
        "axes.grid": False,
        "font.size": 10,
        "legend.frameon": False,
    })


def save_fig(fig, name: str) -> None:
    """Save a figure to outputs/charts/<name>.png (overwrites, so reruns stay reproducible)."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHARTS_DIR / f"{name}.png", bbox_inches="tight", facecolor="white")


def thousands(ax, axis: str = "y") -> None:
    fmt = plt.FuncFormatter(lambda v, _: f"{v:,.0f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)
